"""Runs queued agent work, one person at a time.

Runs wait in plytos.agent_run. The worker claims a few that are due, then
does each one inside that person's own transaction, so row-level security
holds for everything the agent reads and writes. If an agent fails, its
writes roll back with the transaction and the run goes back in the queue to
try again later, up to a limit.

In development the API runs a worker on a background thread
(PLYTOS_AGENTS_INLINE). In production it runs as its own service.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from plytos_api.agents.model import AgentName, RunView
from plytos_api.agents.store import AgentStore
from plytos_api.agents.thinking import Usage
from plytos_api.cards.repository import CardRepository
from plytos_api.db import Database
from plytos_api.keys import Vault
from plytos_api.resumes.store import ResumeStore

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3


@dataclass
class Context:
    """Everything one run may touch: one person's data, through their stores."""

    run: RunView
    user_id: UUID
    store: AgentStore
    cards: CardRepository
    resumes: ResumeStore
    usage: Usage = field(default_factory=Usage)


class Agent(Protocol):
    name: AgentName

    def run(self, ctx: Context) -> None: ...


class AgentGaveUpError(Exception):
    """The agent couldn't do its job this time, for example because the model
    didn't answer. `code` says why, in a few words, never with content."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class Worker:
    def __init__(
        self,
        db: Database,
        vault: Vault,
        agents: Mapping[str, Agent],
        *,
        lease_seconds: int = 300,
        retry_base_seconds: int = 60,
    ) -> None:
        self._db = db
        self._vault = vault
        self._agents = agents
        self._lease = lease_seconds
        self._retry_base = retry_base_seconds

    def run_once(self, max_runs: int = 10) -> int:
        """Claims up to `max_runs` due runs and works through them. Returns how many."""
        with self._db.pool.connection() as conn, conn.transaction():
            claimed = conn.execute(
                "select id, owner_id, agent from plytos.claim_agent_runs(%s, %s)",
                (max_runs, self._lease),
            ).fetchall()
        for run_id, owner_id, agent in claimed:
            self._work(run_id, owner_id, agent)
        return len(claimed)

    def run_until_idle(self, max_rounds: int = 20) -> int:
        """Keeps going while runs are due, including the ones runs queue for
        each other. For tests and scripts."""
        total = 0
        for _ in range(max_rounds):
            done = self.run_once()
            if done == 0:
                break
            total += done
        return total

    def _work(self, run_id: UUID, owner_id: UUID, name: str) -> None:
        agent = self._agents.get(name)
        try:
            if agent is None:
                raise AgentGaveUpError("agent_not_running")
            with self._db.as_user(owner_id) as conn:
                cipher = self._vault.cipher_for(conn, owner_id)
                store = AgentStore(conn, owner_id, cipher)
                ctx = Context(
                    run=store.run(run_id),
                    user_id=owner_id,
                    store=store,
                    cards=CardRepository(conn, owner_id, cipher),
                    resumes=ResumeStore(conn, owner_id, cipher),
                )
                agent.run(ctx)
                store.finish_run(
                    run_id, ctx.usage.model, ctx.usage.input_tokens, ctx.usage.output_tokens
                )
        except Exception as exc:
            code = exc.code if isinstance(exc, AgentGaveUpError) else "error_" + _snake(exc)
            log.warning("Agent %s run %s failed: %s", name, run_id, code)
            self._fail(run_id, owner_id, code)

    def _fail(self, run_id: UUID, owner_id: UUID, code: str) -> None:
        with self._db.as_user(owner_id) as conn:
            store = AgentStore(conn, owner_id, self._vault.cipher_for(conn, owner_id))
            attempts = store.run(run_id).attempts
            retry = None if attempts >= MAX_ATTEMPTS else self._retry_base * 2 ** (attempts - 1)
            store.fail_run(run_id, code[:64], retry)


def _snake(exc: Exception) -> str:
    name = type(exc).__name__
    out = "".join("_" + c.lower() if c.isupper() else c for c in name).lstrip("_")
    return "".join(c for c in out if c.isalnum() or c == "_")[:50] or "unknown"


class Runs(Protocol):
    def run_once(self) -> int: ...


class BackgroundWorker:
    """Runs a worker (agent runs, or reading imports) on a thread until stopped,
    looking again straight away while there's work and every few seconds when
    there isn't."""

    def __init__(self, worker: Runs, every_seconds: float = 2.0, name: str = "agents") -> None:
        self._worker = worker
        self._every = every_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name=f"plytos-{name}", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=10)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                busy = self._worker.run_once() > 0
            except Exception as exc:
                log.warning("Worker round failed: %s", type(exc).__name__)
                busy = False
            if not busy:
                self._stop.wait(self._every)
