"""Turns Claude's proofreading into findings the person can act on.

Claude reports misspellings, wrong words and broken grammar, quoting the words
and suggesting a fix. A typo is kept only when its quote is on the line it
names; the suggestion is only a suggestion, and nothing changes unless the
person edits the card. Skill names the audit already flags aren't repeated.
"""

from __future__ import annotations

import re

from plytos_api.imports.ai import TYPO_KINDS, AiProofread
from plytos_api.imports.model import ExtractedDocument, Finding, Location, ParsedResume
from plytos_api.imports.skills import spelling_fixes

MAX_TYPOS = 20
_MAX_QUOTE = 120


def proofread_findings(
    doc: ExtractedDocument, parsed: ParsedResume, found: AiProofread
) -> list[Finding]:
    """One finding per typo Claude found, checked against the resume's lines."""
    blocks = {b.index: b for b in doc.blocks}
    # Skill names the audit already flags (content.skill_spelling).
    skills = [skill for items in parsed.skills.values() for skill in items]
    flagged = {wrong.lower() for wrong, _ in spelling_fixes(skills)}
    out: list[Finding] = []
    seen: set[tuple[int, str]] = set()
    for typo in found.typos:
        block = blocks.get(typo.line)
        quote = _norm(typo.quote)
        suggestion = _norm(typo.suggestion)
        if (
            block is None
            or not quote
            or not suggestion
            or len(quote) > _MAX_QUOTE
            or len(suggestion) > _MAX_QUOTE
            or quote == suggestion
            or quote not in _norm(block.text)
            or (block.index, quote) in seen
            or any(re.search(rf"(?<!\w){re.escape(f)}(?!\w)", quote.lower()) for f in flagged)
        ):
            continue
        seen.add((block.index, quote))
        kind = typo.kind if typo.kind in TYPO_KINDS else "spelling"
        what = {"spelling": "spelling", "grammar": "grammar", "word": "word"}[kind]
        short = quote if len(quote) <= 40 else quote[:39].rsplit(" ", 1)[0] + "…"
        out.append(
            Finding(
                rule="content.proofread",
                severity="improve",
                category="content",
                about="cards",
                title=f"Check the {what} in “{short}”",
                detail=f"Did you mean “{suggestion}”? Plytos only suggests: nothing "
                "changes unless you edit the card.",
                locations=[Location(block=block.index, excerpt=quote)],
            )
        )
        if len(out) >= MAX_TYPOS:
            break
    return out


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
