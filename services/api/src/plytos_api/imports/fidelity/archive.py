"""Labels for a folder of resumes whose web versions are kept beside them.

Some scraped resume sets keep each resume twice: a PDF, and the resume builder's web
page it was printed from, in a CSV (columns ID, Resume_html, Category; the PDF is
<pdfs>/<Category>/<ID>.pdf). The page marks up each field by the builder's field codes
in its element ids (digits around a code: 12JTIT3 is a job title), so what the PDF says
is known field by field without anyone reading it:

    python -m plytos_api.imports.fidelity.archive Resume.csv data/data OUT

Each label is written as truth.Career JSON named by the PDF's id (real.py), readable by
its owner only. Only counts are printed. What's labelled: the summary, every job's
title, dates and accomplishments (one per bullet; one per sentence of a paragraph),
the education, and the accomplishments section, as highlights. Employers are written
as a stand-in, so which jobs were at one employer isn't known: titles are scored
without their employer. Every other section is left out of the score.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import lxml.html
from lxml import etree

from plytos_api.imports.fidelity.real import file_id, write_private
from plytos_api.imports.fidelity.truth import (
    PRESENT,
    Career,
    Employment,
    Group,
    Highlight,
    Position,
    School,
)

# The section codes in a SECTION_<code> id that hold jobs, and the one that holds
# accomplishments of the whole career. Any other section is left out of the score.
JOB_SECTIONS = {"EXPR", "WRKH", "MILI", "RELO", "EXFU"}
SUMMARY_SECTIONS = {"SUMM"}
EDUCATION_SECTIONS = {"EDUC"}
HIGHLIGHT_SECTIONS = {"ACCM"}

STAND_IN = "company name"
MONTHS = {
    m: i + 1
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    )
}
NOW = {"current", "present", "now", "to date", "today"}
BULLETS = "•●▪■◦○·*-–—>"
BLOCK_TAGS = {"p", "div", "ul", "ol", "table", "tbody", "thead", "tr", "td", "th", "h1", "h2"}
BLOCK_TAGS |= {"h3", "h4", "h5", "h6", "section", "blockquote", "dl", "dt", "dd"}


class Unlabelable(Exception):
    """A resume whose markup can't be turned into a label; the message says why."""


# -- the page's text ---------------------------------------------------------------


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def _blocks(element: Any) -> list[tuple[str, str]]:
    """An element's text as the blocks a reader sees: ("li", text) for each list item
    and ("p", text) for everything else, with line breaks kept as newlines."""
    out: list[tuple[str, list[str]]] = []
    open_: list[bool] = [False]

    def put(text: str | None, *, raw: bool = True) -> None:
        if not text:
            return
        if raw:
            # Line breaks in the page's source are spaces; only <br> breaks a line.
            text = re.sub(r"\s+", " ", text)
        if not open_[0]:
            out.append(("p", []))
            open_[0] = True
        out[-1][1].append(text)

    def close() -> None:
        open_[0] = False

    def walk(node: Any) -> None:
        tag = node.tag.lower() if isinstance(node.tag, str) else ""
        if tag == "br":
            put("\n", raw=False)
        elif tag == "li":
            close()
            out.append(("li", []))
            open_[0] = True
            put(node.text)
            for child in node:
                walk(child)
            close()
        elif tag in BLOCK_TAGS:
            close()
            put(node.text)
            for child in node:
                walk(child)
            close()
        elif tag:
            put(node.text)
            for child in node:
                walk(child)
        put(node.tail)

    put(element.text)
    for child in element:
        walk(child)
    blocks = [(kind, "".join(parts)) for kind, parts in out]
    return [(kind, text) for kind, text in blocks if _clean(text)]


def sentences(text: str) -> list[str]:
    """A paragraph's sentences."""
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(“])", _clean(text))
    return [p for p in parts if p]


def items(element: Any) -> list[str]:
    """What an element lists, one item per bullet, and per sentence of a paragraph."""
    return _items(_blocks(element))


def _items(blocks: list[tuple[str, str]]) -> list[str]:
    found: list[str] = []
    for kind, text in blocks:
        if kind == "li":
            item = _clean(text).lstrip(BULLETS).strip()
            if item:
                found.append(item)
            continue
        prose: list[str] = []
        for line in text.split("\n"):
            line = _clean(line)
            if line[:1] in BULLETS and line.lstrip(BULLETS).strip():
                found += sentences(" ".join(prose))
                prose = []
                found.append(line.lstrip(BULLETS).strip())
            elif line:
                prose.append(line)
        found += sentences(" ".join(prose))
    return found


def lines(element: Any) -> list[str]:
    """Every line of an element's text."""
    return [
        line
        for _, text in _blocks(element)
        for line in (_clean(part) for part in text.split("\n"))
        if line
    ]


def _code(element: Any) -> str:
    match = re.fullmatch(r"SECTION_([A-Z]+)\d*", element.get("id") or "")
    return match.group(1) if match else ""


def field(element: Any, code: str) -> Any | None:
    """The first element inside this one carrying a field code in its id."""
    pattern = re.compile(rf"\d*{code}\d*")
    for node in element.iter():
        if isinstance(node.tag, str) and pattern.fullmatch(node.get("id") or ""):
            return node
    return None


def _field_text(element: Any, code: str) -> str:
    node = field(element, code)
    return _clean(node.text_content()) if node is not None else ""


def date(text: str) -> str | None:
    """A written date as YYYY-MM, YYYY or present."""
    t = _clean(text).lower().strip(" .,")
    if not t:
        return None
    if t in NOW:
        return PRESENT
    numbers = re.search(r"\b(\d{1,2})\s*[/\-.\s]\s*((?:19|20)\d{2})\b", t)
    if numbers and 1 <= int(numbers.group(1)) <= 12:
        return f"{numbers.group(2)}-{int(numbers.group(1)):02d}"
    named = re.search(r"\b([a-z]{3})[a-z]*\.?\s*,?\s*((?:19|20)\d{2})\b", t)
    if named and named.group(1) in MONTHS:
        return f"{named.group(2)}-{MONTHS[named.group(1)]:02d}"
    year = re.search(r"\b((?:19|20)\d{2})\b", t)
    return year.group(1) if year else None


# -- the label ---------------------------------------------------------------------


def _paragraphs(section: Any) -> Iterator[Any]:
    for node in section.iter("div"):
        if "paragraph" in (node.get("class") or "").split():
            yield node


def career_from_html(page: str, *, key: str, source: str) -> tuple[Career, list[str]]:
    """The label for one resume's web page, and what was left out of it, in general
    terms, for counting."""
    root = lxml.html.fromstring(page)
    sections = [
        node
        for node in root.iter("div")
        if "section" in (node.get("class") or "").split() and _code(node)
    ]
    summary: list[str] = []
    employments: list[Employment] = []
    education: list[School] = []
    highlights: list[Highlight] = []
    unscored: list[str] = []
    unscored_kinds = ["skill"]
    left_out: list[str] = []

    for section in sections:
        code = _code(section)
        if code in SUMMARY_SECTIONS:
            summary += [text for _, text in _blocks(_body(section))]
        elif code in JOB_SECTIONS or field(section, "JTIT") is not None:
            for job in _paragraphs(section):
                employment = _job(job)
                if employment is None:
                    unscored += lines(job)
                    left_out.append("job without a title")
                else:
                    employments.append(employment)
        elif code in EDUCATION_SECTIONS:
            for entry in _paragraphs(section):
                school = _school(entry)
                free = field(entry, "FRFM")
                if school is None:
                    # Without the school's name it can't be found: none of it is scored.
                    unscored += lines(entry)
                    if "education" not in unscored_kinds:
                        unscored_kinds.append("education")
                    left_out.append("school without a name")
                else:
                    education.append(school)
                    # Coursework and honours under a school aren't labelled.
                    unscored += lines(free) if free is not None else []
        elif code in HIGHLIGHT_SECTIONS:
            # Short lines over the bullets are labels, not accomplishments.
            blocks = _blocks(_body(section))
            labels = [b for b in blocks if b[0] == "p" and _heading_like(b[1])]
            unscored += [_clean(text) for _, text in labels]
            highlights += [
                Highlight(text=t) for t in _items([b for b in blocks if b not in labels])
            ]
        else:
            unscored += lines(_body(section))
            left_out.append(f"section {code}")

    if not employments:
        raise Unlabelable("no jobs marked up")
    employers = {e.employer.lower() for e in employments}
    career = Career(
        key=key,
        source=source,
        summary=" ".join(_clean(s) for s in summary) or None,
        highlights=highlights,
        employments=employments,
        education=education,
        anonymous_employers=bool(employers & {STAND_IN, ""}),
        unscored_kinds=unscored_kinds,
        unscored=[u for u in unscored if u],
        notes="From the resume builder's markup of the page the PDF was printed from.",
    )
    return career, left_out


def _heading_like(text: str) -> bool:
    words = _clean(text)
    return bool(words) and len(words.split()) <= 6 and words[-1] not in ".!?"


def _body(section: Any) -> Any:
    """A section without its heading."""
    for node in section.iter("div"):
        if "heading" in (node.get("class") or "").split():
            parent = node.getparent()
            if parent is not None:
                parent.remove(node)
            break
    return section


def _job(job: Any) -> Employment | None:
    title = _field_text(job, "JTIT")
    if not title:
        return None
    employer = _field_text(job, "COMP")
    where = ", ".join(t for t in (_field_text(job, "JCIT"), _field_text(job, "JSTA")) if t)
    description = field(job, "JDES")
    found = items(description) if description is not None else []
    return Employment(
        employer=employer,
        location=where or None,
        positions=[
            Position(
                title=title,
                start=date(_field_text(job, "JSTD")),
                end=date(_field_text(job, "EDDT")),
                groups=[Group(items=found)] if found else [],
            )
        ],
    )


def _school(entry: Any) -> School | None:
    name = _field_text(entry, "SCHO")
    if not name:
        return None
    year = re.search(r"\b((?:19|20)\d{2})\b", _field_text(entry, "GRYR"))
    return School(
        school=name,
        degree=_field_text(entry, "DGRE"),
        field=_field_text(entry, "STUY"),
        year=year.group(1) if year else None,
    )


# -- the folder --------------------------------------------------------------------


def convert(csv_path: Path, pdfs: Path, out: Path) -> Counter[str]:
    """Writes a label for every resume in the CSV whose PDF is there. Returns counts."""
    counts: Counter[str] = Counter()
    csv.field_size_limit(2**31 - 1)
    with csv_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            counts["rows"] += 1
            pdf = pdfs / row.get("Category", "") / f"{row.get('ID', '')}.pdf"
            if not pdf.is_file():
                counts["skipped: no PDF"] += 1
                continue
            key = file_id(pdf.read_bytes())
            try:
                career, left_out = career_from_html(
                    row.get("Resume_html", ""), key=key, source=str(pdf)
                )
            except Unlabelable as why:
                counts[f"skipped: {why}"] += 1
                continue
            except (ValueError, etree.ParserError):
                counts["skipped: page unreadable"] += 1
                continue
            write_private(out / f"{key}.json", career.model_dump_json(indent=1))
            counts["labelled"] += 1
            counts["jobs"] += len(career.employments)
            counts["accomplishments"] += sum(
                len(p.items) for e in career.employments for p in e.positions
            )
            counts["jobs without dates"] += sum(
                1 for e in career.employments for p in e.positions if not (p.start or p.end)
            )
            counts["schools"] += len(career.education)
            counts["highlights"] += len(career.highlights)
            counts["with a summary"] += career.summary is not None
            counts["employers written as a stand-in"] += career.anonymous_employers
            for what in left_out:
                counts[f"left out: {what}"] += 1
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m plytos_api.imports.fidelity.archive")
    parser.add_argument("csv", type=Path, help="the CSV of web pages (ID, Resume_html, Category)")
    parser.add_argument("pdfs", type=Path, help="the folder of <Category>/<ID>.pdf")
    parser.add_argument("out", type=Path, help="where to write the labels")
    args = parser.parse_args(argv)
    counts = convert(args.csv, args.pdfs, args.out)
    for name, n in sorted(counts.items()):
        print(f"{name}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
