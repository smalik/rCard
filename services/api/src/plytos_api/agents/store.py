"""Reads and writes the conversation, tidbits, proposals and agent runs for one
person.

The connection passed in must already be scoped to that person
(Database.as_user), so row-level security limits every query to their rows.
Everything a person or an agent says is encrypted with the person's key, each
record under its own associated data, so a ciphertext can't be moved to
another row.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg import sql

from plytos_api.agents.model import (
    AgentName,
    Channel,
    MessageView,
    ProposalBody,
    ProposalKind,
    ProposalState,
    ProposalView,
    Reading,
    RunView,
    TidbitKind,
    TidbitView,
    TriggerKind,
)
from plytos_api.cards.model import MainContent
from plytos_api.cards.repository import Author, CardDetail, CardRepository
from plytos_api.ids import uuid7
from plytos_api.keys import UserCipher


class AgentRecordNotFoundError(Exception):
    pass


class ProposalConflictError(Exception):
    """The proposal can't be decided as asked: it was decided already, or it
    isn't the kind that turns into a card."""


_PROPOSAL_COLUMNS = sql.SQL(
    "id, agent, kind, state, card_id, cites, payload_ciphertext, created_at, decided_at,"
    " result_version_id"
)
_TIDBIT_COLUMNS = sql.SQL(
    "id, kind, said_at, body_ciphertext, message_id, card_id, reading_ciphertext, read_at,"
    " created_at"
)
_RUN_COLUMNS = sql.SQL(
    "id, agent, trigger_kind, trigger_id, state, attempts, model, input_tokens, output_tokens,"
    " error_code, created_at, finished_at"
)


def _aad(record: str, record_id: UUID) -> bytes:
    return b"plytos." + record.encode() + b":" + record_id.bytes


class AgentStore:
    def __init__(self, conn: psycopg.Connection, user_id: UUID, cipher: UserCipher) -> None:
        self._conn = conn
        self._user_id = user_id
        self._cipher = cipher

    # -- the conversation ------------------------------------------------------

    def say(self, text: str, channel: Channel = "app") -> MessageView:
        """Saves the person's message and asks the Listener to read it."""
        message = self._message("person", text, channel, None)
        self._event("person", "message.sent", "message", message.id)
        self.enqueue("listener", "message", message.id)
        return message

    def reply(self, text: str, agent: AgentName, proposal_id: UUID | None = None) -> MessageView:
        """Saves a message from Plytos, written by one of the agents."""
        message = self._message("plytos", text, "app", proposal_id)
        self._event("ai", "message.sent", "message", message.id, agent)
        return message

    def share_resume(self, import_id: UUID, reading: str) -> list[MessageView]:
        """The person shares a resume in the conversation, and Plytos says what
        it read. The import itself is kept by ImportStore."""
        shared = self._message("person", "Here's my resume.", "app", None, import_id)
        self._event("person", "message.sent", "message", shared.id)
        answer = self._message("plytos", reading, "app", None, import_id)
        self._event("system", "message.sent", "message", answer.id, "import")
        return [shared, answer]

    def message(self, message_id: UUID) -> MessageView:
        row = self._conn.execute(
            "select id, author, channel, body_ciphertext, proposal_id, created_at, import_id"
            " from plytos.message where id = %s",
            (message_id,),
        ).fetchone()
        if row is None:
            raise AgentRecordNotFoundError(str(message_id))
        return self._message_view(row)

    def conversation(self, limit: int = 50, before: UUID | None = None) -> list[MessageView]:
        """The latest messages, oldest first. `before` pages further back."""
        rows = self._conn.execute(
            "select id, author, channel, body_ciphertext, proposal_id, created_at, import_id"
            " from plytos.message"
            " where %(before)s::uuid is null or (created_at, id) <"
            "   (select created_at, id from plytos.message where id = %(before)s)"
            " order by created_at desc, id desc limit %(limit)s",
            {"before": before, "limit": limit},
        ).fetchall()
        return [self._message_view(r) for r in reversed(rows)]

    # -- tidbits ---------------------------------------------------------------

    def add_tidbit(
        self,
        kind: TidbitKind,
        text: str,
        *,
        message_id: UUID | None = None,
        said_at: datetime | None = None,
        agent: AgentName | None = None,
    ) -> TidbitView:
        """Keeps a note about work. `agent` names the agent that lifted it out of
        a message; a note the person adds directly has none."""
        tidbit_id = uuid7()
        row = self._conn.execute(
            sql.SQL(
                "insert into plytos.tidbit (id, owner_id, kind, message_id, said_at,"
                " body_ciphertext) values (%s, %s, %s, %s, coalesce(%s, now()), %s)"
                " returning {}"
            ).format(_TIDBIT_COLUMNS),
            (
                tidbit_id,
                self._user_id,
                kind,
                message_id,
                said_at,
                self._cipher.encrypt(text.encode(), _aad("tidbit.body", tidbit_id)),
            ),
        ).fetchone()
        assert row is not None
        if agent is None:
            self._event("person", "tidbit.added", "tidbit", tidbit_id)
        else:
            self._event("ai", "tidbit.added", "tidbit", tidbit_id, agent)
        return self._tidbit_view(row)

    def read_tidbit(self, tidbit_id: UUID, card_id: UUID | None, reading: Reading) -> TidbitView:
        """Records the Listener's reading. A tidbit is read once."""
        row = self._conn.execute(
            sql.SQL(
                "update plytos.tidbit set card_id = %s, reading_ciphertext = %s, read_at = now()"
                " where id = %s and read_at is null returning {}"
            ).format(_TIDBIT_COLUMNS),
            (
                card_id,
                self._cipher.encrypt(
                    reading.model_dump_json().encode(), _aad("tidbit.reading", tidbit_id)
                ),
                tidbit_id,
            ),
        ).fetchone()
        if row is None:
            raise AgentRecordNotFoundError(str(tidbit_id))
        return self._tidbit_view(row)

    def tidbit(self, tidbit_id: UUID) -> TidbitView:
        row = self._conn.execute(
            sql.SQL("select {} from plytos.tidbit where id = %s").format(_TIDBIT_COLUMNS),
            (tidbit_id,),
        ).fetchone()
        if row is None:
            raise AgentRecordNotFoundError(str(tidbit_id))
        return self._tidbit_view(row)

    def tidbits(self, card_id: UUID | None = None) -> list[TidbitView]:
        """Every tidbit, or those filed under one job, oldest first."""
        rows = self._conn.execute(
            sql.SQL(
                "select {} from plytos.tidbit"
                " where %(card)s::uuid is null or card_id = %(card)s"
                " order by said_at, id"
            ).format(_TIDBIT_COLUMNS),
            {"card": card_id},
        ).fetchall()
        return [self._tidbit_view(r) for r in rows]

    # -- proposals -------------------------------------------------------------

    def propose(
        self,
        agent: AgentName,
        kind: ProposalKind,
        body: ProposalBody,
        *,
        cites: Sequence[UUID] = (),
        card_id: UUID | None = None,
        run_id: UUID | None = None,
    ) -> ProposalView:
        """Saves a proposal and the message from Plytos that offers it."""
        proposal_id = uuid7()
        row = self._conn.execute(
            sql.SQL(
                "insert into plytos.proposal (id, owner_id, agent, kind, card_id,"
                " payload_ciphertext, cites, run_id) values (%s, %s, %s, %s, %s, %s, %s, %s)"
                " returning {}"
            ).format(_PROPOSAL_COLUMNS),
            (
                proposal_id,
                self._user_id,
                agent,
                kind,
                card_id,
                self._cipher.encrypt(
                    body.model_dump_json().encode(), _aad("proposal", proposal_id)
                ),
                list(cites),
                run_id,
            ),
        ).fetchone()
        assert row is not None
        self._event("ai", "proposal.made", "proposal", proposal_id, agent)
        self.reply(body.message, agent, proposal_id)
        return self._proposal_view(row)

    def proposal(self, proposal_id: UUID) -> ProposalView:
        row = self._conn.execute(
            sql.SQL("select {} from plytos.proposal where id = %s").format(_PROPOSAL_COLUMNS),
            (proposal_id,),
        ).fetchone()
        if row is None:
            raise AgentRecordNotFoundError(str(proposal_id))
        return self._proposal_view(row)

    def proposals(
        self, state: ProposalState | None = "open", agent: AgentName | None = None
    ) -> list[ProposalView]:
        rows = self._conn.execute(
            sql.SQL(
                "select {} from plytos.proposal"
                " where (%(state)s::text is null or state = %(state)s)"
                " and (%(agent)s::text is null or agent = %(agent)s)"
                " order by created_at, id"
            ).format(_PROPOSAL_COLUMNS),
            {"state": state, "agent": agent},
        ).fetchall()
        return [self._proposal_view(r) for r in rows]

    def keep(
        self,
        proposal_id: UUID,
        cards: CardRepository,
        edited: MainContent | None = None,
    ) -> tuple[ProposalView, CardDetail]:
        """Turns a proposed card into a card. Kept as proposed, the version is
        the agent's (author_kind 'ai'); kept after the person's edits, it's theirs."""
        proposal = self._open_for_update(proposal_id)
        card = proposal.body.card
        if proposal.kind != "new_card" or card is None:
            raise ProposalConflictError("Only a proposed card can be kept as a card.")
        content = edited if edited is not None else card.content
        author = (
            Author("person", str(self._user_id))
            if edited is not None
            else Author("ai", proposal.agent)
        )
        detail = cards.create_card(card.kind, content, author, status="approved")
        state: ProposalState = "kept" if edited is None else "edited"
        self._decide(proposal_id, state, detail.main.head.id)
        self._event("person", f"proposal.{state}", "proposal", proposal_id)
        return self.proposal(proposal_id), detail

    def dismiss(self, proposal_id: UUID) -> ProposalView:
        self._open_for_update(proposal_id)
        self._decide(proposal_id, "dismissed", None)
        self._event("person", "proposal.dismissed", "proposal", proposal_id)
        return self.proposal(proposal_id)

    def supersede(self, proposal_id: UUID, agent: AgentName) -> None:
        """An agent replaces its own open proposal with a better one."""
        self._open_for_update(proposal_id)
        self._decide(proposal_id, "superseded", None)
        self._event("ai", "proposal.superseded", "proposal", proposal_id, agent)

    # -- agent runs ------------------------------------------------------------

    def enqueue(
        self,
        agent: AgentName,
        trigger_kind: TriggerKind,
        trigger_id: UUID | None = None,
        *,
        dedupe_key: str | None = None,
        delay_seconds: int = 0,
    ) -> UUID | None:
        """Queues a run. With a dedupe key, a run already queued under that key
        stands in for this one and None comes back."""
        row = self._conn.execute(
            "insert into plytos.agent_run (id, owner_id, agent, trigger_kind, trigger_id,"
            " dedupe_key, run_after) values (%s, %s, %s, %s, %s, %s,"
            " now() + make_interval(secs => %s))"
            " on conflict (owner_id, dedupe_key) where state = 'queued' and dedupe_key is not null"
            " do nothing returning id",
            (uuid7(), self._user_id, agent, trigger_kind, trigger_id, dedupe_key, delay_seconds),
        ).fetchone()
        return row[0] if row else None

    def run(self, run_id: UUID) -> RunView:
        row = self._conn.execute(
            sql.SQL("select {} from plytos.agent_run where id = %s").format(_RUN_COLUMNS), (run_id,)
        ).fetchone()
        if row is None:
            raise AgentRecordNotFoundError(str(run_id))
        return self._run_view(row)

    def runs(self, limit: int = 50) -> list[RunView]:
        rows = self._conn.execute(
            sql.SQL(
                "select {} from plytos.agent_run order by created_at desc, id desc limit %s"
            ).format(_RUN_COLUMNS),
            (limit,),
        ).fetchall()
        return [self._run_view(r) for r in rows]

    def finish_run(
        self, run_id: UUID, model: str | None, input_tokens: int, output_tokens: int
    ) -> None:
        self._conn.execute(
            "update plytos.agent_run set state = 'done', finished_at = now(), locked_until = null,"
            " model = %s, input_tokens = %s, output_tokens = %s, error_code = null where id = %s",
            (model, input_tokens, output_tokens, run_id),
        )

    def fail_run(self, run_id: UUID, error_code: str, retry_in_seconds: int | None) -> None:
        """Marks a run failed, or puts it back in the queue to try again later."""
        if retry_in_seconds is None:
            self._conn.execute(
                "update plytos.agent_run set state = 'failed', finished_at = now(),"
                " locked_until = null, error_code = %s where id = %s",
                (error_code, run_id),
            )
        else:
            self._conn.execute(
                "update plytos.agent_run set state = 'queued', locked_until = null,"
                " error_code = %s, run_after = now() + make_interval(secs => %s) where id = %s",
                (error_code, retry_in_seconds, run_id),
            )

    # -- internals -------------------------------------------------------------

    def _message(
        self,
        author: str,
        text: str,
        channel: Channel,
        proposal_id: UUID | None,
        import_id: UUID | None = None,
    ) -> MessageView:
        message_id = uuid7()
        row = self._conn.execute(
            "insert into plytos.message (id, owner_id, author, channel, body_ciphertext,"
            " proposal_id, import_id) values (%s, %s, %s, %s, %s, %s, %s)"
            " returning id, author, channel, body_ciphertext, proposal_id, created_at,"
            " import_id",
            (
                message_id,
                self._user_id,
                author,
                channel,
                self._cipher.encrypt(text.encode(), _aad("message", message_id)),
                proposal_id,
                import_id,
            ),
        ).fetchone()
        assert row is not None
        return self._message_view(row)

    def _open_for_update(self, proposal_id: UUID) -> ProposalView:
        row = self._conn.execute(
            sql.SQL("select {} from plytos.proposal where id = %s for update").format(
                _PROPOSAL_COLUMNS
            ),
            (proposal_id,),
        ).fetchone()
        if row is None:
            raise AgentRecordNotFoundError(str(proposal_id))
        proposal = self._proposal_view(row)
        if proposal.state != "open":
            raise ProposalConflictError("This was already decided.")
        return proposal

    def _decide(self, proposal_id: UUID, state: ProposalState, version_id: UUID | None) -> None:
        self._conn.execute(
            "update plytos.proposal set state = %s, decided_at = now(), result_version_id = %s"
            " where id = %s",
            (state, version_id, proposal_id),
        )

    def _message_view(self, row: Sequence[Any]) -> MessageView:
        proposal = self.proposal(row[4]) if row[4] is not None else None
        return MessageView(
            id=row[0],
            author=row[1],
            channel=row[2],
            text=self._cipher.decrypt(bytes(row[3]), _aad("message", row[0])).decode(),
            proposal=proposal,
            created_at=row[5],
            import_id=row[6],
        )

    def _proposal_view(self, row: Sequence[Any]) -> ProposalView:
        body = ProposalBody.model_validate_json(
            self._cipher.decrypt(bytes(row[6]), _aad("proposal", row[0]))
        )
        return ProposalView(
            id=row[0],
            agent=row[1],
            kind=row[2],
            state=row[3],
            card_id=row[4],
            cites=list(row[5]),
            body=body,
            created_at=row[7],
            decided_at=row[8],
            result_version_id=row[9],
        )

    def _tidbit_view(self, row: Sequence[Any]) -> TidbitView:
        reading = None
        if row[6] is not None:
            reading = Reading.model_validate_json(
                self._cipher.decrypt(bytes(row[6]), _aad("tidbit.reading", row[0]))
            )
        return TidbitView(
            id=row[0],
            kind=row[1],
            said_at=row[2],
            text=self._cipher.decrypt(bytes(row[3]), _aad("tidbit.body", row[0])).decode(),
            message_id=row[4],
            card_id=row[5],
            reading=reading,
            read_at=row[7],
            created_at=row[8],
        )

    @staticmethod
    def _run_view(row: Sequence[Any]) -> RunView:
        return RunView(
            id=row[0],
            agent=row[1],
            trigger_kind=row[2],
            trigger_id=row[3],
            state=row[4],
            attempts=row[5],
            model=row[6],
            input_tokens=row[7],
            output_tokens=row[8],
            error_code=row[9],
            created_at=row[10],
            finished_at=row[11],
        )

    def _event(
        self,
        actor_kind: str,
        action: str,
        record_type: str,
        record_id: UUID,
        actor_ref: str | None = None,
    ) -> None:
        self._conn.execute(
            "insert into plytos.event (owner_id, actor_kind, actor_ref, action, record_type,"
            " record_id) values (%s, %s, %s, %s, %s, %s)",
            (
                self._user_id,
                actor_kind,
                actor_ref if actor_ref is not None else str(self._user_id),
                action,
                record_type,
                record_id,
            ),
        )
