"""Compare the engine outputs in _work/ and write the cross-engine benchmark artifacts.

    uv run --project pipelines/network-import python tests/cross_engine/compare.py [<id> ...]

Inputs: _work/<id>.pandapower.json, _work/<id>.pypsa.json, _work/<id>.reference.json (written by
pp_side.py / pypsa_side.py). Outputs:
  * data/artifacts/cross-engine/cross-engine-<id>.json  (contracts.md §5, kind "benchmark")
  * data/artifacts/cross-engine/index.json
  * _work/tables.md (the markdown tables quoted in docs/benchmarks/cross-engine.md)

Verdicts: AGREES (metric <= tolerance), DISAGREES (metric > tolerance), EXPECTED_DIFFERENCE (a
modelling difference that is reported, not judged: AC vs DC), NOT_RUN (an engine failed or skipped).
"""

from __future__ import annotations

import hashlib
import json
import math
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mpc  # noqa: E402
import numpy as np  # noqa: E402

ARTIFACT_DIR = mpc.REPO / "data" / "artifacts" / "cross-engine"
ENGINE = "cross-engine"
COMMAND = "python tests/cross_engine/run_all.py"

# Tolerances (absolute, per branch / generator). Both DC power flows solve the same linear system
# B' theta = P, so the only legitimate difference is floating-point rounding (~1e-12 MW at these
# magnitudes); 1e-6 MW (1 W) leaves six orders of margin. _negative_controls() measures how far
# realistic modelling errors (taps ignored, one reactance off by 1 %) move the flows, to show that
# the tolerance would catch them.
TOL_DC_FLOW_MW = 1e-6
TOL_DC_ANGLE_DEG = 1e-6
TOL_X_REL = 1e-9
# OPF: pandapower's PIPS is an interior-point method (default tolerances ~1e-6 relative), HiGHS
# simplex is exact up to ~1e-9; objectives must agree to 1e-6 relative, dispatch to 0.01 MW.
TOL_OPF_OBJ_REL = 1e-6
TOL_OPF_GEN_MW = 1e-2
SIG = 6  # contracts.md §5 asks for rounding only where size requires; 6 keeps objectives readable


def _sig(x: float, digits: int = SIG) -> float:
    if x == 0 or not math.isfinite(x):
        return x
    return round(x, digits - 1 - int(math.floor(math.log10(abs(x)))))


def _round(obj):
    if isinstance(obj, float):
        return _sig(obj)
    if isinstance(obj, dict):
        return {k: _round(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round(v) for v in obj]
    return obj


def canonical_sha256(obj) -> str:
    data = json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _vec(a: dict, b: dict, keys: list[str]) -> tuple[np.ndarray, np.ndarray]:
    x, y = np.array([a[k] for k in keys], float), np.array([b[k] for k in keys], float)
    if not len(keys) or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("comparison needs non-empty finite numerical vectors")
    return x, y


def _diff_metrics(a: dict, b: dict, keys: list[str], *, rel_floor_mw: float = 1.0) -> dict:
    x, y = _vec(a, b, keys)
    e = np.abs(x - y)
    big = np.abs(y) >= rel_floor_mw
    return {
        "max_abs_diff_mw": float(e.max()),
        "mean_abs_diff_mw": float(e.mean()),
        "p95_abs_diff_mw": float(np.percentile(e, 95)),
        "max_rel_diff": float((e[big] / np.abs(y[big])).max()) if big.any() else None,
        "rel_diff_floor_mw": rel_floor_mw,
        "argmax": keys[int(e.argmax())],
    }


def _worst(a: dict, b: dict, keys: list[str], names: tuple[str, str], n: int = 5) -> list[dict]:
    x, y = _vec(a, b, keys)
    order = np.argsort(-np.abs(x - y))[:n]
    return [
        {"id": keys[i], names[0]: float(x[i]), names[1]: float(y[i]), "diff_mw": float(x[i] - y[i])}
        for i in order
    ]


def _check(
    check_id, case, title, engines, quantity, n, metrics, tol, verdict, explanation, **extra
):
    return {
        "check_id": check_id,
        "case": case,
        "title": title,
        "engines": list(engines),
        "quantity": quantity,
        "n_compared": int(n),
        "metrics": metrics,
        "tolerance": tol,
        "verdict": verdict,
        "explanation": explanation,
        **extra,
    }


def _dcpf_check(check_id, case, a, b, names, bus_ids, branch_ids):
    m = _diff_metrics(a["branch_flow_mw"], b["branch_flow_mw"], branch_ids)
    ang = _vec(a["bus_angle_deg"], b["bus_angle_deg"], bus_ids)
    inj = _vec(a["bus_injection_mw"], b["bus_injection_mw"], bus_ids)
    m["max_angle_diff_deg"] = float(np.abs(ang[0] - ang[1]).max())
    m["max_injection_diff_mw"] = float(np.abs(inj[0] - inj[1]).max())
    ok = (
        m["max_abs_diff_mw"] <= TOL_DC_FLOW_MW
        and m["max_angle_diff_deg"] <= TOL_DC_ANGLE_DEG
        and m["max_injection_diff_mw"] <= TOL_DC_FLOW_MW
    )
    expl = (
        f"All {len(branch_ids)} branch flows, {len(bus_ids)} bus angles and injections match to "
        f"floating-point rounding."
        if ok
        else f"Largest flow difference on {m['argmax']}; see worst_branches and the "
        "parameter audit."
    )
    return _check(
        check_id,
        case,
        f"DC power flow: {names[0]} vs {names[1]}",
        names,
        "branch_flow_mw",
        len(branch_ids),
        m,
        {
            "metric": "max_abs_diff_mw",
            "value": TOL_DC_FLOW_MW,
            "unit": "MW",
            "also": {
                "max_angle_diff_deg": TOL_DC_ANGLE_DEG,
                "max_injection_diff_mw": TOL_DC_FLOW_MW,
            },
        },
        "AGREES" if ok else "DISAGREES",
        expl,
        worst_branches=_worst(a["branch_flow_mw"], b["branch_flow_mw"], branch_ids, names),
    )


def _negative_controls(case: dict, dispatch: dict, ref_dc: dict) -> dict:
    """How far realistic modelling errors move the reference DC solution (detectability of errors).

    For each in-service branch, its reactance is raised by 1 % and the DC PF re-solved. On a bridge
    branch (radial feeder) the flow is fixed by KCL alone, so an x error there changes only the
    angles beyond it; such errors are caught by the angle tolerance, not the flow tolerance.
    """
    flows, angles = ref_dc["branch_flow_mw"], ref_dc["bus_angle_deg"]

    def change(mod: dict) -> tuple[float, float]:
        r = mpc.reference_dcpf(mod, dispatch)
        return (
            float(max(abs(r["branch_flow_mw"][k] - flows[k]) for k in flows)),
            float(max(abs(r["bus_angle_deg"][k] - angles[k]) for k in angles)),
        )

    no_tap = {**case, "branch": case["branch"].copy()}
    no_tap["branch"][:, mpc.TAP] = 0.0
    per_branch = []
    for row in np.flatnonzero(case["branch"][:, mpc.BR_STATUS] > 0):
        mod = {**case, "branch": case["branch"].copy()}
        mod["branch"][row, mpc.BR_X] *= 1.01
        per_branch.append((*change(mod), mpc.branch_id(int(row))))
    by_flow = [p for p in per_branch if p[0] > TOL_DC_FLOW_MW]
    by_any = [p for p in per_branch if p[0] > TOL_DC_FLOW_MW or p[1] > TOL_DC_ANGLE_DEG]
    tap_flow, tap_angle = change(no_tap)
    return {
        "taps_ignored_max_flow_change_mw": tap_flow,
        "taps_ignored_max_angle_change_deg": tap_angle,
        "x_plus_1pct_n_branches": len(per_branch),
        "x_plus_1pct_n_detected_by_flow_tolerance": len(by_flow),
        "x_plus_1pct_n_detected_by_flow_or_angle_tolerance": len(by_any),
        "x_plus_1pct_flow_invariant_branches": sorted(
            (p[2] for p in per_branch if p[0] <= TOL_DC_FLOW_MW), key=lambda k: int(k.split("-")[1])
        ),
        "x_plus_1pct_min_flow_change_mw_detected": min((p[0] for p in by_flow), default=None),
        "x_plus_1pct_median_flow_change_mw": float(np.median([p[0] for p in per_branch])),
        "tolerance_flow_mw": TOL_DC_FLOW_MW,
        "tolerance_angle_deg": TOL_DC_ANGLE_DEG,
    }


def _param_check(case_id, case, pypsa) -> dict:
    """PyPSA's effective DC reactance (x_pu_eff on baseMVA) vs MATPOWER makeBdc's x * tap."""
    br = case["branch"]
    audit = pypsa["dc"]["param_audit"]
    rel, rel_no_tap = [], []
    for row in range(len(br)):
        bid = mpc.branch_id(row)
        if bid not in audit:
            continue
        tap = br[row, mpc.TAP] or 1.0
        xe = audit[bid]["x_eff_pu"]
        rel.append(abs(xe / (br[row, mpc.BR_X] * tap) - 1))
        rel_no_tap.append(abs(xe / br[row, mpc.BR_X] - 1))
    n_trafo = sum(1 for v in audit.values() if v["component"] == "Transformer")
    m = {
        "max_rel_diff_x_eff_vs_x_times_tap": float(max(rel)),
        "max_rel_diff_x_eff_vs_x_without_tap": float(max(rel_no_tap)),
        "n_transformers_in_pypsa": n_trafo,
        "n_lines_in_pypsa": len(audit) - n_trafo,
    }
    ok = m["max_rel_diff_x_eff_vs_x_times_tap"] <= TOL_X_REL
    return _check(
        "dc_reactance_pypsa_vs_matpower",
        case_id,
        "DC series reactance used by PyPSA vs MATPOWER makeBdc (x * tap)",
        ("pypsa", "matpower-formula-numpy"),
        "x_eff_pu",
        len(rel),
        m,
        {"metric": "max_rel_diff_x_eff_vs_x_times_tap", "value": TOL_X_REL, "unit": "1"},
        "AGREES" if ok else "DISAGREES",
        "PyPSA's linear power flow scales transformer reactance by tap_ratio exactly like "
        "MATPOWER's makeBdc (b = 1 / (x * tap)); ignoring the tap would have changed reactances "
        f"by up to {m['max_rel_diff_x_eff_vs_x_without_tap'] * 100:.1f} %."
        if ok
        else "Effective reactances differ: the importer's unit conversion or tap handling is "
        "inconsistent.",
    )


def _ac_check(case_id, case, pp, pypsa, branch_ids) -> dict:
    ac = pp["ac"]
    if not ac.get("converged"):
        return _check(
            "ac_pp_vs_dc_pypsa",
            case_id,
            "AC (pandapower runpp) vs DC (PyPSA lpf)",
            ("pandapower-ac", "pypsa-dc"),
            "branch_flow_mw",
            0,
            {},
            None,
            "NOT_RUN",
            "pandapower Newton-Raphson did not converge on the fixed dispatch.",
        )
    m = _diff_metrics(ac["branch_flow_mw"], pypsa["dc"]["branch_flow_mw"], branch_ids)
    # Remove half of this branch's own losses, not the system-wide slack loss redistribution.
    mid = {k: 0.5 * (ac["branch_flow_mw"][k] - ac["branch_flow_to_mw"][k]) for k in branch_ids}
    mm = _diff_metrics(mid, pypsa["dc"]["branch_flow_mw"], branch_ids)
    rate = {mpc.branch_id(i): case["branch"][i, mpc.RATE_A] for i in range(len(case["branch"]))}
    rated = [k for k in branch_ids if rate[k] > 0]
    x, y = _vec(ac["branch_flow_mw"], pypsa["dc"]["branch_flow_mw"], rated)
    m.update(
        {
            "max_abs_diff_midpoint_mw": mm["max_abs_diff_mw"],
            "mean_abs_diff_midpoint_mw": mm["mean_abs_diff_mw"],
            "max_diff_pct_of_rate_a": float(
                (np.abs(x - y) / np.array([rate[k] for k in rated])).max() * 100
            ),
            "ac_total_losses_mw": ac["total_losses_mw"],
            "ac_slack_p_mw": ac["ext_grid_p_mw"],
            "dc_slack_p_mw": pp["dispatch"]["slack_gen_p_mw"],
            "ac_vm_pu_min": ac["vm_pu_min"],
            "ac_vm_pu_max": ac["vm_pu_max"],
            "max_gen_q_limit_violation_mvar": ac["max_gen_q_limit_violation_mvar"],
            "n_gen_q_limit_violations": ac["n_gen_q_limit_violations"],
            "max_vm_limit_violation_pu": ac["max_vm_limit_violation_pu"],
            "ac_slack_minus_dc_minus_losses_mw": (
                ac["ext_grid_p_mw"] - pp["dispatch"]["slack_gen_p_mw"] - ac["total_losses_mw"]
            ),
        }
    )
    worst = m["argmax"]
    row = int(worst.split("-")[1]) - 1
    ends = (mpc.bus_id(case["branch"][row, mpc.F_BUS]), mpc.bus_id(case["branch"][row, mpc.T_BUS]))
    slack = pp["dispatch"]["slack_bus"]
    return _check(
        "ac_pp_vs_dc_pypsa",
        case_id,
        "AC (pandapower runpp) vs DC (PyPSA lpf): linearisation error",
        ("pandapower-ac", "pypsa-dc"),
        "branch_flow_mw",
        len(branch_ids),
        m,
        None,
        "EXPECTED_DIFFERENCE",
        f"Same P set points. The DC model is lossless, with flat |V| and no reactive power; in "
        f"AC the slack generator at {slack} additionally supplies the "
        f"{ac['total_losses_mw']:.1f} MW of losses (AC slack {ac['ext_grid_p_mw']:.1f} MW vs DC "
        f"{pp['dispatch']['slack_gen_p_mw']:.1f} MW). Largest difference "
        f"{m['max_abs_diff_mw']:.1f} MW on {worst} ({ends[0]}-{ends[1]}"
        f"{', incident to the slack bus' if slack in ends else ''}); local-loss midpoint flow "
        f"max {mm['max_abs_diff_mw']:.1f} MW; mean {m['mean_abs_diff_mw']:.2f} MW over "
        f"{len(branch_ids)} branches. This is the linearisation error of the DC approximation, "
        f"not an engine disagreement.",
        worst_branches=_worst(
            ac["branch_flow_mw"],
            pypsa["dc"]["branch_flow_mw"],
            branch_ids,
            ("pandapower-ac", "pypsa-dc"),
        ),
    )


def _opf_check(check_id, case_id, a, b, names, obj_a, obj_b, note) -> dict:
    if set(a["gen_p_mw"]) != set(b["gen_p_mw"]):
        raise ValueError("OPF generator sets differ")
    gens = sorted(a["gen_p_mw"], key=lambda g: int(g.split("-")[1]))
    x, y = _vec(a["gen_p_mw"], b["gen_p_mw"], gens)
    m = {
        "objective_a": obj_a,
        "objective_b": obj_b,
        "objective_rel_diff": abs(obj_a - obj_b) / max(abs(obj_b), 1e-9),
        "max_gen_abs_diff_mw": float(np.abs(x - y).max()),
        "argmax_gen": gens[int(np.abs(x - y).argmax())],
    }
    if "branch_flow_mw" in a and "branch_flow_mw" in b:
        if set(a["branch_flow_mw"]) != set(b["branch_flow_mw"]):
            raise ValueError("OPF branch sets differ")
        keys = sorted(a["branch_flow_mw"], key=lambda k: int(k.split("-")[1]))
        m["max_branch_flow_abs_diff_mw"] = _diff_metrics(
            a["branch_flow_mw"], b["branch_flow_mw"], keys
        )["max_abs_diff_mw"]
    obj_ok = m["objective_rel_diff"] <= TOL_OPF_OBJ_REL
    gen_ok = m["max_gen_abs_diff_mw"] <= TOL_OPF_GEN_MW
    if obj_ok and gen_ok:
        verdict, expl = (
            "AGREES",
            f"Same optimum: objective and every generator set point match. {note}",
        )
    elif obj_ok:
        verdict, expl = (
            "DISAGREES",
            (
                f"Objectives agree but dispatch differs by up to "
                f"{m['max_gen_abs_diff_mw']:.3g} MW on {m['argmax_gen']}; this can indicate "
                f"LP degeneracy, but dispatch agreement is not established. {note}"
            ),
        )
    else:
        verdict, expl = "DISAGREES", f"Objectives differ. {note}"
    return _check(
        check_id,
        case_id,
        f"DC OPF: {names[0]} vs {names[1]}",
        names,
        "objective_and_dispatch",
        len(gens),
        m,
        {
            "metric": "objective_rel_diff",
            "value": TOL_OPF_OBJ_REL,
            "unit": "1",
            "also": {"max_gen_abs_diff_mw": TOL_OPF_GEN_MW},
        },
        verdict,
        expl,
    )


def _cost_model(case: dict, pypsa: dict) -> dict:
    gc, gen = case["gencost"], case["gen"]
    max_diff, n_quad, c0_total = 0.0, 0, 0.0
    if np.any(gc[: len(gen), 0] != 2) or np.any(gc[: len(gen), 3] > 3):
        raise ValueError("cost-model check supports polynomial gencost of order <= 2 only")
    for i in range(len(gen)):
        ncoef = int(gc[i, 3])
        c2, c1, c0 = ([0.0] * (3 - ncoef) + list(gc[i, 4 : 4 + ncoef]))[-3:]
        mc = pypsa["model"]["generator_cost"][mpc.gen_id(i)]["marginal_cost"]
        expected = c1 + c2 * gen[i, mpc.PMAX]
        max_diff = max(max_diff, abs(mc - expected))
        n_quad += c2 != 0
        c0_total += c0
    return {
        "gencost_model": int(gc[0, 0]),
        "n_generators": len(gen),
        "n_quadratic_c2_nonzero": int(n_quad),
        "sum_c0_per_h": float(c0_total),
        "max_abs_diff_pypsa_marginal_cost_vs_c1_plus_c2_pmax": float(max_diff),
    }


def compare(network_id: str) -> tuple[dict, dict, str]:
    w = mpc.WORK
    pp = mpc.read_json(w / f"{network_id}.pandapower.json")
    py = mpc.read_json(w / f"{network_id}.pypsa.json")
    ref = mpc.read_json(w / f"{network_id}.reference.json")
    src = mpc.source_path(network_id)
    case = mpc.load_case(src)
    if (
        pp["source"]["sha256"] != mpc.sha256_file(src)
        or py["source"]["sha256"] != pp["source"]["sha256"]
    ):
        raise RuntimeError(f"{network_id}: engines were run on different source files")
    for side in (pp, py):
        if side["dispatch"] != ref["dispatch"]:
            raise RuntimeError(f"{network_id}: dispatch mismatch between harness outputs")
        if side["dispatch"] != mpc.fixed_dispatch(case):
            raise RuntimeError(f"{network_id}: stale balanced dispatch")
        if side["raw_dispatch"] != ref["raw_dispatch"]:
            raise RuntimeError(f"{network_id}: original PG dispatch mismatch")
        if side["raw_dispatch"] != mpc.fixed_dispatch(case, balance=False):
            raise RuntimeError(f"{network_id}: stale original PG dispatch")
    nc = mpc.NETWORKS / network_id / "network.nc"
    if py["network_nc"]["sha256"] != mpc.sha256_file(nc):
        raise RuntimeError(f"{network_id}: network.nc changed since the PyPSA run")
    branch_ids = [b["id"] for b in ref["branch_meta"] if b["status"] > 0]
    bus_ids = list(ref["dc"]["bus_angle_deg"])
    checks = []
    for cid, a_name, b_name, a, b in (
        ("dcpf_pp_vs_pypsa", "pandapower", "pypsa", pp["dc"], py["dc"]),
        ("dcpf_pp_vs_reference", "pandapower", "matpower-formula-numpy", pp["dc"], ref["dc"]),
        ("dcpf_pypsa_vs_reference", "pypsa", "matpower-formula-numpy", py["dc"], ref["dc"]),
    ):
        checks.append(_dcpf_check(cid, network_id, a, b, (a_name, b_name), bus_ids, branch_ids))
    for cid, a_name, b_name, a, b in (
        ("raw_pg_dcpf_pp_vs_pypsa", "pandapower", "pypsa", pp["raw_dc"], py["raw_dc"]),
        (
            "raw_pg_dcpf_pp_vs_reference",
            "pandapower",
            "matpower-formula-numpy",
            pp["raw_dc"],
            ref["raw_dc"],
        ),
        (
            "raw_pg_dcpf_pypsa_vs_reference",
            "pypsa",
            "matpower-formula-numpy",
            py["raw_dc"],
            ref["raw_dc"],
        ),
    ):
        c = _dcpf_check(cid, network_id, a, b, (a_name, b_name), bus_ids, branch_ids)
        c["title"] += " (unmodified PGLib PG, reference slack balances)"
        checks.append(c)
    checks.append(_param_check(network_id, case, py))
    checks.append(_ac_check(network_id, case, pp, py, branch_ids))

    cost = _cost_model(case, py)
    cost_ok = cost["max_abs_diff_pypsa_marginal_cost_vs_c1_plus_c2_pmax"] <= 1e-9
    checks.append(
        _check(
            "cost_model_pypsa_vs_pglib",
            network_id,
            "PyPSA marginal_cost vs PGLib gencost (c1 + c2*Pmax)",
            ("pypsa", "pglib-gencost"),
            "marginal_cost",
            cost["n_generators"],
            {k: v for k, v in cost.items() if k != "gencost_model"},
            {
                "metric": "max_abs_diff_pypsa_marginal_cost_vs_c1_plus_c2_pmax",
                "value": 1e-9,
                "unit": "$/MWh",
            },
            "AGREES" if cost_ok else "DISAGREES",
            "The importer's documented linearisation (secant slope c1 + c2*Pmax, c0 dropped) "
            "is what network.nc carries."
            + (
                " With c2 = 0 for every generator it equals the PGLib cost exactly "
                "(up to the dropped constant c0)."
                if cost["n_quadratic_c2_nonzero"] == 0
                else " Generators with c2 != 0 are over-costed at partial load, so "
                "LOPF results are NOT comparable to a quadratic-cost OPF."
            ),
        )
    )
    rdc, pdc, ydc = ref["dcopf"], pp["dcopf"], py["dcopf"]
    angmax = float(np.max(np.abs(case["branch"][:, mpc.ANGMAX])))
    exact = (
        "so the importer's linear marginal cost c1 + c2*Pmax is exact here"
        if cost["n_quadratic_c2_nonzero"] == 0
        else "so the importer's linear cost is an approximation"
    )
    note = (
        f"PGLib gencost: {cost['n_quadratic_c2_nonzero']} of {cost['n_generators']} generators "
        f"have a non-zero quadratic term and sum(c0) = {cost['sum_c0_per_h']:.4g} $/h, {exact}. "
        f"Angle-difference limits (PGLib +/-{angmax:g} deg) are not modelled by any engine; the "
        f"reference optimum's largest angle difference is "
        f"{rdc.get('max_abs_angle_diff_deg', float('nan')):.2f} deg."
    )
    if pdc.get("converged") and ydc.get("status") == "ok":
        # pandapower's res_cost includes c0 (poly_cost cp0_eur); PyPSA's objective does not (the
        # importer drops c0), so PyPSA is compared with c0 added back.
        checks.append(
            _opf_check(
                "dcopf_pp_vs_pypsa",
                network_id,
                pdc,
                ydc,
                ("pandapower", "pypsa"),
                pdc["objective"],
                ydc["objective"] + cost["sum_c0_per_h"],
                note,
            )
        )
    else:
        checks.append(
            _check(
                "dcopf_pp_vs_pypsa",
                network_id,
                "DC OPF: pandapower vs pypsa",
                ("pandapower", "pypsa"),
                "objective_and_dispatch",
                0,
                {},
                None,
                "NOT_RUN",
                f"pandapower: {pdc.get('error', pdc.get('converged'))}; pypsa: {ydc.get('status')}",
            )
        )
    if rdc.get("status") == "optimal" and ydc.get("status") == "ok":
        checks.append(
            _opf_check(
                "dcopf_pypsa_vs_reference",
                network_id,
                ydc,
                rdc,
                ("pypsa", "scipy-highs-reference"),
                ydc["objective"] + cost["sum_c0_per_h"],
                rdc["objective"],
                note,
            )
        )
    else:
        checks.append(
            _check(
                "dcopf_pypsa_vs_reference",
                network_id,
                "DC OPF: pypsa vs scipy reference",
                ("pypsa", "scipy-highs-reference"),
                "objective_and_dispatch",
                0,
                {},
                None,
                "NOT_RUN",
                f"reference: {rdc.get('status')} {rdc.get('reason', '')}",
            )
        )

    engines = [
        {
            "name": "pandapower",
            "version": pp["engine"]["version"],
            "role": "rundcpp / runpp / rundcopp on from_mpc conversion",
        },
        {
            "name": "pypsa",
            "version": py["engine"]["version"],
            "role": f"lpf / optimize ({ydc.get('solver', 'HiGHS')}) on "
            f"{py['network_nc']['origin']}",
        },
        {
            "name": "matpower-formula-numpy",
            "version": ref["engine"]["version"],
            "role": "independent makeBdc/dcpf arbiter; DC OPF LP via scipy.optimize.linprog(highs)",
        },
    ]
    payload = _round(
        {
            "network_id": network_id,
            "engines": engines,
            "dispatch": {k: v for k, v in pp["dispatch"].items() if not isinstance(v, dict)},
            "raw_dispatch": {
                k: v for k, v in pp["raw_dispatch"].items() if not isinstance(v, dict)
            },
            "case_features": ref["case_features"],
            "conversion": {
                "pandapower": {
                    k: v for k, v in pp["conversion"].items() if k != "parser_crosscheck"
                },
                "pandapower_parser_crosscheck": pp["conversion"]["parser_crosscheck"],
                "pypsa": py["model"]["counts"],
                "pypsa_mapping_issues": py["mapping_issues"],
            },
            "cost_model": cost,
            "negative_controls": _negative_controls(case, ref["dispatch"], ref["dc"]),
            "checks": checks,
            "summary": {
                v: sum(c["verdict"] == v for c in checks)
                for v in ("AGREES", "DISAGREES", "EXPECTED_DIFFERENCE", "NOT_RUN")
            },
        }
    )
    header = {
        "schema_version": "gridstorm-artifact/1.0",
        "artifact_id": f"cross-engine-{network_id}",
        "kind": "benchmark",
        "engine": ENGINE,
        "engine_version": f"pandapower {pp['engine']['version']} | pypsa {py['engine']['version']}",
        "network_id": network_id,
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "command": COMMAND,
        "inputs": [
            {"path": pp["source"]["path"], "sha256": pp["source"]["sha256"]},
            {"path": py["network_nc"]["path"], "sha256": py["network_nc"]["sha256"]},
            *[
                {"path": mpc.display_path(p), "sha256": mpc.sha256_file(p)}
                for p in (
                    *sorted(Path(__file__).parent.glob("*.py")),
                    mpc.REPO / "workers/pandapower/uv.lock",
                    mpc.REPO / "pipelines/network-import/uv.lock",
                )
            ],
        ],
        "platform": f"{platform.platform()}; python {platform.python_version()}",
        "execution_mode": "precomputed",
        "payload_sha256": canonical_sha256(payload),
    }
    title = f"Cross-engine agreement (pandapower vs PyPSA vs MATPOWER formulas) — {network_id}"
    return (
        {"artifact": header, "payload": payload},
        {
            "artifact_id": header["artifact_id"],
            "kind": "benchmark",
            "network_id": network_id,
            "title": title,
        },
        _table(payload),
    )


def _fmt(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.3g}" if (abs(v) < 1e-3 or abs(v) >= 1e5) and v != 0 else f"{v:.4g}"
    return str(v)


def _table(p: dict) -> str:
    lines = [
        f"#### {p['network_id']}",
        "",
        "| check | metric | value | tolerance | verdict |",
        "|---|---|---|---|---|",
    ]
    for c in p["checks"]:
        tol = c["tolerance"]
        key = tol["metric"] if tol else next(iter(c["metrics"]), None)
        val = c["metrics"].get(key) if key else None
        lines.append(
            f"| `{c['check_id']}` | {key or '—'} | {_fmt(val)} | "
            f"{_fmt(tol['value']) + ' ' + tol['unit'] if tol else '—'} | **{c['verdict']}** |"
        )
    return "\n".join(lines) + "\n"


def main(ids: list[str]) -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    index_path = ARTIFACT_DIR / "index.json"
    entries = json.loads(index_path.read_text("utf-8"))["artifacts"] if index_path.exists() else []
    tables = []
    failed = False
    for nid in ids:
        art, entry, table = compare(nid)
        path = ARTIFACT_DIR / f"{entry['artifact_id']}.json"
        path.write_text(
            json.dumps(art, indent=1, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8"
        )
        entries = [e for e in entries if e["artifact_id"] != entry["artifact_id"]]
        entries.append(
            {**entry, "path": path.name, "payload_sha256": art["artifact"]["payload_sha256"]}
        )
        tables.append(table)
        s = art["payload"]["summary"]
        failed |= bool(s["DISAGREES"] or s["NOT_RUN"])
        print(
            f"{nid}: "
            + ", ".join(f"{k}={v}" for k, v in s.items())
            + f" -> {mpc.display_path(path)}"
        )
        for c in art["payload"]["checks"]:
            print(f"  {c['check_id']:<32} {c['verdict']:<20} {json.dumps(c['metrics'])[:160]}")
    entries.sort(key=lambda e: e["artifact_id"])
    index_path.write_text(
        json.dumps(
            {
                "schema_version": "gridstorm-artifact-index/1.0",
                "engine": ENGINE,
                "artifacts": entries,
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    (mpc.WORK / "tables.md").write_text("\n".join(tables), encoding="utf-8")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or list(mpc.CASES)))
