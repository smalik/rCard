"""Checks that keep variants honest.

M0 enforces the deterministic part of "no new claims": every number in a
variant's text must already appear in the main version it's based on, and a
variant may only show facts that exist. Checking names, titles and skills
needs language understanding and arrives with the AI critics in M1.
"""

import re

from plytos_api.cards.model import FactValue, MainContent, VariantContent

_NUMBER = re.compile(r"\$?\d[\d,]*(?:\.\d+)?(?:\s?%|[kKmMbB]\b)?")


def _normalize(token: str) -> str:
    return token.replace("$", "").replace(",", "").replace(" ", "").lower().rstrip(".")


def number_tokens(text: str) -> set[str]:
    return {_normalize(m.group(0)) for m in _NUMBER.finditer(text)}


def _fact_text(value: FactValue) -> str:
    return " ".join(value) if isinstance(value, list) else str(value)


def unsupported_claims(variant: VariantContent, main: MainContent) -> list[str]:
    """Returns one plain-language problem per claim the main version doesn't back."""
    problems: list[str] = []
    known = {key for key in main.facts}
    for key in variant.framing.shown_facts or []:
        if key not in known:
            problems.append(f'shows a fact "{key}" that the main card does not have')

    supported: set[str] = set()
    for value in main.facts.values():
        supported |= number_tokens(_fact_text(value))
    supported |= number_tokens(main.framing.headline)
    supported |= number_tokens(main.framing.body)

    cited = number_tokens(variant.framing.headline) | number_tokens(variant.framing.body)
    for token in sorted(cited - supported):
        problems.append(f'cites "{token}", which is not in the main card\'s facts or text')
    return problems


def facts_changed(before: MainContent | None, after: MainContent) -> bool:
    return before is None or before.facts != after.facts
