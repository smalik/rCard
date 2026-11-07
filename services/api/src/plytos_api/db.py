"""Connection pool and per-person transactions.

Every query that touches a person's data runs inside Database.as_user, which
sets plytos.user_id for the transaction. Postgres row-level security then
limits the app role to that person's rows.

The database can be far from the API (a preview database across the
country), so each request keeps its trips to it few: who a sign-in belongs to
is remembered, and a transaction's begin and setup go in one trip with the
person's wrapped data key, which the Vault then uses without asking again.
"""

import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from uuid import UUID

import psycopg
from psycopg_pool import ConnectionPool

# The wrapped data key fetched with the current transaction's setup, by person.
# Set only inside Database.as_user; the Vault reads it (keys.py).
prefetched_keys: ContextVar[dict[UUID, bytes] | None] = ContextVar("prefetched_keys", default=None)

# How long a sign-in's person is remembered. People are never re-assigned to
# another sign-in, so this only bounds how long a deleted one lingers here.
_SUBJECT_TTL_SECONDS = 600.0


class Database:
    def __init__(self, url: str, *, min_size: int = 1, max_size: int = 10) -> None:
        self.pool = ConnectionPool(url, min_size=min_size, max_size=max_size, open=False)
        self._subjects: dict[str, tuple[UUID, float]] = {}

    def open(self) -> None:
        self.pool.open(wait=True)

    def close(self) -> None:
        self.pool.close()

    @contextmanager
    def as_user(self, user_id: UUID) -> Iterator[psycopg.Connection]:
        with self.pool.connection() as conn:
            # One trip: begin, scope the transaction to the person and fetch
            # their wrapped data key, which almost every request needs next.
            # psycopg would send its own BEGIN in a trip of its own, so the
            # transaction is begun and ended here instead.
            conn.autocommit = True
            try:
                with conn.pipeline():
                    conn.execute("begin")
                    conn.execute("select set_config('plytos.user_id', %s, true)", (str(user_id),))
                    key = conn.execute(
                        "select wrapped_dek from plytos_vault.user_key where user_id = %s",
                        (user_id,),
                    )
                row = key.fetchone()
                token = prefetched_keys.set({user_id: bytes(row[0])} if row else {})
                try:
                    yield conn
                finally:
                    prefetched_keys.reset(token)
            except BaseException:
                with suppress(psycopg.Error):
                    conn.execute("rollback")
                raise
            else:
                conn.execute("commit")
            finally:
                # Back to how the pool hands connections out. A broken
                # connection refuses, and the pool throws it away.
                with suppress(psycopg.Error):
                    conn.autocommit = False

    def user_id_for_subject(self, subject: str) -> UUID | None:
        known = self._subjects.get(subject)
        if known is not None and known[1] > time.monotonic():
            return known[0]
        with self.pool.connection() as conn:
            row = conn.execute("select plytos.user_id_for_subject(%s)", (subject,)).fetchone()
        user_id: UUID | None = row[0] if row else None
        if user_id is not None:
            self._subjects[subject] = (user_id, time.monotonic() + _SUBJECT_TTL_SECONDS)
        return user_id

    def forget_user(self, user_id: UUID) -> None:
        """Drops any sign-in remembered as this person, so the next request
        looks it up afresh: the person may have been erased, or replaced by a
        copy from another database (transfer.py)."""
        for subject, (known, _) in list(self._subjects.items()):
            if known == user_id:
                self._subjects.pop(subject, None)
