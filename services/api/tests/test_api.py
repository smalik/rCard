from collections.abc import Iterator
from typing import Any
from urllib.parse import quote, unquote
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from plytos_api.agents.model import NewCard, NewResume, ProposalBody, Rewording
from plytos_api.agents.store import AgentStore
from plytos_api.auth import find_or_create_user
from plytos_api.cards.model import Framing
from plytos_api.cards.repository import Author
from plytos_api.config import Settings
from plytos_api.db import Database
from plytos_api.imports.worker import ImportWorker
from plytos_api.keys import Vault
from plytos_api.main import create_app
from plytos_api.resumes.model import ResumeContent
from plytos_api.resumes.store import ResumeStore

from .conftest import DbUrls, main_content
from .resume_samples import promotions_text, title_first_text


@pytest.fixture(scope="module")
def client(test_db: DbUrls, kek_setting: str) -> Iterator[TestClient]:
    app = create_app(
        Settings(env="test", database_url=test_db.app_url, kek=kek_setting, imports_inline=False)
    )
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def reads(db: Database, vault: Vault) -> ImportWorker:
    """Reads uploads the way the background worker does, when a test asks."""
    return ImportWorker(db, vault, None, retry_base_seconds=0)


def as_user(name: str) -> dict[str, str]:
    return {"X-Plytos-Dev-User": name}


def upload(
    client: TestClient, reads: ImportWorker, data: bytes, name: str, me: dict[str, str]
) -> dict[str, Any]:
    """Uploads a resume, lets the worker read it, and returns the import."""
    kept = client.post("/v1/imports", content=data, headers=me | {"X-Plytos-Filename": quote(name)})
    assert kept.status_code == 202, kept.text
    reads.run_until_idle()
    view: dict[str, Any] = client.get(f"/v1/imports/{kept.json()['id']}", headers=me).json()
    assert view["state"] == "read"
    return view


def test_every_response_forbids_indexing_and_caching(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert "noindex" in response.headers["x-robots-tag"]
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/v1/cards").headers["x-robots-tag"].startswith("noindex")


def test_requests_without_a_person_are_refused(client: TestClient) -> None:
    assert client.get("/v1/cards").status_code == 401


def test_prod_refuses_until_sign_in_exists(test_db: DbUrls) -> None:
    settings = Settings(
        env="prod",
        database_url=test_db.app_url,
        kek="gcp-kms:projects/p/locations/us/keyRings/r/cryptoKeys/k",
        imports_inline=False,
    )
    with TestClient(create_app(settings)) as prod:
        assert prod.get("/v1/cards", headers=as_user("someone")).status_code == 501
        assert prod.get("/docs").status_code == 404
        assert prod.get("/openapi.json").status_code == 404


def test_card_flow_over_http(client: TestClient) -> None:
    me = as_user("api-flow")
    created = client.post(
        "/v1/cards",
        json={"kind": "accomplishment", "content": main_content().model_dump()},
        headers=me,
    )
    assert created.status_code == 201, created.text
    card = created.json()
    card_id, v1 = card["id"], card["main"]["head"]["id"]

    saved = client.post(
        f"/v1/cards/{card_id}/versions",
        json={"base_version_id": v1, "content": main_content(team_size="7").model_dump()},
        headers=me,
    )
    assert saved.status_code == 201, saved.text
    assert saved.json()["version"]["number"] == 2

    stale = client.post(
        f"/v1/cards/{card_id}/versions",
        json={"base_version_id": v1, "content": main_content(team_size="8").model_dump()},
        headers=me,
    )
    assert stale.status_code == 409
    assert stale.json()["current_head_id"] == saved.json()["version"]["id"]

    target = client.post("/v1/targets", json={"kind": "industry", "name": "Finance"}, headers=me)
    assert target.status_code == 201
    target_id = target.json()["id"]

    bad = client.post(
        f"/v1/cards/{card_id}/variants",
        json={"target_id": target_id, "content": {"framing": {"headline": "Saved $2M"}}},
        headers=me,
    )
    assert bad.status_code == 422
    assert bad.json()["problems"]

    good = client.post(
        f"/v1/cards/{card_id}/variants",
        json={"target_id": target_id, "content": {"framing": {"headline": "Close in 4 days"}}},
        headers=me,
    )
    assert good.status_code == 201, good.text
    assert good.json()["variants"][0]["based_on_main_number"] == 2

    assert [
        v["number"] for v in client.get(f"/v1/cards/{card_id}/versions", headers=me).json()
    ] == [
        1,
        2,
    ]
    assert client.get(f"/v1/cards/{card_id}/verify", headers=me).json() == {
        "ok": True,
        "problems": [],
    }
    listed = client.get("/v1/cards", headers=me).json()
    assert [c["id"] for c in listed] == [card_id]

    stranger = as_user("someone-else")
    assert client.get(f"/v1/cards/{card_id}", headers=stranger).status_code == 404
    assert client.get("/v1/cards", headers=stranger).json() == []


def test_the_library_keeps_attachments_and_the_persons_order(client: TestClient) -> None:
    me = as_user("api-library")

    def card(kind: str, headline: str, parent: str | None = None, **extra: Any) -> str:
        content = {"parent": parent, "facts": {}, "framing": {"headline": headline}, **extra}
        made = client.post("/v1/cards", json={"kind": kind, "content": content}, headers=me)
        assert made.status_code == 201, made.text
        return str(made.json()["id"])

    job = card("employment", "Contoso Bank", facts={"employer": "Contoso Bank"})
    title = card("position", "ETL Developer", job, facts={"title": "ETL Developer"})
    paper = {"kind": "paper", "url": "https://example.org/loads.pdf", "title": "Nightly loads"}
    first = card("accomplishment", "Built nightly loads", title, attachments=[paper])
    second = card("accomplishment", "Cut load time by 40%", title)

    library = client.get("/v1/library", headers=me).json()
    by_id = {c["id"]: c for c in library}
    assert by_id[first]["content"]["attachments"] == [paper | {"note": ""}]
    assert by_id[second]["content"]["attachments"] == []
    assert by_id[first]["version"] == 1 and by_id[first]["version_author"] == "person"
    detail = client.get(f"/v1/cards/{first}", headers=me).json()
    assert by_id[first]["version_id"] == detail["main"]["head"]["id"]
    under = [c["id"] for c in library if c["parent_id"] == title]
    assert under == [first, second]

    moved = client.post(
        "/v1/cards/reorder", json={"parent_id": title, "card_ids": [second, first]}, headers=me
    )
    assert moved.status_code == 204, moved.text
    library = client.get("/v1/library", headers=me).json()
    assert [c["id"] for c in library if c["parent_id"] == title] == [second, first]

    # A card that sits elsewhere, or someone else's, can't be ordered here.
    wrong = client.post(
        "/v1/cards/reorder", json={"parent_id": title, "card_ids": [second, job]}, headers=me
    )
    assert wrong.status_code == 409
    stranger = as_user("someone-else-library")
    theirs = client.post(
        "/v1/cards/reorder",
        json={"parent_id": title, "card_ids": [first, second]},
        headers=stranger,
    )
    assert theirs.status_code == 409
    assert client.get("/v1/library", headers=stranger).json() == []
    library = client.get("/v1/library", headers=me).json()
    assert [c["id"] for c in library if c["parent_id"] == title] == [second, first]

    script = {"kind": "link", "url": "javascript:alert(1)", "title": "Nope"}
    refused = client.post(
        "/v1/cards",
        json={
            "kind": "accomplishment",
            "content": {"framing": {"headline": "x"}, "attachments": [script]},
        },
        headers=me,
    )
    assert refused.status_code == 422


def test_unknown_parent_target_is_not_found(client: TestClient) -> None:
    response = client.post(
        "/v1/targets",
        json={
            "kind": "company",
            "name": "JP Morgan",
            "parent_id": "01890000-0000-7000-8000-000000000000",
        },
        headers=as_user("parent-check"),
    )
    assert response.status_code == 404


def test_resume_import_keeps_the_original_and_saves_only_approved_cards(
    client: TestClient, reads: ImportWorker
) -> None:
    from .resume_samples import consultant_docx

    me = as_user("importer")
    before = client.get("/v1/cards", headers=me).json()
    data = consultant_docx()
    response = client.post(
        "/v1/imports",
        content=data,
        headers={**me, "X-Plytos-Filename": "Casey%20Morgan%20Resume.docx"},
    )
    # Kept at once and read in the background.
    assert response.status_code == 202, response.text
    assert response.headers["cache-control"] == "no-store"
    kept = response.json()
    import_id = kept["id"]
    assert (kept["state"], kept["stage"], kept["error_code"]) == ("reading", None, None)
    assert kept["file"] == {"format": "docx", "size": len(data), "name": "Casey Morgan Resume.docx"}
    waiting = client.get(f"/v1/imports/{import_id}", headers=me).json()
    assert waiting["state"] == "reading" and waiting["result"] is None
    assert waiting["to_settle"] == []
    [listed] = [s for s in client.get("/v1/imports", headers=me).json() if s["id"] == import_id]
    assert (listed["state"], listed["cards"]) == ("reading", 0)
    unread = client.post(
        f"/v1/imports/{import_id}/cards/card-1/decision", json={"state": "later"}, headers=me
    )
    assert unread.status_code == 409 and "still being read" in unread.json()["detail"]

    reads.run_until_idle()
    status_now = client.get(f"/v1/imports/{import_id}/status", headers=me).json()
    assert (status_now["state"], status_now["stage"]) == ("read", None)
    view = client.get(f"/v1/imports/{import_id}", headers=me).json()
    assert view["state"] == "read"
    assert view["progress"] == {"settled": {}, "cards": {}, "edits": {}, "moves": {}}
    assert len(view["result"]["roles"]) == 4
    assert client.get("/v1/cards", headers=me).json() == before

    original = client.get(f"/v1/imports/{import_id}/original", headers=me)
    assert original.status_code == 200
    assert original.content == data
    assert original.headers["content-type"].startswith("application/vnd.openxml")
    assert unquote(original.headers["x-plytos-filename"]) == "Casey Morgan Resume.docx"

    [summary] = [s for s in client.get("/v1/imports", headers=me).json() if s["id"] == import_id]
    assert summary["cards"] == len(view["result"]["cards"])
    assert summary["approved"] == 0
    assert summary["to_settle"] >= 1

    # The resume quotes the same result as ~30% and 25%. Picking 25% rewrites
    # the card that said 30%, and only that card.
    findings = view["result"]["findings"]
    conflict = next(i for i, f in enumerate(findings) if f["rule"] == "consistency.figures")
    assert conflict in view["to_settle"]
    assert all(findings[i]["about"] == "cards" for i in view["to_settle"])
    assert [loc["figure"] for loc in findings[conflict]["locations"]] == ["30%", "25%"]
    bad = client.post(
        f"/v1/imports/{import_id}/settle",
        json={"finding": conflict, "answer": "chosen", "value": "40%"},
        headers=me,
    )
    assert bad.status_code == 409
    settled = client.post(
        f"/v1/imports/{import_id}/settle",
        json={"finding": conflict, "answer": "chosen", "value": "25%"},
        headers=me,
    )
    assert settled.status_code == 200, settled.text
    progress = settled.json()
    [ref] = progress["settled"][str(conflict)]["changed"]
    edited = progress["edits"][ref]
    assert "~25%" in edited["framing"]["headline"]
    assert edited["facts"]["figures"] == ["25%"]

    # Changing the answer puts the import's own wording back.
    unsure = client.post(
        f"/v1/imports/{import_id}/settle",
        json={"finding": conflict, "answer": "later"},
        headers=me,
    ).json()
    assert unsure["edits"] == {}
    client.post(
        f"/v1/imports/{import_id}/settle",
        json={"finding": conflict, "answer": "chosen", "value": "25%"},
        headers=me,
    )

    # The card sits under a position, which sits under an employment: approving it
    # first is refused, so nothing lands loose.
    proposals = {c["ref"]: c for c in view["result"]["cards"]}
    early = client.post(f"/v1/imports/{import_id}/cards/{ref}/approve", json={}, headers=me)
    assert early.status_code == 409
    assert "first" in early.json()["detail"]
    chain: list[str] = []
    up_ref = proposals[ref]["parent_ref"]
    while up_ref is not None:
        chain.insert(0, up_ref)
        up_ref = proposals[up_ref]["parent_ref"]
    # The highlight names the client, so it sits under that engagement.
    assert [proposals[r]["kind"] for r in chain] == ["employment", "position", "engagement"]
    saved: dict[str, str] = {}
    for step in chain:
        up = client.post(f"/v1/imports/{import_id}/cards/{step}/approve", json={}, headers=me)
        assert up.status_code == 201, up.text
        saved[step] = up.json()["card"]["id"]

    approved = client.post(f"/v1/imports/{import_id}/cards/{ref}/approve", json={}, headers=me)
    assert approved.status_code == 201, approved.text
    card = approved.json()["card"]
    assert card["status"] == "approved"
    assert card["parent_id"] == saved[chain[-1]]
    assert card["main"]["content"]["parent"] == saved[chain[-1]]
    assert "~25%" in card["main"]["content"]["framing"]["headline"]
    assert card["main"]["head"]["author_kind"] == "person"
    again = client.post(f"/v1/imports/{import_id}/cards/{ref}/approve", json={}, headers=me)
    assert again.status_code == 409

    later = client.post(
        f"/v1/imports/{import_id}/cards/card-1/decision", json={"state": "later"}, headers=me
    )
    assert later.json()["cards"]["card-1"] == {"state": "later", "card_id": None}
    assert (
        client.post(
            f"/v1/imports/{import_id}/cards/card-999/decision",
            json={"state": "later"},
            headers=me,
        ).status_code
        == 404
    )
    assert len(client.get("/v1/cards", headers=me).json()) == len(before) + 4

    someone = as_user("someone-else")
    assert client.get(f"/v1/imports/{import_id}", headers=someone).status_code == 404
    assert client.get(f"/v1/imports/{import_id}/status", headers=someone).status_code == 404
    assert client.post(f"/v1/imports/{import_id}/read-again", headers=someone).status_code == 404
    assert client.get(f"/v1/imports/{import_id}/original", headers=someone).status_code == 404
    assert client.delete(f"/v1/imports/{import_id}", headers=someone).status_code == 404
    assert client.get("/v1/imports", headers=someone).json() == []

    assert client.delete(f"/v1/imports/{import_id}", headers=me).status_code == 204
    assert client.get(f"/v1/imports/{import_id}", headers=me).status_code == 404
    assert len(client.get("/v1/cards", headers=me).json()) == len(before) + 4


def test_resume_import_refuses_bad_files(client: TestClient) -> None:
    me = as_user("bad-files")
    old_doc = client.post("/v1/imports", content=b"\xd0\xcf\x11\xe0" + b"\0" * 64, headers=me)
    assert old_doc.status_code == 422
    assert ".docx" in old_doc.json()["detail"]
    too_big = client.post("/v1/imports", content=b"x" * (5 * 1024 * 1024 + 1), headers=me)
    assert too_big.status_code == 413
    assert client.post("/v1/imports", content=b"", headers=me).status_code == 422
    assert client.post("/v1/imports", content=b"hello").status_code == 401
    assert client.get("/v1/imports", headers=me).json() == []


def test_conversation_over_http(client: TestClient, db: Database, vault: Vault) -> None:
    me, other = as_user("api-talk"), as_user("api-talk-other")
    said = client.post(
        "/v1/conversation", json={"text": "Shipped the routing tool to 3 sites"}, headers=me
    )
    assert said.status_code == 201, said.text
    assert said.json()["author"] == "person"
    assert client.get("/v1/conversation", headers=me).json() == [said.json()]
    assert client.get("/v1/conversation", headers=other).json() == []
    [run] = client.get("/v1/agent-runs", headers=me).json()
    assert (run["agent"], run["state"]) == ("listener", "queued")
    too_long = client.post("/v1/conversation", json={"text": "x" * 4001}, headers=me)
    assert too_long.status_code == 422
    assert client.get("/v1/proposals", headers=me).json() == []

    user = find_or_create_user(db, vault, "dev:api-talk")
    card = NewCard(kind="accomplishment", content=main_content())
    with db.as_user(user) as conn:
        store = AgentStore(conn, user, vault.cipher_for(conn, user))
        keep_id = store.propose(
            "stitcher", "new_card", ProposalBody(message="One win?", card=card)
        ).id
        drop_id = store.propose(
            "stitcher", "new_card", ProposalBody(message="Another?", card=card)
        ).id
    assert len(client.get("/v1/proposals", headers=me).json()) == 2
    assert client.post(f"/v1/proposals/{keep_id}/keep", json={}, headers=other).status_code == 404

    kept = client.post(f"/v1/proposals/{keep_id}/keep", json={}, headers=me)
    assert kept.status_code == 201, kept.text
    assert kept.json()["proposal"]["state"] == "kept"
    assert kept.json()["card"]["main"]["head"]["author_kind"] == "ai"
    again = client.post(f"/v1/proposals/{keep_id}/keep", json={}, headers=me)
    assert again.status_code == 409

    dropped = client.post(f"/v1/proposals/{drop_id}/dismiss", headers=me)
    assert dropped.status_code == 200 and dropped.json()["state"] == "dismissed"
    assert client.get("/v1/proposals", headers=me).json() == []
    for state, proposal_id in (("kept", keep_id), ("dismissed", drop_id)):
        listed = client.get("/v1/proposals", params={"state": state}, headers=me).json()
        assert [p["id"] for p in listed] == [str(proposal_id)]


def test_sharing_a_resume_in_the_conversation(client: TestClient, reads: ImportWorker) -> None:
    me, other = as_user("api-resume"), as_user("api-resume-other")
    shared = client.post(
        "/v1/conversation/resume",
        content=promotions_text().encode(),
        headers=me | {"X-Plytos-Filename": quote("Avery Quinn.txt")},
    )
    assert shared.status_code == 201, shared.text
    body = shared.json()
    [person] = body["messages"]
    assert person["author"] == "person" and person["import_id"] == body["resume"]["id"]
    assert body["resume"]["file"]["name"] == "Avery Quinn.txt"
    assert (body["resume"]["state"], body["resume"]["cards"]) == ("reading", 0)

    # Plytos answers once the worker has read it, and only once.
    reads.run_until_idle()
    reads.run_until_idle()
    person_again, plytos = client.get("/v1/conversation", headers=me).json()
    assert person_again["id"] == person["id"]
    assert plytos["author"] == "plytos" and plytos["text"].startswith("I read it:")
    assert plytos["import_id"] == body["resume"]["id"]
    [resume] = client.get("/v1/imports", headers=me).json()
    assert resume["state"] == "read" and resume["cards"] > 0 and resume["approved"] == 0
    assert client.get("/v1/conversation", headers=other).json() == []
    assert client.get("/v1/agent-runs", headers=me).json() == []
    empty = client.post("/v1/conversation/resume", content=b"", headers=me)
    assert empty.status_code == 422
    old_doc = client.post(
        "/v1/conversation/resume", content=b"\xd0\xcf\x11\xe0" + b"\0" * 64, headers=me
    )
    assert old_doc.status_code == 422


def test_a_reading_that_fails_says_so_and_can_be_tried_again(
    client: TestClient, reads: ImportWorker
) -> None:
    me = as_user("api-read-fails")
    broken = b"%PDF-1.7\n" + b"this is not really a PDF\n" * 10
    shared = client.post(
        "/v1/conversation/resume",
        content=broken,
        headers=me | {"X-Plytos-Filename": quote("Resume.pdf")},
    ).json()
    import_id = shared["resume"]["id"]
    reads.run_until_idle()
    failed = client.get(f"/v1/imports/{import_id}/status", headers=me).json()
    assert (failed["state"], failed["error_code"]) == ("failed", "unreadable")
    said = client.get("/v1/conversation", headers=me).json()
    assert [m["author"] for m in said] == ["person", "plytos"]
    assert said[-1]["text"].startswith("I couldn't read that file.")

    again = client.post(f"/v1/imports/{import_id}/read-again", headers=me)
    assert again.status_code == 200
    assert (again.json()["state"], again.json()["error_code"]) == ("reading", None)
    reads.run_until_idle()
    assert client.get(f"/v1/imports/{import_id}/status", headers=me).json()["state"] == "failed"
    # Plytos says how each reading went, once.
    said = client.get("/v1/conversation", headers=me).json()
    assert [m["author"] for m in said] == ["person", "plytos", "plytos"]
    reads.run_until_idle()
    assert len(client.get("/v1/conversation", headers=me).json()) == 3

    read = upload(client, reads, promotions_text().encode(), "Avery Quinn.txt", me)
    refused = client.post(f"/v1/imports/{read['id']}/read-again", headers=me)
    assert refused.status_code == 409


def test_check_ins_over_http(client: TestClient) -> None:
    me, other = as_user("api-check-ins"), as_user("api-check-ins-other")
    assert client.get("/v1/check-ins", headers=me).json() == {
        "plan": None,
        "label": None,
        "next_at": None,
    }
    plan = {"week": -1, "weekday": 5, "time": "16:00", "time_zone": "America/Chicago"}
    saved = client.put("/v1/check-ins", json=plan, headers=me)
    assert saved.status_code == 200, saved.text
    check_ins = saved.json()["check_ins"]
    assert check_ins["plan"] == plan | {"state": "on"}
    assert check_ins["label"] == "The last Friday of the month at 4 PM"
    assert check_ins["next_at"] is not None
    message = saved.json()["message"]
    assert message["author"] == "plytos"
    assert message["text"].startswith("Got it. I'll check in once a month, on the last Friday")
    assert client.get("/v1/conversation", headers=me).json() == [message]
    assert client.get("/v1/check-ins", headers=me).json() == check_ins
    assert client.get("/v1/check-ins", headers=other).json()["plan"] is None

    off = client.put("/v1/check-ins", json=plan | {"state": "off"}, headers=me)
    assert off.status_code == 200, off.text
    assert off.json()["check_ins"]["next_at"] is None
    assert off.json()["message"]["text"].startswith("Okay, no check-ins")

    for bad in (
        plan | {"time_zone": "Mars/Olympus"},
        plan | {"time": "25:00"},
        plan | {"week": 5},
        plan | {"weekday": 0},
        plan | {"weekdays": [1, 2]},
        plan | {"channel": "text_message"},
    ):
        refused = client.put("/v1/check-ins", json=bad, headers=me)
        assert refused.status_code == 422, bad
    unknown = client.put("/v1/check-ins", json=plan | {"time_zone": "Mars/Olympus"}, headers=me)
    assert unknown.json()["detail"] == "Plytos doesn't know that time zone."


def test_bringing_a_resume_in_again_carries_on_the_same_cards(
    client: TestClient, reads: ImportWorker
) -> None:
    me, other = as_user("api-again"), as_user("api-again-other")
    text = title_first_text().encode()
    first = upload(client, reads, text, "Robin Diaz.txt", me)
    kept = {}
    for card in first["result"]["cards"]:
        approved = client.post(
            f"/v1/imports/{first['id']}/cards/{card['ref']}/approve", json={}, headers=me
        )
        assert approved.status_code == 201, approved.text
        kept[card["ref"]] = approved.json()["card"]["id"]

    again = upload(client, reads, text, "Robin Diaz.txt", me)
    assert {ref: m["card_id"] for ref, m in again["matches"].items()} == kept
    assert all(m["same"] for m in again["matches"].values())
    matches = client.get(f"/v1/imports/{again['id']}/matches", headers=me)
    assert matches.json() == again["matches"]
    assert client.get(f"/v1/imports/{again['id']}/matches", headers=other).status_code == 404

    url = f"/v1/imports/{again['id']}/cards"
    linked = client.post(f"{url}/card-1/approve", json={"choice": "keep"}, headers=me)
    assert linked.status_code == 201 and linked.json()["card"]["id"] == kept["card-1"]
    separate = client.post(f"{url}/card-7/approve", json={"choice": "separate"}, headers=me)
    assert separate.status_code == 201 and separate.json()["card"]["id"] != kept["card-7"]
    # A choice it doesn't know is refused.
    refused = client.post(f"{url}/card-2/approve", json={"choice": "sideways"}, headers=me)
    assert refused.status_code == 422


def test_resume_flow_over_http(client: TestClient, reads: ImportWorker) -> None:
    me, other = as_user("api-resumes"), as_user("api-resumes-other")
    imported = upload(client, reads, promotions_text().encode(), "Avery Quinn.txt", me)
    import_id = imported["id"]
    assert client.get("/v1/resumes", headers=me).json() == {"resumes": [], "ready": []}
    nothing = client.post("/v1/resumes/as-written", json={"import_id": import_id}, headers=me)
    assert nothing.status_code == 422
    for card in imported["result"]["cards"]:
        approved = client.post(
            f"/v1/imports/{import_id}/cards/{card['ref']}/approve", json={}, headers=me
        )
        assert approved.status_code == 201, approved.text
    [ready] = client.get("/v1/resumes", headers=me).json()["ready"]
    assert ready["id"] == import_id

    made = client.post("/v1/resumes/as-written", json={"import_id": import_id}, headers=me)
    assert made.status_code == 201, made.text
    resume, page = made.json()["resume"], made.json()["page"]
    resume_id, v1 = resume["id"], resume["head"]["id"]
    assert resume["import_id"] == import_id and resume["head"]["number"] == 1
    assert page["header"]["name"] == "Avery Quinn"
    assert page["entries"][0]["employer"] == "Northwind Logistics"
    again = client.post("/v1/resumes/as-written", json={"import_id": import_id}, headers=me)
    assert again.json()["resume"]["id"] == resume_id
    listed = client.get("/v1/resumes", headers=me).json()
    assert [r["id"] for r in listed["resumes"]] == [resume_id] and listed["ready"] == []

    content = resume["content"]
    first_entry = content["entries"][0]
    content["entries"] = content["entries"][1:]
    preview = client.post(f"/v1/resumes/{resume_id}/preview", json=content, headers=me)
    assert preview.status_code == 200, preview.text
    assert first_entry["card"] in [e["card"] for e in preview.json()["left_out"]]
    assert (
        client.get(f"/v1/resumes/{resume_id}", headers=me).json()["resume"]["head"]["number"] == 1
    )
    saved = client.post(
        f"/v1/resumes/{resume_id}/versions",
        json={"base_version_id": v1, "content": content},
        headers=me,
    )
    assert saved.status_code == 201, saved.text
    v2 = saved.json()["resume"]["head"]["id"]
    assert [e["card"] for e in saved.json()["page"]["left_out"]].count(first_entry["card"]) == 1
    stale = client.post(
        f"/v1/resumes/{resume_id}/versions",
        json={"base_version_id": v1, "content": content},
        headers=me,
    )
    assert stale.status_code == 409 and stale.json()["current_head_id"] == v2

    old = client.get(f"/v1/resumes/{resume_id}/versions/1", headers=me).json()
    assert old["version"]["number"] == 1 and old["content"]["entries"][0] == first_entry
    restored = client.post(
        f"/v1/resumes/{resume_id}/restore", json={"number": 1, "base_version_id": v2}, headers=me
    )
    assert restored.status_code == 201, restored.text
    assert restored.json()["resume"]["head"]["note"] == "Back to version 1"
    named = client.post(
        f"/v1/resumes/{resume_id}/versions/3/name", json={"name": "Sent to Contoso"}, headers=me
    )
    assert named.json()["versions"][2]["names"] == ["Sent to Contoso"]

    copy = client.post(
        f"/v1/resumes/{resume_id}/copies",
        json={"name": "Fintech", "target": "Fintech operations roles", "target_kind": "industry"},
        headers=me,
    )
    assert copy.status_code == 201, copy.text
    copy_id = copy.json()["resume"]["id"]
    assert copy.json()["resume"]["parent_name"] == "My resume"
    assert copy.json()["resume"]["target_name"] == "Fintech operations roles"

    head = restored.json()["resume"]["head"]["id"]
    trimmed = restored.json()["resume"]["content"]
    trimmed["context"] = []
    client.post(
        f"/v1/resumes/{resume_id}/versions",
        json={"base_version_id": head, "content": trimmed},
        headers=me,
    )
    reviewed = client.get(f"/v1/resumes/{copy_id}/parent-changes", headers=me).json()
    changes = reviewed["changes"]
    assert reviewed["parent_version_id"] is not None
    assert [c["change"]["kind"] for c in changes] == ["context_removed"]
    assert changes[0]["label"].startswith("Removed “")
    taken = client.post(
        f"/v1/resumes/{copy_id}/take",
        json={
            "keys": [changes[0]["change"]["key"]],
            "base_version_id": copy.json()["resume"]["head"]["id"],
            "parent_version_id": reviewed["parent_version_id"],
        },
        headers=me,
    )
    assert taken.status_code == 201, taken.text
    assert taken.json()["resume"]["content"]["context"] == []

    asked = client.post(
        f"/v1/resumes/{resume_id}/ask", json={"text": "A version for fintech ops"}, headers=me
    )
    assert asked.status_code == 201 and asked.json()["resume_id"] == resume_id

    assert client.get(f"/v1/resumes/{resume_id}", headers=other).status_code == 404
    assert client.get(f"/v1/resumes/{resume_id}/versions/1", headers=other).status_code == 404
    assert (
        client.post(f"/v1/resumes/{resume_id}/ask", json={"text": "Mine now"}, headers=other)
    ).status_code == 404
    assert client.get("/v1/resumes", headers=other).json() == {"resumes": [], "ready": []}


def test_a_proposed_resume_over_http(client: TestClient, db: Database, vault: Vault) -> None:
    me = as_user("api-resume-proposal")
    card = client.post(
        "/v1/cards",
        json={
            "kind": "employment",
            "content": {
                "facts": {"employer": "Northwind Logistics", "start": "2014-03"},
                "framing": {"headline": "Northwind Logistics"},
            },
        },
        headers=me,
    ).json()
    win = client.post(
        "/v1/cards",
        json={
            "kind": "accomplishment",
            "content": {
                "parent": card["id"],
                "facts": {"figures": ["22%"]},
                "framing": {"headline": "Cut late shipments by 22%"},
            },
        },
        headers=me,
    ).json()
    content = {"entries": [{"card": card["id"], "items": [{"card": win["id"]}]}]}
    user_id = find_or_create_user(db, vault, "dev:api-resume-proposal")
    with db.as_user(user_id) as conn:
        cipher = vault.cipher_for(conn, user_id)
        parent = ResumeStore(conn, user_id, cipher).create(
            "My resume", ResumeContent.model_validate(content), Author("person")
        )
        proposal = AgentStore(conn, user_id, cipher).propose(
            "assembler",
            "resume",
            ProposalBody(
                message="Here's a version for fintech.",
                resume=NewResume(
                    name="Fintech",
                    target="Fintech operations roles",
                    target_kind="industry",
                    parent_id=parent.id,
                    parent_version_id=parent.head.id,
                    content=ResumeContent.model_validate(content),
                    rewordings=[
                        Rewording(
                            card=UUID(win["id"]),
                            framing=Framing(headline="Cut late deliveries 22%"),
                        )
                    ],
                ),
            ),
        )
    preview = client.get(f"/v1/proposals/{proposal.id}/resume", headers=me)
    assert preview.status_code == 200, preview.text
    assert preview.json()["parent_name"] == "My resume"
    [role] = preview.json()["page"]["entries"][0]["roles"]
    assert [(i["text"], i["wording"]) for i in role["items"]] == [
        ("Cut late deliveries 22%", "target")
    ]
    kept = client.post(f"/v1/proposals/{proposal.id}/keep-resume", json={}, headers=me)
    assert kept.status_code == 201, kept.text
    assert kept.json()["proposal"]["state"] == "kept"
    resume = kept.json()["resume"]
    assert resume["parent_id"] == str(parent.id)
    assert resume["head"]["author_kind"] == "ai"
    shown = client.get(f"/v1/resumes/{resume['id']}", headers=me).json()["page"]
    assert shown["entries"][0]["roles"][0]["items"][0]["text"] == "Cut late deliveries 22%"
    again = client.post(f"/v1/proposals/{proposal.id}/keep-resume", json={}, headers=me)
    assert again.status_code == 409
