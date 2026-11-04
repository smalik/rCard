"""Proposes cards from a parsed resume.

Every proposal keeps the resume's own words. Nothing here rewrites them; the
person accepts, edits or drops each card, and only accepted cards are saved.
"""

import re

from plytos_api.cards.model import FactValue, Framing, MainContent
from plytos_api.cards.rules import _NUMBER
from plytos_api.imports.career import group_employments
from plytos_api.imports.model import (
    DateRange,
    Employment,
    Entry,
    Finding,
    ParsedResume,
    ProposedCard,
    Role,
)
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
        kind: str,
        facts: dict[str, FactValue],
        text: str,
        blocks: list[int],
        role: str | None,
        parent: str | None = None,
    ) -> ProposedCard:
        headline, body = _framing(text)
        card = ProposedCard.model_validate(
            {
                "ref": f"card-{len(cards) + 1}",
                "kind": kind,
                "content": MainContent(
                    facts={k: v for k, v in facts.items() if v not in (None, "", [])},
                    framing=Framing(headline=headline, body=body),
                ),
                "parent_ref": parent,
                "role_ref": role,
                "source_blocks": blocks,
                "findings": rules_for(blocks),
            }
        )
        cards.append(card)
        return card

    if parsed.summary:
        add("story", {"use": "summary"}, parsed.summary, parsed.summary_blocks, None)

    employments = parsed.employments or group_employments(parsed.roles, parsed_blocks)
    # The proposed card each role became: a position, or an engagement for client work.
    held: dict[str, ProposedCard] = {}
    for employment in employments:
        roles = [by_ref[r] for r in employment.role_refs if r in by_ref]
        if not roles:
            continue
        first = roles[0]
        employer = add(
            "employment",
            _employment_facts(employment),
            employment.organization or first.client or first.header_text or "Employer",
            employment.header_blocks or first.header_blocks,
            None,
        )
        employer.employment_ref = employment.ref
        employer.needs_check = _employment_checks(employment, roles)
        if employment.description:
            employer.content.framing.body = employment.description
            employer.source_blocks += employment.description_blocks
        for role in roles:
            parent = held.get(role.parent_ref or "") if role.client else None
            if role.client:
                card = add(
                    "engagement",
                    _engagement_facts(role),
                    role.client,
                    _own(role, employment),
                    role.ref,
                    (parent or employer).ref,
                )
            else:
                card = add(
                    "position",
                    _position_facts(role, employment),
                    role.title or "Title not found",
                    _own(role, employment),
                    role.ref,
                    employer.ref,
                )
            held[role.ref] = card
            card.needs_check = _role_checks(
                role, by_ref.get(role.parent_ref or ""), dated_by=employment
            )
            prose = role.description is not None and not role.bullets
            if role.description and not prose:
                card.content.framing.body = role.description
                card.source_blocks += role.description_blocks
            for bullet in role.bullets:
                extra: dict[str, FactValue] = {"workstream": bullet.group} if bullet.group else {}
                add(
                    "accomplishment",
                    {**extra, **_figures(bullet.text)},
                    bullet.text,
                    [bullet.block],
                    role.ref,
                    card.ref,
                )
            if prose:
                # One proposed card per sentence of a paragraph-style role.
                for block in role.description_blocks:
                    for sentence in sentences(parsed_blocks[block]):
                        if len(sentence.split()) < 5:
                            continue
                        add(
                            "accomplishment",
                            _figures(sentence),
                            sentence,
                            [block],
                            role.ref,
                            card.ref,
                        )

    for entry in parsed.highlights:
        # A highlight that names one client or employer belongs to that work.
        home = _named_in(entry.text, cards)
        card = add(
            "accomplishment",
            _figures(entry.text),
            entry.text,
            entry.blocks,
            home.role_ref if home else None,
            home.ref if home else None,
        )
        if home is not None:
            card.needs_check = [f"Is this from your work at {home.content.framing.headline}?"]

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
    for entry in parsed.activities:
        add("activity", _dated({"name": entry.text}, entry), entry.text, entry.blocks, None)
        cards[-1].content.framing.body = "\n".join(entry.details)
    return cards


def _named_in(text: str, cards: list[ProposedCard]) -> ProposedCard | None:
    """The one engagement or employment whose client or employer the text names."""
    lowered = text.lower()
    for kind, key in (("engagement", "client"), ("employment", "employer")):
        named = [
            c
            for c in cards
            if c.kind == kind
            and isinstance(name := c.content.facts.get(key), str)
            and re.search(r"\b" + re.escape(name.lower()) + r"\b", lowered)
        ]
        if len(named) == 1:
            return named[0]
    return None


def _employment_checks(employment: Employment, roles: list[Role]) -> list[str]:
    checks: list[str] = []
    org = employment.organization
    if not org:
        checks.append("Who was the employer?")
    elif employment.organization_inferred and len(roles) == 1 and not roles[0].client:
        checks.append(f"Was this role at {org}?")
    if employment.dates is None and org:
        checks.append(f"When did you start and leave {org}?")
    return checks


def _role_checks(role: Role, parent: Role | None, *, dated_by: Employment) -> list[str]:
    checks: list[str] = []
    if role.client and parent is not None:
        span = f" (within {parent.dates.raw})" if parent.dates else ""
        checks.append(f"When did your work for {role.client} start and end{span}?")
        if not role.title:
            checks.append(f"What was your title on the {role.client} work?")
        return checks
    if role.confidence == "low" and role.title and role.organization:
        checks.append(f"Is “{role.title}” the job title and “{role.organization}” the employer?")
    if not role.title:
        checks.append("What was the job title?")
    if role.dates is None:
        if not (dated_by.tenure_written and dated_by.dates is not None):
            # A title inside a written tenure is dated by it; asking isn't needed.
            checks.append("When did you start and finish in this title?")
    elif "YYYY" in (role.dates.start_format, role.dates.end_format):
        checks.append("Which months did you start and finish in this title?")
    return checks


def _framing(text: str) -> tuple[str, str]:
    text = re.sub(r"\s+", " ", text).strip() or "Untitled"
    if len(text) <= _HEADLINE_MAX:
        return text, ""
    cut = text[: _HEADLINE_MAX - 1].rsplit(" ", 1)[0]
    return cut + "…", text


def _employment_facts(employment: Employment) -> dict[str, FactValue]:
    facts: dict[str, FactValue] = {
        "employer": employment.organization or "",
        "employment_type": employment.employment_type or "",
        "location": employment.location or "",
        **_span(employment.dates),
    }
    if employment.section == "volunteer":
        facts["role_type"] = "volunteer"
    if employment.dates is not None and not employment.tenure_written:
        # Worked out from the titles' dates; the resume doesn't state it.
        facts["tenure"] = "from positions"
    return facts


def _position_facts(role: Role, employment: Employment) -> dict[str, FactValue]:
    facts: dict[str, FactValue] = {"title": role.title or "", **_span(role.dates)}
    if role.location and role.location != employment.location:
        facts["location"] = role.location
    if role.employment_type and role.employment_type != employment.employment_type:
        facts["employment_type"] = role.employment_type
    return facts


def _engagement_facts(role: Role) -> dict[str, FactValue]:
    return {
        "client": role.client or "",
        "title": role.title or "",
        "location": role.location or "",
        **_span(role.dates),
    }


def _span(dates: DateRange | None) -> dict[str, FactValue]:
    facts: dict[str, FactValue] = {}
    if dates is None:
        return facts
    if dates.start is not None:
        facts["start"] = dates.start.iso()
    if dates.current:
        facts["end"] = "present"
    elif dates.end is not None:
        facts["end"] = dates.end.iso()
    return facts


def _own(role: Role, employment: Employment) -> list[int]:
    """The role's own lines, without the employer line its employment cites."""
    own = [b for b in role.header_blocks if b not in employment.header_blocks]
    return own or role.header_blocks


# "24/7" says always on; it isn't two figures.
_ROUND_THE_CLOCK = re.compile(r"\b24\s*[/x]\s*7\b", re.IGNORECASE)
# A capitalised word right before a number, past the start: "Dynamics 365", "Windows 11".
_NAMED_BEFORE = re.compile(r"(?<=\S)\s+[A-Z][A-Za-z]*\s$")


def _figures(text: str) -> dict[str, FactValue]:
    """The numbers in a line, leaving out ones that are part of a name or "24/7"."""
    text = _ROUND_THE_CLOCK.sub(" ", text)
    figures: list[str] = []
    for m in _NUMBER.finditer(text):
        token = m.group(0).strip()
        before = text[: m.start()]
        if before[-1:].isalpha():
            continue  # part of a word or code, like "Q3" or "S4"
        if token.isdigit() and _NAMED_BEFORE.search(before):
            continue
        figures.append(token)
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
