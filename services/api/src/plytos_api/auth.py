"""Who is calling.

Sign-in is deferred until much later (decided 2026-11-04); resume import comes
first. Until sign-in exists:

* In dev and test, the X-Plytos-Dev-User header names a sign-in subject, and
  the person is created on first use.
* In prod, every request is refused, so nothing is reachable by accident.
"""

from uuid import UUID

from fastapi import HTTPException, Request, status
from psycopg import errors

from plytos_api.db import Database
from plytos_api.ids import uuid7
from plytos_api.keys import Vault

DEV_USER_HEADER = "x-plytos-dev-user"


def resolve_user(request: Request) -> UUID:
    settings = request.app.state.settings
    if not settings.dev_shortcuts:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Sign-in is not available yet")
    subject = request.headers.get(DEV_USER_HEADER, "").strip()
    if not subject:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in first")
    db: Database = request.app.state.db
    vault: Vault = request.app.state.vault
    return find_or_create_user(db, vault, "dev:" + subject)


def find_or_create_user(db: Database, vault: Vault, subject: str) -> UUID:
    existing = db.user_id_for_subject(subject)
    if existing is not None:
        return existing
    user_id = uuid7()
    try:
        with db.as_user(user_id) as conn:
            conn.execute(
                "insert into plytos.app_user (id, auth_subject) values (%s, %s)",
                (user_id, subject),
            )
            vault.create_user_key(conn, user_id)
    except errors.UniqueViolation:
        # Another request created this person first.
        existing = db.user_id_for_subject(subject)
        if existing is None:
            raise
        return existing
    return user_id
