"""Applies SQL migrations in order. Run as the database owner:

    python -m plytos_api.migrate

Each file runs once, in its own transaction. Editing a migration that has
already run is an error; add a new file instead.
"""

import hashlib
import logging
from pathlib import Path

import psycopg
from psycopg import sql

from plytos_api.config import get_settings

log = logging.getLogger(__name__)

_LOCK_KEY = 0x504C59544F53  # "PLYTOS"


def migrate(url: str, migrations_dir: Path, app_login_roles: list[str]) -> list[str]:
    applied_now: list[str] = []
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("select pg_advisory_lock(%s)", (_LOCK_KEY,))
        try:
            conn.execute(
                "create schema if not exists plytos_meta;"
                "create table if not exists plytos_meta.schema_migration ("
                " version text primary key,"
                " checksum text not null,"
                " applied_at timestamptz not null default now())"
            )
            applied: dict[str, str] = dict(
                conn.execute(
                    "select version, checksum from plytos_meta.schema_migration"
                ).fetchall()
            )
            for path in sorted(migrations_dir.glob("*.sql")):
                body = path.read_text(encoding="utf-8")
                checksum = hashlib.sha256(body.encode("utf-8")).hexdigest()
                if path.name in applied:
                    if applied[path.name] != checksum:
                        raise RuntimeError(f"{path.name} changed after it was applied")
                    continue
                with conn.transaction():
                    conn.execute(body.encode("utf-8"))
                    conn.execute(
                        "insert into plytos_meta.schema_migration (version, checksum)"
                        " values (%s, %s)",
                        (path.name, checksum),
                    )
                applied_now.append(path.name)
                log.info("applied %s", path.name)
            for role in app_login_roles:
                conn.execute(sql.SQL("grant plytos_app to {}").format(sql.Identifier(role)))
        finally:
            conn.execute("select pg_advisory_unlock(%s)", (_LOCK_KEY,))
    return applied_now


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    roles = [r.strip() for r in settings.app_login_roles.split(",") if r.strip()]
    applied = migrate(settings.database_url, settings.migrations_dir, roles)
    log.info("migrations applied: %s", ", ".join(applied) or "none")


if __name__ == "__main__":
    main()
