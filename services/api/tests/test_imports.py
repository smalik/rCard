"""Resume import: reading, splitting, auditing and proposing cards.

These run on made-up resumes (tests/resume_samples.py), never a real person's.
"""

import io
import zipfile
from datetime import date

import pytest

from plytos_api.cards.model import MainContent
from plytos_api.imports.dates import find_range, strip_range
from plytos_api.imports.extract import UnsupportedFileError, _markings, extract
from plytos_api.imports.model import ImportResult
from plytos_api.imports.pipeline import import_resume
from plytos_api.imports.segment import sentences
from plytos_api.imports.skills import spelling_fixes

from .resume_samples import clean_pdf, consultant_docx, messy_docx, messy_text, two_column_pdf

TODAY = date(2026, 11, 4)


@pytest.fixture(scope="module")
def messy() -> ImportResult:
    return import_resume(messy_docx(), "Jordan Rivera Resume_NWL final.docx", today=TODAY)


def rules(result: ImportResult) -> set[str]:
    return {f.rule for f in result.findings}


@pytest.mark.parametrize(
    ("text", "start", "end", "current", "fmt"),
    [
        ("Analyst\tJan 2018 - Feb 2021", "2018-01", "2021-02", False, "Mon YYYY"),
        ("03/2021 – Present", "2021-03", None, True, "MM/YYYY"),
        ("September 2019 to Current", "2019-09", None, True, "Month YYYY"),
        ("2014 to 2016", "2014", "2016", False, "YYYY"),
        ("Summer 2020 – Fall 2020", "2020-06", "2020-09", False, "Season YYYY"),
        ("Aug '19 — Dec '21", "2019-08", "2021-12", False, "Mon 'YY"),
        ("2019/04 - 2020/11", "2019-04", "2020-11", False, "YYYY/MM"),
    ],
)
def test_date_ranges_in_many_formats(
    text: str, start: str, end: str | None, current: bool, fmt: str
) -> None:
    found = find_range(text)
    assert found is not None
    assert found.start is not None and found.start.iso() == start
    assert (found.end.iso() if found.end else None) == end
    assert found.current is current
    assert found.start_format == fmt


def test_strip_range_leaves_the_rest_of_the_line() -> None:
    line = "Senior Analyst, Northwind | Jan 2018 - Feb 2021"
    found = find_range(line)
    assert found is not None
    assert strip_range(line, found) == "Senior Analyst, Northwind"


def test_word_file_keeps_where_text_sat() -> None:
    doc = extract(messy_docx(), "x.docx")
    where = {b.text: b.where for b in doc.blocks}
    assert where[next(t for t in where if t.startswith("Jordan Rivera"))] == "header"
    assert where["Certifications: CPA (Ohio), 2017"] == "text_box"
    assert where["Excel, SQL, Python"] == "table"
    assert doc.facts.tables == 1 and doc.facts.text_boxes == 1
    bullets = {b.bullet_char for b in doc.blocks if b.is_bullet}
    assert bullets == {"•", "-", "▪"}
    assert "Arial" in doc.facts.fonts and "Calibri" in doc.facts.fonts


def test_roles_titles_employers_and_dates(messy: ImportResult) -> None:
    got = [(r.title, r.organization, r.dates.raw if r.dates else None) for r in messy.roles]
    assert got == [
        ("Senior Financial Analyst", "Northwind Logistics", "03/2021 – Present"),
        ("Financial Analyst", "Contoso Health", "Jan 2018 - Feb 2021"),
        ("Volunteer Treasurer", "Riverside Food Bank", "Jun 2019 – Dec 2020"),
        ("Staff Accountant", "Fabrikam Inc.", "2014 to 2016"),
    ]
    assert [r.title_first for r in messy.roles] == [True, False, True, True]
    assert [len(r.bullets) for r in messy.roles] == [3, 3, 1, 2]


def test_contact_details_are_found_in_the_page_header(messy: ImportResult) -> None:
    contact = messy.contact
    assert contact.name == "Jordan Rivera"
    assert contact.emails == ["jordan.rivera@example.com"]
    assert contact.phones == ["(614) 555-0182"]
    assert contact.street_address is True


def test_audit_finds_every_planted_problem(messy: ImportResult) -> None:
    planted = {
        "ats.contact_in_header",
        "ats.text_boxes",
        "ats.tables",
        "consistency.tense",
        "consistency.date_formats",
        "consistency.date_separators",
        "consistency.bullets",
        "consistency.role_order",
        "consistency.end_punctuation",
        "consistency.fonts",
        "consistency.heading_case",
        "dates.year_only",
        "dates.overlap",
        "dates.gap",
        "content.objective",
        "content.references",
        "content.weak_openers",
        "content.first_person",
        "content.duplicates",
        "content.cliches",
        "content.no_numbers",
        "contact.street_address",
        "contact.no_linkedin",
        "file.tailored_name",
        "file.version_name",
    }
    assert planted <= rules(messy)
    severities = [f.severity for f in messy.findings]
    assert severities == sorted(severities, key=["fix", "improve", "note"].index)


def test_tense_slip_points_at_the_line(messy: ImportResult) -> None:
    tense = next(f for f in messy.findings if f.rule == "consistency.tense")
    assert [loc.excerpt for loc in tense.locations] == [
        "Manage accounts payable reconciliations for $40M in annual spend."
    ]


def test_gap_is_measured_between_roles(messy: ImportResult) -> None:
    gap = next(f for f in messy.findings if f.rule == "dates.gap")
    assert gap.title == "A 12-month gap"
    assert "Dec 2016" in gap.detail and "Jan 2018" in gap.detail


def test_tidy_pdf_has_nothing_to_fix() -> None:
    result = import_resume(clean_pdf(), "Avery Chen Resume.pdf", today=TODAY)
    assert [f.rule for f in result.findings if f.severity != "note"] == []
    assert [(r.title, r.organization) for r in result.roles] == [
        ("Product Manager", "Tailspin Toys"),
        ("Associate Product Manager", "Adventure Works"),
    ]
    first = result.roles[0].bullets[0].text
    assert first.endswith("in its first year.")


def test_two_column_pdf_reads_each_column_in_order() -> None:
    result = import_resume(two_column_pdf(), "Sam Okafor Resume.pdf", today=TODAY)
    assert result.facts.columns == 2
    assert "ats.columns" in rules(result)
    assert result.contact.name == "Sam Okafor"
    assert [(r.title, r.organization, len(r.bullets)) for r in result.roles] == [
        ("Account Executive", "Litware Inc.", 2),
        ("Sales Development Rep", "Proseware", 2),
    ]


def test_plain_text_resume() -> None:
    result = import_resume(messy_text().encode(), "resume.txt", today=TODAY)
    assert len(result.roles) == 4
    assert result.contact.name == "Jordan Rivera"
    assert "consistency.tense" in rules(result)


def test_cards_keep_the_resume_wording(messy: ImportResult) -> None:
    kinds = [c.kind for c in messy.cards]
    assert kinds.count("role") == 4
    assert kinds.count("accomplishment") == 9
    assert {"story", "skill", "education", "credential"} <= set(kinds)
    for card in messy.cards:
        MainContent.model_validate(card.content.model_dump())

    spend = next(c for c in messy.cards if "$40M" in c.content.framing.headline)
    assert spend.content.facts["employer"] == "Contoso Health"
    assert spend.content.facts["figures"] == ["$40M"]
    assert spend.content.facts["start"] == "2018-01"
    assert "consistency.tense" in spend.findings

    fabrikam = next(
        c
        for c in messy.cards
        if c.kind == "role" and c.content.facts["employer"] == "Fabrikam Inc."
    )
    assert fabrikam.needs_check == ["Which months did this role start and end?"]


def test_unreadable_files_are_refused() -> None:
    with pytest.raises(UnsupportedFileError, match=r"\.doc"):
        extract(b"\xd0\xcf\x11\xe0" + b"\x00" * 100, "old.doc")
    with pytest.raises(UnsupportedFileError):
        extract(b"\x89PNG\r\n\x1a\n" + bytes(range(256)), "photo.png")
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("notes.txt", "hello")
    with pytest.raises(UnsupportedFileError, match="zip"):
        extract(archive.getvalue(), "notes.zip")
    with pytest.raises(UnsupportedFileError, match="5 MB"):
        extract(b"x" * (5 * 1024 * 1024 + 1), "big.txt")


@pytest.fixture(scope="module")
def consultant() -> ImportResult:
    return import_resume(consultant_docx(), "Riley Park Resume.docx", today=TODAY)


def test_client_engagements_sit_under_the_agency(consultant: ImportResult) -> None:
    got = [(r.title, r.organization, r.client, r.parent_ref) for r in consultant.roles]
    assert got == [
        ("Senior Analyst", "Fabrikam Inc.", None, None),
        ("Consultant", "Contoso Staffing", None, None),
        ("Data Scientist", "Contoso Staffing", "Northwind Health", "role-2"),
        ("Analytics Lead", "Contoso Staffing", "Tailspin Bank", "role-2"),
    ]
    northwind = next(
        c for c in consultant.cards if c.kind == "role" and "Northwind" in str(c.content.facts)
    )
    assert northwind.content.facts["employer"] == "Contoso Staffing"
    assert northwind.content.facts["client"] == "Northwind Health"
    assert northwind.needs_check == [
        "When did your work for Northwind Health start and end (within January 2019 – June 2023)?"
    ]


def test_workstream_labels_stay_inside_their_role(consultant: ImportResult) -> None:
    fabrikam = consultant.roles[0]
    assert [b.group for b in fabrikam.bullets] == ["Pricing", "Pricing", "Forecasting"]
    card = next(c for c in consultant.cards if "demand forecast" in c.content.framing.headline)
    assert card.content.facts["workstream"] == "Forecasting"


def test_paragraph_roles_become_one_card_per_sentence(consultant: ImportResult) -> None:
    northwind = [c for c in consultant.cards if c.role_ref == "role-3" and c.kind != "role"]
    assert [c.content.framing.headline for c in northwind] == [
        "Built a reminder model that cut patient no-shows 25% across 14 clinics.",
        "Led the rollout with clinic managers and trained 30 front-desk staff.",
    ]


def test_contractor_resume_audit(consultant: ImportResult) -> None:
    assert consultant.contact.name == "Riley Park"
    assert consultant.contact.phones == ["(303) 555 - 0199"]
    assert {
        "file.classification_marking",
        "ats.contact_in_text_boxes",
        "ats.misfiled_summary",
        "ats.large_image",
        "consistency.figures",
        "consistency.tense",
        "dates.undated_engagements",
        "content.paragraphs",
        "content.skill_spelling",
        "layout.small_text",
        "contact.phone_format",
    } <= rules(consultant)
    assert "dates.missing" not in rules(consultant)
    assert "content.no_bullets" not in rules(consultant)

    figures = next(f for f in consultant.findings if f.rule == "consistency.figures")
    assert "30%" in figures.detail and "25%" in figures.detail
    tense = next(f for f in consultant.findings if f.rule == "consistency.tense")
    assert [loc.excerpt for loc in tense.locations] == [
        "Provide weekly risk dashboards to the credit committee, covering 2 portfolios worth "
        "$1.2B in loans."
    ]
    spelling = next(f for f in consultant.findings if f.rule == "content.skill_spelling")
    assert '"Tableu" (usually "Tableau")' in spelling.detail


def test_markings_from_word_custom_properties() -> None:
    custom = (
        b'<Properties><property name="ClassificationContentMarkingHeaderText">'
        b"<vt:lpwstr>CONFIDENTIAL</vt:lpwstr></property>"
        b'<property name="MSIP_Label_1234_Name"><vt:lpwstr>Internal</vt:lpwstr></property>'
        b"</Properties>"
    )
    assert _markings(custom) == ["CONFIDENTIAL", "Internal"]


def test_sentences_keep_abbreviations_whole() -> None:
    text = "Advised the U.S. Department of State on KPIs.  Led 3 analysts, e.g. on RCA. Done."
    assert sentences(text) == [
        "Advised the U.S. Department of State on KPIs.",
        "Led 3 analysts, e.g. on RCA.",
        "Done.",
    ]


def test_skill_spelling() -> None:
    assert spelling_fixes(["AWS Sagemaker", "Milvius", "LangChain/LangGraph", "R", "Llama"]) == [
        ("Sagemaker", "SageMaker"),
        ("Milvius", "Milvus"),
    ]
