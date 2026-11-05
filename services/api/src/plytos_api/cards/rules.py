"""Checks that keep variants honest.

M0 enforces the deterministic part of "no new claims": every number in a
variant's text must already appear in the main version it's based on, and a
variant may only show facts that exist. Checking names, titles and skills
needs language understanding and arrives with the AI critics in M1.
"""

import re

from plytos_api.cards.model import FactValue, Framing, MainContent, VariantContent, WrittenPart

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


# The one author whose words are marked as Plytos's own (Framing.plytos_wrote).
SUMMARIZER_REF = "summarizer"


def _part(framing: Framing, part: WrittenPart) -> str:
    return framing.headline if part == "headline" else framing.body


def honest_marks(
    before: MainContent | None, after: MainContent, *, by_summarizer: bool
) -> MainContent:
    """`after` with Plytos's marks as they truly stand. The Summarizer marks
    what it writes. Anyone else keeps a mark only on text left exactly as
    Plytos wrote it, so editing a part makes it the person's own, and no one
    else can mark text as Plytos's."""
    if by_summarizer:
        return after
    kept: list[WrittenPart] = []
    if before is not None:
        kept = [
            p
            for p in before.framing.plytos_wrote
            if _part(before.framing, p) == _part(after.framing, p)
        ]
    if kept == after.framing.plytos_wrote:
        return after
    framing = after.framing.model_copy(update={"plytos_wrote": kept})
    return after.model_copy(update={"framing": framing})


def employer_name(content: MainContent) -> str:
    """An employment's employer: the fact, or the headline on cards from
    before the headline summed the job up."""
    name = content.facts.get("employer")
    return (name.strip() if isinstance(name, str) else "") or content.framing.headline.strip()


def has_headline(content: MainContent) -> bool:
    """Whether an employment's headline sums the job up, rather than standing
    in with the employer's name as it does until someone writes one. Only an
    employment has the employer fact, so other cards never have one."""
    name = content.facts.get("employer")
    if not isinstance(name, str) or not name.strip():
        return False
    return content.framing.headline.strip().casefold() != name.strip().casefold()
