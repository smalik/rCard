"""The shape of a real resume, its label and a reading of it, without its words.

    python -m plytos_api.imports.fidelity.shape --labels DIR [--readings DIR] KEY...

Shows where a reading went wrong on a resume that can't leave its machine: each line's
place and kind, and each word only as its kind (W a capitalized word, w a lowercase
one, A one in capitals, 9 one with a figure), with its punctuation. Section headings
and month names are shown as the import names them, since they say nothing about the
person. Then the label's jobs and accomplishments, by the lines they're on, and the
reading's cards, by the lines they came from, with the misses marked on each.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from plytos_api.imports.dates import find_range
from plytos_api.imports.extract import extract
from plytos_api.imports.fidelity.real import file_id, load_labels
from plytos_api.imports.fidelity.score import norm, score
from plytos_api.imports.fidelity.truth import Career
from plytos_api.imports.model import ImportResult, ProposedCard
from plytos_api.imports.segment import HEADINGS, normalize_heading

_MONTH_WORDS = (
    "jan feb mar apr may jun jul aug sep sept oct nov dec january february march april "
    "june july august september october november december present current"
)
_MONTHS = {m: m.title() for m in _MONTH_WORDS.split(" ")}
_EDGE = re.compile(r"^(\W*)(.*?)(\W*)$")


def skeleton(text: str, most: int = 24) -> str:
    """A line's words as their kinds: "Grew sales 12%." is "W w 9."."""
    out = []
    words = text.split()
    for word in words[:most]:
        lead, core, tail = _EDGE.match(word).groups()  # type: ignore[union-attr]
        if not core:
            out.append(re.sub(r"[A-Za-z0-9]", "", word) or "·")
            continue
        if core.lower().rstrip(".") in _MONTHS:
            kind = _MONTHS[core.lower().rstrip(".")]
        elif any(c.isdigit() for c in core):
            kind = "9"
        elif core.isupper() and len(core) > 1:
            kind = "A"
        elif core[0].isupper():
            kind = "W"
        else:
            kind = "w"
        out.append(f"{lead}{kind}{tail}")
    if len(words) > most:
        out.append(f"+{len(words) - most}")
    return " ".join(out)


def _heading(text: str) -> str | None:
    kind = HEADINGS.get(normalize_heading(text))
    return f"[{kind} heading: {normalize_heading(text)}]" if kind else None


def _when(start: str | None, end: str | None) -> str:
    """A label's dates by their form only: "2019-03" is "9999-99"."""
    return "-".join(re.sub(r"\d", "9", d) if d else "?" for d in (start, end))


def _lines_of(words: str, lines: dict[int, str]) -> list[int]:
    """The lines a label's words are on: the first that holds their start, and those
    after it that go on holding them."""
    want = norm(words)
    found: list[int] = []
    for index, text in lines.items():
        have = norm(text)
        if not have:
            continue
        if (found and have in want) or (not found and want.startswith(have[:40])):
            found.append(index)
        elif want[:40] in have:
            return [index]
        elif found:
            break
    return found


def show(career: Career, reading: ImportResult | None) -> str:
    source = Path(career.source or "")
    data = source.read_bytes()
    if file_id(data) != career.key:
        return f"{career.key}: the label is for another file\n"
    doc = extract(data, source.name)
    out = [f"== {career.key} ({source.parent.name})", "", "Lines"]
    lines: dict[int, str] = {}
    for block in doc.blocks:
        lines[block.index] = block.text
        marks = "".join(
            m
            for m, on in (("•", block.is_bullet), ("B", block.bold), ("D", find_range(block.text)))
            if on
        )
        place = "" if block.where == "body" else f" {block.where}"
        out.append(
            f"  {block.index:3} p{block.page or 1}{place} {marks:3} "
            + (_heading(block.text) or skeleton(block.text))
        )
    out += ["", "Label"]
    for e, employment in enumerate(career.employments, 1):
        when = _when(employment.start, employment.end)
        out.append(f"  E{e} employer {skeleton(employment.employer)} {when}")
        for t, position in enumerate(employment.positions, 1):
            title = skeleton(position.title or "")
            out.append(f"    T{e}.{t} {title} {_when(position.start, position.end)}")
            for group in position.groups:
                label = f" under {skeleton(group.label)}" if group.label else ""
                for item in group.items:
                    words = len(item.split())
                    out.append(f"      item {words}w{label} on {_lines_of(item, lines)}")
    for school in career.education:
        out.append(
            f"  school {skeleton(school.school)} | degree {skeleton(school.degree)}"
            f" | field {skeleton(school.field)} | {_when(school.year, None)}"
        )
    if reading is None:
        return "\n".join(out) + "\n"
    scored = score(career, None, reading, kind="?", name="?")
    out += ["", f"Reading ({100 * scored.fidelity:.0f}%)"]
    number = {c.ref: n for n, c in enumerate(reading.cards, 1)}
    by_ref = {c.ref: c for c in reading.cards}

    def depth(card: ProposedCard) -> int:
        d, at = 0, card
        while at.parent_ref in by_ref and d < 6:
            at, d = by_ref[at.parent_ref], d + 1
        return d

    for card in reading.cards:
        facts = card.content.facts
        stream = facts.get("workstream")
        out.append(
            "  " * (depth(card) + 1)
            + f"c{number[card.ref]} {card.kind} "
            + (f"(in c{number[card.parent_ref]}) " if card.parent_ref in number else "")
            + skeleton(card.content.framing.headline, 12)
            + f" on {card.source_blocks}"
            + (f" workstream {skeleton(stream)}" if isinstance(stream, str) else "")
            + f" facts {sorted(k for k in facts if k != 'workstream')}"
            + (f" MISS {scored.marks[card.ref]}" if card.ref in scored.marks else "")
        )
    lost = {k: v for k, v in scored.kinds.items() if "lost" in k}
    if lost:
        out.append(f"  lost: {lost}")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m plytos_api.imports.fidelity.shape")
    parser.add_argument("--labels", type=Path, required=True, metavar="DIR")
    parser.add_argument("--readings", type=Path, metavar="DIR", help="saved readings")
    parser.add_argument("keys", nargs="+", help="file ids, or their first characters")
    args = parser.parse_args(argv)
    careers, _ = load_labels(args.labels)
    for want in args.keys:
        for career in (c for c in careers if c.key.startswith(want)):
            reading = None
            if args.readings is not None:
                saved = args.readings / f"{career.key}.json"
                if saved.exists():
                    reading = ImportResult.model_validate_json(saved.read_text())
            sys.stdout.write(show(career, reading) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
