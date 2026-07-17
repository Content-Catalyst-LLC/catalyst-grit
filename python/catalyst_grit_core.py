#!/usr/bin/env python3
"""Compatibility entry point for the canonical Catalyst Grit package.

Prefer the installed `grit generate` command. This wrapper keeps the v1.0.0
repository command working while routing every calculation through the package.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from catalyst_grit import generate_record, to_markdown  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a Catalyst Grit recovery record.")
    parser.add_argument("input", type=Path, help="Path to input JSON")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))
    record = generate_record(data)
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


if __name__ == "__main__":
    raise SystemExit(main())
