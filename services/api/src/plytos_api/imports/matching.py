"""Matching an import's proposed cards to the cards the person already has.

A person brings in a resume more than once: an updated copy, or the same file
again. Each employer, title and line they already keep as a card should carry
on as that card, so a new upload adds versions instead of duplicates.

A proposal matches an existing card of the same kind that sits in the same
place (under the card its parent became, or would become) and goes by the same
name: the employer for an employment (or its former name), the title for a
position, the client and title for an engagement, the headline for anything
else. Names are compared
loosely (case, accents, punctuation, "Inc." and the like, "Sr." for
"Senior"). Dates that are written on both sides must overlap, to the month
where they give one, so a second stint at the same employer stays its own card.

Matching only proposes. The person decides on each card: save it as the next
version of theirs, keep theirs as it is, or make a separate card.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Collection, Mapping
from uuid import UUID

from pydantic import BaseModel

from plytos_api.cards.model import MainContent
from plytos_api.cards.repository import CardText
from plytos_api.cards.rules import has_headline
from plytos_api.imports.model import ImportResult, ProposedCard


class CardMatch(BaseModel):
    """One of the person's cards that a proposed card stands for."""

    card_id: UUID
    # The card's headline now, so the person knows which card it is.
    headline: str
    # True when the import says nothing the card doesn't already: approving
    # just links them, and no version is added.
    same: bool


class Decided(BaseModel):
    """What the person decided about a proposed card, as matching needs it."""

    state: str
    card_id: UUID | None = None


_SUFFIXES = {
    "inc",
    "incorporated",
    "llc",
    "ltd",
    "limited",
    "corp",
    "corporation",
    "co",
    "company",
    "plc",
    "gmbh",
    "lp",
    "llp",
}
_SPELLED = {"sr": "senior", "jr": "junior", "mgr": "manager", "asst": "assistant"}


def _words(text: str) -> list[str]:
    """Lowercase words, accents folded so "Nestlé" is "Nestle". Letters in any
    script are kept: "北京 Inc." and "上海 Inc." stay apart."""
    text = unicodedata.normalize("NFKD", text.casefold().replace("&", " and "))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return [w for w in re.split(r"[\W_]+", text) if w]


def name_key(text: str) -> str:
    """A name compared loosely: "Acme Health, Inc." and "acme health" match."""
    words = [_SPELLED.get(w, w) for w in _words(text)]
    if words and words[0] == "the":
        words = words[1:]
    while len(words) > 1 and words[-1] in _SUFFIXES:
        words.pop()
    return " ".join(words)


def _fact(content: MainContent, key: str) -> str:
    value = content.facts.get(key)
    return value if isinstance(value, str) else ""


def names(kind: str, content: MainContent) -> set[str]:
    """The names a card goes by, compared loosely. Empty when it has none: an
    employment without an employer, or a position without a title, matches
    nothing, since its headline may only say what's missing."""
    found: list[str] = []
    if kind == "employment":
        found = [_fact(content, "employer"), _fact(content, "former_employer")]
    elif kind == "position":
        found = [_fact(content, "title")]
    elif kind == "engagement":
        client = _fact(content, "client")
        found = [f"{client} {_fact(content, 'title')}" if client else ""]
    else:
        found = [content.framing.headline]
    return {k for k in (name_key(n) for n in found) if k}


def _month(value: object, *, end: bool) -> int | None:
    """A date as a count of months. A year alone runs from its first month at
    the start of a span to its last at the end."""
    if not isinstance(value, str):
        return None
    if value.strip().lower() in ("present", "current", "now"):
        return 9999 * 12 if end else None
    m = re.match(r"^\s*(\d{4})(?:-(\d{1,2}))?", value)
    if m is None:
        return None
    month = int(m.group(2)) if m.group(2) else (12 if end else 1)
    return int(m.group(1)) * 12 + min(max(month, 1), 12) - 1


def _span(content: MainContent) -> tuple[int, int] | None:
    start = content.facts.get("start")
    first = _month(start, end=False)
    if first is None:
        return None
    last = _month(content.facts.get("end"), end=True)
    if last is None:
        # No end: just the start's own year, or month.
        last = _month(start, end=True)
    return first, last if last is not None else first


def overlaps(a: MainContent, b: MainContent) -> bool:
    """Whether two cards' dates overlap. Undated cards overlap anything."""
    sa, sb = _span(a), _span(b)
    if sa is None or sb is None:
        return True
    return sa[0] <= sb[1] and sb[0] <= sa[1]


def merged(existing: MainContent, chosen: MainContent) -> MainContent:
    """The next version of an existing card from what the import read: its own
    facts kept, the import's facts and wording on top, and where it sits and
    what's attached to it unchanged. Words on the card that the import has
    nothing for stay, as they were and by whoever wrote them: a job's headline
    the import only has as the employer's name, and a story or detail the
    import has no words for."""
    after = MainContent(
        parent=existing.parent,
        facts={**existing.facts, **chosen.facts},
        framing=chosen.framing,
        attachments=existing.attachments,
    )
    kept: dict[str, str] = {}
    if has_headline(existing) and not has_headline(after):
        kept["headline"] = existing.framing.headline
    if existing.framing.body.strip() and not chosen.framing.body.strip():
        kept["body"] = existing.framing.body
    if kept:
        marks = [p for p in existing.framing.plytos_wrote if p in kept]
        after.framing = chosen.framing.model_copy(update={**kept, "plytos_wrote": marks})
    return after


def unchanged(existing: MainContent, chosen: MainContent) -> bool:
    """Whether saving `chosen` over `existing` would change nothing."""
    after = merged(existing, chosen)
    return after.facts == existing.facts and after.framing == existing.framing


def match_cards(
    result: ImportResult,
    decided: Mapping[str, Decided],
    moves: Mapping[str, str | None],
    contents: Mapping[str, MainContent],
    cards: Mapping[UUID, CardText],
    reserved: Collection[UUID] = (),
) -> dict[str, CardMatch]:
    """The person's card each proposed card stands for, by ref. `contents` is
    each proposal's wording as it stands (after the person's edits). `reserved`
    cards match nothing, such as ones a proposal left out in the same breath
    showed as its match."""
    by_ref = {p.ref: p for p in result.cards}
    # Cards this import already linked to or made, so no second proposal takes them.
    taken = {d.card_id for d in decided.values() if d.card_id is not None} | set(reserved)
    matches: dict[str, CardMatch] = {}
    visited: set[str] = set()
    # Oldest first (ids are time-ordered), so a tie goes to the card kept longest.
    known_names = {
        card_id: names(card.kind, card.content) for card_id, card in sorted(cards.items())
    }

    def parent_ref(p: ProposedCard) -> str | None:
        return moves.get(p.ref, p.parent_ref)

    def card_of(ref: str) -> tuple[bool, UUID | None]:
        """(known, card) for a proposal: known is False when it becomes a new card."""
        d = decided.get(ref)
        if d is not None and d.state == "approved":
            return True, d.card_id
        if ref in matches:
            return True, matches[ref].card_id
        return False, None

    def under(p: ProposedCard) -> tuple[bool, UUID | None]:
        """Where a proposal's card sits: (known, the card above it)."""
        ref = parent_ref(p)
        seen: set[str] = set()
        while ref is not None and ref not in seen:
            seen.add(ref)
            d = decided.get(ref)
            if d is not None and d.state == "dropped":
                # A dropped parent passes its children up to its own parent.
                parent = by_ref.get(ref)
                ref = parent_ref(parent) if parent is not None else None
                continue
            return card_of(ref)
        return True, None

    def visit(p: ProposedCard, stack: set[str]) -> None:
        if p.ref in visited or p.ref in stack:
            return
        # Parents first: a card can only match under the card its parent matched.
        stack.add(p.ref)
        parent = parent_ref(p)
        if parent is not None and parent in by_ref:
            visit(by_ref[parent], stack)
        stack.discard(p.ref)
        visited.add(p.ref)

        d = decided.get(p.ref)
        if d is not None and d.state in ("approved", "dropped"):
            return  # Already linked, or left out: it takes none of the person's cards.
        known, above = under(p)
        if not known:
            return  # Its parent becomes a new card, so nothing of the person's sits there.
        content = contents.get(p.ref, p.content)
        wanted = names(p.kind, content)
        if not wanted:
            return
        for card_id, have in known_names.items():
            card = cards[card_id]
            if (
                card_id in taken
                or card.kind != p.kind
                or card.parent_id != above
                or not (have & wanted)
                or not overlaps(card.content, content)
            ):
                continue
            matches[p.ref] = CardMatch(
                card_id=card_id,
                headline=card.content.framing.headline,
                same=unchanged(card.content, content),
            )
            taken.add(card_id)
            return

    for proposal in result.cards:
        visit(proposal, set())
    return matches
