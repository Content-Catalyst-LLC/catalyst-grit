"""Command-line interface for the canonical recovery-record engine."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .core import GritValidationError, generate_record, to_markdown
from .version import __version__


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GritValidationError(f"input file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise GritValidationError(f"invalid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise GritValidationError("input JSON must contain an object")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="grit", description="Generate and validate Catalyst Grit recovery records."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="Generate a recovery record")
    generate.add_argument("input", type=Path, help="Input JSON path")
    generate.add_argument("--format", choices=("json", "markdown"), default="json")
    generate.add_argument("--output", type=Path)

    validate = subparsers.add_parser("validate", help="Normalize and validate an input")
    validate.add_argument("input", type=Path, help="Input JSON path")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        data = _read_json(args.input)
        record = generate_record(data)
        if args.command == "validate":
            print("Catalyst Grit input is valid.")
            return 0
        rendered = (
            json.dumps(record.to_dict(), indent=2)
            if args.format == "json"
            else to_markdown(record)
        )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered.rstrip() + "\n", encoding="utf-8")
        else:
            print(rendered)
        return 0
    except GritValidationError as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
