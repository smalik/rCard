"""PDFs printed from a web page with no styling, as resume sets scraped from builder
sites are: one plain font, headings set like any other line, bullets drawn rather than
typed, and characters mangled on the way. Everyone here is made up."""

from datetime import date
from typing import Any

from fpdf import FPDF

from plytos_api.imports.extract import clean, extract
from plytos_api.imports.fidelity.layouts import PDF
from plytos_api.imports.fidelity.truth import MORGAN
from plytos_api.imports.pipeline import import_resume

TODAY = date(2026, 11, 1)
WEB_PRINT = next(lay for lay in PDF if lay.name == "pdf-web-print")


def plain_pdf(lines: list[tuple[str, bool]]) -> bytes:
    """Lines in one plain font, each with a drawn dot before it or not."""
    pdf: Any = FPDF(format="A4")
    pdf.add_page()
    pdf.set_font("Times", "", 11.4)
    y = 12.0
    for text, dotted in lines:
        if dotted:
            pdf.ellipse(16.6, y + 1.7, 1.06, 1.06, style="F")
        pdf.set_xy(20.2 if dotted else 11.7, y)
        pdf.cell(0, 4.2, text)
        y += 4.23
    return bytes(pdf.output())


def test_bullets_drawn_as_dots_are_bullets() -> None:
    doc = extract(WEB_PRINT.render(MORGAN), "resume.pdf")
    bullets = [b for b in doc.blocks if b.is_bullet]
    items = sum(len(p.items) for e in MORGAN.employments for p in e.positions)
    assert len(bullets) >= items
    assert all(b.bullet_char == "•" for b in bullets)


def test_a_plain_heading_is_never_joined_to_the_line_above() -> None:
    full = (
        "Scheduling, inventory control, visual merchandising, vendor relations, hiring "
        "and training,"
    )
    doc = extract(
        plain_pdf([(full, False), ("Professional Experience", False), ("Store Manager", False)]),
        "resume.pdf",
    )
    assert [b.text for b in doc.blocks][1:] == ["Professional Experience", "Store Manager"]


def test_characters_mangled_on_the_way_are_put_back() -> None:
    assert clean("Didnâ€™t miss a deadline") == "Didn’t miss a deadline"
    assert clean("a â€“ b") == "a – b"
    # A wide dash that lost its last byte, between two words: a separator.
    assert clean("Company Name ï¼​ City , State") == "Company Name - City , State"
    assert clean("Fabrikam ｜ Chicago") == "Fabrikam | Chicago"
    # Text that only looks mangled stays as it is.
    assert clean("João São Paulo") == "João São Paulo"


def read(text: str) -> Any:
    return import_resume(text.encode(), "resume.txt", today=TODAY, reader=None)


def test_a_date_before_the_school_is_not_part_of_its_name() -> None:
    result = read(
        "Pat Lee\nEducation\n"
        "Bachelor of Science : Business Administration , May 2015 Lakeshore College\n"
    )
    [card] = [c for c in result.cards if c.kind == "education"]
    assert card.content.facts["institution"] == "Lakeshore College"
    assert card.content.facts["degree"] == "Bachelor of Science : Business Administration"


def test_a_high_school_diploma_is_a_degree() -> None:
    result = read("Pat Lee\nEducation\nHigh School Diploma, Lincoln High School, 2008\n")
    [card] = [c for c in result.cards if c.kind == "education"]
    assert card.content.facts["degree"] == "High School Diploma"
    assert card.content.facts["institution"] == "Lincoln High School"


def test_a_sentence_under_a_dated_title_is_what_the_job_was() -> None:
    result = read(
        "Pat Lee\nExperience\nStore Manager\nMarch 2019 to Current Fabrikam Retail - Chicago, IL\n"
        "Ran a store of 40 people.\n• Grew sales 12% in two years.\n"
    )
    [title] = [c for c in result.cards if c.kind == "position"]
    assert title.content.facts["title"] == "Store Manager"
    assert title.content.framing.body == "Ran a store of 40 people."
    assert [c.content.framing.headline for c in result.cards if c.kind == "accomplishment"] == [
        "Grew sales 12% in two years."
    ]


def test_a_job_read_as_one_endless_line_does_not_stop_the_import() -> None:
    endless = " ".join(["Handled the store's weekly ordering and stock counts"] * 120)
    result = read(f"Pat Lee\nExperience\nStore Manager, Fabrikam, 2019 - 2021\n• {endless}\n")
    assert all(len(c.content.framing.body) <= 5000 for c in result.cards)


def test_a_very_tall_scanned_page_is_read_in_page_sized_pieces() -> None:
    import io

    import pdfplumber
    from PIL import Image

    from plytos_api.imports.fidelity.layouts import write_pdf
    from plytos_api.imports.fidelity.truth import SAM

    page = write_pdf(SAM, PDF[0].style)
    with pdfplumber.open(io.BytesIO(page)) as doc:
        shot = doc.pages[0].to_image(resolution=72).original.convert("L")
    # One endless page: the same page three times over, as a long screenshot is.
    tall = Image.new("L", (shot.width, shot.height * 3), 255)
    for k in range(3):
        tall.paste(shot, (0, shot.height * k))
    out = io.BytesIO()
    tall.save(out, "PDF", resolution=72)
    doc = extract(out.getvalue(), "resume.pdf")
    assert doc.facts.scanned_pages == [1]
    assert len(doc.images) >= 3
    for image in doc.images:
        with Image.open(io.BytesIO(image.data)) as piece:
            assert piece.height <= piece.width * 1.7


def test_a_school_without_college_in_its_name_is_found_before_its_city() -> None:
    result = read("Pat Lee\nEducation\nBachelors : Biology , 2010 Penn State - Erie, PA\n")
    [card] = [c for c in result.cards if c.kind == "education"]
    assert card.content.facts["institution"] == "Penn State"
    assert card.content.facts["degree"] == "Bachelors : Biology"


def test_accomplishments_with_a_colon_inside_a_job_stay_in_the_job() -> None:
    result = read(
        "Pat Lee\nExperience\nStore Manager\nMarch 2019 to Current Fabrikam Retail - Chicago, IL\n"
        "Accomplishments:\n• Grew sales 12% in two years.\n"
        "Assistant Manager\n01/2016 to 02/2019 Fabrikam Retail - Chicago, IL\n"
        "• Trained nine new cashiers.\n"
    )
    titles = [c.content.facts.get("title") for c in result.cards if c.kind == "position"]
    assert titles == ["Store Manager", "Assistant Manager"]
    grew = next(c for c in result.cards if c.content.framing.headline.startswith("Grew"))
    assert "workstream" not in grew.content.facts


def test_a_date_range_set_over_three_lines_is_one() -> None:
    doc = extract(
        plain_pdf(
            [
                ("Experience", False),
                ("May 2019", False),
                ("to", False),
                ("January 2021", False),
                ("Store Manager", False),
            ]
        ),
        "resume.pdf",
    )
    assert [b.text for b in doc.blocks] == [
        "Experience",
        "May 2019 to January 2021",
        "Store Manager",
    ]


def test_a_bullet_typed_against_its_first_word_is_a_bullet() -> None:
    from plytos_api.imports.extract import split_bullet

    assert split_bullet("•Grew sales 12%.") == ("Grew sales 12%.", "•")
    assert split_bullet("-Trained nine cashiers.") == ("Trained nine cashiers.", "-")
    # A figure or a word that starts with a dash is no bullet.
    assert split_bullet("-2% shrink")[1] is None
    assert split_bullet("-based pricing")[1] is None
    doc = extract("Experience\n•Grew sales 12% in two years.\n".encode(), "resume.txt")
    [line] = [b for b in doc.blocks if b.is_bullet]
    assert line.text == "Grew sales 12% in two years."


def _jobs(result: Any) -> list[tuple[str, Any, Any, int]]:
    """Each position as (kind, title, client, how many accomplishments sit under it)."""
    under = {
        c.ref: sum(1 for d in result.cards if d.parent_ref == c.ref and d.kind == "accomplishment")
        for c in result.cards
    }
    return [
        (c.kind, c.content.facts.get("title"), c.content.facts.get("client"), under[c.ref])
        for c in result.cards
        if c.kind in ("position", "engagement")
    ]


def test_an_employer_under_a_dated_title_is_no_client() -> None:
    result = read(
        "Pat Lee\nExperience\nNovember 2009 to July 2012 Senior Flight Attendant\n"
        "Fabrikam Airlines\n• Served 180 passengers a flight.\n• Trained six new crew.\n"
    )
    assert _jobs(result) == [("position", "Senior Flight Attendant", None, 2)]
    employment = next(c for c in result.cards if c.kind == "employment")
    assert employment.content.facts.get("employer") == "Fabrikam Airlines"


def test_a_title_and_employer_under_dates_alone_are_the_job() -> None:
    result = read(
        "Pat Lee\nExperience\n2015 to 2017\nSenior Engineer, Contoso Systems\n"
        "• Cut build times in half.\n"
    )
    assert _jobs(result) == [("position", "Senior Engineer", None, 1)]


def test_a_client_under_a_title_under_its_employer_is_still_a_client() -> None:
    result = read(
        "Pat Lee\nExperience\nBrightline Partners\tJun 2010 – Feb 2014\n"
        "Consultant (Jun 2010 – Feb 2014)\nFabrikam Health\n• Mapped freight for 120 suppliers.\n"
    )
    kinds = [(kind, client, n) for kind, _, client, n in _jobs(result)]
    assert kinds == [("position", None, 0), ("engagement", "Fabrikam Health", 1)]


def test_years_throughout_ask_no_months() -> None:
    years = read(
        "Pat Lee\nExperience\nStore Manager, Fabrikam Retail, 2019 – 2021\n• Grew sales 12%.\n"
        "Cashier, Contoso Foods Inc., 2016 – 2019\n• Trained nine new cashiers.\n"
    )
    assert not any("months" in q for c in years.cards for q in c.needs_check)
    # One title in years among titles with months may have lost them.
    mixed = read(
        "Pat Lee\nExperience\nStore Manager, Fabrikam Retail, March 2019 – May 2021\n"
        "• Grew sales 12%.\nCashier, Contoso Foods Inc., 2016 – 2019\n"
        "• Trained nine new cashiers.\n"
    )
    asked = [c for c in mixed.cards if any("months" in q for q in c.needs_check)]
    assert [c.content.facts.get("title") for c in asked] == ["Cashier"]


def test_a_short_sentence_in_a_paragraph_is_kept() -> None:
    result = read(
        "Pat Lee\nExperience\nCashier, Contoso Foods Inc., March 2016 – May 2019\n"
        "Processed returns and exchanges. Trained four new cashiers on the register.\n"
    )
    done = [c.content.framing.headline for c in result.cards if c.kind == "accomplishment"]
    assert done == [
        "Processed returns and exchanges.",
        "Trained four new cashiers on the register.",
    ]


def test_a_title_and_employer_run_together_are_told_apart() -> None:
    result = read(
        "Pat Lee\nExperience\n2015 to 2017\nSenior Software Engineer Contoso Systems\n"
        "• Cut build times in half.\n2012 to 2015\nFabrikam Bank Senior Analyst\n"
        "• Built the loan dashboard.\n2010 to 2012\nDirector of Health Services\n"
        "• Opened two clinics.\n"
    )
    jobs = [
        (c.content.facts.get("title"), by.content.facts.get("employer"))
        for by in result.cards
        if by.kind == "employment"
        for c in result.cards
        if c.kind == "position" and c.parent_ref == by.ref
    ]
    assert jobs[:2] == [
        ("Senior Software Engineer", "Contoso Systems"),
        ("Senior Analyst", "Fabrikam Bank"),
    ]
    # Joined by "of", the words are one name, whichever it is.
    assert "Director of Health Services" in jobs[2]


def test_an_employer_line_with_a_place_no_rule_knows_is_still_the_employer() -> None:
    for place in ["Toronto, Ontario", "Springfield"]:
        result = read(
            f"Pat Lee\nExperience\nFabrikam Retail, {place}\tMar 2016 – Present\n"
            "Sales Associate\tMar 2016 – Present\n• Greeted customers.\n"
        )
        [employment] = [c for c in result.cards if c.kind == "employment"]
        assert employment.content.facts.get("employer") == "Fabrikam Retail"
        assert employment.content.facts.get("location") == place
        titles = [c.content.facts.get("title") for c in result.cards if c.kind == "position"]
        assert titles == ["Sales Associate"]


def test_a_dated_title_line_is_not_divided_when_its_employer_follows() -> None:
    result = read(
        "Pat Lee\nExperience\nSenior Engineer Health Services Oct 2015 to Current\n"
        "Contoso Systems\n• Cut build times in half.\n"
    )
    jobs = [
        (c.content.facts.get("title"), by.content.facts.get("employer"))
        for by in result.cards
        if by.kind == "employment"
        for c in result.cards
        if c.kind in ("position", "engagement") and c.parent_ref == by.ref
    ]
    assert jobs == [("Senior Engineer Health Services", "Contoso Systems")]
