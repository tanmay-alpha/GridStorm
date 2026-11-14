"""StormSpec engine adapter: ``run_scenario(scenario, network_dir) -> gridstorm-result/1.0 dict``.

Supported (``execution.engine == "pandapower"``): formulations ``ac_pf`` and ``n_minus_1``; one
snapshot; events ``line_outage`` (component line|transformer), ``generator_outage`` and
``demand_multiplier`` without windows; ``mitigation.load_shedding.enabled = false``. Everything else
raises :class:`ScenarioRejected` (code ``unsupported_operation``) — nothing is approximated.

Event semantics:

* ``demand_multiplier`` scales ``p_mw`` and ``q_mvar`` (constant power factor) of the loads at
  ``buses`` (all loads if null); several multipliers compound multiplicatively.
* ``generator_outage`` takes the generator out of service; its active power is picked up by the
  slack. If the outaged unit is the only slack, the in-service generator with the largest ``Pmax``
  becomes the slack (reported in ``warnings``).
* ``line_outage`` takes the line / transformer out of service (topology change).

The operating point before events is the AC-OPF dispatch (see :mod:`.operating_point`); events
are applied afterwards without re-dispatch.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import matpowercaseframes
import numba
import numpy as np
import pandapower as pp
import pandas as pd
import scipy
import stormspec
from pydantic import ValidationError
from stormspec import ExecutionManifest, Scenario, file_sha256, result_sha256, scenario_hash
from stormspec.manifest import detect_git_sha, utc_now_iso

from .contingency import contingency_study, evaluate_state, total_load_mw
from .model import GridModel, load_matpower, resolve_case_file
from .operating_point import apply_acopf_dispatch
from .powerflow import PF_OPTIONS, bus_voltages, power_balance, run_pf

ENGINE = "pandapower"
STAGES = ("loading_network", "applying_scenario", "building_model", "solving",
          "postprocessing", "done")

ASSUMPTIONS = [
    "Steady-state balanced AC power flow (pandapower Newton-Raphson, single snapshot); no "
    "protection, dynamics or transient stability.",
    "Operating point before events: pandapower AC-OPF dispatch of the unperturbed case; events are "
    "applied without re-dispatch, the single slack absorbs any active-power imbalance.",
    "Generator reactive-power limits are not enforced in the power flow.",
    "Line loading = apparent power at the more loaded end / RATE_A (MVA); RATE_A = 0 is unlimited.",
    "Loads are constant-power (P and Q); demand multipliers keep the power factor.",
    "Islanded buses (no path to a slack) are de-energised; their load counts as unserved.",
]


class ScenarioRejected(ValueError):
    """Scenario cannot be run by the pandapower adapter (``issues`` explain why)."""

    def __init__(self, issues: list[dict[str, str]]):
        self.issues = issues
        self.code = issues[0]["code"] if issues else "unsupported_operation"
        super().__init__("; ".join(f"{i['code']} at {i['path']}: {i['message']}" for i in issues))


def _issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _parse(scenario: Scenario | dict) -> Scenario:
    if isinstance(scenario, Scenario):
        return scenario
    try:
        return Scenario.model_validate(scenario)
    except ValidationError as exc:
        raise ScenarioRejected(
            [_issue("schema_error", ".".join(map(str, e["loc"])) or "$", e["msg"])
             for e in exc.errors()]
        ) from None


def check_scenario(scenario: Scenario) -> list[dict[str, str]]:
    """Engine-level checks that need no network."""
    issues = []
    if scenario.execution.engine != ENGINE:
        issues.append(_issue("unsupported_operation", "execution.engine",
                             f"pandapower adapter cannot run engine {scenario.execution.engine!r}"))
    issues += [i.model_dump() for i in stormspec.check_capabilities(scenario)]
    return issues


def _load_network(scenario: Scenario, network_dir: Path) -> tuple[GridModel, Path, dict | None]:
    network_id = scenario.dataset.network_id
    try:
        case_path = resolve_case_file(network_id, network_dir)
    except (FileNotFoundError, ValueError) as exc:
        raise ScenarioRejected([_issue("unsupported_operation", "dataset.network_id", str(exc))]) \
            from None
    canonical_path = network_dir / "canonical.json"
    canonical = (json.loads(canonical_path.read_text(encoding="utf-8"))
                 if canonical_path.is_file() else None)
    return load_matpower(case_path, network_id), case_path, canonical


def _validate_against_network(scenario: Scenario, model: GridModel, canonical: dict | None,
                              network_dir: Path) -> list[dict[str, str]]:
    report = stormspec.validate(scenario, canonical or model.canonical_index())
    issues = [i.model_dump() for i in report.errors]
    pinned = scenario.dataset.sha256
    nc = network_dir / "network.nc"
    if pinned is not None and nc.is_file() and file_sha256(nc) != pinned:
        issues.append(_issue("dataset_mismatch", "dataset.sha256",
                             f"pinned sha256 {pinned} != {nc.name} sha256"))
    # the engine id map must resolve every referenced asset (canonical.json and case must agree)
    for i, ev in enumerate(scenario.events):
        try:
            if ev.type == "line_outage":
                model.branch(ev.asset_id, ev.component)
            elif ev.type == "generator_outage":
                model.gen(ev.asset_id)
            elif ev.type == "demand_multiplier" and ev.buses:
                missing = [b for b in ev.buses if f"load-{b[4:]}" not in model.loads]
                if missing:
                    issues.append(_issue("no_loads", f"events[{i}].buses",
                                         f"no load at {missing} in the MATPOWER case"))
        except KeyError as exc:
            issues.append(_issue("unknown_asset", f"events[{i}].asset_id", str(exc.args[0])))
    return issues


def _apply_events(scenario: Scenario, model: GridModel) -> tuple[set[str], set[str], list[str]]:
    net = model.net
    out_branches: set[str] = set()
    out_gens: set[str] = set()
    warnings: list[str] = []
    for ev in scenario.events:
        if ev.type == "demand_multiplier":
            if ev.buses is None:
                sel = net.load.index
            else:
                sel = [model.loads[f"load-{b[4:]}"] for b in ev.buses]
            net.load.loc[sel, "p_mw"] *= ev.value
            net.load.loc[sel, "q_mvar"] *= ev.value
        elif ev.type == "line_outage":
            br = model.branch(ev.asset_id, ev.component)
            net[br.table].at[br.index, "in_service"] = False
            out_branches.add(f"{br.component}:{br.id}")
        elif ev.type == "generator_outage":
            g = model.gen(ev.asset_id)
            net[g.table].at[g.index, "in_service"] = False
            out_gens.add(g.id)
    has_slack = bool(net.ext_grid.in_service.any()) or bool((net.gen.slack & net.gen.in_service).any())
    if not has_slack:
        cand = net.gen[net.gen.in_service]
        if cand.empty:
            raise ScenarioRejected([_issue("unsupported_operation", "events",
                                           "no in-service synchronous generator left as slack")])
        new = int(cand.max_p_mw.idxmax())
        net.gen.at[new, "slack"] = True
        warnings.append(
            f"slack generator outaged; {model.gen_for_element('gen', new).id} (largest Pmax) "
            "takes over as slack and absorbs the lost generation"
        )
    return out_branches, out_gens, warnings


def _r(x: float | None, nd: int = 4) -> float | None:
    return None if x is None or not np.isfinite(x) else round(float(x), nd)


def _package_versions() -> dict[str, str]:
    return {"pandapower": pp.__version__, "numpy": np.__version__, "scipy": scipy.__version__,
            "pandas": pd.__version__, "numba": numba.__version__,
            "matpowercaseframes": getattr(matpowercaseframes, "__version__", "unknown"),
            "stormspec": stormspec.__version__}


def run_scenario(scenario: Scenario | dict, network_dir: str | Path, *,
                 progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Run a StormSpec scenario with steady-state AC power flow (and optional N-1)."""
    started = utc_now_iso()
    emit = progress or (lambda _stage: None)
    sc = _parse(scenario)
    issues = check_scenario(sc)
    if issues:
        raise ScenarioRejected(issues)
    network_dir = Path(network_dir)

    emit("loading_network")
    model, case_path, canonical = _load_network(sc, network_dir)
    issues = _validate_against_network(sc, model, canonical, network_dir)
    if issues:
        raise ScenarioRejected(issues)

    emit("applying_scenario")
    opf = apply_acopf_dispatch(model)
    warnings: list[str] = list(model.notes)
    if not opf["converged"]:
        warnings.append(f"AC-OPF base dispatch failed ({opf['message']}); case-file generator "
                        "set points used as operating point")
    out_branches, out_gens, ev_warn = _apply_events(sc, model)
    warnings += ev_warn

    emit("building_model")
    net = model.net
    emit("solving")
    pf = run_pf(net, init="dc")

    emit("postprocessing")
    termination = "converged" if pf.converged else ("error" if pf.error else "not_converged")
    outcome = "feasible" if pf.converged else ("error" if pf.error else "infeasible")
    if not pf.converged and pf.error is None:
        warnings.append("Newton-Raphson did not converge; this does not prove that no AC "
                        "operating point exists (possible voltage collapse)")
    result: dict[str, Any] = {
        "schema_version": "gridstorm-result/1.0",
        "scenario_id": sc.id,
        "scenario_hash": scenario_hash(sc),
        "network_id": model.network_id,
        "engine": {"name": ENGINE, "version": pp.__version__,
                   "formulation": sc.execution.formulation},
        "solver": {"name": "newton_raphson", "version": pp.__version__,
                   "status": "ok" if pf.converged else ("error" if pf.error else "warning"),
                   "termination_condition": termination, "objective_eur": None,
                   "wall_time_s": round(pf.wall_time_s, 4)},
        "outcome": outcome,
        "snapshots": ["now"],
        "snapshot_weightings_h": [1.0],
        "operating_point": {"source": "acopf" if opf["converged"] else "case_file_setpoints",
                            "acopf_converged": opf["converged"],
                            "acopf_objective_cost": _r(opf["objective"], 2)},
        "metrics": None,
        "ac": None,
        "series": {},
        "assets": {},
        "contingency": None,
        "assumptions": ASSUMPTIONS + list(sc.assumptions),
        "warnings": warnings,
    }
    if pf.error:
        result["error"] = {"code": "solver_error", "message": pf.error}
    if pf.converged:
        _fill_solution(result, model, canonical, out_branches, out_gens)
        if sc.execution.formulation == "n_minus_1":
            result["contingency"] = contingency_study(model)
    result["manifest"] = ExecutionManifest(
        scenario_hash=result["scenario_hash"],
        dataset_sha256=file_sha256(case_path),
        engine_name=ENGINE,
        engine_version=pp.__version__,
        solver_name="newton_raphson",
        solver_version=pp.__version__,
        solver_options={k: v for k, v in PF_OPTIONS.items() if k != "numba"},
        package_versions=_package_versions(),
        started_at=started,
        finished_at=utc_now_iso(),
        result_sha256=result_sha256(result),
        git_sha=detect_git_sha(Path(__file__)),
    ).model_dump(mode="json")
    emit("done")
    return result


def _fill_solution(result: dict, model: GridModel, canonical: dict | None,
                   out_branches: set[str], out_gens: set[str]) -> None:
    net = model.net
    # islanding after events: in-service buses without a path to a slack
    in_service_buses = {int(i) for i in net.bus.index[net.bus.in_service]}
    st = evaluate_state(model, net, total_load_mw=total_load_mw(net),
                        base_energised=in_service_buses)
    bal = power_balance(net)
    load_total = total_load_mw(net)
    unserved = st["islanded_load_mw"]
    flows = st["flows"]
    loadings = [f["loading_pct"] for f in flows if f["loading_pct"] is not None]

    carrier_of = {g["id"]: g.get("carrier") or "unknown"
                  for g in (canonical or {}).get("generators", [])}
    gen_rows, by_carrier = [], {}
    for g in model.gens:
        p = float(net[f"res_{g.table}"].at[g.index, "p_mw"])
        q = float(net[f"res_{g.table}"].at[g.index, "q_mvar"])
        p, q = (0.0 if not np.isfinite(p) else p), (0.0 if not np.isfinite(q) else q)
        carrier = carrier_of.get(g.id, "unknown")
        by_carrier[carrier] = by_carrier.get(carrier, 0.0) + p
        gen_rows.append({"id": g.id, "carrier": carrier, "bus": g.bus, "p_mw": [_r(p, 3)],
                         "q_mvar": [_r(q, 3)], "outaged": g.id in out_gens})

    result["metrics"] = {
        "total_load_mwh": _r(load_total, 3),
        "served_load_mwh": _r(load_total - unserved, 3),
        "unserved_energy_mwh": _r(unserved, 3),
        "peak_load_shed_mw": _r(unserved, 3),
        "load_shed_hours": 1.0 if unserved > 0 else 0.0,
        "total_system_cost_eur": None,
        "generation_cost_eur": None,
        "load_shedding_cost_eur": None,
        "generation_by_carrier_mwh": {k: _r(v, 3) for k, v in sorted(by_carrier.items())},
        "curtailment_mwh": None,
        "curtailment_by_carrier_mwh": {},
        "max_line_loading_pct": _r(max(loadings), 2) if loadings else None,
        "mean_line_loading_pct": _r(float(np.mean(loadings)), 2) if loadings else None,
        "congested_line_count": sum(lp >= 99.9 for lp in loadings),
        "storage_discharge_mwh": None,
        "storage_charge_mwh": None,
        "co2_emissions_t": None,
        "balance_residual_max_mw": float(f"{abs(bal['residual_mw']):.3e}"),
    }
    result["ac"] = {
        "converged": True,
        "losses_mw": _r(bal["losses_mw"], 3),
        "generation_mw": _r(bal["generation_mw"], 3),
        "load_mw": _r(bal["load_mw"], 3),
        "min_vm_pu": _r(st["min_vm_pu"]),
        "max_vm_pu": _r(st["max_vm_pu"]),
        "classes": st["flags"] or ["secure"],
        "thermal_overloads": st["overloads"],
        "voltage_violations": st["voltage_violations"],
        "islanded_buses": st["islanded_buses"],
        "islanded_load_mw": _r(unserved, 3),
        "slack_p_mw": _r(float(net.res_ext_grid.p_mw.sum())
                         + float(net.res_gen.p_mw[net.gen.slack].sum()), 3),
    }
    result["series"] = {"load_mw": [_r(bal["load_mw"], 3)], "load_shed_mw": [_r(unserved, 3)]}
    volts = bus_voltages(model, net)
    branch_rows = {"lines": [], "transformers": []}
    for f in flows:
        br = f["ref"]
        branch_rows["lines" if br.component == "line" else "transformers"].append({
            "id": br.id, "bus0": br.from_bus, "bus1": br.to_bus, "s_nom_mva": br.rate_a_mva,
            "outaged": f"{br.component}:{br.id}" in out_branches,
            "flow_mw": [_r(f["p_from_mw"], 3)], "flow_mvar": [_r(f["q_from_mvar"], 3)],
            "flow_to_mw": [_r(f["p_to_mw"], 3)], "loading_pct": [_r(f["loading_pct"], 2)],
        })
    result["assets"] = {
        **branch_rows,
        "buses": [{"id": b, "vm_pu": [_r(volts[b][0])], "va_deg": [_r(volts[b][1])],
                   "vm_min_pu": model.vm_limits[b][0], "vm_max_pu": model.vm_limits[b][1]}
                  for b in model.buses],
        "generators": gen_rows,
    }
