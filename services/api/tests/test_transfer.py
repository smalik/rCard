"""Moving one person to another database (transfer.py), as when leaving the
Supabase preview for Cloud SQL."""

import base64
import os
from collections.abc import Iterator
from typing import Any
from urllib.parse import quote

import psycopg
import pytest
from fastapi.testclient import TestClient

from plytos_api.agents.model import NewCard, ProposalBody
from plytos_api.agents.store import AgentStore
from plytos_api.auth import find_or_create_user
from plytos_api.config import Settings
from plytos_api.db import Database
from plytos_api.imports.worker import ImportWorker
from plytos_api.keys import LocalKek, Vault
from plytos_api.main import create_app
from plytos_api.transfer import TransferError, main, plan, read_tables, transfer

from .conftest import DbUrls, fresh_database, main_content
from .resume_samples import promotions_text


def _kek() -> tuple[str, LocalKek]:
    key = os.urandom(32)
    return "local:" + base64.b64encode(key).decode(), LocalKek(key)


TARGET_SETTING, TARGET_KEK = _kek()


@pytest.fixture
def target_db() -> Iterator[DbUrls]:
    with fresh_database("plytos_transfer") as urls:
        yield urls


@pytest.fixture(scope="module")
def source(test_db: DbUrls, kek_setting: str) -> Iterator[TestClient]:
    app = create_app(
        Settings(env="test", database_url=test_db.app_url, kek=kek_setting, imports_inline=False)
    )
    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="module")
def source_kek(kek_setting: str) -> LocalKek:
    return LocalKek(base64.b64decode(kek_setting.removeprefix("local:")))


def _as(name: str) -> dict[str, str]:
    return {"X-Plytos-Dev-User": name}


@pytest.fixture(scope="module")
def someone(source: TestClient, db: Database, vault: Vault) -> str:
    """A person with a bit of everything: cards with history and a variant, a
    resume read from a file, a copy of it aimed at a target, a named version,
    the conversation, check-ins and a proposal."""
    me = _as("moving")
    kept = source.post(
        "/v1/imports",
        content=promotions_text().encode(),
        headers=me | {"X-Plytos-Filename": quote("Avery Quinn.txt")},
    )
    assert kept.status_code == 202, kept.text
    import_id = kept.json()["id"]
    ImportWorker(db, vault, None, retry_base_seconds=0).run_until_idle()
    imported = source.get(f"/v1/imports/{import_id}", headers=me).json()
    for card in imported["result"]["cards"]:
        approved = source.post(
            f"/v1/imports/{import_id}/cards/{card['ref']}/approve", json={}, headers=me
        )
        assert approved.status_code == 201, approved.text
    made = source.post("/v1/resumes/as-written", json={"import_id": import_id}, headers=me)
    assert made.status_code == 201, made.text
    resume_id = made.json()["resume"]["id"]
    named = source.post(
        f"/v1/resumes/{resume_id}/versions/1/name", json={"name": "Sent to Contoso"}, headers=me
    )
    assert named.status_code in (200, 201), named.text
    copy = source.post(
        f"/v1/resumes/{resume_id}/copies",
        json={"name": "Fintech", "target": "Fintech operations roles", "target_kind": "industry"},
        headers=me,
    )
    assert copy.status_code == 201, copy.text

    card = source.post(
        "/v1/cards",
        json={"kind": "accomplishment", "content": main_content().model_dump()},
        headers=me,
    ).json()
    saved = source.post(
        f"/v1/cards/{card['id']}/versions",
        json={
            "base_version_id": card["main"]["head"]["id"],
            "content": main_content(team_size="7").model_dump(),
        },
        headers=me,
    )
    assert saved.status_code == 201, saved.text
    target = source.post("/v1/targets", json={"kind": "industry", "name": "Finance"}, headers=me)
    variant = source.post(
        f"/v1/cards/{card['id']}/variants",
        json={
            "target_id": target.json()["id"],
            "content": {"framing": {"headline": "Close in 4 days"}},
        },
        headers=me,
    )
    assert variant.status_code == 201, variant.text

    said = source.post("/v1/conversation", json={"text": "Shipped it to 3 sites"}, headers=me)
    assert said.status_code == 201, said.text
    plan_body = {"week": -1, "weekday": 5, "time": "16:00", "time_zone": "America/Chicago"}
    assert source.put("/v1/check-ins", json=plan_body, headers=me).status_code == 200
    user = find_or_create_user(db, vault, "dev:moving")
    with db.as_user(user) as conn:
        AgentStore(conn, user, vault.cipher_for(conn, user)).propose(
            "stitcher",
            "new_card",
            ProposalBody(
                message="One win?", card=NewCard(kind="accomplishment", content=main_content())
            ),
        )

    # Somebody else, who stays behind.
    source.post(
        "/v1/cards",
        json={"kind": "accomplishment", "content": main_content("Not moving").model_dump()},
        headers=_as("staying"),
    )
    return "dev:moving"


def _everything(client: TestClient, me: dict[str, str]) -> dict[str, Any]:
    """What a person sees, read the way the app reads it."""
    seen: dict[str, Any] = {}
    for path in ("/v1/me", "/v1/cards", "/v1/targets", "/v1/imports", "/v1/resumes"):
        seen[path] = client.get(path, headers=me).json()
    seen["/v1/conversation"] = client.get("/v1/conversation", headers=me).json()
    seen["/v1/check-ins"] = client.get("/v1/check-ins", headers=me).json()
    seen["/v1/proposals"] = client.get("/v1/proposals", headers=me).json()
    for card in seen["/v1/cards"]:
        for part in ("", "/versions", "/verify"):
            path = f"/v1/cards/{card['id']}{part}"
            seen[path] = client.get(path, headers=me).json()
    for resume in seen["/v1/resumes"]["resumes"]:
        path = f"/v1/resumes/{resume['id']}"
        seen[path] = client.get(path, headers=me).json()
    for imported in seen["/v1/imports"]:
        path = f"/v1/imports/{imported['id']}"
        seen[path] = client.get(path, headers=me).json()
        original = client.get(f"{path}/original", headers=me)
        seen[f"{path}/original"] = (original.status_code, original.content)
    return seen


def _people(url: str) -> list[str]:
    with psycopg.connect(url) as conn:
        return [r[0] for r in conn.execute("select auth_subject from plytos.app_user").fetchall()]


def test_a_person_arrives_whole_and_readable(
    test_db: DbUrls,
    target_db: DbUrls,
    source: TestClient,
    source_kek: LocalKek,
    someone: str,
) -> None:
    before = _everything(source, _as("moving"))
    assert before["/v1/cards"] and before["/v1/resumes"]["resumes"]

    rehearsal = transfer(
        test_db.owner_url, source_kek, target_db.owner_url, TARGET_KEK,
        someone, "dev:moved", commit=False,
    )  # fmt: skip
    assert not rehearsal.committed
    assert _people(target_db.owner_url) == []

    report = transfer(
        test_db.owner_url, source_kek, target_db.owner_url, TARGET_KEK,
        someone, "dev:moved", commit=True,
    )  # fmt: skip
    assert report.counts == rehearsal.counts
    assert report.counts["plytos.app_user"] == 1 and report.counts["plytos_vault.user_key"] == 1
    for table in ("card", "card_line", "card_version", "target", "resume", "resume_version",
                  "resume_version_name", "resume_import", "message", "proposal",
                  "check_in_plan", "event"):  # fmt: skip
        assert report.counts[f"plytos.{table}"] > 0, table
    # Only this person came, under the new sign-in, with their key resealed.
    assert _people(target_db.owner_url) == ["dev:moved"]
    with psycopg.connect(target_db.owner_url) as conn:
        assert conn.execute("select kek_name from plytos_vault.user_key").fetchone() == (
            TARGET_KEK.name,
        )

    app = create_app(
        Settings(
            env="test", database_url=target_db.app_url, kek=TARGET_SETTING, imports_inline=False
        )
    )
    with TestClient(app) as moved:
        assert _everything(moved, _as("moved")) == before
        # The copy carries on as the person's own: the next version follows.
        card = before["/v1/cards"][0]
        head = before[f"/v1/cards/{card['id']}"]["main"]["head"]
        saved = moved.post(
            f"/v1/cards/{card['id']}/versions",
            json={"base_version_id": head["id"], "content": main_content("Next").model_dump()},
            headers=_as("moved"),
        )
        assert saved.status_code == 201, saved.text
        assert saved.json()["version"]["number"] == head["number"] + 1

    # The source is untouched.
    assert _everything(source, _as("moving")) == before

    with pytest.raises(TransferError, match="already in the target"):
        transfer(
            test_db.owner_url, source_kek, target_db.owner_url, TARGET_KEK,
            someone, "dev:moved-again", commit=True,
        )  # fmt: skip


def test_an_empty_account_made_first_gives_way_and_a_used_one_doesnt(
    test_db: DbUrls, target_db: DbUrls, source_kek: LocalKek, someone: str
) -> None:
    target = Database(target_db.app_url, max_size=2)
    target.open()
    try:
        vault = Vault(TARGET_KEK)
        early = find_or_create_user(target, vault, "dev:early")
        used = find_or_create_user(target, vault, "dev:used")
        with target.as_user(used) as conn:
            conn.execute(
                "insert into plytos.target (owner_id, kind, name_ciphertext)"
                " values (%s, 'custom', %s)",
                (used, vault.cipher_for(conn, used).encrypt(b"x", b"test")),
            )
    finally:
        target.close()

    with pytest.raises(TransferError, match="already has things"):
        transfer(
            test_db.owner_url, source_kek, target_db.owner_url, TARGET_KEK,
            someone, "dev:used", commit=True,
        )  # fmt: skip
    report = transfer(
        test_db.owner_url, source_kek, target_db.owner_url, TARGET_KEK,
        someone, "dev:early", commit=True,
    )  # fmt: skip
    assert report.replaced_empty_user
    with psycopg.connect(target_db.owner_url) as conn:
        ids = conn.execute(
            "select id from plytos.app_user where auth_subject = 'dev:early'"
        ).fetchall()
    assert ids == [(report.user_id,)] and report.user_id != early


def test_nothing_is_copied_when_something_is_off(
    test_db: DbUrls, target_db: DbUrls, source_kek: LocalKek, someone: str
) -> None:
    def attempt(**changes: Any) -> None:
        args: dict[str, Any] = {
            "source_url": test_db.owner_url,
            "source_kek": source_kek,
            "target_url": target_db.owner_url,
            "target_kek": TARGET_KEK,
            "from_subject": someone,
            "to_subject": "dev:moved",
            "commit": True,
        }
        transfer(**(args | changes))

    with pytest.raises(TransferError, match="nobody signs in"):
        attempt(from_subject="dev:nobody")
    with pytest.raises(TransferError, match="different key"):
        attempt(source_kek=_kek()[1])
    with pytest.raises(TransferError, match="name the subject"):
        attempt(to_subject="")
    with psycopg.connect(target_db.owner_url, autocommit=True) as conn:
        conn.execute(
            "delete from plytos_meta.schema_migration"
            " where version = (select max(version) from plytos_meta.schema_migration)"
        )
    with pytest.raises(TransferError, match="different migrations"):
        attempt()
    assert _people(target_db.owner_url) == []


def test_tables_that_point_at_each_other_are_filled_in_afterwards(test_db: DbUrls) -> None:
    with psycopg.connect(test_db.owner_url) as conn:
        steps = plan(read_tables(conn))
    order = [t.name for t in steps.order]
    assert order[0] == "plytos.app_user"
    assert order.index("plytos.card") < order.index("plytos.card_line")
    assert order.index("plytos.card_line") < order.index("plytos.card_version")
    assert order.index("plytos.resume") < order.index("plytos.resume_version")
    assert sorted((fk.table, fk.columns) for fk in steps.deferred) == [
        ("plytos.card_line", ("head_version_id",)),
        ("plytos.resume", ("head_version_id",)),
    ]


def test_the_command_rehearses_unless_told_to_copy(
    test_db: DbUrls,
    target_db: DbUrls,
    kek_setting: str,
    someone: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--from-subject", someone, "--to-subject", "dev:moved"]) == 2
    assert "PLYTOS_TRANSFER_SOURCE_URL" in capsys.readouterr().err
    monkeypatch.setenv("PLYTOS_TRANSFER_SOURCE_URL", test_db.owner_url)
    monkeypatch.setenv("PLYTOS_TRANSFER_SOURCE_KEK", kek_setting)
    monkeypatch.setenv("PLYTOS_TRANSFER_TARGET_URL", target_db.owner_url)
    monkeypatch.setenv("PLYTOS_TRANSFER_TARGET_KEK", TARGET_SETTING)

    assert main(["--from-subject", someone, "--to-subject", "dev:moved"]) == 0
    printed = capsys.readouterr().out
    assert "plytos.card " in printed and "Rehearsal only" in printed
    # Counts and table names only: no addresses or keys.
    assert target_db.owner_url not in printed and TARGET_SETTING not in printed
    assert _people(target_db.owner_url) == []

    assert main(["--from-subject", "dev:nobody", "--to-subject", "dev:moved"]) == 1
    assert "Nothing copied" in capsys.readouterr().err
    assert main(["--from-subject", someone, "--to-subject", "dev:moved", "--commit"]) == 0
    assert "Copied." in capsys.readouterr().out
    assert _people(target_db.owner_url) == ["dev:moved"]
