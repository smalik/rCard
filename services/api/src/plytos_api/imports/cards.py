"""Proposes cards from a parsed resume.

Every proposal keeps the resume's own words. Nothing here rewrites them; the
person accepts, edits or drops each card, and only accepted cards are saved.
"""

import re

from plytos_api.cards.model import FactValue, Framing, MainContent
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
_BODY_MAX = 5000


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
            bullets = {b.block: b for b in role.bullets}
            lines = [(b.block, b.text, b.bullet_char is not None) for b in role.bullets]
            for run in _wrapped(lines):
                lead = bullets[run[0][0]]
                extra: dict[str, FactValue] = {"workstream": lead.group} if lead.group else {}
                if len(run) == 1 and lead.bullet_char is not None:
                    pieces = [(lead.text, [lead.block])]
                else:
                    # A bullet that wraps onto lines of its own, or a paragraph, with no
                    # bullet mark to tell where the next begins: a card per sentence.
                    pieces = _sentences_over(run, shortest=3)
                for text, spanned in pieces:
                    add(
                        "accomplishment",
                        extra,
                        text,
                        spanned,
                        role.ref,
                        card.ref,
                    )
            if prose:
                # One proposed card per sentence of a paragraph-style role, joining
                # the lines a sentence wraps over.
                prose_lines = [(b, parsed_blocks[b], False) for b in role.description_blocks]
                for run in _wrapped(prose_lines):
                    for sentence, spanned in _sentences_over(run):
                        if len(sentence.split()) < 5:
                            continue
                        add(
                            "accomplishment",
                            {},
                            sentence,
                            spanned,
                            role.ref,
                            card.ref,
                        )

    for entry in parsed.highlights:
        # A highlight that names one client or employer belongs to that work.
        home = _named_in(entry.text, cards)
        card = add(
            "accomplishment",
            {},
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
            _dated({}, entry),
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
    for card in cards:
        card.content.framing.body = _fit(card.content.framing.body)
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
    return cut + "…", _fit(text)


def _fit(body: str) -> str:
    """A body no longer than a card holds. Only a misread runs this long (a whole job's
    lines read as one), and its lines are still there to be read again."""
    if len(body) <= _BODY_MAX:
        return body
    return body[: _BODY_MAX - 1].rsplit(" ", 1)[0] + "…"


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


_ENDS = (".", "!", "?", ":", ";")
# A line that ends on one of these words runs on to the next.
_RUNS_ON = re.compile(
    r"(?:[,&/–-]|\b(?:and|or|of|the|a|an|to|for|with|in|on|at|by|from|as|into|across))$",
    re.IGNORECASE,
)


def _wrapped(lines: list[tuple[int, str, bool]]) -> list[list[tuple[int, str]]]:
    """Lines grouped into runs where one wraps onto the next: the next line follows
    it directly, has no bullet mark of its own, and the line breaks mid-sentence
    (it starts lowercase, or the line before ends on "and", "of", a comma...).
    ``lines`` holds each line's block, text and whether it has a bullet mark."""
    runs: list[list[tuple[int, str]]] = []
    for block, text, marked in lines:
        if runs:
            prev_block, prev_text = runs[-1][-1]
            prev, nxt = prev_text.rstrip(), text.lstrip()
            if (
                block == prev_block + 1
                and not marked
                and nxt
                and not prev.endswith(_ENDS)
                and (nxt[0].islower() or _RUNS_ON.search(prev) is not None)
            ):
                runs[-1].append((block, text))
                continue
        runs.append([(block, text)])
    return runs


def _sentences_over(run: list[tuple[int, str]], shortest: int = 0) -> list[tuple[str, list[int]]]:
    """Each sentence of a run of lines, with the lines it sits on. A piece shorter
    than ``shortest`` words joins the sentence before it."""
    text = ""
    spans: list[tuple[int, int, int]] = []  # (start, end, block)
    for block, line in run:
        line = line.strip()
        if text:
            text += " "
        spans.append((len(text), len(text) + len(line), block))
        text += line
    out: list[tuple[str, list[int]]] = []
    at = 0
    for sentence in sentences(text):
        start = text.find(sentence, at)
        start = start if start >= 0 else at
        end = start + len(sentence)
        at = end
        blocks = [b for s, e, b in spans if s < end and e > start]
        if out and len(sentence.split()) < shortest:
            prev_text, prev_blocks = out[-1]
            out[-1] = (f"{prev_text} {sentence}", sorted({*prev_blocks, *blocks}))
            continue
        out.append((sentence, blocks))
    return out


def _dated(facts: dict[str, FactValue], entry: Entry) -> dict[str, FactValue]:
    if entry.dates is not None and entry.dates.end is not None:
        facts["date"] = entry.dates.end.iso()
    return facts


_DEGREE_WORD = re.compile(
    r"\b(?:Diploma|Certificate|GED|Bachelor|Master|Associate|Doctor|Doctorate)\b", re.I
)
# A date at either end of a piece of an education line: "May 2015 Lakeshore College".
_MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
_DATE_EDGE = re.compile(
    rf"^(?:{_MONTH}\s+)?(?:19|20)\d{{2}}\b[\s:,-]*|[\s:,-]*\b(?:{_MONTH}\s+)?(?:19|20)\d{{2}}$",
    re.I,
)


def _education_facts(entry: Entry) -> dict[str, FactValue]:
    facts: dict[str, FactValue] = {}
    pieces = [
        p.strip() for p in re.split(r",|\t|\s+[|–—-]\s+", " , ".join([entry.text, *entry.details]))
    ]
    for piece in pieces:
        piece = _DATE_EDGE.sub("", piece).strip()
        if not piece:
            continue
        # "High School Diploma" is a degree; "Lincoln High School" is a school.
        degree = _DEGREE.search(piece) and (not _SCHOOL.search(piece) or _DEGREE_WORD.search(piece))
        if "degree" not in facts and degree:
            facts["degree"] = piece
        elif "institution" not in facts and _SCHOOL.search(piece):
            facts["institution"] = piece
    return _dated(facts, entry)
