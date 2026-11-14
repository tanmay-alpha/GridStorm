"""Export JSON Schemas to ``packages/canonical-grid/schema/``.

Usage: ``uv run python -m canonical_grid.schema_export [--check]``
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from canonical_grid.models import CanonicalNetwork, DatasetManifest, NetworkCatalog

SCHEMAS = {
    "canonical-grid-1.0.schema.json": (CanonicalNetwork, "canonical-grid/1.0"),
    "dataset-manifest-1.0.schema.json": (DatasetManifest, "dataset-manifest/1.0"),
    "network-catalog-1.0.schema.json": (NetworkCatalog, "network-catalog/1.0"),
}

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "schema"


def render() -> dict[str, str]:
    out: dict[str, str] = {}
    for filename, (model, version) in SCHEMAS.items():
        schema = model.model_json_schema(mode="validation")
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"https://gridstorm.dev/schema/{filename}",
            "title": version,
            **{k: v for k, v in schema.items() if k != "title"},
        }
        out[filename] = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--check", action="store_true", help="fail if committed schemas are stale")
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    stale = []
    for filename, text in render().items():
        path = args.out / filename
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(filename)
        else:
            path.write_text(text, encoding="utf-8", newline="\n")
            print(f"wrote {path}")
    if stale:
        print(f"stale schemas: {stale}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
