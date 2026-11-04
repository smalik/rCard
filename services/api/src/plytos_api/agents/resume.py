"""What Plytos says after reading a resume the person shared in the conversation.

The reading is the import's own (imports/pipeline.py). This only tells the
person, in a sentence or two, what was found and what's left for them.
"""

from __future__ import annotations

from plytos_api.imports.model import ImportResult
from plytos_api.imports.store import to_settle


def _count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _join(parts: list[str]) -> str:
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def reading(result: ImportResult) -> str:
    kinds = [c.kind for c in result.cards]
    employers = kinds.count("employment")
    titles = kinds.count("position") + kinds.count("role")
    results = kinds.count("accomplishment")
    if not result.cards:
        return (
            "I couldn't find roles or results in that file. You can tell me about your work"
            " here instead, a sentence at a time."
        )
    found = [
        part
        for n, part in (
            (employers, _count(employers, "employer", "employers")),
            (titles, _count(titles, "title", "titles")),
            (results, _count(results, "result", "results")),
        )
        if n
    ]
    others = len(kinds) - employers - titles - results
    if others:
        found.append(_count(others, "other card", "other cards"))
    questions = len(to_settle(result))
    next_step = (
        f" {_count(questions, 'thing needs', 'things need')} a quick answer first."
        if questions
        else " Go through them when you have a few minutes and keep what's right."
    )
    return f"I read it: {_join(found)}.{next_step} Nothing becomes a card until you keep it."
