"""Pulls the skills, scope and outcome out of each accomplishment, in the person's words.

Claude names them; each is kept only when it's found word for word in that
accomplishment, so a card never claims a skill, a size or a result its words
don't. They become facts on the proposed card (``skills``, ``scope``,
``outcome``), which the person sees and can change before approving it.
"""

from __future__ import annotations

from plytos_api.imports.ai import AiFacts, verbatim
from plytos_api.imports.model import ProposedCard

MAX_SKILLS = 8
MAX_SCOPE = 4
_MAX_LENGTH = 80


def to_ask(cards: list[ProposedCard]) -> dict[str, ProposedCard]:
    """The accomplishments to read, by a short ref (R1, R2...)."""
    results = [c for c in cards if c.kind == "accomplishment"]
    return {f"R{i}": card for i, card in enumerate(results, start=1)}


def words(card: ProposedCard) -> str:
    """An accomplishment's own words. A long one keeps them whole in the body."""
    return card.content.framing.body or card.content.framing.headline


def add_result_facts(asked: dict[str, ProposedCard], found: AiFacts) -> None:
    """Puts each fact Claude found on its card, if the card's words hold it."""
    for item in found.results:
        card = asked.get(item.result.strip().upper())
        if card is None:
            continue
        text = [words(card)]
        facts = card.content.facts
        skills = _kept(item.skills, text, MAX_SKILLS)
        if skills and "skills" not in facts:
            facts["skills"] = skills
        scope = _kept(item.scope, text, MAX_SCOPE)
        if scope and "scope" not in facts:
            facts["scope"] = scope
        outcome = verbatim(item.outcome, text) if len(item.outcome) <= 200 else None
        if outcome and "outcome" not in facts:
            facts["outcome"] = outcome


def _kept(values: list[str], text: list[str], most: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if len(value) > _MAX_LENGTH:
            continue
        found = verbatim(value, text)
        if found is None or found.lower() in seen:
            continue
        seen.add(found.lower())
        out.append(found)
    return out[:most]
