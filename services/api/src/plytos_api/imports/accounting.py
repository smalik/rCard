"""Accounts for every line of a resume once an import has read it.

Each line ends up in one of four places: on a proposed card, in the contact
details, as a section heading, or skipped for a stated reason (a page number,
a page header repeated on page two, "references available on request"). A
line in none of those is proposed as a card of its own and marked for the
person to check, so nothing they wrote is lost without them seeing it.
"""

from __future__ import annotations

import re

from plytos_api.cards.model import CardKind, FactValue, Framing, MainContent
from plytos_api.imports.cards import _figures, _framing
from plytos_api.imports.model import (
    ExtractedDocument,
    LineAccount,
    ParsedResume,
    ProposedCard,
    Section,
    SectionKind,
    SkippedLine,
    SkipReason,
)
from plytos_api.imports.segment import is_marking, plain_skip

_WORK = ("employment", "position", "engagement")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def account(
    doc: ExtractedDocument,
    parsed: ParsedResume,
    cards: list[ProposedCard],
    *,
    skipped: dict[int, SkipReason] | None = None,
) -> LineAccount:
    """Checks every line landed somewhere, and proposes a card for any that didn't.
    ``skipped`` holds lines the reader left out on purpose, with its reason."""
    blocks = {b.index: b for b in doc.blocks}
    on_cards = {i for c in cards for i in c.source_blocks if i in blocks}
    contact = sorted(i for i in parsed.contact.blocks if i in blocks and i not in on_cards)
    headings = sorted(
        {s.heading_block for s in parsed.sections if s.heading_block in blocks} - on_cards
    )
    placed = on_cards | set(contact) | set(headings)
    contact_texts = {_norm(blocks[i].text) for i in parsed.contact.blocks if i in blocks}
    if parsed.contact.name:
        contact_texts.add(_norm(parsed.contact.name))

    skips: list[SkippedLine] = []
    left: list[int] = []
    for block in doc.blocks:
        i = block.index
        if i in placed:
            continue
        text = block.text.strip()
        reason: SkipReason | None = None
        if is_marking(block, doc.facts.markings):
            reason = "marking"
        elif (plain := plain_skip(text)) is not None:
            reason = plain
        elif block.where in ("header", "footer") or _norm(text) in contact_texts:
            # A page header, or the name and contact line repeated on a later page.
            reason = "page_header"
        elif skipped is not None and i in skipped:
            reason = skipped[i]
        if reason is not None:
            skips.append(SkippedLine(block=i, reason=reason))
        else:
            left.append(i)

    for i in left:
        cards.append(_guess(i, blocks[i].text, blocks[i].is_bullet, parsed, cards))
    return LineAccount(
        lines=len(doc.blocks),
        on_cards=len(on_cards),
        contact=contact,
        headings=headings,
        skipped=skips,
        guessed=left,
    )


def _section(i: int, sections: list[Section]) -> SectionKind | None:
    for s in sections:
        if i in s.blocks:
            return s.holds or s.kind
    above = [s for s in sections if s.heading_block is not None and s.heading_block < i]
    if above:
        last = max(above, key=lambda s: s.heading_block or 0)
        return last.holds or last.kind
    return None


def _guess(
    i: int, text: str, bullet: bool, parsed: ParsedResume, cards: list[ProposedCard]
) -> ProposedCard:
    """A card for a line nothing claimed, placed where it most likely belongs."""
    section = _section(i, parsed.sections)
    unsure = (
        "Plytos wasn't sure where this line belongs, so it's on a card of its own. "
        "Keep it, move it or drop it."
    )
    kind: CardKind = "activity"
    facts: dict[str, FactValue] = {}
    parent: ProposedCard | None = None
    check = unsure
    if section in ("experience", "volunteer") or (section is None and _after_work(i, cards)):
        kind, facts = "accomplishment", _figures(text)
        parent = _work_above(i, cards)
        if parent is not None:
            where = _employer_of(parent, cards)
            check = (
                f"Plytos wasn't sure where this line belongs. Is it from your time at {where}?"
                if where
                else unsure
            )
        else:
            check = "Plytos wasn't sure where this line belongs. Which job is it from?"
    elif section in ("summary", "objective"):
        kind, facts = "story", {"use": "summary"}
    elif section in ("contact", None):
        kind, facts = "story", {"use": "headline"}
    elif section in ("highlights", "awards"):
        kind, facts = "accomplishment", _figures(text)
    elif section == "education":
        kind = "education"
    elif section == "certifications":
        kind, facts = "credential", {"name": text.strip()}
    elif section in ("skills", "languages"):
        items = [p.strip(" .") for p in re.split(r"[,;|•·]", text) if p.strip(" .")]
        kind = "skill"
        facts = {"category": "Languages" if section == "languages" else "Skills", "skills": items}
    elif section == "projects":
        kind, facts = "project", _figures(text)
    else:
        facts = {"name": text.strip()}
    headline, body = _framing(text)
    card = ProposedCard(
        ref=f"card-{len(cards) + 1}",
        kind=kind,
        content=MainContent(facts=facts, framing=Framing(headline=headline, body=body)),
        parent_ref=parent.ref if parent is not None else None,
        role_ref=parent.role_ref if parent is not None else None,
        source_blocks=[i],
        needs_check=[check],
    )
    if kind == "skill":
        card.content.framing.body = ", ".join(facts.get("skills", []))  # type: ignore[arg-type]
    return card


def _after_work(i: int, cards: list[ProposedCard]) -> bool:
    return _work_above(i, cards) is not None


def _work_above(i: int, cards: list[ProposedCard]) -> ProposedCard | None:
    """The nearest employer, title or client card written above line ``i``, or the
    one an accomplishment above it sits under."""
    by_ref = {c.ref: c for c in cards}
    best: tuple[int, ProposedCard] | None = None
    for card in cards:
        if card.kind not in (*_WORK, "accomplishment"):
            continue
        before = [b for b in card.source_blocks if b < i]
        if not before:
            continue
        at = max(before)
        if best is None or at > best[0]:
            best = (at, card)
    if best is None:
        return None
    card = best[1]
    while card.kind not in _WORK:
        if card.parent_ref is None or card.parent_ref not in by_ref:
            return None
        card = by_ref[card.parent_ref]
    return card


def _employer_of(card: ProposedCard, cards: list[ProposedCard]) -> str | None:
    by_ref = {c.ref: c for c in cards}
    while card.kind != "employment" and card.parent_ref in by_ref:
        card = by_ref[card.parent_ref or ""]
    employer = card.content.facts.get("employer")
    return employer if isinstance(employer, str) and employer else None
