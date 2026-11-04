"""Test fixtures. Tests run against a real Postgres, in a fresh database that
is created and dropped for each test session.

Set PLYTOS_TEST_ADMIN_URL to a superuser connection string; the default
matches `docker compose up db` and the CI service container.
"""

import base64
import os
import secrets
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from plytos_api.auth import find_or_create_user
from plytos_api.cards.model import Framing, MainContent
from plytos_api.cards.repository import CardRepository
from plytos_api.config import DEFAULT_MIGRATIONS_DIR
from plytos_api.db import Database
from plytos_api.keys import LocalKek, Vault
from plytos_api.migrate import migrate

ADMIN_URL = os.environ.get(
    "PLYTOS_TEST_ADMIN_URL", "postgresql://postgres:postgres@localhost:5432/postgres"
)


@dataclass(frozen=True)
class DbUrls:
    owner_url: str
    app_url: str
    shredder_url: str


def _login_role(conn: psycopg.Connection, name: str, password: str) -> None:
    exists = conn.execute("select 1 from pg_roles where rolname = %s", (name,)).fetchone()
    verb = "alter" if exists else "create"
    conn.execute(
        sql.SQL(verb + " role {} login password {}").format(
            sql.Identifier(name), sql.Literal(password)
        )
    )


@pytest.fixture(scope="session")
def test_db() -> Iterator[DbUrls]:
    name = "plytos_test_" + secrets.token_hex(4)
    app_password = secrets.token_hex(16)
    shredder_password = secrets.token_hex(16)
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(sql.SQL("create database {}").format(sql.Identifier(name)))
        _login_role(admin, "plytos_test_app", app_password)
        _login_role(admin, "plytos_test_shredder", shredder_password)
    owner_url = make_conninfo(ADMIN_URL, dbname=name)
    migrate(owner_url, DEFAULT_MIGRATIONS_DIR, ["plytos_test_app"])
    with psycopg.connect(owner_url, autocommit=True) as owner:
        owner.execute("grant plytos_shredder to plytos_test_shredder")
    try:
        yield DbUrls(
            owner_url=owner_url,
            app_url=make_conninfo(owner_url, user="plytos_test_app", password=app_password),
            shredder_url=make_conninfo(
                owner_url, user="plytos_test_shredder", password=shredder_password
            ),
        )
    finally:
        with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
            admin.execute(
                sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(name))
            )


@pytest.fixture(scope="session")
def kek_setting() -> str:
    return "local:" + base64.b64encode(os.urandom(32)).decode()


@pytest.fixture(scope="session")
def db(test_db: DbUrls) -> Iterator[Database]:
    database = Database(test_db.app_url, max_size=4)
    database.open()
    yield database
    database.close()


@pytest.fixture(scope="session")
def vault(kek_setting: str) -> Vault:
    return Vault(LocalKek(base64.b64decode(kek_setting.removeprefix("local:"))))


@pytest.fixture
def make_user(db: Database, vault: Vault) -> Callable[[], UUID]:
    return lambda: find_or_create_user(db, vault, f"test:{uuid4()}")


RepoFor = Callable[[UUID], AbstractContextManager[CardRepository]]


@pytest.fixture
def repo_for(db: Database, vault: Vault) -> RepoFor:
    @contextmanager
    def _repo(user_id: UUID) -> Iterator[CardRepository]:
        with db.as_user(user_id) as conn:
            yield CardRepository(conn, user_id, vault.cipher_for(conn, user_id))

    return _repo


def main_content(
    headline: str = "Cut month-end close from 10 days to 4", **facts: object
) -> MainContent:
    defaults: dict[str, object] = {
        "employer": "Acme Health",
        "title": "Finance Manager",
        "start": "2021-03",
        "close_days_before": "10",
        "close_days_after": "4",
        "team_size": "6",
    }
    defaults.update(facts)
    return MainContent.model_validate(
        {
            "facts": defaults,
            "framing": Framing(
                headline=headline,
                body="Rebuilt the close checklist and automated 3 reconciliations"
                " with a team of 6.",
            ).model_dump(),
        }
    )
