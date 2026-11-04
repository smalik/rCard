"""The first resume a person has: their own, as written.

Made from an import once its cards are kept. It shows the employments the
person kept, in the order the file had them, each with the accomplishments
kept under it, in the file's order, and the education, skills, credentials
and activities that came with it. The header comes from the contact details
the file had. Nothing is reworded: every line uses the card's own wording.
"""

from __future__ import annotations

from uuid import UUID

from plytos_api.cards.repository import CardText
from plytos_api.imports.model import ImportResult
from plytos_api.imports.store import ImportProgress
from plytos_api.resumes.model import (
    ENTRY_KINDS,
    ITEM_KINDS,
    ResumeContent,
    ResumeEntry,
    ResumeHeader,
    ResumeItem,
)

CONTEXT_FROM_IMPORT = frozenset({"skill", "education", "credential", "activity"})


def as_written(
    result: ImportResult, progress: ImportProgress, library: dict[UUID, CardText]
) -> ResumeContent:
    kept: list[UUID] = []
    for proposed in result.cards:
        decision = progress.cards.get(proposed.ref)
        if decision and decision.state == "approved" and decision.card_id in library:
            assert decision.card_id is not None
            kept.append(decision.card_id)

    entries: dict[UUID, ResumeEntry] = {}
    for card_id in kept:
        if library[card_id].kind in ENTRY_KINDS:
            entries.setdefault(card_id, ResumeEntry(card=card_id))

    context: list[ResumeItem] = []
    for card_id in kept:
        kind = library[card_id].kind
        if kind in ITEM_KINDS:
            employment = _employment_of(card_id, library)
            if employment in entries:
                entries[employment].items.append(ResumeItem(card=card_id))
            else:
                context.append(ResumeItem(card=card_id))
        elif kind in CONTEXT_FROM_IMPORT:
            context.append(ResumeItem(card=card_id))

    contact = result.contact
    header = ResumeHeader(
        name=(contact.name or "")[:120],
        email=(contact.emails[0] if contact.emails else "")[:200],
        phone=(contact.phones[0] if contact.phones else "")[:60],
        location=(contact.location or "")[:120],
        links=[link[:300] for link in contact.links[:5]],
    )
    return ResumeContent(header=header, entries=list(entries.values()), context=context)


def _employment_of(card_id: UUID, library: dict[UUID, CardText]) -> UUID | None:
    """The employment (or flat role) a card sits under, however deep."""
    seen: set[UUID] = set()
    current = library.get(card_id)
    while current is not None and current.parent_id is not None:
        parent_id = current.parent_id
        if parent_id in seen:
            return None
        seen.add(parent_id)
        parent = library.get(parent_id)
        if parent is None:
            return None
        if parent.kind in ENTRY_KINDS:
            return parent_id
        current = parent
    return None
