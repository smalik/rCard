"""Scores the import on real resumes, against labels kept on the machine that has them.

A label (truth.Career, as JSON) names the file it describes in `source`, and its `key`
is the file's id: the first 16 hex characters of the sha256 of its bytes, as the resume
bench names it. Labels, readings and per-resume scores hold a real person's words, so
they're written readable by their owner only and never leave that machine; what's
reported from them is counts (score.report(private=True)).
"""

from __future__ import annotations

import hashlib
import os
import random
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from plytos_api.imports.ai import ResumeReader
from plytos_api.imports.bench import Ledger
from plytos_api.imports.fidelity.run import TODAY
from plytos_api.imports.fidelity.score import Score, score
from plytos_api.imports.fidelity.truth import Career
from plytos_api.imports.model import ImportResult
from plytos_api.imports.pipeline import import_resume
from plytos_api.imports.usage import AiCall


def file_id(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def load_labels(
    folder: Path, *, sample: int | None = None, seed: int = 7
) -> tuple[list[Career], int]:
    """The labels in a folder, in a fixed order (or a fixed sample of them), and how
    many files there couldn't be read as one."""
    careers: list[Career] = []
    bad = 0
    for path in sorted(folder.glob("*.json")):
        try:
            careers.append(Career.model_validate_json(path.read_text()))
        except ValueError:
            bad += 1
    if sample is not None and sample < len(careers):
        picked = random.Random(seed).sample(careers, sample)  # noqa: S311 (a fixed sample)
        careers = sorted(picked, key=lambda c: c.key)
    return careers, bad


def _kind(result: ImportResult) -> str:
    facts = result.facts
    return "scan" if facts.scanned_pages or not facts.has_text_layer else facts.format


def write_private(path: Path, text: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(text)
    os.chmod(path, 0o600)


def read_label(
    career: Career,
    reader: ResumeReader | None = None,
    *,
    readings: Path | None = None,
    save: Path | None = None,
) -> Score | None:
    """Reads the labelled file and scores the reading. With `readings`, scores the
    reading saved there instead (no Claude calls), or nothing when there isn't one.
    With `save`, keeps the reading there to score again later."""
    source = Path(career.source or "")
    group = source.parent.name or "unknown"
    if readings is not None:
        saved = readings / f"{career.key}.json"
        if not saved.exists():
            return None
        result = ImportResult.model_validate_json(saved.read_text())
        return score(career, None, result, kind=_kind(result), name=group)
    try:
        data = source.read_bytes()
    except OSError as exc:
        return score(career, None, None, failed=type(exc).__name__, kind="?", name=group)
    if file_id(data) != career.key:
        return score(career, None, None, failed="LabelIsForAnotherFile", kind="?", name=group)
    started = time.monotonic()
    try:
        result = import_resume(data, source.name, today=TODAY, reader=reader)
    except Exception as exc:
        out = score(career, None, None, failed=type(exc).__name__, kind="?", name=group)
        calls: list[AiCall] = getattr(exc, "ai_calls", [])
        out.cost_usd = sum(c.cost_usd or 0.0 for c in calls)
    else:
        if save is not None:
            write_private(save / f"{career.key}.json", result.model_dump_json())
        out = score(career, None, result, kind=_kind(result), name=group)
    out.seconds = round(time.monotonic() - started, 2)
    return out


def read_labels(
    careers: list[Career],
    reader: ResumeReader | None = None,
    *,
    ledger: Ledger | None = None,
    workers: int = 1,
    readings: Path | None = None,
    save: Path | None = None,
    heard: Callable[[Score], None] | None = None,
) -> list[Score]:
    """Every labelled resume, in the labels' order. With a ledger, stops starting new
    ones once the budget is spent."""
    done: dict[str, Score] = {}

    def one(career: Career) -> None:
        if ledger is not None and not ledger.may_start():
            return
        result = read_label(career, reader, readings=readings, save=save)
        if result is None:
            return
        if ledger is not None:
            ledger.add(result.cost_usd)
        done[career.key] = result
        if heard is not None:
            heard(result)

    if workers <= 1:
        for career in careers:
            one(career)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(one, careers))
    return [done[c.key] for c in careers if c.key in done]
