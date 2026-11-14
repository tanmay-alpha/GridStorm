"""AC power flow with fixed options and solver-independent result extraction.

Branch loading is computed uniformly for every branch type as the MATPOWER apparent-power
convention ``loading_pct = 100 * max(|S_from|, |S_to|) / RATE_A`` (MVA). ``RATE_A = 0`` means no
limit (loading reported as ``None``). pandapower's own ``res_line.loading_percent`` is current based
and is not used.
"""

from __future__ import annotations

import logging
import time
import warnings
from dataclasses import dataclass

import numpy as np
import pandapower as pp
from pandapower.auxiliary import LoadflowNotConverged

from .model import GridModel

#: Fixed Newton-Raphson options used for every power flow in this package.
PF_OPTIONS: dict = {
    "algorithm": "nr",
    "calculate_voltage_angles": True,
    "trafo_model": "pi",  # MATPOWER uses a pi equivalent, not pandapower's default T model.
    "tolerance_mva": 1e-8,
    "max_iteration": 30,
    "enforce_q_lims": False,
    "numba": True,
}

_FLOW_COLUMNS = {
    "line": ("p_from_mw", "q_from_mvar", "p_to_mw", "q_to_mvar"),
    "impedance": ("p_from_mw", "q_from_mvar", "p_to_mw", "q_to_mvar"),
    "trafo": ("p_hv_mw", "q_hv_mvar", "p_lv_mw", "q_lv_mvar"),
}

logging.getLogger("pandapower").setLevel(logging.ERROR)


@dataclass
class PFOutcome:
    converged: bool
    error: str | None
    wall_time_s: float
    iterations: int | None


def run_pf(net: pp.pandapowerNet, *, init: str = "dc", **overrides) -> PFOutcome:
    """Run ``pp.runpp`` with :data:`PF_OPTIONS`; never raises for solver failures."""
    opts = {**PF_OPTIONS, **overrides}
    t0 = time.perf_counter()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            pp.runpp(net, init=init, **opts)
    except LoadflowNotConverged:
        return PFOutcome(False, None, time.perf_counter() - t0, None)
    except Exception as exc:  # noqa: BLE001 - classified as `error` by callers
        return PFOutcome(False, f"{type(exc).__name__}: {exc}", time.perf_counter() - t0, None)
    iterations = net._ppc.get("iterations") if isinstance(net._ppc, dict) else None
    return PFOutcome(
        bool(net.converged),
        None,
        time.perf_counter() - t0,
        int(iterations) if iterations is not None else None,
    )


def _nan_to_none(x: float) -> float | None:
    return None if x is None or not np.isfinite(x) else float(x)


def branch_flows(model: GridModel, net: pp.pandapowerNet | None = None) -> list[dict]:
    """Per-branch flows (MW/Mvar at both ends) and S-based loading for a solved net."""
    net = model.net if net is None else net
    rows = []
    for br in model.branches:
        res = net[f"res_{br.table}"]
        in_service = bool(net[br.table].at[br.index, "in_service"])
        pf, qf, pt, qt = (float(res.at[br.index, c]) for c in _FLOW_COLUMNS[br.table])
        if not in_service or not np.all(np.isfinite([pf, qf, pt, qt])):
            rows.append(
                {
                    "ref": br,
                    "in_service": in_service,
                    "p_from_mw": None,
                    "q_from_mvar": None,
                    "p_to_mw": None,
                    "q_to_mvar": None,
                    "s_max_mva": None,
                    "loading_pct": None,
                }
            )
            continue
        if br.table == "trafo" and int(net.trafo.at[br.index, "hv_bus"]) != model.bus_index(
            br.from_bus
        ):
            pf, qf, pt, qt = pt, qt, pf, qf  # pandapower hv side is the MATPOWER to-bus
        s_max = max(np.hypot(pf, qf), np.hypot(pt, qt))
        loading = 100.0 * s_max / br.rate_a_mva if br.rate_a_mva else None
        rows.append(
            {
                "ref": br,
                "in_service": True,
                "p_from_mw": pf,
                "q_from_mvar": qf,
                "p_to_mw": pt,
                "q_to_mvar": qt,
                "s_max_mva": float(s_max),
                "loading_pct": loading,
            }
        )
    return rows


def bus_voltages(model: GridModel, net: pp.pandapowerNet | None = None) -> dict[str, tuple]:
    """bus id -> (vm_pu | None, va_deg | None); None for de-energised buses."""
    net = model.net if net is None else net
    vm = net.res_bus.vm_pu
    va = net.res_bus.va_degree
    return {
        model.bus_id(i): (_nan_to_none(vm.at[i]), _nan_to_none(va.at[i])) for i in net.bus.index
    }


def _nansum(series) -> float:
    return float(np.nansum(series.values)) if len(series) else 0.0


def power_balance(net: pp.pandapowerNet) -> dict:
    """Σ generation − Σ load − Σ shunt P − Σ branch losses (MW); ≈ 0 for a converged PF."""
    gen = _nansum(net.res_ext_grid.p_mw) + _nansum(net.res_gen.p_mw) + _nansum(net.res_sgen.p_mw)
    load = _nansum(net.res_load.p_mw)
    shunt = _nansum(net.res_shunt.p_mw) if len(net.shunt) else 0.0
    losses = sum(
        _nansum(net[f"res_{t}"].pl_mw) for t in ("line", "trafo", "impedance") if len(net[t])
    )
    return {
        "generation_mw": gen,
        "load_mw": load,
        "shunt_mw": shunt,
        "losses_mw": losses,
        "residual_mw": gen - load - shunt - losses,
    }
