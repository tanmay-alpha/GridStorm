"""Validate and run the generated observed-analogue scenarios with the PyPSA adapter.

Run with the ``workers/pypsa`` environment (it provides ``gridstorm_pypsa``)::

    cd workers/pypsa
    OMP_NUM_THREADS=1 uv run python ../../pipelines/observed/scripts/run_analogues.py \
        [--network-dir ../../data/networks/scigrid-de]

Each ``data/scenarios/observed/*.yaml`` is validated with ``stormspec.validate`` against the
network's ``canonical.json`` (when present) and against the index of the loaded PyPSA network,
then solved with ``gridstorm_pypsa.run_scenario`` one at a time (HiGHS, threads = 1). A compact
summary of the real results is written to ``data/observed/analogue-results.json``; the full
``gridstorm-result/1.0`` documents go to the data cache outside the repository.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import stormspec
from gridstorm_pypsa import load_network, network_index, run_scenario

REPO_ROOT = Path(__file__).resolve().parents[3]
SCENARIO_DIR = REPO_ROOT / "data" / "scenarios" / "observed"
OUT_PATH = REPO_ROOT / "data" / "observed" / "analogue-results.json"
RES_CARRIERS = ("Wind Onshore", "Wind Offshore", "Solar")
METRIC_KEYS = (
    "total_load_mwh",
    "unserved_energy_mwh",
    "peak_load_shed_mw",
    "load_shed_hours",
    "total_system_cost_eur",
    "generation_cost_eur",
    "load_shedding_cost_eur",
    "curtailment_mwh",
    "curtailment_by_carrier_mwh",
    "max_line_loading_pct",
    "mean_line_loading_pct",
    "congested_line_count",
    "storage_discharge_mwh",
)


def _cache_dir() -> Path:
    env = os.environ.get("GRIDSTORM_DATA_CACHE")
    path = (Path(env) if env else REPO_ROOT.parent / "upstream" / "_data_cache") / "observed-runs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _issues(report) -> dict:
    return {
        "valid": report.valid,
        "errors": [f"{i.code} {i.path}: {i.message}" for i in report.errors],
        "warnings": sorted({i.code for i in report.warnings}),
        "warning_count": len(report.warnings),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--network-dir", type=Path,
                    default=REPO_ROOT / "data" / "networks" / "scigrid-de")
    args = ap.parse_args(argv)
    ndir = args.network_dir.resolve()
    nc_sha = stormspec.file_sha256(ndir / "network.nc")
    canonical_path = ndir / "canonical.json"
    canonical = (
        json.loads(canonical_path.read_text(encoding="utf-8")) if canonical_path.exists() else None
    )
    pypsa_index = network_index(load_network(ndir), "scigrid-de")

    paths = sorted(SCENARIO_DIR.glob("*.yaml"))
    if not paths:
        raise SystemExit(f"no scenarios in {SCENARIO_DIR}")
    scenarios = [(p, stormspec.load_scenario(p)) for p in paths]
    # Reference run: identical settings, no events = the network's own 2011-01-01 day.
    first = scenarios[0][1]
    baseline = first.model_copy(update={
        "id": "observed-baseline-network-day",
        "name": "Baseline: scigrid-de 2011-01-01 without events (same settings)",
        "description": "Reference for the observed-analogue scenarios; not written to disk.",
        "events": [],
        "assumptions": [],
    })

    runs = []
    failed = False
    for path, scen in [(None, baseline), *scenarios]:
        entry: dict = {
            "scenario_id": scen.id,
            "role": "baseline" if path is None else "observed_analogue",
            "scenario_file": path.relative_to(REPO_ROOT).as_posix() if path else None,
            "scenario_sha256": stormspec.file_sha256(path) if path else None,
            "scenario_hash": stormspec.scenario_hash(scen),
            "events": len(scen.events),
            "validation": {
                "canonical_json": _issues(stormspec.validate(scen, canonical))
                if canonical is not None else None,
                "pypsa_network_index": _issues(stormspec.validate(scen, pypsa_index)),
            },
        }
        print(f"[{scen.id}] solving ...", flush=True)
        t0 = time.perf_counter()
        result = run_scenario(scen, ndir)
        elapsed = time.perf_counter() - t0
        full = _cache_dir() / f"{scen.id}.result.json"
        full.write_text(json.dumps(result, indent=1), encoding="utf-8")
        metrics = result.get("metrics") or {}
        by_carrier = metrics.get("curtailment_by_carrier_mwh") or {}
        entry.update({
            "outcome": result["outcome"],
            "provenance": result["provenance"],
            "solver": result["solver"],
            "run_wall_time_s": round(elapsed, 2),
            "metrics": {k: metrics.get(k) for k in METRIC_KEYS},
            "wind_solar_curtailment_mwh": round(
                sum(float(by_carrier.get(c) or 0.0) for c in RES_CARRIERS), 3),
            "generation_by_carrier_mwh": metrics.get("generation_by_carrier_mwh"),
            "result_warnings": result["warnings"],
            "dataset_sha256": result["manifest"]["dataset_sha256"],
            "result_sha256": result["manifest"]["result_sha256"],
            "package_versions": result["manifest"]["package_versions"],
        })
        failed |= result["outcome"] != "feasible"
        runs.append(entry)
        m = entry["metrics"]
        print(
            f"[{scen.id}] {result['outcome']} cost={m.get('total_system_cost_eur')} "
            f"unserved={m.get('unserved_energy_mwh')} MWh "
            f"res_curtail={entry['wind_solar_curtailment_mwh']} MWh "
            f"max_loading={m.get('max_line_loading_pct')}% ({elapsed:.1f}s)",
            flush=True,
        )

    summary = {
        "schema_version": "gridstorm-observed-runs/1.0",
        "provenance": "modeled",
        "network_id": "scigrid-de",
        "network_nc_sha256": nc_sha,
        "canonical_json_present": canonical is not None,
        "runs": runs,
    }
    OUT_PATH.write_bytes((json.dumps(summary, indent=2) + "\n").encode("utf-8"))
    print(f"wrote {OUT_PATH}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
