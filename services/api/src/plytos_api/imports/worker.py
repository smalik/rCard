"""Reads kept uploads in the background.

An upload is kept as soon as it arrives (ImportStore.keep) and waits for the
worker. The worker claims a few that are due, reads each one as its owner, and
says which stage it's at as it goes, each in a short transaction of its own so
the person waiting sees it. Nothing is held open while Claude reads.

A reading that breaks is tried again later, up to MAX_READS tries in all. A
file that can't be opened at all fails at once, since trying again won't help.
A reading whose worker stopped is claimed again once its lease runs out, and
given up on if that was its last try. The lease is renewed at each stage, and
each write names the attempt that claimed it, so a worker that ran past its
lease can't undo the work of the one that took over.

When the person shared the resume in the conversation, Plytos answers there
once the reading is done, or says it couldn't read it.
"""

from __future__ import annotations

import logging
from uuid import UUID

from plytos_api.agents.resume import reading
from plytos_api.agents.store import AgentStore
from plytos_api.db import Database
from plytos_api.imports.ai import ResumeReader
from plytos_api.imports.extract import UnsupportedFileError
from plytos_api.imports.pipeline import Stage, import_resume
from plytos_api.imports.store import MAX_READS, ImportStore, ReadingStage
from plytos_api.keys import Vault

log = logging.getLogger(__name__)

COULD_NOT_READ = (
    "I couldn't read that file. If it's a scan or a PDF that won't open, try a Word copy,"
    " or paste the text here."
)


class ImportWorker:
    def __init__(
        self,
        db: Database,
        vault: Vault,
        reader: ResumeReader | None,
        *,
        lease_seconds: int = 300,
        retry_base_seconds: int = 30,
    ) -> None:
        self._db = db
        self._vault = vault
        self._reader = reader
        self._lease = lease_seconds
        self._retry_base = retry_base_seconds

    def run_once(self) -> int:
        """Claims one due reading and reads it, and says so for any given up on.
        Returns how many it handled. One at a time, so no claim waits out its
        lease behind another reading."""
        with self._db.pool.connection() as conn, conn.transaction():
            claimed = conn.execute(
                "select id, owner_id, attempt, gave_up from plytos.claim_resume_imports(1, %s)",
                (self._lease,),
            ).fetchall()
        for import_id, owner_id, attempt, gave_up in claimed:
            if gave_up:
                self._gave_up(import_id, owner_id)
            else:
                self.read(import_id, owner_id, attempt)
        return len(claimed)

    def run_until_idle(self, max_rounds: int = 100) -> int:
        """Keeps going while readings are due. For tests and scripts."""
        total = 0
        for _ in range(max_rounds):
            done = self.run_once()
            if done == 0:
                break
            total += done
        return total

    def read(self, import_id: UUID, owner_id: UUID, attempt: int) -> None:
        """Reads one claimed upload as its owner. `attempt` is the claim's: every
        write names it, so nothing is written once another worker has taken over."""
        with self._db.as_user(owner_id) as conn:
            store = ImportStore(conn, owner_id, self._vault.cipher_for(conn, owner_id))
            upload = store.to_read(import_id, attempt)
            if upload is not None:
                store.at_stage(import_id, attempt, "file", self._lease)
        if upload is None:  # deleted, read already, or claimed again
            return
        data, filename = upload

        def on_stage(stage: Stage) -> None:
            self._at(import_id, owner_id, attempt, stage)

        try:
            result = import_resume(data, filename, reader=self._reader, on_stage=on_stage)
        except UnsupportedFileError:
            self._failed(import_id, owner_id, attempt, "unreadable", retry=False)
            return
        except Exception as exc:
            log.warning("Reading import %s failed: %s", import_id, type(exc).__name__)
            self._failed(import_id, owner_id, attempt, "error_" + _snake(exc), retry=True)
            return
        with self._db.as_user(owner_id) as conn:
            cipher = self._vault.cipher_for(conn, owner_id)
            if ImportStore(conn, owner_id, cipher).finish(import_id, attempt, result):
                AgentStore(conn, owner_id, cipher).answer_shared_resume(import_id, reading(result))

    def _at(self, import_id: UUID, owner_id: UUID, attempt: int, stage: ReadingStage) -> None:
        # Shows the stage and renews the lease. Progress is only for show: a failure
        # to record it mustn't stop the reading.
        try:
            with self._db.as_user(owner_id) as conn:
                ImportStore(conn, owner_id, self._vault.cipher_for(conn, owner_id)).at_stage(
                    import_id, attempt, stage, self._lease
                )
        except Exception as exc:
            log.warning("Recording a reading's stage failed: %s", type(exc).__name__)

    def _gave_up(self, import_id: UUID, owner_id: UUID) -> None:
        # Its last try ran out of time, so the worker reading it likely stopped.
        with self._db.as_user(owner_id) as conn:
            cipher = self._vault.cipher_for(conn, owner_id)
            AgentStore(conn, owner_id, cipher).answer_shared_resume(import_id, COULD_NOT_READ)

    def _failed(
        self, import_id: UUID, owner_id: UUID, attempt: int, code: str, *, retry: bool
    ) -> None:
        again = retry and attempt < MAX_READS
        delay = self._retry_base * 2 ** (attempt - 1) if again else None
        with self._db.as_user(owner_id) as conn:
            cipher = self._vault.cipher_for(conn, owner_id)
            recorded = ImportStore(conn, owner_id, cipher).failed(import_id, attempt, code, delay)
            if recorded and delay is None:
                AgentStore(conn, owner_id, cipher).answer_shared_resume(import_id, COULD_NOT_READ)


def _snake(exc: Exception) -> str:
    name = type(exc).__name__
    out = "".join("_" + c.lower() if c.isupper() else c for c in name).lstrip("_")
    return "".join(c for c in out if c.isalnum() or c == "_")[:50] or "unknown"
