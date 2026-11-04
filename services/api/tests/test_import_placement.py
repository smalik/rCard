"""Every result sits under the job it came from (imports/placement.py). A fake reader
files the made-up resume in tests/resume_samples.py, sometimes wrongly, and a fake
second look stands in for Claude's placement check."""

from datetime import date
from typing import Any

import pytest

from plytos_api.cards.repository import Author, CardRepository
from plytos_api.imports.ai import AiPlacementCheck, AiResume
from plytos_api.imports.model import ExtractedDocument, ImportResult, ProposedCard
from plytos_api.imports.pipeline import import_resume
from plytos_api.imports.store import ImportConflictError, ImportNotFoundError, ImportStore
from tests.resume_samples import one_line_text, stint_text
from tests.test_import_lines import _role, reading

TODAY = date(2026, 11, 4)
ME = Author("person")


class FakeReader:
    name = "fake-model"

    def __init__(self, found: dict[str, Any], misfiled: list[dict[str, Any]] | None) -> None:
        self.found = found
        self.misfiled = misfiled
        self.trees: list[str] = []

    def read(self, doc: ExtractedDocument) -> AiResume | None:
        return AiResume.model_validate(self.found)

    def check_placements(self, doc: ExtractedDocument, tree: str) -> AiPlacementCheck | None:
        self.trees.append(tree)
        if self.misfiled is None:
            return None
        return AiPlacementCheck.model_validate({"misfiled": self.misfiled})


def _import(
    found: dict[str, Any], misfiled: list[dict[str, Any]] | None = None
) -> tuple[ImportResult, FakeReader]:
    reader = FakeReader(found, misfiled if misfiled is not None else [])
    result = import_resume(stint_text().encode(), "jordan.txt", today=TODAY, reader=reader)
    return result, reader


def _card(result: ImportResult, line: int) -> ProposedCard:
    return next(c for c in result.cards if c.source_blocks and min(c.source_blocks) == line)


def _title_of(result: ImportResult, ref: str | None) -> Any:
    card = next(c for c in result.cards if c.ref == ref)
    return card.content.facts.get("title") or card.content.facts.get("employer")


def _misfiled_under_director() -> dict[str, Any]:
    """Files the Manager's result (line 8) under the Director (line 5)."""
    found = reading()
    found["roles"][0]["bullet_lines"] = [6, 8]
    found["roles"][1]["bullet_lines"] = []
    return found


def test_a_good_filing_raises_no_questions() -> None:
    result, reader = _import(reading())
    assert [c.ref for c in result.cards if c.placement] == []
    # The second look sees the tree with short refs and line numbers.
    assert reader.trees == [
        "E1 Contoso Health — employer line 3; also 4\n"
        "  T1 Director of Patient Access — title line 5; lines 6\n"
        "  T2 Manager, Scheduling — title line 7; lines 8\n"
        "  T3 Supervisor, Registration — title line 9; lines 10\n"
        "E2 Fabrikam Clinics — employer line 11\n"
        "  T4 Office Manager — title line 12; lines 13"
    ]


def test_both_checks_agree_so_the_result_moves_and_asks() -> None:
    misfiled = [
        {
            "line": 8,
            "belongs_under": "T2",
            "sure": True,
            "reason": "Your resume lists it under Manager, Scheduling.",
        }
    ]
    result, _ = _import(_misfiled_under_director(), misfiled)
    card = _card(result, 8)
    assert _title_of(result, card.parent_ref) == "Manager, Scheduling"
    assert card.placement is not None
    assert card.placement.question == "Which job is this from?"
    assert card.placement.reason == "Your resume lists it under Manager, Scheduling."
    assert [c.label for c in card.placement.choices] == [
        "Manager, Scheduling at Contoso Health",
        "Director of Patient Access at Contoso Health",
    ]
    assert _title_of(result, card.placement.moved_from) == "Director of Patient Access"


def test_order_alone_asks_without_moving() -> None:
    result, _ = _import(_misfiled_under_director(), [])
    card = _card(result, 8)
    assert _title_of(result, card.parent_ref) == "Director of Patient Access"
    assert card.placement is not None and card.placement.moved_from is None
    assert card.placement.reason == (
        "It's written under Manager, Scheduling at Contoso Health on your resume."
    )
    assert [c.label for c in card.placement.choices] == [
        "Director of Patient Access at Contoso Health",
        "Manager, Scheduling at Contoso Health",
    ]


def test_the_second_look_alone_asks_without_moving() -> None:
    misfiled = [
        {
            "line": 6,
            "belongs_under": "T3",
            "sure": False,
            "reason": "Registration wait times sound like the Supervisor role.",
        }
    ]
    result, _ = _import(reading(), misfiled)
    card = _card(result, 6)
    assert _title_of(result, card.parent_ref) == "Director of Patient Access"
    assert card.placement is not None and card.placement.moved_from is None
    assert card.placement.reason == "Registration wait times sound like the Supervisor role."
    assert [c.label for c in card.placement.choices][1] == (
        "Supervisor, Registration at Contoso Health"
    )


def test_a_title_filed_under_the_wrong_employer_is_questioned() -> None:
    found = reading()
    found["roles"][2]["employment"] = 1  # Supervisor (line 9) put under Fabrikam
    result, _ = _import(found, [])
    card = _card(result, 9)
    assert card.kind == "position"
    assert card.placement is not None
    assert card.placement.question == "Which employer was this title at?"
    assert [c.label for c in card.placement.choices] == [
        "Fabrikam Clinics, 2012 – 2015",
        "Contoso Health, 2015 – 2023",
    ]


def test_misfiled_with_no_place_offers_every_job() -> None:
    misfiled = [{"line": 13, "belongs_under": "", "sure": False, "reason": "Unclear."}]
    result, _ = _import(reading(), misfiled)
    card = _card(result, 13)
    assert card.placement is not None
    labels = [c.label for c in card.placement.choices]
    assert labels[0] == "Office Manager at Fabrikam Clinics"
    assert "Director of Patient Access at Contoso Health" in labels
    assert len(labels) == 4


def test_no_check_runs_when_the_rules_read_the_resume() -> None:
    result = import_resume(stint_text().encode(), "jordan.txt", today=TODAY)
    assert result.read_by is None


def test_a_placed_card_is_saved_where_the_person_says(make_user, db: Any, vault: Any) -> None:
    misfiled = [{"line": 8, "belongs_under": "T2", "sure": True, "reason": "Under Manager."}]
    result, _ = _import(_misfiled_under_director(), misfiled)
    card = _card(result, 8)
    assert card.placement is not None
    moved_to, original = (c.parent_ref for c in card.placement.choices)
    employer = next(c for c in result.cards if c.kind == "employment")
    user = make_user()
    data = stint_text().encode()
    with db.as_user(user) as conn:
        cipher = vault.cipher_for(conn, user)
        store = ImportStore(conn, user, cipher)
        cards = CardRepository(conn, user, cipher)
        import_id = store.create(data, "jordan.txt", result).id
        saved = {}
        for ref in (employer.ref, moved_to, original):
            assert ref is not None
            saved[ref] = store.approve(import_id, ref, None, cards, ME)[0].id
        with pytest.raises(ImportConflictError, match="Which job is this from"):
            store.approve(import_id, card.ref, None, cards, ME)
        with pytest.raises(ImportNotFoundError):
            store.place(import_id, card.ref, "card-999")
        # The person says it's from the Director role after all.
        progress = store.place(import_id, card.ref, original)
        assert progress.moves == {card.ref: original}
        detail, _ = store.approve(import_id, card.ref, None, cards, ME)
        assert detail.parent_id == saved[original]
        with pytest.raises(ImportConflictError, match="already approved"):
            store.place(import_id, card.ref, moved_to)


def test_a_title_cant_be_moved_off_its_employer(make_user, db: Any, vault: Any) -> None:
    found = reading()
    found["roles"][2]["employment"] = 1
    result, _ = _import(found, [])
    title = _card(result, 9)
    other = next(c for c in result.cards if c.kind == "position" and c.ref != title.ref)
    user = make_user()
    with db.as_user(user) as conn:
        store = ImportStore(conn, user, vault.cipher_for(conn, user))
        import_id = store.create(stint_text().encode(), "jordan.txt", result).id
        for bad in (None, other.ref):
            with pytest.raises(ImportConflictError):
                store.place(import_id, title.ref, bad)


def test_one_line_jobs_and_later_sections_raise_no_questions() -> None:
    """A title on its employer's line belongs to that employer, and an award in its own
    section isn't asked about because of a job written above the heading."""
    found = {
        "name": "Morgan Diaz",
        "contact_lines": [0, 1],
        "sections": [
            {"kind": "contact", "heading_line": -1, "lines": [0, 1]},
            {"kind": "experience", "heading_line": 2, "lines": list(range(3, 10))},
            {"kind": "awards", "heading_line": 10, "lines": [11]},
        ],
        "summary_lines": [],
        "employments": [
            {
                "employer": "Northwind Traders",
                "location": "Seattle, WA",
                "dates": "2020 – 2024",
                "header_lines": [3],
                "description_lines": [],
            },
            {
                "employer": "Tailspin Toys",
                "location": "",
                "dates": "March 2017 to June 2020",
                "header_lines": [],
                "description_lines": [],
            },
            {
                "employer": "Fabrikam Inc.",
                "location": "",
                "dates": "2015 to 2017",
                "header_lines": [],
                "description_lines": [],
            },
        ],
        "roles": [
            _role(title="Senior Buyer", header_lines=[4], bullet_lines=[5]),
            _role(
                employment=1,
                title="Buyer",
                employer="Tailspin Toys",
                dates="March 2017 to June 2020",
                header_lines=[6],
                bullet_lines=[7],
            ),
            _role(
                employment=2,
                title="Analyst",
                employer="Fabrikam Inc.",
                dates="2015 to 2017",
                header_lines=[8],
                bullet_lines=[9],
            ),
        ],
        "skills": [],
        "entries": [{"kind": "award", "lines": [11], "dates": "2016"}],
        "skipped": [],
    }
    reader = FakeReader(found, [])
    result = import_resume(one_line_text().encode(), "morgan.txt", today=TODAY, reader=reader)
    employers = {
        c.ref: c.content.facts.get("employer") for c in result.cards if c.kind == "employment"
    }
    titles = {
        c.content.facts.get("title"): employers.get(c.parent_ref or "")
        for c in result.cards
        if c.kind == "position"
    }
    assert titles == {
        "Senior Buyer": "Northwind Traders",
        "Buyer": "Tailspin Toys",
        "Analyst": "Fabrikam Inc.",
    }
    assert [(c.kind, min(c.source_blocks)) for c in result.cards if c.placement] == []
