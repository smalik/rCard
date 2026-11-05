"""Bringing a resume in again: proposed cards carry on as the person's own cards.

Made-up resumes only (resume_samples.py). The rules read them, so nothing
calls a model.
"""

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from uuid import UUID

import pytest

from plytos_api.cards.model import Framing, MainContent
from plytos_api.cards.repository import Author, CardRepository, CardText
from plytos_api.db import Database
from plytos_api.imports.matching import name_key, overlaps
from plytos_api.imports.model import ImportResult
from plytos_api.imports.pipeline import import_resume
from plytos_api.imports.store import ImportConflictError, ImportStore, KeepCard, MatchChoice
from plytos_api.keys import Vault

from .resume_samples import title_first_text

ME = Author("person")


@dataclass
class Stores:
    imports: ImportStore
    cards: CardRepository


Open = Callable[[UUID], AbstractContextManager[Stores]]


@pytest.fixture
def open_(db: Database, vault: Vault) -> Open:
    @contextmanager
    def _open(user_id: UUID) -> Iterator[Stores]:
        with db.as_user(user_id) as conn:
            cipher = vault.cipher_for(conn, user_id)
            yield Stores(ImportStore(conn, user_id, cipher), CardRepository(conn, user_id, cipher))

    return _open


def updated_text() -> str:
    """The same resume a year on: a tenure that ran longer, and one result reworded."""
    return (
        title_first_text()
        .replace("Jun 2005 – Jan 2007", "Jun 2005 – Mar 2007")
        .replace("Cut load time by 40%.", "Cut nightly load time by 45%.")
    )


def bring_in(s: Stores, text: str) -> tuple[UUID, ImportResult]:
    result = import_resume(text.encode(), "Robin Diaz.txt")
    return s.imports.create(text.encode(), "Robin Diaz.txt", result).id, result


def approve_all(
    s: Stores, import_id: UUID, result: ImportResult, **choices: MatchChoice
) -> dict[str, UUID]:
    """Approves every proposed card, parents first. A choice for card-2 is card_2=."""
    saved = {}
    for proposed in result.cards:
        choice = choices.get(proposed.ref.replace("-", "_"))
        card, _ = s.imports.approve(import_id, proposed.ref, None, s.cards, ME, choice)
        saved[proposed.ref] = card.id
    return saved


def versions(s: Stores, card_id: UUID) -> int:
    return s.cards.card_detail(card_id).main.head.number


def test_names_are_compared_loosely() -> None:
    assert name_key("Acme Health, Inc.") == name_key("acme health") == "acme health"
    assert name_key("The Contoso Group LLC") == "contoso group"
    assert name_key("Sr. Analyst") == name_key("Senior Analyst")
    assert name_key("R&D Lead") == name_key("R and D lead")
    # A suffix on its own is a name.
    assert name_key("Co.") == "co"
    # Accents fold; letters in any script are kept.
    assert name_key("Nestlé") == name_key("Nestle")
    assert name_key("Müller GmbH") == "muller" != name_key("Møller")
    assert name_key("北京 Inc.") == "北京" != name_key("上海 Inc.")


def test_dates_must_overlap_when_both_sides_have_them() -> None:
    def card(**facts: object) -> MainContent:
        return MainContent(facts=facts, framing=Framing(headline="x"))  # type: ignore[arg-type]

    assert overlaps(card(start="2019-01", end="present"), card(start="2021", end="2022"))
    assert overlaps(card(start="2002", end="2005"), card(start="2005-06", end="2007-01"))
    assert not overlaps(card(start="2002", end="2004"), card(start="2010", end="present"))
    assert overlaps(card(), card(start="2010", end="present"))
    # To the month where both give one: two stints in one year stay apart.
    assert not overlaps(card(start="2024-01", end="2024-03"), card(start="2024-09", end="2024-12"))
    assert overlaps(card(start="2024", end="2024"), card(start="2024-09", end="2024-12"))
    assert overlaps(card(start="2024-03"), card(start="2024"))
    assert not overlaps(card(start="2024-03"), card(start="2024-05"))


def test_the_same_resume_again_adds_nothing(make_user, open_: Open) -> None:
    user = make_user()
    with open_(user) as s:
        first_id, first = bring_in(s, title_first_text())
        kept = approve_all(s, first_id, first)
        count = len(s.cards.list_cards())

        again_id, again = bring_in(s, title_first_text())
        matches = s.imports.matches(again_id, s.cards)
        # Every proposal stands for the card made from the first upload, as it is.
        assert {ref: m.card_id for ref, m in matches.items()} == kept
        assert all(m.same for m in matches.values())

        linked = approve_all(s, again_id, again)
        assert linked == kept
        assert len(s.cards.list_cards()) == count
        assert {versions(s, card_id) for card_id in kept.values()} == {1}


def test_an_updated_resume_adds_versions_and_only_new_lines_become_cards(
    make_user, open_: Open
) -> None:
    user = make_user()
    with open_(user) as s:
        first_id, first = bring_in(s, title_first_text())
        kept = approve_all(s, first_id, first)

        again_id, again = bring_in(s, updated_text())
        matches = s.imports.matches(again_id, s.cards)
        # card-4 is the reworded result: it's new, and sits under the same title.
        assert set(matches) == set(kept) - {"card-4"}
        changed = {ref for ref, m in matches.items() if not m.same}
        assert changed == {"card-1", "card-2"}  # the employment and the title, whose end moved

        saved = approve_all(s, again_id, again)
        for ref in matches:
            assert saved[ref] == kept[ref]
        assert saved["card-4"] not in kept.values()
        assert s.cards.card_detail(saved["card-4"]).parent_id == kept["card-2"]
        # The longer tenure is the next version of the person's cards; the rest stay as they were.
        assert versions(s, kept["card-1"]) == 2 and versions(s, kept["card-2"]) == 2
        head = s.cards.card_detail(kept["card-2"]).main.content
        assert isinstance(head, MainContent) and head.facts["end"] == "2007-03"
        assert versions(s, kept["card-3"]) == 1


def test_the_person_can_keep_their_card_or_make_a_separate_one(make_user, open_: Open) -> None:
    user = make_user()
    with open_(user) as s:
        first_id, first = bring_in(s, title_first_text())
        kept = approve_all(s, first_id, first)
        # They reworded their own title card since.
        detail = s.cards.card_detail(kept["card-2"])
        mine = detail.main.content
        assert isinstance(mine, MainContent)
        reworded = mine.model_copy(
            update={"framing": Framing(headline="ETL Developer, nightly loads")}
        )
        s.cards.save_main_version(kept["card-2"], detail.main.head.id, reworded, ME)

        again_id, again = bring_in(s, updated_text())
        # Their wording stays: the title is linked, not saved over.
        approve_all(s, again_id, again, card_2="keep")
        assert versions(s, kept["card-2"]) == 2
        assert s.cards.card_detail(kept["card-2"]).main.content == reworded

        third_id, third = bring_in(s, updated_text())
        # A separate card: its titles and results then match nothing of theirs.
        separate = approve_all(s, third_id, third, card_1="separate")
        assert separate["card-1"] != kept["card-1"]
        assert separate["card-2"] not in kept.values()
        assert s.cards.card_detail(separate["card-2"]).parent_id == separate["card-1"]


def test_a_second_stint_at_the_same_employer_stays_its_own_card(make_user, open_: Open) -> None:
    user = make_user()
    with open_(user) as s:
        first_id, first = bring_in(s, title_first_text())
        approve_all(s, first_id, first)
        later = title_first_text().replace("Jun 2005 – Jan 2007", "Jun 2015 – Present")
        later = later.replace("2002 – 2005", "2012 – 2015")
        again_id, _ = bring_in(s, later)
        assert s.imports.matches(again_id, s.cards).keys() == {"card-7"}  # only the degree


def test_a_choice_that_no_longer_fits_is_refused(make_user, open_: Open) -> None:
    user = make_user()
    with open_(user) as s:
        import_id, result = bring_in(s, title_first_text())
        with pytest.raises(ImportConflictError, match="doesn't match one of yours"):
            s.imports.approve(import_id, "card-1", None, s.cards, ME, "update")
        # As a new card, it goes through.
        card, _ = s.imports.approve(import_id, "card-1", None, s.cards, ME, "separate")
        assert result.cards[0].content.framing.headline == "Contoso Bank"
        assert s.cards.card_detail(card.id).kind == "employment"


def test_a_card_left_out_leaves_the_persons_card_to_the_next(make_user, open_: Open) -> None:
    user = make_user()
    with open_(user) as s:
        first_id, first = bring_in(s, title_first_text())
        kept = approve_all(s, first_id, first)
        # The same result written twice: one card of theirs, two proposals.
        line = "• Cut load time by 40%."
        again_id, _ = bring_in(s, title_first_text().replace(line, f"{line}\n{line}"))
        matches = s.imports.matches(again_id, s.cards)
        assert matches["card-4"].card_id == kept["card-4"] and "card-5" not in matches

        s.imports.decide(again_id, "card-4", "dropped")
        assert s.imports.matches(again_id, s.cards)["card-5"].card_id == kept["card-4"]


def test_wording_edited_while_approving_goes_into_the_same_card(make_user, open_: Open) -> None:
    user = make_user()
    with open_(user) as s:
        first_id, first = bring_in(s, title_first_text())
        kept = approve_all(s, first_id, first)
        again_id, again = bring_in(s, title_first_text())
        for proposed in again.cards[:3]:
            s.imports.approve(again_id, proposed.ref, None, s.cards, ME)

        # The line matched one of theirs by its headline, then they reworded it.
        line = again.cards[3]
        framing = line.content.framing.model_copy(update={"headline": "Cut nightly loads by 40%."})
        edited = line.content.model_copy(update={"framing": framing})
        card, _ = s.imports.approve(again_id, line.ref, edited, s.cards, ME, "update")

        assert card.id == kept["card-4"] and versions(s, card.id) == 2
        head = s.cards.card_detail(card.id).main.content
        assert isinstance(head, MainContent) and head.framing.headline == framing.headline


def test_a_change_made_in_another_tab_meanwhile_is_kept(
    make_user, db: Database, vault: Vault
) -> None:
    user = make_user()
    with db.as_user(user) as conn:
        cipher = vault.cipher_for(conn, user)
        s = Stores(ImportStore(conn, user, cipher), CardRepository(conn, user, cipher))
        first_id, first = bring_in(s, title_first_text())
        kept = approve_all(s, first_id, first)
        again_id, _ = bring_in(s, updated_text())

        class Racing(CardRepository):
            """Another tab saves the employment just after approving reads it."""

            def main_contents(self) -> dict[UUID, CardText]:
                read = super().main_contents()
                detail = self.card_detail(kept["card-1"])
                mine = detail.main.content
                assert isinstance(mine, MainContent)
                added = {**mine.facts, "employment_type": "full-time"}
                self.save_main_version(
                    kept["card-1"],
                    detail.main.head.id,
                    mine.model_copy(update={"facts": added}),
                    ME,
                )
                return read

        racing = Racing(conn, user, cipher)
        s.imports.approve(again_id, "card-1", None, racing, ME, "update")

        head = s.cards.card_detail(kept["card-1"]).main.content
        assert isinstance(head, MainContent)
        assert head.facts["employment_type"] == "full-time" and head.facts["end"] == "2007-03"
        assert versions(s, kept["card-1"]) == 3


# -- going through a job at once ------------------------------------------------


def keeping(*refs: str) -> list[KeepCard]:
    return [KeepCard(ref=ref) for ref in refs]


def test_a_job_is_kept_in_one_go_each_card_under_its_own(make_user, open_: Open) -> None:
    user = make_user()
    with open_(user) as s:
        import_id, _ = bring_in(s, title_first_text())
        # Listed children first: each is still saved after the card it sits under.
        progress = s.imports.keep_group(
            import_id,
            keeping("card-6", "card-4", "card-5", "card-2", "card-1"),
            s.cards,
            ME,
            leave_out=["card-3"],
            later=["card-7"],
        )
        decided = {ref: d.state for ref, d in progress.cards.items()}
        assert decided == {
            "card-1": "approved",
            "card-2": "approved",
            "card-4": "approved",
            "card-5": "approved",
            "card-6": "approved",
            "card-3": "dropped",
            "card-7": "later",
        }
        saved = {ref: d.card_id for ref, d in progress.cards.items() if d.card_id}
        assert s.cards.card_detail(saved["card-4"]).parent_id == saved["card-2"]
        assert s.cards.card_detail(saved["card-6"]).parent_id == saved["card-5"]
        assert s.cards.card_detail(saved["card-5"]).parent_id == saved["card-1"]
        assert len(s.cards.list_cards()) == 5


def test_a_job_kept_in_another_tab_meanwhile_isnt_kept_twice(make_user, open_: Open) -> None:
    user = make_user()
    with open_(user) as s:
        import_id, _ = bring_in(s, title_first_text())
        s.imports.keep_group(import_id, keeping("card-1", "card-2"), s.cards, ME)
        with pytest.raises(ImportConflictError):
            s.imports.keep_group(import_id, keeping("card-2", "card-3"), s.cards, ME)
        with pytest.raises(ImportConflictError):
            s.imports.keep_group(import_id, keeping("card-3"), s.cards, ME, later=["card-3"])


def test_a_group_that_cant_all_be_kept_keeps_none_of_it(make_user, open_: Open) -> None:
    user = make_user()
    with open_(user) as s:
        import_id, _ = bring_in(s, title_first_text())
    # The title's employer is still undecided, so the whole group is refused,
    # and the transaction it ran in keeps nothing.
    with pytest.raises(ImportConflictError), open_(user) as s:
        s.imports.keep_group(import_id, keeping("card-3", "card-2"), s.cards, ME)
    with open_(user) as s:
        assert s.cards.list_cards() == []
        assert s.imports.summary(import_id).approved == 0


def twice_text() -> str:
    """The same result written twice under one title. Made up."""
    return title_first_text().replace(
        "• Cut load time by 40%.", "• Cut load time by 40%.\n• Cut load time by 40%."
    )


def test_a_line_left_out_keeps_its_match_to_itself(make_user, open_: Open) -> None:
    user = make_user()
    with open_(user) as s:
        first_id, first = bring_in(s, twice_text())
        kept = approve_all(s, first_id, first)

        again_id, _ = bring_in(s, twice_text())
        seen = s.imports.matches(again_id, s.cards)
        assert seen["card-4"].card_id == kept["card-4"]
        assert seen["card-5"].card_id == kept["card-5"]
        # Leaving out the first copy doesn't hand its card to the second: the
        # second carries on as the card it showed as.
        progress = s.imports.keep_group(
            again_id, keeping("card-1", "card-2", "card-5"), s.cards, ME, leave_out=["card-4"]
        )
        assert progress.cards["card-5"].card_id == kept["card-5"]
        assert progress.cards["card-4"].state == "dropped"


def test_a_job_brought_in_again_carries_on_as_the_persons_cards(make_user, open_: Open) -> None:
    user = make_user()
    with open_(user) as s:
        first_id, first = bring_in(s, title_first_text())
        kept = approve_all(s, first_id, first)

        again_id, _ = bring_in(s, updated_text())
        progress = s.imports.keep_group(
            again_id,
            [
                KeepCard(ref="card-1"),
                KeepCard(ref="card-2", choice="keep"),
                KeepCard(ref="card-3"),
                KeepCard(ref="card-4"),
            ],
            s.cards,
            ME,
        )
        saved = {ref: d.card_id for ref, d in progress.cards.items()}
        assert saved["card-1"] == kept["card-1"] and versions(s, kept["card-1"]) == 2
        # Kept as it was, though its end moved.
        assert saved["card-2"] == kept["card-2"] and versions(s, kept["card-2"]) == 1
        assert saved["card-3"] == kept["card-3"]
        assert saved["card-4"] not in kept.values()
