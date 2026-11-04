"""Building resumes: as written from an import, versions, branches that take
their parent's changes, how a page reads, and the Assembler in the conversation.

Everyone here is made up and built in code. Agents think through FakeThinker,
so nothing calls a model.
"""

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import pytest
from psycopg import errors

from plytos_api.agents.assembler import (
    AI_OFF,
    NO_RESUME,
    Assembler,
    AssemblerAnswer,
    PickedEntry,
    Reword,
)
from plytos_api.agents.check_in import CheckIn
from plytos_api.agents.listener import Listener, ListenerAnswer
from plytos_api.agents.model import NewResume, ProposalBody
from plytos_api.agents.runtime import Agent, Worker
from plytos_api.agents.stitcher import Stitcher
from plytos_api.agents.store import AgentStore, ProposalConflictError
from plytos_api.cards.model import Framing, MainContent, VariantContent
from plytos_api.cards.repository import Author, CardRepository
from plytos_api.db import Database
from plytos_api.imports.pipeline import import_resume
from plytos_api.imports.store import ImportStore
from plytos_api.keys import Vault
from plytos_api.resumes.as_written import as_written
from plytos_api.resumes.model import ResumeContent, ResumeEntry, ResumeHeader, ResumeItem
from plytos_api.resumes.render import describe, render
from plytos_api.resumes.store import ResumeNotFoundError, ResumeStore, StaleResumeError

from .resume_samples import promotions_text
from .test_agents import FakeThinker

ME = Author("person")


@dataclass
class Stores:
    agents: AgentStore
    cards: CardRepository
    resumes: ResumeStore
    imports: ImportStore


Open = Callable[[UUID], AbstractContextManager[Stores]]


@pytest.fixture
def open_(db: Database, vault: Vault) -> Open:
    @contextmanager
    def _open(user_id: UUID) -> Iterator[Stores]:
        with db.as_user(user_id) as conn:
            cipher = vault.cipher_for(conn, user_id)
            cards = CardRepository(conn, user_id, cipher)
            yield Stores(
                AgentStore(conn, user_id, cipher),
                cards,
                ResumeStore(conn, user_id, cipher),
                ImportStore(conn, user_id, cipher),
            )

    return _open


MakeWorker = Callable[..., Worker]


@pytest.fixture
def worker(db: Database, vault: Vault) -> MakeWorker:
    """Builds a worker over the given agents, after running out whatever other
    tests left in the queue."""
    quiet: dict[str, Agent] = {
        "listener": Listener(None, 0),
        "stitcher": Stitcher(None),
        "check_in": CheckIn(None),
        "assembler": Assembler(None),
    }
    Worker(db, vault, quiet, retry_base_seconds=0).run_until_idle()

    def _worker(*agents: Agent) -> Worker:
        return Worker(db, vault, quiet | {a.name: a for a in agents}, retry_base_seconds=0)

    return _worker


@dataclass
class Career:
    northwind: UUID
    director: UUID
    senior: UUID
    late: UUID  # under Director
    forecast: UUID  # under Director
    rollout: UUID  # under Senior Manager
    mentoring: UUID  # on Northwind itself, under no title
    brightline: UUID
    freight: UUID
    degree: UUID


def card(
    cards: CardRepository, kind: Any, headline: str, parent: UUID | None = None, **facts: Any
) -> UUID:
    content = MainContent(parent=parent, facts=facts, framing=Framing(headline=headline))
    return cards.create_card(kind, content, ME).id


def career(cards: CardRepository) -> Career:
    """Avery Quinn, made up: two titles at Northwind, one at Brightline, a degree."""
    nw = card(
        cards,
        "employment",
        "Northwind Logistics",
        employer="Northwind Logistics",
        location="Chicago, IL",
        start="2014-03",
        end="present",
    )
    director = card(
        cards, "position", "Director", nw, title="Director", start="2021-01", end="present"
    )
    senior = card(
        cards,
        "position",
        "Senior Manager",
        nw,
        title="Senior Manager",
        start="2017-06",
        end="2020-12",
    )
    bl = card(
        cards,
        "employment",
        "Brightline Partners",
        employer="Brightline Partners",
        start="2010-06",
        end="2014-02",
    )
    consultant = card(
        cards, "position", "Consultant", bl, title="Consultant", start="2010-06", end="2014-02"
    )
    return Career(
        northwind=nw,
        director=director,
        senior=senior,
        late=card(
            cards,
            "accomplishment",
            "Cut late shipments by 22%",
            director,
            figures=["22%"],
            date="2022-05",
        ),
        forecast=card(
            cards,
            "accomplishment",
            "Built the demand forecast, saving $3.1M",
            director,
            figures=["$3.1M"],
            date="2023-02",
        ),
        rollout=card(
            cards,
            "accomplishment",
            "Rolled out warehouse software to 6 sites",
            senior,
            figures=["6"],
            date="2019-04",
        ),
        mentoring=card(cards, "accomplishment", "Mentored new analysts", nw),
        brightline=bl,
        freight=card(
            cards,
            "accomplishment",
            "Mapped inbound freight for 120 suppliers",
            consultant,
            figures=["120"],
        ),
        degree=card(cards, "education", "B.S. Industrial Engineering", degree="B.S."),
    )


def whole(c: Career) -> ResumeContent:
    return ResumeContent(
        header=ResumeHeader(name="Avery Quinn", email="avery.quinn@example.com"),
        entries=[
            ResumeEntry(
                card=c.northwind,
                items=[ResumeItem(card=i) for i in (c.late, c.forecast, c.rollout, c.mentoring)],
            ),
            ResumeEntry(card=c.brightline, items=[ResumeItem(card=c.freight)]),
        ],
        context=[ResumeItem(card=c.degree)],
    )


def lines(content: ResumeContent) -> list[UUID]:
    return [i.card for e in content.entries for i in e.items] + [i.card for i in content.context]


# -- what the database guarantees ----------------------------------------------


def test_links_to_resumes_stay_with_their_owner(make_user, open_: Open, db: Database) -> None:
    alice, bob = make_user(), make_user()
    with open_(alice) as s:
        resume = s.resumes.create("Mine", ResumeContent(), ME)
        result = import_resume(promotions_text().encode(), "Avery Quinn.txt")
        kept = s.imports.create(promotions_text().encode(), "Avery Quinn.txt", result)
    with pytest.raises(errors.ForeignKeyViolation), db.as_user(bob) as conn:
        conn.execute(
            "insert into plytos.message (owner_id, author, body_ciphertext, resume_id)"
            " values (%s, 'person', '\\x00', %s)",
            (bob, resume.id),
        )
    with pytest.raises(errors.ForeignKeyViolation), db.as_user(bob) as conn:
        conn.execute(
            "insert into plytos.resume (owner_id, name_ciphertext, import_id)"
            " values (%s, '\\x00', %s)",
            (bob, kept.id),
        )
    with open_(bob) as s:
        assert s.resumes.summaries() == []
        with pytest.raises(ResumeNotFoundError):
            s.resumes.detail(resume.id)
    with pytest.raises(errors.ForeignKeyViolation), open_(bob) as s:
        s.agents.ask_for_resume("A version for fintech", resume.id)


def test_one_resume_as_written_per_file(make_user, open_: Open) -> None:
    user = make_user()
    with open_(user) as s:
        result = import_resume(promotions_text().encode(), "Avery Quinn.txt")
        kept = s.imports.create(promotions_text().encode(), "Avery Quinn.txt", result)
        s.resumes.create("My resume", ResumeContent(), ME, import_id=kept.id)
        assert s.resumes.imported() == {kept.id}
    with pytest.raises(errors.UniqueViolation), open_(user) as s:
        s.resumes.create("Again", ResumeContent(), ME, import_id=kept.id)


def test_a_kept_resume_proposal_records_the_version_it_made(make_user, open_: Open) -> None:
    user = make_user()
    with open_(user) as s:
        c = career(s.cards)
        parent = s.resumes.create("My resume", whole(c), ME)
        body = ProposalBody(
            message="Here's a version for fintech.",
            resume=NewResume(
                name="Fintech",
                target="Fintech operations roles",
                target_kind="industry",
                parent_id=parent.id,
                parent_version_id=parent.head.id,
                content=whole(c),
            ),
        )
        proposal = s.agents.propose("assembler", "resume", body)
        kept, resume = s.agents.keep_resume(proposal.id, s.cards, s.resumes)
        assert kept.state == "kept"
        assert kept.result_resume_version_id == resume.head.id
        assert kept.result_version_id is None
        with pytest.raises(ProposalConflictError):
            s.agents.keep_resume(proposal.id, s.cards, s.resumes)


# -- as written ----------------------------------------------------------------


def test_as_written_shows_the_kept_cards_in_the_files_order(make_user, open_: Open) -> None:
    user = make_user()
    data = promotions_text().encode()
    result = import_resume(data, "Avery Quinn.txt")
    with open_(user) as s:
        kept = s.imports.create(data, "Avery Quinn.txt", result)
        saved: dict[str, UUID] = {}
        for proposed in result.cards:
            if proposed.content.framing.headline.startswith("Automated"):
                s.imports.decide(kept.id, proposed.ref, "dropped")
                continue
            detail, _ = s.imports.approve(kept.id, proposed.ref, None, s.cards, ME)
            saved[proposed.ref] = detail.id
        view = s.imports.get(kept.id)
        content = as_written(view.result, view.progress, s.cards.main_contents())

    kinds = {p.ref: p.kind for p in result.cards}
    headlines = {p.ref: p.content.framing.headline for p in result.cards}
    employments = [saved[r] for r in saved if kinds[r] == "employment"]
    assert [e.card for e in content.entries] == employments
    shown = lines(content)
    for ref, card_id in saved.items():
        if kinds[ref] in ("accomplishment", "education"):
            assert card_id in shown, headlines[ref]
    assert all(not headlines[r].startswith("Automated") for r in saved)
    assert len(shown) == len(set(shown))
    # Each accomplishment sits under the employment it was filed under.
    for entry in content.entries:
        for item in entry.items:
            ref = next(r for r, cid in saved.items() if cid == item.card)
            position = next(p for p in result.cards if p.ref == ref).parent_ref
            employment = next(p for p in result.cards if p.ref == position).parent_ref
            assert assert_saved(saved, employment) == entry.card
    assert content.header.name == "Avery Quinn"
    assert content.header.email == "avery.quinn@example.com"
    assert content.header.phone == "312-555-0142"
    assert all(i.wording == "auto" for i in content.context)


def assert_saved(saved: dict[str, UUID], ref: str | None) -> UUID:
    assert ref is not None
    return saved[ref]


# -- versions ------------------------------------------------------------------


def test_every_change_is_a_version_that_can_come_back(make_user, open_: Open) -> None:
    user = make_user()
    with open_(user) as s:
        c = career(s.cards)
        first = s.resumes.create("My resume", whole(c), ME)
        shorter = whole(c)
        shorter.entries[0].items = shorter.entries[0].items[:2]
        second = s.resumes.save(first.id, shorter, first.head.id, ME)
        assert second.head.number == 2
        with pytest.raises(StaleResumeError) as stale:
            s.resumes.save(first.id, whole(c), first.head.id, ME)
        assert stale.value.current_head_id == second.head.id

        third = s.resumes.restore(first.id, 1, second.head.id, ME)
        assert third.head.number == 3
        assert lines(third.content) == lines(whole(c))
        assert third.head.note == "Back to version 1"
        assert [v.number for v in third.versions] == [1, 2, 3]

        named = s.resumes.name_version(first.id, 2, "Sent to Contoso")
        assert named.versions[1].names == ["Sent to Contoso"]
        assert s.resumes.verify(first.id) == []
        _, two = s.resumes.version(first.id, 2)
        assert lines(two) == lines(shorter)


def test_a_version_for_a_target_takes_the_changes_the_person_picks(make_user, open_: Open) -> None:
    user = make_user()
    with open_(user) as s:
        c = career(s.cards)
        mine = s.resumes.create("My resume", whole(c), ME)
        target = s.cards.create_target("industry", "Fintech", None)
        fintech = s.resumes.create(
            "Fintech",
            whole(c),
            ME,
            target_id=target.id,
            parent_id=mine.id,
            synced_parent_version_id=mine.head.id,
        )
        assert fintech.parent_name == "My resume"
        assert fintech.target_name == "Fintech"
        assert s.resumes.parent_changes(fintech.id) == []

        changed = whole(c)
        changed.entries[0].items = [i for i in changed.entries[0].items if i.card != c.rollout]
        changed.context = []
        changed.entries[0].fold_earlier = True
        mine = s.resumes.save(mine.id, changed, mine.head.id, ME)

        library = s.cards.main_contents()
        changes = s.resumes.parent_changes(fintech.id)
        labels = {ch.kind: describe(ch, library) for ch in changes}
        assert labels == {
            "item_removed": "Switched off “Rolled out warehouse software to 6 sites”",
            "context_removed": "Removed “B.S. Industrial Engineering”",
            "fold": "Folded earlier titles at Northwind Logistics into one line",
        }
        assert s.resumes.detail(fintech.id).parent_changes == 3

        take = [ch.key for ch in changes if ch.kind == "item_removed"]
        taken = s.resumes.take(fintech.id, take, fintech.head.id, ME)
        assert c.rollout not in lines(taken.content)
        assert c.degree in lines(taken.content)  # Not taken, so it stays.
        assert not taken.content.entries[0].fold_earlier
        assert taken.head.synced_parent_version_id == mine.head.id
        assert taken.parent_changes == 0
        assert taken.head.note == "Took 1 change from the resume it was made from"


# -- how a page reads ----------------------------------------------------------


def test_a_page_shows_titles_latest_first_and_what_is_left_out(make_user, open_: Open) -> None:
    user = make_user()
    with open_(user) as s:
        c = career(s.cards)
        content = whole(c)
        content.entries[0].items = [ResumeItem(card=c.forecast), ResumeItem(card=c.mentoring)]
        content.entries.pop()
        page = render(content, s.cards)

        [northwind] = page.entries
        assert northwind.employer == "Northwind Logistics"
        assert northwind.dates == "Mar 2014 – Present"
        assert [r.title for r in northwind.roles] == ["", "Director", "Senior Manager"]
        assert [i.text for i in northwind.roles[0].items] == ["Mentored new analysts"]
        assert [i.text for i in northwind.roles[1].items] == [
            "Built the demand forecast, saving $3.1M"
        ]
        assert northwind.roles[2].items == []
        assert sorted(h.text for h in northwind.hidden) == [
            "Cut late shipments by 22%",
            "Rolled out warehouse software to 6 sites",
        ]
        assert [e.employer for e in page.left_out] == ["Brightline Partners"]
        assert [(sec.label, [i.text for i in sec.items]) for sec in page.sections] == [
            ("Education", ["B.S. Industrial Engineering"])
        ]

        content.entries[0].fold_earlier = True
        content.entries[0].items.append(ResumeItem(card=c.rollout))
        folded = render(content, s.cards).entries[0]
        assert [r.title for r in folded.roles] == ["", "Director"]
        assert folded.earlier_titles == ["Senior Manager (Jun 2017 – Dec 2020)"]
        assert "Rolled out warehouse software to 6 sites" in [i.text for i in folded.roles[1].items]


def test_each_line_shows_the_wording_the_resume_asks_for(make_user, open_: Open) -> None:
    user = make_user()
    with open_(user) as s:
        c = career(s.cards)
        target = s.cards.create_target("industry", "Fintech", None)
        s.cards.create_variant(
            c.late,
            target.id,
            VariantContent(framing=Framing(headline="Cut late payments-style delays by 22%")),
            ME,
        )
        content = ResumeContent(
            entries=[
                ResumeEntry(
                    card=c.northwind,
                    items=[
                        ResumeItem(card=c.late),
                        ResumeItem(card=c.forecast),
                    ],
                )
            ]
        )

        def shown(target_id: UUID | None, **kw: Any) -> list[tuple[str, str]]:
            page = render(content, s.cards, target_id, **kw)
            return [(i.text, i.wording) for r in page.entries[0].roles for i in r.items]

        assert shown(None) == [
            ("Cut late shipments by 22%", "main"),
            ("Built the demand forecast, saving $3.1M", "main"),
        ]
        assert ("Cut late payments-style delays by 22%", "target") in shown(target.id)
        content.entries[0].items[0].wording = "main"
        assert ("Cut late shipments by 22%", "main") in shown(target.id)
        proposed = {c.forecast: Framing(headline="Saved $3.1M with a demand forecast")}
        assert ("Saved $3.1M with a demand forecast", "target") in shown(None, proposed=proposed)


# -- the Assembler -------------------------------------------------------------


def assemble(data: dict[str, Any]) -> AssemblerAnswer:
    """Picks the latest employment with its first accomplishment, sneaks in an
    accomplishment from the other employment and a ref that doesn't exist, and
    rewords two lines, one with a number the card doesn't have."""
    first, second = data["employments"][0], data["employments"][1]
    mine = first["accomplishments"]
    return AssemblerAnswer(
        understood=True,
        question="",
        target="Operations roles at fintech companies",
        target_kind="industry",
        name="Fintech operations",
        entries=[
            PickedEntry(
                employment=first["ref"],
                fold_earlier=True,
                accomplishments=[
                    mine[0]["ref"],
                    second["accomplishments"][0]["ref"],
                    "A99",
                    mine[1]["ref"],
                ],
            )
        ],
        context=[o["ref"] for o in data["other_cards"]],
        rewordings=[
            Reword(ref=mine[0]["ref"], headline="Saved $3.1M by forecasting demand network-wide"),
            Reword(ref=mine[1]["ref"], headline="Cut late shipments by 35%"),
        ],
        message="I led with the forecast and left out Brightline.",
    )


def test_the_assembler_proposes_a_version_from_what_is_on_file(
    make_user, open_: Open, worker: MakeWorker
) -> None:
    user = make_user()
    with open_(user) as s:
        c = career(s.cards)
        mine = s.resumes.create("My resume", whole(c), ME)
        asked = s.agents.ask_for_resume("Make a version for fintech ops roles", mine.id)
        assert asked.resume_id == mine.id
    thinker = FakeThinker(AssemblerAnswer=assemble)
    worker(Assembler(thinker)).run_until_idle()

    [(_, prompt)] = thinker.asked
    assert prompt["request"] == "Make a version for fintech ops roles"
    assert prompt["employments"][0]["employer"] == "Northwind Logistics"
    assert [a["headline"] for a in prompt["employments"][0]["accomplishments"]][:2] == [
        "Built the demand forecast, saving $3.1M",
        "Cut late shipments by 22%",
    ]
    assert str(c.late) not in str(prompt)  # Refs, never ids.

    with open_(user) as s:
        [proposal] = s.agents.proposals("open", agent="assembler")
        assert proposal.kind == "resume"
        new = proposal.body.resume
        assert new is not None
        assert new.parent_id == mine.id and new.parent_version_id == mine.head.id
        assert new.target == "Operations roles at fintech companies"
        [entry] = new.content.entries
        assert entry.card == c.northwind and entry.fold_earlier
        # The Brightline line and the made-up ref are dropped.
        assert [i.card for i in entry.items] == [c.forecast, c.late]
        assert [i.card for i in new.content.context] == [c.degree]
        assert new.content.header.name == "Avery Quinn"
        # The rewording with a number the card doesn't have is dropped.
        assert [(r.card, r.framing.headline) for r in new.rewordings] == [
            (c.forecast, "Saved $3.1M by forecasting demand network-wide")
        ]
        offered = s.agents.conversation()[-1]
        assert offered.proposal is not None and offered.proposal.id == proposal.id
        assert offered.text == "I led with the forecast and left out Brightline."

        kept, resume = s.agents.keep_resume(proposal.id, s.cards, s.resumes)
        assert kept.state == "kept"
        assert resume.parent_id == mine.id
        assert resume.target_name == "Operations roles at fintech companies"
        assert (resume.head.author_kind, resume.head.author_ref) == ("ai", "assembler")
        page = render(resume.content, s.cards, resume.target_id)
        shown = [(i.text, i.wording) for r in page.entries[0].roles for i in r.items]
        assert ("Saved $3.1M by forecasting demand network-wide", "target") in shown
        variant = s.cards.card_detail(c.forecast).variants[0]
        assert variant.head.author_kind == "ai"


def test_keeping_after_changes_is_the_persons_and_skips_unwanted_wording(
    make_user, open_: Open, worker: MakeWorker
) -> None:
    user = make_user()
    with open_(user) as s:
        c = career(s.cards)
        mine = s.resumes.create("My resume", whole(c), ME)
        s.agents.ask_for_resume("A version for fintech", mine.id)
    worker(Assembler(FakeThinker(AssemblerAnswer=assemble))).run_until_idle()
    with open_(user) as s:
        [proposal] = s.agents.proposals("open", agent="assembler")
        assert proposal.body.resume is not None
        edited = proposal.body.resume.content.model_copy(deep=True)
        edited.context = []
        kept, resume = s.agents.keep_resume(proposal.id, s.cards, s.resumes, edited, [])
        assert kept.state == "edited"
        assert resume.head.author_kind == "person"
        assert resume.content.context == []
        assert s.cards.card_detail(c.forecast).variants == []


def test_the_assembler_says_so_when_it_cannot_help(
    make_user, open_: Open, worker: MakeWorker
) -> None:
    nobody, offline, unclear = make_user(), make_user(), make_user()
    with open_(nobody) as s:
        s.agents.enqueue("assembler", "message", s.agents.say("A version for fintech").id)
    for user in (offline, unclear):
        with open_(user) as s:
            c = career(s.cards)
            mine = s.resumes.create("My resume", whole(c), ME)
            s.agents.ask_for_resume("Make me another one", mine.id)

    worker(Assembler(None)).run_until_idle()
    for user, said in ((nobody, NO_RESUME), (offline, AI_OFF)):
        with open_(user) as s:
            assert said in [m.text for m in s.agents.conversation()]
            assert s.agents.proposals(None) == []

    def ask_back(_: dict[str, Any]) -> AssemblerAnswer:
        return AssemblerAnswer(
            understood=False,
            question="Who is this version for?",
            target="",
            target_kind="custom",
            name="",
            entries=[],
            context=[],
            rewordings=[],
            message="",
        )

    with open_(unclear) as s:
        mine_id = s.resumes.summaries()[0].id
        s.agents.ask_for_resume("Make me another one", mine_id)
    worker(Assembler(FakeThinker(AssemblerAnswer=ask_back))).run_until_idle()
    with open_(unclear) as s:
        assert s.agents.conversation()[-1].text == "Who is this version for?"
        assert s.agents.proposals("open", agent="assembler") == []


def test_the_listener_hands_a_resume_request_to_the_assembler(
    make_user, open_: Open, worker: MakeWorker
) -> None:
    user = make_user()
    with open_(user) as s:
        c = career(s.cards)
        s.resumes.create("My resume", whole(c), ME)
        s.agents.say("Can you make a version of my resume for fintech ops roles?")

    def route(_: dict[str, Any]) -> ListenerAnswer:
        return ListenerAnswer(
            about_work=False,
            job="",
            summary="",
            projects=[],
            figures=[],
            has_outcome=False,
            reply="I'll put that together.",
            resume_for="fintech ops roles",
        )

    worker(
        Listener(FakeThinker(ListenerAnswer=route), 0),
        Assembler(FakeThinker(AssemblerAnswer=assemble)),
    ).run_until_idle()
    with open_(user) as s:
        assert s.agents.tidbits() == []
        said = [m.text for m in s.agents.conversation()]
        assert said[1] == "I'll put that together."
        [proposal] = s.agents.proposals("open", agent="assembler")
        assert proposal.body.resume is not None
        assert said[2] == proposal.body.message
