"""Test-only stand-in for ``python -m gridstorm_pypsa run`` (same CLI and output contract).

Behaviour is selected by ``assumptions`` entries in the scenario (they are part of the hash):
``fake:fail`` (exit 3), ``fake:sleep=<s>`` (sleep before writing), ``fake:memory`` (allocate until
killed), ``fake:infeasible``, ``fake:garbage`` (invalid output), ``fake:wrong-hash``.
Metrics scale with the product of ``demand_multiplier`` values so comparisons have real deltas.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

import stormspec


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cmd", choices=["run"])
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--network-dir", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    with open(args.scenario, encoding="utf-8") as fh:
        spec = json.load(fh)
    scenario = stormspec.Scenario.model_validate(spec)
    flags = {a.split("=")[0]: (a.split("=", 1)[1] if "=" in a else "") for a in spec["assumptions"]}

    print("STAGE loading_network", flush=True)
    print("STAGE applying_scenario", flush=True)
    if "fake:fail" in flags:
        print("boom: synthetic engine failure", file=sys.stderr, flush=True)
        return 3
    if "fake:sleep" in flags:
        print("STAGE solving", flush=True)
        time.sleep(float(flags["fake:sleep"]))
    if "fake:memory" in flags:
        print("STAGE building_model", flush=True)
        hog = []
        for _ in range(100):  # up to ~1 GB, 10 MB at a time; the watchdog must kill us first
            hog.append(bytearray(10 * 1024 * 1024))
            time.sleep(0.05)
        return 0
    print("STAGE building_model", flush=True)
    print("STAGE solving", flush=True)
    print("STAGE postprocessing", flush=True)

    if "fake:garbage" in flags:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write('{"not": "a result"}')
        print("STAGE done", flush=True)
        return 0

    mult = 1.0
    for ev in spec["events"]:
        if ev["type"] == "demand_multiplier":
            mult *= ev["value"]
    infeasible = "fake:infeasible" in flags
    load = 100.0 * mult
    n = scenario.horizon.snapshots
    metrics = (
        {}
        if infeasible
        else {
            "total_load_mwh": load * n,
            "served_load_mwh": min(load, 110.0) * n,
            "unserved_energy_mwh": max(0.0, load - 110.0) * n,
            "peak_load_shed_mw": max(0.0, load - 110.0),
            "load_shed_hours": n if load > 110.0 else 0,
            "total_system_cost_eur": 50.0 * load * n,
            "generation_cost_eur": 50.0 * min(load, 110.0) * n,
            "load_shedding_cost_eur": 0.0,
            "generation_by_carrier_mwh": {"gas": 60.0 * n, "wind": (min(load, 110.0) - 60.0) * n},
            "curtailment_mwh": 0.0,
            "curtailment_by_carrier_mwh": {"wind": 0.0},
            "max_line_loading_pct": 40.0 * mult,
            "mean_line_loading_pct": 20.0 * mult,
            "congested_line_count": 0,
            "storage_discharge_mwh": 0.0,
            "storage_charge_mwh": 0.0,
            "co2_emissions_t": 0.4 * 60.0 * n,
            "balance_residual_max_mw": 0.0,
        }
    )
    result = {
        "schema_version": "gridstorm-result/1.0",
        "scenario_id": scenario.id,
        "scenario_hash": "0" * 64
        if "fake:wrong-hash" in flags
        else stormspec.scenario_hash(scenario),
        "network_id": scenario.dataset.network_id,
        "engine": {"name": "fake", "version": "0.0", "formulation": "lopf"},
        "solver": {
            "name": "highs",
            "version": "test",
            "status": "warning" if infeasible else "ok",
            "termination_condition": "infeasible" if infeasible else "optimal",
            "objective_eur": None if infeasible else 50.0 * load * n,
            "wall_time_s": 0.01,
        },
        "outcome": "infeasible" if infeasible else "feasible",
        "snapshots": [] if infeasible else [f"2020-01-01T{h:02d}:00:00" for h in range(n)],
        "snapshot_weightings_h": [] if infeasible else [1.0] * n,
        "metrics": metrics,
        "series": {},
        "assets": {
            "lines": []
            if infeasible
            else [
                {
                    "id": "l0",
                    "s_nom_mva": 200.0,
                    "outaged": False,
                    "flow_mw": [load * 0.8] * n,
                    "loading_pct": [40.0 * mult] * n,
                },
            ],
            "transformers": []
            if infeasible
            else [
                {
                    "id": "l0",
                    "s_nom_mva": 100.0,
                    "outaged": False,
                    "flow_mw": [10.0] * n,
                    "loading_pct": [10.0] * n,
                },
            ],
            "links": [],
            "buses": [],
            "generators": [],
            "storage_units": [],
        },
        "assumptions": ["fake engine for API tests"],
        "warnings": [],
        "manifest": {"schema_version": "execution-manifest/1.0", "engine": "fake"},
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh)
    print("STAGE done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
