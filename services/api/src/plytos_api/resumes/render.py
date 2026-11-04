"""Turns a resume's content into what the page shows.

Content is a selection over cards (resumes/model.py); this reads the cards as
they are now. Employments show their employer, place and tenure; their
positions show as titles, latest first, each with the accomplishments
switched on under it. Wording comes from the item's choice: a pinned card
version, the card's own wording, or the wording made for a target. Facts
always come from the card's main line.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from plytos_api.cards.model import FactValue, Framing
from plytos_api.cards.repository import CardRepository, CardText
from plytos_api.resumes.model import (
    ENTRY_KINDS,
    ITEM_KINDS,
    ResumeChange,
    ResumeContent,
    ResumeHeader,
    ResumeItem,
)

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

SECTION_LABELS: dict[str, str] = {
    "skill": "Skills",
    "education": "Education",
    "credential": "Certifications",
    "activity": "Activities",
    "accomplishment": "Highlights",
    "project": "Projects",
    "story": "Stories",
}

HEADING_KINDS = frozenset({"position", "engagement"})


class RenderedItem(BaseModel):
    card: UUID
    kind: str
    text: str
    detail: str = ""
    # Whose wording shows: the card's own, the target's, or one pinned here.
    wording: Literal["main", "target", "pinned"] = "main"
    date: str = ""


class RenderedRole(BaseModel):
    # None for results that sit on the employment itself, under no title.
    card: UUID | None
    title: str
    dates: str
    items: list[RenderedItem]


class RenderedEntry(BaseModel):
    card: UUID
    employer: str
    location: str
    dates: str
    fold_earlier: bool
    # Titles folded into one line when fold_earlier is on.
    earlier_titles: list[str]
    roles: list[RenderedRole]
    # Accomplishments in this employment that this resume leaves out.
    hidden: list[RenderedItem]


class RenderedSection(BaseModel):
    kind: str
    label: str
    items: list[RenderedItem]


class LeftOut(BaseModel):
    card: UUID
    employer: str
    dates: str


class RenderedResume(BaseModel):
    header: ResumeHeader
    entries: list[RenderedEntry]
    sections: list[RenderedSection]
    # Employments in the library this resume leaves out.
    left_out: list[LeftOut]
    # Items whose card is gone (archived), so they can't show.
    missing: int


def month(value: FactValue | None) -> str:
    """'2019-03' as 'Mar 2019', '2019' as is, 'present' as 'Present'."""
    if not isinstance(value, str) or not value:
        return ""
    if value.lower() == "present":
        return "Present"
    if len(value) == 7 and value[4] == "-" and value[:4].isdigit() and value[5:].isdigit():
        m = int(value[5:])
        if 1 <= m <= 12:
            return f"{_MONTHS[m - 1]} {value[:4]}"
    return value


def span(start: FactValue | None, end: FactValue | None) -> str:
    a, b = month(start), month(end)
    if a and b:
        return a if a == b else f"{a} \u2013 {b}"
    return a or b


def _text(value: FactValue | None) -> str:
    if isinstance(value, list):
        return ", ".join(value)
    return "" if value is None else str(value)


class _Wording:
    """Picks each item's wording from what the resume asks for."""

    def __init__(
        self,
        cards: CardRepository,
        content: ResumeContent,
        target_id: UUID | None,
        proposed: dict[UUID, Framing],
    ) -> None:
        items = [i for e in content.entries for i in e.items] + list(content.context)
        self._pins = cards.version_framings([i.version for i in items if i.version])
        targets = {i.wording for i in items if isinstance(i.wording, UUID)}
        if target_id is not None:
            targets.add(target_id)
        self._variants = {t: cards.variant_framings(t) for t in targets}
        self._target = target_id
        self._proposed = proposed

    def pick(self, item: ResumeItem, main: Framing) -> tuple[Framing, str]:
        if item.version is not None and item.version in self._pins:
            return self._pins[item.version], "pinned"
        if item.wording == "main":
            return main, "main"
        if item.wording == "auto" and item.card in self._proposed:
            return self._proposed[item.card], "target"
        target = item.wording if isinstance(item.wording, UUID) else self._target
        if target is not None:
            framing = self._variants.get(target, {}).get(item.card)
            if framing is not None:
                return framing, "target"
        return main, "main"


ItemView = Callable[[ResumeItem], RenderedItem | None]


def render(
    content: ResumeContent,
    cards: CardRepository,
    target_id: UUID | None = None,
    proposed: dict[UUID, Framing] | None = None,
) -> RenderedResume:
    """`proposed` is wording drafted for a target that doesn't exist yet, shown
    in place of the target's own when previewing a proposed resume."""
    library = cards.main_contents()
    wording = _Wording(cards, content, target_id, proposed or {})
    children: dict[UUID, list[UUID]] = defaultdict(list)
    for card_id, card in library.items():
        if card.parent_id is not None:
            children[card.parent_id].append(card_id)

    missing = 0

    def item_view(item: ResumeItem) -> RenderedItem | None:
        nonlocal missing
        card = library.get(item.card)
        if card is None:
            missing += 1
            return None
        framing, whose = wording.pick(item, card.content.framing)
        return RenderedItem(
            card=item.card,
            kind=card.kind,
            text=framing.headline,
            detail=framing.body,
            wording=whose,  # type: ignore[arg-type]
            date=month(card.content.facts.get("date")),
        )

    entries: list[RenderedEntry] = []
    on_resume: set[UUID] = set()
    for entry in content.entries:
        head = library.get(entry.card)
        if head is None:
            missing += 1 + len(entry.items)
            continue
        on_resume.add(entry.card)
        entries.append(
            _entry(entry.card, head, entry.items, entry.fold_earlier, library, children, item_view)
        )

    sections: dict[str, RenderedSection] = {}
    for item in content.context:
        view = item_view(item)
        if view is None:
            continue
        section = sections.setdefault(
            view.kind,
            RenderedSection(kind=view.kind, label=SECTION_LABELS.get(view.kind, "More"), items=[]),
        )
        section.items.append(view)

    left_out = [
        LeftOut(
            card=card_id,
            employer=_employer(card),
            dates=span(card.content.facts.get("start"), card.content.facts.get("end")),
        )
        for card_id, card in library.items()
        if card.kind in ENTRY_KINDS and card_id not in on_resume
    ]
    left_out.sort(key=lambda e: e.employer.lower())
    return RenderedResume(
        header=content.header,
        entries=entries,
        sections=list(sections.values()),
        left_out=left_out,
        missing=missing,
    )


def _employer(card: CardText) -> str:
    facts = card.content.facts
    return _text(facts.get("employer")) or card.content.framing.headline


def _start(card: CardText | None) -> str:
    value = card.content.facts.get("start") if card else None
    return value if isinstance(value, str) else ""


def _entry(
    entry_id: UUID,
    card: CardText,
    items: list[ResumeItem],
    fold: bool,
    library: dict[UUID, CardText],
    children: dict[UUID, list[UUID]],
    view_of: ItemView,
) -> RenderedEntry:
    facts = card.content.facts
    branch = _branch(entry_id, children)
    switched_on = {i.card for i in items}

    # A flat role card from before the career tree is its own one heading.
    if card.kind == "role":
        roles = [
            RenderedRole(
                card=entry_id,
                title=_text(facts.get("title")),
                dates=span(facts.get("start"), facts.get("end")),
                items=[v for i in items if (v := view_of(i)) is not None],
            )
        ]
        return RenderedEntry(
            card=entry_id,
            employer=_employer(card),
            location=_text(facts.get("location")),
            dates=span(facts.get("start"), facts.get("end")),
            fold_earlier=False,
            earlier_titles=[],
            roles=roles,
            hidden=_hidden(branch, switched_on, library, view_of),
        )

    headings = [c for c in branch if library[c].kind in HEADING_KINDS]
    headings.sort(key=lambda c: _start(library[c]), reverse=True)
    grouped: dict[UUID | None, list[RenderedItem]] = defaultdict(list)
    for item in items:
        view = view_of(item)
        if view is None:
            continue
        grouped[_heading_of(item.card, entry_id, library)].append(view)

    roles = [
        RenderedRole(
            card=h,
            title=_title(library[h]),
            dates=span(library[h].content.facts.get("start"), library[h].content.facts.get("end")),
            items=grouped.get(h, []),
        )
        for h in headings
    ]
    earlier: list[str] = []
    if fold and len(roles) > 1:
        latest, rest = roles[0], roles[1:]
        for role in rest:
            earlier.append(f"{role.title} ({role.dates})" if role.dates else role.title)
            latest.items.extend(role.items)
        roles = [latest]
    on_employment = grouped.get(None, [])
    if on_employment:
        roles.insert(0, RenderedRole(card=None, title="", dates="", items=on_employment))
    return RenderedEntry(
        card=entry_id,
        employer=_employer(card),
        location=_text(facts.get("location")),
        dates=span(facts.get("start"), facts.get("end")),
        fold_earlier=fold,
        earlier_titles=earlier,
        roles=roles,
        hidden=_hidden(branch, switched_on, library, view_of),
    )


def _branch(root: UUID, children: dict[UUID, list[UUID]]) -> list[UUID]:
    out: list[UUID] = []
    stack = list(children.get(root, []))
    while stack:
        card = stack.pop()
        out.append(card)
        stack.extend(children.get(card, []))
    return out


def _heading_of(card_id: UUID, entry_id: UUID, library: dict[UUID, CardText]) -> UUID | None:
    """The nearest title or client work above a card, inside its employment."""
    seen: set[UUID] = set()
    current = library.get(card_id)
    while current is not None and current.parent_id not in (None, entry_id):
        parent_id = current.parent_id
        assert parent_id is not None
        if parent_id in seen:
            break
        seen.add(parent_id)
        parent = library.get(parent_id)
        if parent is None:
            break
        if parent.kind in HEADING_KINDS:
            return parent_id
        current = parent
    return None


def _title(card: CardText) -> str:
    facts = card.content.facts
    if card.kind == "engagement":
        client = _text(facts.get("client"))
        title = _text(facts.get("title"))
        return f"{title}, {client}" if title and client else client or title
    return _text(facts.get("title")) or card.content.framing.headline


def _hidden(
    branch: list[UUID],
    switched_on: set[UUID],
    library: dict[UUID, CardText],
    view_of: ItemView,
) -> list[RenderedItem]:
    out = []
    for card_id in branch:
        card = library[card_id]
        if card.kind in ITEM_KINDS and card_id not in switched_on:
            view = view_of(ResumeItem(card=card_id))
            if view is not None:
                out.append(view)
    out.sort(key=lambda v: v.text.lower())
    return out


def describe(change: ResumeChange, library: dict[UUID, CardText]) -> str:
    """One line on a parent resume's change, for the person deciding whether
    to take it."""
    card = library.get(change.card)
    if change.kind == "header":
        return "Changed the top: name, contact details or summary"
    if card is None:
        return "Changed a card that's no longer in your library"
    if change.kind in ("entry_added", "entry_removed", "fold"):
        employer = _employer(card)
        if change.kind == "entry_added":
            return f"Added {employer}"
        if change.kind == "entry_removed":
            return f"Left out {employer}"
        return (
            f"Folded earlier titles at {employer} into one line"
            if change.fold_earlier
            else f"Showed each title at {employer}"
        )
    line = f"“{card.content.framing.headline}”"
    return {
        "item_added": f"Switched on {line}",
        "item_removed": f"Switched off {line}",
        "wording": f"Changed which wording {line} uses",
        "context_added": f"Added {line}",
        "context_removed": f"Removed {line}",
    }.get(change.kind, f"Changed {line}")
