"""Reads a resume file into lines of text in reading order.

Each line keeps the layout facts the audit needs: whether it sat in a table,
text box, header or footer, its bullet, fonts and sizes. Word files are read
from their XML so text boxes, content controls and tracked insertions aren't
missed; PDFs are read from their text layer.

Pictures that may hold words (a screenshot of bullets, a heading drawn as an
image, a scanned page with no text layer) are kept as images too, so Claude can
read them before the lines are sorted (imports/pictures.py).
"""

import io
import re
import zipfile
from collections import Counter
from collections.abc import Iterable, Iterator
from typing import Any, Literal, NamedTuple

import docx
import pdfplumber
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from docx.text.run import Run
from lxml import etree
from PIL import Image

from plytos_api.imports.dates import find_range, only_dates
from plytos_api.imports.model import (
    Block,
    DocFormat,
    DocumentFacts,
    ExtractedDocument,
    Picture,
    PictureImage,
)
from plytos_api.imports.segment import HEADINGS, normalize_heading

MAX_BYTES = 5 * 1024 * 1024
MAX_PAGES = 12
# Pictures read for words, per resume. A resume rarely has more than a few that hold any.
MAX_PICTURES = 10
# Claude reads images up to about this many pixels on the long edge without shrinking them.
_MAX_EDGE = 1568
_MAX_PIXELS = 40_000_000
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
_BLIPS = etree.XPath(".//a:blip[not(ancestor::mc:Fallback)]", namespaces=_NS)
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


# Fullwidth letters and punctuation, as their plain forms.
_FULLWIDTH = {code: code - 0xFEE0 for code in range(0xFF01, 0xFF5F)}


def clean(text: str) -> str:
    text = _unmangle(text.replace(" ", " ").replace("​", "").replace("﻿", ""))
    return text.translate(_FULLWIDTH).replace("‑", "-").strip(" \r")


# A character's UTF-8 bytes read one by one as Windows-1252: a lead byte, then one to
# three continuation bytes (an en dash comes out as three odd letters).
_CONTINUATION = (
    "\u0080-\u00bf\u20ac\u201a\u0192\u201e\u2026\u2020\u2021\u02c6"
    "\u2030\u0160\u2039\u0152\u017d\u2018\u2019\u201c\u201d\u2022\u2013"
    "\u2014\u02dc\u2122\u0161\u203a\u0153\u017e\u0178"
)
_MANGLED = re.compile(f"[\u00c2-\u00f4][{_CONTINUATION}]{{1,3}}")


def _unmangle(text: str) -> str:
    """Puts back characters whose UTF-8 bytes were read as Windows-1252, as some PDF
    makers write them. Only a run that decodes as UTF-8 is changed."""

    def fix(match: re.Match[str]) -> str:
        raw = bytearray()
        for char in match.group(0):
            try:
                raw += char.encode("cp1252")
            except UnicodeEncodeError:
                if ord(char) > 0xFF:
                    return match.group(0)
                raw.append(ord(char))
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            # A character that lost a byte on the way. Standing alone between words,
            # it was a separator (a wide dash or bar); inside a word, leave it be.
            before = match.string[match.start() - 1 : match.start()]
            after = match.string[match.end() : match.end() + 1]
            return "-" if before in ("", " ") and after in ("", " ") else match.group(0)

    return _MANGLED.sub(fix, text) if _MANGLED.search(text) else text


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


def worth_reading(width_in: float, height_in: float) -> bool:
    """Whether a picture is big enough to hold a line of words. Icons and bullets aren't."""
    return width_in >= 1.0 and height_in >= 0.25


def _prepared(raw: bytes | Image.Image) -> tuple[Literal["image/png", "image/jpeg"], bytes] | None:
    """The picture as a PNG (a JPEG when that's too large), shrunk to what Claude reads,
    or None when it isn't a picture Claude can take (a Windows metafile, say)."""
    try:
        image = raw if isinstance(raw, Image.Image) else Image.open(io.BytesIO(raw))
        if image.width * image.height > _MAX_PIXELS:
            return None
        image.load()
        if image.mode not in ("RGB", "L"):
            rgba = image.convert("RGBA")
            image = Image.new("RGB", rgba.size, "white")
            image.paste(rgba, mask=rgba.getchannel("A"))
        image.thumbnail((_MAX_EDGE, _MAX_EDGE))
        out = io.BytesIO()
        image.save(out, "PNG", optimize=True)
        if out.tell() <= 3_500_000:
            return "image/png", out.getvalue()
        out = io.BytesIO()
        image.convert("RGB").save(out, "JPEG", quality=85)
        return "image/jpeg", out.getvalue()
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        return None


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
        self.images: list[PictureImage] = []
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
        return ExtractedDocument(facts=facts, blocks=self.blocks, images=self.images)

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
                picture = Picture(
                    after_block=len(self.blocks) - 1 if self.blocks else None,
                    width_in=round(int(extent.get("cx", "0")) / _EMU_PER_INCH, 2),
                    height_in=round(int(extent.get("cy", "0")) / _EMU_PER_INCH, 2),
                    where=where,
                )
                self.pictures.append(picture)
                self._keep_image(extent, paragraph, picture)
        for box in _TEXT_BOXES(p):
            nearest = _NEAREST_P(box)
            if nearest and nearest[0] is p:
                if where in ("header", "footer"):
                    self._walk(box, where, owner)
                else:
                    self.text_boxes += 1
                    self._walk(box, "text_box", owner)

    def _keep_image(self, extent: Any, paragraph: Paragraph, picture: Picture) -> None:
        """Keeps the picture's pixels when it's big enough to hold words."""
        if len(self.images) >= MAX_PICTURES or not worth_reading(
            picture.width_in, picture.height_in
        ):
            return
        blips = _BLIPS(extent.getparent())
        rid = blips[0].get(f"{{{_NS['r']}}}embed") if blips else None
        part = paragraph.part.related_parts.get(rid) if rid else None
        blob = getattr(part, "blob", None)
        prepared = _prepared(blob) if isinstance(blob, bytes) else None
        if prepared is not None:
            self.images.append(
                PictureImage(
                    after_block=picture.after_block,
                    picture=len(self.pictures) - 1,
                    media_type=prepared[0],
                    data=prepared[1],
                )
            )

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
    flow: dict[int, _Flow] = {}
    images = 0
    columns = 1
    pictures: list[Picture] = []
    kept: list[PictureImage] = []
    scanned: list[int] = []
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
            before = len(blocks) - 1 if blocks else None
            if not words:
                if page.images and len(kept) < MAX_PICTURES:
                    # A scanned page: keep the whole page as a picture to read.
                    image = _render(page, None, 150)
                    if image is not None:
                        scanned.append(number)
                        kept.append(
                            PictureImage(
                                after_block=before, page=number, media_type=image[0], data=image[1]
                            )
                        )
                continue
            has_text = True
            gutter = _gutter(words, float(page.width))
            if gutter is not None:
                columns = 2
                regions: Iterable[list[dict[str, Any]]] = _split_columns(words, gutter)
            else:
                regions = [words]
            tops: list[tuple[int, float]] = []  # (block, top) of each line on this page
            marks = _bullet_marks(page)
            for region in regions:
                lines = list(_pdf_lines(region))
                for line in lines:
                    line["marked"] = _marked(line, marks)
                # The region's right margin: where the longest line of running text
                # stops. Dates set against a tab stop can reach past it.
                running = [
                    line
                    for line in lines
                    if "\t" not in line["text"] and not _ends_on_date(line["text"])
                ] or lines
                right = max(float(w["x1"]) for line in running for w in line["words"])
                for line in lines:
                    count = len(blocks)
                    _add_pdf_line(blocks, line, number, bullet_x, flow, right)
                    if len(blocks) > count:
                        tops.append((blocks[-1].index, line["top"]))
            for img in page.images:
                _pdf_picture(page, img, words, number, before, tops, pictures, kept)
    _mark_running_lines(blocks)
    facts = _facts(
        "pdf",
        filename,
        blocks,
        pages=pages,
        images=images,
        columns=columns,
        has_text_layer=has_text,
        scanned_pages=scanned,
        pictures=pictures,
    )
    return ExtractedDocument(facts=facts, blocks=blocks, images=kept)


def _mark_running_lines(blocks: list[Block]) -> None:
    """Marks a line repeated at the top or foot of the pages, as a running header or
    footer is, the way a Word file marks its own. Otherwise a header printed again at
    the top of page 2 reads as part of whatever section it lands in."""
    pages = sorted({b.page for b in blocks if b.page is not None})
    if len(pages) < 2:
        return
    by_page = {page: [b for b in blocks if b.page == page] for page in pages}

    def key(block: Block) -> str:
        # "Page 1 of 2" and "Page 2 of 2" are the same line.
        return re.sub(r"\d+", "#", block.text.strip().lower())

    marks: list[tuple[Literal["header", "footer"], slice]] = [
        ("header", slice(0, 2)),
        ("footer", slice(-2, None)),
    ]
    for where, ends in marks:
        seen: dict[str, set[int]] = {}
        for page, on_page in by_page.items():
            for block in on_page[ends]:
                seen.setdefault(key(block), set()).add(page)
        repeated = {k for k, on in seen.items() if len(on) >= 2}
        for on_page in by_page.values():
            for block in on_page[ends]:
                if key(block) in repeated and block.where == "body":
                    block.where = where


def _pdf_picture(
    page: Any,
    img: dict[str, Any],
    words: list[dict[str, Any]],
    number: int,
    before: int | None,
    tops: list[tuple[int, float]],
    pictures: list[Picture],
    kept: list[PictureImage],
) -> None:
    """Records an image on a page with text, and keeps it to read if it may hold words.

    An image with text-layer words over it is a background, or the scan under a
    PDF that was already turned into text; its words are read from the layer.
    """
    x0, x1 = max(0.0, float(img["x0"])), min(float(page.width), float(img["x1"]))
    top, bottom = max(0.0, float(img["top"])), min(float(page.height), float(img["bottom"]))
    if x1 - x0 < 1 or bottom - top < 1:
        return
    over = sum(
        1
        for w in words
        if x0 <= (float(w["x0"]) + float(w["x1"])) / 2 <= x1
        and top <= (float(w["top"]) + float(w["bottom"])) / 2 <= bottom
    )
    if over >= 3:
        return
    above = [block for block, line_top in tops if line_top <= top]
    picture = Picture(
        after_block=max(above) if above else before,
        width_in=round((x1 - x0) / 72, 2),
        height_in=round((bottom - top) / 72, 2),
    )
    pictures.append(picture)
    if len(kept) >= MAX_PICTURES or not worth_reading(picture.width_in, picture.height_in):
        return
    image = _render(page, (x0, top, x1, bottom), 200)
    if image is not None:
        kept.append(
            PictureImage(
                after_block=picture.after_block,
                page=number,
                picture=len(pictures) - 1,
                media_type=image[0],
                data=image[1],
            )
        )


def _render(
    page: Any, box: tuple[float, float, float, float] | None, dpi: int
) -> tuple[Literal["image/png", "image/jpeg"], bytes] | None:
    """A page, or part of one, as a picture."""
    try:
        area = page.crop(box) if box is not None else page
        return _prepared(area.to_image(resolution=dpi).original)
    except Exception:  # a picture that won't render is left unread
        return None


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


# The narrowest clear strip, in points, that can part two columns. The gaps between
# words can line up down a few lines of a paragraph, but they're narrower than this.
_GUTTER = 8.0


def _gutter(words: list[dict[str, Any]], width: float) -> float | None:
    """The x of an empty vertical strip that splits the page into two columns.

    A strip only counts when it's wider than a gap between words, and when there are
    columns on both sides of it: lines of more than dates, each side's starting at
    one left edge, and a fair share of the words. Dates set against the right margin
    leave a strip clear too, and a column of them is no column of text.
    """
    lines = _cluster_lines(words)
    if len(lines) < 12:
        return None
    half = _GUTTER / 2
    scored: list[tuple[float, float]] = []
    for x in range(int(width * 0.2), int(width * 0.8), 2):
        crossing = sum(
            1
            for line in lines
            if any(float(w["x0"]) < x + half and float(w["x1"]) > x - half for w in line)
        )
        if crossing > len(lines) * 0.1:
            continue
        sides = [
            _column_text([[w for w in line if float(w["x1"]) <= x] for line in lines]),
            _column_text([[w for w in line if float(w["x0"]) >= x] for line in lines]),
        ]
        if any(len(side) < 6 or _aligned(side) < 6 for side in sides):
            continue
        counts = [sum(len(part) for part in side) for side in sides]
        if min(counts) < len(words) * 0.08:
            continue
        scored.append((float(x), float(min(counts) - crossing * 10)))
    if not scored:
        return None
    # The middle of the clearest strip, so the fewest words sit across it.
    top = max(score for _, score in scored)
    clearest = [x for x, score in scored if score == top]
    return clearest[len(clearest) // 2]


def _column_text(parts: list[list[dict[str, Any]]]) -> list[list[dict[str, Any]]]:
    """One side's piece of each line, leaving out empty pieces and ones that are only
    dates."""
    return [p for p in parts if p and not only_dates(" ".join(str(w["text"]) for w in p))]


def _aligned(parts: list[list[dict[str, Any]]]) -> int:
    """How many of the pieces start at the most common left edge, give or take 2 points."""
    starts = Counter(round(float(p[0]["x0"])) for p in parts)
    return max(sum(n for s, n in starts.items() if abs(s - edge) <= 2) for edge in starts)


def _split_columns(words: list[dict[str, Any]], gutter: float) -> list[list[dict[str, Any]]]:
    left = [w for w in words if float(w["x1"]) <= gutter]
    right = [w for w in words if float(w["x0"]) >= gutter]
    spanning = [w for w in words if float(w["x0"]) < gutter < float(w["x1"])]
    first_column_top = min((float(w["top"]) for w in left + right), default=0.0)
    above = [w for w in spanning if float(w["top"]) <= first_column_top]
    below = [w for w in spanning if float(w["top"]) > first_column_top]
    return [r for r in (above, left, right, below) if r]


def _bullet_marks(page: Any) -> list[tuple[float, float, float]]:
    """Bullets drawn rather than typed, as a browser prints a list: small dots and
    squares, as (right edge, top, bottom)."""
    marks: list[tuple[float, float, float]] = []
    for shape in [*page.curves, *page.rects]:
        width, height = float(shape["width"]), float(shape["height"])
        if 1.5 <= width <= 8 and 1.5 <= height <= 8 and abs(width - height) <= 1.5:
            marks.append((float(shape["x1"]), float(shape["top"]), float(shape["bottom"])))
    return marks


def _marked(line: dict[str, Any], marks: list[tuple[float, float, float]]) -> bool:
    """Whether a drawn bullet sits just left of a line, level with its first words."""
    return any(
        0 <= line["x0"] - right <= 20 and top >= line["top"] - 2 and bottom <= line["bottom"] + 2
        for right, top, bottom in marks
    )


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


class _Flow(NamedTuple):
    """Where a plain PDF line sat, to tell whether the next line carries it on."""

    x0: float
    x1: float
    bottom: float
    fonts: tuple[str, ...]
    size: float
    # Text set apart on the line, such as dates against the right margin.
    spaced: bool


def _wraps_from(above: _Flow, line: dict[str, Any], text: str, right: float) -> bool:
    """Whether a line is the one above carried on: it starts at the same left edge
    just below, in the same type, and its first word wouldn't have fit at the end of
    the line above, so the line above was full. A line that ends a sentence or on a
    date, or one that starts "Label:", stands on its own."""
    words = line["words"]
    first = words[0]
    size = float(first["size"])
    fonts = tuple(sorted({str(w["fontname"]) for w in words}))
    if (
        above.spaced
        or "\t" in line["text"]
        or abs(above.x0 - line["x0"]) > 2
        or line["top"] - above.bottom > size * 0.9
        or fonts != above.fonts
        or abs(size - above.size) > 0.1
    ):
        return False
    room = right - above.x1
    fits = float(first["x1"]) - float(first["x0"]) + size * 0.25 <= room + 1
    return not fits and not re.match(r"^\S+(?:\s+\S+){0,2}:\s", text)


def _add_pdf_line(
    blocks: list[Block],
    line: dict[str, Any],
    page: int,
    bullet_x: dict[int, tuple[float, float]],
    flow: dict[int, _Flow],
    right: float,
) -> None:
    """Adds a PDF line as a block, or joins it to the bullet or the line it wraps from.

    bullet_x maps a bullet block's index to the x where its text starts and
    the bottom of its last line, so wrapped lines can be found. flow does the same
    for plain lines, which carry on only from a line that filled the column.
    """
    words = line["words"]
    text = clean(line["text"])
    if not text:
        return
    raw_fonts = [str(w["fontname"]) for w in words]
    stripped, glyph = split_bullet(text)
    drawn = glyph is None and bool(line.get("marked"))
    if drawn:
        stripped, glyph = text, "•"
    prev = blocks[-1] if blocks else None
    # A section heading never carries a line on, nor is carried on by one, whatever its
    # type: a resume printed in one plain font sets its headings like any other line.
    heading = _is_heading(text)
    if (
        glyph is None
        and not heading
        and prev is not None
        and prev.page == page
        and prev.index in bullet_x
    ):
        text_x, bottom = bullet_x[prev.index]
        size = float(words[0]["size"])
        if abs(text_x - line["x0"]) <= 3 and line["top"] - bottom < size * 1.2:
            prev.text = f"{prev.text} {text}"
            bullet_x[prev.index] = (text_x, line["bottom"])
            return
    line_x1 = max(float(w["x1"]) for w in words)
    if (
        glyph is None
        and prev is not None
        and prev.page == page
        and prev.index in flow
        and not heading
        and not _is_heading(prev.text)
        and not prev.text.rstrip().endswith((".", "!", "?"))
        and not _ends_on_date(prev.text)
        and _wraps_from(flow[prev.index], line, text, right)
    ):
        prev.text = f"{prev.text} {text}"
        above = flow[prev.index]
        flow[prev.index] = above._replace(x1=line_x1, bottom=float(line["bottom"]))
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
        typed = not drawn and len(words) > 1
        text_x = float(words[1]["x0"]) if typed else line["x0"]
        bullet_x[block.index] = (text_x, line["bottom"])
    else:
        flow[block.index] = _Flow(
            x0=float(line["x0"]),
            x1=line_x1,
            bottom=float(line["bottom"]),
            fonts=tuple(sorted(set(raw_fonts))),
            size=float(words[0]["size"]),
            spaced="\t" in line["text"],
        )
    blocks.append(block)


def _is_heading(text: str) -> bool:
    return normalize_heading(text.strip().rstrip(":")) in HEADINGS


def _ends_on_date(text: str) -> bool:
    found = find_range(text)
    return found is not None and text.rstrip(" )").endswith(found.raw.rstrip(" )"))


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
