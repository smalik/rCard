"""Runs the import over folders of resumes the way real use would, and measures it.

    python -m plytos_api.imports.bench DIR [DIR ...] --budget 20 --sample 50

Each resume is imported on its own, start to finish, as one person uploading it
would be: no prompt caching or shared context between resumes. By default one
runs at a time; --workers runs a few at once, like people arriving together.
Every Claude call's tokens, seconds and cost are recorded (imports/usage.py).

A spend ledger in the output folder keeps the total across runs, and a run
stops before starting a resume once the next one could take the total past
the budget. Resumes already measured are skipped, so each run covers new ones.

The output folder holds what was read from the resumes, so it belongs on the
machine that has them and is created readable by its owner only:

* results.jsonl: one line of numbers per resume (tokens, cost and seconds per
  step, how its lines were accounted for, questions raised).
* index.jsonl: the resumes read, with what's needed to group similar ones
  later (category, size, employers, titles, years, skills).
* readings/<id>.json: everything the import read from each resume, for
  checking it against the file.
* summary-<run>.md: cost per resume and per step, and what a budget buys.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import statistics
import sys
import threading
import time
from collections import Counter, defaultdict
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from plytos_api.imports.ai import ResumeReader
from plytos_api.imports.extract import UnsupportedFileError
from plytos_api.imports.model import ImportResult
from plytos_api.imports.pipeline import import_resume

SUFFIXES = (".pdf", ".docx")
STEPS = ("pictures", "structure", "placement", "facts", "proofread")
BUDGETS = (1.0, 3.0, 20.0)


def find_resumes(roots: Iterable[Path]) -> list[tuple[Path, str]]:
    """Every resume file under the roots, with its category: the folder it sits in
    directly under its root, or the root's own name for a file at the top."""
    found: list[tuple[Path, str]] = []
    for root in roots:
        for path in sorted(root.rglob("*")):
            if path.suffix.lower() not in SUFFIXES or not path.is_file():
                continue
            parts = path.relative_to(root).parts
            found.append((path, parts[0] if len(parts) > 1 else root.name))
    return found


def pick(found: list[tuple[Path, str]], count: int, seed: int) -> list[tuple[Path, str]]:
    """A sample spread across categories: shuffled within each, then taken in turn."""
    groups: dict[str, list[tuple[Path, str]]] = defaultdict(list)
    for item in found:
        groups[item[1]].append(item)
    rng = random.Random(seed)  # noqa: S311 - a repeatable sample, not a secret
    for items in groups.values():
        rng.shuffle(items)
    order = sorted(groups)
    rng.shuffle(order)
    out: list[tuple[Path, str]] = []
    while len(out) < count and any(groups.values()):
        for name in order:
            if groups[name] and len(out) < count:
                out.append(groups[name].pop())
    return out


class Ledger:
    """What all runs have spent, kept in the output folder."""

    def __init__(self, path: Path, budget: float) -> None:
        self.path = path
        self.budget = budget
        self.lock = threading.Lock()
        data = json.loads(path.read_text()) if path.exists() else {}
        self.spent: float = float(data.get("spent_usd", 0.0))
        self.most: float = float(data.get("most_per_resume_usd", 0.0))
        self.resumes: int = int(data.get("resumes", 0))
        self.in_flight = 0

    def may_start(self) -> bool:
        """Whether one more resume fits, counting the ones still running at the most
        any resume has cost so far."""
        with self.lock:
            if self.spent + self.most * (self.in_flight + 1) > self.budget:
                return False
            self.in_flight += 1
            return True

    def add(self, cost: float) -> None:
        with self.lock:
            self.in_flight -= 1
            self.spent += cost
            self.most = max(self.most, cost)
            self.resumes += 1
            _write_json(
                self.path,
                {
                    "spent_usd": round(self.spent, 6),
                    "most_per_resume_usd": round(self.most, 6),
                    "resumes": self.resumes,
                    "updated": _now(),
                },
            )


def run(
    items: list[tuple[Path, str]],
    reader: ResumeReader | None,
    out: Path,
    budget: float,
    *,
    workers: int = 1,
    pace: float = 0.0,
    run_id: str | None = None,
) -> list[dict[str, Any]]:
    """Imports each resume, records it, and returns the records of this run."""
    out.mkdir(parents=True, exist_ok=True)
    os.chmod(out, 0o700)
    run_id = run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    ledger = Ledger(out / "spend.json", budget)
    lock = threading.Lock()
    records: list[dict[str, Any]] = []
    stop = threading.Event()

    def one(item: tuple[Path, str]) -> None:
        if stop.is_set():
            return
        if not ledger.may_start():
            stop.set()
            return
        path, category = item
        entry: dict[str, Any] | None = None
        try:
            record, entry = measure(path, category, reader, run_id)
        except OSError as exc:  # a file that can't be read
            record = {"id": "", "run": run_id, "path": str(path), "category": category}
            record.update(error=type(exc).__name__, cost_usd=0.0, seconds=0.0)
        ledger.add(record["cost_usd"] or 0.0)
        reading = record.pop("reading", None)
        if reading is not None:
            _write_private(out / "readings" / f"{record['id']}.json", reading)
        with lock:
            records.append(record)
            _append(out / "results.jsonl", record)
            if entry is not None:
                _append(out / "index.jsonl", entry)
        if pace:
            time.sleep(pace)

    if workers <= 1:
        for item in items:
            one(item)
            if stop.is_set():
                break
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(one, items))
    summary = summarize(records, run_id, ledger, stopped=stop.is_set())
    (out / f"summary-{run_id}.md").write_text(summary)
    return records


def measure(
    path: Path, category: str, reader: ResumeReader | None, run_id: str
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """One resume, imported as a person's upload would be, and its numbers."""
    data = path.read_bytes()
    rid = hashlib.sha256(data).hexdigest()[:16]
    record: dict[str, Any] = {
        "id": rid,
        "run": run_id,
        "path": str(path),
        "category": category,
        "bytes": len(data),
        "cost_usd": 0.0,
    }
    started = time.monotonic()
    try:
        result = import_resume(data, path.name, reader=reader)
    except UnsupportedFileError:
        record.update(error="unsupported", seconds=round(time.monotonic() - started, 2))
        return record, None
    except Exception as exc:  # one bad file mustn't end the run
        record.update(error=type(exc).__name__, seconds=round(time.monotonic() - started, 2))
        return record, None
    record["seconds"] = round(time.monotonic() - started, 2)
    record.update(_numbers(result))
    record["reading"] = result.model_dump_json()
    return record, _index_entry(rid, path, category, result, run_id)


def _numbers(result: ImportResult) -> dict[str, Any]:
    facts = result.facts
    usage = result.usage
    steps: dict[str, dict[str, float]] = {}
    for call in usage.calls if usage is not None else []:
        s = steps.setdefault(
            call.step,
            {
                "calls": 0,
                "failed": 0,
                "input": 0,
                "output": 0,
                "thinking": 0,
                "cache_read": 0,
                "cache_write": 0,
                "images": 0,
                "seconds": 0.0,
                "cost_usd": 0.0,
            },
        )
        s["calls"] += 1
        s["failed"] += 0 if call.ok else 1
        s["input"] += call.input_tokens
        s["output"] += call.output_tokens
        s["thinking"] += call.thinking_tokens or 0
        s["cache_read"] += call.cache_read_tokens
        s["cache_write"] += call.cache_write_tokens
        s["images"] += call.images
        s["seconds"] += call.seconds
        s["cost_usd"] += call.cost_usd or 0.0
    results = [c for c in result.cards if c.kind == "accomplishment"]
    lines = result.lines
    severities = Counter(f.severity for f in result.findings)
    return {
        "format": facts.format,
        "pages": facts.pages,
        "words": facts.word_count,
        "columns": facts.columns,
        "read_by": result.read_by,
        "cost_usd": round(usage.cost_usd or 0.0, 6) if usage is not None else 0.0,
        "steps": steps,
        "lines": {
            "total": lines.lines,
            "on_cards": lines.on_cards,
            "contact": len(lines.contact),
            "headings": len(lines.headings),
            "skipped": len(lines.skipped),
            "guessed": len(lines.guessed),
        }
        if lines is not None
        else None,
        "cards": dict(Counter(c.kind for c in result.cards)),
        "placement_questions": sum(1 for c in result.cards if c.placement is not None),
        "moved": sum(1 for c in result.cards if c.placement is not None and c.placement.moved_from),
        "pictures": len(facts.pictures),
        "picture_lines": sum(1 for b in result.blocks if b.where == "image"),
        "scanned_pages": len(facts.scanned_pages),
        "proofread": sum(1 for f in result.findings if f.rule == "content.proofread"),
        "accomplishments": len(results),
        "with_skills": sum(1 for c in results if c.content.facts.get("skills")),
        "with_scope": sum(1 for c in results if c.content.facts.get("scope")),
        "with_outcome": sum(1 for c in results if c.content.facts.get("outcome")),
        "findings": dict(severities),
    }


def _index_entry(
    rid: str, path: Path, category: str, result: ImportResult, run_id: str
) -> dict[str, Any]:
    """What grouping similar resumes later needs. It holds names from the resume."""
    years: list[int] = []
    for card in result.cards:
        for key in ("start", "end"):
            value = card.content.facts.get(key)
            if isinstance(value, str) and value[:4].isdigit():
                years.append(int(value[:4]))
    skills: list[str] = []
    for card in result.cards:
        found = card.content.facts.get("skills")
        if isinstance(found, list):
            skills += [s for s in found if s.lower() not in {x.lower() for x in skills}]
    employers = [
        str(c.content.facts.get("employer"))
        for c in result.cards
        if c.kind == "employment" and c.content.facts.get("employer")
    ]
    titles = [
        str(c.content.facts.get("title"))
        for c in result.cards
        if c.kind == "position" and c.content.facts.get("title")
    ]
    return {
        "id": rid,
        "path": str(path),
        "category": category,
        "run": run_id,
        "read_by": result.read_by,
        "pages": result.facts.pages,
        "words": result.facts.word_count,
        "employers": employers,
        "titles": titles,
        "years": [min(years), max(years)] if years else None,
        "skills": skills[:60],
    }


def measured_ids(out: Path) -> set[str]:
    path = out / "results.jsonl"
    if not path.exists():
        return set()
    return {json.loads(line)["id"] for line in path.read_text().splitlines() if line.strip()}


# --- Summary -------------------------------------------------------------------------


def summarize(records: list[dict[str, Any]], run_id: str, ledger: Ledger, *, stopped: bool) -> str:
    """Numbers only: nothing from the resumes' text."""
    read = [r for r in records if "error" not in r]
    errors = Counter(r["error"] for r in records if "error" in r)
    by_claude = [r for r in read if r.get("read_by")]
    costs = [r["cost_usd"] for r in read]
    spent = sum(costs)
    out = [f"# Import bench, run {run_id}", ""]
    out.append(
        f"{len(records)} resumes tried: {len(read)} read, {len(by_claude)} by Claude, "
        f"{len(read) - len(by_claude)} by the rules alone"
        + (f"; failed: {dict(errors)}" if errors else "")
        + "."
    )
    out.append(
        f"Spent ${spent:.4f} this run; ${ledger.spent:.4f} of the ${ledger.budget:.2f} budget "
        f"across all runs ({ledger.resumes} resumes)."
        + (" Stopped at the budget." if stopped else "")
    )
    if not read:
        return "\n".join(out) + "\n"

    out += ["", "## Per resume", ""]
    out.append("| | mean | median | p95 | max |")
    out.append("| --- | --- | --- | --- | --- |")
    out.append(_row("Cost (USD)", costs, "{:.4f}"))
    out.append(_row("Seconds, start to finish", [r["seconds"] for r in read], "{:.1f}"))
    tokens_in = [sum(s["input"] for s in r["steps"].values()) for r in by_claude]
    tokens_out = [sum(s["output"] for s in r["steps"].values()) for r in by_claude]
    if by_claude:
        out.append(_row("Tokens in", tokens_in, "{:.0f}"))
        out.append(_row("Tokens out (with thinking)", tokens_out, "{:.0f}"))
    out.append(_row("Pages", [r["pages"] or 0 for r in read], "{:.1f}"))
    out.append(_row("Words", [r["words"] for r in read], "{:.0f}"))

    out += ["", "## Per step", ""]
    out.append(
        "| Step | Resumes | Share of cost | Mean cost | Mean tokens in | Mean tokens out "
        "| Mean thinking | Mean seconds | Failed calls |"
    )
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for step in STEPS:
        rows = [r["steps"][step] for r in read if step in r["steps"]]
        if not rows:
            continue
        step_cost = sum(s["cost_usd"] for s in rows)
        out.append(
            f"| {step} | {len(rows)} | {step_cost / spent:.0%} | "
            f"{step_cost / len(rows):.5f} | {_mean(s['input'] for s in rows):.0f} | "
            f"{_mean(s['output'] for s in rows):.0f} | {_mean(s['thinking'] for s in rows):.0f} | "
            f"{_mean(s['seconds'] for s in rows):.1f} | {sum(s['failed'] for s in rows)} |"
            if spent
            else f"| {step} | {len(rows)} | – | – | – | – | – | – | – |"
        )

    out += ["", "## What a budget buys", ""]
    mean_cost = _mean(costs)
    p95 = _pct(costs, 95)
    out.append("| Budget | Resumes at the mean cost | Resumes at the p95 cost |")
    out.append("| --- | --- | --- |")
    for budget in BUDGETS:
        at_mean = f"{int(budget / mean_cost):,}" if mean_cost else "–"
        at_p95 = f"{int(budget / p95):,}" if p95 else "–"
        out.append(f"| ${budget:g} | {at_mean} | {at_p95} |")

    out += ["", "## How the reading went (signals, not a score)", ""]
    with_lines = [r for r in read if r.get("lines")]
    total_lines = sum(r["lines"]["total"] for r in with_lines)
    guessed = sum(r["lines"]["guessed"] for r in with_lines)
    accomplishments = sum(r["accomplishments"] for r in read)
    out += [
        f"- Lines no step claimed (proposed as cards to check): {guessed} of {total_lines} "
        f"({guessed / total_lines:.1%})"
        if total_lines
        else "- No lines read.",
        f"- Placement questions: {_mean(r['placement_questions'] for r in read):.2f} per "
        f"resume; cards moved: {sum(r['moved'] for r in read)}",
        f"- Proofreading suggestions: {_mean(r['proofread'] for r in read):.2f} per resume",
        f"- Accomplishments: {accomplishments}; with skills "
        f"{_share(read, 'with_skills', accomplishments)}, scope "
        f"{_share(read, 'with_scope', accomplishments)}, outcome "
        f"{_share(read, 'with_outcome', accomplishments)}",
        f"- Resumes with words read from pictures: "
        f"{sum(1 for r in read if r['picture_lines'])}; scanned pages: "
        f"{sum(r['scanned_pages'] for r in read)}",
        f"- Categories: {dict(Counter(r['category'] for r in read).most_common())}",
    ]
    return "\n".join(out) + "\n"


def _row(label: str, values: list[float], fmt: str) -> str:
    cells = [_mean(values), statistics.median(values), _pct(values, 95), max(values)]
    return f"| {label} | " + " | ".join(fmt.format(v) for v in cells) + " |"


def _mean(values: Iterable[float]) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 0.0


def _pct(values: list[float], pct: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(pct / 100 * (len(ordered) - 1)))]


def _share(records: list[dict[str, Any]], key: str, total: int) -> str:
    return f"{sum(r[key] for r in records) / total:.0%}" if total else "–"


def _append(path: Path, record: dict[str, Any]) -> None:
    new = not path.exists()
    with path.open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    if new:
        os.chmod(path, 0o600)


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(mode=0o700, exist_ok=True)
    path.write_text(text)
    os.chmod(path, 0o600)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def main(argv: list[str] | None = None) -> int:
    from plytos_api.config import Settings
    from plytos_api.imports.ai import reader_for

    parser = argparse.ArgumentParser(prog="python -m plytos_api.imports.bench")
    parser.add_argument("roots", type=Path, nargs="+", help="folders of resumes")
    parser.add_argument("--budget", type=float, required=True, help="USD, across all runs")
    parser.add_argument("--sample", type=int, default=50, help="resumes to try this run")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", type=Path, default=Path.home() / ".plytos" / "bench")
    parser.add_argument("--workers", type=int, default=1, help="resumes at once (at most 4)")
    parser.add_argument("--pace", type=float, default=0.0, help="seconds between resumes")
    parser.add_argument("--again", action="store_true", help="include resumes measured before")
    args = parser.parse_args(argv)

    found = find_resumes(args.roots)
    if not args.again:
        done = measured_ids(args.out)
        found = [
            item
            for item in found
            if hashlib.sha256(item[0].read_bytes()).hexdigest()[:16] not in done
        ]
    items = pick(found, args.sample, args.seed)
    settings = Settings()
    provider = "anthropic" if settings.ai_provider == "off" else settings.ai_provider
    reader = reader_for(
        provider,
        settings.ai_model,
        settings.ai_effort,
        settings.ai_vertex_project,
        settings.ai_vertex_region,
    )
    print(f"{len(found)} resumes not yet measured; trying {len(items)}.", file=sys.stderr)
    run(items, reader, args.out, args.budget, workers=min(4, args.workers), pace=args.pace)
    latest = max(args.out.glob("summary-*.md"), key=lambda p: p.stat().st_mtime)
    sys.stdout.write(latest.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
