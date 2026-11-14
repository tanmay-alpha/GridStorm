"""Export the StormSpec 1.0 JSON Schema.

Usage (from packages/stormspec):
    uv run python scripts/export_schema.py            # write schema/stormspec-1.0.schema.json
    uv run python scripts/export_schema.py --check    # exit 1 if the committed file is stale
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from stormspec import Scenario

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema" / "stormspec-1.0.schema.json"
SCHEMA_ID = "urn:gridstorm:schema:stormspec:1.0"


def build_schema() -> dict:
    schema = Scenario.model_json_schema(mode="validation")
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        **schema,
    }


def render() -> str:
    return json.dumps(build_schema(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="verify the committed schema is current")
    args = ap.parse_args(argv)
    text = render()
    if args.check:
        current = SCHEMA_PATH.read_text(encoding="utf-8") if SCHEMA_PATH.exists() else ""
        if current != text:
            print(f"{SCHEMA_PATH} is stale; run scripts/export_schema.py", file=sys.stderr)
            return 1
        print("schema up to date")
        return 0
    SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_PATH.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {SCHEMA_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
