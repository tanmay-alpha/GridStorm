"""CLI: ``python -m gridstorm_pypsa run --scenario s.json --network-dir DIR --out result.json``.

Prints ``STAGE <name>`` lines to stdout. Exit codes:
0 = result written (feasible OR infeasible — both are scientific outcomes),
2 = scenario rejected (invalid/unsupported; details on stderr as JSON),
1 = engine/solver error (result with ``outcome: "error"`` written if one was produced).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from stormspec import load_scenario_dict

from .runner import ScenarioRejected, run_scenario


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="gridstorm_pypsa")
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="run a StormSpec scenario with PyPSA LOPF")
    run.add_argument("--scenario", required=True, type=Path, help=".json/.yaml scenario")
    run.add_argument("--network-dir", required=True, type=Path, help="data/networks/<id>")
    run.add_argument("--out", required=True, type=Path, help="result JSON path")
    args = ap.parse_args(argv)

    def progress(stage: str) -> None:
        print(f"STAGE {stage}", flush=True)

    try:
        scenario = load_scenario_dict(args.scenario)
        result = run_scenario(scenario, args.network_dir, progress=progress)
    except ScenarioRejected as exc:
        err = {
            "error": {
                "code": exc.code,
                "message": str(exc),
                "details": {"issues": [i.model_dump() for i in exc.issues]},
            }
        }
        print(json.dumps(err), file=sys.stderr)
        return 2
    except Exception as exc:  # engine error: report, never fabricate a result
        err = {"error": {"code": "engine_error", "message": f"{type(exc).__name__}: {exc}"}}
        print(json.dumps(err), file=sys.stderr)
        return 1
    _write_json(args.out, result)
    return 1 if result["outcome"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
