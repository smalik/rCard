"""Proposes cards from a parsed resume.

Every proposal keeps the resume's own words. Nothing here rewrites them; the
person accepts, edits or drops each card, and only accepted cards are saved.
"""

import re

from plytos_api.cards.model import FactValue, Framing, MainContent
from plytos_api.cards.rules import _NUMBER
from plytos_api.imports.model import Entry, Finding, ParsedResume, ProposedCard, Role
from plytos_api.imports.segment import _DEGREE, _SCHOOL, sentences

_HEADLINE_MAX = 200


def propose_cards(
    parsed: ParsedResume, findings: list[Finding], blocks: dict[int, str]
) -> list[ProposedCard]:
    parsed_blocks = blocks
    by_block: dict[int, list[str]] = {}
    for finding in findings:
        for loc in finding.locations:
            if loc.block is not None:
                rules = by_block.setdefault(loc.block, [])
                if finding.rule not in rules:
                    rules.append(finding.rule)

    def rules_for(blocks: list[int]) -> list[str]:
        out: list[str] = []
        for i in blocks:
            out += [r for r in by_block.get(i, []) if r not in out]
        return out

    cards: list[ProposedCard] = []
    by_ref = {r.ref: r for r in parsed.roles}

    def add(
        kind: str, facts: dict[str, FactValue], text: str, blocks: list[int], role: str | None
    ) -> None:
        headline, body = _framing(text)
        cards.append(
            ProposedCard.model_validate(
                {
                    "ref": f"card-{len(cards) + 1}",
                    "kind": kind,
                    "content": MainContent(
                        facts={k: v for k, v in facts.items() if v not in (None, "", [])},
                        framing=Framing(headline=headline, body=body),
                    ),
                    "role_ref": role,
                    "source_blocks": blocks,
                    "findings": rules_for(blocks),
                }
            )
        )

    if parsed.summary:
        add("story", {"use": "summary"}, parsed.summary, parsed.summary_blocks, None)

    for role in parsed.roles:
        facts = _role_facts(role)
        label = ", ".join(p for p in (role.title, role.organization) if p) or role.header_text
        parent = by_ref.get(role.parent_ref or "")
        if role.client:
            label = ", ".join(p for p in (role.title, role.client) if p) or role.client
        prose = role.description is not None and not role.bullets
        add("role", facts, label, role.header_blocks, role.ref)
        if role.description and not prose:
            cards[-1].content.framing.body = role.description
            cards[-1].source_blocks += role.description_blocks
        cards[-1].needs_check = _role_checks(role, parent)
        context = {
            k: v for k, v in facts.items() if k in ("employer", "client", "title", "start", "end")
        }
        for bullet in role.bullets:
            extra: dict[str, FactValue] = {"workstream": bullet.group} if bullet.group else {}
            add(
                "accomplishment",
                {**context, **extra, **_figures(bullet.text)},
                bullet.text,
                [bullet.block],
                role.ref,
            )
        if prose:
            # One proposed card per sentence of a paragraph-style role.
            for block in role.description_blocks:
                for sentence in sentences(parsed_blocks[block]):
                    if len(sentence.split()) < 5:
                        continue
                    add(
                        "accomplishment",
                        {**context, **_figures(sentence)},
                        sentence,
                        [block],
                        role.ref,
                    )

    for entry in parsed.highlights:
        add("accomplishment", _figures(entry.text), entry.text, entry.blocks, None)

    for category, items in parsed.skills.items():
        add(
            "skill",
            {"category": category, "skills": items},
            category if category != "Skills" else "Skills",
            parsed.skill_blocks.get(category, []),
            None,
        )
        cards[-1].content.framing.body = ", ".join(items)

    for entry in parsed.education:
        add("education", _education_facts(entry), entry.text, entry.blocks, None)
        cards[-1].content.framing.body = "\n".join(entry.details)
    for entry in parsed.certifications:
        add("credential", _dated({"name": entry.text}, entry), entry.text, entry.blocks, None)
    for entry in parsed.projects:
        add(
            "project",
            _dated(_figures(" ".join([entry.text, *entry.details])), entry),
            entry.text,
            entry.blocks,
            None,
        )
        cards[-1].content.framing.body = "\n".join(entry.details)
    for entry in parsed.awards:
        add("accomplishment", _dated({"award": entry.text}, entry), entry.text, entry.blocks, None)
    return cards


def _role_checks(role: Role, parent: Role | None) -> list[str]:
    checks: list[str] = []
    if role.client and parent is not None:
        span = f" (within {parent.dates.raw})" if parent.dates else ""
        checks.append(f"When did your work for {role.client} start and end{span}?")
        if not role.title:
            checks.append(f"What was your title on the {role.client} work?")
        return checks
    if role.confidence == "low" and role.title and role.organization:
        checks.append(f"Is “{role.title}” the job title and “{role.organization}” the employer?")
    if role.organization_inferred and role.organization:
        checks.append(f"Was this role at {role.organization}?")
    if not role.title:
        checks.append("What was the job title?")
    if not role.organization:
        checks.append("Who was the employer?")
    if role.dates is None:
        checks.append("When did this role start and end?")
    elif "YYYY" in (role.dates.start_format, role.dates.end_format):
        checks.append("Which months did this role start and end?")
    return checks


def _framing(text: str) -> tuple[str, str]:
    text = re.sub(r"\s+", " ", text).strip() or "Untitled"
    if len(text) <= _HEADLINE_MAX:
        return text, ""
    cut = text[: _HEADLINE_MAX - 1].rsplit(" ", 1)[0]
    return cut + "…", text


def _role_facts(role: Role) -> dict[str, FactValue]:
    facts: dict[str, FactValue] = {
        "employer": role.organization or "",
        "client": role.client or "",
        "title": role.title or "",
        "location": role.location or "",
        "employment_type": role.employment_type or "",
    }
    if role.section == "volunteer":
        facts["role_type"] = "volunteer"
    if role.dates is not None:
        if role.dates.start is not None:
            facts["start"] = role.dates.start.iso()
        if role.dates.current:
            facts["end"] = "present"
        elif role.dates.end is not None:
            facts["end"] = role.dates.end.iso()
    return facts


def _figures(text: str) -> dict[str, FactValue]:
    figures = [m.group(0).strip() for m in _NUMBER.finditer(text)]
    return {"figures": list(dict.fromkeys(figures))} if figures else {}


def _dated(facts: dict[str, FactValue], entry: Entry) -> dict[str, FactValue]:
    if entry.dates is not None and entry.dates.end is not None:
        facts["date"] = entry.dates.end.iso()
    return facts


def _education_facts(entry: Entry) -> dict[str, FactValue]:
    facts: dict[str, FactValue] = {}
    pieces = [
        p.strip() for p in re.split(r",|\t|\s+[|–—-]\s+", " , ".join([entry.text, *entry.details]))
    ]
    for piece in pieces:
        if not piece:
            continue
        if "institution" not in facts and _SCHOOL.search(piece):
            facts["institution"] = piece
        elif "degree" not in facts and _DEGREE.search(piece):
            facts["degree"] = piece
    return _dated(facts, entry)
