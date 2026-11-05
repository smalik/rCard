"""Every line of a resume lands somewhere (imports/accounting.py), and titles that
share an employer's tenure aren't asked for dates of their own. Uses a made-up
resume (tests/resume_samples.py) and a fake reader in place of Claude."""

from datetime import date
from typing import Any

from plytos_api.imports.ai import AiResume
from plytos_api.imports.model import ExtractedDocument, ImportResult
from plytos_api.imports.pipeline import import_resume
from tests.resume_samples import stint_text, workstream_text, wrapped_text

TODAY = date(2026, 11, 4)
LINES = 20


class FakeReader:
    name = "fake-model"

    def __init__(self, reading: dict[str, Any]) -> None:
        self.reading = reading

    def read(self, doc: ExtractedDocument) -> AiResume | None:
        return AiResume.model_validate(self.reading)


def _role(**fields: Any) -> dict[str, Any]:
    role: dict[str, Any] = {
        "employment": 0,
        "volunteer": False,
        "title": "",
        "employer": "",
        "client": "",
        "location": "",
        "employment_type": "",
        "dates": "",
        "header_lines": [],
        "engagement_of": -1,
        "subheading_lines": [],
        "bullet_lines": [],
        "description_lines": [],
        "unsure": False,
    }
    role.update(fields)
    return role


def reading() -> dict[str, Any]:
    """A good reading of stint_text()."""
    return {
        "name": "Jordan Lee",
        "contact_lines": [0, 1],
        "sections": [
            {"kind": "contact", "heading_line": -1, "lines": [0, 1]},
            {"kind": "experience", "heading_line": 2, "lines": list(range(3, 15))},
            {"kind": "education", "heading_line": 15, "lines": [16]},
            {"kind": "other", "heading_line": 17, "lines": [18, 19]},
        ],
        "summary_lines": [],
        "employments": [
            {
                "employer": "Contoso Health",
                "location": "Denver, CO",
                "dates": "2015 – 2023",
                "header_lines": [3],
                "description_lines": [4],
            },
            {
                "employer": "Fabrikam Clinics",
                "location": "Boulder, CO",
                "dates": "2012 – 2015",
                "header_lines": [11],
                "description_lines": [],
            },
        ],
        "roles": [
            _role(title="Director of Patient Access", header_lines=[5], bullet_lines=[6]),
            _role(title="Manager, Scheduling", header_lines=[7], bullet_lines=[8]),
            _role(title="Supervisor, Registration", header_lines=[9], bullet_lines=[10]),
            _role(employment=1, title="Office Manager", header_lines=[12], bullet_lines=[13]),
        ],
        "skills": [],
        "entries": [
            {"kind": "education", "lines": [16], "dates": "2012", "school": "", "degree": ""},
            {"kind": "activity", "lines": [18], "dates": "2022", "school": "", "degree": ""},
        ],
        "skipped": [{"line": 14, "reason": "page_number"}, {"line": 19, "reason": "references"}],
    }


def _import(found: dict[str, Any] | None) -> ImportResult:
    return import_resume(
        stint_text().encode(),
        "jordan.txt",
        today=TODAY,
        reader=FakeReader(found) if found is not None else None,
    )


def _every_line_accounted(result: ImportResult) -> None:
    lines = result.lines
    assert lines is not None and lines.lines == LINES
    on_cards = {i for c in result.cards for i in c.source_blocks}
    places = [
        on_cards,
        set(lines.contact),
        set(lines.headings),
        {s.block for s in lines.skipped},
    ]
    assert set().union(*places) == set(range(LINES))
    # Guessed lines are on cards of their own, marked to check.
    for i in lines.guessed:
        card = next(c for c in result.cards if i in c.source_blocks)
        assert card.needs_check


def _employment(result: ImportResult, name: str) -> Any:
    return next(
        c
        for c in result.cards
        if c.kind == "employment" and c.content.facts.get("employer") == name
    )


def test_a_good_reading_places_every_line() -> None:
    result = _import(reading())
    _every_line_accounted(result)
    assert result.lines is not None and result.lines.guessed == []
    skipped = {(s.block, s.reason) for s in result.lines.skipped}
    assert skipped == {(14, "page_number"), (19, "references")}
    assert "content.references" in {f.rule for f in result.findings}
    contoso = _employment(result, "Contoso Health")
    assert contoso.content.framing.body == (
        "A regional hospital network with 12 sites and 9,000 staff."
    )
    assert 4 in contoso.source_blocks
    activity = next(c for c in result.cards if c.kind == "activity")
    assert activity.content.framing.headline == ("Speaker, Colorado Healthcare Access Summit, 2022")
    assert activity.content.facts["date"] == "2022"


def test_a_line_about_the_employer_left_out_still_describes_it() -> None:
    found = reading()
    found["employments"][0]["description_lines"] = []
    found["sections"][1]["lines"] = list(range(3, 15))
    result = _import(found)
    _every_line_accounted(result)
    contoso = _employment(result, "Contoso Health")
    assert contoso.content.framing.body.startswith("A regional hospital network")
    assert result.lines is not None and 4 not in result.lines.guessed


def test_a_line_nothing_claimed_becomes_a_card_to_check() -> None:
    found = reading()
    found["entries"] = [e for e in found["entries"] if e["kind"] != "activity"]
    found["sections"][3]["lines"] = [18, 19]
    result = _import(found)
    _every_line_accounted(result)
    assert result.lines is not None and result.lines.guessed == [18]
    card = next(c for c in result.cards if 18 in c.source_blocks)
    assert card.kind == "activity"
    assert card.needs_check and "wasn't sure" in card.needs_check[0]


def test_a_stray_line_under_a_title_asks_which_job() -> None:
    found = reading()
    found["roles"][1]["bullet_lines"] = []  # line 8 left out
    found["sections"][1]["lines"] = [i for i in range(3, 15) if i != 8]
    result = _import(found)
    _every_line_accounted(result)
    card = next(c for c in result.cards if 8 in c.source_blocks)
    assert card.kind == "accomplishment"
    by_ref = {c.ref: c for c in result.cards}
    assert card.parent_ref is not None
    assert by_ref[card.parent_ref].content.facts.get("title") == "Manager, Scheduling"
    assert card.needs_check == [
        "Plytos wasn't sure where this line belongs. Is it from your time at Contoso Health?"
    ]


def test_titles_inside_a_dated_employer_dont_need_their_own_dates() -> None:
    result = _import(reading())
    rules = {f.rule for f in result.findings}
    assert "dates.missing" not in rules
    shared = next(f for f in result.findings if f.rule == "dates.titles_share_tenure")
    assert shared.severity == "note"
    assert "3 titles at Contoso Health" in shared.title
    for card in result.cards:
        if card.kind == "position":
            assert "When did you start and finish in this title?" not in card.needs_check
    # A lone title under a dated employer takes the employer's dates without a note.
    assert len([f for f in result.findings if f.rule == "dates.titles_share_tenure"]) == 1


def test_the_rules_alone_also_account_for_every_line() -> None:
    result = _import(None)
    assert result.read_by is None
    _every_line_accounted(result)
    assert result.lines is not None
    skipped = {(s.block, s.reason) for s in result.lines.skipped}
    assert (14, "page_number") in skipped
    # The rules read the references line as a heading; the audit points it out.
    assert 19 in result.lines.headings
    assert "content.references" in {f.rule for f in result.findings}


def _workstream_reading(subheadings: list[int], experience: list[int]) -> dict[str, Any]:
    """A reading of workstream_text() that takes the "Continued..." footer for a
    contact line, as Claude once did."""
    return {
        "name": "Casey Morgan",
        "contact_lines": [0, 1, 9],
        "sections": [
            {"kind": "contact", "heading_line": -1, "lines": [0, 1]},
            {"kind": "experience", "heading_line": 2, "lines": experience},
            {"kind": "education", "heading_line": 10, "lines": [11]},
        ],
        "summary_lines": [],
        "employments": [],
        "roles": [
            _role(
                title="Consultant",
                employer="Contoso Motors",
                location="Plano, TX",
                dates="Aug 2025 – Present",
                header_lines=[3],
                subheading_lines=subheadings,
                bullet_lines=[5, 6, 8],
            )
        ],
        "skills": [],
        "entries": [
            {"kind": "education", "lines": [11], "dates": "2015", "school": "", "degree": ""}
        ],
        "skipped": [],
    }


def _workstreams(result: ImportResult) -> dict[int, object]:
    return {
        c.source_blocks[0]: c.content.facts.get("workstream")
        for c in result.cards
        if c.kind == "accomplishment"
    }


def _import_workstreams(found: dict[str, Any] | None) -> ImportResult:
    return import_resume(
        workstream_text().encode(),
        "casey.txt",
        today=TODAY,
        reader=FakeReader(found) if found is not None else None,
    )


def _all_lines_placed(result: ImportResult) -> None:
    lines = result.lines
    assert lines is not None
    on_cards = {i for c in result.cards for i in c.source_blocks}
    placed = on_cards | set(lines.contact) | set(lines.headings) | {s.block for s in lines.skipped}
    assert placed == set(range(lines.lines))


def test_workstream_labels_are_headings_not_cards() -> None:
    result = _import_workstreams(_workstream_reading([4, 7], [3, 4, 5, 6, 7, 8, 9]))
    _all_lines_placed(result)
    assert result.lines is not None
    assert result.lines.guessed == []
    assert {4, 7} <= set(result.lines.headings)
    assert _workstreams(result) == {
        5: "Enterprise AI",
        6: "Enterprise AI",
        8: "Workforce Strategies",
    }


def test_a_continued_footer_taken_for_contact_is_skipped() -> None:
    result = _import_workstreams(_workstream_reading([4, 7], [3, 4, 5, 6, 7, 8, 9]))
    assert result.lines is not None
    assert 9 not in result.lines.contact
    assert (9, "page_number") in {(s.block, s.reason) for s in result.lines.skipped}


def test_a_label_the_reader_left_out_still_names_its_workstream() -> None:
    # The labels are in no list at all: they read as headings over the bullets below.
    result = _import_workstreams(_workstream_reading([], [3, 5, 6, 8, 9]))
    _all_lines_placed(result)
    assert result.lines is not None
    assert result.lines.guessed == []
    assert _workstreams(result) == {
        5: "Enterprise AI",
        6: "Enterprise AI",
        8: "Workforce Strategies",
    }


def test_the_rules_alone_keep_workstream_labels_off_cards() -> None:
    result = _import_workstreams(None)
    _all_lines_placed(result)
    assert result.lines is not None
    assert result.lines.guessed == []
    assert set(_workstreams(result).values()) == {"Enterprise AI", "Workforce Strategies"}


def test_duties_cut_at_line_wraps_become_one_card_each() -> None:
    """Claude lists each wrapped line as a bullet, as it did on such a PDF: the cards
    follow the sentences, not the wraps."""
    found = {
        "name": "Jamie Fox",
        "contact_lines": [0, 1],
        "sections": [
            {"kind": "contact", "heading_line": -1, "lines": [0, 1]},
            {"kind": "experience", "heading_line": 2, "lines": list(range(3, 9))},
        ],
        "summary_lines": [],
        "employments": [],
        "roles": [
            _role(
                title="Public Relations Specialist",
                employer="Company Name",
                dates="Jan 2015 – Dec 2019",
                header_lines=[3],
                bullet_lines=[4, 5, 6],
            ),
            _role(
                title="Account Coordinator",
                employer="Company Name",
                dates="Jan 2012 – Dec 2014",
                header_lines=[7],
                bullet_lines=[8],
            ),
        ],
        "skills": [],
        "entries": [],
        "skipped": [],
    }
    result = import_resume(
        wrapped_text().encode(), "jamie.txt", today=TODAY, reader=FakeReader(found)
    )
    duties = [
        (c.content.framing.headline, c.source_blocks)
        for c in result.cards
        if c.kind == "accomplishment"
    ]
    assert duties == [
        ("Wrote press releases for 6 product launches.", [4]),
        ("Managed media relations with trade press and pitched 40 stories a year.", [4, 5]),
        ("Coordinated events for the firm.", [5, 6]),
        ("Tracked coverage for 12 clients.", [8]),
    ]
    _all_lines_placed(result)
    # Two jobs at "Company Name" are two employers, not one stint.
    assert len([c for c in result.cards if c.kind == "employment"]) == 2


def test_entries_listed_under_a_year_take_that_year() -> None:
    text = "\n".join(
        [
            "Lee Park",
            "lee.park@example.com",
            "EXHIBITIONS",
            "2019",
            "Group show, Contoso Gallery, Austin",
            "Solo show, Fabrikam Arts Center, Dallas",
            "2017",
            "Open studio, Northwind Studios, Austin",
        ]
    )
    found = {
        "name": "Lee Park",
        "contact_lines": [0, 1],
        "sections": [
            {"kind": "contact", "heading_line": -1, "lines": [0, 1]},
            {"kind": "activities", "heading_line": 2, "lines": [3, 4, 5, 6, 7]},
        ],
        "summary_lines": [],
        "employments": [],
        "roles": [],
        "skills": [],
        "entries": [
            {"kind": "activity", "lines": [4], "dates": "2019", "school": "", "degree": ""},
            {"kind": "activity", "lines": [5], "dates": "2019", "school": "", "degree": ""},
            {"kind": "activity", "lines": [7], "dates": "2017", "school": "", "degree": ""},
        ],
        "skipped": [],
    }
    result = import_resume(text.encode(), "lee.txt", today=TODAY, reader=FakeReader(found))
    dated = {
        c.content.framing.headline: c.content.facts.get("date")
        for c in result.cards
        if c.kind == "activity"
    }
    assert dated == {
        "Group show, Contoso Gallery, Austin": "2019",
        "Solo show, Fabrikam Arts Center, Dallas": "2019",
        "Open studio, Northwind Studios, Austin": "2017",
    }
    # The year lines head the entries under them.
    assert result.lines is not None
    assert result.lines.guessed == [] and {3, 6} <= set(result.lines.headings)


def test_a_workstream_read_as_another_title_is_folded_back() -> None:
    # The second label read as a title of its own, undated, under the same employer.
    found = _workstream_reading([4], [3, 4, 5, 6, 7, 8, 9])
    found["roles"][0]["bullet_lines"] = [5, 6]
    found["roles"].append(_role(title="Workforce Strategies", header_lines=[7], bullet_lines=[8]))
    found["employments"] = [
        {
            "employer": "Contoso Motors",
            "location": "Plano, TX",
            "dates": "",
            "header_lines": [],
            "description_lines": [],
        }
    ]
    found["roles"][0]["employment"] = 0
    result = _import_workstreams(found)
    _all_lines_placed(result)
    assert [c.content.facts.get("title") for c in result.cards if c.kind == "position"] == [
        "Consultant"
    ]
    assert _workstreams(result) == {
        5: "Enterprise AI",
        6: "Enterprise AI",
        8: "Workforce Strategies",
    }


def test_an_undated_title_under_a_dated_one_stays_a_title() -> None:
    text = "\n".join(
        [
            "Casey Morgan",
            "casey.morgan@example.com | 555-0100",
            "EXPERIENCE",
            "Consultant, Contoso Motors, Plano, TX\tAug 2025 – Present",
            "• Built a document search assistant used by 400 analysts.",
            "Senior Consultant",
            "• Modeled staffing needs for 6 plants.",
        ]
    )
    found = _workstream_reading([], [3, 4, 5, 6])
    found["sections"] = found["sections"][:2]
    found["contact_lines"] = [0, 1]
    found["entries"] = []
    found["roles"][0].update(subheading_lines=[], bullet_lines=[4])
    found["roles"].append(_role(title="Senior Consultant", header_lines=[5], bullet_lines=[6]))
    result = import_resume(text.encode(), "casey.txt", today=TODAY, reader=FakeReader(found))
    titles = [c.content.facts.get("title") for c in result.cards if c.kind == "position"]
    assert titles == ["Consultant", "Senior Consultant"]
