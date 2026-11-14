"""Base operating point from pandapower's AC optimal power flow (PIPS interior point).

PGLib cases ship generator set points that are not a feasible operating point (e.g. the
pglib_opf_case118_ieee file dispatch overloads branches to ~197 % and drives the slack above its
Pmax). Contingency studies are therefore run around an AC-OPF base point: generator active power
and voltage set points are taken from ``pp.runopp`` (polynomial costs from ``mpc.gencost``, branch
MVA limits ``RATE_A``, bus voltage limits, generator P/Q limits). pandapower's OPF does not model
MATPOWER branch angle-difference limits (``ANGMIN``/``ANGMAX``), so its objective can be slightly
below the PGLib baseline.
"""

from __future__ import annotations

import copy
import time
import warnings

import pandapower as pp

from .model import GridModel


def _ext_grids_to_slack_gens(net: pp.pandapowerNet) -> dict[int, int]:
    """Replace ext_grids by slack gens (pandapower's OPF honours costs/limits on gens reliably)."""
    mapping: dict[int, int] = {}
    for i, eg in net.ext_grid.iterrows():
        g = pp.create_gen(
            net, bus=eg.bus, p_mw=0.0, vm_pu=eg.vm_pu, slack=True, controllable=True,
            max_p_mw=eg.max_p_mw, min_p_mw=eg.min_p_mw, max_q_mvar=eg.max_q_mvar,
            min_q_mvar=eg.min_q_mvar, in_service=eg.in_service,
        )
        sel = (net.poly_cost.et == "ext_grid") & (net.poly_cost.element == i)
        net.poly_cost.loc[sel, "et"] = "gen"
        net.poly_cost.loc[sel, "element"] = g
        mapping[int(i)] = int(g)
    net.ext_grid.drop(net.ext_grid.index, inplace=True)
    return mapping


def apply_acopf_dispatch(model: GridModel) -> dict:
    """Solve the AC-OPF on a copy and write P/V set points into ``model.net`` in place.

    Returns a summary ``{converged, objective, wall_time_s, message}``. On failure ``model.net``
    keeps the case-file set points.
    """
    net = copy.deepcopy(model.net)
    eg_map = _ext_grids_to_slack_gens(net)
    t0 = time.perf_counter()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            pp.runopp(net, calculate_voltage_angles=True, init="flat", numba=True)
        converged, message = bool(net.OPF_converged), None
    except Exception as exc:  # noqa: BLE001 - reported, base falls back to case set points
        converged, message = False, f"{type(exc).__name__}: {exc}"
    wall = time.perf_counter() - t0
    if not converged:
        return {"converged": False, "objective": None, "wall_time_s": wall,
                "message": message or "OPF did not converge"}

    vm = net.res_bus.vm_pu
    base = model.net
    for g in model.gens:
        if g.table == "ext_grid":
            base.ext_grid.at[g.index, "vm_pu"] = float(vm.at[base.ext_grid.at[g.index, "bus"]])
            continue
        if g.table == "gen":
            base.gen.at[g.index, "p_mw"] = float(net.res_gen.at[g.index, "p_mw"])
            base.gen.at[g.index, "vm_pu"] = float(vm.at[base.gen.at[g.index, "bus"]])
        else:  # sgen: fixed P and Q injection
            base.sgen.at[g.index, "p_mw"] = float(net.res_sgen.at[g.index, "p_mw"])
            base.sgen.at[g.index, "q_mvar"] = float(net.res_sgen.at[g.index, "q_mvar"])
    slack_p = {i: float(net.res_gen.at[g, "p_mw"]) for i, g in eg_map.items()}
    return {"converged": True, "objective": float(net.res_cost), "wall_time_s": wall,
            "message": None, "slack_p_mw": slack_p}
