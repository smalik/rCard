"""Turns the words Claude read in a resume's pictures into lines of the resume.

A screenshot of bullets, a heading drawn as an image or a scanned page holds
words the text of the file doesn't. Claude reads them, and each becomes a line
right after the line the picture follows, marked as read from a picture. The
reading and the audit then treat them like any other line, and every card made
from one asks the person to check its wording, since reading a picture can get
a word wrong.
"""

from __future__ import annotations

from plytos_api.imports.ai import AiPictureLine, AiPictures
from plytos_api.imports.extract import _is_caps, _words, clean, split_bullet
from plytos_api.imports.model import Block, ExtractedDocument, ProposedCard

PICTURE_CHECK = "Plytos read this from a picture in your resume. Check the wording."


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


def mark_picture_cards(blocks: list[Block], cards: list[ProposedCard]) -> None:
    """Asks the person to check the wording of every card made from a picture's words."""
    from_pictures = {b.index for b in blocks if b.where == "image"}
    if not from_pictures:
        return
    for card in cards:
        if from_pictures.intersection(card.source_blocks) and PICTURE_CHECK not in card.needs_check:
            card.needs_check.append(PICTURE_CHECK)
