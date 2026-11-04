"""Pulls the skills, scope and outcome out of each accomplishment, in the person's words.

Claude names them; each is kept only when it's found word for word in that
accomplishment, so a card never claims a skill, a size or a result its words
don't. They become facts on the proposed card (``skills``, ``scope``,
``outcome``), which the person sees and can change before approving it.
"""

from __future__ import annotations

import logging
import re

from plytos_api.imports.ai import AiFacts, verbatim
from plytos_api.imports.model import ProposedCard

log = logging.getLogger(__name__)

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
    matched = offered = kept = 0
    for item in found.results:
        card = asked.get(_ref(item.result))
        if card is None:
            continue
        matched += 1
        text = [words(card)]
        facts = card.content.facts
        offered += len(item.skills) + len(item.scope) + bool(item.outcome)
        skills = _kept(item.skills, text, MAX_SKILLS)
        if skills and "skills" not in facts:
            facts["skills"] = skills
            kept += len(skills)
        scope = _kept(item.scope, text, MAX_SCOPE)
        if scope and "scope" not in facts:
            facts["scope"] = scope
            kept += len(scope)
        outcome = verbatim(item.outcome, text) if len(item.outcome) <= 200 else None
        if outcome and "outcome" not in facts:
            facts["outcome"] = outcome
            kept += 1
    # Numbers only, to tell a reply that missed the refs from one the words didn't hold.
    log.info(
        "Facts: asked=%d answered=%d matched=%d offered=%d kept=%d",
        len(asked),
        len(found.results),
        matched,
        offered,
        kept,
    )


def _ref(written: str) -> str:
    """R3 however the reply writes it: "R3", "[R3]", "r03" or "3"."""
    number = re.search(r"\d+", written)
    return f"R{int(number.group())}" if number else written.strip().upper()


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
