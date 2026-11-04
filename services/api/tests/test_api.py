from collections.abc import Iterator
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from plytos_api.config import Settings
from plytos_api.main import create_app

from .conftest import DbUrls, main_content


@pytest.fixture(scope="module")
def client(test_db: DbUrls, kek_setting: str) -> Iterator[TestClient]:
    app = create_app(Settings(env="test", database_url=test_db.app_url, kek=kek_setting))
    with TestClient(app) as c:
        yield c


def as_user(name: str) -> dict[str, str]:
    return {"X-Plytos-Dev-User": name}


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
    client: TestClient,
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
    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    view = response.json()
    import_id = view["id"]
    assert view["file"] == {"format": "docx", "size": len(data), "name": "Casey Morgan Resume.docx"}
    assert view["progress"] == {"settled": {}, "cards": {}, "edits": {}}
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

    approved = client.post(f"/v1/imports/{import_id}/cards/{ref}/approve", json={}, headers=me)
    assert approved.status_code == 201, approved.text
    card = approved.json()["card"]
    assert card["status"] == "approved"
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
    assert len(client.get("/v1/cards", headers=me).json()) == len(before) + 1

    someone = as_user("someone-else")
    assert client.get(f"/v1/imports/{import_id}", headers=someone).status_code == 404
    assert client.get(f"/v1/imports/{import_id}/original", headers=someone).status_code == 404
    assert client.delete(f"/v1/imports/{import_id}", headers=someone).status_code == 404
    assert client.get("/v1/imports", headers=someone).json() == []

    assert client.delete(f"/v1/imports/{import_id}", headers=me).status_code == 204
    assert client.get(f"/v1/imports/{import_id}", headers=me).status_code == 404
    assert len(client.get("/v1/cards", headers=me).json()) == len(before) + 1


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
