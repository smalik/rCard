"""Scores the import on every made-up career in every layout.

    python -m plytos_api.imports.fidelity                       # the rules, no AI
    python -m plytos_api.imports.fidelity --ai --budget 20      # Claude reads them
    python -m plytos_api.imports.fidelity --only word-classic --keep /tmp/files

With --ai, spend is counted in the same ledger as the resume bench
(~/.plytos/bench/spend.json), so one budget covers both.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from plytos_api.imports.fidelity.layouts import layouts
from plytos_api.imports.fidelity.run import read_all
from plytos_api.imports.fidelity.score import Score, baseline, report
from plytos_api.imports.fidelity.truth import CAREERS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m plytos_api.imports.fidelity")
    parser.add_argument("--ai", action="store_true", help="have Claude read them")
    parser.add_argument("--budget", type=float, help="USD, across all bench runs (with --ai)")
    parser.add_argument("--only", nargs="+", metavar="LAYOUT", help="just these layouts")
    parser.add_argument("--career", nargs="+", metavar="KEY", help="just these careers")
    parser.add_argument("--workers", type=int, default=1, help="resumes at once (at most 4)")
    parser.add_argument("--keep", type=Path, help="save each file written here, to look at")
    parser.add_argument("--out", type=Path, help="write the report here as well")
    parser.add_argument("--json", type=Path, help="write every score here")
    parser.add_argument(
        "--ledger", type=Path, default=Path.home() / ".plytos" / "bench" / "spend.json"
    )
    parser.add_argument(
        "--write-baseline",
        type=Path,
        metavar="PATH",
        help="write the rules' scores on the Word and PDF layouts as the floor CI holds to",
    )
    args = parser.parse_args(argv)
    if args.write_baseline and args.ai:
        parser.error("the baseline is the rules' reading: leave out --ai")

    chosen = layouts()
    if args.only:
        unknown = set(args.only) - {lay.name for lay in chosen}
        if unknown:
            parser.error(f"unknown layouts: {', '.join(sorted(unknown))}")
        chosen = [lay for lay in chosen if lay.name in args.only]
    careers = [c for c in CAREERS if not args.career or c.key in args.career]

    reader = None
    ledger = None
    if args.ai:
        if args.budget is None:
            parser.error("--ai needs --budget")
        from plytos_api.config import Settings
        from plytos_api.imports.ai import reader_for
        from plytos_api.imports.bench import Ledger

        settings = Settings()
        provider = "anthropic" if settings.ai_provider == "off" else settings.ai_provider
        reader = reader_for(
            provider,
            settings.ai_model,
            settings.ai_effort,
            settings.ai_vertex_project,
            settings.ai_vertex_region,
        )
        args.ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger = Ledger(args.ledger, args.budget)
        print(f"Spent so far ${ledger.spent:.2f} of ${args.budget:.2f}.", file=sys.stderr)

    def heard(s: Score) -> None:
        print(
            f"{s.career}/{s.layout}: {100 * s.fidelity:.0f}%"
            + (f" failed {s.failed}" if s.failed else "")
            + (f" ${s.cost_usd:.4f}" if s.cost_usd else ""),
            file=sys.stderr,
        )

    scores = read_all(
        careers,
        chosen,
        reader,
        ledger=ledger,
        workers=min(4, args.workers),
        keep=args.keep,
        heard=heard,
    )
    title = "Import fidelity, " + ("Claude reading" if reader else "rules only")
    text = report(scores, title=title)
    if args.out:
        args.out.write_text(text)
    if args.json:
        args.json.write_text(json.dumps([s.model_dump() for s in scores], indent=1))
    if args.write_baseline:
        args.write_baseline.write_text(json.dumps(baseline(scores), indent=1) + "\n")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
