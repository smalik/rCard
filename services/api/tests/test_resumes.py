"""The resume tables (migrations/0007_resumes.sql): each person sees only their own
resumes, and versions are append-only."""

from uuid import UUID

import pytest
from psycopg import errors

from plytos_api.db import Database

HASH = bytes(32)


def _resume(db: Database, owner: UUID) -> tuple[UUID, UUID]:
    """A resume with one named version, written as its owner. The bytes stand in for
    ciphertext; these tests are about who can see and change rows."""
    with db.as_user(owner) as conn:
        row = conn.execute(
            "insert into plytos.resume (owner_id, name_ciphertext) values (%s, %s) returning id",
            (owner, b"name"),
        ).fetchone()
        assert row is not None
        resume = row[0]
        row = conn.execute(
            "insert into plytos.resume_version (owner_id, resume_id, number, schema_version,"
            " author_kind, content_ciphertext, content_hash, chain_hash)"
            " values (%s, %s, 1, 1, 'person', %s, %s, %s) returning id",
            (owner, resume, b"content", HASH, HASH),
        ).fetchone()
        assert row is not None
        version = row[0]
        conn.execute(
            "insert into plytos.resume_version_name (owner_id, version_id, name_ciphertext)"
            " values (%s, %s, %s)",
            (owner, version, b"sent to Contoso"),
        )
    return resume, version


def test_people_only_see_their_own_resumes(make_user, db: Database) -> None:
    alice, bob = make_user(), make_user()
    _resume(db, alice)
    with db.as_user(bob) as conn:
        for table in ("resume", "resume_version", "resume_version_name"):
            count = conn.execute(f"select count(*) from plytos.{table}").fetchone()  # noqa: S608
            assert count == (0,), table
    with db.as_user(alice) as conn:
        assert conn.execute("select count(*) from plytos.resume").fetchone() == (1,)


def test_cannot_write_a_resume_for_someone_else(make_user, db: Database) -> None:
    alice, bob = make_user(), make_user()
    with pytest.raises(errors.InsufficientPrivilege), db.as_user(bob) as conn:
        conn.execute(
            "insert into plytos.resume (owner_id, name_ciphertext) values (%s, %s)",
            (alice, b"name"),
        )


def test_resume_versions_are_append_only(make_user, db: Database) -> None:
    owner = make_user()
    _, version = _resume(db, owner)
    for statement in (
        "update plytos.resume_version set author_ref = 'x' where id = %s",
        "update plytos.resume_version set content_ciphertext = 'x' where id = %s",
        "delete from plytos.resume_version where id = %s",
    ):
        with pytest.raises(errors.InsufficientPrivilege), db.as_user(owner) as conn:
            conn.execute(statement, (version,))


def test_only_the_owner_can_erase_a_version(make_user, db: Database) -> None:
    """Deleting a version (0012) erases its content and names; the row stays."""
    owner, other = make_user(), make_user()
    _, version = _resume(db, owner)
    erase = (
        "update plytos.resume_version set content_ciphertext = null,"
        " redacted_at = clock_timestamp() where id = %s"
    )
    forget = "delete from plytos.resume_version_name where version_id = %s"
    with db.as_user(other) as conn:
        assert conn.execute(erase, (version,)).rowcount == 0
        assert conn.execute(forget, (version,)).rowcount == 0
    with db.as_user(owner) as conn:
        assert conn.execute(forget, (version,)).rowcount == 1
        assert conn.execute(erase, (version,)).rowcount == 1
    # Erased stays erased.
    with pytest.raises(errors.InsufficientPrivilege), db.as_user(owner) as conn:
        conn.execute(
            "update plytos.resume_version set content_ciphertext = 'x', redacted_at = null"
            " where id = %s",
            (version,),
        )
