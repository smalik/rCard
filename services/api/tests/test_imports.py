"""Resume import: reading, splitting, auditing and proposing cards.

These run on made-up resumes (tests/resume_samples.py), never a real person's.
"""

import inspect
import io
import re
import zipfile
from datetime import date

import pytest
from docx import Document

from plytos_api.cards.model import MainContent
from plytos_api.imports import audit as audit_module
from plytos_api.imports.audit import CARD_RULES
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


# Every rule the audit can raise, read from its source.
ALL_RULES = set(re.findall(r'_finding\(\s*"([a-z]+\.[a-z_]+)"', inspect.getsource(audit_module)))


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
        # Files converted from PDF that lost the dash between two dates.
        ("Jan 2018  Dec 2020", "2018-01", "2020-12", False, "Mon YYYY"),
        ("1/2018  12/2020", "2018-01", "2020-12", False, "M/YYYY"),
        ("Jan 2018  Present", "2018-01", None, True, "Mon YYYY"),
        ("Sales Manager 20182020", "2018", "2020", False, "YYYY"),
        ("Fabrikam 2019/---", "2019", None, True, "YYYY"),
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


def test_two_dates_with_only_a_gap_are_a_range_only_in_order() -> None:
    found = find_range("Lakeshore College 2015  2012")
    assert found is not None and found.separator is None
    assert found.start is not None and found.start.iso() == "2012"


def converted_docx(lines: list[str]) -> bytes:
    """A Word file the way PDF-to-Word converters write one: a paragraph whose lines
    are joined by line breaks, bullets' marks lost."""
    document = Document()
    document.add_paragraph("Pat Lee")
    document.add_paragraph("Experience")
    paragraph = document.add_paragraph()
    for i, line in enumerate(lines):
        run = paragraph.add_run(line)
        if i < len(lines) - 1:
            run.add_break()
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def test_a_bullet_whose_mark_was_lost_in_conversion_is_still_an_item() -> None:
    data = converted_docx(
        [
            "Store Manager, Fabrikam Retail",
            "Jan 2018  Dec 2020",
            " Grew sales 12% in two years by reworking the floor plan",
            " Trained nine new cashiers",
            "Fabrikam Outlet, Springfield",
        ]
    )
    blocks = extract(data, "resume.docx").blocks
    marked = [(b.text, b.is_bullet, b.bullet_char) for b in blocks[2:]]
    assert marked == [
        ("Store Manager, Fabrikam Retail", False, None),
        ("Jan 2018  Dec 2020", False, None),
        ("Grew sales 12% in two years by reworking the floor plan", True, ""),
        ("Trained nine new cashiers", True, ""),
        ("Fabrikam Outlet, Springfield", False, None),
    ]
    result = import_resume(data, "resume.docx", today=TODAY, reader=None)
    items = [c.content.framing.headline for c in result.cards if c.kind == "accomplishment"]
    assert items == [
        "Grew sales 12% in two years by reworking the floor plan",
        "Trained nine new cashiers",
    ]


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


def test_findings_say_whether_they_travel_with_the_cards(messy: ImportResult) -> None:
    about = {f.rule: f.about for f in messy.findings}
    # Wording and dates come along into the cards.
    assert about["consistency.tense"] == "cards"
    assert about["content.weak_openers"] == "cards"
    assert about["dates.overlap"] == "cards"
    # Formatting and layout belong to this file only.
    assert about["consistency.date_formats"] == "document"
    assert about["consistency.bullets"] == "document"
    assert about["ats.tables"] == "document"
    assert about["file.tailored_name"] == "document"
    assert CARD_RULES <= ALL_RULES


def test_tense_slip_points_at_the_line(messy: ImportResult) -> None:
    tense = next(f for f in messy.findings if f.rule == "consistency.tense")
    assert [loc.excerpt for loc in tense.locations] == [
        "Manage accounts payable reconciliations for $40M in annual spend."
    ]


def test_gap_is_measured_between_roles(messy: ImportResult) -> None:
    gap = next(f for f in messy.findings if f.rule == "dates.gap")
    assert gap.title == "A 12-month gap"
    assert "Dec 2016" in gap.detail and "Jan 2018" in gap.detail


def test_a_gap_reads_as_it_is_said() -> None:
    assert [audit_module._article(n) for n in (7, 8, 11, 12, 18, 24, 80)] == [
        "a",
        "an",
        "an",
        "a",
        "an",
        "a",
        "an",
    ]


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
    assert kinds.count("employment") == 4
    assert kinds.count("position") == 4
    assert kinds.count("accomplishment") == 9
    assert "role" not in kinds
    assert {"story", "skill", "education", "credential"} <= set(kinds)
    for card in messy.cards:
        MainContent.model_validate(card.content.model_dump())

    by_ref = {c.ref: c for c in messy.cards}
    spend = next(c for c in messy.cards if "$40M" in c.content.framing.headline)
    # The accomplishment holds its own facts; the title and employer sit above it.
    assert spend.content.facts == {}
    assert "consistency.tense" in spend.findings
    position = by_ref[spend.parent_ref or ""]
    assert position.kind == "position"
    assert position.content.facts["start"] == "2018-01"
    employer = by_ref[position.parent_ref or ""]
    assert employer.kind == "employment"
    assert employer.content.facts["employer"] == "Contoso Health"

    fabrikam = next(
        c
        for c in messy.cards
        if c.kind == "position"
        and by_ref[c.parent_ref or ""].content.facts.get("employer") == "Fabrikam Inc."
    )
    assert fabrikam.needs_check == ["Which months did you start and finish in this title?"]


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
    by_ref = {c.ref: c for c in consultant.cards}
    northwind = next(
        c
        for c in consultant.cards
        if c.kind == "engagement" and "Northwind" in str(c.content.facts)
    )
    assert northwind.content.facts["client"] == "Northwind Health"
    assert "employer" not in northwind.content.facts
    consultant_role = by_ref[northwind.parent_ref or ""]
    assert (consultant_role.kind, consultant_role.content.facts["title"]) == (
        "position",
        "Consultant",
    )
    agency = by_ref[consultant_role.parent_ref or ""]
    assert agency.content.facts["employer"] == "Contoso Staffing"
    assert northwind.needs_check == [
        "When did your work for Northwind Health start and end (within January 2019 – June 2023)?"
    ]
    # One agency employment holds the consultant role and both client engagements.
    assert [e.organization for e in consultant.employments] == ["Fabrikam Inc.", "Contoso Staffing"]
    assert consultant.employments[1].role_refs == ["role-2", "role-3", "role-4"]


def test_workstream_labels_stay_inside_their_role(consultant: ImportResult) -> None:
    fabrikam = consultant.roles[0]
    assert [b.group for b in fabrikam.bullets] == ["Pricing", "Pricing", "Forecasting"]
    card = next(c for c in consultant.cards if "demand forecast" in c.content.framing.headline)
    assert card.content.facts["workstream"] == "Forecasting"


def test_paragraph_roles_become_one_card_per_sentence(consultant: ImportResult) -> None:
    northwind = [
        (c.content.framing.headline, c.needs_check)
        for c in consultant.cards
        if c.role_ref == "role-3" and c.kind == "accomplishment"
    ]
    assert northwind == [
        ("Built a reminder model that cut patient no-shows 25% across 14 clinics.", []),
        ("Led the rollout with clinic managers and trained 30 front-desk staff.", []),
        # The highlight at the top names the client, so it's proposed under that work.
        (
            "Cut patient no-shows ~30% at Northwind Health with a reminder model.",
            ["Is this from your work at Northwind Health?"],
        ),
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


def test_an_agency_tenure_is_the_one_position_written_over_its_client_work() -> None:
    """The consultant line at Contoso Staffing, dated January 2019 to June 2023, heads
    two client engagements, and the reader gave the employer no line of its own: the
    position's dates are the tenure as written, not worked out from the titles."""
    from plytos_api.imports.career import settle_employments
    from plytos_api.imports.dates import find_range
    from plytos_api.imports.model import Employment, Role

    texts = {
        3: "Consultant, Contoso Staffing - January 2019 – June 2023",
        4: "Data Scientist, Northwind Health",
        6: "Analytics Lead, Tailspin Bank",
    }
    roles = [
        Role(
            ref="role-1",
            title="Consultant",
            organization="Contoso Staffing",
            dates=find_range(texts[3]),
            header_blocks=[3],
            employment_ref="employment-1",
        ),
        Role(
            ref="role-2",
            title="Data Scientist",
            client="Northwind Health",
            parent_ref="role-1",
            header_blocks=[4],
            employment_ref="employment-1",
        ),
        Role(
            ref="role-3",
            title="Analytics Lead",
            client="Tailspin Bank",
            parent_ref="role-1",
            header_blocks=[6],
            employment_ref="employment-1",
        ),
    ]
    [contoso] = settle_employments([Employment(ref="employment-1")], roles, texts)
    assert contoso.tenure_written
    assert contoso.dates is not None and contoso.dates.raw == "January 2019 – June 2023"


def test_a_year_shared_without_months_isnt_an_overlap() -> None:
    text = "\n".join(
        [
            "Sam Patel",
            "sam.patel@example.com",
            "EXPERIENCE",
            "Data Architect, Contoso Ltd., MAR 2005 – Present",
            "• Designed the data platform for 3 business units.",
            "Database Administrator, Fabrikam Inc., 2003 – 2005",
            "• Kept 40 databases running.",
            "Database Administrator, Tailspin Toys, 2001 – 2003",
            "• Ran nightly backups.",
            "Analyst, Northwind Traders, June 2000 – June 2002",
            "• Built reports.",
        ]
    )
    result = import_resume(text.encode(), "sam.txt", today=TODAY)
    pairs = [
        sorted(loc.excerpt.split(",")[1].strip() for loc in f.locations)
        for f in result.findings
        if f.rule == "dates.overlap"
    ]
    # Only the months that really overlap are flagged.
    assert pairs == [["Northwind Traders", "Tailspin Toys"]]


def _short_resume(*bullets: str) -> ImportResult:
    text = "\n".join(
        [
            "Avery Chen",
            "avery.chen@example.com",
            "EXPERIENCE",
            "Analyst, Contoso Ltd., Jan 2020 – Present",
            *(f"• {b}" for b in bullets),
        ]
    )
    return import_resume(text.encode(), "avery.txt", today=TODAY)


def test_a_cliche_is_a_whole_word_not_part_of_a_product() -> None:
    product = _short_resume("Moved 40 teams onto Microsoft Dynamics 365.")
    assert "content.cliches" not in rules(product)
    cliche = _short_resume("Dynamic analyst who cut reporting time by 30%.")
    assert "content.cliches" in rules(cliche)


def test_notes_left_in_the_text_are_flagged() -> None:
    result = _short_resume(
        "Grew renewals XX% at AlgoNorth (confirm employer).",
        "Built the TBD pipeline for 12 teams.",
        "Supported Check Point Software (Contract) firewall rollouts for 30 sites.",
        "Launched add-on sales (Add-on bundle) worth $1M.",
    )
    [notes] = [f for f in result.findings if f.rule == "content.placeholder"]
    assert notes.severity == "fix" and notes.about == "cards"
    assert [loc.block for loc in notes.locations] == [4, 5]


def test_an_objective_under_another_heading_is_found_without_a_crash() -> None:
    from plytos_api.imports.audit import audit
    from plytos_api.imports.extract import extract as read
    from plytos_api.imports.model import Contact, ParsedResume, Section

    text = "Kai Ito\nkai@example.com\nPROFILE\nSeeking a role in data analysis."
    doc = read(text.encode(), "kai.txt")
    parsed = ParsedResume(
        contact=Contact(name="Kai Ito", blocks=[0, 1]),
        sections=[
            Section(
                kind="summary", holds="objective", heading="PROFILE", heading_block=2, blocks=[3]
            )
        ],
        roles=[],
    )
    found = {f.rule: f for f in audit(doc, parsed, today=TODAY)}
    assert [loc.block for loc in found["content.objective"].locations] == [2]
