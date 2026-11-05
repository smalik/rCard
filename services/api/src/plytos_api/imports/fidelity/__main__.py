"""Scores the import on every made-up career in every layout.

    python -m plytos_api.imports.fidelity                       # the rules, no AI
    python -m plytos_api.imports.fidelity --ai --budget 20      # Claude reads them
    python -m plytos_api.imports.fidelity --only word-classic --keep /tmp/files

Real resumes, against labels written for them (real.py), on the machine that has them:

    python -m plytos_api.imports.fidelity --labels ~/.plytos/bench/labels
    python -m plytos_api.imports.fidelity --labels DIR --from-readings ~/.plytos/bench/readings/RUN
    python -m plytos_api.imports.fidelity --labels DIR --ai --budget 14 --save-readings DIR
    python -m plytos_api.imports.fidelity --labels DIR --ai --budget 14 --tape DIR

The report on real resumes is counts only. --json and --save-readings hold their words:
they're written readable by their owner only, and stay on that machine.

With --ai, spend is counted in the same ledger as the resume bench
(~/.plytos/bench/spend.json), so one budget covers both.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from plytos_api.imports.fidelity.layouts import layouts
from plytos_api.imports.fidelity.real import load_labels, read_labels, write_private
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
    parser.add_argument("--labels", type=Path, metavar="DIR", help="score real resumes")
    parser.add_argument("--sample", type=int, help="just this many labels (with --labels)")
    parser.add_argument("--seed", type=int, default=7, help="for --sample")
    parser.add_argument(
        "--from-readings", type=Path, metavar="DIR", help="score readings saved here (no AI)"
    )
    parser.add_argument("--save-readings", type=Path, metavar="DIR", help="keep each reading")
    parser.add_argument(
        "--tape",
        type=Path,
        metavar="DIR",
        help="keep Claude's answers here, and answer a question asked before from them (tape.py)",
    )
    args = parser.parse_args(argv)
    if args.write_baseline and args.ai:
        parser.error("the baseline is the rules' reading: leave out --ai")
    if args.labels is None and (args.from_readings or args.save_readings or args.sample):
        parser.error("--from-readings, --save-readings and --sample go with --labels")
    if args.labels is not None and (args.only or args.career or args.keep or args.write_baseline):
        parser.error("--only, --career, --keep and --write-baseline are for the made-up bench")
    if args.from_readings is not None and args.ai:
        parser.error("--from-readings scores saved readings: leave out --ai")
    if args.tape is not None and not args.ai:
        parser.error("--tape keeps Claude's answers: it goes with --ai")

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
        from plytos_api.imports.ai import ClaudeReader, reader_for
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
        if args.tape is not None and isinstance(reader, ClaudeReader):
            from plytos_api.imports.fidelity.tape import TapedReader

            reader = TapedReader(reader, args.tape)
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

    title = "Import fidelity, " + ("Claude reading" if reader else "rules only")
    if args.labels is not None:
        labelled, bad = load_labels(args.labels, sample=args.sample, seed=args.seed)
        print(f"{len(labelled)} labels ({bad} unreadable).", file=sys.stderr)
        scores = read_labels(
            labelled,
            reader,
            ledger=ledger,
            workers=min(4, args.workers),
            readings=args.from_readings,
            save=args.save_readings,
            heard=heard,
        )
        if args.from_readings is not None:
            title = "Import fidelity, saved readings"
        text = report(scores, title=title + ", real resumes", private=True)
    else:
        scores = read_all(
            careers,
            chosen,
            reader,
            ledger=ledger,
            workers=min(4, args.workers),
            keep=args.keep,
            heard=heard,
        )
        text = report(scores, title=title)
    if args.out:
        args.out.write_text(text)
    if args.json:
        write_private(args.json, json.dumps([s.model_dump() for s in scores], indent=1))
    if args.write_baseline:
        args.write_baseline.write_text(json.dumps(baseline(scores), indent=1) + "\n")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
