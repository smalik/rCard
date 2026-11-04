"""Checks that every line sits under the job it came from.

The reading decides which employer each title belongs to and which title each
accomplishment belongs to. Two checks go over that, independently:

* Order. On most resumes a line belongs to the title written above it, and a
  title to the employer written above it. A line filed somewhere else is
  suspect. This check is skipped for multi-column layouts, where reading order
  isn't reliable.
* A second look by Claude, separate from the reading, that gets the resume and
  the tree built from it and names anything filed under the wrong title or
  employer, with the cue in the resume that shows it.

A card either check flags gets a question for the person. When both agree on
where it belongs, the card is moved there and the question asks them to
confirm it; otherwise it stays put and the question offers the other place.
Either way nothing is saved until the person answers, so a result never sits
under the wrong job without them being asked.
"""

from __future__ import annotations

from plytos_api.imports.ai import AiMisfiled, PlacementChecker
from plytos_api.imports.model import (
    Employment,
    ExtractedDocument,
    ParsedResume,
    PlaceChoice,
    Placement,
    ProposedCard,
    Role,
)

_JOBS = ("position", "engagement")
_QUESTIONS = {
    "accomplishment": "Which job is this from?",
    "position": "Which employer was this title at?",
    "engagement": "Which job was this client work part of?",
}


def check_placements(
    doc: ExtractedDocument,
    parsed: ParsedResume,
    cards: list[ProposedCard],
    checker: PlacementChecker | None,
) -> None:
    """Puts a placement question on every card the checks disagree about."""
    by_ref = {c.ref: c for c in cards}
    roles = {r.ref: r for r in parsed.roles}
    employments = {e.ref: e for e in parsed.employments}
    if not any(c.kind in _JOBS for c in cards):
        return
    keys = {c.ref: line for c in cards if (line := _key_line(c, roles, employments)) is not None}
    order = {} if doc.facts.columns > 1 else _by_order(cards, roles, employments, keys)
    names, tree = _tree(cards, keys)
    found: dict[int, AiMisfiled] = {}
    if checker is not None and tree:
        check = checker.check_placements(doc, tree)
        if check is not None:
            found = {m.line: m for m in check.misfiled}
    for card in cards:
        if card.kind not in _QUESTIONS or card.ref not in keys:
            continue
        line = keys[card.ref]
        current = card.parent_ref
        by_order = order.get(card.ref)
        if by_order is not None and (by_order == current or _above(by_order, current, by_ref)):
            by_order = None
        flagged = found.get(line)
        named = names.get(flagged.belongs_under.strip().upper()) if flagged else None
        if flagged is not None and named is not None and not _fits(card, by_ref[named]):
            named = None
        if flagged is not None and named == current:
            flagged = None
        if by_order is None and flagged is None:
            continue
        suggested = named or by_order
        reason = _reason(flagged, by_order, by_ref)
        if suggested is not None and by_order is not None and named == by_order:
            # Both checks put it in the same other place: move it, and ask.
            card.placement = Placement(
                question=_QUESTIONS[card.kind],
                reason=reason,
                choices=[_choice(suggested, by_ref), _choice(current, by_ref)],
                moved_from=current,
            )
            _move(card, suggested, by_ref)
            continue
        choices = [_choice(current, by_ref)]
        if suggested is not None and suggested != current:
            choices.append(_choice(suggested, by_ref))
        else:
            # No one place to suggest: offer every job it could be from.
            jobs = [c for c in cards if c.kind in _JOBS] if card.kind == "accomplishment" else []
            choices += [
                _choice(c.ref, by_ref)
                for c in (jobs or cards)
                if c.ref != current and c.ref != card.ref and _fits(card, c)
            ]
        card.placement = Placement(question=_QUESTIONS[card.kind], reason=reason, choices=choices)


def _key_line(
    card: ProposedCard, roles: dict[str, Role], employments: dict[str, Employment]
) -> int | None:
    """The line that places a card: an accomplishment's own line, or a title's own line."""
    if card.kind == "accomplishment":
        return min(card.source_blocks) if card.source_blocks else None
    role = roles.get(card.role_ref or "")
    if role is None:
        return None
    employment = employments.get(role.employment_ref or "")
    shared = set(employment.header_blocks) if employment is not None else set()
    own = [b for b in role.header_blocks if b != role.employer_block and b not in shared]
    return min(own) if own else None


def _by_order(
    cards: list[ProposedCard],
    roles: dict[str, Role],
    employments: dict[str, Employment],
    keys: dict[str, int],
) -> dict[str, str]:
    """Where each card sits by reading order: the nearest title or employer line above."""
    anchors: list[tuple[int, str]] = []  # (line, card ref)
    for card in cards:
        if card.kind == "employment":
            employment = employments.get(card.employment_ref or "")
            if employment is not None and employment.header_blocks:
                anchors.append((min(employment.header_blocks), card.ref))
        elif card.kind in _JOBS and card.ref in keys:
            anchors.append((keys[card.ref], card.ref))
    anchors.sort()
    kinds = {c.ref: c.kind for c in cards}
    out: dict[str, str] = {}
    for card in cards:
        line = keys.get(card.ref)
        if line is None or card.kind not in _QUESTIONS:
            continue
        wanted: tuple[str, ...] = ("employment", *_JOBS)
        if card.kind == "position":
            wanted = ("employment",)
        elif card.kind == "engagement":
            wanted = ("employment", "position")
        above = [ref for start, ref in anchors if start < line and kinds[ref] in wanted]
        if above:
            out[card.ref] = above[-1]
    return out


def _above(ref: str, child: str | None, by_ref: dict[str, ProposedCard]) -> bool:
    """Whether card ``ref`` is ``child`` or one of its ancestors."""
    seen: set[str] = set()
    while child is not None and child not in seen:
        if child == ref:
            return True
        seen.add(child)
        child = by_ref[child].parent_ref if child in by_ref else None
    return False


def _fits(card: ProposedCard, parent: ProposedCard) -> bool:
    if card.kind == "position":
        return parent.kind == "employment"
    if card.kind == "engagement":
        return parent.kind in ("employment", "position")
    return parent.kind in ("employment", *_JOBS)


def _tree(cards: list[ProposedCard], keys: dict[str, int]) -> tuple[dict[str, str], str]:
    """The career tree as short refs (E1, T1, C1) and line numbers, for Claude."""
    names: dict[str, str] = {}
    counts = {"employment": 0, "position": 0, "engagement": 0}
    letters = {"employment": "E", "position": "T", "engagement": "C"}
    children: dict[str | None, list[ProposedCard]] = {}
    for card in cards:
        if card.kind in letters:
            counts[card.kind] += 1
            names[f"{letters[card.kind]}{counts[card.kind]}"] = card.ref
        children.setdefault(card.parent_ref, []).append(card)
    label = {ref: name for name, ref in names.items()}
    out: list[str] = []

    def walk(card: ProposedCard, depth: int) -> None:
        pad = "  " * depth
        own = sorted(card.source_blocks)
        what = {"employment": "employer", "position": "title", "engagement": "client"}[card.kind]
        key = keys.get(card.ref)
        head = [key] if key is not None else own[:1]
        rest = [b for b in own if b not in head]
        line = f"{pad}{label[card.ref]} {card.content.framing.headline} — {what} line "
        line += ", ".join(str(b) for b in head)
        if rest:
            line += "; also " + ", ".join(str(b) for b in rest)
        results = [c for c in children.get(card.ref, []) if c.kind == "accomplishment"]
        if results:
            line += "; lines " + ", ".join(str(min(c.source_blocks)) for c in results)
        out.append(line)
        for child in children.get(card.ref, []):
            if child.kind in letters:
                walk(child, depth + 1)

    for card in cards:
        if card.kind == "employment" and card.parent_ref is None:
            walk(card, 0)
    loose = [c for c in children.get(None, []) if c.kind == "accomplishment" and c.source_blocks]
    if loose:
        out.append(
            "Not under any job: lines " + ", ".join(str(min(c.source_blocks)) for c in loose)
        )
    return names, "\n".join(out)


def _choice(ref: str | None, by_ref: dict[str, ProposedCard]) -> PlaceChoice:
    return PlaceChoice(parent_ref=ref, label=_label(ref, by_ref))


def _label(ref: str | None, by_ref: dict[str, ProposedCard]) -> str:
    if ref is None or ref not in by_ref:
        return "Not under a job"
    card = by_ref[ref]
    facts = card.content.facts
    employer = _employer(card, by_ref)
    if card.kind == "employment":
        span = _span(facts.get("start"), facts.get("end"))
        name = employer or card.content.framing.headline
        return f"{name}, {span}" if span else name
    if card.kind == "engagement":
        client = str(facts.get("client") or card.content.framing.headline)
        return f"{client} (client work at {employer})" if employer else f"{client} (client work)"
    title = str(facts.get("title") or card.content.framing.headline)
    return f"{title} at {employer}" if employer else title


def _employer(card: ProposedCard, by_ref: dict[str, ProposedCard]) -> str | None:
    seen: set[str] = set()
    while card.kind != "employment" and card.parent_ref in by_ref and card.ref not in seen:
        seen.add(card.ref)
        card = by_ref[card.parent_ref or ""]
    employer = card.content.facts.get("employer") if card.kind == "employment" else None
    return employer if isinstance(employer, str) and employer else None


def _span(start: object, end: object) -> str:
    def year(value: object) -> str:
        if value == "present":
            return "present"
        return str(value)[:4] if isinstance(value, str) and value else ""

    first, last = year(start), year(end)
    return f"{first} – {last}" if first and last else first or last


def _reason(
    flagged: AiMisfiled | None, by_order: str | None, by_ref: dict[str, ProposedCard]
) -> str:
    if flagged is not None and flagged.reason.strip():
        text = " ".join(flagged.reason.split())
        return text if len(text) <= 240 else text[:239].rsplit(" ", 1)[0] + "…"
    if by_order is not None:
        return f"It's written under {_label(by_order, by_ref)} on your resume."
    return "Plytos isn't sure this is filed under the right job."


def _move(card: ProposedCard, parent: str, by_ref: dict[str, ProposedCard]) -> None:
    target = by_ref[parent]
    card.parent_ref = parent
    if card.kind == "accomplishment":
        card.role_ref = target.role_ref if target.kind in _JOBS else None
