"""Reads a resume file into lines of text in reading order.

Each line keeps the layout facts the audit needs: whether it sat in a table,
text box, header or footer, its bullet, fonts and sizes. Word files are read
from their XML so text boxes, content controls and tracked insertions aren't
missed; PDFs are read from their text layer.
"""

import io
import re
import zipfile
from collections import Counter
from collections.abc import Iterable, Iterator
from typing import Any, Literal

import docx
import pdfplumber
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from docx.text.run import Run
from lxml import etree

from plytos_api.imports.model import (
    Block,
    DocFormat,
    DocumentFacts,
    ExtractedDocument,
    Picture,
)

MAX_BYTES = 5 * 1024 * 1024
MAX_PAGES = 12
_MAX_UNZIPPED = 60 * 1024 * 1024

Where = Literal["body", "table", "text_box", "header", "footer"]

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_NS = {
    "w": _W,
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "v": "urn:schemas-microsoft-com:vml",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
_MC_FALLBACK = f"{{{_NS['mc']}}}Fallback"
_TEXT_BOXES = etree.XPath(".//w:txbxContent[not(ancestor::mc:Fallback)]", namespaces=_NS)
_NEAREST_P = etree.XPath("ancestor::w:p[1]", namespaces=_NS)
_IMAGES = etree.XPath(
    ".//a:blip[not(ancestor::mc:Fallback)] | .//v:imagedata[not(ancestor::mc:Fallback)]",
    namespaces=_NS,
)
_COLS = etree.XPath(".//w:sectPr/w:cols", namespaces=_NS)
_EXTENTS = etree.XPath(
    ".//wp:extent[not(ancestor::mc:Fallback)][following-sibling::*//a:blip or ../*//a:blip]",
    namespaces={
        **_NS,
        "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    },
)
_EMU_PER_INCH = 914400
_HYPERLINK_FIELD = re.compile(r'HYPERLINK\s+"([^"]+)"')

# Bullets typed by hand, and the Symbol/Wingdings glyphs Word uses for list bullets.
_BULLET_GLYPHS = "•●○◦▪▫■□►▸▶➢➤➣✓✔❖◆◇⁃∙·*–—-"
_SYMBOL_BULLETS = {
    "": "•",
    "": "▪",
    "": "■",
    "": "➢",
    "": "❖",
    "": "✓",
    "": "◆",
    "": "➢",
    "": "◆",
    "o": "◦",
}
_LEADING_BULLET = re.compile(rf"^\s*([{re.escape(_BULLET_GLYPHS)}-])\s+(?=\S)")


class UnsupportedFileError(ValueError):
    """The file isn't a resume format we can read."""


def detect_format(data: bytes, filename: str) -> DocFormat:
    if data[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                if "word/document.xml" in zf.namelist():
                    return "docx"
        except zipfile.BadZipFile:
            pass
        raise UnsupportedFileError("This file is a zip archive, not a Word document.")
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:4] == b"\xd0\xcf\x11\xe0":
        raise UnsupportedFileError(
            "This is an old-style .doc file. Save it as .docx or PDF and try again."
        )
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise UnsupportedFileError(
            f"Couldn't read {filename!r}. Upload a .docx, PDF or plain-text resume."
        ) from None
    if "\x00" in text:
        raise UnsupportedFileError("This file isn't plain text.")
    return "text"


def extract(data: bytes, filename: str) -> ExtractedDocument:
    if len(data) > MAX_BYTES:
        raise UnsupportedFileError("Resumes over 5 MB aren't supported.")
    fmt = detect_format(data, filename)
    if fmt == "docx":
        return _DocxReader(data, filename).read()
    if fmt == "pdf":
        return _read_pdf(data, filename)
    return _read_text(data.decode("utf-8"), filename)


def clean(text: str) -> str:
    text = text.replace(" ", " ").replace("​", "").replace("﻿", "")
    return text.replace("‑", "-").strip(" \r")


def split_bullet(text: str) -> tuple[str, str | None]:
    """Splits a typed bullet off the front of a line."""
    m = _LEADING_BULLET.match(text)
    if not m:
        return text, None
    glyph = m.group(1)
    return text[m.end() :], _SYMBOL_BULLETS.get(glyph, glyph)


def _words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9][\w'’&.+/-]*", text))


def _is_caps(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 2 and all(c.isupper() for c in letters)


def _facts(fmt: DocFormat, filename: str, blocks: list[Block], **extra: Any) -> DocumentFacts:
    fonts: Counter[str] = Counter()
    sizes: Counter[str] = Counter()
    for b in blocks:
        weight = max(1, _words(b.text))
        for name in set(b.font_names):
            fonts[name] += weight
        for size in set(b.font_sizes):
            sizes[f"{size:g}"] += weight
    return DocumentFacts(
        format=fmt,
        filename=filename,
        word_count=sum(_words(b.text) for b in blocks),
        table_words=sum(_words(b.text) for b in blocks if b.where == "table"),
        fonts=dict(fonts.most_common()),
        font_sizes=dict(sizes.most_common()),
        **extra,
    )


# --- Word -------------------------------------------------------------------


class _DocxReader:
    def __init__(self, data: bytes, filename: str) -> None:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            infos = zf.infolist()
            if len(infos) > 2000 or sum(i.file_size for i in infos) > _MAX_UNZIPPED:
                raise UnsupportedFileError("This Word file is too large to read.")
            names = zf.namelist()
            app_xml = zf.read("docProps/app.xml") if "docProps/app.xml" in names else b""
            custom = zf.read("docProps/custom.xml") if "docProps/custom.xml" in names else b""
        try:
            self.doc = docx.Document(io.BytesIO(data))
        except Exception as exc:
            raise UnsupportedFileError("This Word file is damaged or password protected.") from exc
        self.filename = filename
        self.pages = _app_pages(app_xml)
        self.markings = _markings(custom)
        self.blocks: list[Block] = []
        self.pictures: list[Picture] = []
        self.tables = 0
        self.text_boxes = 0
        self.theme = self._theme_fonts()
        self.default_font, self.default_size = self._doc_defaults()
        self.numbering = self._numbering()

    def read(self) -> ExtractedDocument:
        body = self.doc.element.body
        self._header_footer("header")
        self._walk(body, "body", self.doc)
        self._header_footer("footer")
        columns = max([int(c.get(qn("w:num"), "1")) for c in _COLS(body)] or [1])
        images = len(_IMAGES(body))
        for section in self.doc.sections:
            for part in (section.header, section.first_page_header):
                if not part.is_linked_to_previous:
                    images += len(_IMAGES(part._element))
        facts = _facts(
            "docx",
            self.filename,
            self.blocks,
            pages=self.pages,
            tables=self.tables,
            text_boxes=self.text_boxes,
            images=images,
            columns=columns,
            markings=self.markings,
            pictures=self.pictures,
            text_width_in=self._text_width(),
        )
        return ExtractedDocument(facts=facts, blocks=self.blocks)

    def _text_width(self) -> float | None:
        section = self.doc.sections[-1]
        if section.page_width is None:
            return None
        width = section.page_width - (section.left_margin or 0) - (section.right_margin or 0)
        return round(width / _EMU_PER_INCH, 2)

    # Structure ---------------------------------------------------------------

    def _header_footer(self, which: Literal["header", "footer"]) -> None:
        seen: set[int] = set()
        for section in self.doc.sections:
            parts: list[Any]
            if which == "header":
                parts = [section.header]
                if section.different_first_page_header_footer:
                    parts.insert(0, section.first_page_header)
            else:
                parts = [section.footer]
                if section.different_first_page_header_footer:
                    parts.insert(0, section.first_page_footer)
            for part in parts:
                if part.is_linked_to_previous and seen:
                    continue
                element = part._element
                if id(element) in seen:
                    continue
                seen.add(id(element))
                self._walk(element, which, part)

    def _walk(self, parent: Any, where: Where, owner: Any) -> None:
        for child in parent.iterchildren():
            if child.tag == qn("w:p"):
                self._paragraph(child, where, owner)
            elif child.tag == qn("w:tbl"):
                self.tables += 1
                self._table(child, "table" if where == "body" else where, owner)
            elif child.tag == qn("w:sdt"):
                content = child.find(qn("w:sdtContent"))
                if content is not None:
                    self._walk(content, where, owner)
            elif child.tag in (qn("w:customXml"), qn("w:ins")):
                self._walk(child, where, owner)

    def _table(self, tbl: Any, where: Where, owner: Any) -> None:
        for tr in tbl.iterchildren(qn("w:tr")):
            for tc in tr.iterchildren(qn("w:tc")):
                tc_pr = tc.find(qn("w:tcPr"))
                vmerge = tc_pr.find(qn("w:vMerge")) if tc_pr is not None else None
                if vmerge is not None and vmerge.get(qn("w:val")) in (None, "continue"):
                    continue
                self._walk(tc, where, owner)

    def _paragraph(self, p: Any, where: Where, owner: Any) -> None:
        paragraph = Paragraph(p, owner)
        lines = self._lines(p, paragraph)
        style = paragraph.style.name if paragraph.style is not None else None
        bullet = self._list_bullet(p, paragraph)
        if bullet is not None:
            text = " ".join(line[0].strip() for line in lines if line[0].strip())
            merged: tuple[str, bool, bool, set[str], set[float], list[str]] = (
                text,
                all(line[1] for line in lines if line[0].strip()),
                all(line[2] for line in lines if line[0].strip()),
                set().union(*(line[3] for line in lines)) if lines else set(),
                set().union(*(line[4] for line in lines)) if lines else set(),
                [link for line in lines for link in line[5]],
            )
            lines = [merged]
        for text, bold, caps, fonts, sizes, links in lines:
            text = clean(text)
            if not text:
                continue
            is_bullet, bullet_char = bullet is not None, bullet
            if not is_bullet:
                stripped, typed = split_bullet(text)
                if typed is not None:
                    text, is_bullet, bullet_char = stripped, True, typed
            self.blocks.append(
                Block(
                    index=len(self.blocks),
                    text=text,
                    is_bullet=is_bullet,
                    bullet_char=bullet_char,
                    style=style,
                    bold=bold,
                    all_caps=caps or _is_caps(text),
                    font_names=sorted(fonts),
                    font_sizes=sorted(sizes),
                    where=where,
                    links=links,
                )
            )
        for extent in _EXTENTS(p):
            nearest = _NEAREST_P(extent)
            if nearest and nearest[0] is p:
                self.pictures.append(
                    Picture(
                        after_block=len(self.blocks) - 1 if self.blocks else None,
                        width_in=round(int(extent.get("cx", "0")) / _EMU_PER_INCH, 2),
                        height_in=round(int(extent.get("cy", "0")) / _EMU_PER_INCH, 2),
                        where=where,
                    )
                )
        for box in _TEXT_BOXES(p):
            nearest = _NEAREST_P(box)
            if nearest and nearest[0] is p:
                if where in ("header", "footer"):
                    self._walk(box, where, owner)
                else:
                    self.text_boxes += 1
                    self._walk(box, "text_box", owner)

    # Runs and formatting -----------------------------------------------------

    def _lines(
        self, p: Any, paragraph: Paragraph
    ) -> list[tuple[str, bool, bool, set[str], set[float], list[str]]]:
        """The paragraph split at manual line breaks, with each line's formatting."""
        lines: list[tuple[str, bool, bool, set[str], set[float], list[str]]] = []
        text, bold, caps = "", True, True
        fonts: set[str] = set()
        sizes: set[float] = set()
        links: list[str] = []

        def flush() -> None:
            nonlocal text, bold, caps, fonts, sizes, links
            has_text = bool(text.strip())
            lines.append((text, bold and has_text, caps and has_text, fonts, sizes, links))
            text, bold, caps, fonts, sizes, links = "", True, True, set(), set(), []

        for r, link in _runs(p, None, paragraph):
            run = Run(r, paragraph)
            for piece in _run_text(r):
                if piece.startswith("\x00HYPERLINK "):
                    links.append(piece.removeprefix("\x00HYPERLINK "))
                    continue
                if piece == "\n":
                    flush()
                    continue
                text += piece
                if piece.strip():
                    bold = bold and self._bold(run, paragraph)
                    caps = caps and bool(self._run_flag(run, paragraph, "caps"))
                    fonts.add(self._font(r, run, paragraph))
                    sizes.add(self._size(run, paragraph))
            if link and link not in links:
                links.append(link)
        flush()
        return lines

    def _bold(self, run: Run, paragraph: Paragraph) -> bool:
        return bool(self._run_flag(run, paragraph, "b"))

    def _run_flag(self, run: Run, paragraph: Paragraph, tag: str) -> bool | None:
        for rpr in self._rpr_chain(run, paragraph):
            el = rpr.find(qn(f"w:{tag}"))
            if el is not None:
                return el.get(qn("w:val"), "true") not in ("0", "false", "off")
        return None

    def _rpr_chain(self, run: Run, paragraph: Paragraph) -> Iterator[Any]:
        r_pr = run._r.rPr
        if r_pr is not None:
            yield r_pr
        for style in _styles(run.style):
            if style.element.rPr is not None:
                yield style.element.rPr
        for style in _styles(paragraph.style):
            if style.element.rPr is not None:
                yield style.element.rPr

    def _font(self, r: Any, run: Run, paragraph: Paragraph) -> str:
        for rpr in self._rpr_chain(run, paragraph):
            name = self._rfonts(rpr)
            if name:
                return name
        return self.default_font

    def _rfonts(self, rpr: Any) -> str | None:
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            return None
        name = rfonts.get(qn("w:ascii")) or rfonts.get(qn("w:hAnsi"))
        if name:
            return str(name)
        theme = rfonts.get(qn("w:asciiTheme")) or rfonts.get(qn("w:hAnsiTheme"))
        if theme:
            return self.theme["major" if theme.startswith("major") else "minor"]
        return None

    def _size(self, run: Run, paragraph: Paragraph) -> float:
        for rpr in self._rpr_chain(run, paragraph):
            sz = rpr.find(qn("w:sz"))
            if sz is not None and sz.get(qn("w:val")):
                return int(sz.get(qn("w:val"))) / 2
        return self.default_size

    def _list_bullet(self, p: Any, paragraph: Paragraph) -> str | None:
        """The list marker Word draws for this paragraph, if it's in a list."""
        num_id, level = None, 0
        candidates = [p.pPr] + [s.element.pPr for s in _styles(paragraph.style)]
        for ppr in candidates:
            if ppr is None:
                continue
            num_pr = ppr.find(qn("w:numPr"))
            if num_pr is None:
                continue
            nid = num_pr.find(qn("w:numId"))
            ilvl = num_pr.find(qn("w:ilvl"))
            if num_id is None and nid is not None:
                num_id = nid.get(qn("w:val"))
            if ilvl is not None and level == 0:
                level = int(ilvl.get(qn("w:val"), "0"))
            if num_id is not None:
                break
        if num_id in (None, "0"):
            return None
        fmt, text = self.numbering.get((str(num_id), level), ("bullet", "•"))
        if fmt == "bullet":
            return _SYMBOL_BULLETS.get(text, text) or "•"
        return "1."

    # Document defaults -------------------------------------------------------

    def _theme_fonts(self) -> dict[str, str]:
        fonts = {"major": "Calibri Light", "minor": "Calibri"}
        for rel in self.doc.part.rels.values():
            if rel.reltype.endswith("/theme") and not rel.is_external:
                root = etree.fromstring(
                    rel.target_part.blob, etree.XMLParser(resolve_entities=False)
                )
                for key in ("major", "minor"):
                    latin = root.find(f".//a:{key}Font/a:latin", _NS)
                    if latin is not None and latin.get("typeface"):
                        fonts[key] = latin.get("typeface")
        return fonts

    def _doc_defaults(self) -> tuple[str, float]:
        font, size = self.theme["minor"], 10.0
        path = f"{qn('w:docDefaults')}/{qn('w:rPrDefault')}/{qn('w:rPr')}"
        rpr = self.doc.styles.element.find(path)
        if rpr is not None:
            font = self._rfonts(rpr) or font
            sz = rpr.find(qn("w:sz"))
            if sz is not None and sz.get(qn("w:val")):
                size = int(sz.get(qn("w:val"))) / 2
        return font, size

    def _numbering(self) -> dict[tuple[str, int], tuple[str, str]]:
        try:
            root = self.doc.part.numbering_part.element
        except (KeyError, NotImplementedError):
            return {}
        abstract: dict[str, dict[int, tuple[str, str]]] = {}
        for an in root.iterchildren(qn("w:abstractNum")):
            levels: dict[int, tuple[str, str]] = {}
            for lvl in an.iterchildren(qn("w:lvl")):
                fmt = lvl.find(qn("w:numFmt"))
                txt = lvl.find(qn("w:lvlText"))
                levels[int(lvl.get(qn("w:ilvl"), "0"))] = (
                    fmt.get(qn("w:val"), "bullet") if fmt is not None else "bullet",
                    txt.get(qn("w:val"), "") if txt is not None else "",
                )
            abstract[an.get(qn("w:abstractNumId"), "")] = levels
        result: dict[tuple[str, int], tuple[str, str]] = {}
        for num in root.iterchildren(qn("w:num")):
            ref = num.find(qn("w:abstractNumId"))
            if ref is None:
                continue
            for level, value in abstract.get(ref.get(qn("w:val"), ""), {}).items():
                result[(num.get(qn("w:numId"), ""), level)] = value
        return result


def _styles(style: Any) -> Iterator[Any]:
    seen = 0
    while style is not None and seen < 20:
        yield style
        style = style.base_style
        seen += 1


def _runs(el: Any, link: str | None, paragraph: Paragraph) -> Iterator[tuple[Any, str | None]]:
    """Runs in a paragraph, including those in links, fields, content controls and insertions."""
    for child in el.iterchildren():
        tag = child.tag
        if tag == qn("w:r"):
            yield child, link
        elif tag == qn("w:hyperlink"):
            rid = child.get(qn("r:id"))
            address = link
            if rid and rid in paragraph.part.rels and paragraph.part.rels[rid].is_external:
                address = paragraph.part.rels[rid].target_ref
            yield from _runs(child, address, paragraph)
        elif tag in (qn("w:del"), qn("w:moveFrom"), qn("w:pPr"), _MC_FALLBACK):
            continue
        elif isinstance(tag, str):
            yield from _runs(child, link, paragraph)


def _run_text(r: Any) -> Iterator[str]:
    for child in r.iterchildren():
        tag = child.tag
        if tag == qn("w:t"):
            yield child.text or ""
        elif tag == qn("w:tab"):
            yield "\t"
        elif tag in (qn("w:br"), qn("w:cr")):
            yield "\n"
        elif tag == qn("w:noBreakHyphen"):
            yield "-"
        elif tag == qn("w:sym"):
            code = child.get(qn("w:char"))
            if code:
                yield chr(int(code, 16))
        elif tag == qn("w:instrText"):
            m = _HYPERLINK_FIELD.search(child.text or "")
            if m:
                yield "\x00HYPERLINK " + m.group(1)


_MARKING_PROPERTY = re.compile(
    rb'name="(ClassificationContentMarking(?:Header|Footer|Watermark)Text|MSIP_Label_[^"]*_Name)"'
    rb"[^>]*>\s*<vt:lpwstr>([^<]*)</vt:lpwstr>"
)


def _markings(custom_xml: bytes) -> list[str]:
    """Labels from Microsoft Purview (or similar) stored in the file's custom properties."""
    found: list[str] = []
    for _, value in _MARKING_PROPERTY.findall(custom_xml):
        text = value.decode("utf-8", "replace").strip()
        if text and text not in found:
            found.append(text)
    return found


def _app_pages(app_xml: bytes) -> int | None:
    m = re.search(rb"<(?:\w+:)?Pages>(\d+)</", app_xml)
    return int(m.group(1)) if m else None


# --- PDF --------------------------------------------------------------------


def _read_pdf(data: bytes, filename: str) -> ExtractedDocument:
    blocks: list[Block] = []
    bullet_x: dict[int, tuple[float, float]] = {}
    images = 0
    columns = 1
    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except Exception as exc:
        raise UnsupportedFileError("This PDF is damaged or password protected.") from exc
    with pdf:
        pages = len(pdf.pages)
        if pages > MAX_PAGES:
            raise UnsupportedFileError(f"Resumes over {MAX_PAGES} pages aren't supported.")
        has_text = False
        for number, page in enumerate(pdf.pages, start=1):
            images += len(page.images)
            words = page.extract_words(extra_attrs=["fontname", "size"], keep_blank_chars=False)
            if not words:
                continue
            has_text = True
            gutter = _gutter(words, float(page.width))
            if gutter is not None:
                columns = 2
                regions: Iterable[list[dict[str, Any]]] = _split_columns(words, gutter)
            else:
                regions = [words]
            for region in regions:
                for line in _pdf_lines(region):
                    _add_pdf_line(blocks, line, number, bullet_x)
    facts = _facts(
        "pdf",
        filename,
        blocks,
        pages=pages,
        images=images,
        columns=columns,
        has_text_layer=has_text,
    )
    return ExtractedDocument(facts=facts, blocks=blocks)


def _font_name(raw: str) -> str:
    name = raw.split("+", 1)[1] if re.match(r"^[A-Z]{6}\+", raw) else raw
    return re.split(r"[-,]", name, maxsplit=1)[0]


def _is_bold_font(raw: str) -> bool:
    return bool(re.search(r"bold|black|heavy|semibold|demi", raw, re.IGNORECASE))


def _cluster_lines(words: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    lines: list[list[dict[str, Any]]] = []
    for w in sorted(words, key=lambda w: (round(float(w["top"])), float(w["x0"]))):
        if lines:
            last = lines[-1]
            ref = last[0]
            tolerance = max(2.0, float(ref["size"]) * 0.4)
            if abs(float(w["top"]) - float(ref["top"])) <= tolerance:
                last.append(w)
                continue
        lines.append([w])
    return [sorted(line, key=lambda w: float(w["x0"])) for line in lines]


def _gutter(words: list[dict[str, Any]], width: float) -> float | None:
    """The x of an empty vertical strip that splits the page into two columns.

    Right-aligned dates also leave a strip empty, so both sides must carry a
    real share of the words before the page counts as two columns.
    """
    lines = _cluster_lines(words)
    if len(lines) < 12:
        return None
    total = len(words)
    best: tuple[float, float] | None = None
    for x in range(int(width * 0.2), int(width * 0.8), 2):
        crossing = sum(
            1 for line in lines if any(float(w["x0"]) < x < float(w["x1"]) for w in line)
        )
        if crossing > len(lines) * 0.1:
            continue
        left_words = sum(1 for w in words if float(w["x1"]) <= x)
        right_words = sum(1 for w in words if float(w["x0"]) >= x)
        left_lines = sum(1 for line in lines if any(float(w["x1"]) <= x for w in line))
        right_lines = sum(1 for line in lines if any(float(w["x0"]) >= x for w in line))
        if min(left_words, right_words) < total * 0.2 or min(left_lines, right_lines) < 6:
            continue
        score = min(left_words, right_words) - crossing * 10
        if best is None or score > best[1]:
            best = (float(x), float(score))
    return best[0] if best else None


def _split_columns(words: list[dict[str, Any]], gutter: float) -> list[list[dict[str, Any]]]:
    left = [w for w in words if float(w["x1"]) <= gutter]
    right = [w for w in words if float(w["x0"]) >= gutter]
    spanning = [w for w in words if float(w["x0"]) < gutter < float(w["x1"])]
    first_column_top = min((float(w["top"]) for w in left + right), default=0.0)
    above = [w for w in spanning if float(w["top"]) <= first_column_top]
    below = [w for w in spanning if float(w["top"]) > first_column_top]
    return [r for r in (above, left, right, below) if r]


def _pdf_lines(words: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    for line in _cluster_lines(words):
        parts: list[str] = []
        prev: dict[str, Any] | None = None
        for w in line:
            if prev is not None:
                gap = float(w["x0"]) - float(prev["x1"])
                parts.append("\t" if gap > float(prev["size"]) * 1.6 else " ")
            parts.append(str(w["text"]))
            prev = w
        yield {
            "text": "".join(parts),
            "x0": float(line[0]["x0"]),
            "top": float(line[0]["top"]),
            "bottom": max(float(w["bottom"]) for w in line),
            "words": line,
        }


def _add_pdf_line(
    blocks: list[Block],
    line: dict[str, Any],
    page: int,
    bullet_x: dict[int, tuple[float, float]],
) -> None:
    """Adds a PDF line as a block, or joins it to the bullet it wraps from.

    bullet_x maps a bullet block's index to the x where its text starts and
    the bottom of its last line, so wrapped lines can be found.
    """
    words = line["words"]
    text = clean(line["text"])
    if not text:
        return
    raw_fonts = [str(w["fontname"]) for w in words]
    stripped, glyph = split_bullet(text)
    prev = blocks[-1] if blocks else None
    if glyph is None and prev is not None and prev.page == page and prev.index in bullet_x:
        text_x, bottom = bullet_x[prev.index]
        size = float(words[0]["size"])
        if abs(text_x - line["x0"]) <= 3 and line["top"] - bottom < size * 1.2:
            prev.text = f"{prev.text} {text}"
            bullet_x[prev.index] = (text_x, line["bottom"])
            return
    block = Block(
        index=len(blocks),
        text=stripped if glyph is not None else text,
        is_bullet=glyph is not None,
        bullet_char=glyph,
        bold=all(_is_bold_font(f) for f in raw_fonts),
        all_caps=_is_caps(text),
        font_names=sorted({_font_name(f) for f in raw_fonts}),
        font_sizes=sorted({round(float(w["size"]) * 2) / 2 for w in words}),
        page=page,
    )
    if glyph is not None:
        text_x = float(words[1]["x0"]) if len(words) > 1 else line["x0"]
        bullet_x[block.index] = (text_x, line["bottom"])
    blocks.append(block)


# --- Plain text ---------------------------------------------------------------


def _read_text(text: str, filename: str) -> ExtractedDocument:
    blocks: list[Block] = []
    for raw in text.splitlines():
        line = clean(raw)
        if not line:
            continue
        stripped, glyph = split_bullet(line)
        blocks.append(
            Block(
                index=len(blocks),
                text=stripped if glyph is not None else line,
                is_bullet=glyph is not None,
                bullet_char=glyph,
                all_caps=_is_caps(line),
            )
        )
    return ExtractedDocument(facts=_facts("text", filename, blocks), blocks=blocks)
