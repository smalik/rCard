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
from datetime import datetime, time
from typing import Any
from uuid import UUID

import psycopg
from psycopg import sql

from plytos_api.agents.model import (
    AgentName,
    Channel,
    CheckInPlan,
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
from plytos_api.cards.model import MainContent, VariantContent
from plytos_api.cards.repository import (
    Author,
    CardDetail,
    CardNotFoundError,
    CardRepository,
    UnsupportedClaimsError,
)
from plytos_api.ids import uuid7
from plytos_api.keys import UserCipher
from plytos_api.resumes.model import ResumeContent
from plytos_api.resumes.store import ResumeDetail, ResumeStore


class AgentRecordNotFoundError(Exception):
    pass


class CheckInPlanError(ValueError):
    """The plan can't be saved as given, such as an unknown time zone."""


class ProposalConflictError(Exception):
    """The proposal can't be decided as asked: it was decided already, or it
    isn't the kind that turns into a card."""


_PROPOSAL_COLUMNS = sql.SQL(
    "id, agent, kind, state, card_id, cites, payload_ciphertext, created_at, decided_at,"
    " result_version_id, result_resume_version_id"
)
_TIDBIT_COLUMNS = sql.SQL(
    "id, kind, said_at, body_ciphertext, message_id, card_id, reading_ciphertext, read_at,"
    " created_at"
)
_RUN_COLUMNS = sql.SQL(
    "id, agent, trigger_kind, trigger_id, state, attempts, model, input_tokens, output_tokens,"
    " error_code, created_at, run_after, finished_at"
)


# The plan's day in this month and the next two, as local times in the
# person's time zone, and the first of them still to come. A week of -1 is the
# last such weekday of the month.
_NEXT_CHECK_IN = """
select min(slot) from (
  select (
    case when %(week)s = -1
      then (g.m + interval '1 month' - interval '1 day')::date
        - ((extract(isodow from g.m + interval '1 month' - interval '1 day')::int
            - %(weekday)s + 7) %% 7)
      else g.m::date + ((%(weekday)s - extract(isodow from g.m)::int + 7) %% 7)
        + (%(week)s - 1) * 7
    end + %(time)s::time
  ) at time zone %(tz)s as slot
  from generate_series(
    date_trunc('month', coalesce(%(after)s, clock_timestamp()) at time zone %(tz)s),
    date_trunc('month', coalesce(%(after)s, clock_timestamp()) at time zone %(tz)s)
      + interval '2 months',
    interval '1 month') as g(m)
) s
where slot > coalesce(%(after)s, clock_timestamp())
"""


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

    def share_resume(self, import_id: UUID) -> MessageView:
        """The person shares a resume in the conversation. The import itself is
        kept by ImportStore and read in the background; Plytos answers with what
        it read once it's done (answer_shared_resume)."""
        shared = self._message("person", "Here's my resume.", "app", None, import_id)
        self._event("person", "message.sent", "message", shared.id)
        return shared

    def answer_shared_resume(self, import_id: UUID, text: str) -> MessageView | None:
        """Plytos says what it read from a resume shared in the conversation, once.
        Nothing is said about an upload the person didn't share here."""
        row = self._conn.execute(
            "select bool_or(author = 'person'), bool_or(author = 'plytos')"
            " from plytos.message where import_id = %s",
            (import_id,),
        ).fetchone()
        if row is None or not row[0] or row[1]:
            return None
        answer = self._message("plytos", text, "app", None, import_id)
        self._event("system", "message.sent", "message", answer.id, "import")
        return answer

    def ask_for_resume(self, text: str, resume_id: UUID) -> MessageView:
        """The person asks for a version of one of their resumes. The Assembler
        puts it together; the Listener doesn't need to read it."""
        message = self._message("person", text, "app", None, resume_id=resume_id)
        self._event("person", "message.sent", "message", message.id)
        self.enqueue("assembler", "message", message.id)
        return message

    def notice(self, text: str, ref: str) -> MessageView:
        """Saves a message from Plytos that no agent wrote, such as confirming a
        change the person made. `ref` says what wrote it."""
        message = self._message("plytos", text, "app", None)
        self._event("system", "message.sent", "message", message.id, ref)
        return message

    def message(self, message_id: UUID) -> MessageView:
        row = self._conn.execute(
            "select id, author, channel, body_ciphertext, proposal_id, created_at, import_id,"
            " resume_id"
            " from plytos.message where id = %s",
            (message_id,),
        ).fetchone()
        if row is None:
            raise AgentRecordNotFoundError(str(message_id))
        return self._message_view(row)

    def conversation(self, limit: int = 50, before: UUID | None = None) -> list[MessageView]:
        """The latest messages, oldest first. `before` pages further back."""
        rows = self._conn.execute(
            "select id, author, channel, body_ciphertext, proposal_id, created_at, import_id,"
            " resume_id"
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

    def keep_resume(
        self,
        proposal_id: UUID,
        cards: CardRepository,
        resumes: ResumeStore,
        edited: ResumeContent | None = None,
        rewordings: Sequence[UUID] | None = None,
    ) -> tuple[ProposalView, ResumeDetail]:
        """Turns a proposed resume into a resume made from its parent, for its
        target. Kept as proposed, its first version is the agent's; kept after
        the person's changes, it's theirs.

        The lines the agent worded for the target become each card's variant
        for it, as the agent's versions. `rewordings` names the cards whose
        new wording the person kept; None keeps them all."""
        proposal = self._open_for_update(proposal_id)
        new = proposal.body.resume
        if proposal.kind != "resume" or new is None:
            raise ProposalConflictError("Only a proposed resume can be kept as a resume.")
        target = cards.create_target(new.target_kind, new.target, None)
        wanted = None if rewordings is None else set(rewordings)
        for r in new.rewordings:
            if wanted is not None and r.card not in wanted:
                continue
            try:
                cards.create_variant(
                    r.card,
                    target.id,
                    VariantContent(framing=r.framing),
                    Author("ai", proposal.agent),
                )
            except (CardNotFoundError, UnsupportedClaimsError):
                # The card changed or went since the draft: it keeps its own wording.
                continue
        author = (
            Author("person", str(self._user_id))
            if edited is not None
            else Author("ai", proposal.agent)
        )
        resume = resumes.create(
            new.name,
            edited if edited is not None else new.content,
            author,
            target_id=target.id,
            parent_id=new.parent_id,
            synced_parent_version_id=new.parent_version_id,
        )
        state: ProposalState = "kept" if edited is None else "edited"
        self._decide(proposal_id, state, None, resume.head.id)
        self._event("person", f"proposal.{state}", "proposal", proposal_id)
        return self.proposal(proposal_id), resume

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

    # -- check-ins -------------------------------------------------------------

    def check_in_plan(self) -> CheckInPlan | None:
        row = self._conn.execute(
            "select state, week, weekday, local_time, time_zone from plytos.check_in_plan"
        ).fetchone()
        if row is None:
            return None
        return CheckInPlan(
            state=row[0],
            week=row[1],
            weekday=row[2],
            time=row[3].strftime("%H:%M"),
            time_zone=row[4],
        )

    def set_check_in_plan(self, plan: CheckInPlan) -> datetime | None:
        """Saves when the person wants check-ins. When they're on, the next one
        is queued (or moved) for the next time due, which comes back."""
        known = self._conn.execute(
            "select exists (select 1 from pg_timezone_names where name = %s)", (plan.time_zone,)
        ).fetchone()
        if not known or not known[0]:
            raise CheckInPlanError("Plytos doesn't know that time zone.")
        self._conn.execute(
            "insert into plytos.check_in_plan"
            " (owner_id, state, week, weekday, local_time, time_zone)"
            " values (%(owner)s, %(state)s, %(week)s, %(weekday)s, %(time)s, %(tz)s)"
            " on conflict (owner_id) do update set state = excluded.state,"
            " week = excluded.week, weekday = excluded.weekday,"
            " local_time = excluded.local_time, time_zone = excluded.time_zone,"
            " updated_at = clock_timestamp()",
            {
                "owner": self._user_id,
                "state": plan.state,
                "week": plan.week,
                "weekday": plan.weekday,
                "time": time.fromisoformat(plan.time),
                "tz": plan.time_zone,
            },
        )
        self._event("person", f"check_in.turned_{plan.state}", "check_in_plan", self._user_id)
        if plan.state != "on":
            return None
        return self.schedule_check_in(plan)

    def schedule_check_in(self, plan: CheckInPlan, after: datetime | None = None) -> datetime:
        """Queues the Check-in agent for the plan's next time after `after`
        (now by default), worked out in the person's time zone. A check-in
        already queued is moved, not doubled."""
        row = self._conn.execute(
            _NEXT_CHECK_IN,
            {
                "week": plan.week,
                "weekday": plan.weekday,
                "time": time.fromisoformat(plan.time),
                "tz": plan.time_zone,
                "after": after,
            },
        ).fetchone()
        assert row is not None and row[0] is not None
        due: datetime = row[0]
        self.schedule("check_in", "schedule", due, dedupe_key="check_in")
        return due

    def next_check_in(self) -> datetime | None:
        row = self._conn.execute(
            "select r.run_after from plytos.agent_run r join plytos.check_in_plan p"
            " on p.owner_id = r.owner_id and p.state = 'on'"
            " where r.dedupe_key = 'check_in' and r.state = 'queued'"
        ).fetchone()
        return row[0] if row else None

    def last_said(self) -> datetime | None:
        """When the person last wrote anything."""
        row = self._conn.execute(
            "select max(created_at) from plytos.message where author = 'person'"
        ).fetchone()
        return row[0] if row else None

    def check_ins_asked(self, limit: int = 3) -> tuple[int, list[MessageView]]:
        """How many check-ins Plytos has asked, and the latest few, newest first."""
        count = self._conn.execute(
            "select count(*) from plytos.event where action = 'check_in.asked'"
        ).fetchone()
        rows = self._conn.execute(
            "select m.id, m.author, m.channel, m.body_ciphertext, m.proposal_id, m.created_at,"
            " m.import_id, m.resume_id"
            " from plytos.event e join plytos.message m on m.id = e.record_id"
            " where e.action = 'check_in.asked'"
            " order by m.created_at desc, m.id desc limit %s",
            (limit,),
        ).fetchall()
        return (count[0] if count else 0), [self._message_view(r) for r in rows]

    def followed_up(self) -> set[UUID]:
        """Drafts and notes a check-in already asked about."""
        rows = self._conn.execute(
            "select record_id from plytos.event where action = 'check_in.followed_up'"
        ).fetchall()
        return {r[0] for r in rows}

    def asked(self, message_id: UUID, about: tuple[str, UUID] | None = None) -> None:
        """Records that a message was a check-in, and what it followed up."""
        self._event("ai", "check_in.asked", "message", message_id, "check_in")
        if about is not None:
            self._event("ai", "check_in.followed_up", about[0], about[1], "check_in")

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

    def schedule(
        self, agent: AgentName, trigger_kind: TriggerKind, at: datetime, *, dedupe_key: str
    ) -> None:
        """Queues a run for a set time. A run already queued under the key is
        moved to that time instead."""
        self._conn.execute(
            "insert into plytos.agent_run (id, owner_id, agent, trigger_kind, dedupe_key,"
            " run_after) values (%s, %s, %s, %s, %s, %s)"
            " on conflict (owner_id, dedupe_key) where state = 'queued' and dedupe_key is not null"
            " do update set run_after = excluded.run_after",
            (uuid7(), self._user_id, agent, trigger_kind, dedupe_key, at),
        )

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
        resume_id: UUID | None = None,
    ) -> MessageView:
        message_id = uuid7()
        row = self._conn.execute(
            "insert into plytos.message (id, owner_id, author, channel, body_ciphertext,"
            " proposal_id, import_id, resume_id) values (%s, %s, %s, %s, %s, %s, %s, %s)"
            " returning id, author, channel, body_ciphertext, proposal_id, created_at,"
            " import_id, resume_id",
            (
                message_id,
                self._user_id,
                author,
                channel,
                self._cipher.encrypt(text.encode(), _aad("message", message_id)),
                proposal_id,
                import_id,
                resume_id,
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

    def _decide(
        self,
        proposal_id: UUID,
        state: ProposalState,
        version_id: UUID | None,
        resume_version_id: UUID | None = None,
    ) -> None:
        self._conn.execute(
            "update plytos.proposal set state = %s, decided_at = now(), result_version_id = %s,"
            " result_resume_version_id = %s where id = %s",
            (state, version_id, resume_version_id, proposal_id),
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
            resume_id=row[7],
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
            result_resume_version_id=row[10],
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
            run_after=row[11],
            finished_at=row[12],
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
