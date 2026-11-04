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
from plytos_api.cards.repository import Author, CardRepository
from plytos_api.db import Database
from plytos_api.imports.matching import name_key, overlaps
from plytos_api.imports.model import ImportResult
from plytos_api.imports.pipeline import import_resume
from plytos_api.imports.store import ImportConflictError, ImportStore, MatchChoice
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


def test_dates_must_overlap_when_both_sides_have_them() -> None:
    def card(**facts: object) -> MainContent:
        return MainContent(facts=facts, framing=Framing(headline="x"))  # type: ignore[arg-type]

    assert overlaps(card(start="2019-01", end="present"), card(start="2021", end="2022"))
    assert overlaps(card(start="2002", end="2005"), card(start="2005-06", end="2007-01"))
    assert not overlaps(card(start="2002", end="2004"), card(start="2010", end="present"))
    assert overlaps(card(), card(start="2010", end="present"))


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
