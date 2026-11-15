"""Precompute every ``gridstorm_analytics`` kind for every catalog network (unfiltered).

Writes ``<data-dir>/networks/<id>/analytics/<kind>.json`` (the exact ``compute()`` result) and
``index.json`` (sha256 of ``network.nc`` and of each file, source versions). The API serves these
files and never imports pypsa (docs/benchmarks/api-memory.md). Output is deterministic: no
timestamps, stable key order, fixed float repr.

    cd services/analytics && uv run python scripts/precompute_analytics.py [--network ID ...]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from importlib.metadata import version
from pathlib import Path

import pypsa

import gridstorm_analytics

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_VERSION = "gridstorm-analytics-precomputed/1.0"
COMMAND = "cd services/analytics && uv run python scripts/precompute_analytics.py"


def _dump(obj: object) -> bytes:
    return (json.dumps(obj, indent=1, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def generator() -> dict[str, str]:
    return {
        "command": COMMAND,
        "gridstorm_analytics": version("gridstorm-analytics"),
        "pypsa": pypsa.__version__,
        "pandas": version("pandas"),
        "numpy": version("numpy"),
        "python": platform.python_version(),
    }


def manifest_network_sha256(network_dir: Path) -> str | None:
    manifest = json.loads((network_dir / "manifest.json").read_text(encoding="utf-8"))
    for f in manifest.get("files") or []:
        if f.get("path") == "network.nc":
            return f.get("sha256")
    return None


def precompute(network_id: str, network_dir: Path) -> dict[str, object]:
    nc = network_dir / "network.nc"
    network_sha = _sha256(nc.read_bytes())
    expected = manifest_network_sha256(network_dir)
    if expected is not None and expected != network_sha:
        raise SystemExit(f"{network_id}: network.nc sha256 {network_sha} != manifest {expected}")
    n = pypsa.Network(str(nc))
    basis = json.loads((network_dir / "manifest.json").read_text(encoding="utf-8")).get(
        "cost_basis"
    )
    out_dir = network_dir / "analytics"
    out_dir.mkdir(exist_ok=True)
    kinds: dict[str, dict[str, object]] = {}
    for kind in gridstorm_analytics.KINDS:
        data = _dump(gridstorm_analytics.compute(kind, n, cost_basis=basis))
        (out_dir / f"{kind}.json").write_bytes(data)
        kinds[kind] = {"path": f"{kind}.json", "sha256": _sha256(data), "bytes": len(data)}
    index = {
        "schema_version": SCHEMA_VERSION,
        "network_id": network_id,
        "network_sha256": network_sha,
        "execution_mode": "precomputed",
        "provenance": "calculated",
        "filters": {"carriers": None, "countries": None},
        # PyPSA statistics apply a carrier filter only to components with a `carrier` attribute;
        # rows of these components are kept under any carrier filter (API filter derivation).
        "carrier_filter_exempt_components": sorted(
            c.name for c in n.components.values() if "carrier" not in c.static.columns
        ),
        "generator": generator(),
        "kinds": kinds,
    }
    (out_dir / "index.json").write_bytes(_dump(index))
    return index


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=REPO_ROOT / "data")
    parser.add_argument("--network", action="append", help="network id (default: whole catalog)")
    args = parser.parse_args(argv)
    networks_dir = args.data_dir / "networks"
    catalog = json.loads((networks_dir / "catalog.json").read_text(encoding="utf-8"))
    selected = set(args.network or [])
    for item in catalog["networks"]:
        if selected and item["id"] not in selected:
            continue
        network_dir = networks_dir / item["path"]
        if not (network_dir / "network.nc").is_file():
            print(f"skip {item['id']}: no network.nc", file=sys.stderr)
            continue
        index = precompute(item["id"], network_dir)
        print(f"{item['id']}: network.nc sha256 {index['network_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
