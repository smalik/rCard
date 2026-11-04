from collections.abc import Iterator

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
