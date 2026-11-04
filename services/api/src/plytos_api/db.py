"""Connection pool and per-person transactions.

Every query that touches a person's data runs inside Database.as_user, which
sets plytos.user_id for the transaction. Postgres row-level security then
limits the app role to that person's rows.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

import psycopg
from psycopg_pool import ConnectionPool


class Database:
    def __init__(self, url: str, *, min_size: int = 1, max_size: int = 10) -> None:
        self.pool = ConnectionPool(url, min_size=min_size, max_size=max_size, open=False)

    def open(self) -> None:
        self.pool.open(wait=True)

    def close(self) -> None:
        self.pool.close()

    @contextmanager
    def as_user(self, user_id: UUID) -> Iterator[psycopg.Connection]:
        with self.pool.connection() as conn, conn.transaction():
            conn.execute("select set_config('plytos.user_id', %s, true)", (str(user_id),))
            yield conn

    def user_id_for_subject(self, subject: str) -> UUID | None:
        with self.pool.connection() as conn:
            row = conn.execute("select plytos.user_id_for_subject(%s)", (subject,)).fetchone()
            return row[0] if row else None
