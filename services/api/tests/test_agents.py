"""Agents: the conversation, tidbits, proposals, and the queue that runs them.

Agents here think through a fake that answers from the prompt it's given, so
nothing calls a model. The queue is shared by every person in the test
database, so each test that runs the worker drains it first and checks only
its own person's rows.
"""

import json
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from psycopg import errors
from pydantic import BaseModel

from plytos_api.agents.check_in import (
    QUESTIONS,
    CheckIn,
    CheckInAnswer,
    plan_confirmation,
    plan_label,
)
from plytos_api.agents.listener import FALLBACK_REPLY, Listener, ListenerAnswer
from plytos_api.agents.model import CheckInPlan, NewCard, ProposalBody, Reading
from plytos_api.agents.resume import reading
from plytos_api.agents.runtime import Agent, Context, Worker
from plytos_api.agents.stitcher import StitchedWin, Stitcher, StitcherAnswer
from plytos_api.agents.store import (
    AgentRecordNotFoundError,
    AgentStore,
    CheckInPlanError,
    ProposalConflictError,
)
from plytos_api.agents.thinking import Usage
from plytos_api.cards.model import Framing, MainContent
from plytos_api.cards.repository import Author, CardRepository
from plytos_api.db import Database
from plytos_api.imports.pipeline import import_resume
from plytos_api.imports.store import ImportStore
from plytos_api.keys import Vault

from .resume_samples import promotions_text

ME = Author("person")

Stores = Callable[[UUID], AbstractContextManager[tuple[AgentStore, CardRepository]]]


@pytest.fixture
def stores(db: Database, vault: Vault) -> Stores:
    @contextmanager
    def _stores(user_id: UUID) -> Iterator[tuple[AgentStore, CardRepository]]:
        with db.as_user(user_id) as conn:
            cipher = vault.cipher_for(conn, user_id)
            yield AgentStore(conn, user_id, cipher), CardRepository(conn, user_id, cipher)

    return _stores


MakeWorker = Callable[..., Worker]


@pytest.fixture
def worker(db: Database, vault: Vault) -> MakeWorker:
    """Builds a worker over the given agents, after running out whatever other
    tests left in the queue."""
    quiet: dict[str, Agent] = {
        "listener": Listener(None, 0),
        "stitcher": Stitcher(None),
        "check_in": CheckIn(None),
    }
    Worker(db, vault, quiet, retry_base_seconds=0).run_until_idle()

    def _worker(*agents: Agent, retry_base_seconds: int = 0) -> Worker:
        crew = dict(quiet) | {a.name: a for a in agents}
        return Worker(db, vault, crew, retry_base_seconds=retry_base_seconds)

    return _worker


class FakeThinker:
    """Answers each call from the prompt, through the function given for that
    answer type, and remembers what it was asked."""

    def __init__(self, **respond: Callable[[dict[str, Any]], BaseModel | None]) -> None:
        self._respond = respond
        self.asked: list[tuple[str, dict[str, Any]]] = []

    def think(self, system: str, prompt: str, answer: type[Any], usage: Usage) -> Any:
        data = json.loads(prompt)
        self.asked.append((answer.__name__, data))
        usage.model = "fake"
        usage.input_tokens += 10
        usage.output_tokens += 2
        respond = self._respond.get(answer.__name__)
        return respond(data) if respond else None


class Scripted:
    """An agent whose work a test writes."""

    def __init__(self, name: Any, act: Callable[[Context], None]) -> None:
        self.name = name
        self._act = act
        self.calls = 0

    def run(self, ctx: Context) -> None:
        self.calls += 1
        self._act(ctx)


def proposed_card(headline: str = "Cut late shipments from 12% to 7%") -> NewCard:
    return NewCard(
        kind="accomplishment",
        content=MainContent(facts={"figures": ["12%", "7%"]}, framing=Framing(headline=headline)),
    )


def offer(store: AgentStore, cites: list[UUID] | None = None) -> UUID:
    body = ProposalBody(message="I think these notes are one win.", card=proposed_card())
    return store.propose("stitcher", "new_card", body, cites=cites or []).id


def career(cards: CardRepository) -> UUID:
    """Riley's current job: Operations Manager at Northwind Logistics."""
    job = cards.create_card(
        "employment",
        MainContent(
            facts={"employer": "Northwind Logistics", "start": "2014-03", "end": "present"},
            framing=Framing(headline="Northwind Logistics"),
        ),
        ME,
    )
    role = cards.create_card(
        "position",
        MainContent(
            parent=job.id,
            facts={"title": "Operations Manager", "start": "2021-01"},
            framing=Framing(headline="Operations Manager"),
        ),
        ME,
    )
    return role.id


def note(store: AgentStore, text: str, day: str, card_id: UUID | None) -> UUID:
    said_at = datetime.fromisoformat(day).replace(tzinfo=UTC)
    tidbit = store.add_tidbit("text", text, said_at=said_at, agent="listener")
    store.read_tidbit(tidbit.id, card_id, Reading(summary=text))
    return tidbit.id


# -- what the database guarantees ----------------------------------------------


def test_people_only_see_their_own_agent_records(make_user, stores: Stores, db: Database) -> None:
    alice, bob = make_user(), make_user()
    with stores(alice) as (store, _):
        said = store.say("Shipped the new routing tool to 3 sites")
        tidbit = store.add_tidbit("text", said.text, message_id=said.id)
        proposal_id = offer(store, [tidbit.id])
        [run] = store.runs()
    with stores(bob) as (store, cards):
        assert store.conversation() == []
        assert store.tidbits() == []
        assert store.proposals(None) == []
        assert store.runs() == []
        for read, record_id in (
            (store.message, said.id),
            (store.tidbit, tidbit.id),
            (store.proposal, proposal_id),
            (store.run, run.id),
            (store.dismiss, proposal_id),
        ):
            with pytest.raises(AgentRecordNotFoundError):
                read(record_id)
        with pytest.raises(AgentRecordNotFoundError):
            store.keep(proposal_id, cards)
    with db.as_user(bob) as conn:
        for table in ("message", "tidbit", "proposal", "agent_run"):
            count = conn.execute(f"select count(*) from plytos.{table}").fetchone()  # noqa: S608
            assert count == (0,), table
    with db.pool.connection() as conn:
        assert conn.execute("select count(*) from plytos.message").fetchone() == (0,)


def test_cannot_write_agent_records_for_someone_else(make_user, db: Database) -> None:
    alice, bob = make_user(), make_user()
    with pytest.raises(errors.InsufficientPrivilege), db.as_user(bob) as conn:
        conn.execute(
            "insert into plytos.agent_run (owner_id, agent, trigger_kind)"
            " values (%s, 'listener', 'schedule')",
            (alice,),
        )


def test_what_people_say_is_kept_as_they_said_it(make_user, stores: Stores, db: Database) -> None:
    user = make_user()
    with stores(user) as (store, _):
        said = store.say("Late shipments are down to 7% at the Dayton site")
        tidbit_id = note(store, said.text, "2026-10-20", None)
        proposal_id = offer(store, [tidbit_id])
    with db.as_user(user) as conn:
        for (blob,) in conn.execute(
            "select body_ciphertext from plytos.message union all"
            " select body_ciphertext from plytos.tidbit union all"
            " select payload_ciphertext from plytos.proposal"
        ).fetchall():
            assert b"Dayton" not in bytes(blob)
    for statement, record_id in (
        ("update plytos.message set body_ciphertext = body_ciphertext where id = %s", said.id),
        ("delete from plytos.message where id = %s", said.id),
        ("update plytos.tidbit set body_ciphertext = body_ciphertext where id = %s", tidbit_id),
        ("update plytos.tidbit set said_at = now() where id = %s", tidbit_id),
        ("delete from plytos.tidbit where id = %s", tidbit_id),
        ("update plytos.proposal set cites = '{}' where id = %s", proposal_id),
        ("delete from plytos.proposal where id = %s", proposal_id),
        ("delete from plytos.agent_run where owner_id = %s", user),
    ):
        with pytest.raises(errors.InsufficientPrivilege), db.as_user(user) as conn:
            conn.execute(statement, (record_id,))


def test_a_tidbit_is_read_once(make_user, stores: Stores, db: Database) -> None:
    user = make_user()
    with stores(user) as (store, _):
        tidbit = store.add_tidbit("text", "Cut late shipments from 12% to 7%")
        assert tidbit.reading is None and tidbit.read_at is None
        read = store.read_tidbit(
            tidbit.id, None, Reading(summary="Cut late shipments", figures=["12%", "7%"])
        )
        assert read.reading is not None and read.reading.figures == ["12%", "7%"]
        assert read.text == tidbit.text and read.read_at is not None
        with pytest.raises(AgentRecordNotFoundError):
            store.read_tidbit(tidbit.id, None, Reading(summary="Something else"))
    with pytest.raises(errors.CheckViolation), db.as_user(user) as conn:
        conn.execute("update plytos.tidbit set card_id = null where id = %s", (tidbit.id,))


def test_keeping_a_proposal_makes_a_card_the_agent_wrote(
    make_user, stores: Stores, db: Database
) -> None:
    user = make_user()
    with stores(user) as (store, cards):
        proposal_id = offer(store)
        offered = store.conversation()[-1]
        assert offered.author == "plytos"
        assert offered.proposal is not None and offered.proposal.id == proposal_id
        kept, card = store.keep(proposal_id, cards)
        assert kept.state == "kept" and kept.decided_at is not None
        assert kept.result_version_id == card.main.head.id
        assert card.status == "approved"
        assert card.main.head.author_kind == "ai"
        assert card.main.content == proposed_card().content
        with pytest.raises(ProposalConflictError):
            store.keep(proposal_id, cards)
        with pytest.raises(ProposalConflictError):
            store.dismiss(proposal_id)
    with pytest.raises(errors.CheckViolation), db.as_user(user) as conn:
        conn.execute("update plytos.proposal set state = 'open' where id = %s", (proposal_id,))


def test_keeping_after_edits_makes_the_card_the_persons(make_user, stores: Stores) -> None:
    user = make_user()
    mine = proposed_card("Cut late shipments from 12% to 7% across 9 carriers").content
    with stores(user) as (store, cards):
        kept, card = store.keep(offer(store), cards, edited=mine)
        assert kept.state == "edited"
        assert card.main.head.author_kind == "person"
        assert card.main.content == mine


def test_proposals_can_be_dismissed_or_replaced(make_user, stores: Stores) -> None:
    user = make_user()
    with stores(user) as (store, cards):
        first, second = offer(store), offer(store)
        question = store.propose(
            "stitcher", "question", ProposalBody(message="Did late shipments drop?")
        ).id
        assert store.dismiss(first).state == "dismissed"
        store.supersede(second, "stitcher")
        assert store.proposal(second).state == "superseded"
        with pytest.raises(ProposalConflictError):
            store.keep(question, cards)
        assert [p.id for p in store.proposals()] == [question]
        assert {p.id for p in store.proposals(None)} == {first, second, question}
        assert cards.list_cards() == []


def test_the_queue_keeps_one_waiting_run_per_key(make_user, stores: Stores) -> None:
    user = make_user()
    with stores(user) as (store, _):
        first = store.enqueue("stitcher", "tidbit", dedupe_key="stitcher", delay_seconds=60)
        again = store.enqueue("stitcher", "tidbit", dedupe_key="stitcher")
        assert first is not None and again is None
        assert [r.id for r in store.runs()] == [first]


def test_claiming_takes_due_runs_once(make_user, stores: Stores, db: Database) -> None:
    user = make_user()
    with stores(user) as (store, _):
        due = store.enqueue("listener", "schedule")
        later = store.enqueue("stitcher", "schedule", delay_seconds=3600)
    claim = "select id, owner_id, agent from plytos.claim_agent_runs(%s, %s)"
    with db.pool.connection() as conn, conn.transaction(force_rollback=True):
        claimed = {r[0]: r for r in conn.execute(claim, (1000, 60)).fetchall()}
        assert claimed[due] == (due, user, "listener")
        assert later not in claimed
        assert due not in {r[0] for r in conn.execute(claim, (1000, 60)).fetchall()}


# -- the worker ---------------------------------------------------------------


def test_a_finished_run_records_what_it_spent(
    make_user, stores: Stores, worker: MakeWorker
) -> None:
    user = make_user()

    def check_in(ctx: Context) -> None:
        ctx.store.reply("Morning. What moved this week?", "check_in")
        ctx.usage.model = "test-model"
        ctx.usage.input_tokens += 12
        ctx.usage.output_tokens += 5

    with stores(user) as (store, _):
        run_id = store.enqueue("check_in", "schedule")
    worker(Scripted("check_in", check_in)).run_until_idle()
    with stores(user) as (store, _):
        run = store.run(run_id)
        assert (run.state, run.attempts, run.error_code) == ("done", 1, None)
        assert (run.model, run.input_tokens, run.output_tokens) == ("test-model", 12, 5)
        assert run.finished_at is not None
        assert [m.text for m in store.conversation()] == ["Morning. What moved this week?"]


def test_a_failing_run_leaves_nothing_behind_and_stops_after_three_tries(
    make_user, stores: Stores, worker: MakeWorker
) -> None:
    user = make_user()

    def half_done(ctx: Context) -> None:
        ctx.store.reply("Halfway there", "check_in")
        raise RuntimeError("boom")

    agent = Scripted("check_in", half_done)
    with stores(user) as (store, _):
        run_id = store.enqueue("check_in", "schedule")
    worker(agent).run_until_idle()
    with stores(user) as (store, _):
        run = store.run(run_id)
        assert (run.state, run.attempts, run.error_code) == ("failed", 3, "error_runtime_error")
        assert store.conversation() == []
    assert agent.calls >= 3


def test_when_the_model_does_not_answer_the_run_waits_to_try_again(
    make_user, stores: Stores, worker: MakeWorker
) -> None:
    user = make_user()
    silent = FakeThinker()
    with stores(user) as (store, _):
        said = store.say("Closed the Q3 audit with no findings")
    worker(Listener(silent, 0), retry_base_seconds=60).run_until_idle()
    with stores(user) as (store, _):
        [run] = store.runs()
        assert (run.state, run.attempts, run.error_code) == ("queued", 1, "model_no_answer")
        assert [m.id for m in store.conversation()] == [said.id]
        assert store.tidbits() == []


# -- the Listener ---------------------------------------------------------------


def test_with_ai_off_the_listener_keeps_the_note_under_the_current_job(
    make_user, stores: Stores, worker: MakeWorker
) -> None:
    user = make_user()
    with stores(user) as (store, cards):
        role = career(cards)
        said = store.say("Cut late shipments from 12% to 7% this quarter")
    worker().run_until_idle()
    with stores(user) as (store, _):
        [kept] = store.tidbits()
        assert (kept.text, kept.message_id, kept.card_id) == (said.text, said.id, role)
        assert kept.reading is not None and kept.reading.figures == ["12%", "7%"]
        assert store.conversation()[-1].text == FALLBACK_REPLY
        assert sorted((r.agent, r.state) for r in store.runs()) == [
            ("listener", "done"),
            ("stitcher", "done"),
        ]


def test_the_listener_files_the_note_and_drops_numbers_nobody_wrote(
    make_user, stores: Stores, worker: MakeWorker
) -> None:
    user = make_user()
    thinker = FakeThinker(
        ListenerAnswer=lambda data: ListenerAnswer(
            about_work=True,
            job=data["jobs"][0]["ref"],
            summary="Cut late shipments from 12% to 7% with a carrier scorecard",
            projects=["Carrier scorecard"],
            figures=["12%", "7%", "25%"],
            has_outcome=True,
            reply="That's a real drop. Which carriers moved the most?",
        )
    )
    with stores(user) as (store, cards):
        role = career(cards)
        store.reply("What moved this week?", "check_in")
        said = store.say("Late shipments went from 12% to 7% after the carrier scorecard")
    worker(Listener(thinker, 30)).run_until_idle()

    [(_, prompt)] = [a for a in thinker.asked if a[1]["new_message"] == said.text]
    assert prompt["jobs"] == [
        {
            "ref": "job-1",
            "job": "Operations Manager at Northwind Logistics (2021-01 to present)",
            "current": True,
        }
    ]
    assert prompt["earlier_messages"] == [{"from": "plytos", "text": "What moved this week?"}]
    with stores(user) as (store, _):
        [kept] = store.tidbits()
        assert kept.card_id == role and kept.text == said.text
        assert kept.reading is not None
        assert kept.reading.figures == ["12%", "7%"]
        assert kept.reading.projects == ["Carrier scorecard"]
        assert kept.reading.has_outcome
        assert store.conversation()[-1].text == "That's a real drop. Which carriers moved the most?"
        waiting = [r for r in store.runs() if r.agent == "stitcher"]
        assert [r.state for r in waiting] == ["queued"]


def test_small_talk_gets_a_reply_and_no_note(make_user, stores: Stores, worker: MakeWorker) -> None:
    user = make_user()
    thinker = FakeThinker(
        ListenerAnswer=lambda data: ListenerAnswer(
            about_work=False,
            job="",
            summary="",
            projects=[],
            figures=[],
            has_outcome=False,
            reply="I keep notes on your work. Tell me what happened any time.",
        )
    )
    with stores(user) as (store, _):
        store.say("What's the weather like?")
    worker(Listener(thinker, 0)).run_until_idle()
    with stores(user) as (store, _):
        assert store.tidbits() == []
        assert store.conversation()[-1].author == "plytos"
        assert [r.agent for r in store.runs()] == ["listener"]


# -- the Stitcher ---------------------------------------------------------------

SCORECARD = "Started a carrier scorecard because late shipments were at 12%."
ROLLOUT = "Rolled the scorecard out to all 9 carriers."
RESULT = "Late shipments are down to 7% this quarter."


def stitch(data: dict[str, Any]) -> StitcherAnswer:
    """Joins the scorecard notes, the way a model might, plus one win that
    claims a number no note has."""
    refs = [n["ref"] for n in data["notes"]]
    invented = StitchedWin(
        notes=refs[:1],
        headline="Cut late shipments by 40%",
        body="",
        missing="",
        message="One win.",
    )
    if len(refs) == 2:
        win = StitchedWin(
            notes=refs,
            headline="Built a carrier scorecard and rolled it out to all 9 carriers",
            body="Late shipments were at 12% when it started.",
            missing="Did late shipments drop?",
            message="I think two of your notes are one win. Did late shipments drop?",
        )
    else:
        win = StitchedWin(
            notes=refs,
            headline="Cut late shipments from 12% to 7% with a scorecard for all 9 carriers",
            body="",
            missing="",
            message="Your scorecard notes have a result now.",
        )
    return StitcherAnswer(wins=[win, invented])


def test_the_stitcher_joins_notes_into_one_win_and_improves_it(
    make_user, stores: Stores, worker: MakeWorker
) -> None:
    user = make_user()
    thinker = FakeThinker(StitcherAnswer=stitch)
    stitcher = Stitcher(thinker)
    with stores(user) as (store, cards):
        role = career(cards)
        scorecard = note(store, SCORECARD, "2026-08-03", role)
        rollout = note(store, ROLLOUT, "2026-09-14", role)
        store.enqueue("stitcher", "tidbit")
    worker(stitcher).run_until_idle()

    with stores(user) as (store, _):
        [draft] = store.proposals()
        assert draft.agent == "stitcher" and draft.kind == "new_card"
        assert draft.cites == [scorecard, rollout]
        assert draft.body.card is not None
        assert draft.body.card.missing == "Did late shipments drop?"
        content = draft.body.card.content
        assert content.parent == role
        assert content.framing.headline.startswith("Built a carrier scorecard")
        assert content.facts == {"date": "2026-09"}
        offered = store.conversation()[-1]
        assert offered.proposal is not None and offered.proposal.id == draft.id
        assert offered.text.startswith("I think two of your notes")

        result = note(store, RESULT, "2026-10-20", role)
        store.enqueue("stitcher", "tidbit")
    worker(stitcher).run_until_idle()

    _, second = [a for a in thinker.asked if a[0] == "StitcherAnswer"][-1]
    assert second["job"] == "Operations Manager at Northwind Logistics (2021-01 to present)"
    assert second["earlier_drafts"] == [
        {"notes": ["n1", "n2"], "headline": content.framing.headline}
    ]
    with stores(user) as (store, cards):
        assert store.proposal(draft.id).state == "superseded"
        [better] = store.proposals()
        assert better.cites == [scorecard, rollout, result]
        assert better.body.card is not None and better.body.card.missing is None
        assert "7%" in better.body.card.content.framing.headline

        asked = len(thinker.asked)
        store.enqueue("stitcher", "tidbit")
    worker(stitcher).run_until_idle()
    assert len(thinker.asked) == asked  # Nothing new since the draft.

    with stores(user) as (store, cards):
        store.keep(better.id, cards)
        store.enqueue("stitcher", "tidbit")
    worker(stitcher).run_until_idle()
    assert len(thinker.asked) == asked  # Notes in a kept card are used.
    with stores(user) as (store, cards):
        [win] = [c for c in cards.list_cards() if c.kind == "accomplishment"]
        assert win.parent_id == role
        assert store.proposals() == []


# -- a resume shared in the conversation -----------------------------------------


def share(db: Database, vault: Vault, user: UUID) -> tuple[UUID, list[UUID]]:
    data = promotions_text().encode()
    result = import_resume(data, "Avery Quinn.txt")
    with db.as_user(user) as conn:
        cipher = vault.cipher_for(conn, user)
        kept = ImportStore(conn, user, cipher).create(data, "Avery Quinn.txt", result)
        store = AgentStore(conn, user, cipher)
        shared = store.share_resume(kept.id)
        answer = store.answer_shared_resume(kept.id, reading(result))
        # Plytos answers once.
        assert answer is not None and store.answer_shared_resume(kept.id, "again") is None
    return kept.id, [shared.id, answer.id]


def test_a_shared_resume_sits_in_the_conversation_until_it_is_deleted(
    make_user, stores: Stores, db: Database, vault: Vault
) -> None:
    user = make_user()
    import_id, _ = share(db, vault, user)
    with stores(user) as (store, _):
        shared, answer = store.conversation()
        assert (shared.author, shared.import_id) == ("person", import_id)
        assert (answer.author, answer.import_id) == ("plytos", import_id)
        assert answer.text == reading(import_resume(promotions_text().encode(), "Avery Quinn.txt"))
        assert answer.text.startswith("I read it: ")
        assert answer.text.endswith("Nothing becomes a card until you keep it.")
        assert store.runs() == []  # Sharing a resume isn't a note for the Listener.
    with db.as_user(user) as conn:
        ImportStore(conn, user, vault.cipher_for(conn, user)).delete(import_id)
    with stores(user) as (store, _):
        assert [(m.author, m.import_id) for m in store.conversation()] == [
            ("person", None),
            ("plytos", None),
        ]


def test_a_message_cannot_point_at_someone_elses_resume(
    make_user, db: Database, vault: Vault
) -> None:
    alice, bob = make_user(), make_user()
    import_id, _ = share(db, vault, alice)
    with pytest.raises(errors.ForeignKeyViolation), db.as_user(bob) as conn:
        conn.execute(
            "insert into plytos.message (owner_id, author, body_ciphertext, import_id)"
            " values (%s, 'person', '\\x00', %s)",
            (bob, import_id),
        )


def test_reading_says_what_was_found_and_what_is_left() -> None:
    result = import_resume(promotions_text().encode(), "Avery Quinn.txt")
    empty = result.model_copy(update={"cards": [], "findings": []})
    assert reading(empty).startswith("I couldn't find roles or results")
    assert "a quick answer first" in reading(result) or "Go through them" in reading(result)


# -- check-ins ----------------------------------------------------------------

LAST_FRIDAY = CheckInPlan(week=-1, weekday=5, time="16:00", time_zone="America/Chicago")


def due_now(store: AgentStore, minutes_ago: float = 1) -> None:
    """Moves the queued check-in so it's due."""
    at = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    store.schedule("check_in", "schedule", at, dedupe_key="check_in")


def asked(store: AgentStore) -> list[str]:
    """The check-in questions Plytos asked, oldest first."""
    return [m.text for m in reversed(store.check_ins_asked(20)[1])]


def queued_check_ins(db: Database, user: UUID) -> int:
    with db.as_user(user) as conn:
        row = conn.execute(
            "select count(*) from plytos.agent_run where agent = 'check_in' and state = 'queued'"
        ).fetchone()
    return row[0] if row else 0


def test_check_in_plans_are_private(make_user, stores: Stores, db: Database) -> None:
    alice, bob = make_user(), make_user()
    with stores(alice) as (store, _):
        store.set_check_in_plan(LAST_FRIDAY)
        assert store.check_in_plan() == LAST_FRIDAY
    with stores(bob) as (store, _):
        assert store.check_in_plan() is None
        assert store.next_check_in() is None
    with db.as_user(bob) as conn:
        assert conn.execute("select count(*) from plytos.check_in_plan").fetchone() == (0,)
    with pytest.raises(errors.InsufficientPrivilege), db.as_user(bob) as conn:
        conn.execute(
            "insert into plytos.check_in_plan"
            " (owner_id, state, week, weekday, local_time, time_zone)"
            " values (%s, 'on', 1, 1, '09:00', 'UTC')",
            (alice,),
        )


def test_a_plan_needs_a_real_time_zone(make_user, stores: Stores) -> None:
    with stores(make_user()) as (store, _), pytest.raises(CheckInPlanError):
        store.set_check_in_plan(LAST_FRIDAY.model_copy(update={"time_zone": "Mars/Olympus"}))


def test_check_ins_come_once_a_month_at_the_persons_local_time(
    make_user, stores: Stores, db: Database
) -> None:
    user = make_user()

    def utc(text: str) -> datetime:
        return datetime.fromisoformat(text).replace(tzinfo=UTC)

    with stores(user) as (store, _):
        # The last Friday of November, 4 PM in Chicago, is 22:00 UTC.
        assert store.schedule_check_in(LAST_FRIDAY, utc("2026-11-04T12:00")) == utc(
            "2026-11-27T22:00"
        )
        # In October, before the clocks went back, it was 21:00 UTC.
        assert store.schedule_check_in(LAST_FRIDAY, utc("2026-10-01T12:00")) == utc(
            "2026-10-30T21:00"
        )
        # Once it's asked, the next is a month on, into the new year.
        assert store.schedule_check_in(LAST_FRIDAY, utc("2026-11-27T22:00")) == utc(
            "2026-12-25T22:00"
        )
        assert store.schedule_check_in(LAST_FRIDAY, utc("2026-12-25T22:00")) == utc(
            "2027-01-29T22:00"
        )
        # The first Monday at 9:30 in Kolkata: November's (the 2nd) has passed.
        first_monday = CheckInPlan(week=1, weekday=1, time="09:30", time_zone="Asia/Kolkata")
        assert store.schedule_check_in(first_monday, utc("2026-11-04T12:00")) == utc(
            "2026-12-07T04:00"
        )
        # Each schedule moved the one queued check-in rather than adding one.
        store.set_check_in_plan(LAST_FRIDAY)
        next_at = store.next_check_in()
        assert next_at is not None and next_at > datetime.now(UTC)
    assert queued_check_ins(db, user) == 1


def test_a_check_in_asks_one_question_and_queues_next_month(
    make_user, stores: Stores, worker: MakeWorker
) -> None:
    user = make_user()
    with stores(user) as (store, _):
        store.set_check_in_plan(LAST_FRIDAY)
        due_now(store)
    worker(CheckIn(None)).run_until_idle()
    with stores(user) as (store, _):
        assert asked(store) == [QUESTIONS[0]]
        [question] = store.conversation()
        assert question.author == "plytos"
        [run] = [r for r in store.runs() if r.state == "done"]
        assert (run.agent, run.trigger_kind) == ("check_in", "schedule")
        next_at = store.next_check_in()
        assert next_at is not None and next_at > datetime.now(UTC) + timedelta(days=20)


def test_a_check_in_waits_a_day_when_the_person_is_mid_conversation(
    make_user, stores: Stores, worker: MakeWorker
) -> None:
    user = make_user()
    with stores(user) as (store, _):
        store.set_check_in_plan(LAST_FRIDAY)
        store.say("Wrapped the vendor review today")
        due_now(store)
    worker(CheckIn(None)).run_until_idle()
    with stores(user) as (store, _):
        assert asked(store) == []
        next_at = store.next_check_in()
        assert next_at is not None
        assert timedelta(hours=23) < next_at - datetime.now(UTC) < timedelta(hours=24)
        due_now(store)
    worker(CheckIn(None, talking_hours=0)).run_until_idle()
    with stores(user) as (store, _):
        assert asked(store) == [QUESTIONS[0]]


def test_a_late_check_in_is_skipped_and_the_next_one_queued(
    make_user, stores: Stores, worker: MakeWorker
) -> None:
    user = make_user()
    with stores(user) as (store, _):
        store.set_check_in_plan(LAST_FRIDAY)
        due_now(store, minutes_ago=7 * 60)
    worker(CheckIn(None)).run_until_idle()
    with stores(user) as (store, _):
        assert asked(store) == []
        next_at = store.next_check_in()
        assert next_at is not None and next_at > datetime.now(UTC)


def test_turning_check_ins_off_stops_them(
    make_user, stores: Stores, worker: MakeWorker, db: Database
) -> None:
    user = make_user()
    off = LAST_FRIDAY.model_copy(update={"state": "off"})
    with stores(user) as (store, _):
        store.set_check_in_plan(LAST_FRIDAY)
        assert store.set_check_in_plan(off) is None
        assert store.next_check_in() is None
        due_now(store)
    worker(CheckIn(None)).run_until_idle()
    with stores(user) as (store, _):
        assert asked(store) == []
        assert store.check_in_plan() == off
    assert queued_check_ins(db, user) == 0


def test_a_check_in_follows_up_a_draft_missing_its_result_once(
    make_user, stores: Stores, worker: MakeWorker
) -> None:
    user = make_user()
    with stores(user) as (store, _):
        store.set_check_in_plan(LAST_FRIDAY)
        card = proposed_card("Rolled out the new routing tool").model_copy(
            update={"missing": "Did late shipments drop?"}
        )
        body = ProposalBody(message="I think this is a win.", card=card)
        fresh = store.propose("stitcher", "new_card", body).id
        due_now(store)
    # The draft was just offered, and asked already.
    worker(CheckIn(None)).run_until_idle()
    with stores(user) as (store, _):
        assert asked(store) == [QUESTIONS[0]]
        due_now(store)
    later = CheckIn(None, late_hours=24 * 30, clock=lambda: datetime.now(UTC) + timedelta(days=4))
    worker(later).run_until_idle()
    with stores(user) as (store, _):
        assert asked(store)[-1] == "Quick follow-up: Did late shipments drop?"
        assert store.followed_up() == {fresh}
        due_now(store)
    worker(later).run_until_idle()
    with stores(user) as (store, _):
        assert asked(store)[-1] == QUESTIONS[2]


def test_the_model_words_the_question_from_the_persons_own_notes(
    make_user, stores: Stores, worker: MakeWorker
) -> None:
    user = make_user()
    ten_days_ago = (datetime.now(UTC) - timedelta(days=10)).date().isoformat()
    with stores(user) as (store, cards):
        role = career(cards)
        pilot = note(store, "Started the routing pilot at 3 sites", ten_days_ago, role)
        store.set_check_in_plan(LAST_FRIDAY)
        due_now(store)
    replies = iter(
        [
            CheckInAnswer(question="How did the routing pilot at 3 sites go?", follows_up="n1"),
            CheckInAnswer(question="Did late shipments drop by 40%?", follows_up=""),
        ]
    )
    thinker = FakeThinker(CheckInAnswer=lambda _: next(replies))
    agent = CheckIn(thinker)
    worker(agent).run_until_idle()
    [(_, prompt)] = thinker.asked
    assert prompt["jobs"] == ["Operations Manager at Northwind Logistics (2021-01 to present)"]
    assert [n["note"] for n in prompt["notes_without_an_outcome"]] == [
        "Started the routing pilot at 3 sites"
    ]
    with stores(user) as (store, _):
        assert asked(store) == ["How did the routing pilot at 3 sites go?"]
        assert store.followed_up() == {pilot}
        due_now(store)
    worker(agent).run_until_idle()
    with stores(user) as (store, _):
        # 40% is nowhere in the notes, so Plytos asks a plain question instead.
        assert asked(store)[-1] == QUESTIONS[1]
        [_, second] = thinker.asked
        assert second[1]["notes_without_an_outcome"] == []
        assert second[1]["recent_check_ins"] == ["How did the routing pilot at 3 sites go?"]


@pytest.mark.parametrize(
    ("week", "weekday", "time", "label"),
    [
        (-1, 5, "16:00", "The last Friday of the month at 4 PM"),
        (1, 1, "09:30", "The first Monday of the month at 9:30 AM"),
        (2, 3, "12:00", "The second Wednesday of the month at 12 PM"),
        (4, 7, "00:00", "The fourth Sunday of the month at 12 AM"),
        (3, 6, "21:15", "The third Saturday of the month at 9:15 PM"),
    ],
)
def test_plans_are_said_plainly(week: Any, weekday: int, time: str, label: str) -> None:
    plan = CheckInPlan(week=week, weekday=weekday, time=time, time_zone="UTC")
    assert plan_label(plan) == label
    said = plan_confirmation(plan)
    assert said.startswith("Got it. I'll check in once a month, on the ")
    assert "job" not in said.lower()
