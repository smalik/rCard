"""Rules the database enforces on its own, whatever the app code does."""

from uuid import UUID

import psycopg
import pytest
from psycopg import errors

from plytos_api.agents.model import CheckInPlan, ProposalBody
from plytos_api.agents.store import AgentStore
from plytos_api.cards.repository import Author, CardNotFoundError
from plytos_api.db import Database
from plytos_api.imports.pipeline import import_resume
from plytos_api.imports.store import ImportNotFoundError, ImportStore
from plytos_api.keys import KeyShreddedError, Vault

from .conftest import DbUrls, RepoFor, main_content
from .resume_samples import messy_text

ME = Author("person")


def test_people_only_see_their_own_rows(make_user, repo_for: RepoFor, db: Database) -> None:
    alice, bob = make_user(), make_user()
    with repo_for(alice) as repo:
        card = repo.create_card("accomplishment", main_content(), ME)
        repo.create_target("company", "JP Morgan", None)
    with repo_for(bob) as repo:
        assert repo.list_cards() == []
        assert repo.list_targets() == []
        with pytest.raises(CardNotFoundError):
            repo.card_detail(card.id)
    with db.as_user(bob) as conn:
        for table in ("card", "card_line", "card_version", "target", "event"):
            count = conn.execute(f"select count(*) from plytos.{table}").fetchone()  # noqa: S608
            assert count == (0,), table
        assert conn.execute("select count(*) from plytos_vault.user_key").fetchone() == (1,)


def test_without_a_person_set_nothing_is_visible(
    make_user, repo_for: RepoFor, db: Database
) -> None:
    with repo_for(make_user()) as repo:
        repo.create_card("accomplishment", main_content(), ME)
    with db.pool.connection() as conn:
        assert conn.execute("select count(*) from plytos.card").fetchone() == (0,)
        assert conn.execute("select count(*) from plytos_vault.user_key").fetchone() == (0,)


def test_cannot_write_rows_for_someone_else(make_user, db: Database) -> None:
    alice, bob = make_user(), make_user()
    with pytest.raises(errors.InsufficientPrivilege), db.as_user(bob) as conn:
        conn.execute("insert into plytos.card (owner_id, kind) values (%s, 'skill')", (alice,))


def test_app_role_cannot_rewrite_or_delete_versions(
    make_user, repo_for: RepoFor, db: Database
) -> None:
    user = make_user()
    with repo_for(user) as repo:
        card = repo.create_card("accomplishment", main_content(), ME)
    for statement in (
        "update plytos.card_version set author_ref = 'x' where card_id = %s",
        "delete from plytos.card_version where card_id = %s",
        "delete from plytos.event where record_id = %s",
    ):
        with pytest.raises(errors.InsufficientPrivilege), db.as_user(user) as conn:
            conn.execute(statement, (card.id,))


def test_even_the_owner_can_only_redact_a_version(
    make_user, repo_for: RepoFor, test_db: DbUrls
) -> None:
    user = make_user()
    with repo_for(user) as repo:
        card = repo.create_card("accomplishment", main_content(), ME)
    with psycopg.connect(test_db.owner_url) as owner:
        with pytest.raises(errors.InsufficientPrivilege):
            owner.execute(
                "update plytos.card_version set content_hash = %s where card_id = %s",
                (bytes(32), card.id),
            )
        owner.rollback()
        owner.execute(
            "update plytos.card_version set content_ciphertext = null, redacted_at = now()"
            " where card_id = %s",
            (card.id,),
        )
        owner.commit()
    with repo_for(user) as repo:
        detail = repo.card_detail(card.id)
        assert detail.main.head.redacted
        assert detail.main.content is None
        assert repo.verify(card.id) == []


def test_version_numbers_must_follow_their_parent(
    make_user, repo_for: RepoFor, test_db: DbUrls
) -> None:
    user = make_user()
    with repo_for(user) as repo:
        card = repo.create_card("accomplishment", main_content(), ME)
    with psycopg.connect(test_db.owner_url) as owner, pytest.raises(errors.CheckViolation):
        owner.execute(
            "insert into plytos.card_version (owner_id, card_id, line_id, number, parent_id,"
            " schema_version, author_kind, content_ciphertext, content_hash, chain_hash)"
            " values (%s, %s, %s, 5, %s, 1, 'person', '\\x00', %s, %s)",
            (user, card.id, card.main.id, card.main.head.id, bytes(32), bytes(32)),
        )


def test_deleting_an_account_shreds_the_key_and_every_row(
    make_user, repo_for: RepoFor, db: Database, vault: Vault, test_db: DbUrls
) -> None:
    user, other = make_user(), make_user()
    with repo_for(user) as repo:
        card = repo.create_card("accomplishment", main_content(), ME)
        target = repo.create_target("industry", "Pharma", None)
        from plytos_api.cards.model import Framing, VariantContent

        repo.create_variant(
            card.id, target.id, VariantContent(framing=Framing(headline="Faster close")), ME
        )
    with repo_for(other) as repo:
        repo.create_card("skill", main_content(), ME)
    _import(db, vault, user)
    with db.as_user(user) as conn:
        store = AgentStore(conn, user, vault.cipher_for(conn, user))
        said = store.say("Cut late shipments from 12% to 7%")
        tidbit = store.add_tidbit("text", said.text, message_id=said.id)
        store.propose(
            "stitcher", "question", ProposalBody(message="Which site?"), cites=[tidbit.id]
        )
        store.set_check_in_plan(CheckInPlan(time_zone="UTC"))

    with psycopg.connect(test_db.app_url) as app, pytest.raises(errors.InsufficientPrivilege):
        app.execute("select plytos.purge_user(%s)", (user,))

    with psycopg.connect(test_db.shredder_url) as shredder:
        shredder.execute("select plytos.purge_user(%s)", (user,))
        shredder.commit()

    with psycopg.connect(test_db.owner_url) as owner:
        for table, column in (
            ("plytos.app_user", "id"),
            ("plytos_vault.user_key", "user_id"),
            ("plytos.card", "owner_id"),
            ("plytos.card_line", "owner_id"),
            ("plytos.card_version", "owner_id"),
            ("plytos.target", "owner_id"),
            ("plytos.event", "owner_id"),
            ("plytos.resume_import", "owner_id"),
            ("plytos.message", "owner_id"),
            ("plytos.tidbit", "owner_id"),
            ("plytos.proposal", "owner_id"),
            ("plytos.agent_run", "owner_id"),
            ("plytos.check_in_plan", "owner_id"),
        ):
            row = owner.execute(
                f"select count(*) from {table} where {column} = %s",  # noqa: S608
                (user,),
            ).fetchone()
            assert row == (0,), table
        assert owner.execute(
            "select count(*) from plytos.card where owner_id = %s", (other,)
        ).fetchone() == (1,)

    with db.as_user(user) as conn, pytest.raises(KeyShreddedError):
        vault.cipher_for(conn, user)


def _import(db: Database, vault: Vault, user: UUID) -> UUID:
    data = messy_text().encode()
    with db.as_user(user) as conn:
        store = ImportStore(conn, user, vault.cipher_for(conn, user))
        return store.create(data, "Jordan Rivera.txt", import_resume(data, "Jordan Rivera.txt")).id


def test_people_only_see_their_own_imports(make_user, db: Database, vault: Vault) -> None:
    alice, bob = make_user(), make_user()
    import_id = _import(db, vault, alice)
    with db.as_user(bob) as conn:
        store = ImportStore(conn, bob, vault.cipher_for(conn, bob))
        assert store.summaries() == []
        for read in (store.get, store.original, store.delete):
            with pytest.raises(ImportNotFoundError):
                read(import_id)
        assert conn.execute("select count(*) from plytos.resume_import").fetchone() == (0,)
    with db.as_user(alice) as conn:
        store = ImportStore(conn, alice, vault.cipher_for(conn, alice))
        assert [s.id for s in store.summaries()] == [import_id]


def test_an_import_keeps_the_original_encrypted_and_unchanged(
    make_user, db: Database, vault: Vault
) -> None:
    user = make_user()
    import_id = _import(db, vault, user)
    with db.as_user(user) as conn:
        row = conn.execute(
            "select file_ciphertext, name_ciphertext, result_ciphertext"
            " from plytos.resume_import where id = %s",
            (import_id,),
        ).fetchone()
        assert row is not None
        for blob in row:
            assert b"Jordan" not in bytes(blob)
        store = ImportStore(conn, user, vault.cipher_for(conn, user))
        info, data = store.original(import_id)
        assert data == messy_text().encode()
        assert info.name == "Jordan Rivera.txt"
    for column in ("file_ciphertext", "name_ciphertext", "file_format"):
        with pytest.raises(errors.InsufficientPrivilege), db.as_user(user) as conn:
            conn.execute(
                f"update plytos.resume_import set {column} = {column} where id = %s",  # noqa: S608
                (import_id,),
            )
    # What was read is written once, and a read import stays read.
    for change in ("result_ciphertext = '\\x00'", "state = 'reading', result_ciphertext = null"):
        with pytest.raises(errors.CheckViolation), db.as_user(user) as conn:
            conn.execute(
                f"update plytos.resume_import set {change} where id = %s",  # noqa: S608
                (import_id,),
            )


def test_migrations_run_once(test_db: DbUrls) -> None:
    from plytos_api.config import DEFAULT_MIGRATIONS_DIR
    from plytos_api.migrate import migrate

    assert migrate(test_db.owner_url, DEFAULT_MIGRATIONS_DIR, []) == []
