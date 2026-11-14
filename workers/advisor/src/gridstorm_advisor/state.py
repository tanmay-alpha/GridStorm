"""AC power-flow solve and violation detection for one network state."""

from __future__ import annotations

import math
import warnings

import pandapower as pp
import pandapower.topology as top

from gridstorm_advisor.network import AdvisorNetwork

# Deterministic solver settings used for EVERY AC evaluation (crisis state, candidates, N-1).
PF_OPTIONS = {
    "algorithm": "nr",
    "enforce_q_lims": True,
    "max_iteration": 30,
    "tolerance_mva": 1e-8,
    "calculate_voltage_angles": True,
}
THERMAL_LIMIT_PCT = 100.0
THERMAL_TOL_PCT = 0.01  # OPF solutions sit on the limit to solver tolerance (100.00001 %)
VOLTAGE_TOL_PU = 1e-4  # avoids flagging setpoints that sit exactly on VMIN/VMAX
SLACK_P_TOL_MW = 1e-3


def solve_ac(net: pp.pandapowerNet) -> bool:
    """Newton-Raphson AC power flow, DC-initialised; one deterministic retry from a flat start."""
    for init in ("dc", "flat"):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                pp.runpp(net, init=init, **PF_OPTIONS)
            if net.converged:
                return True
        except Exception:  # noqa: BLE001 - any solver failure = not converged (reported, not hidden)
            continue
    return False


def _r(x: float, nd: int = 4) -> float:
    return float(round(float(x), nd))


def islanded(net: pp.pandapowerNet) -> tuple[list[int], float]:
    """In-service buses with no path to a slack, and the in-service load (MW) on them."""
    unsup = sorted(int(b) for b in top.unsupplied_buses(net, respect_switches=True))
    ld = net.load
    mask = ld.in_service & ld.bus.isin(unsup)
    return unsup, float((ld.p_mw * ld.scaling)[mask].sum())


def _slack_rows(net: pp.pandapowerNet) -> list[tuple[str, int, float, float, float]]:
    """(table, index, p_mw, min_p_mw, max_p_mw) for every in-service slack element."""
    rows = []
    for idx in net.ext_grid.index[net.ext_grid.in_service]:
        rows.append(
            (
                "ext_grid",
                int(idx),
                float(net.res_ext_grid.at[idx, "p_mw"]),
                float(net.ext_grid.at[idx, "min_p_mw"])
                if "min_p_mw" in net.ext_grid
                else -math.inf,
                float(net.ext_grid.at[idx, "max_p_mw"]) if "max_p_mw" in net.ext_grid else math.inf,
            )
        )
    for idx in net.gen.index[net.gen.in_service & net.gen.slack]:
        rows.append(
            (
                "gen",
                int(idx),
                float(net.res_gen.at[idx, "p_mw"]),
                float(net.gen.at[idx, "min_p_mw"]),
                float(net.gen.at[idx, "max_p_mw"]),
            )
        )
    return rows


def branch_loading(adv: AdvisorNetwork, net: pp.pandapowerNet) -> dict[str, float]:
    """Loading (%) of every in-service, energised, rated branch keyed by asset id."""
    out: dict[str, float] = {}
    for bid, ref in adv.branches.items():
        if not bool(net[ref.table].at[ref.index, "in_service"]):
            continue
        res = net[f"res_{ref.table}"]
        if adv.loading_basis == "pandapower_loading_percent":
            val = float(res.at[ref.index, "loading_percent"])
        else:
            rating = adv.branch_rating_mva.get(bid)
            if rating is None:
                continue
            if ref.table != "trafo":
                cols = ("p_from_mw", "q_from_mvar", "p_to_mw", "q_to_mvar")
            else:
                cols = ("p_hv_mw", "q_hv_mvar", "p_lv_mw", "q_lv_mvar")
            pf, qf, pt, qt = (float(res.at[ref.index, c]) for c in cols)
            val = 100.0 * max(math.hypot(pf, qf), math.hypot(pt, qt)) / rating
        if not math.isnan(val):
            out[bid] = val
    return out


def gen_dispatch(adv: AdvisorNetwork, net: pp.pandapowerNet) -> dict[str, float]:
    """Solved active power of every in-service generator keyed by asset id."""
    out: dict[str, float] = {}
    for gid, ref in adv.generators.items():
        if not bool(net[ref.table].at[ref.index, "in_service"]):
            continue
        val = float(net[f"res_{ref.table}"].at[ref.index, "p_mw"])
        if not math.isnan(val):
            out[gid] = val
    return out


def generation_cost(adv: AdvisorNetwork, dispatch: dict[str, float]) -> float | None:
    if not adv.gen_cost:
        return None
    return float(sum(adv.gen_cost[g](p) for g, p in dispatch.items() if g in adv.gen_cost))


def evaluate_state(adv: AdvisorNetwork, net: pp.pandapowerNet) -> dict:
    """Solve the AC power flow on ``net`` (mutated: results written) and summarise it.

    Violations: thermal (> 100 % of rating), voltage outside the bus VMIN/VMAX band, slack
    active power outside [Pmin, Pmax], or non-convergence. Islanded load is reported separately.
    """
    unsup, islanded_mw = islanded(net)
    ld = net.load
    supplied_load = float((ld.p_mw * ld.scaling)[ld.in_service & ~ld.bus.isin(unsup)].sum())
    base = {
        "islanded_buses": [adv.bus_id_of(b) for b in unsup],
        "islanded_load_mw": _r(islanded_mw),
        "supplied_load_mw": _r(supplied_load),
    }
    if not solve_ac(net):
        return {
            **base,
            "converged": False,
            "violations": [
                {
                    "kind": "non_convergence",
                    "asset_id": None,
                    "value": None,
                    "limit": None,
                    "unit": None,
                }
            ],
            "max_branch_loading_pct": None,
            "max_branch_id": None,
            "min_vm_pu": None,
            "max_vm_pu": None,
            "slack_p_mw": None,
            "losses_mw": None,
            "generation_cost_eur_per_h": None,
            "branch_loading_pct": {},
            "bus_vm_pu": {},
            "gen_p_mw": {},
        }

    loading = branch_loading(adv, net)
    violations: list[dict] = []
    if islanded_mw > 1e-6:
        violations.append(
            {
                "kind": "islanded_load",
                "asset_id": None,
                "value": _r(islanded_mw),
                "limit": 0.0,
                "unit": "mw",
            }
        )
    for bid, val in loading.items():
        if val > THERMAL_LIMIT_PCT + THERMAL_TOL_PCT:
            violations.append(
                {
                    "kind": "thermal",
                    "asset_id": bid,
                    "value": _r(val, 3),
                    "limit": THERMAL_LIMIT_PCT,
                    "unit": "pct",
                }
            )
    vm = net.res_bus.vm_pu
    bus_vm: dict[str, float] = {}
    for bid, b in adv.buses.items():
        v = float(vm.at[b])
        if math.isnan(v) or not bool(net.bus.at[b, "in_service"]):
            continue
        bus_vm[bid] = v
        vmin = float(net.bus.at[b, "min_vm_pu"]) if "min_vm_pu" in net.bus else 0.95
        vmax = float(net.bus.at[b, "max_vm_pu"]) if "max_vm_pu" in net.bus else 1.05
        if v < vmin - VOLTAGE_TOL_PU:
            violations.append(
                {
                    "kind": "voltage_low",
                    "asset_id": bid,
                    "value": _r(v, 5),
                    "limit": vmin,
                    "unit": "pu",
                }
            )
        elif v > vmax + VOLTAGE_TOL_PU:
            violations.append(
                {
                    "kind": "voltage_high",
                    "asset_id": bid,
                    "value": _r(v, 5),
                    "limit": vmax,
                    "unit": "pu",
                }
            )
    slack_total = 0.0
    for table, idx, p, pmin, pmax in _slack_rows(net):
        slack_total += p
        gid = adv.gen_id_of(table, idx)
        if p > pmax + SLACK_P_TOL_MW:
            violations.append(
                {
                    "kind": "slack_p_max",
                    "asset_id": gid,
                    "value": _r(p, 3),
                    "limit": pmax,
                    "unit": "mw",
                }
            )
        elif p < pmin - SLACK_P_TOL_MW:
            violations.append(
                {
                    "kind": "slack_p_min",
                    "asset_id": gid,
                    "value": _r(p, 3),
                    "limit": pmin,
                    "unit": "mw",
                }
            )
    violations.sort(key=lambda v: (v["kind"], str(v["asset_id"])))

    dispatch = gen_dispatch(adv, net)
    cost = generation_cost(adv, dispatch)
    max_bid = max(loading, key=lambda k: (loading[k], k)) if loading else None
    losses = float(net.res_line.pl_mw.fillna(0.0).sum())
    if len(net.trafo):
        losses += float(net.res_trafo.pl_mw.fillna(0.0).sum())
    return {
        **base,
        "converged": True,
        "violations": violations,
        "max_branch_loading_pct": _r(loading[max_bid], 3) if max_bid else None,
        "max_branch_id": max_bid,
        "min_vm_pu": _r(min(bus_vm.values()), 5) if bus_vm else None,
        "max_vm_pu": _r(max(bus_vm.values()), 5) if bus_vm else None,
        "slack_p_mw": _r(slack_total, 3),
        "losses_mw": _r(losses, 3),
        "generation_cost_eur_per_h": _r(cost, 2) if cost is not None else None,
        "branch_loading_pct": {k: _r(v, 3) for k, v in sorted(loading.items())},
        "bus_vm_pu": {k: _r(v, 5) for k, v in sorted(bus_vm.items())},
        "gen_p_mw": {k: _r(v, 3) for k, v in sorted(dispatch.items())},
    }


def violation_keys(state: dict) -> set[tuple[str, str | None]]:
    return {(v["kind"], v["asset_id"]) for v in state["violations"]}


def overloaded_branches(state: dict) -> list[str]:
    return [v["asset_id"] for v in state["violations"] if v["kind"] == "thermal"]
