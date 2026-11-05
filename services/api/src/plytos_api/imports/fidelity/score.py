"""Scores an import's reading of a resume against the career it was written from.

Nothing is fuzzy about what's right: the career says which employer each title sits
under, which title each accomplishment sits under, its workstream, and which section
everything else belongs to. The score counts what came through whole and in the right
place, and names each thing that didn't, so a layout's weak spots can be read off.

A reading is good when nothing is lost, nothing is put in the wrong place, and nothing
is invented: `fidelity` is what came through right over everything there was to get,
with each card that matches nothing in the career counted against it.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable

from pydantic import BaseModel, Field, computed_field

from plytos_api.cards.model import FactValue
from plytos_api.imports.fidelity.layouts import Layout
from plytos_api.imports.fidelity.truth import PRESENT, Career, Employment, Position
from plytos_api.imports.model import Contact, ImportResult, ProposedCard


class Tally(BaseModel):
    right: int = 0
    of: int = 0

    def add(self, ok: bool) -> bool:
        self.of += 1
        self.right += int(ok)
        return ok

    def plus(self, other: Tally) -> Tally:
        return Tally(right=self.right + other.right, of=self.of + other.of)


# Notes what went wrong, and marks the cards it went wrong on.
Miss = Callable[..., None]


class Score(BaseModel):
    career: str
    layout: str
    kind: str
    # The error's class when the import failed outright. Everything then counts as lost.
    failed: str | None = None
    # One employment card per employer, its name exactly as written.
    employers: Tally = Field(default_factory=Tally)
    # One title per position, under the right employer.
    positions: Tally = Field(default_factory=Tally)
    # Each employment's and each title's start and end.
    dates: Tally = Field(default_factory=Tally)
    # Each accomplishment as a card of its own, whole, under its own title.
    items: Tally = Field(default_factory=Tally)
    # Each accomplishment written under a workstream label, carrying that label.
    groups: Tally = Field(default_factory=Tally)
    # Each title's accomplishments, kept in the order they were written.
    order: Tally = Field(default_factory=Tally)
    # The summary, highlights, skills, education, awards and talks, each in its place.
    others: Tally = Field(default_factory=Tally)
    # Name, email, phone and location.
    contact: Tally = Field(default_factory=Tally)
    # What went wrong with the accomplishments. One can be both merged and misplaced.
    misattributed: int = 0  # under another title or employer
    unplaced: int = 0  # under no title at all
    merged: int = 0  # on a card that also holds other words
    split: int = 0  # across more than one card
    missing: int = 0  # nowhere
    wrong_kind: int = 0  # on a card that isn't an accomplishment
    # Employers read as more than one employment.
    employers_split: int = 0
    # Cards that match nothing in the career: invented, a heading taken for content,
    # or an employer that isn't one.
    extra: int = 0
    # Cards that carry a question, and how many of the wrong things carried one.
    asked: int = 0
    asked_wrong: int = 0
    lines: int = 0
    guessed: int = 0
    cost_usd: float = 0.0
    seconds: float = 0.0
    misses: list[str] = Field(default_factory=list)

    @property
    def tallies(self) -> list[Tally]:
        return [
            self.employers,
            self.positions,
            self.dates,
            self.items,
            self.groups,
            self.order,
            self.others,
            self.contact,
        ]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def fidelity(self) -> float:
        right = sum(t.right for t in self.tallies)
        of = sum(t.of for t in self.tallies) + self.extra
        return round(right / of, 4) if of else 1.0


# -- comparing words ---------------------------------------------------------------


def norm(text: str) -> str:
    """Words as compared: case, punctuation and spacing don't count; figures do."""
    text = unicodedata.normalize("NFKC", text).lower().replace("’", "'")
    text = re.sub(r"[^a-z0-9%$&'.+ ]+", " ", text)
    # A full stop that ends a sentence, not the one in $1.2M.
    text = re.sub(r"\.(?=\s|$)", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def card_text(card: ProposedCard) -> str:
    framing = card.content.framing
    head = norm(framing.headline.rstrip("…"))
    body = norm(framing.body)
    if not body:
        return head
    # A long line keeps its whole text in the body, cut short in the headline.
    return body if body.startswith(head) else f"{head} {body}"


def _short(text: str, most: int = 48) -> str:
    return text if len(text) <= most else text[: most - 1].rstrip() + "…"


def _same_date(found: FactValue | None, want: str, years_only: bool) -> bool:
    if not isinstance(found, str):
        return False
    if want == PRESENT:
        return found == "present"
    return found[:4] == want[:4] if years_only else found == want


def _year_of(card: ProposedCard) -> str | None:
    date = card.content.facts.get("date")
    return date[:4] if isinstance(date, str) else None


# -- the reading -------------------------------------------------------------------


def _home(reading: _Reading, card: ProposedCard) -> tuple[Employment | None, Position | None]:
    employment, title = reading.ancestors(card)
    return reading.employer_of(employment), reading.position_of(title)


class _Reading:
    """A reading's cards, with what each stands for in the career."""

    def __init__(self, career: Career, cards: list[ProposedCard]) -> None:
        self.career = career
        self.cards = cards
        self.by_ref = {c.ref: c for c in cards}
        self.order = {c.ref: i for i, c in enumerate(cards)}
        self.text = {c.ref: card_text(c) for c in cards}
        self.used: set[str] = set()

    def ancestors(self, card: ProposedCard) -> tuple[ProposedCard | None, ProposedCard | None]:
        """The employment and the title a card sits under, if any."""
        employment = title = None
        seen: set[str] = set()
        at = self.by_ref.get(card.parent_ref or "")
        while at is not None and at.ref not in seen:
            seen.add(at.ref)
            if at.kind in ("position", "engagement") and title is None:
                title = at
            if at.kind == "employment":
                employment = at
                break
            at = self.by_ref.get(at.parent_ref or "")
        return employment, title

    def employer_of(self, card: ProposedCard | None) -> Employment | None:
        """The career's employer an employment card names, if it names one."""
        if card is None:
            return None
        employer = card.content.facts.get("employer")
        name = norm(employer if isinstance(employer, str) and employer else "")
        name = name or self.text[card.ref]
        named = [e for e in self.career.employments if norm(e.employer) in name]
        return max(named, key=lambda e: len(e.employer)) if named else None

    def position_of(self, card: ProposedCard | None) -> Position | None:
        """The career's title a position card stands for: by its title, under its
        employer; or the employer's only title, when its title was misread."""
        if card is None:
            return None
        employment, _ = self.ancestors(card)
        employer = self.employer_of(employment)
        everywhere = [p for e in self.career.employments for p in e.positions]
        pools = [employer.positions, everywhere] if employer else [everywhere]
        title = card.content.facts.get("title")
        name = norm(title if isinstance(title, str) and title else self.text[card.ref])
        # The title exactly, under its employer or anywhere; then a title with more
        # words around it (dates, the employer), the longest that fits.
        for pool in pools:
            exact = [p for p in pool if norm(p.title) == name]
            if exact:
                return exact[0]
        for pool in pools:
            within = [p for p in pool if norm(p.title) in name]
            if within:
                return max(within, key=lambda p: len(p.title))
        return employer.positions[0] if employer and len(employer.positions) == 1 else None

    def holding(self, text: str) -> list[ProposedCard]:
        """Cards holding these words, the ones holding nothing else first."""
        want = norm(text)
        found = [c for c in self.cards if want in self.text[c.ref]]
        return sorted(
            found,
            key=lambda c: (
                self.text[c.ref] != want,
                c.kind != "accomplishment",
                len(self.text[c.ref]),
            ),
        )

    def pieces(self, text: str) -> list[ProposedCard]:
        """Cards that each hold part of these words, when together they hold most."""
        want = norm(text)
        parts = [
            c
            for c in self.cards
            if c.kind == "accomplishment"
            and len(self.text[c.ref]) >= 12
            and self.text[c.ref] in want
            and self.text[c.ref] != want
        ]
        covered = sum(len(self.text[c.ref]) for c in parts)
        return parts if parts and covered >= 0.8 * len(want) else []


# -- scoring -----------------------------------------------------------------------


def score(
    career: Career,
    layout: Layout,
    result: ImportResult | None,
    *,
    failed: str | None = None,
) -> Score:
    """How well a reading of `career`, written in `layout`, came through."""
    out = Score(career=career.key, layout=layout.name, kind=layout.kind, failed=failed)
    cards = result.cards if result is not None else []
    reading = _Reading(career, cards)
    wrong: set[str] = set()
    years_only = layout.years_only

    def miss(note: str, *on: ProposedCard) -> None:
        out.misses.append(note)
        wrong.update(c.ref for c in on)

    # Employers, each read as one employment with its name exactly as written.
    employment_cards = [c for c in cards if c.kind == "employment"]
    for employment in career.employments:
        read_as = [c for c in employment_cards if reading.employer_of(c) is employment]
        reading.used.update(c.ref for c in read_as)
        if len(read_as) > 1:
            out.employers_split += 1
            miss(f"{employment.employer} read as {len(read_as)} employments", *read_as)
        if not read_as:
            out.employers.add(False)
            miss(f"{employment.employer} not found")
            out.dates.of += 2
            continue
        card = read_as[0]
        named = card.content.facts.get("employer")
        exact = isinstance(named, str) and norm(named) == norm(employment.employer)
        if not out.employers.add(exact and len(read_as) == 1) and not exact:
            if isinstance(named, str) and named:
                miss(f"{employment.employer} read as “{_short(named)}”", card)
            else:
                miss(
                    f"{employment.employer} without its name: “{_short(reading.text[card.ref])}”",
                    card,
                )
        for key, want in (("start", employment.start), ("end", employment.end)):
            found = card.content.facts.get(key)
            if not out.dates.add(_same_date(found, want, years_only)):
                miss(f"{employment.employer} {key} read as {found or 'nothing'}, not {want}", card)
    for card in employment_cards:
        if card.ref not in reading.used:
            out.extra += 1
            reading.used.add(card.ref)
            miss(f"An employment that isn't one: “{_short(reading.text[card.ref])}”", card)

    # Titles, each once, under the right employer, with their dates.
    title_cards = [c for c in cards if c.kind in ("position", "engagement")]
    for employment in career.employments:
        for position in employment.positions:
            read_as = [c for c in title_cards if reading.position_of(c) is position]
            reading.used.update(c.ref for c in read_as)
            if not read_as:
                out.positions.add(False)
                miss(f"{position.title} at {employment.employer} not found")
                out.dates.of += 2
                continue
            card = read_as[0]
            under, _ = reading.ancestors(card)
            title = card.content.facts.get("title")
            ok = (
                len(read_as) == 1
                and isinstance(title, str)
                and norm(title) == norm(position.title)
                and reading.employer_of(under) is employment
            )
            if not out.positions.add(ok):
                put = reading.employer_of(under)
                why = (
                    f"read {len(read_as)} times"
                    if len(read_as) > 1
                    else f"read as “{_short(str(title or ''))}”"
                    if not isinstance(title, str) or norm(title) != norm(position.title)
                    else f"under {put.employer if put else 'an employer that isn’t one'}"
                )
                miss(f"{position.title} at {employment.employer} {why}", *read_as)
            for key, want in (("start", position.start), ("end", position.end)):
                found = card.content.facts.get(key)
                if not out.dates.add(_same_date(found, want, years_only)):
                    miss(f"{position.title} {key} read as {found or 'nothing'}, not {want}", card)
    for card in title_cards:
        if card.ref not in reading.used:
            out.extra += 1
            reading.used.add(card.ref)
            miss(f"A title that isn't one: “{_short(reading.text[card.ref])}”", card)

    # Accomplishments: each whole, on a card of its own, under its own title.
    for employment in career.employments:
        for position in employment.positions:
            placed: list[int] = []
            for group in position.groups:
                for item in group.items:
                    first = _score_item(out, reading, employment, position, group.label, item, miss)
                    if first is not None:
                        placed.append(reading.order[first.ref])
            if len(placed) >= 2 and not out.order.add(placed == sorted(placed)):
                miss(f"{position.title}'s accomplishments out of order")

    _score_others(out, reading, career, layout, miss)
    if result is not None:
        _score_contact(out, result.contact, career, miss)
    else:
        out.contact.of += 4

    # Anything else on a card is something the career doesn't have.
    for card in cards:
        if card.ref not in reading.used:
            out.extra += 1
            miss(
                f"A card that matches nothing ({card.kind}): “{_short(reading.text[card.ref])}”",
                card,
            )

    asked = {c.ref for c in cards if c.needs_check}
    out.asked = len(asked)
    out.asked_wrong = len(asked & wrong)
    if result is not None and result.lines is not None:
        out.lines = result.lines.lines
        out.guessed = len(result.lines.guessed)
    if result is not None and result.usage is not None:
        out.cost_usd = result.usage.cost_usd
    return out


def _score_item(
    out: Score,
    reading: _Reading,
    employment: Employment,
    position: Position,
    label: str | None,
    item: str,
    miss: Miss,
) -> ProposedCard | None:
    """Scores one accomplishment; returns the card it begins on, if found."""
    short = _short(item)
    holders = reading.holding(item)
    if holders:
        card = holders[0]
        cards = [card]
        whole = reading.text[card.ref] == norm(item)
        if not whole:
            out.merged += 1
            miss(f"“{short}” merged into a longer card", card)
    else:
        cards = reading.pieces(item)
        if not cards:
            out.items.add(False)
            out.missing += 1
            miss(f"“{short}” lost")
            if label is not None:
                out.groups.add(False)
            return None
        cards.sort(key=lambda c: reading.order[c.ref])
        card = cards[0]
        whole = False
        out.split += 1
        miss(f"“{short}” split across {len(cards)} cards", *cards)
    reading.used.update(c.ref for c in cards)

    kind_ok = all(c.kind == "accomplishment" for c in cards)
    if not kind_ok:
        out.wrong_kind += 1
        miss(f"“{short}” on a card that isn't an accomplishment ({card.kind})", card)
    # Where the person would see it: the title it sits under, and that title's employer.
    homes = {tuple(map(id, _home(reading, c))) for c in cards}
    employer, home = _home(reading, card)
    if home is None:
        out.unplaced += 1
        miss(f"“{short}” under no title", card)
    elif len(homes) > 1 or home is not position or employer is not employment:
        out.misattributed += 1
        where = f"{home.title} at {employer.employer if employer else 'no employer'}"
        miss(f"“{short}” under {where}, not {position.title} at {employment.employer}", card)
    placed = home is position and employer is employment and len(homes) == 1
    out.items.add(whole and kind_ok and placed)

    stream = card.content.facts.get("workstream")
    if label is not None:
        if not out.groups.add(isinstance(stream, str) and norm(stream) == norm(label)):
            miss(f"“{short}” lost its workstream {label}", card)
    elif stream:
        out.groups.add(False)
        miss(f"“{short}” given a workstream it doesn't have: {stream}", card)
    return card


def _score_others(
    out: Score, reading: _Reading, career: Career, layout: Layout, miss: Miss
) -> None:
    style = layout.style

    def find(text: str, kinds: Iterable[str]) -> ProposedCard | None:
        holders = reading.holding(text)
        if not holders:
            return None
        card = next((c for c in holders if c.kind in kinds), holders[0])
        reading.used.add(card.ref)
        return card

    summary = find(career.summary, ["story"])
    if not out.others.add(summary is not None and summary.kind == "story"):
        miss(
            "The summary " + (f"on a card ({summary.kind})" if summary else "lost"),
            *([summary] if summary else []),
        )

    for highlight in career.highlights if style.highlights else []:
        card = find(highlight.text, ["accomplishment"])
        short = _short(highlight.text)
        if card is None:
            out.others.add(False)
            miss(f"Highlight “{short}” lost")
            continue
        employment, _ = reading.ancestors(card)
        under = reading.employer_of(employment)
        want = highlight.names
        placed = (
            (under is None and card.parent_ref is None)
            if want is None
            else (under is not None and under.employer == want)
        )
        ok = (
            card.kind == "accomplishment"
            and placed
            and reading.text[card.ref] == norm(highlight.text)
        )
        if not out.others.add(ok):
            where = under.employer if under else "nothing"
            miss(f"Highlight “{short}” on a card ({card.kind}) under {where}", card)

    skill_cards = [c for c in reading.cards if c.kind == "skill"]
    for group in career.skills:
        listed = {norm(s) for s in group.items}
        match = None
        for card in skill_cards:
            category = card.content.facts.get("category")
            if isinstance(category, str) and norm(category) == norm(group.category):
                match = card
                break
        if match is not None:
            reading.used.add(match.ref)
        skills = match.content.facts.get("skills") if match is not None else None
        got = {norm(s) for s in skills} if isinstance(skills, list) else set()
        if not out.others.add(match is not None and got == listed):
            miss(
                f"Skills “{group.category}” read as {sorted(got) or 'nothing'}",
                *([match] if match else []),
            )

    for school in career.education:
        card = find(school.school, ["education"])
        institution = card.content.facts.get("institution") if card else None
        degree = card.content.facts.get("degree") if card else None
        ok = (
            card is not None
            and card.kind == "education"
            and isinstance(institution, str)
            and norm(institution) == norm(school.school)
            and isinstance(degree, str)
            and norm(school.degree) in norm(degree)
            and norm(school.field) in norm(degree)
            and _year_of(card) == school.year
        )
        if not out.others.add(ok):
            miss(
                f"Education at {school.school}: "
                + (f"{card.kind}, {card.content.facts}" if card else "lost"),
                *([card] if card else []),
            )

    for award in career.awards:
        card = find(award.name, ["accomplishment"])
        ok = (
            card is not None
            and card.kind == "accomplishment"
            and "award" in card.content.facts
            and _year_of(card) == award.year
        )
        if not out.others.add(ok):
            miss(
                f"Award “{award.name}”: "
                + (f"{card.kind}, year {_year_of(card)}" if card else "lost"),
                *([card] if card else []),
            )

    for talk in career.talks:
        card = find(talk.text, ["activity"])
        ok = card is not None and card.kind == "activity" and _year_of(card) == talk.year
        if not out.others.add(ok):
            year = _year_of(card) if card else None
            miss(
                f"Talk “{_short(talk.text)}”: "
                + (f"{card.kind}, year {year}, not {talk.year}" if card else "lost"),
                *([card] if card else []),
            )


def _score_contact(out: Score, contact: Contact, career: Career, miss: Miss) -> None:
    def digits(text: str) -> str:
        return re.sub(r"\D", "", text)

    checks = [
        ("name", contact.name is not None and norm(contact.name) == norm(career.name)),
        ("email", career.email.lower() in [e.lower() for e in contact.emails]),
        ("phone", digits(career.phone) in [digits(p) for p in contact.phones]),
        (
            "location",
            contact.location is not None and norm(contact.location) == norm(career.location),
        ),
    ]
    for field, ok in checks:
        if not out.contact.add(ok):
            miss(f"Contact {field} not read")


# -- reporting ---------------------------------------------------------------------


def total(scores: Iterable[Score], label: str = "all") -> Score:
    """Scores added together."""
    sum_ = Score(career="*", layout=label, kind="*")
    for s in scores:
        for name in (
            "employers",
            "positions",
            "dates",
            "items",
            "groups",
            "order",
            "others",
            "contact",
        ):
            setattr(sum_, name, getattr(sum_, name).plus(getattr(s, name)))
        for name in (
            "misattributed",
            "unplaced",
            "merged",
            "split",
            "missing",
            "wrong_kind",
            "employers_split",
            "extra",
            "asked",
            "asked_wrong",
            "lines",
            "guessed",
        ):
            setattr(sum_, name, getattr(sum_, name) + getattr(s, name))
        sum_.cost_usd += s.cost_usd
        sum_.seconds += s.seconds
        if s.failed:
            sum_.misses.append(f"{s.career}/{s.layout} failed: {s.failed}")
    return sum_


def baseline(scores: Iterable[Score]) -> dict[str, dict[str, float | int]]:
    """The floor each Word and PDF layout is held to in CI: no less right, no more
    in the wrong place or lost. Scans and Word-saved PDFs need Claude or LibreOffice,
    which CI doesn't have."""
    return {
        f"{s.career}/{s.layout}": {
            "fidelity": s.fidelity,
            "wrong_place": s.misattributed + s.unplaced,
            "missing": s.missing,
        }
        for s in scores
        if s.kind in ("docx", "pdf") and not s.failed
    }


def _pct(t: Tally) -> str:
    return f"{100 * t.right / t.of:.0f}%" if t.of else "–"


def report(scores: list[Score], *, title: str = "Import fidelity") -> str:
    """A Markdown report: overall, by layout, by kind of file, then what went wrong."""
    lines = [f"# {title}", ""]
    everything = total(scores)
    runs = len(scores)
    failed = sum(1 for s in scores if s.failed)
    lines += [
        f"{runs} resumes read ({failed} failed). Fidelity {100 * everything.fidelity:.1f}%: "
        f"{everything.misattributed} accomplishments in the wrong place, "
        f"{everything.missing} lost, {everything.merged} merged, {everything.split} split, "
        f"{everything.extra} cards that match nothing.",
        "",
    ]
    if everything.cost_usd:
        lines += [
            f"Claude cost ${everything.cost_usd:.4f} in all, "
            f"${everything.cost_usd / max(runs, 1):.4f} a resume; "
            f"{everything.seconds / max(runs, 1):.0f} s a resume on average.",
            "",
        ]
    header = (
        "| | Fidelity | Employers | Titles | Dates | Accomplishments | Wrong place | Lost "
        "| Merged/split | Workstreams | Order | Other sections | Contact | Extra | Questions "
        "(on wrong) |"
    )
    rule = "|" + "---|" * 15

    def row(name: str, s: Score) -> str:
        return (
            f"| {name} | {100 * s.fidelity:.0f}% | {_pct(s.employers)} | {_pct(s.positions)} "
            f"| {_pct(s.dates)} | {_pct(s.items)} | {s.misattributed + s.unplaced} | {s.missing} "
            f"| {s.merged}/{s.split} | {_pct(s.groups)} | {_pct(s.order)} | {_pct(s.others)} "
            f"| {_pct(s.contact)} | {s.extra} | {s.asked} ({s.asked_wrong}) |"
        )

    lines += ["## By layout", "", header, rule]
    for name in dict.fromkeys(s.layout for s in scores):
        lines.append(row(name, total(s for s in scores if s.layout == name)))
    lines += ["", "## By kind of file", "", header, rule]
    for kind in dict.fromkeys(s.kind for s in scores):
        lines.append(row(kind, total(s for s in scores if s.kind == kind)))
    lines += ["", "## By career", "", header, rule]
    for key in dict.fromkeys(s.career for s in scores):
        lines.append(row(key, total(s for s in scores if s.career == key)))
    lines += ["", "## What went wrong", ""]
    for s in scores:
        if s.failed:
            lines.append(f"- **{s.career}/{s.layout}** failed: {s.failed}")
        elif s.misses:
            lines.append(f"- **{s.career}/{s.layout}**")
            lines += [f"  - {note}" for note in s.misses[:25]]
            if len(s.misses) > 25:
                lines.append(f"  - and {len(s.misses) - 25} more")
    lines.append("")
    return "\n".join(lines)
