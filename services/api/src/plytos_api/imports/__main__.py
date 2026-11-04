"""Runs an import on a local file: python -m plytos_api.imports resume.docx [--json].

For trying the importer on your own resume. Output goes to the terminal only.
"""

import argparse
import sys
from pathlib import Path

from plytos_api.imports.extract import UnsupportedFileError
from plytos_api.imports.pipeline import import_resume
from plytos_api.imports.report import to_markdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m plytos_api.imports")
    parser.add_argument("file", type=Path)
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = parser.parse_args(argv)
    try:
        result = import_resume(args.file.read_bytes(), args.file.name)
    except UnsupportedFileError as exc:
        print(exc, file=sys.stderr)
        return 2
    sys.stdout.write(result.model_dump_json(indent=2) if args.json else to_markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
