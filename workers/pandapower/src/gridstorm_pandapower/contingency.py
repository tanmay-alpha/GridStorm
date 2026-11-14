"""N-1 / selected N-2 branch contingency screening with steady-state AC power flow.

For every in-service line and transformer the outage is applied to a deep copy of the solved base
net and Newton-Raphson is re-run with the fixed :data:`~gridstorm_pandapower.powerflow.PF_OPTIONS`,
initialised from the base-case solution (``init="results"``).

Classification flags (all that apply are listed in ``classes``):

* ``islanding`` — at least one bus energised in the base case is no longer connected to a slack
  (``pandapower.topology.unsupplied_buses``); ``islanded_load_mw`` = base-case load at those buses,
  ``islanded_generation_mw`` = generator set points stranded there. If the outage cuts every slack
  off from the island with the largest load, :func:`reassign_isolated_slack` first moves the
  reference there (reported in ``slack_reassignment``) and the old slack's island is de-energised.
* ``thermal_overload`` — a branch with ``RATE_A > 0`` has ``loading_pct > 100 + LOADING_TOL_PCT``.
* ``voltage_violation`` — an energised bus has ``vm_pu`` outside
  ``[vmin − VM_TOL_PU, vmax + VM_TOL_PU]``.
* ``non_convergent`` — Newton-Raphson did not converge within ``max_iteration``.
* ``error`` — any other exception.
* ``secure`` — none of the above.

Primary ``class`` precedence: error > non_convergent > islanding > thermal_overload >
voltage_violation > secure.

Severity (dimensionless; ``None`` for non_convergent/error, which rank first):

    S = Σ_b (L_b/100 − 1)²                       over overloaded branches (L = loading %)
      + Σ_i (d_i / 0.05)²                        d_i = pu distance outside the voltage band
      + 100 · (P_islanded + P_slack,excess) / P_load,total

``P_slack,excess`` = Σ max(0, P − Pmax) over the in-service slack(s): with no re-dispatch the single
slack absorbs all lost generation, and output beyond its ``Pmax`` is a supply shortfall counted
like disconnected load (reported as ``slack_excess_mw``; it is not a separate class).
A 120 % overload contributes 0.04, a 0.05 pu voltage excursion 1.0, losing 1 % of system load 1.0.
"""

from __future__ import annotations

import itertools
import time
from collections import Counter

import networkx as nx
import numpy as np
from pandapower.topology import create_nxgraph, unsupplied_buses

from .model import BranchRef, GridModel
from .powerflow import PF_OPTIONS, branch_flows, power_balance, run_pf

CLASSES = (
    "secure",
    "thermal_overload",
    "voltage_violation",
    "islanding",
    "non_convergent",
    "error",
)
_PRECEDENCE = ("error", "non_convergent", "islanding", "thermal_overload", "voltage_violation")
LOADING_TOL_PCT = 0.01
VM_TOL_PU = 1e-4
VOLTAGE_NORM_PU = 0.05
ISLAND_WEIGHT = 100.0


def _r(x: float | None, nd: int = 4) -> float | None:
    return None if x is None else round(float(x), nd)


def evaluate_state(
    model: GridModel, net, *, total_load_mw: float, base_energised: set[int]
) -> dict:
    """Violation analysis of a solved (converged) net."""
    flows = branch_flows(model, net)
    overloads = []
    max_row = None
    loadings = []
    for f in flows:
        lp = f["loading_pct"]
        if lp is None:
            continue
        loadings.append(lp)
        if max_row is None or lp > max_row["loading_pct"]:
            max_row = f
        if lp > 100.0 + LOADING_TOL_PCT:
            overloads.append(f)
    unsupplied = {int(b) for b in unsupplied_buses(net)} & base_energised
    vm = net.res_bus.vm_pu
    vviol = []
    vms = []
    for i in net.bus.index:
        if i in unsupplied or not net.bus.at[i, "in_service"]:
            continue
        v = float(vm.at[i])
        if not np.isfinite(v):
            continue
        vms.append(v)
        lo, hi = model.vm_limits[model.bus_id(i)]
        if v < lo - VM_TOL_PU or v > hi + VM_TOL_PU:
            vviol.append(
                {
                    "bus_id": model.bus_id(i),
                    "vm_pu": _r(v),
                    "vm_min_pu": lo,
                    "vm_max_pu": hi,
                    "deviation_pu": max(lo - v, v - hi),
                }
            )
    islanded_load, islanded_gen = _islanded_power(net, unsupplied)
    slack_excess = slack_excess_mw(net)
    flags = []
    if unsupplied:
        flags.append("islanding")
    if overloads:
        flags.append("thermal_overload")
    if vviol:
        flags.append("voltage_violation")
    severity = (
        sum((f["loading_pct"] / 100.0 - 1.0) ** 2 for f in overloads)
        + sum((v["deviation_pu"] / VOLTAGE_NORM_PU) ** 2 for v in vviol)
        + (
            ISLAND_WEIGHT * (islanded_load + slack_excess) / total_load_mw
            if total_load_mw > 0
            else 0.0
        )
    )
    balance = power_balance(net)
    return {
        "flags": flags,
        "severity": severity,
        "max_loading_pct": max_row["loading_pct"] if max_row else None,
        "max_loading_element": (
            {"id": max_row["ref"].id, "component": max_row["ref"].component} if max_row else None
        ),
        "mean_loading_pct": float(np.mean(loadings)) if loadings else None,
        "overloads": sorted(
            (
                {
                    "id": f["ref"].id,
                    "component": f["ref"].component,
                    "loading_pct": _r(f["loading_pct"], 2),
                }
                for f in overloads
            ),
            key=lambda o: -o["loading_pct"],
        ),
        "min_vm_pu": min(vms) if vms else None,
        "max_vm_pu": max(vms) if vms else None,
        "voltage_violations": [
            {k: v for k, v in d.items() if k != "deviation_pu"}
            for d in sorted(vviol, key=lambda d: -d["deviation_pu"])
        ],
        "islanded_buses": sorted((model.bus_id(b) for b in unsupplied), key=_bus_sort),
        "islanded_load_mw": islanded_load,
        "islanded_generation_mw": islanded_gen,
        "slack_excess_mw": slack_excess,
        "losses_mw": balance["losses_mw"],
        "balance_residual_mw": balance["residual_mw"],
        "flows": flows,
    }


def slack_excess_mw(net) -> float:
    """Σ max(0, P − Pmax) over in-service slacks: generation the single slack cannot supply."""
    total = 0.0
    for table, mask in (
        ("ext_grid", net.ext_grid.in_service),
        ("gen", net.gen.in_service & net.gen.slack),
    ):
        df = net[table][mask]
        if df.empty or "max_p_mw" not in df:
            continue
        p = net[f"res_{table}"].p_mw.reindex(df.index).to_numpy(float)
        pmax = df.max_p_mw.to_numpy(float)
        ok = np.isfinite(p) & np.isfinite(pmax)
        total += float(np.clip(p[ok] - pmax[ok], 0.0, None).sum())
    return total


def _bus_sort(bus_id: str) -> int:
    return int(bus_id[4:])


def _islanded_power(net, unsupplied: set[int]) -> tuple[float, float]:
    """(load MW, generator set-point MW) at de-energised buses."""
    ld = net.load
    load = float((ld.p_mw * ld.scaling)[ld.bus.isin(unsupplied) & ld.in_service].sum())
    gen = sum(
        float(net[t].p_mw[net[t].bus.isin(unsupplied) & net[t].in_service].sum())
        for t in ("gen", "sgen")
    )
    return load, gen


def primary_class(flags: list[str]) -> str:
    for c in _PRECEDENCE:
        if c in flags:
            return c
    return "secure"


def energised_buses(net) -> set[int]:
    return {int(i) for i in net.bus.index[np.isfinite(net.res_bus.vm_pu.values)]}


def total_load_mw(net) -> float:
    ld = net.load
    return float((ld.p_mw * ld.scaling)[ld.in_service].sum())


def reassign_isolated_slack(model: GridModel, net) -> dict | None:
    """Move the reference to the main island if the outage cut every slack off from it.

    The main island is the connected component with the largest in-service load. If it holds no
    slack (ext_grid or slack gen), the in-service ``gen`` with the largest ``max_p_mw`` in it
    becomes the slack and every slack outside it is taken out of service (its island is
    de-energised; its pre-outage active power is reported as stranded generation). Without this,
    a single-slack power flow would report the whole system as islanded when only the slack's
    step-up branch is lost. Returns ``None`` when nothing changes or no candidate exists.
    """
    graph = create_nxgraph(net, respect_switches=True, include_out_of_service=False)
    ld = net.load[net.load.in_service]
    load_at = (ld.p_mw * ld.scaling).groupby(ld.bus).sum()
    comps = list(nx.connected_components(graph))
    if len(comps) < 2:
        return None
    main = max(comps, key=lambda c: float(load_at.reindex(list(c)).fillna(0.0).sum()))
    eg = net.ext_grid[net.ext_grid.in_service]
    sg = net.gen[net.gen.in_service & net.gen.slack]
    if eg.bus.isin(main).any() or sg.bus.isin(main).any():
        return None
    cand = net.gen[net.gen.in_service & net.gen.bus.isin(main)]
    if cand.empty:
        return None
    stranded, stranded_p = [], 0.0
    for table, rows in (("ext_grid", eg), ("gen", sg)):
        for i in rows.index:
            stranded.append(model.gen_for_element(table, i).id)
            stranded_p += float(net[f"res_{table}"].at[i, "p_mw"])  # pre-outage solution
            net[table].at[i, "in_service"] = False
    new = int(cand.max_p_mw.idxmax())
    net.gen.at[new, "slack"] = True
    return {
        "new_slack": model.gen_for_element("gen", new).id,
        "new_slack_max_p_mw": float(net.gen.at[new, "max_p_mw"]),
        "stranded_slack": stranded,
        "stranded_slack_p_mw": stranded_p,
        "new_slack_p_mw": None,
        "new_slack_exceeds_pmax": None,
    }


def run_outage(
    model: GridModel, outage: tuple[BranchRef, ...], *, total_load: float, base_energised: set[int]
) -> dict:
    """Apply ``outage`` to a copy of the solved base net, re-solve and classify."""
    net = model.copy().net
    for br in outage:
        net[br.table].at[br.index, "in_service"] = False
    reslack = reassign_isolated_slack(model, net)
    pf = run_pf(net, init="results")
    stranded_p = reslack["stranded_slack_p_mw"] if reslack else 0.0
    row: dict = {
        "outage": [{"id": br.id, "component": br.component} for br in outage],
        "converged": pf.converged,
        "message": None,
    }
    empty = {
        "severity": None,
        "max_loading_pct": None,
        "max_loading_element": None,
        "overloads": [],
        "min_vm_pu": None,
        "max_vm_pu": None,
        "voltage_violations": [],
        "islanded_buses": [],
        "islanded_load_mw": None,
        "islanded_generation_mw": None,
        "slack_excess_mw": None,
        "losses_mw": None,
    }
    if pf.error is not None:
        row.update(empty, classes=["error"], message=pf.error)
    elif not pf.converged:
        # islanding is still reported topologically even if NR fails on the remaining grid
        unsupplied = {int(b) for b in unsupplied_buses(net)} & base_energised
        isl_load, isl_gen = _islanded_power(net, unsupplied)
        row.update(
            empty,
            classes=["non_convergent"] + (["islanding"] if unsupplied else []),
            islanded_buses=sorted((model.bus_id(b) for b in unsupplied), key=_bus_sort),
            islanded_load_mw=_r(isl_load, 3),
            islanded_generation_mw=_r(isl_gen + stranded_p, 3),
            message=f"Newton-Raphson not converged in {PF_OPTIONS['max_iteration']} iterations",
        )
    else:
        st = evaluate_state(model, net, total_load_mw=total_load, base_energised=base_energised)
        row.update(
            classes=st["flags"] or ["secure"],
            severity=_r(st["severity"], 6),
            max_loading_pct=_r(st["max_loading_pct"], 2),
            max_loading_element=st["max_loading_element"],
            overloads=st["overloads"],
            min_vm_pu=_r(st["min_vm_pu"]),
            max_vm_pu=_r(st["max_vm_pu"]),
            voltage_violations=st["voltage_violations"],
            islanded_buses=st["islanded_buses"],
            islanded_load_mw=_r(st["islanded_load_mw"], 3),
            islanded_generation_mw=_r(st["islanded_generation_mw"] + stranded_p, 3),
            slack_excess_mw=_r(st["slack_excess_mw"], 3),
            losses_mw=_r(st["losses_mw"], 3),
        )
        if reslack:
            new = model.gen(reslack["new_slack"])
            p = float(net.res_gen.at[new.index, "p_mw"])
            reslack["new_slack_p_mw"] = _r(p, 3)
            reslack["new_slack_exceeds_pmax"] = bool(p > reslack["new_slack_max_p_mw"] + 1e-6)
    if reslack:
        reslack["stranded_slack_p_mw"] = _r(reslack["stranded_slack_p_mw"], 3)
    row["slack_reassignment"] = reslack
    row["class"] = primary_class(row["classes"])
    return row


def _rank(rows: list[dict]) -> list[dict]:
    def key(r: dict):
        unsolved = r["severity"] is None
        return (
            0 if unsolved else 1,
            0.0 if unsolved else -r["severity"],
            _PRECEDENCE.index(r["class"]) if r["class"] in _PRECEDENCE else len(_PRECEDENCE),
            [int(o["id"].rsplit("-", 1)[-1]) for o in r["outage"]],
        )

    rows = sorted(rows, key=key)
    out = []
    for i, r in enumerate(rows, start=1):
        ordered = {"rank": i, "class": r["class"]}
        ordered.update({k: v for k, v in r.items() if k != "class"})
        out.append(ordered)
    return out


def _counts(rows: list[dict]) -> dict[str, int]:
    c = Counter(r["class"] for r in rows)
    return {k: int(c.get(k, 0)) for k in CLASSES}


def contingency_study(model: GridModel, *, n2_top_k: int = 0) -> dict:
    """N-1 over all in-service branches (+ N-2 over pairs of the ``n2_top_k`` worst N-1)."""
    net = model.net
    if not net.converged:
        raise RuntimeError("base case must be solved and converged before contingency screening")
    base_energised = energised_buses(net)
    total_load = total_load_mw(net)
    candidates = [b for b in model.branches if bool(net[b.table].at[b.index, "in_service"])]

    t0 = time.perf_counter()
    n1 = _rank(
        [
            run_outage(model, (b,), total_load=total_load, base_energised=base_energised)
            for b in candidates
        ]
    )
    n1_time = time.perf_counter() - t0
    by_id = {(b.component, b.id): b for b in candidates}

    n2_block = None
    if n2_top_k > 0:
        top = [r for r in n1 if r["class"] != "error"][:n2_top_k]
        pairs = list(
            itertools.combinations(
                [by_id[(r["outage"][0]["component"], r["outage"][0]["id"])] for r in top], 2
            )
        )
        t1 = time.perf_counter()
        n2 = _rank(
            [
                run_outage(model, pair, total_load=total_load, base_energised=base_energised)
                for pair in pairs
            ]
        )
        n2_block = {
            "selection": f"all pairs of the {len(top)} highest-ranked N-1 contingencies",
            "top_k": n2_top_k,
            "pair_count": len(pairs),
            "class_counts": _counts(n2),
            "runtime_s": round(time.perf_counter() - t1, 3),
            "contingencies": n2,
        }
    severities = [r["severity"] for r in n1 if r["severity"] is not None]
    return {
        "summary": {
            "contingency_count": len(n1),
            "class_counts": _counts(n1),
            "runtime_s": round(n1_time, 3),
            "worst_severity": max(severities) if severities else None,
        },
        "contingencies": n1,
        "n_minus_2": n2_block,
    }
