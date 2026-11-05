"""Writes a made-up career out as a resume file, in one of many layouts.

Each layout is a set of choices people really make (`Style`): employer or title
first, how dates are written, Word bullets or typed ones, a sidebar, contact
details in the page header, a summary under the Experience heading, talks
grouped under years. The same career written in every layout gives answers
that can be compared like for like.

Word files are written with python-docx. PDFs are written directly with fpdf2,
and, where LibreOffice is installed, also by saving each Word layout as a PDF
the way people do. A scan is a PDF turned into page pictures with no text
layer, which only Claude can read.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal

from docx import Document
from docx.enum.text import WD_TAB_ALIGNMENT
from docx.shared import Inches, Pt

from plytos_api.imports.fidelity.truth import PRESENT, Career, Employment, Group, Position

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

Kind = Literal["docx", "pdf", "scan", "pdf-from-word"]


@dataclass(frozen=True)
class Style:
    # web_print: each title on its own line, then "dates employer - place".
    header: Literal["employer_first", "title_first", "one_line", "web_print"] = "employer_first"
    dates: Literal["mon", "num", "year"] = "mon"
    bullets: Literal["word", "typed", "paragraph"] = "word"
    contact: Literal["body", "page_header"] = "body"
    summary: Literal["section", "in_experience"] = "section"
    highlights: bool = True
    talks: Literal["inline", "by_year"] = "inline"
    sidebar: bool = False
    # PDF only: a narrow column and a larger font, so bullets wrap onto more lines.
    wrap: bool = False
    # PDF only: a web page printed without its stylesheet, as a browser prints it: one
    # plain font throughout, headings set like any other line, bullets drawn as dots.
    plain: bool = False


@dataclass(frozen=True)
class Layout:
    name: str
    kind: Kind
    style: Style
    note: str

    @property
    def years_only(self) -> bool:
        return self.style.dates == "year"

    @property
    def needs_ai(self) -> bool:
        return self.kind == "scan"

    def render(self, career: Career) -> bytes:
        if self.kind == "docx":
            return write_docx(career, self.style)
        if self.kind == "pdf":
            return write_pdf(career, self.style)
        if self.kind == "scan":
            return scan(write_pdf(career, self.style))
        pdf = word_to_pdf(write_docx(career, self.style))
        if pdf is None:
            raise RuntimeError("LibreOffice isn't installed")
        return pdf

    @property
    def suffix(self) -> str:
        return ".docx" if self.kind == "docx" else ".pdf"


WORD: list[Layout] = [
    Layout("word-classic", "docx", Style(), "Employer line with tenure, titles in italics"),
    Layout(
        "word-title-first",
        "docx",
        Style(header="title_first"),
        "Title, then employer, on one line per title",
    ),
    Layout(
        "word-one-line",
        "docx",
        Style(header="one_line", dates="num", bullets="typed"),
        "Title, employer, place | dates, typed bullets",
    ),
    Layout(
        "word-header-contact", "docx", Style(contact="page_header"), "Contact in the page header"
    ),
    Layout("word-sidebar", "docx", Style(sidebar=True), "A two-column table with a sidebar"),
    Layout("word-typed-bullets", "docx", Style(bullets="typed"), "Bullets typed as characters"),
    Layout(
        "word-paragraphs",
        "docx",
        Style(bullets="paragraph", highlights=False),
        "Each job written as a paragraph",
    ),
    Layout(
        "word-summary-in-experience",
        "docx",
        Style(summary="in_experience", highlights=False),
        "The summary under the Experience heading",
    ),
    Layout(
        "word-year-dates",
        "docx",
        Style(dates="year", talks="by_year"),
        "Years only, talks grouped under years",
    ),
]

PDF: list[Layout] = [
    Layout("pdf-classic", "pdf", Style(), "Employer line, dates on the right"),
    Layout("pdf-title-first", "pdf", Style(header="title_first"), "Title first"),
    Layout("pdf-one-line", "pdf", Style(header="one_line", dates="num"), "One line per title"),
    Layout("pdf-two-column", "pdf", Style(sidebar=True), "A sidebar column on the left"),
    Layout("pdf-wrapped", "pdf", Style(wrap=True), "Long bullets wrapping onto more lines"),
    Layout(
        "pdf-no-breaks",
        "pdf",
        Style(bullets="paragraph", highlights=False),
        "Line breaks lost: each job's lines run together",
    ),
    Layout(
        "pdf-year-dates", "pdf", Style(dates="year", talks="by_year"), "Years only, talks by year"
    ),
    Layout(
        "pdf-web-print",
        "pdf",
        Style(header="web_print", plain=True),
        "A web page printed unstyled: one plain font, drawn bullets, plain headings",
    ),
]

SCANS: list[Layout] = [
    Layout("scan-classic", "scan", Style(), "A scanned page: pictures only"),
    Layout("scan-two-column", "scan", Style(sidebar=True), "A scanned sidebar layout"),
]


def layouts(*, with_word_pdfs: bool | None = None) -> list[Layout]:
    """Every layout. Word layouts saved as PDF are included when LibreOffice is
    installed, or when asked for."""
    found = WORD + PDF + SCANS
    if with_word_pdfs is None:
        with_word_pdfs = libreoffice() is not None
    if with_word_pdfs:
        found += [
            replace(w, name=f"{w.name}.pdf", kind="pdf-from-word", note=f"{w.note}, saved as PDF")
            for w in WORD
        ]
    return found


# -- dates -------------------------------------------------------------------------


def show_date(value: str | None, style: str) -> str:
    if value is None:
        return ""
    if value == PRESENT:
        return "Present"
    year, _, month = value.partition("-")
    if style == "year" or not month:
        return year
    if style == "num":
        return f"{month}/{year}"
    return f"{MONTHS[int(month) - 1]} {year}"


def span(start: str | None, end: str | None, style: str) -> str | None:
    """A job's dates as written, or nothing when the label has none."""
    if start is None and end is None:
        return None
    return f"{show_date(start, style)} – {show_date(end, style)}".strip(" –")


def _place(*parts: str | None) -> str:
    """Words joined by commas, leaving out those the label doesn't have: a real
    person's job may have no place written, and "None" is no place."""
    return ", ".join(p for p in parts if p)


def contact_line(c: Career) -> str:
    return " | ".join(part for part in (c.location, c.phone, c.email) if part)


# -- what a resume says, in order --------------------------------------------------

# One line of a resume: what it is and its words. "right" is text set against the
# right margin on the same line (dates).
Line = tuple[str, str, str | None]


def _job_lines(e: Employment, s: Style) -> Iterator[Line]:
    if s.header == "web_print":
        for p in e.positions:
            if p.title:
                yield ("title", p.title, None)
            where = " - ".join(w for w in (e.employer, e.location) if w)
            if p.start or p.end:
                where = f"{show_date(p.start, s.dates)} to {show_date(p.end, s.dates)} {where}"
            yield ("text", where, None)
            yield from _groups(p, s)
        return
    if s.header == "employer_first":
        yield ("employer", _place(e.employer, e.location), span(e.start, e.end, s.dates))
        for p in e.positions:
            if p.title:
                yield ("title", p.title, span(p.start, p.end, s.dates))
            yield from _groups(p, s)
        return
    for p in e.positions:
        when = span(p.start, p.end, s.dates)
        if s.header == "title_first":
            where = _place(e.employer, e.location)
            yield ("employer", f"{p.title} — {where}" if p.title else where, when)
        else:
            line = _place(p.title, e.employer, e.location)
            yield ("employer", f"{line} | {when}" if when else line, None)
        yield from _groups(p, s)


def _groups(p: Position, s: Style) -> Iterator[Line]:
    for g in p.groups:
        if g.label:
            yield ("label", g.label, None)
        yield from _items(g, s)


def _items(g: Group, s: Style) -> Iterator[Line]:
    if s.bullets == "paragraph":
        # Written as prose, each one ends its sentence, as a person writing a
        # paragraph would; the words are scored without their punctuation.
        yield ("para", " ".join(_sentence(item) for item in g.items), None)
    else:
        for item in g.items:
            yield ("bullet", item, None)


def _sentence(item: str) -> str:
    item = item.rstrip()
    return item if item.endswith((".", "!", "?")) else f"{item.rstrip(';,:')}."


def _sections(c: Career, s: Style) -> dict[str, list[Line]]:
    """The resume's sections as lines, by where they go: "side" in a sidebar, "main"
    otherwise. Without a sidebar everything is main, in the usual order."""
    side: list[Line] = []
    main: list[Line] = []
    contact: list[Line] = [("text", contact_line(c), None)] if s.contact == "body" else []
    skills: list[Line] = [("heading", "SKILLS", None)]
    skills += [("text", f"{g.category}: {', '.join(g.items)}", None) for g in c.skills]
    education: list[Line] = [("heading", "EDUCATION", None)]
    for school in c.education:
        if s.header == "web_print":
            education += [("text", f"{school.degree} : {school.field} , {school.year}", None)]
            education += [("text", school.school, None)]
        else:
            line = f"{school.degree} {school.field}, {school.school}, {school.year}"
            education += [("text", line, None)]
    summary: list[Line] = (
        [("heading", "SUMMARY", None), ("text", c.summary, None)]
        if s.summary == "section" and c.summary
        else []
    )
    highlights: list[Line] = []
    if s.highlights and c.highlights:
        highlights = [("heading", "SELECTED ACHIEVEMENTS", None)]
        highlights += [("bullet", h.text, None) for h in c.highlights]
    experience: list[Line] = [("heading", "EXPERIENCE", None)]
    if s.summary == "in_experience" and c.summary:
        experience.append(("text", c.summary, None))
    for e in c.employments:
        experience += list(_job_lines(e, s))
    awards: list[Line] = []
    if c.awards:
        awards = [("heading", "AWARDS", None)]
        awards += [("text", f"{a.name}, {a.issuer}, {a.year}", None) for a in c.awards]
    talks: list[Line] = []
    if c.talks:
        talks = [("heading", "TALKS", None)]
        if s.talks == "by_year":
            for year in sorted({t.year for t in c.talks}, reverse=True):
                talks.append(("label", year, None))
                talks += [("text", t.text, None) for t in c.talks if t.year == year]
        else:
            talks += [("text", f"{t.text} ({t.year})", None) for t in c.talks]
    if s.sidebar:
        side = contact + skills + education
        main = summary + highlights + experience + awards + talks
    else:
        main = contact + summary + highlights + experience + skills + education + awards + talks
    if s.plain:
        # Headings in the words' own case, like any other line.
        main = [(k, t.title() if k == "heading" else t, r) for k, t, r in main]
    return {"side": side, "main": main}


# -- Word ----------------------------------------------------------------------------


def write_docx(c: Career, s: Style) -> bytes:
    doc = Document()
    styles: Any = doc.styles
    styles["Normal"].font.name = "Calibri"
    styles["Normal"].font.size = Pt(10.5)
    if s.contact == "page_header":
        doc.sections[0].header.paragraphs[0].text = f"{c.name} | {contact_line(c)}"
    name = doc.add_paragraph().add_run(c.name)
    name.bold = True
    name.font.size = Pt(18)
    parts = _sections(c, s)
    if s.bullets == "typed":
        parts = {where: _typed(lines) for where, lines in parts.items()}
    if s.sidebar:
        table = doc.add_table(rows=1, cols=2)
        table.autofit = False
        left, right = table.cell(0, 0), table.cell(0, 1)
        left.width, right.width = Inches(2.0), Inches(4.5)
        _docx_lines(left, parts["side"], Inches(1.9))
        # Word may still split the table evenly, so the dates' tab stop stays inside
        # the narrower of the two widths.
        _docx_lines(right, parts["main"], Inches(3.1))
    else:
        _docx_lines(doc, parts["main"], Inches(6.5))
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def _docx_lines(where: Any, lines: list[Line], width: Any) -> None:
    for kind, text, right in lines:
        if kind == "bullet":
            where.add_paragraph(text, style="List Bullet")
            continue
        para = where.add_paragraph()
        if right is not None:
            para.paragraph_format.tab_stops.add_tab_stop(width, WD_TAB_ALIGNMENT.RIGHT)
        run = para.add_run(text if right is None else f"{text}\t{right}")
        run.bold = kind in ("heading", "employer", "label")
        run.italic = kind == "title"
        if kind == "heading":
            para.paragraph_format.space_before = Pt(8)


def _typed(lines: list[Line]) -> list[Line]:
    """Bullets typed as a character at the start of the line, not a Word list."""
    return [("text", f"• {t}", r) if k == "bullet" else (k, t, r) for k, t, r in lines]


# -- PDF -----------------------------------------------------------------------------

_PDF_CHARS = {"•": chr(149), "–": chr(150), "—": chr(151), "’": "'", "“": '"', "”": '"'}


def _pdf_text(text: str) -> str:
    for char, code in _PDF_CHARS.items():
        text = text.replace(char, code)
    return text


class _Flow:
    """Writes lines down one column of a PDF page."""

    def __init__(
        self, pdf: Any, x: float, width: float, size: float, top: float, *, plain: bool = False
    ) -> None:
        self.pdf, self.x, self.width, self.size = pdf, x, width, size
        self.y = top
        self.plain = plain
        self.h = size * (0.37 if plain else 0.5)

    def write(self, lines: list[Line]) -> None:
        pdf = self.pdf
        for kind, text, right in lines:
            pdf.set_xy(self.x, self.y)
            bold = kind in ("heading", "employer", "label")
            if self.plain:
                pdf.set_font("Times", "", self.size)
            else:
                style = "B" if bold else ("I" if kind == "title" else "")
                pdf.set_font("Helvetica", style, self.size)
            if kind == "heading":
                pdf.set_y(self.y + self.h * 0.6)
                pdf.set_x(self.x)
            if kind == "bullet" and self.plain:
                # A dot drawn the way a browser draws a list's bullet: not a character.
                pdf.ellipse(self.x + 4.9, self.y + self.h * 0.4, 1.06, 1.06, style="F")
                pdf.set_x(self.x + 8.5)
                pdf.multi_cell(
                    self.width - 8.5,
                    self.h,
                    _pdf_text(text),
                    align="L",
                    new_x="LMARGIN",
                    new_y="NEXT",
                )
            elif kind == "bullet":
                pdf.cell(4, self.h, chr(149))
                pdf.set_x(self.x + 4)
                pdf.multi_cell(
                    self.width - 4,
                    self.h,
                    _pdf_text(text),
                    align="L",
                    new_x="LMARGIN",
                    new_y="NEXT",
                )
            elif right is not None:
                if pdf.get_string_width(_pdf_text(text)) > self.width - 44:
                    # No room beside it: the dates go on a line of their own.
                    pdf.multi_cell(
                        self.width,
                        self.h,
                        _pdf_text(text),
                        align="L",
                        new_x="LMARGIN",
                        new_y="NEXT",
                    )
                    pdf.set_x(self.x)
                    pdf.cell(
                        self.width,
                        self.h,
                        _pdf_text(right),
                        align="R",
                        new_x="LMARGIN",
                        new_y="NEXT",
                    )
                else:
                    pdf.cell(self.width - 42, self.h, _pdf_text(text))
                    pdf.cell(42, self.h, _pdf_text(right), align="R", new_x="LMARGIN", new_y="NEXT")
            else:
                pdf.multi_cell(
                    self.width, self.h, _pdf_text(text), align="L", new_x="LMARGIN", new_y="NEXT"
                )
            self.y = pdf.get_y()


def write_pdf(c: Career, s: Style) -> bytes:
    from fpdf import FPDF

    pdf = FPDF(format="Letter")
    pdf.set_auto_page_break(True, margin=12)
    pdf.add_page()
    if s.contact == "page_header":
        pdf.set_font("Helvetica", "", 8)
        pdf.set_xy(12, 5)
        pdf.cell(0, 4, _pdf_text(f"{c.name} | {contact_line(c)}"))
    if s.plain:
        pdf.set_font("Times", "", 11.4)
    else:
        pdf.set_font("Helvetica", "B", 16)
    pdf.set_xy(12, 12)
    pdf.cell(0, 8, _pdf_text(c.name or ""))
    parts = _sections(c, s)
    size = 11.4 if s.plain else 9.0 if s.sidebar else (11.0 if s.wrap else 10.0)
    if s.sidebar:
        _Flow(pdf, 12, 52, size, 24).write(parts["side"])
        pdf.page = 1
        _Flow(pdf, 72, 132, size, 24).write(parts["main"])
    else:
        _Flow(pdf, 12, 100 if s.wrap else 190, size, 24, plain=s.plain).write(parts["main"])
    return bytes(pdf.output())


def scan(pdf: bytes, resolution: int = 150) -> bytes:
    """The same pages as pictures only, the way a scanner or a "print to image" makes
    them: no text layer at all."""
    import pdfplumber

    pages = []
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        for page in doc.pages:
            pages.append(page.to_image(resolution=resolution).original.convert("L"))
    out = io.BytesIO()
    pages[0].save(out, "PDF", resolution=resolution, save_all=True, append_images=pages[1:])
    return out.getvalue()


def libreoffice() -> str | None:
    return shutil.which("soffice") or shutil.which("libreoffice")


def word_to_pdf(docx: bytes) -> bytes | None:
    """The Word file saved as PDF by LibreOffice, as people do before sending."""
    soffice = libreoffice()
    if soffice is None:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "resume.docx"
        src.write_bytes(docx)
        subprocess.run(  # noqa: S603 - our own LibreOffice on a file we just wrote
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", tmp, str(src)],
            check=True,
            capture_output=True,
            timeout=120,
            env={"HOME": tmp, "PATH": "/usr/bin:/bin"},
        )
        return (Path(tmp) / "resume.pdf").read_bytes()
