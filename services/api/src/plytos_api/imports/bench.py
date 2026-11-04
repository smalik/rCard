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
* readings/<run>/<id>.json: everything the import read from each resume, for
  checking it against the file.
* summary-<run>.md: cost per resume and per step, and what a budget buys.

To measure a change (a lower effort for a step, say) on the same resumes:

    python -m plytos_api.imports.bench --rerun RUN --effort structure=low --budget 20
    python -m plytos_api.imports.bench --compare RUN NEW_RUN

--skip leaves a step out: --skip proofread prices proofreading on demand.

--compare reads the two runs' readings and says, in numbers only, how often they
agree on employers, titles, dates, which job each accomplishment is under and
its facts, and what each step cost. It makes no Claude calls.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import random
import statistics
import sys
import threading
import time
import traceback
from collections import Counter, defaultdict
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast, get_args

from plytos_api.imports.ai import ResumeReader
from plytos_api.imports.extract import UnsupportedFileError
from plytos_api.imports.model import ImportResult, ProposedCard
from plytos_api.imports.pipeline import import_resume
from plytos_api.imports.usage import AiUsage

SUFFIXES = (".pdf", ".docx")
STEPS = ("pictures", "structure", "placement", "facts", "proofread")
# Steps an import can go without; the structure reading isn't one of them.
SKIPPABLE = ("pictures", "placement", "facts", "proofread")
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
    label: str | None = None,
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
        if label:
            record["label"] = label
        reading = record.pop("reading", None)
        if reading is not None:
            _write_private(out / "readings" / run_id / f"{record['id']}.json", reading)
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
    summary = summarize(records, run_id, ledger, stopped=stop.is_set(), label=label)
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
        record["where"] = _where(exc)
        # Claude calls made before the failure were billed: count them.
        calls = getattr(exc, "ai_calls", None) or []
        record["cost_usd"] = round(AiUsage(calls=calls).estimated_cost_usd, 6)
        return record, None
    record["seconds"] = round(time.monotonic() - started, 2)
    record.update(_numbers(result))
    record["reading"] = result.model_dump_json()
    return record, _index_entry(rid, path, category, result, run_id)


def _where(exc: BaseException) -> str:
    """Where an error was raised: the last frame's file, line and function. Never the
    message, which may quote the resume."""
    while exc.__context__ is not None and exc.__suppress_context__ is False:
        # The innermost error: a StopIteration inside a generator surfaces as the
        # RuntimeError it was turned into, raised from the caller's frame.
        exc = exc.__context__
    frames = traceback.extract_tb(exc.__traceback__)
    if not frames:
        return ""
    last = frames[-1]
    return f"{Path(last.filename).name}:{last.lineno} in {last.name}"


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
        # Calls lost to an error are counted at an estimate, so the budget holds.
        "cost_usd": round(usage.estimated_cost_usd, 6) if usage is not None else 0.0,
        "unpriced_calls": usage.unpriced if usage is not None else 0,
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


def rerun_items(out: Path, run_id: str) -> list[tuple[Path, str]]:
    """The resumes an earlier run read, in the order it read them."""
    items: list[tuple[Path, str]] = []
    for row in _rows(out):
        if row.get("run") == run_id and "error" not in row:
            items.append((Path(row["path"]), row["category"]))
    return items


def _rows(out: Path) -> list[dict[str, Any]]:
    path = out / "results.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# --- Comparing two runs ----------------------------------------------------------------


def _key(value: object) -> str:
    return " ".join(str(value or "").lower().split())


def _tree(result: ImportResult) -> dict[str, Any]:
    """The career tree as plain keys: employers, jobs (employer > title or client), each
    job's dates, and the job each accomplishment line is under, keyed by its text."""
    by_ref = {c.ref: c for c in result.cards}
    texts = {b.index: _key(b.text) for b in result.blocks}

    def path(card: ProposedCard | None) -> tuple[str, ...]:
        out: list[str] = []
        while card is not None:
            facts = card.content.facts
            if card.kind == "employment":
                out.append(_key(facts.get("employer")))
            elif card.kind == "position":
                out.append(_key(facts.get("title")))
            elif card.kind == "engagement":
                out.append(f"{_key(facts.get('client'))} / {_key(facts.get('title'))}")
            card = by_ref.get(card.parent_ref) if card.parent_ref else None
        return tuple(reversed(out))

    jobs: dict[tuple[str, ...], tuple[str, str]] = {}
    placed: dict[str, tuple[str, ...]] = {}
    for card in result.cards:
        if card.kind in ("position", "engagement"):
            facts = card.content.facts
            jobs[path(card)] = (_key(facts.get("start")), _key(facts.get("end")))
        elif card.kind == "accomplishment" and card.source_blocks:
            parent = by_ref.get(card.parent_ref) if card.parent_ref else None
            placed[texts.get(card.source_blocks[0], "")] = path(parent)
    employers = {
        _key(c.content.facts.get("employer")) for c in result.cards if c.kind == "employment"
    }
    return {"employers": employers, "jobs": jobs, "placed": placed}


def _facts(result: ImportResult) -> dict[str, tuple[set[str], set[str], str]]:
    """Each accomplishment's skills, scope and outcome, keyed by its first line."""
    texts = {b.index: _key(b.text) for b in result.blocks}
    out: dict[str, tuple[set[str], set[str], str]] = {}
    for card in result.cards:
        if card.kind != "accomplishment" or not card.source_blocks:
            continue
        facts = card.content.facts
        out[texts.get(card.source_blocks[0], "")] = (
            _keys(facts.get("skills")),
            _keys(facts.get("scope")),
            _key(facts.get("outcome")),
        )
    return out


def _keys(value: object) -> set[str]:
    return {_key(v) for v in value} if isinstance(value, list) else set()


def _jaccard(a: set[Any], b: set[Any]) -> float:
    return len(a & b) / len(a | b) if a | b else 1.0


def _reading(out: Path, run_id: str, rid: str) -> ImportResult | None:
    for path in (out / "readings" / run_id / f"{rid}.json", out / "readings" / f"{rid}.json"):
        if path.exists():
            return ImportResult.model_validate_json(path.read_text())
    return None


def compare(out: Path, first: str, second: str) -> str:
    """How two runs' readings of the same resumes agree. Numbers only."""
    rows = _rows(out)
    runs = {
        name: {r["id"]: r for r in rows if r.get("run") == name and "error" not in r}
        for name in (first, second)
    }
    shared = sorted(set(runs[first]) & set(runs[second]))
    employers: list[float] = []
    jobs: list[float] = []
    same_dates = [0, 0]
    same_place = [0, 0]
    resumes_all_placed_alike = 0
    skills: list[float] = []
    scope: list[float] = []
    same_outcome = [0, 0]
    for rid in shared:
        a, b = _reading(out, first, rid), _reading(out, second, rid)
        if a is None or b is None:
            continue
        fa, fb = _facts(a), _facts(b)
        for text in set(fa) & set(fb):
            skills.append(_jaccard(fa[text][0], fb[text][0]))
            scope.append(_jaccard(fa[text][1], fb[text][1]))
            same_outcome[0] += fa[text][2] == fb[text][2]
            same_outcome[1] += 1
        ta, tb = _tree(a), _tree(b)
        employers.append(_jaccard(ta["employers"], tb["employers"]))
        jobs.append(_jaccard(set(ta["jobs"]), set(tb["jobs"])))
        for job in set(ta["jobs"]) & set(tb["jobs"]):
            same_dates[0] += ta["jobs"][job] == tb["jobs"][job]
            same_dates[1] += 1
        lines = set(ta["placed"]) & set(tb["placed"])
        alike = sum(ta["placed"][t] == tb["placed"][t] for t in lines)
        same_place[0] += alike
        same_place[1] += len(lines)
        resumes_all_placed_alike += alike == len(lines)

    def mean(run: str, key: str) -> float:
        return _mean(runs[run][rid][key] for rid in shared)

    def step_cost(run: str, step: str) -> float:
        return _mean(runs[run][rid]["steps"].get(step, {}).get("cost_usd", 0.0) for rid in shared)

    def calls(run: str, step: str) -> float:
        return _mean(runs[run][rid]["steps"].get(step, {}).get("calls", 0) for rid in shared)

    def share(run: str, key: str) -> str:
        total = sum(runs[run][rid]["accomplishments"] for rid in shared)
        return _share([runs[run][rid] for rid in shared], key, total)

    def guessed(run: str) -> float:
        rs = [runs[run][rid]["lines"] for rid in shared if runs[run][rid].get("lines")]
        total = sum(r["total"] for r in rs)
        return sum(r["guessed"] for r in rs) / total if total else 0.0

    compared = len(employers)
    out_lines = [
        f"# Comparing run {first} with run {second}",
        "",
        f"{compared} resumes read in both.",
        "",
        "## Agreement",
        "",
        f"- Employers (mean overlap): {_mean(employers):.1%}",
        f"- Jobs, employer and title (mean overlap): {_mean(jobs):.1%}",
        f"- Dates of jobs found in both: {_ratio(same_dates)}",
        f"- Accomplishments under the same job: {_ratio(same_place)}; resumes with every "
        f"accomplishment under the same job: {resumes_all_placed_alike} of {compared}",
        "",
        "## Side by side",
        "",
        f"| | {first} | {second} |",
        "| --- | --- | --- |",
        f"| Mean cost (USD) | {mean(first, 'cost_usd'):.4f} | {mean(second, 'cost_usd'):.4f} |",
        f"| Mean cost without proofreading | "
        f"{mean(first, 'cost_usd') - step_cost(first, 'proofread'):.4f} | "
        f"{mean(second, 'cost_usd') - step_cost(second, 'proofread'):.4f} |",
        *(
            f"| Mean cost of {step} | {step_cost(first, step):.4f} | "
            f"{step_cost(second, step):.4f} |"
            for step in STEPS
        ),
        f"| Structure calls per resume | {calls(first, 'structure'):.2f} | "
        f"{calls(second, 'structure'):.2f} |",
        f"| Mean seconds | {mean(first, 'seconds'):.1f} | {mean(second, 'seconds'):.1f} |",
        f"| Placement questions per resume | {mean(first, 'placement_questions'):.2f} | "
        f"{mean(second, 'placement_questions'):.2f} |",
        f"| Lines no step claimed | {guessed(first):.1%} | {guessed(second):.1%} |",
        f"| Accomplishments per resume | {mean(first, 'accomplishments'):.1f} | "
        f"{mean(second, 'accomplishments'):.1f} |",
        f"| Accomplishments with skills | {share(first, 'with_skills')} | "
        f"{share(second, 'with_skills')} |",
        f"| Accomplishments with scope | {share(first, 'with_scope')} | "
        f"{share(second, 'with_scope')} |",
        f"| Accomplishments with an outcome | {share(first, 'with_outcome')} | "
        f"{share(second, 'with_outcome')} |",
        "",
        "## Facts on the same accomplishments",
        "",
        f"- Skills (mean overlap): {_mean(skills):.1%} over {len(skills)} accomplishments",
        f"- Scope (mean overlap): {_mean(scope):.1%}",
        f"- Same outcome: {_ratio(same_outcome)}",
    ]
    return "\n".join(out_lines) + "\n"


def _ratio(pair: list[int]) -> str:
    return f"{pair[0] / pair[1]:.1%} of {pair[1]}" if pair[1] else "none to compare"


# --- Summary -------------------------------------------------------------------------


def summarize(
    records: list[dict[str, Any]],
    run_id: str,
    ledger: Ledger,
    *,
    stopped: bool,
    label: str | None = None,
) -> str:
    """Numbers only: nothing from the resumes' text."""
    read = [r for r in records if "error" not in r]
    errors = Counter(r["error"] for r in records if "error" in r)
    by_claude = [r for r in read if r.get("read_by")]
    costs = [r["cost_usd"] for r in read]
    spent = sum(costs)
    out = [f"# Import bench, run {run_id}", ""]
    if label:
        out += [f"Variant: {label}", ""]
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
    path.parent.parent.mkdir(mode=0o700, exist_ok=True)
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
    from plytos_api.imports.ai import ClaudeReader, Effort, reader_for

    parser = argparse.ArgumentParser(prog="python -m plytos_api.imports.bench")
    parser.add_argument("roots", type=Path, nargs="*", help="folders of resumes")
    parser.add_argument("--budget", type=float, help="USD, across all runs")
    parser.add_argument("--sample", type=int, default=50, help="resumes to try this run")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", type=Path, default=Path.home() / ".plytos" / "bench")
    parser.add_argument("--workers", type=int, default=1, help="resumes at once (at most 4)")
    parser.add_argument("--pace", type=float, default=0.0, help="seconds between resumes")
    parser.add_argument("--again", action="store_true", help="include resumes measured before")
    parser.add_argument("--rerun", metavar="RUN", help="read the resumes of an earlier run again")
    parser.add_argument(
        "--effort",
        action="append",
        default=[],
        metavar="STEP=LEVEL",
        help="a step's effort in place of its usual one, e.g. structure=low",
    )
    parser.add_argument(
        "--skip",
        action="append",
        default=[],
        choices=SKIPPABLE,
        help="leave a step out, e.g. proofread to price proofreading on demand",
    )
    parser.add_argument("--label", help="a name for this run's variant, kept with its results")
    parser.add_argument("--compare", nargs=2, metavar="RUN", help="compare two runs' readings")
    args = parser.parse_args(argv)
    # Warnings, and the numbers-only line on how many facts landed, go to stderr.
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("plytos_api.imports.facts").setLevel(logging.INFO)

    if args.compare:
        sys.stdout.write(compare(args.out, *args.compare))
        return 0
    if args.budget is None:
        parser.error("--budget is required")
    efforts = dict(e.split("=", 1) for e in args.effort)
    for step, level in efforts.items():
        if step not in STEPS or level not in get_args(Effort):
            parser.error(f"--effort {step}={level}: unknown step or level")

    if args.rerun:
        items = rerun_items(args.out, args.rerun)[: args.sample]
        if not items:
            parser.error(f"run {args.rerun} has no resumes in {args.out}")
    else:
        if not args.roots:
            parser.error("give the folders of resumes, or --rerun")
        items = _new_items(args.roots, args.out, args.sample, args.seed, again=args.again)
    settings = Settings()
    provider = "anthropic" if settings.ai_provider == "off" else settings.ai_provider
    reader = reader_for(
        provider,
        settings.ai_model,
        settings.ai_effort,
        settings.ai_vertex_project,
        settings.ai_vertex_region,
    )
    if isinstance(reader, ClaudeReader):
        reader.step_efforts = cast(dict[str, Effort], efforts)
        reader.skip_steps = frozenset(args.skip)
    variant = [f"{k}={v}" for k, v in efforts.items()] + [f"skip={s}" for s in args.skip]
    label = args.label or (" ".join(variant) or None)
    print(f"Trying {len(items)} resumes.", file=sys.stderr)
    run(
        items,
        reader,
        args.out,
        args.budget,
        workers=min(4, args.workers),
        pace=args.pace,
        label=label,
    )
    latest = max(args.out.glob("summary-*.md"), key=lambda p: p.stat().st_mtime)
    sys.stdout.write(latest.read_text())
    return 0


def _new_items(
    roots: list[Path], out: Path, sample: int, seed: int, *, again: bool
) -> list[tuple[Path, str]]:
    found = find_resumes(roots)
    if not again:
        done = measured_ids(out)
        found = [
            item
            for item in found
            if hashlib.sha256(item[0].read_bytes()).hexdigest()[:16] not in done
        ]
    print(f"{len(found)} resumes not yet measured.", file=sys.stderr)
    return pick(found, sample, seed)


if __name__ == "__main__":
    raise SystemExit(main())
