"""Turns the words Claude read in a resume's pictures into lines of the resume.

A screenshot of bullets, a heading drawn as an image or a scanned page holds
words the text of the file doesn't. Claude reads them, and each becomes a line
right after the line the picture follows, marked as read from a picture. The
reading and the audit then treat them like any other line. Reading a picture can
get a word wrong, so the review shows the page beside the cards made from it and
asks once whether they match (page_picture), not on every card.
"""

from __future__ import annotations

import io
import logging

import pdfplumber

from plytos_api.imports.ai import AiPictureLine, AiPictures
from plytos_api.imports.extract import _is_caps, _words, clean, split_bullet
from plytos_api.imports.model import Block, ExtractedDocument

log = logging.getLogger(__name__)

# A page shown to check against: wide enough to read on a laptop, and no bigger,
# however tall the page.
PAGE_WIDTH = 1000
PAGE_PIXELS = 6_000_000


def add_picture_lines(doc: ExtractedDocument, found: AiPictures) -> ExtractedDocument:
    """The document with the pictures' words as lines, renumbered in reading order."""
    read: dict[int, list[AiPictureLine]] = {}
    for picture in found.pictures:
        i = picture.picture - 1
        if picture.kind != "text" or not 0 <= i < len(doc.images) or i in read:
            continue
        lines = [line for line in picture.lines if clean(line.text)]
        if lines:
            read[i] = lines
    if not read:
        return doc

    after: dict[int | None, list[int]] = {}
    for i in sorted(read):
        after.setdefault(doc.images[i].after_block, []).append(i)
    blocks: list[Block] = []
    moved: dict[int, int] = {}

    def add(i: int) -> None:
        page = doc.images[i].page
        for line in read[i]:
            text, glyph = split_bullet(clean(line.text))
            bullet = line.bullet or glyph is not None
            blocks.append(
                Block(
                    index=len(blocks),
                    text=text,
                    is_bullet=bullet,
                    bullet_char=(glyph or "•") if bullet else None,
                    bold=line.bold,
                    all_caps=_is_caps(text),
                    where="image",
                    page=page,
                )
            )

    for i in after.get(None, []):
        add(i)
    for block in doc.blocks:
        moved[block.index] = len(blocks)
        blocks.append(block.model_copy(update={"index": len(blocks)}))
        for i in after.get(block.index, []):
            add(i)

    pictures = [
        p.model_copy(
            update={"after_block": moved.get(p.after_block) if p.after_block is not None else None}
        )
        for p in doc.facts.pictures
    ]
    for i, lines in read.items():
        number = doc.images[i].picture
        if number is not None and 0 <= number < len(pictures):
            pictures[number].lines_read = len(lines)
    facts = doc.facts.model_copy(
        update={"pictures": pictures, "word_count": sum(_words(b.text) for b in blocks)}
    )
    # The pictures have been read; their places no longer match the renumbered lines.
    return ExtractedDocument(facts=facts, blocks=blocks)


def page_picture(data: bytes, page: int) -> bytes | None:
    """A page of a PDF as a JPEG, for the person to check what was read from it
    against: None when the file has no such page or it can't be drawn."""
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            if not 1 <= page <= len(pdf.pages):
                return None
            drawn = pdf.pages[page - 1]
            width, height = float(drawn.width), float(drawn.height)
            scale = min(PAGE_WIDTH / width, (PAGE_PIXELS / (width * height)) ** 0.5)
            image = drawn.to_image(resolution=72 * scale).original.convert("RGB")
    except Exception as exc:  # a file that read once but won't draw
        log.warning("Couldn't draw a page of a resume: %s", type(exc).__name__)
        return None
    out = io.BytesIO()
    image.save(out, "JPEG", quality=82)
    return out.getvalue()
