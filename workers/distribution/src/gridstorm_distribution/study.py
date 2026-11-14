"""AC time-series power flow of a SimBench distribution grid (``pandapower.timeseries``).

One study = one SimBench grid code, one contiguous window of the SimBench 2016 profiles (15-min
resolution), optional stress factors on load and PV, and an optional mitigation built only from
existing pandapower machinery:

* ``pv_feed_in_cap_pu``: modeled static active-power limit per PV unit,
  ``p <= cap * sn_mva``; applied before the power flow, with curtailed energy reported.
* ``q_u_control``: stylised reactive power voltage control Q(U) of every PV unit with
  ``pandapower.control.DERController`` + ``QModelQVCurve`` inside pandapower's
  ``PQVArea4105(variant=2)``. This is not a grid-code compliance assessment.

Balanced three-phase positive-sequence AC power flow (Newton-Raphson); no protection, no dynamics.
"""

from __future__ import annotations

import copy
import functools
import importlib.metadata
import logging
import time
from dataclasses import asdict, dataclass

import numpy as np
import pandapower as pp
import pandas as pd
import simbench as sb
from pandapower.control import ConstControl
from pandapower.control.controller.DERController import (
    DERController,
    PQVArea4105,
    QModelQVCurve,
    QVCurve,
)
from pandapower.timeseries import DFData, OutputWriter, run_timeseries

from .metrics import energy_mwh, loading_flags, summarize_flags, top_elements, voltage_flags

DT_H = 0.25  # SimBench profiles: 15-min resolution, calendar year 2016
PROFILE_TIME_FORMAT = "%d.%m.%Y %H:%M"
# Stylised Q(U): full requested reactive power at 0.93 / 1.07 pu, dead band 0.97..1.03 pu.
# q is in pu of sn_mva, positive = injecting. PQVArea4105 further constrains the request.
QU_VM_POINTS_PU = (0.0, 0.93, 0.97, 1.03, 1.07, 2.0)
QU_Q_POINTS_PU = (0.484, 0.484, 0.0, 0.0, -0.484, -0.484)
# Fallback limits only for buses where SimBench gives none (EN 50160: Un +/- 10 %).
DEFAULT_VM_MIN_PU = 0.9
DEFAULT_VM_MAX_PU = 1.1
DEFAULT_MAX_LOADING_PCT = 100.0
PF_TOLERANCE_MVA = 1e-8
PF_MAX_ITERATION = 30

log = logging.getLogger("gridstorm_distribution")


@dataclass(frozen=True)
class StudyConfig:
    grid_code: str
    start: str  # "YYYY-MM-DD HH:MM", inside the SimBench 2016 profile year
    n_steps: int  # 15-min steps
    load_factor: float = 1.0  # multiplies load p_mw and q_mvar profiles
    pv_factor: float = 1.0  # multiplies PV installed capacity (sn_mva) and PV p_mw profile
    pv_feed_in_cap_pu: float | None = None  # mitigation: p <= cap * sn_mva per PV unit
    q_u_control: bool = False  # mitigation: DERController Q(U) on every PV unit
    # Upstream boundary: MV-side voltage setpoint of the ext_grid (None = SimBench value 1.025).
    ext_grid_vm_pu: float | None = None


def versions() -> dict[str, str]:
    return {
        "pandapower": importlib.metadata.version("pandapower"),
        "simbench": importlib.metadata.version("simbench"),
        "pandas": importlib.metadata.version("pandas"),
        "numpy": importlib.metadata.version("numpy"),
    }


@functools.lru_cache(maxsize=4)
def _load_cached(grid_code: str):
    net = sb.get_simbench_net(grid_code)
    abs_values = sb.get_absolute_values(net, profiles_instead_of_study_cases=True)
    times = pd.to_datetime(net.profiles["load"]["time"], format=PROFILE_TIME_FORMAT)
    return net, abs_values, pd.DatetimeIndex(times)


def load_grid(grid_code: str):
    """Return a fresh copy of ``(net, absolute profile values, profile timestamps)``."""
    net, abs_values, times = _load_cached(grid_code)
    return copy.deepcopy(net), {k: v.copy() for k, v in abs_values.items()}, times


def _window(times: pd.DatetimeIndex, start: str, n_steps: int) -> np.ndarray:
    t0 = pd.Timestamp(start)
    pos = np.flatnonzero(times == t0)
    if pos.size != 1:
        raise ValueError(f"window start {start!r} is not a SimBench profile timestamp")
    i0 = int(pos[0])
    if n_steps < 1 or i0 + n_steps > len(times):
        raise ValueError(f"window {start!r} + {n_steps} steps exceeds the profile year")
    return np.arange(i0, i0 + n_steps)


def _pv_index(net) -> pd.Index:
    return net.sgen.index[net.sgen["type"].astype(str).str.contains("PV", case=False)]


def _names(df: pd.DataFrame) -> list[str]:
    return [
        str(n) if isinstance(n, str) and n else f"#{i}"
        for i, n in zip(df.index, df["name"], strict=True)
    ]


def run_study(cfg: StudyConfig) -> dict:
    """Run one time-series study; returns a JSON-compatible payload (contract §5 ``timeseries``)."""
    net, abs_values, times = load_grid(cfg.grid_code)
    rows = _window(times, cfg.start, cfg.n_steps)
    stamps = times[rows]
    steps = range(cfg.n_steps)
    pv = _pv_index(net)
    # SimBench scenario-2 PV-home-storage profiles convert (simbench 1.6.3 -> pandapower) to a
    # discharge-only series (1-LV-rural1--2-sw: -125 MWh/yr from 0.41 MWh of capacity), which is
    # not physical; storages are therefore held idle (p = q = 0) instead of following it.
    if cfg.ext_grid_vm_pu is not None:
        net.ext_grid["vm_pu"] = cfg.ext_grid_vm_pu
    n_storage_idled = int(len(net.storage))
    if n_storage_idled:
        net.storage[["p_mw", "q_mvar"]] = 0.0

    # ---- profiles for the window (absolute MW / MVAr, columns = element index) -----------------
    prof: dict[tuple[str, str], pd.DataFrame] = {}
    for key, df in abs_values.items():
        if df.shape[1] == 0 or key[0] == "storage":
            continue
        sub = df.iloc[rows].reset_index(drop=True)
        if key[0] == "load":
            sub = sub * cfg.load_factor
        prof[key] = sub

    sgen_p = prof.get(("sgen", "p_mw"))
    pv_uncapped = pd.DataFrame(index=range(cfg.n_steps))
    if len(pv):
        net.sgen.loc[pv, "sn_mva"] = net.sgen.loc[pv, "sn_mva"] * cfg.pv_factor
        net.sgen.loc[pv, "p_mw"] = net.sgen.loc[pv, "p_mw"] * cfg.pv_factor
        sgen_p.loc[:, pv] = sgen_p.loc[:, pv] * cfg.pv_factor
        pv_uncapped = sgen_p.loc[:, pv].copy()
        if cfg.pv_feed_in_cap_pu is not None:
            cap = net.sgen.loc[pv, "sn_mva"].to_numpy() * cfg.pv_feed_in_cap_pu
            sgen_p.loc[:, pv] = np.minimum(sgen_p.loc[:, pv].to_numpy(), cap)

    # ---- controllers ------------------------------------------------------------------------
    for (elm, var), df in prof.items():
        idx = list(df.columns)
        if elm == "sgen" and var == "p_mw" and cfg.q_u_control:
            idx = [i for i in idx if i not in set(pv)]
        if not idx:
            continue
        ConstControl(
            net,
            element=elm,
            variable=var,
            element_index=idx,
            data_source=DFData(df[idx]),
            profile_name=idx,
        )
    if cfg.q_u_control and len(pv):
        DERController(
            net,
            list(pv),
            element="sgen",
            q_model=QModelQVCurve(
                QVCurve(vm_points_pu=QU_VM_POINTS_PU, q_points_pu=QU_Q_POINTS_PU)
            ),
            pqv_area=PQVArea4105(variant=2),
            data_source=DFData(sgen_p[list(pv)]),
            p_profile=list(pv),
            ts_absolute=True,
        )

    # ---- run ----------------------------------------------------------------------------------
    ow = OutputWriter(net, time_steps=steps, output_path=None)
    logged = [
        ("res_bus", "vm_pu"),
        ("res_line", "loading_percent"),
        ("res_line", "pl_mw"),
        ("res_trafo", "loading_percent"),
        ("res_trafo", "pl_mw"),
        ("res_ext_grid", "p_mw"),
        ("res_ext_grid", "q_mvar"),
        ("res_load", "p_mw"),
        ("res_sgen", "p_mw"),
        ("res_sgen", "q_mvar"),
    ]
    for table, var in logged:
        ow.log_variable(table, var)
    t0 = time.perf_counter()
    run_timeseries(
        net,
        time_steps=steps,
        continue_on_divergence=True,
        verbose=False,
        algorithm="nr",
        tolerance_mva=PF_TOLERANCE_MVA,
        max_iteration=PF_MAX_ITERATION,
        numba=False,
    )
    runtime_s = time.perf_counter() - t0
    out = ow.output
    params = out["Parameters"]
    failed = params["powerflow_failed"].to_numpy(dtype=bool)
    unstable = params["controller_unstable"].to_numpy(dtype=bool)
    invalid = failed | unstable

    def res(key: str) -> pd.DataFrame:
        df = out[key].copy()
        df.loc[invalid, :] = np.nan  # neither failed PF nor unstable controls are usable
        return df

    vm = res("res_bus.vm_pu")
    line_ld = res("res_line.loading_percent")
    trafo_ld = res("res_trafo.loading_percent")
    losses = res("res_line.pl_mw").sum(axis=1, min_count=1) + res("res_trafo.pl_mw").sum(
        axis=1, min_count=1
    )
    imp = res("res_ext_grid.p_mw").sum(axis=1, min_count=1)
    imp_q = res("res_ext_grid.q_mvar").sum(axis=1, min_count=1)
    load_mw = res("res_load.p_mw").sum(axis=1, min_count=1)
    sgen_res = res("res_sgen.p_mw")
    pv_mw = sgen_res[list(pv)].sum(axis=1, min_count=1) if len(pv) else pd.Series(0.0, index=steps)
    pv_q = (
        res("res_sgen.q_mvar")[list(pv)].sum(axis=1, min_count=1)
        if len(pv)
        else pd.Series(0.0, index=steps)
    )
    pv_curtailed = (
        (pv_uncapped.sum(axis=1) - sgen_p[list(pv)].sum(axis=1))
        if len(pv)
        else pd.Series(0.0, index=steps)
    )
    pv_curtailed.loc[invalid] = np.nan

    # ---- limits & flags -----------------------------------------------------------------------
    bus = net.bus.loc[vm.columns]
    vmin = (
        bus["min_vm_pu"].fillna(DEFAULT_VM_MIN_PU).to_numpy()
        if "min_vm_pu" in bus
        else np.full(len(bus), DEFAULT_VM_MIN_PU)
    )
    vmax = (
        bus["max_vm_pu"].fillna(DEFAULT_VM_MAX_PU).to_numpy()
        if "max_vm_pu" in bus
        else np.full(len(bus), DEFAULT_VM_MAX_PU)
    )
    under, over = voltage_flags(vm.to_numpy(), vmin, vmax)
    line_lim = _limit(net.line, line_ld.columns)
    trafo_lim = _limit(net.trafo, trafo_ld.columns)
    line_over = loading_flags(line_ld.to_numpy(), line_lim)
    trafo_over = loading_flags(trafo_ld.to_numpy(), trafo_lim)
    bus_names = _names(net.bus.loc[vm.columns])
    line_names = _names(net.line.loc[line_ld.columns])
    trafo_names = _names(net.trafo.loc[trafo_ld.columns])

    vm_np = vm.to_numpy()
    series = {
        "time": [t.strftime("%Y-%m-%dT%H:%M") for t in stamps],
        "converged": (~invalid).tolist(),
        "vm_min_pu": _nan_reduce(np.nanmin, vm_np),
        "vm_max_pu": _nan_reduce(np.nanmax, vm_np),
        "n_buses_over_voltage": over.sum(axis=1).tolist(),
        "n_buses_under_voltage": under.sum(axis=1).tolist(),
        "max_line_loading_pct": _nan_reduce(np.nanmax, line_ld.to_numpy()),
        "n_lines_overloaded": line_over.sum(axis=1).tolist(),
        "max_trafo_loading_pct": _nan_reduce(np.nanmax, trafo_ld.to_numpy()),
        "n_trafos_overloaded": trafo_over.sum(axis=1).tolist(),
        "losses_mw": _list(losses),
        "grid_import_mw": _list(imp),
        "grid_import_mvar": _list(imp_q),
        "load_mw": _list(load_mw),
        "pv_mw": _list(pv_mw),
        "pv_q_mvar": _list(pv_q),
        "pv_curtailed_mw": _list(pv_curtailed),
    }
    load_energy = energy_mwh(load_mw, DT_H)
    loss_energy = energy_mwh(losses, DT_H)
    summary = {
        "vm_min_pu": _scalar(np.nanmin, vm_np),
        "vm_max_pu": _scalar(np.nanmax, vm_np),
        "max_line_loading_pct": _scalar(np.nanmax, line_ld.to_numpy()),
        "max_trafo_loading_pct": _scalar(np.nanmax, trafo_ld.to_numpy()),
        "over_voltage": summarize_flags(over, DT_H),
        "under_voltage": summarize_flags(under, DT_H),
        "line_overload": summarize_flags(line_over, DT_H),
        "trafo_overload": summarize_flags(trafo_over, DT_H),
        "any_violation": summarize_flags(
            np.column_stack([over.any(1), under.any(1), line_over.any(1), trafo_over.any(1)]), DT_H
        )["steps_with_violation"]
        * DT_H,
        "energy_mwh": {
            "load": load_energy,
            "pv": energy_mwh(pv_mw, DT_H),
            "pv_curtailed": energy_mwh(pv_curtailed, DT_H),
            "grid_import": energy_mwh(imp.clip(lower=0), DT_H),
            "grid_export": energy_mwh((-imp).clip(lower=0), DT_H),
            "losses": loss_energy,
        },
        "losses_pct_of_load": (
            loss_energy / load_energy * 100.0
            if load_energy is not None and load_energy > 0
            else None
        ),
        "max_reverse_flow_mw": float(max(0.0, -np.nanmin(imp.to_numpy())))
        if imp.notna().any()
        else None,
    }
    top = {
        "over_voltage_buses": top_elements(over, vm_np, bus_names, worst="max", dt_h=DT_H),
        "under_voltage_buses": top_elements(under, vm_np, bus_names, worst="min", dt_h=DT_H),
        "overloaded_lines": top_elements(
            line_over, line_ld.to_numpy(), line_names, worst="max", dt_h=DT_H
        ),
        "overloaded_trafos": top_elements(
            trafo_over, trafo_ld.to_numpy(), trafo_names, worst="max", dt_h=DT_H
        ),
    }
    grid = {
        "simbench_code": cfg.grid_code,
        "buses": int(len(net.bus)),
        "lines": int(len(net.line)),
        "trafos": int(len(net.trafo)),
        "loads": int(len(net.load)),
        "sgens": int(len(net.sgen)),
        "pv_units": int(len(pv)),
        "storages": int(len(net.storage)),
        "storages_idled": n_storage_idled,
        "pv_installed_mva": float(net.sgen.loc[pv, "sn_mva"].sum()) if len(pv) else 0.0,
        "load_reference_mw": float(net.load["p_mw"].sum()),
        "trafo_sn_mva": [float(x) for x in net.trafo["sn_mva"]],
        "ext_grid_vm_pu": [float(x) for x in net.ext_grid["vm_pu"]],
    }
    return {
        "schema": "gridstorm-distribution-timeseries/1.0",
        "provenance": "calculated",
        "source": {
            "name": "SimBench",
            "package_version": versions()["simbench"],
            "data_version": 1,
            "provenance": "synthetic",
            "url": "https://simbench.de/en/",
            "license": "ODbL-1.0",
            "contents_license": "DbCL-1.0",
            "attribution": "SimBench: University of Kassel, TU Dortmund, RWTH Aachen "
            "University and Fraunhofer IEE; individual contributors.",
        },
        "config": asdict(cfg),
        "grid": grid,
        "window": {
            "start": series["time"][0],
            "end": series["time"][-1],
            "n_steps": cfg.n_steps,
            "dt_h": DT_H,
            "profile_year": 2016,
        },
        "assumptions": _assumptions(cfg, n_storage_idled),
        "limits": {
            "voltage": "per-bus SimBench min_vm_pu/max_vm_pu (LV buses 0.90-1.10 pu = EN 50160 "
            "+/-10 %; MV buses 0.965-1.055 pu); fallback 0.90-1.10 pu",
            "vm_min_pu_range": [float(vmin.min()), float(vmin.max())],
            "vm_max_pu_range": [float(vmax.min()), float(vmax.max())],
            "line_max_loading_pct": [float(line_lim.min()), float(line_lim.max())]
            if len(line_lim)
            else None,
            "trafo_max_loading_pct": [float(trafo_lim.min()), float(trafo_lim.max())]
            if len(trafo_lim)
            else None,
            "violation_rule": "strict: vm > max, vm < min, loading > max_loading_percent",
        },
        "solver": {
            "name": "pandapower.runpp",
            "algorithm": "nr",
            "tolerance_mva": PF_TOLERANCE_MVA,
            "max_iteration": PF_MAX_ITERATION,
            "continue_on_divergence": True,
            "threads": 1,
            "controllers": sorted({type(c).__name__ for c in net.controller["object"]}),
            "versions": versions(),
        },
        "convergence": {
            "steps": cfg.n_steps,
            "converged_steps": int((~invalid).sum()),
            "failed_steps": int(failed.sum()),
            "controller_unstable_steps": int(unstable.sum()),
            "valid_hours": float((~invalid).sum() * DT_H),
            "energy_scope": "only converged PF steps with stable controls",
        },
        "runtime_s": runtime_s,
        "summary": summary,
        "top_violations": top,
        "series": series,
    }


def _assumptions(cfg: StudyConfig, n_storage_idled: int) -> list[str]:
    out = [
        "Balanced three-phase positive-sequence AC power flow (pandapower Newton-Raphson); "
        "no unbalance, protection, dynamics or thermal time constants.",
        "Profiles: SimBench 2016 absolute load and PV profiles (15-min), step-wise quasi-static.",
        "Upstream MV grid modelled as SimBench ext_grid at its fixed setpoint; transformer tap "
        "position fixed at the SimBench value (no OLTC action).",
        "Loading limits: SimBench max_loading_percent (100 %) on continuous rating; short-term "
        "overload capability of transformers is not credited.",
    ]
    if cfg.load_factor != 1.0:
        out.append(f"Load P and Q profiles scaled by {cfg.load_factor} (stress factor).")
    if cfg.pv_factor != 1.0:
        out.append(f"PV installed capacity (sn_mva) and PV P profile scaled by {cfg.pv_factor}.")
    if cfg.pv_feed_in_cap_pu is not None:
        out.append(
            f"PV active power capped at {cfg.pv_feed_in_cap_pu} x sn_mva per unit "
            "(static feed-in limit); surplus reported as curtailed energy."
        )
    if cfg.ext_grid_vm_pu is not None:
        out.append(
            f"MV-side (ext_grid) voltage held at {cfg.ext_grid_vm_pu} pu "
            "(explicit fixed upstream boundary assumption, not an observed voltage)."
        )
    if cfg.q_u_control:
        out.append(
            "Stylised PV Q(U) via pandapower DERController/QModelQVCurve with "
            "PQVArea4105 variant 2; inverter apparent-power saturation not modelled; "
            "not a grid-code compliance assessment."
        )
    if n_storage_idled:
        out.append(
            f"{n_storage_idled} SimBench PV-home storages held idle (p=q=0): their "
            "converted profiles discharge only and are not energy-consistent."
        )
    return out


def _limit(table: pd.DataFrame, cols) -> np.ndarray:
    if "max_loading_percent" in table:
        return table.loc[cols, "max_loading_percent"].fillna(DEFAULT_MAX_LOADING_PCT).to_numpy()
    return np.full(len(cols), DEFAULT_MAX_LOADING_PCT)


def _nan_reduce(fn, arr: np.ndarray) -> list[float | None]:
    if arr.shape[1] == 0:
        return [None] * arr.shape[0]
    out = []
    for row in arr:
        out.append(None if np.isnan(row).all() else float(fn(row)))
    return out


def _scalar(fn, arr: np.ndarray) -> float | None:
    return None if arr.size == 0 or np.isnan(arr).all() else float(fn(arr))


def _list(s: pd.Series) -> list[float | None]:
    return [None if pd.isna(x) else float(x) for x in s]


def tiny_net_check() -> dict:
    """Single AC power flow on the smallest SimBench LV grid (used by tests)."""
    net, _, _ = load_grid("1-LV-rural1--0-sw")
    pp.runpp(net, algorithm="nr", tolerance_mva=PF_TOLERANCE_MVA, numba=False)
    return {
        "converged": bool(net.converged),
        "vm_min_pu": float(net.res_bus.vm_pu.min()),
        "vm_max_pu": float(net.res_bus.vm_pu.max()),
    }
