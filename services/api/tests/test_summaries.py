"""The Summarizer: a job's headline and each title's story, summed up from the
accomplishments in Plytos's own words, and who wrote what.

Everyone here is made up and built in code. The model is a fake that answers
from the prompt it's given, so nothing calls Claude.
"""

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from plytos_api.agents.store import AgentStore
from plytos_api.agents.summarizer import (
    Summarizer,
    SummaryAnswer,
    SummaryUnavailableError,
    TitleStory,
    needs_first_summary,
    summarize,
)
from plytos_api.agents.thinking import Usage
from plytos_api.cards.model import Framing, MainContent
from plytos_api.cards.repository import Author, CardRepository
from plytos_api.cards.rules import honest_marks
from plytos_api.config import Settings
from plytos_api.db import Database
from plytos_api.imports.matching import merged, unchanged
from plytos_api.keys import Vault

from .conftest import DbUrls
from .test_agents import FakeThinker, MakeWorker, worker  # noqa: F401

ME = Author("person")
PLYTOS = Author("ai", "summarizer")

Cards = Callable[..., AbstractContextManager[tuple[CardRepository, AgentStore]]]


@pytest.fixture
def cards(db: Database, vault: Vault) -> Cards:
    @contextmanager
    def _cards(
        user_id: UUID, hook: Callable[[UUID], None] | None = None
    ) -> Iterator[tuple[CardRepository, AgentStore]]:
        with db.as_user(user_id) as conn:
            cipher = vault.cipher_for(conn, user_id)
            yield (
                CardRepository(conn, user_id, cipher, on_job_changed=hook),
                AgentStore(conn, user_id, cipher),
            )

    return _cards


def content(headline: str, body: str = "", **facts: Any) -> MainContent:
    return MainContent(facts=facts, framing=Framing(headline=headline, body=body))


def under(parent: UUID, c: MainContent) -> MainContent:
    return c.model_copy(update={"parent": parent})


class Job:
    """Dana Okafor's eight years at Fernwood Freight: two titles and their wins."""

    def __init__(self, cards: CardRepository) -> None:
        self.job = cards.create_card(
            "employment",
            content(
                "Fernwood Freight", employer="Fernwood Freight", start="2016-02", end="present"
            ),
            ME,
        ).id
        self.lead = cards.create_card(
            "position",
            under(self.job, content("Planning Lead", title="Planning Lead", start="2020-05")),
            ME,
        ).id
        self.analyst = cards.create_card(
            "position",
            under(
                self.job,
                content(
                    "Planning Analyst", title="Planning Analyst", start="2016-02", end="2020-04"
                ),
            ),
            ME,
        ).id
        self.win = cards.create_card(
            "accomplishment",
            under(
                self.lead,
                content(
                    "Cut empty miles by 18% by pooling loads across 4 depots",
                    figures=["18%", "4"],
                ),
            ),
            ME,
        ).id
        cards.create_card(
            "accomplishment",
            under(self.analyst, content("Built the weekly lane forecast the depots plan from")),
            ME,
        )


def answer(headline: str, **stories: str) -> Callable[[dict[str, Any]], SummaryAnswer]:
    """Answers with the headline, and a story for each title named by its
    title fact, for whichever titles the prompt asks stories for."""

    def respond(data: dict[str, Any]) -> SummaryAnswer:
        out = []
        for t in data["titles"]:
            if t["write_story"] and t["title"] in stories:
                out.append(TitleStory(ref=t["ref"], story=stories[t["title"]]))
        return SummaryAnswer(headline=headline if data["write_headline"] else "", stories=out)

    return respond


STORIES = {
    "Planning Lead": "Led planning for the depots, pooling loads to cut empty miles by 18%.",
    "Planning Analyst": "Built the lane forecast the depots still plan from each week.",
}
HEADLINE = "Grew from analyst to planning lead, cutting empty miles by 18%"


def main(cards: CardRepository, card_id: UUID) -> MainContent:
    c = cards.card_detail(card_id).main.content
    assert isinstance(c, MainContent)
    return c


# -- who wrote what --------------------------------------------------------------


def test_a_persons_edit_makes_the_part_it_touches_their_own() -> None:
    before = MainContent(
        framing=Framing(
            headline="Led the move", body="Plytos's story", plytos_wrote=["headline", "body"]
        )
    )
    edited = before.model_copy(
        update={"framing": before.framing.model_copy(update={"body": "My own story"})}
    )
    after = honest_marks(before, edited, by_summarizer=False)
    assert after.framing.plytos_wrote == ["headline"]
    # Nobody but the Summarizer marks text as Plytos's, even text it didn't change.
    claimed = MainContent(framing=Framing(headline="Mine", plytos_wrote=["headline", "body"]))
    assert honest_marks(None, claimed, by_summarizer=False).framing.plytos_wrote == []
    assert honest_marks(None, claimed, by_summarizer=True).framing.plytos_wrote == [
        "headline",
        "body",
    ]


def test_the_repository_keeps_the_marks_honest(make_user, cards: Cards) -> None:
    with cards(make_user()) as (repo, _):
        made = repo.create_card(
            "accomplishment",
            MainContent(framing=Framing(headline="Mine", plytos_wrote=["headline"])),
            ME,
        )
        assert main(repo, made.id).framing.plytos_wrote == []
        job = Job(repo)
        written = summarize(
            repo, FakeThinker(SummaryAnswer=answer(HEADLINE, **STORIES)), job.job, Usage()
        )
        assert written.headline and written.stories == 2
        head = repo.card_detail(job.job).main
        assert head.head.author_kind == "ai"
        # Saving the job's dates leaves Plytos's headline marked as its own.
        dated = head.content.model_copy(update={"facts": {**head.content.facts, "end": "2025-06"}})
        repo.save_main_version(job.job, head.head.id, dated, ME)
        assert main(repo, job.job).framing.plytos_wrote == ["headline"]


# -- writing ------------------------------------------------------------------------


def test_plytos_sums_up_the_job_and_each_title(make_user, cards: Cards) -> None:
    user = make_user()
    with cards(user) as (repo, _):
        job = Job(repo)
    with cards(user) as (repo, _):
        thinker = FakeThinker(SummaryAnswer=answer(HEADLINE, **STORIES))
        usage = Usage()
        written = summarize(repo, thinker, job.job, usage)
        assert (written.headline, written.stories, written.dropped) == (True, 2, 0)
        employment = main(repo, job.job)
        assert employment.framing.headline == HEADLINE
        assert employment.framing.plytos_wrote == ["headline"]
        assert employment.facts["employer"] == "Fernwood Freight"
        lead = main(repo, job.lead)
        assert lead.framing.body == STORIES["Planning Lead"]
        assert lead.framing.plytos_wrote == ["body"]
        assert lead.framing.headline == "Planning Lead"
        assert usage.input_tokens > 0
        [(_, asked)] = thinker.asked
        assert asked["employer"] == "Fernwood Freight"
        assert [t["title"] for t in asked["titles"]] == ["Planning Lead", "Planning Analyst"]
        assert asked["titles"][0]["accomplishments"][0]["figures"] == "18%, 4"

    with cards(user) as (repo, _):
        # Nothing changed since: nothing to write, and no call to the model.
        assert summarize(repo, thinker, job.job, Usage()).headline is False
        assert len(thinker.asked) == 1


def test_a_number_the_cards_dont_have_is_never_written(make_user, cards: Cards) -> None:
    with cards(make_user()) as (repo, _):
        job = Job(repo)
        invented = answer(
            "Cut empty miles by 25% across the network",
            **{
                "Planning Lead": "Led a team of 12 planners.",
                "Planning Analyst": STORIES["Planning Analyst"],
            },
        )
        written = summarize(repo, FakeThinker(SummaryAnswer=invented), job.job, Usage())
        assert (written.headline, written.stories, written.dropped) == (False, 1, 2)
        assert main(repo, job.job).framing.headline == "Fernwood Freight"
        assert main(repo, job.lead).framing.body == ""
        assert main(repo, job.analyst).framing.body == STORIES["Planning Analyst"]


def test_the_persons_own_words_stay_unless_they_ask(make_user, cards: Cards) -> None:
    with cards(make_user()) as (repo, _):
        job = Job(repo)
        lead = repo.card_detail(job.lead).main
        mine = lead.content.model_copy(
            update={"framing": lead.content.framing.model_copy(update={"body": "My own words."})}
        )
        repo.save_main_version(job.lead, lead.head.id, mine, ME)
        thinker = FakeThinker(SummaryAnswer=answer(HEADLINE, **STORIES))

        summarize(repo, thinker, job.job, Usage(), force=True)
        assert main(repo, job.lead).framing.body == "My own words."
        assert [t["write_story"] for t in thinker.asked[-1][1]["titles"]] == [False, True]

        summarize(repo, thinker, job.job, Usage(), force=True, replace_own=True)
        assert main(repo, job.lead).framing.body == STORIES["Planning Lead"]
        assert main(repo, job.lead).framing.plytos_wrote == ["body"]
        # Their words stay in the history.
        assert len(repo.history(job.lead, None)) == 3


def test_a_changed_accomplishment_rewrites_only_what_plytos_wrote(make_user, cards: Cards) -> None:
    user = make_user()
    with cards(user) as (repo, _):
        job = Job(repo)
    with cards(user) as (repo, _):
        summarize(repo, FakeThinker(SummaryAnswer=answer(HEADLINE, **STORIES)), job.job, Usage())
    with cards(user) as (repo, _):
        analyst = repo.card_detail(job.analyst).main
        mine = analyst.content.model_copy(
            update={"framing": analyst.content.framing.model_copy(update={"body": "Mine."})}
        )
        repo.save_main_version(job.analyst, analyst.head.id, mine, ME)
        win = repo.card_detail(job.win).main
        better = win.content.model_copy(
            update={
                "framing": win.content.framing.model_copy(
                    update={"headline": "Cut empty miles by 18% by pooling loads across 6 depots"}
                ),
                "facts": {"figures": ["18%", "6"]},
            }
        )
        repo.save_main_version(job.win, win.head.id, better, ME)
    with cards(user) as (repo, _):
        newer = {"Planning Lead": "Pooled loads across 6 depots, cutting empty miles by 18%."}
        thinker = FakeThinker(
            SummaryAnswer=answer("Planning lead who cut empty miles by 18%", **newer)
        )
        written = summarize(repo, thinker, job.job, Usage())
        assert (written.headline, written.stories) == (True, 1)
        asked = thinker.asked[0][1]
        assert [t["write_story"] for t in asked["titles"]] == [True, False]
        assert main(repo, job.lead).framing.body == newer["Planning Lead"]
        assert main(repo, job.analyst).framing.body == "Mine."


def test_a_job_whose_headline_was_its_name_keeps_the_name(make_user, cards: Cards) -> None:
    with cards(make_user()) as (repo, _):
        old = repo.create_card("employment", content("Juniper Mills"), ME).id
        title = repo.create_card("position", under(old, content("Buyer", title="Buyer")), ME).id
        repo.create_card(
            "accomplishment", under(title, content("Moved 3 suppliers onto one contract")), ME
        )
        thinker = FakeThinker(
            SummaryAnswer=lambda _: SummaryAnswer(
                headline="Brought 3 suppliers onto one contract", stories=[]
            )
        )
        assert summarize(repo, thinker, old, Usage()).headline
        written = main(repo, old)
        assert written.facts["employer"] == "Juniper Mills"
        assert written.framing.headline == "Brought 3 suppliers onto one contract"


def test_no_answer_leaves_everything_as_it_was(make_user, cards: Cards) -> None:
    with cards(make_user()) as (repo, _):
        job = Job(repo)
        with pytest.raises(SummaryUnavailableError):
            summarize(repo, FakeThinker(), job.job, Usage())
        assert main(repo, job.job).framing.headline == "Fernwood Freight"


def test_jobs_with_nothing_summed_up_yet(make_user, cards: Cards) -> None:
    with cards(make_user()) as (repo, _):
        job = Job(repo)
        empty = repo.create_card("employment", content("Birch & Co", employer="Birch & Co"), ME).id
        library = repo.library()
        assert needs_first_summary(library) == [job.job]
        assert empty not in needs_first_summary(library)
        summarize(repo, FakeThinker(SummaryAnswer=answer(HEADLINE, **STORIES)), job.job, Usage())
        assert needs_first_summary(repo.library()) == []


# -- from the queue ------------------------------------------------------------------


def test_changing_an_accomplishment_queues_one_summary_for_its_job(
    make_user,
    cards: Cards,
    worker: MakeWorker,  # noqa: F811
) -> None:
    me = make_user()
    with cards(me) as (repo, store):

        def sum_up(employment_id: UUID) -> None:
            store.enqueue(
                "summarizer", "card", employment_id, dedupe_key=f"summarize-{employment_id}"
            )

        hooked = CardRepository(repo._conn, me, repo._cipher, on_job_changed=sum_up)
        job = Job(hooked)
        # A burst of changes to one job queues one run for it.
        assert store.runs_about("summarizer", waiting=True) == {job.job}
        assert len([r for r in store.runs() if r.agent == "summarizer"]) == 1

    thinker = FakeThinker(SummaryAnswer=answer(HEADLINE, **STORIES))
    worker(Summarizer(thinker)).run_until_idle()
    with cards(me) as (repo, store):
        assert main(repo, job.job).framing.headline == HEADLINE
        assert store.runs_about("summarizer", waiting=True) == set()
        [run] = [r for r in store.runs() if r.agent == "summarizer"]
        assert (run.state, run.model) == ("done", "fake")

        # Plytos's own saves don't queue another run.
        hooked = CardRepository(
            repo._conn, me, repo._cipher, on_job_changed=lambda _: pytest.fail()
        )
        summarize(hooked, thinker, job.job, Usage(), force=True)


# -- re-imports ------------------------------------------------------------------------


def test_a_reimport_keeps_the_headline_and_stories_it_has_no_words_for() -> None:
    existing = MainContent(
        facts={"employer": "Fernwood Freight", "start": "2016-02"},
        framing=Framing(headline=HEADLINE, plytos_wrote=["headline"]),
    )
    imported = content("Fernwood Freight", employer="Fernwood Freight", start="2016-02")
    after = merged(existing, imported)
    assert after.framing.headline == HEADLINE
    assert after.framing.plytos_wrote == ["headline"]
    assert unchanged(existing, imported)

    story = MainContent(
        facts={"title": "Planning Lead"},
        framing=Framing(headline="Planning Lead", body="Plytos's story.", plytos_wrote=["body"]),
    )
    assert merged(story, content("Planning Lead", title="Planning Lead")).framing.body == (
        "Plytos's story."
    )
    worded = merged(story, content("Planning Lead", "From the resume.", title="Planning Lead"))
    assert (worded.framing.body, worded.framing.plytos_wrote) == ("From the resume.", [])


# -- the API -----------------------------------------------------------------------------


def me(name: str) -> dict[str, str]:
    return {"X-Plytos-Dev-User": name}


def make_job(client: TestClient, who: dict[str, str]) -> dict[str, str]:
    def card(kind: str, body: dict[str, Any]) -> str:
        made = client.post("/v1/cards", json={"kind": kind, "content": body}, headers=who)
        assert made.status_code == 201, made.text
        return str(made.json()["id"])

    job = card(
        "employment",
        {"facts": {"employer": "Fernwood Freight"}, "framing": {"headline": "Fernwood Freight"}},
    )
    lead = card(
        "position",
        {
            "parent": job,
            "facts": {"title": "Planning Lead"},
            "framing": {"headline": "Planning Lead"},
        },
    )
    card(
        "accomplishment",
        {"parent": lead, "facts": {}, "framing": {"headline": "Cut empty miles by 18%"}},
    )
    return {"job": job, "lead": lead}


def test_asking_for_a_rewrite_with_ai_off_says_so(test_db: DbUrls, kek_setting: str) -> None:
    settings = Settings(
        env="test", database_url=test_db.app_url, kek=kek_setting, imports_inline=False
    )
    from plytos_api.main import create_app

    with TestClient(create_app(settings)) as client:
        who = me("summary-off")
        ids = make_job(client, who)
        refused = client.post(f"/v1/cards/{ids['job']}/summaries", json={}, headers=who)
        assert refused.status_code == 503
        cards = client.get("/v1/library", headers=who).json()
        assert not any(c["writing"] for c in cards)


def test_the_card_asks_plytos_to_rewrite(
    test_db: DbUrls, kek_setting: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    thinker = FakeThinker(
        SummaryAnswer=answer(
            "Planning lead who cut empty miles by 18%",
            **{"Planning Lead": "Pooled loads to cut empty miles by 18%."},
        )
    )
    monkeypatch.setattr("plytos_api.main.thinker_for", lambda *_: thinker)
    settings = Settings(
        env="test", database_url=test_db.app_url, kek=kek_setting, imports_inline=False
    )
    from plytos_api.main import create_app

    with TestClient(create_app(settings)) as client:
        who = me("summary-on")
        ids = make_job(client, who)
        library = {c["id"]: c for c in client.get("/v1/library", headers=who).json()}
        # Accomplishments changed, so a summary is on its way.
        assert library[ids["job"]]["writing"] is True
        assert library[ids["lead"]]["writing"] is False

        done = client.post(f"/v1/cards/{ids['job']}/summaries", json={}, headers=who)
        assert done.status_code == 200, done.text
        assert done.json() == {"headline": True, "stories": 1, "dropped": 0}
        library = {c["id"]: c for c in client.get("/v1/library", headers=who).json()}
        job = library[ids["job"]]
        assert job["content"]["framing"]["headline"] == "Planning lead who cut empty miles by 18%"
        assert job["content"]["framing"]["plytos_wrote"] == ["headline"]
        assert job["version_author"] == "ai"
        lead = library[ids["lead"]]["content"]["framing"]
        assert (lead["body"], lead["plytos_wrote"]) == (
            "Pooled loads to cut empty miles by 18%.",
            ["body"],
        )

        # Only a job has a headline to write.
        assert (
            client.post(f"/v1/cards/{ids['lead']}/summaries", json={}, headers=who).status_code
            == 422
        )
        # Someone else's job isn't there for them.
        other = client.post(
            f"/v1/cards/{ids['job']}/summaries", json={}, headers=me("summary-other")
        )
        assert other.status_code == 404
