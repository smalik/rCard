"""Scores an import's reading of a resume against the career it was written from.

Nothing is fuzzy about what's right: the career says which employer each title sits
under, which title each accomplishment sits under, its workstream, and which section
everything else belongs to. The score counts what came through whole and in the right
place, and names each thing that didn't, so a layout's weak spots can be read off.

A reading is good when nothing is lost, nothing is put in the wrong place, and nothing
is invented: `fidelity` is what came through right over everything there was to get,
with each card that matches nothing in the career counted against it.

Real resumes are scored the same way against labels (truth.py). Their words are matched
nearly as well as exactly, since a scan's are read from a picture; what a label leaves
out is neither scored nor counted as invented. A real resume's misses hold its words,
so they stay on the machine it's on: `report(private=True)` gives counts only.
"""

from __future__ import annotations

import html
import re
import unicodedata
from collections.abc import Callable, Iterable
from difflib import SequenceMatcher

from pydantic import BaseModel, Field, computed_field

from plytos_api.cards.model import FactValue
from plytos_api.imports.fidelity.layouts import Layout
from plytos_api.imports.fidelity.truth import PRESENT, Career, Employment, Position
from plytos_api.imports.model import Contact, ImportResult, ProposedCard
from plytos_api.imports.segment import is_generic_label


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
    # Accomplishments found only by words nearly the same (a scan misread, say).
    garbled: int = 0
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
    # How many of each kind of miss: what can be reported without a resume's words.
    kinds: dict[str, int] = Field(default_factory=dict)
    # The kinds of miss marked on each card, by its ref: where a reading went wrong,
    # to look at without its words (shape.py).
    marks: dict[str, list[str]] = Field(default_factory=dict)

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


def _unmangle(text: str) -> str:
    """Text that was UTF-8 read as Windows-1252, as text copied out of some PDFs is
    (a curly quote as three odd letters), put back."""
    if not any(sign in text for sign in ("â€", "Ã", "Â")):
        return text
    try:
        return text.encode("cp1252").decode("utf-8")
    except UnicodeError:
        return text.replace("Â", " ")


def norm(text: str) -> str:
    """Words as compared: case, punctuation and spacing don't count; figures do."""
    text = _unmangle(html.unescape(text))
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


# How alike two texts must be to count as the same words misread.
NEARLY = 0.9

# "(Contract)" after a title says how the person was employed, which a reading may
# well file as the job's employment type instead of keeping it in the title.
_HOW_EMPLOYED = re.compile(
    r"\s*\((?:contract(?:or)?|freelance|part[- ]time|full[- ]time|internship|intern|"
    r"temporary|temp|seasonal|interim)\)\s*$",
    re.IGNORECASE,
)


def same_title(read: str, label: str) -> bool:
    """Whether a title as read is the label's, with or without how the person was
    employed after it."""
    have = norm(read)
    return have == norm(label) or (bool(have) and have == norm(_HOW_EMPLOYED.sub("", label)))


def _share_words(a: str, b: str) -> bool:
    """A cheap test before a slow one: most of a's words are in b."""
    words = set(a.split())
    return bool(words) and len(words & set(b.split())) >= 0.6 * len(words)


def nearly(a: str, b: str, at_least: float = NEARLY) -> bool:
    """Normalized texts that are the same words, give or take a few letters."""
    if not a or not b or min(len(a), len(b)) < at_least * max(len(a), len(b)):
        return False
    if not _share_words(a, b):
        return False
    return SequenceMatcher(None, a, b, autojunk=False).ratio() >= at_least


def nearly_within(want: str, text: str, at_least: float = NEARLY) -> bool:
    """Whether `want` is nearly all there, in order, inside the longer `text`."""
    if not want or len(text) < len(want) or not _share_words(want, text):
        return False
    blocks = SequenceMatcher(None, want, text, autojunk=False).get_matching_blocks()
    return sum(b.size for b in blocks if b.size >= 4) >= at_least * len(want)


def _short(text: str, most: int = 48) -> str:
    return text if len(text) <= most else text[: most - 1].rstrip() + "…"


def _same_date(found: FactValue | None, want: str, years_only: bool) -> bool:
    if not isinstance(found, str):
        return False
    if want == PRESENT:
        return found == "present"
    # A label that has only the year asks for no more than the year.
    return found[:4] == want[:4] if years_only or len(want) == 4 else found == want


def _year_of(card: ProposedCard) -> str | None:
    date = card.content.facts.get("date")
    return date[:4] if isinstance(date, str) else None


_A_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")


def _year_written(written: str) -> str:
    """The year a label's date stands for: "May 2014" is 2014, and "2010 - 2014"
    (years at school) is the year it ended, the one a card keeps."""
    years = _A_YEAR.findall(written)
    return years[-1] if years else written[:4]


def _dates_fit(card: ProposedCard, start: str | None, end: str | None) -> bool:
    """Whether a card's dates are the ones written, to the year."""
    if start is None and end is None:
        return False
    for key, want in (("start", start), ("end", end)):
        if want is not None and not _same_date(card.content.facts.get(key), want, True):
            return False
    return True


# -- the reading -------------------------------------------------------------------

# What a resume set writes in place of an employer's real name.
STAND_INS = {"", "company name", "company", "employer", "employer name", "your company"}


def anonymous(career: Career) -> bool:
    """Whether an employer is written as a stand-in, so which jobs were at the same
    employer can't be known."""
    return career.anonymous_employers or any(
        norm(e.employer) in STAND_INS for e in career.employments
    )


def _home(reading: _Reading, card: ProposedCard) -> tuple[Employment | None, Position | None]:
    employment, title = reading.ancestors(card)
    return reading.employer_of(employment), reading.position_of(title)


def _pick[T: (Employment, Position)](
    named: list[T], card: ProposedCard, taken: set[int]
) -> T | None:
    """Of the career's jobs or titles a card's words name, the one it stands for: the
    only one; else one whose dates fit; else the first not yet stood for, in order."""
    if len(named) <= 1:
        return named[0] if named else None
    dated = [t for t in named if _dates_fit(card, t.start, t.end)] or named
    free = [t for t in dated if id(t) not in taken]
    return (free or dated)[0]


class _Reading:
    """A reading's cards, with what each stands for in the career."""

    def __init__(self, career: Career, cards: list[ProposedCard]) -> None:
        self.career = career
        self.cards = cards
        self.by_ref = {c.ref: c for c in cards}
        self.order = {c.ref: i for i, c in enumerate(cards)}
        self.text = {c.ref: card_text(c) for c in cards}
        self.used: set[str] = set()
        self.anonymous = anonymous(career)
        # Which employer and which title each card stands for, settled in the order
        # the cards come, so two jobs with the same name are told apart by their dates
        # and then by their order.
        self._employer: dict[str, Employment | None] = {}
        self._position: dict[str, Position | None] = {}
        taken: set[int] = set()
        for card in cards:
            if card.kind == "employment":
                employment = _pick(self._employers_named(card), card, taken)
                self._employer[card.ref] = employment
                if employment is not None:
                    taken.add(id(employment))
        for card in cards:
            if card.kind in ("position", "engagement"):
                position = _pick(self._positions_named(card), card, taken)
                if position is None:
                    position = self._only_title(card)
                self._position[card.ref] = position
                if position is not None:
                    taken.add(id(position))

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

    def _fact(self, card: ProposedCard, key: str) -> str:
        value = card.content.facts.get(key)
        return norm(value) if isinstance(value, str) and value.strip() else self.text[card.ref]

    def _employers_named(self, card: ProposedCard) -> list[Employment]:
        """The career's employers an employment card names: by the name written in it,
        the longest that fits; or by nearly that name, when it was misread."""
        name = self._fact(card, "employer")
        known = [e for e in self.career.employments if norm(e.employer)]
        named = [e for e in known if norm(e.employer) in name]
        if named:
            longest = max(len(e.employer) for e in named)
            return [e for e in named if len(e.employer) == longest]
        return [e for e in known if nearly(norm(e.employer), name, 0.85)]

    def employer_of(self, card: ProposedCard | None) -> Employment | None:
        """The career's employer an employment card stands for, if any."""
        return self._employer.get(card.ref) if card is not None else None

    def _positions_named(self, card: ProposedCard) -> list[Position]:
        """The career's titles a position card names: the title exactly, under its
        employer or anywhere; then a title with more words around it (dates, the
        employer), the longest that fits; then nearly the title."""
        employment, _ = self.ancestors(card)
        employer = (
            None if self.anonymous else self._employer.get(employment.ref if employment else "")
        )
        # A title left blank can't be found by its name.
        everywhere = [p for e in self.career.employments for p in e.positions if norm(p.title)]
        mine = [p for p in employer.positions if norm(p.title)] if employer else []
        pools = [mine, everywhere] if employer else [everywhere]
        title = card.content.facts.get("title")
        if not (isinstance(title, str) and title.strip()):
            # A job with no title written, read as one: it stands for an untitled job.
            untitled = [p for e in self.career.employments for p in e.positions if not p.title]
            mine_untitled = [p for p in employer.positions if not p.title] if employer else []
            if mine_untitled or untitled:
                return mine_untitled or untitled
        name = self._fact(card, "title")
        for pool in pools:
            exact = [p for p in pool if same_title(name, p.title)]
            if exact:
                return exact
        for pool in pools:
            within = [p for p in pool if norm(p.title) in name]
            if within:
                longest = max(len(p.title) for p in within)
                return [p for p in within if len(p.title) == longest]
        for pool in pools:
            near = [p for p in pool if nearly(norm(p.title), name, 0.85)]
            if near:
                return near
        return []

    def _only_title(self, card: ProposedCard) -> Position | None:
        """The employer's only title, when the card's title was misread."""
        employment, _ = self.ancestors(card)
        employer = self._employer.get(employment.ref if employment else "")
        return employer.positions[0] if employer and len(employer.positions) == 1 else None

    def position_of(self, card: ProposedCard | None) -> Position | None:
        """The career's title a position card stands for, if any."""
        return self._position.get(card.ref) if card is not None else None

    def same(self, card: ProposedCard, text: str) -> bool:
        """Whether a card holds these words and nothing else, give or take a misread."""
        have, want = self.text[card.ref], norm(text)
        return have == want or nearly(have, want)

    def holding(self, text: str) -> list[ProposedCard]:
        """Cards holding these words, the ones holding nothing else first. Words found
        only nearly are looked for when they aren't there exactly."""
        want = norm(text)
        if not want:
            return []
        found = [c for c in self.cards if want in self.text[c.ref]]
        if not found:
            found = [
                c
                for c in self.cards
                if nearly(self.text[c.ref], want) or nearly_within(want, self.text[c.ref])
            ]
        return sorted(
            found,
            key=lambda c: (
                not self.same(c, text),
                c.ref in self.used,
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
            and self.text[c.ref] != want
            and (self.text[c.ref] in want or nearly_within(self.text[c.ref], want))
        ]
        covered = sum(len(self.text[c.ref]) for c in parts)
        return parts if parts and covered >= 0.8 * len(want) else []

    def excused(self, card: ProposedCard) -> bool:
        """Whether a card is something the label leaves out."""
        if card.kind in self.career.unscored_kinds:
            return True
        have = self.text[card.ref]
        if len(have) < 3:
            return False
        for words in self.career.unscored:
            left_out = norm(words)
            if left_out and (
                have in left_out
                or (len(left_out) >= 8 and left_out in have)
                or nearly(have, left_out, 0.85)
            ):
                return True
        return False


# -- scoring -----------------------------------------------------------------------


def score(
    career: Career,
    layout: Layout | None,
    result: ImportResult | None,
    *,
    failed: str | None = None,
    kind: str | None = None,
    name: str | None = None,
) -> Score:
    """How well a reading of `career`, written in `layout`, came through. A real
    resume has no layout: say what kind of file it is, and a name to group it by."""
    out = Score(
        career=career.key,
        layout=name or (layout.name if layout else "real"),
        kind=kind or (layout.kind if layout else "real"),
        failed=failed,
    )
    cards = result.cards if result is not None else []
    reading = _Reading(career, cards)
    wrong: set[str] = set()
    years_only = layout.years_only if layout else False
    stand_ins = reading.anonymous

    def miss(what: str, note: str, *on: ProposedCard) -> None:
        out.kinds[what] = out.kinds.get(what, 0) + 1
        out.misses.append(note)
        wrong.update(c.ref for c in on)
        for card in on:
            out.marks.setdefault(card.ref, []).append(what)

    def dates(label: str, card: ProposedCard, start: str | None, end: str | None) -> None:
        for key, want in (("start", start), ("end", end)):
            if want is None:
                continue
            found = card.content.facts.get(key)
            if not out.dates.add(_same_date(found, want, years_only)):
                miss("date", f"{label} {key} read as {found or 'nothing'}, not {want}", card)

    def written(*values: str | None) -> int:
        return sum(1 for v in values if v is not None)

    # Employers, each read as one employment with its name exactly as written. When
    # the employers are stand-ins, which jobs share one can't be known, so they aren't
    # scored.
    employment_cards = [c for c in cards if c.kind == "employment"]
    for employment in [] if stand_ins else career.employments:
        read_as = [c for c in employment_cards if reading.employer_of(c) is employment]
        reading.used.update(c.ref for c in read_as)
        if len(read_as) > 1:
            out.employers_split += 1
            miss(
                "employer read twice",
                f"{employment.employer} read as {len(read_as)} employments",
                *read_as,
            )
        if not read_as:
            out.employers.add(False)
            miss("employer lost", f"{employment.employer} not found")
            out.dates.of += written(employment.start, employment.end)
            continue
        card = read_as[0]
        named = card.content.facts.get("employer")
        exact = isinstance(named, str) and norm(named) == norm(employment.employer)
        if not out.employers.add(exact and len(read_as) == 1) and not exact:
            if isinstance(named, str) and named:
                miss(
                    "employer misread",
                    f"{employment.employer} read as “{_short(named)}”",
                    card,
                )
            else:
                miss(
                    "employer misread",
                    f"{employment.employer} without its name: “{_short(reading.text[card.ref])}”",
                    card,
                )
        dates(employment.employer, card, employment.start, employment.end)
    for card in employment_cards:
        if card.ref not in reading.used:
            reading.used.add(card.ref)
            if stand_ins:
                continue
            out.extra += 1
            miss(
                "employer invented",
                f"An employment that isn't one: “{_short(reading.text[card.ref])}”",
                card,
            )

    # Titles, each once, under the right employer, with their dates.
    title_cards = [c for c in cards if c.kind in ("position", "engagement")]
    for employment in career.employments:
        for position in employment.positions:
            read_as = [c for c in title_cards if reading.position_of(c) is position]
            reading.used.update(c.ref for c in read_as)
            if not read_as:
                out.positions.add(False)
                miss("title lost", f"{position.title} at {employment.employer} not found")
                out.dates.of += written(position.start, position.end)
                continue
            card = read_as[0]
            under, _ = reading.ancestors(card)
            title = card.content.facts.get("title")
            right_name = same_title(title if isinstance(title, str) else "", position.title)
            right_place = stand_ins or reading.employer_of(under) is employment
            if not out.positions.add(len(read_as) == 1 and right_name and right_place):
                put = reading.employer_of(under)
                if len(read_as) > 1:
                    what, why = "title read twice", f"read {len(read_as)} times"
                elif not right_name:
                    what, why = "title misread", f"read as “{_short(str(title or ''))}”"
                else:
                    what = "title under the wrong employer"
                    why = f"under {put.employer if put else 'an employer that isn’t one'}"
                miss(what, f"{position.title} at {employment.employer} {why}", *read_as)
            dates(position.title, card, position.start, position.end)
    for card in title_cards:
        if card.ref not in reading.used:
            reading.used.add(card.ref)
            if reading.excused(card):
                continue
            out.extra += 1
            miss(
                "title invented",
                f"A title that isn't one: “{_short(reading.text[card.ref])}”",
                card,
            )

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
                miss("out of order", f"{position.title}'s accomplishments out of order")

    _score_others(out, reading, career, layout, miss)
    if result is not None:
        _score_contact(out, result.contact, career, miss)
    else:
        out.contact.of += written(career.name, career.email, career.phone, career.location)

    # Anything else on a card is something the career doesn't have.
    for card in cards:
        if card.ref not in reading.used and not reading.excused(card):
            out.extra += 1
            miss(
                f"{card.kind} invented",
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
    # "Responsibilities" over a job's bullets is no workstream, whoever wrote it down.
    label = None if is_generic_label(label) else label
    short = _short(item)
    # The same words can sit under more than one job: take the copy under this one.
    holders = sorted(
        reading.holding(item),
        key=lambda c: (
            not reading.same(c, item),
            c.ref in reading.used,
            _home(reading, c)[1] is not position,
        ),
    )
    # Kept as what its own title was, above the accomplishments: the words are where
    # the person would look for them.
    if (
        holders
        and holders[0].kind in ("position", "engagement")
        and reading.position_of(holders[0]) is position
    ):
        out.items.add(True)
        miss("accomplishment kept as its title's description", f"“{short}” on its title")
        return holders[0]
    if holders:
        card = holders[0]
        cards = [card]
        whole = reading.same(card, item)
        if not whole:
            out.merged += 1
            miss("accomplishment merged", f"“{short}” merged into a longer card", card)
        elif reading.text[card.ref] != norm(item):
            out.garbled += 1
            miss("accomplishment misread", f"“{short}” read with words changed", card)
    else:
        cards = reading.pieces(item)
        if not cards:
            out.items.add(False)
            out.missing += 1
            miss("accomplishment lost", f"“{short}” lost")
            if label is not None:
                out.groups.add(False)
            return None
        cards.sort(key=lambda c: reading.order[c.ref])
        card = cards[0]
        whole = False
        out.split += 1
        miss("accomplishment split", f"“{short}” split across {len(cards)} cards", *cards)
    reading.used.update(c.ref for c in cards)

    kind_ok = all(c.kind == "accomplishment" for c in cards)
    if not kind_ok:
        out.wrong_kind += 1
        miss(
            "accomplishment as another kind",
            f"“{short}” on a card that isn't an accomplishment ({card.kind})",
            card,
        )
    # Where the person would see it: the title it sits under, and that title's employer.
    homes = {tuple(map(id, _home(reading, c))) for c in cards}
    employer, home = _home(reading, card)
    right_employer = reading.anonymous or employer is employment
    if home is None:
        out.unplaced += 1
        miss(_unplaced(reading, card), f"“{short}” under no title", card)
    elif len(homes) > 1 or home is not position or not right_employer:
        out.misattributed += 1
        where = f"{home.title} at {employer.employer if employer else 'no employer'}"
        miss(
            "accomplishment misattributed",
            f"“{short}” under {where}, not {position.title} at {employment.employer}",
            card,
        )
    placed = home is position and right_employer and len(homes) == 1
    out.items.add(whole and kind_ok and placed)

    stream = card.content.facts.get("workstream")
    if isinstance(stream, str) and is_generic_label(stream):
        stream = None
    if label is not None:
        if not out.groups.add(isinstance(stream, str) and norm(stream) == norm(label)):
            miss("workstream lost", f"“{short}” lost its workstream {label}", card)
    elif stream:
        out.groups.add(False)
        miss("workstream invented", f"“{short}” given a workstream it doesn't have: {stream}", card)
    return card


def _unplaced(reading: _Reading, card: ProposedCard) -> str:
    """What an accomplishment under no title of the career's sits under instead."""
    employment, title = reading.ancestors(card)
    if title is not None:
        return "accomplishment under a title the resume doesn't have"
    if employment is not None:
        return "accomplishment under an employer, no title"
    return "accomplishment under no job"


# What kinds of card each kind of other entry belongs on.
OTHER_KINDS = {"credential": ["credential"], "project": ["project"], "activity": ["activity"]}


def _score_others(
    out: Score, reading: _Reading, career: Career, layout: Layout | None, miss: Miss
) -> None:
    def find(text: str, kinds: Iterable[str]) -> ProposedCard | None:
        holders = reading.holding(text)
        if not holders:
            return None
        card = next((c for c in holders if c.kind in kinds), holders[0])
        reading.used.add(card.ref)
        return card

    if career.summary:
        summary = find(career.summary, ["story"])
        if not out.others.add(summary is not None and summary.kind == "story"):
            miss(
                "summary " + ("as another kind" if summary else "lost"),
                "The summary " + (f"on a card ({summary.kind})" if summary else "lost"),
                *([summary] if summary else []),
            )

    for highlight in career.highlights if layout is None or layout.style.highlights else []:
        card = find(highlight.text, ["accomplishment"])
        short = _short(highlight.text)
        if card is None:
            out.others.add(False)
            miss("highlight lost", f"Highlight “{short}” lost")
            continue
        employment, _ = reading.ancestors(card)
        under = reading.employer_of(employment)
        want = highlight.names
        placed = (
            (under is None and card.parent_ref is None)
            if want is None
            else (under is not None and under.employer == want)
        )
        ok = card.kind == "accomplishment" and placed and reading.same(card, highlight.text)
        if not out.others.add(ok):
            where = under.employer if under else "nothing"
            what = "highlight misplaced" if not placed else "highlight misread"
            miss(what, f"Highlight “{short}” on a card ({card.kind}) under {where}", card)

    # Skills are scored as the skills a group lists, wherever the reading put them:
    # how a list is cut into groups is the person's to tidy, not a skill lost.
    read_skills: dict[str, ProposedCard] = {}
    for card in reading.cards:
        listed_on = card.content.facts.get("skills") if card.kind == "skill" else None
        for skill in listed_on if isinstance(listed_on, list) else []:
            read_skills.setdefault(norm(str(skill)), card)

    def skill_card(skill: str) -> ProposedCard | None:
        want = norm(skill)
        if want in read_skills:
            return read_skills[want]
        return next(
            (
                c
                for have, c in read_skills.items()
                if want and have and (want in have or have in want)
            ),
            None,
        )

    for group in career.skills:
        holders = [skill_card(s) for s in group.items]
        on = [c for c in holders if c is not None]
        reading.used.update(c.ref for c in on)
        if not out.others.add(len(on) == len(holders)):
            miss(
                "skills misread" if on else "skills lost",
                f"Skills “{group.category}”: {len(on)} of {len(holders)} found",
                *on,
            )
            continue
        categories = {norm(str(c.content.facts.get("category") or "")) for c in on}
        if categories != {norm(group.category)}:
            # Noted, not counted against the reading.
            out.kinds["skills grouped differently"] = (
                out.kinds.get("skills grouped differently", 0) + 1
            )

    for school in career.education:
        known_by = school.school or " ".join(t for t in (school.degree, school.field) if t)
        if not norm(known_by):
            continue
        card = find(known_by, ["education", "credential"])
        if card is None:
            out.others.add(False)
            miss("education lost", f"Education at {school.school}: lost")
            continue
        institution = card.content.facts.get("institution")
        degree = norm(str(card.content.facts.get("degree") or ""))
        wrong_parts = [
            part
            for part, ok in (
                # A school with no degree or field ("Microsoft Certified...") may be
                # a certificate listed under Education: either reading is right.
                (
                    "as another kind",
                    card.kind == "education"
                    or (card.kind == "credential" and not (school.degree or school.field)),
                ),
                (
                    "school misread",
                    not school.school
                    or (isinstance(institution, str) and norm(institution) == norm(school.school)),
                ),
                (
                    "degree misread",
                    not (school.degree or school.field)
                    or (
                        bool(degree)
                        and norm(school.degree) in degree
                        and norm(school.field) in degree
                    ),
                ),
                (
                    "year misread",
                    school.year is None or _year_of(card) == _year_written(school.year),
                ),
            )
            if not ok
        ]
        if not out.others.add(not wrong_parts):
            for part in wrong_parts:
                miss(
                    f"education {part}",
                    f"Education at {school.school}: {card.kind}, {card.content.facts}",
                    card,
                )

    for award in career.awards:
        card = find(award.name, ["accomplishment"])
        ok = (
            card is not None
            and card.kind == "accomplishment"
            and "award" in card.content.facts
            and (award.year is None or _year_of(card) == _year_written(award.year))
        )
        if not out.others.add(ok):
            miss(
                "award misread" if card else "award lost",
                f"Award “{award.name}”: "
                + (f"{card.kind}, year {_year_of(card)}" if card else "lost"),
                *([card] if card else []),
            )

    entries: list[tuple[str, str, str | None]] = [
        ("activity", t.text, t.year) for t in career.talks
    ]
    entries += [(o.kind, o.text, o.year) for o in career.other]
    for kind, text, year in entries:
        kinds = OTHER_KINDS.get(kind, [kind])
        card = find(text, kinds)
        ok = (
            card is not None and card.kind in kinds and (year is None or _year_of(card) == year[:4])
        )
        if not out.others.add(ok):
            found = _year_of(card) if card else None
            miss(
                f"{kind} misread" if card else f"{kind} lost",
                f"{kind.capitalize()} “{_short(text)}”: "
                + (f"{card.kind}, year {found}, not {year}" if card else "lost"),
                *([card] if card else []),
            )


def _score_contact(out: Score, contact: Contact, career: Career, miss: Miss) -> None:
    def digits(text: str) -> str:
        return re.sub(r"\D", "", text)

    checks: list[tuple[str, bool]] = []
    if career.name:
        checks.append(
            ("name", contact.name is not None and norm(contact.name) == norm(career.name))
        )
    if career.email:
        checks.append(("email", career.email.lower() in [e.lower() for e in contact.emails]))
    if career.phone:
        checks.append(("phone", digits(career.phone) in [digits(p) for p in contact.phones]))
    if career.location:
        # A label may hold the whole address; the import keeps the city and state.
        have = norm(contact.location or "").split()
        checks.append(("location", bool(have) and set(have) <= set(norm(career.location).split())))
    for field, ok in checks:
        if not out.contact.add(ok):
            miss(f"contact {field} lost", f"Contact {field} not read")


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
            "garbled",
            "extra",
            "asked",
            "asked_wrong",
            "lines",
            "guessed",
        ):
            setattr(sum_, name, getattr(sum_, name) + getattr(s, name))
        sum_.cost_usd += s.cost_usd
        sum_.seconds += s.seconds
        for what, n in s.kinds.items():
            sum_.kinds[what] = sum_.kinds.get(what, 0) + n
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


def report(scores: list[Score], *, title: str = "Import fidelity", private: bool = False) -> str:
    """A Markdown report: overall, by layout, by kind of file, then what went wrong.
    A private one is for real resumes: counts only, with no words from them and each
    resume known by its id."""
    lines = [f"# {title}", ""]
    everything = total(scores)
    runs = len(scores)
    failed = sum(1 for s in scores if s.failed)
    lines += [
        f"{runs} resumes read ({failed} failed). Fidelity {100 * everything.fidelity:.1f}%: "
        f"{everything.misattributed} accomplishments in the wrong place, "
        f"{everything.missing} lost, {everything.merged} merged, {everything.split} split, "
        f"{everything.extra} cards that match nothing."
        + (f" {everything.garbled} read with words changed." if everything.garbled else ""),
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

    lines += ["## By folder" if private else "## By layout", "", header, rule]
    for name in dict.fromkeys(s.layout for s in scores):
        lines.append(row(name, total(s for s in scores if s.layout == name)))
    lines += ["", "## By kind of file", "", header, rule]
    for kind in dict.fromkeys(s.kind for s in scores):
        lines.append(row(kind, total(s for s in scores if s.kind == kind)))
    if private:
        lines += ["", "## What went wrong, by kind", "", "| | Times | Resumes |", "|---|---|---|"]
        for what, n in sorted(everything.kinds.items(), key=lambda kv: -kv[1]):
            hit = sum(1 for s in scores if s.kinds.get(what))
            lines.append(f"| {what} | {n} | {hit} |")
        weakest = sorted((s for s in scores if not s.failed), key=lambda s: s.fidelity)[:15]
        lines += ["", "## Weakest resumes, by id", "", header, rule]
        lines += [row(s.career, s) for s in weakest]
        failures = [s for s in scores if s.failed]
        if failures:
            lines += ["", "## Failed", ""]
            lines += [f"- {s.career}: {s.failed}" for s in failures]
        lines.append("")
        return "\n".join(lines)
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
