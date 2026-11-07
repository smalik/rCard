"""The import's fidelity bench: the scorer itself, and the floor each layout is held to.

Every resume here is written from a made-up career (imports/fidelity/truth.py), so
what a right reading looks like is known exactly.
"""

import json
from pathlib import Path

import pytest

from plytos_api.cards.model import FactValue, Framing, MainContent
from plytos_api.imports.fidelity.layouts import PDF, WORD, layouts
from plytos_api.imports.fidelity.run import read_one
from plytos_api.imports.fidelity.score import norm, score
from plytos_api.imports.fidelity.truth import CAREERS, MORGAN, SAM, Career
from plytos_api.imports.model import Contact, DocumentFacts, ImportResult, ProposedCard

BASELINE_PATH = Path(__file__).with_name("fidelity_baseline.json")
BASELINE: dict[str, dict[str, float]] = json.loads(BASELINE_PATH.read_text())
CLASSIC = WORD[0]
YEARS = next(lay for lay in WORD if lay.years_only)


def perfect(career: Career, *, years_only: bool = False) -> ImportResult:
    """The reading a perfect import would give."""
    cards: list[ProposedCard] = []

    def when(value: str) -> str:
        return value[:4] if years_only and value != "present" else value

    def add(
        kind: str,
        headline: str,
        facts: dict[str, FactValue] | None = None,
        parent: str | None = None,
        body: str = "",
    ) -> ProposedCard:
        card = ProposedCard.model_validate(
            {
                "ref": f"card-{len(cards) + 1}",
                "kind": kind,
                "content": MainContent(
                    facts=facts or {}, framing=Framing(headline=headline, body=body)
                ),
                "parent_ref": parent,
            }
        )
        cards.append(card)
        return card

    add("story", career.summary, {"use": "summary"})
    employers: dict[str, str] = {}
    for e in career.employments:
        facts: dict[str, FactValue] = {
            "employer": e.employer,
            "start": when(e.start),
            "end": when(e.end),
        }
        employers[e.employer] = add("employment", e.employer, facts).ref
        for p in e.positions:
            title: dict[str, FactValue] = {
                "title": p.title,
                "start": when(p.start),
                "end": when(p.end),
            }
            at = add("position", p.title, title, employers[e.employer]).ref
            for g in p.groups:
                for item in g.items:
                    add("accomplishment", item, {"workstream": g.label} if g.label else {}, at)
    for h in career.highlights:
        add("accomplishment", h.text, {}, employers[h.names] if h.names else None)
    for s in career.skills:
        add(
            "skill",
            s.category,
            {"category": s.category, "skills": s.items},
            body=", ".join(s.items),
        )
    for school in career.education:
        add(
            "education",
            f"{school.degree} {school.field}, {school.school}, {school.year}",
            {
                "institution": school.school,
                "degree": f"{school.degree} {school.field}",
                "date": school.year,
            },
        )
    for a in career.awards:
        add("accomplishment", f"{a.name}, {a.issuer}, {a.year}", {"award": a.name, "date": a.year})
    for t in career.talks:
        add("activity", t.text, {"name": t.text, "date": t.year})
    return ImportResult(
        facts=DocumentFacts(format="docx", filename="resume.docx"),
        contact=Contact(
            name=career.name,
            emails=[career.email],
            phones=[career.phone],
            location=career.location,
        ),
        sections=[],
        roles=[],
        cards=cards,
        findings=[],
        blocks=[],
    )


def card_with(result: ImportResult, text: str) -> ProposedCard:
    return next(c for c in result.cards if c.content.framing.headline == text)


@pytest.mark.parametrize("career", CAREERS, ids=lambda c: c.key)
def test_a_perfect_reading_scores_full_marks(career: Career) -> None:
    s = score(career, CLASSIC, perfect(career))
    assert s.misses == []
    assert s.fidelity == 1.0
    assert s.items.of == sum(len(p.items) for e in career.employments for p in e.positions)


def test_years_only_layouts_are_held_to_the_year() -> None:
    s = score(MORGAN, YEARS, perfect(MORGAN, years_only=True))
    assert s.fidelity == 1.0
    # The same reading of a layout that writes months is wrong on every date but the
    # two that say "present".
    assert score(MORGAN, CLASSIC, perfect(MORGAN, years_only=True)).dates.right == 2


def test_an_accomplishment_under_the_wrong_title_is_misattributed() -> None:
    reading = perfect(MORGAN)
    moved = card_with(reading, "Found $700K a year in freight billing errors.")
    moved.parent_ref = card_with(reading, "Operations Manager").ref
    s = score(MORGAN, CLASSIC, reading)
    assert (s.misattributed, s.unplaced, s.missing) == (1, 0, 0)
    assert s.items.right == s.items.of - 1
    assert s.fidelity < 1.0


def test_a_title_under_the_wrong_employer_takes_its_accomplishments_with_it() -> None:
    reading = perfect(MORGAN)
    title = card_with(reading, "Senior Operations Manager")
    title.parent_ref = card_with(reading, "Tailspin Freight").ref
    s = score(MORGAN, CLASSIC, reading)
    assert s.misattributed == len(MORGAN.employments[0].positions[1].items)
    assert s.positions.right == s.positions.of - 1


def test_an_accomplishment_under_no_title_is_unplaced() -> None:
    reading = perfect(SAM)
    card_with(reading, "Set up data contracts for 14 producer teams.").parent_ref = None
    s = score(SAM, CLASSIC, reading)
    assert (s.unplaced, s.misattributed) == (1, 0)


def test_two_accomplishments_on_one_card_are_merged() -> None:
    reading = perfect(SAM)
    first = card_with(reading, "Set up data contracts for 14 producer teams.")
    second = card_with(reading, "Mentored four engineers who were each promoted within a year.")
    first.content.framing.headline += " " + second.content.framing.headline
    reading.cards.remove(second)
    s = score(SAM, CLASSIC, reading)
    assert s.merged == 2
    assert s.items.right == s.items.of - 2


def test_an_accomplishment_split_across_cards_is_split() -> None:
    reading = perfect(SAM)
    whole = card_with(
        reading, "Replaced nightly batch jobs with streaming that lands data in minutes."
    )
    whole.content.framing.headline = "Replaced nightly batch jobs"
    tail = whole.model_copy(deep=True)
    tail.ref = "card-tail"
    tail.content.framing.headline = "with streaming that lands data in minutes."
    reading.cards.insert(reading.cards.index(whole) + 1, tail)
    s = score(SAM, CLASSIC, reading)
    assert (s.split, s.missing, s.extra) == (1, 0, 0)


def test_a_lost_workstream_and_an_invented_card_both_count() -> None:
    reading = perfect(MORGAN)
    card_with(reading, "Grew the site leadership team from 6 to 11 managers.").content.facts = {}
    label = card_with(reading, "Director of Operations").model_copy(deep=True)
    label.ref = "card-label"
    label.kind = "accomplishment"
    label.content = MainContent(facts={}, framing=Framing(headline="Network redesign"))
    reading.cards.append(label)
    s = score(MORGAN, CLASSIC, reading)
    assert s.groups.right == s.groups.of - 1
    assert s.extra == 1


def test_an_employer_read_as_two_employments_is_counted() -> None:
    reading = perfect(MORGAN)
    northwind = card_with(reading, "Northwind Logistics")
    twin = northwind.model_copy(deep=True)
    twin.ref = "card-twin"
    reading.cards.append(twin)
    card_with(reading, "Senior Operations Manager").parent_ref = twin.ref
    s = score(MORGAN, CLASSIC, reading)
    assert s.employers_split == 1
    assert s.employers.right == s.employers.of - 1


def test_a_highlight_naming_an_employer_belongs_under_it() -> None:
    reading = perfect(MORGAN)
    card_with(
        reading, "Named to the Tailspin Freight leadership bench after two years."
    ).parent_ref = None
    s = score(MORGAN, CLASSIC, reading)
    assert s.others.right == s.others.of - 1


def test_a_failed_import_counts_everything_as_lost() -> None:
    s = score(SAM, CLASSIC, None, failed="UnsupportedFileError")
    assert s.fidelity == 0.0
    assert s.missing == sum(len(p.items) for e in SAM.employments for p in e.positions)


def test_words_compare_without_case_or_punctuation() -> None:
    assert norm("Raised on-time shipping from 91% to 98.5%.") == norm(
        "raised on time shipping from 91% to 98.5%"
    )
    assert norm("$1.2M under budget.") == "$1.2m under budget"


# -- the floor ----------------------------------------------------------------------

CI_LAYOUTS = {lay.name: lay for lay in layouts(with_word_pdfs=False) if not lay.needs_ai}
CI_CAREERS = {c.key: c for c in CAREERS}


def test_every_word_and_pdf_layout_has_a_baseline() -> None:
    assert set(CI_LAYOUTS) == {lay.name for lay in WORD + PDF}
    want = {f"{c}/{lay}" for c in CI_CAREERS for lay in CI_LAYOUTS}
    assert set(BASELINE) == want, (
        "Write it again: python -m plytos_api.imports.fidelity "
        "--write-baseline tests/fidelity_baseline.json"
    )


@pytest.mark.parametrize("key", sorted(BASELINE))
def test_no_layout_reads_worse_than_its_baseline(key: str) -> None:
    career, layout = key.split("/")
    s = read_one(CI_CAREERS[career], CI_LAYOUTS[layout])
    floor = BASELINE[key]
    assert s.failed is None
    assert s.fidelity >= floor["fidelity"], s.misses
    assert s.misattributed + s.unplaced <= floor["wrong_place"], s.misses
    assert s.missing <= floor["missing"], s.misses
