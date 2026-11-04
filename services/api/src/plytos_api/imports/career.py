"""Groups a resume's roles into employments.

An employment is one continuous stretch with one employer. Its titles become
positions inside it, and client engagements sit under the agency or
consulting role they were done in. A resume with promotions often writes the
employer and the whole tenure once, then each title with its own dates:

    Northwind Logistics, Chicago IL                Mar 2014 - Present
    Director                                       Jan 2021 - Present
    Senior Manager                                 Jun 2017 - Dec 2020

That is one employment (Mar 2014 - Present) holding two positions, not two
unrelated jobs, and the tenure line is kept rather than thrown away.
"""

from __future__ import annotations

import re

from plytos_api.imports.dates import find_range
from plytos_api.imports.model import DateRange, Employment, Role, YearMonth

# A longer gap between two stints at the same employer reads as leaving and
# coming back: two employments, not one.
REJOIN_GAP_MONTHS = 6

_OPEN = 10**7  # an end still in progress sorts after every real date


def group_employments(roles: list[Role], texts: dict[int, str]) -> list[Employment]:
    """Groups roles in resume order and sets each role's employment_ref."""
    employments: list[Employment] = []
    members: dict[str, list[Role]] = {}
    by_ref = {r.ref: r for r in roles}
    for role in roles:
        parent = by_ref.get(role.parent_ref or "")
        if role.client and parent is not None and parent.employment_ref is not None:
            # A client engagement belongs to the employment of its agency role.
            role.employment_ref = parent.employment_ref
            employment = next(e for e in employments if e.ref == parent.employment_ref)
            employment.role_refs.append(role.ref)
            continue
        current = employments[-1] if employments else None
        if current is not None and _continues(current, members[current.ref], role):
            current.role_refs.append(role.ref)
            members[current.ref].append(role)
            if role.employer_block is not None and role.employer_block not in current.header_blocks:
                current.header_blocks.append(role.employer_block)
        else:
            current = Employment(
                ref=f"employment-{len(employments) + 1}",
                section=role.section,
                header_blocks=[role.employer_block] if role.employer_block is not None else [],
                role_refs=[role.ref],
            )
            employments.append(current)
            members[current.ref] = [role]
        role.employment_ref = current.ref
    for employment in employments:
        _settle(employment, members[employment.ref], texts)
        _describe(employment, members[employment.ref], texts)
    return employments


def settle_employments(
    employments: list[Employment], roles: list[Role], texts: dict[int, str]
) -> list[Employment]:
    """Fills in employments a reader already grouped: each role names its
    employment in employment_ref. Employments left without a role are dropped."""
    members: dict[str, list[Role]] = {e.ref: [] for e in employments}
    for role in roles:
        if role.employment_ref in members:
            members[role.employment_ref].append(role)
    kept = [e for e in employments if members[e.ref]]
    for employment in kept:
        employment.role_refs = [r.ref for r in members[employment.ref]]
        _settle(employment, members[employment.ref], texts)
        _describe(employment, members[employment.ref], texts)
    return kept


def _describe(employment: Employment, held: list[Role], texts: dict[int, str]) -> None:
    """Keeps what the resume says about the employer itself."""
    lines = sorted(
        {b for r in held for b in r.employer_description_blocks if b in texts}
        | {b for b in employment.description_blocks if b in texts}
    )
    if lines:
        employment.description_blocks = lines
        employment.description = " ".join(texts[b].strip() for b in lines)


def _continues(employment: Employment, held: list[Role], role: Role) -> bool:
    if role.section != employment.section or role.client:
        return False
    previous = held[-1]
    if role.employment_key is not None and previous.employment_key is not None:
        # The reader said which employment each title is in.
        return role.employment_key == previous.employment_key
    if role.employer_block is not None and role.employer_block in employment.header_blocks:
        return True
    name = _name(role.organization)
    if not name or name != _name(previous.organization):
        return False
    if role.dates is None or previous.dates is None:
        return True
    return _gap(role.dates, previous.dates) <= REJOIN_GAP_MONTHS


def _settle(employment: Employment, held: list[Role], texts: dict[int, str]) -> None:
    """Fills in the employer, place and tenure from the positions it holds, where
    the employer's own line didn't already give them."""
    if employment.organization is None:
        named = [r for r in held if r.organization]
        employment.organization = named[0].organization if named else None
        employment.organization_inferred = bool(named) and all(
            r.organization_inferred for r in named
        )
    if employment.location is None:
        places = {r.location for r in held if r.location}
        employment.location = places.pop() if len(places) == 1 else None
    employment.employment_type = next((r.employment_type for r in held if r.employment_type), None)
    if employment.dates is not None and employment.tenure_written:
        return
    for block in employment.header_blocks:
        written = find_range(texts.get(block, ""))
        if written is not None and written.start is not None:
            employment.dates, employment.tenure_written = written, True
            return
    if len(held) == 1:
        employment.dates = held[0].dates
        employment.tenure_written = held[0].dates is not None
        return
    employment.dates = span([r.dates for r in held if r.dates is not None])


def span(ranges: list[DateRange]) -> DateRange | None:
    """The stretch that covers every range: earliest start to latest end."""
    starts = [r.start for r in ranges if r.start is not None]
    if not starts:
        return None
    start = min(starts, key=lambda d: d.ordinal())
    current = any(r.current for r in ranges)
    ends = [r.end for r in ranges if r.end is not None]
    end: YearMonth | None = None if current or not ends else max(ends, key=_end_ordinal)
    if not current and end is None:
        return None
    return DateRange(
        raw=f"{_written(start)} – {'Present' if current else _written(end)}",
        start=start,
        end=end,
        current=current,
        start_format=None,
        end_format=None,
        separator=" – ",
    )


def _gap(a: DateRange, b: DateRange) -> int:
    """Months between two ranges; zero or less when they touch or overlap."""
    if a.start is None or b.start is None:
        return 0
    a_end = _OPEN if a.current or a.end is None else a.end.ordinal(end=True)
    b_end = _OPEN if b.current or b.end is None else b.end.ordinal(end=True)
    return max(a.start.ordinal(), b.start.ordinal()) - min(a_end, b_end) - 1


def _end_ordinal(d: YearMonth) -> int:
    return d.ordinal(end=True)


_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _written(d: YearMonth | None) -> str:
    if d is None:
        return ""
    return f"{_MONTHS[d.month - 1]} {d.year}" if d.month else str(d.year)


_SUFFIX = re.compile(r"\b(inc|llc|ltd|corp|corporation|co|company|plc|gmbh|lp|llp)\b\.?", re.I)


def _name(organization: str | None) -> str:
    if not organization:
        return ""
    name = _SUFFIX.sub("", organization.lower())
    return re.sub(r"[^a-z0-9]+", " ", name).strip()
