"""Writes each career in each layout, has the import read it back, and scores it."""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from plytos_api.imports.ai import ResumeReader
from plytos_api.imports.bench import Ledger
from plytos_api.imports.fidelity.layouts import Layout
from plytos_api.imports.fidelity.score import Score, score
from plytos_api.imports.fidelity.truth import Career
from plytos_api.imports.pipeline import import_resume
from plytos_api.imports.usage import AiCall

# The day the readings are made on, so "present" and how long ago never move.
TODAY = date(2026, 11, 1)


def read_one(
    career: Career,
    layout: Layout,
    reader: ResumeReader | None = None,
    *,
    keep: Path | None = None,
) -> Score:
    """Writes the career in the layout, reads it back, and scores the reading. With
    `keep`, the file is saved there too, to look at."""
    data = layout.render(career)
    name = f"{career.key}-{layout.name}{layout.suffix}"
    if keep is not None:
        keep.mkdir(parents=True, exist_ok=True)
        (keep / name).write_bytes(data)
    started = time.monotonic()
    try:
        result = import_resume(data, name, today=TODAY, reader=reader)
    except Exception as exc:
        out = score(career, layout, None, failed=type(exc).__name__)
        calls: list[AiCall] = getattr(exc, "ai_calls", [])
        out.cost_usd = sum(c.cost_usd or 0.0 for c in calls)
    else:
        out = score(career, layout, result)
    out.seconds = round(time.monotonic() - started, 2)
    return out


def read_all(
    careers: list[Career],
    layouts: list[Layout],
    reader: ResumeReader | None = None,
    *,
    ledger: Ledger | None = None,
    workers: int = 1,
    keep: Path | None = None,
    heard: Callable[[Score], None] | None = None,
) -> list[Score]:
    """Every career in every layout. Layouts only Claude can read are left out when
    there's no reader. With a ledger, stops starting new ones once the budget is
    spent."""
    todo = [(c, lay) for lay in layouts for c in careers if reader is not None or not lay.needs_ai]
    done: dict[tuple[str, str], Score] = {}

    def one(pair: tuple[Career, Layout]) -> None:
        career, layout = pair
        if ledger is not None and not ledger.may_start():
            return
        result = read_one(career, layout, reader, keep=keep)
        if ledger is not None:
            ledger.add(result.cost_usd)
        done[(career.key, layout.name)] = result
        if heard is not None:
            heard(result)

    if workers <= 1:
        for pair in todo:
            one(pair)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(one, todo))
    # In the order asked for, whatever order they finished in.
    return [done[(c.key, lay.name)] for c, lay in todo if (c.key, lay.name) in done]
