"""Runs an import on a local file: python -m plytos_api.imports resume.docx [--json] [--ai].

For trying the importer on your own resume. Output goes to the terminal only. With
--ai, Claude reads the structure, using the PLYTOS_AI_* settings and ANTHROPIC_API_KEY.
"""

import argparse
import sys
from pathlib import Path

from plytos_api.config import Settings
from plytos_api.imports.ai import reader_for
from plytos_api.imports.extract import UnsupportedFileError
from plytos_api.imports.pipeline import import_resume
from plytos_api.imports.report import to_markdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m plytos_api.imports")
    parser.add_argument("file", type=Path)
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    parser.add_argument("--ai", action="store_true", help="have Claude read the structure")
    args = parser.parse_args(argv)
    reader = None
    if args.ai:
        settings = Settings()
        provider = "anthropic" if settings.ai_provider == "off" else settings.ai_provider
        reader = reader_for(
            provider,
            settings.ai_model,
            settings.ai_effort,
            settings.ai_vertex_project,
            settings.ai_vertex_region,
        )
    try:
        result = import_resume(args.file.read_bytes(), args.file.name, reader=reader)
    except UnsupportedFileError as exc:
        print(exc, file=sys.stderr)
        return 2
    if args.ai and result.read_by is None:
        print("Claude couldn't read it, so the rules did.", file=sys.stderr)
    sys.stdout.write(result.model_dump_json(indent=2) if args.json else to_markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
