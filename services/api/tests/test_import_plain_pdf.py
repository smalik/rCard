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
