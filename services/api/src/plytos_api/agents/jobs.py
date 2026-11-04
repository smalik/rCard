"""The jobs a note can be filed under, described for an agent.

A note belongs under a job title (a position card). An employment with no
titles yet takes notes itself. Labels carry only what the cards say.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from plytos_api.cards.model import FactValue, MainContent
from plytos_api.cards.repository import CardRepository

_OPEN_ENDS = ("", "present", "now", "current")


@dataclass(frozen=True)
class Job:
    ref: str
    card_id: UUID
    label: str
    current: bool
    start: str


def _text(value: FactValue | None) -> str:
    if value is None:
        return ""
    return ", ".join(value) if isinstance(value, list) else str(value)


def jobs(cards: CardRepository) -> list[Job]:
    """Titles and employments a note can sit under, current first, then newest."""
    summaries = [s for s in cards.list_cards() if s.kind in ("employment", "position")]
    content: dict[UUID, MainContent] = {}
    for s in summaries:
        main = cards.card_detail(s.id).main.content
        if isinstance(main, MainContent):
            content[s.id] = main
    has_titles = {c.parent for c in content.values() if c.parent is not None}
    found: list[tuple[UUID, str, bool, str]] = []
    for s in summaries:
        main = content.get(s.id)
        if main is None:
            continue
        facts = main.facts
        start, end = _text(facts.get("start")), _text(facts.get("end"))
        dates = f"{start or '?'} to {end or 'present'}"
        current = end.lower() in _OPEN_ENDS
        if s.kind == "position":
            parent = content.get(main.parent) if main.parent else None
            employer = _text(parent.facts.get("employer")) if parent else ""
            title = _text(facts.get("title")) or main.framing.headline
            label = f"{title} at {employer} ({dates})" if employer else f"{title} ({dates})"
        elif s.id in has_titles:
            continue
        else:
            employer = _text(facts.get("employer")) or main.framing.headline
            label = f"{employer} ({dates})"
        found.append((s.id, label, current, start))
    ordered = sorted((j for j in found if j[2]), key=lambda j: j[3], reverse=True) + sorted(
        (j for j in found if not j[2]), key=lambda j: j[3], reverse=True
    )
    return [
        Job(ref=f"job-{i + 1}", card_id=card_id, label=label, current=current, start=start)
        for i, (card_id, label, current, start) in enumerate(ordered)
    ]
