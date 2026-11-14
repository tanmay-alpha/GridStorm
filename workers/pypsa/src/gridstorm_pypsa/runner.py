"""StormSpec -> PyPSA linear optimal power flow -> gridstorm-result/1.0.

Pipeline (stages reported through ``progress``):

1. ``loading_network``   read ``<network_dir>/network.nc``, hash it, validate the scenario
2. ``applying_scenario`` slice the horizon, fix capacities, apply events and mitigation toggles
3. ``building_model``    ``n.optimize.create_model()`` (linopy)
4. ``solving``           ``n.optimize.solve_model(solver_name="highs", ...)``
5. ``postprocessing``    normalise PyPSA outputs into gridstorm-result/1.0
6. ``done``

Unsupported or invalid scenarios raise :class:`ScenarioRejected` (nothing is approximated).
Infeasible problems return ``outcome: "infeasible"`` without any numbers.
"""

from __future__ import annotations

import json
import logging
import math
import time
import warnings
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pypsa

import stormspec
from stormspec import (
    DemandMultiplier,
    ExecutionManifest,
    GeneratorOutage,
    Issue,
    LineOutage,
    LinkOutage,
    RenewableAvailabilityMultiplier,
    Scenario,
    StorageState,
)
from stormspec.manifest import detect_git_sha, utc_now_iso

STAGES = (
    "loading_network",
    "applying_scenario",
    "building_model",
    "solving",
    "postprocessing",
    "done",
)

RESULT_SCHEMA_VERSION = "gridstorm-result/1.0"
SHED_CARRIER = "load_shedding"
#: Branch loading (% of s_nom * s_max_pu) at or above which a branch counts as congested.
CONGESTION_THRESHOLD_PCT = 99.9
#: Load shedding below this (MW) is treated as numerical noise when counting shed hours.
SHED_EPS_MW = 1e-3
SERIES_DECIMALS = 4
METRIC_DECIMALS = 6

ProgressFn = Callable[[str], None]

logger = logging.getLogger(__name__)


class ScenarioRejected(Exception):
    """The scenario cannot be executed faithfully by this engine (or does not fit the network)."""

    def __init__(self, issues: list[Issue], warnings_: list[Issue] | None = None) -> None:
        self.issues = issues
        self.warnings = warnings_ or []
        super().__init__("; ".join(f"{i.code} at {i.path}: {i.message}" for i in issues))

    @property
    def code(self) -> str:
        return self.issues[0].code if self.issues else "invalid_scenario"


# --------------------------------------------------------------------------- helpers


def _version(pkg: str) -> str | None:
    try:
        return _pkg_version(pkg)
    except PackageNotFoundError:
        return None


def _num(x: Any, nd: int) -> float | None:
    """JSON-safe rounded float (NaN/inf -> None)."""
    if x is None:
        return None
    f = float(x)
    if not math.isfinite(f):
        return None
    r = round(f, nd)
    return 0.0 if r == 0 else r  # normalise -0.0


def _series(values: Any, nd: int = SERIES_DECIMALS) -> list[float | None]:
    return [_num(v, nd) for v in np.asarray(values, dtype=float).ravel()]


def _dense(n: pypsa.Network, component: str, attr: str) -> pd.DataFrame:
    """Snapshot x component dense frame of a static-or-varying attribute."""
    return n.get_switchable_as_dense(component, attr)


def _set_dynamic(n: pypsa.Network, list_name: str, attr: str, df: pd.DataFrame) -> None:
    """Replace the time-varying attribute ``attr`` of a component with ``df`` (full columns)."""
    getattr(n, f"{list_name}_t")[attr] = df


def _ids(df: pd.DataFrame) -> list[str]:
    return [str(i) for i in df.index]


def load_network(network_dir: Path) -> pypsa.Network:
    path = Path(network_dir) / "network.nc"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return pypsa.Network(str(path))


def _network_id(network_dir: Path) -> str:
    for name in ("manifest.json", "canonical.json"):
        p = Path(network_dir) / name
        if p.exists():
            try:
                nid = json.loads(p.read_text(encoding="utf-8")).get("network_id")
            except (OSError, ValueError):
                nid = None
            if nid:
                return str(nid)
    return Path(network_dir).resolve().name


def variable_generators(n: pypsa.Network) -> list[str]:
    """Generators with time-varying availability (a column in ``generators_t.p_max_pu``)."""
    return [str(c) for c in n.generators_t.p_max_pu.columns if c in n.generators.index]


def network_index(n: pypsa.Network, network_id: str) -> dict:
    """Minimal canonical-grid-shaped dict sufficient for :func:`stormspec.validate`.

    Built from the PyPSA network actually loaded so validation and execution agree on ids and on
    which generators are variable.
    """
    var = set(variable_generators(n))
    return {
        "schema_version": "canonical-grid/1.0",
        "network_id": network_id,
        "snapshots": {"count": len(n.snapshots)},
        "buses": [{"id": i} for i in _ids(n.buses)],
        "lines": [{"id": i} for i in _ids(n.lines)],
        "transformers": [{"id": i} for i in _ids(n.transformers)],
        "links": [{"id": i} for i in _ids(n.links)],
        "generators": [
            {"id": str(g), "carrier": str(c), "is_variable": str(g) in var}
            for g, c in n.generators.carrier.items()
        ],
        "loads": [{"id": str(ld), "bus": str(b)} for ld, b in n.loads.bus.items()],
        "storage_units": [{"id": i} for i in _ids(n.storage_units)],
        "stores": [{"id": i} for i in _ids(n.stores)],
        "carriers": [{"id": str(c)} for c in n.carriers.index]
        + [
            {"id": str(c)}
            for c in set(n.generators.carrier.astype(str)) - set(n.carriers.index.astype(str))
        ],
    }


def _reject(code: str, path: str, message: str) -> ScenarioRejected:
    return ScenarioRejected([Issue(code=code, path=path, message=message)])


# --------------------------------------------------------------------------- scenario application


class _Applied:
    """Book-keeping of what the scenario changed (for outputs and assumptions)."""

    def __init__(self) -> None:
        self.outaged_branches: set[tuple[str, str]] = set()  # ("lines"|"transformers", id)
        self.outaged_links: set[str] = set()
        self.outaged_generators: set[str] = set()
        self.shed_generators: dict[str, str] = {}  # shedding generator name -> bus
        self.fixed_extendables: dict[str, int] = {}
        self.assumptions: list[str] = []
        self.warnings: list[str] = []
        #: Variable generators of the ORIGINAL network (before events densify p_max_pu).
        self.variable_generators: list[str] = []


def _window_mask(snapshots: pd.Index, horizon_start: int, window) -> np.ndarray:
    """Boolean mask over the sliced snapshots for an absolute-index window (None = all)."""
    k = len(snapshots)
    if window is None:
        return np.ones(k, dtype=bool)
    idx = np.arange(horizon_start, horizon_start + k)
    return (idx >= window.start) & (idx < window.end)


def _fix_capacities(n: pypsa.Network, applied: _Applied) -> None:
    for list_name, ext, nom in (
        ("generators", "p_nom_extendable", "p_nom"),
        ("storage_units", "p_nom_extendable", "p_nom"),
        ("stores", "e_nom_extendable", "e_nom"),
        ("links", "p_nom_extendable", "p_nom"),
        ("lines", "s_nom_extendable", "s_nom"),
        ("transformers", "s_nom_extendable", "s_nom"),
    ):
        df = getattr(n, list_name)
        if len(df) and ext in df.columns:
            mask = df[ext].astype(bool)
            if mask.any():
                applied.fixed_extendables[list_name] = int(mask.sum())
                df.loc[mask, ext] = False
    if applied.fixed_extendables:
        detail = ", ".join(f"{v} {k}" for k, v in applied.fixed_extendables.items())
        applied.assumptions.append(
            "Dispatch-only optimisation: capacity expansion disabled; extendable components "
            f"({detail}) fixed at their nominal capacity from the dataset"
        )


def _release_setpoints(n: pypsa.Network, applied: _Applied) -> None:
    """Clear dataset dispatch set-points so the LOPF optimises dispatch.

    PyPSA fixes a component's output when ``p_set`` is given. Datasets imported from power-flow
    cases (e.g. MATPOWER ``Pg`` in PGLib) carry set-points meant as a power-flow operating point,
    not as a must-run dispatch; keeping them would turn the OPF into a fixed dispatch. The release
    is recorded as an assumption.
    """
    released = []
    for list_name in ("generators", "links", "storage_units", "stores"):
        df = getattr(n, list_name)
        if not len(df):
            continue
        count = 0
        if "p_set" in df.columns:
            mask = df["p_set"].notna()
            count = int(mask.sum())
            if count:
                df.loc[mask, "p_set"] = np.nan
        dyn = getattr(n, f"{list_name}_t")
        if "p_set" in dyn and not dyn["p_set"].empty:
            count = max(count, int(dyn["p_set"].shape[1]))
            dyn["p_set"] = dyn["p_set"].iloc[:, :0]
        if count:
            released.append(f"{count} {list_name}")
    if released:
        applied.assumptions.append(
            "Dataset dispatch set-points (p_set) released so the LOPF optimises dispatch: "
            + ", ".join(released)
        )


def _drop_global_constraints(n: pypsa.Network, applied: _Applied) -> None:
    """Remove dataset-level global constraints (e.g. the CO2 cap of the ac-dc-meshed example).

    They belong to the dataset's planning study. In a dispatch-only crisis run a binding emission
    cap would trade unserved energy against emissions and dominate the outcome, so they are
    removed and the removal is recorded as an assumption (never silently).
    """
    gc = n.global_constraints
    if not len(gc):
        return
    detail = ", ".join(
        f"{name} ({gc.at[name, 'type']} {gc.at[name, 'sense']} {gc.at[name, 'constant']:g})"
        for name in gc.index
    )
    n.remove("GlobalConstraint", gc.index)
    applied.assumptions.append(
        f"Dataset global constraints removed for dispatch-only crisis analysis: {detail}"
    )


def _apply_events(n: pypsa.Network, scenario: Scenario, applied: _Applied) -> None:
    h0 = scenario.horizon.start
    snaps = n.snapshots
    var_gens = set(variable_generators(n))
    applied.variable_generators = sorted(var_gens)

    loads_p = _dense(n, "Load", "p_set")
    gen_pmax = _dense(n, "Generator", "p_max_pu")
    gen_pmin = _dense(n, "Generator", "p_min_pu")
    loads_touched = gens_touched = False

    for i, ev in enumerate(scenario.events):
        mask = _window_mask(snaps, h0, getattr(ev, "window", None))
        if isinstance(ev, DemandMultiplier):
            cols = (
                list(loads_p.columns)
                if ev.buses is None
                else [ld for ld in loads_p.columns if str(n.loads.at[ld, "bus"]) in set(ev.buses)]
            )
            loads_p.loc[mask, cols] = loads_p.loc[mask, cols] * ev.value
            loads_touched = True
        elif isinstance(ev, RenewableAvailabilityMultiplier):
            cols = [
                g for g in gen_pmax.columns
                if g in var_gens and str(n.generators.at[g, "carrier"]) == ev.carrier
            ]
            gen_pmax.loc[mask, cols] = gen_pmax.loc[mask, cols] * ev.value
            gens_touched = True
        elif isinstance(ev, GeneratorOutage):
            g = ev.asset_id
            if bool(n.generators.at[g, "committable"]):
                raise _reject(
                    "unsupported_operation",
                    f"events[{i}].asset_id",
                    f"generator {g!r} is committable (unit commitment); an outage window would "
                    "conflict with its commitment constraints and is not supported",
                )
            if (gen_pmin.loc[mask, g] > 0).any():
                applied.assumptions.append(
                    f"Generator {g!r}: minimum stable output (p_min_pu > 0) lifted while outaged"
                )
            gen_pmax.loc[mask, g] = 0.0
            gen_pmin.loc[mask, g] = 0.0
            applied.outaged_generators.add(g)
            gens_touched = True
        elif isinstance(ev, LineOutage):
            list_name = "lines" if ev.component == "line" else "transformers"
            getattr(n, list_name).loc[ev.asset_id, "active"] = False
            applied.outaged_branches.add((list_name, ev.asset_id))
        elif isinstance(ev, LinkOutage):
            n.links.loc[ev.asset_id, "active"] = False
            applied.outaged_links.add(ev.asset_id)
        elif isinstance(ev, StorageState):
            su = n.storage_units
            e_nom = float(su.at[ev.asset_id, "p_nom"]) * float(su.at[ev.asset_id, "max_hours"])
            su.loc[ev.asset_id, "state_of_charge_initial"] = ev.initial_soc_fraction * e_nom
            su.loc[ev.asset_id, "cyclic_state_of_charge"] = False
            applied.assumptions.append(
                f"Storage {ev.asset_id!r}: initial state of charge set to "
                f"{ev.initial_soc_fraction:g} x {e_nom:g} MWh; cyclic SOC constraint disabled"
            )

    mit = scenario.mitigation
    if not mit.curtailment and var_gens:
        cols = [g for g in gen_pmin.columns if g in var_gens]
        gen_pmin.loc[:, cols] = gen_pmax.loc[:, cols]
        gens_touched = True
        applied.assumptions.append(
            "Curtailment disabled: variable generators must produce their full available power "
            "(p_min_pu = p_max_pu)"
        )
    if loads_touched:
        _set_dynamic(n, "loads", "p_set", loads_p)
    if gens_touched:
        _set_dynamic(n, "generators", "p_max_pu", gen_pmax)
        _set_dynamic(n, "generators", "p_min_pu", gen_pmin)

    if len(n.storage_units):
        if not mit.storage_dispatch:
            zeros = pd.DataFrame(0.0, index=snaps, columns=n.storage_units.index)
            _set_dynamic(n, "storage_units", "p_max_pu", zeros)
            _set_dynamic(n, "storage_units", "p_min_pu", zeros.copy())
            applied.assumptions.append(
                "Storage dispatch disabled: all storage units held at zero charge/discharge"
            )
            if n.storage_units.cyclic_state_of_charge.astype(bool).any():
                applied.warnings.append(
                    "With storage dispatch disabled and cyclic SOC, the reported state of charge "
                    "is any constant level the solver picks (not unique); it has no physical "
                    "meaning in this run"
                )
        cyc = n.storage_units.cyclic_state_of_charge.astype(bool)
        if cyc.any():
            applied.assumptions.append(
                f"{int(cyc.sum())} storage unit(s) use a cyclic state-of-charge constraint "
                "(SOC at the end of the horizon equals SOC before the first snapshot)"
            )

    if mit.load_shedding.enabled:
        _add_load_shedding(n, loads_p, mit.load_shedding.voll_eur_per_mwh, applied)


def _add_load_shedding(
    n: pypsa.Network, loads_p: pd.DataFrame, voll: float, applied: _Applied
) -> None:
    """One dispatchable generator per load bus, bounded by that bus's demand at each snapshot."""
    if SHED_CARRIER not in n.carriers.index:
        n.add("Carrier", SHED_CARRIER, co2_emissions=0.0, nice_name="Load shedding")
    sign = n.loads["sign"] if "sign" in n.loads.columns else pd.Series(-1.0, index=n.loads.index)
    # demand (positive = consumption) per bus
    demand = (loads_p * (-sign)).clip(lower=0.0)
    by_bus = demand.T.groupby(n.loads.bus.astype(str)).sum().T
    names, buses, p_noms, pmax = [], [], [], {}
    for bus in by_bus.columns:
        peak = float(by_bus[bus].max())
        if peak <= 0.0:
            continue
        name = f"{bus} {SHED_CARRIER}"
        if name in n.generators.index:
            raise _reject(
                "invalid_network", "dataset", f"generator name collision for {name!r}"
            )
        names.append(name)
        buses.append(bus)
        p_noms.append(peak)
        pmax[name] = by_bus[bus] / peak
        applied.shed_generators[name] = bus
    if not names:
        return
    n.add(
        "Generator",
        names,
        bus=buses,
        carrier=SHED_CARRIER,
        p_nom=p_noms,
        marginal_cost=voll,
        p_max_pu=pd.DataFrame(pmax, index=n.snapshots),
    )
    applied.assumptions.append(
        f"Load shedding modelled as one dispatchable generator per load bus ({len(names)} buses), "
        f"marginal cost = VOLL {voll:g} EUR/MWh, bounded by the bus demand at every snapshot"
    )


# --------------------------------------------------------------------------- post-processing


def _sign(n: pypsa.Network, list_name: str) -> pd.Series:
    df = getattr(n, list_name)
    if "sign" in df.columns:
        return df["sign"].astype(float)
    return pd.Series(-1.0 if list_name == "loads" else 1.0, index=df.index)


def balance_residuals(n: pypsa.Network) -> pd.DataFrame:
    """Nodal power balance residual [MW] per snapshot x bus from solved component outputs.

    ``sum(one-port injections) - sum(branch withdrawals)``; zero (to solver tolerance) when the
    nodal balance constraints hold.
    """
    res = pd.DataFrame(0.0, index=n.snapshots, columns=n.buses.index)
    for list_name in ("generators", "loads", "storage_units", "stores"):
        df = getattr(n, list_name)
        if not len(df):
            continue
        p = getattr(n, f"{list_name}_t").p.reindex(columns=df.index).fillna(0.0)
        inj = (p * _sign(n, list_name)).T.groupby(df.bus).sum().T
        res = res.add(inj.reindex(columns=res.columns, fill_value=0.0), fill_value=0.0)
    for list_name in ("lines", "transformers", "links"):
        df = getattr(n, list_name)
        if not len(df):
            continue
        dyn = getattr(n, f"{list_name}_t")
        ports = [c[3:] for c in df.columns if c.startswith("bus") and c[3:].isdigit()]
        for port in ports:
            key = f"p{port}"
            if key not in dyn or dyn[key].empty:
                continue
            buses = df[f"bus{port}"].astype(str)
            valid = buses[buses != ""].index
            flows = dyn[key].reindex(columns=valid).fillna(0.0)
            wd = flows.T.groupby(buses[valid]).sum().T
            res = res.sub(wd.reindex(columns=res.columns, fill_value=0.0), fill_value=0.0)
    return res


def _generation_metrics(n, applied, w):
    gens = n.generators
    real = [g for g in gens.index if g not in applied.shed_generators]
    shed = list(applied.shed_generators)
    p = n.generators_t.p.reindex(columns=gens.index).fillna(0.0)
    avail = _dense(n, "Generator", "p_max_pu").reindex(columns=gens.index) * gens.p_nom
    carriers = gens.carrier.astype(str)
    gen_by_carrier_mw = p[real].T.groupby(carriers[real]).sum().T
    var = [g for g in applied.variable_generators if g in real]
    curt = (avail[var] - p[var]).clip(lower=0.0) if var else pd.DataFrame(index=n.snapshots)
    curt_by_carrier_mw = curt.T.groupby(carriers[var]).sum().T if var else curt
    shed_mw = p[shed] if shed else pd.DataFrame(index=n.snapshots)
    return p, avail, real, shed, gen_by_carrier_mw, curt, curt_by_carrier_mw, shed_mw


def _branch_loading(n: pypsa.Network, applied: _Applied):
    """Per-branch rows for lines and transformers, plus the loading matrix of in-service branches.

    Loading = |p0| / (s_nom * s_max_pu) * 100, i.e. relative to the limit used in the LOPF.
    """
    rows: dict[str, list[dict]] = {"lines": [], "transformers": []}
    loadings = []
    for list_name, comp in (("lines", "Line"), ("transformers", "Transformer")):
        df = getattr(n, list_name)
        if not len(df):
            continue
        p0 = getattr(n, f"{list_name}_t").p0.reindex(columns=df.index).fillna(0.0)
        smax = _dense(n, comp, "s_max_pu").reindex(columns=df.index)
        limit = smax * df.s_nom
        for bid in df.index:
            out = (list_name, bid) in applied.outaged_branches
            flow = np.zeros(len(n.snapshots)) if out else p0[bid].to_numpy(dtype=float)
            lim = limit[bid].to_numpy(dtype=float)
            with np.errstate(divide="ignore", invalid="ignore"):
                load = np.where(lim > 0, np.abs(flow) / lim * 100.0, np.nan)
            if out:
                load = np.zeros_like(load)
            else:
                loadings.append(load)
            rows[list_name].append(
                {
                    "id": str(bid),
                    "bus0": str(df.at[bid, "bus0"]),
                    "bus1": str(df.at[bid, "bus1"]),
                    "s_nom_mva": _num(df.at[bid, "s_nom"], SERIES_DECIMALS),
                    "s_max_pu": _num(np.nanmax(smax[bid].to_numpy(dtype=float)), SERIES_DECIMALS),
                    "outaged": out,
                    "flow_mw": _series(flow),
                    "loading_pct": _series(load),
                }
            )
    arr = np.vstack(loadings) if loadings else np.zeros((0, len(n.snapshots)))
    return rows, arr


def _co2(n: pypsa.Network, p: pd.DataFrame, real: list[str], w: np.ndarray):
    if "co2_emissions" not in n.carriers.columns:
        return None
    intensity = n.carriers.co2_emissions.astype(float).fillna(0.0)
    if not (intensity.abs() > 0).any():
        return None
    gens = n.generators.loc[real]
    eff = gens.efficiency.astype(float).replace(0.0, np.nan)
    factor = gens.carrier.astype(str).map(intensity).fillna(0.0) / eff
    return float((p[real].mul(factor.fillna(0.0), axis=1).sum(axis=1).to_numpy() * w).sum())


def _postprocess(n: pypsa.Network, scenario: Scenario, applied: _Applied) -> dict:
    snaps = n.snapshots
    w = n.snapshot_weightings.generators.reindex(snaps).to_numpy(dtype=float)
    p, avail, real, shed, gen_by_c, curt, curt_by_c, shed_mw = _generation_metrics(n, applied, w)

    sign = _sign(n, "loads")
    load_mw_df = (n.loads_t.p.reindex(columns=n.loads.index).fillna(0.0) * (-sign))
    load_mw = load_mw_df.sum(axis=1).to_numpy(dtype=float)
    shed_total = shed_mw.sum(axis=1).to_numpy(dtype=float) if shed else np.zeros(len(snaps))

    total_load = float((load_mw * w).sum())
    unserved = float((shed_total * w).sum())
    shed_cost = 0.0
    if shed:
        mc = n.generators.loc[shed, "marginal_cost"].astype(float)
        shed_cost = float((shed_mw.mul(mc, axis=1).sum(axis=1).to_numpy() * w).sum())
    objective = float(n.objective) + float(getattr(n, "objective_constant", 0.0) or 0.0)

    su = n.storage_units
    if len(su):
        def su_frame(attr: str) -> pd.DataFrame:
            df = n.storage_units_t.get(attr)
            if df is None or df.empty:
                return pd.DataFrame(0.0, index=snaps, columns=su.index)
            return df.reindex(index=snaps, columns=su.index).fillna(0.0)

        su_p = su_frame("p")
        su_soc = su_frame("state_of_charge")
        su_dispatch = su_frame("p_dispatch")
        su_store = su_frame("p_store")
        su_spill = su_frame("spill")
        dis = float((su_dispatch.sum(axis=1).to_numpy() * w).sum())
        chg = float((su_store.sum(axis=1).to_numpy() * w).sum())
    else:
        su_p = su_soc = su_dispatch = su_store = su_spill = pd.DataFrame(index=snaps)
        dis = chg = 0.0

    branch_rows, loading_arr = _branch_loading(n, applied)
    if loading_arr.size and np.isfinite(loading_arr).any():
        max_loading = float(np.nanmax(loading_arr))
        mean_loading = float(np.nanmean(loading_arr))
        congested = int((np.nanmax(loading_arr, axis=1) >= CONGESTION_THRESHOLD_PCT).sum())
    else:
        max_loading = mean_loading = None
        congested = 0

    residual = balance_residuals(n)
    resid_max = float(residual.abs().to_numpy().max()) if residual.size else 0.0

    co2 = _co2(n, p, real, w)
    if co2 is None:
        applied.warnings.append(
            "Dataset carriers carry no CO2 intensities (all zero/missing): co2_emissions_t is "
            "null (data gap, not a zero-emission finding)"
        )

    prices = n.buses_t.marginal_price.reindex(columns=n.buses.index)

    curt_total = curt.sum(axis=1).to_numpy(dtype=float) if curt.shape[1] else np.zeros(len(snaps))
    shed_by_bus = {}
    for g, bus in applied.shed_generators.items():
        shed_by_bus[bus] = shed_by_bus.get(bus, 0.0) + p[g].to_numpy(dtype=float)

    md = METRIC_DECIMALS
    metrics = {
        "total_load_mwh": _num(total_load, md),
        "served_load_mwh": _num(total_load - unserved, md),
        "unserved_energy_mwh": _num(unserved, md),
        "peak_load_shed_mw": _num(float(shed_total.max()) if len(shed_total) else 0.0, md),
        "load_shed_hours": _num(float(w[shed_total > SHED_EPS_MW].sum()), md),
        "total_system_cost_eur": _num(objective, md),
        "generation_cost_eur": _num(objective - shed_cost, md),
        "load_shedding_cost_eur": _num(shed_cost, md),
        "generation_by_carrier_mwh": {
            str(c): _num(float((gen_by_c[c].to_numpy() * w).sum()), md) for c in gen_by_c.columns
        },
        "curtailment_mwh": _num(float((curt_total * w).sum()), md),
        "curtailment_by_carrier_mwh": {
            str(c): _num(float((curt_by_c[c].to_numpy() * w).sum()), md)
            for c in curt_by_c.columns
        },
        "max_line_loading_pct": _num(max_loading, md),
        "mean_line_loading_pct": _num(mean_loading, md),
        "congested_line_count": congested,
        "storage_discharge_mwh": _num(dis, md),
        "storage_charge_mwh": _num(chg, md),
        "co2_emissions_t": _num(co2, md),
        "balance_residual_max_mw": _num(resid_max, 9),
    }

    series = {
        "load_mw": _series(load_mw),
        "load_shed_mw": _series(shed_total),
        "generation_by_carrier_mw": {str(c): _series(gen_by_c[c]) for c in gen_by_c.columns},
        "storage_dispatch_mw": _series(su_p.sum(axis=1)) if len(su) else [],
        "storage_soc_mwh": _series(su_soc.sum(axis=1)) if len(su) else [],
        "curtailment_mw": _series(curt_total),
        "mean_marginal_price_eur_per_mwh": _series(prices.mean(axis=1)),
    }

    links = n.links
    link_rows = []
    if len(links):
        lp0 = n.links_t.p0.reindex(columns=links.index).fillna(0.0)
        for lid in links.index:
            out = lid in applied.outaged_links
            link_rows.append(
                {
                    "id": str(lid),
                    "bus0": str(links.at[lid, "bus0"]),
                    "bus1": str(links.at[lid, "bus1"]),
                    "p_nom_mw": _num(links.at[lid, "p_nom"], SERIES_DECIMALS),
                    "outaged": out,
                    "flow_mw": _series(np.zeros(len(snaps)) if out else lp0[lid]),
                }
            )

    zeros = np.zeros(len(snaps))
    assets = {
        "lines": branch_rows["lines"],
        "links": link_rows,
        "buses": [
            {
                "id": str(b),
                "marginal_price_eur_per_mwh": _series(prices[b]),
                "load_shed_mw": _series(shed_by_bus.get(str(b), zeros)),
            }
            for b in n.buses.index
        ],
        "generators": [
            {
                "id": str(g),
                "carrier": str(n.generators.at[g, "carrier"]),
                "bus": str(n.generators.at[g, "bus"]),
                "p_mw": _series(p[g]),
                "available_mw": _series(avail[g]),
                "outaged": g in applied.outaged_generators,
            }
            for g in real
        ],
        "storage_units": [
            {
                "id": str(s),
                "bus": str(su.at[s, "bus"]),
                "p_mw": _series(su_p[s]),
                "p_dispatch_mw": _series(su_dispatch[s]),
                "p_store_mw": _series(su_store[s]),
                "spill_mw": _series(su_spill[s]),
                "soc_mwh": _series(su_soc[s]),
            }
            for s in su.index
        ],
    }
    if len(n.transformers):
        assets["transformers"] = branch_rows["transformers"]
    return {"metrics": metrics, "series": series, "assets": assets}


# --------------------------------------------------------------------------- entry point


def _base_assumptions() -> list[str]:
    return [
        "DC linearised power flow (LOPF) — no reactive power, voltage magnitudes or losses",
        "Kirchhoff's voltage law imposed on a cycle basis with series reactances (x_pu_eff); "
        "branch active-power flow limited to s_nom x s_max_pu",
        "Perfect foresight: all snapshots of the horizon are optimised jointly in one LP",
        "Costs are short-run marginal costs from the dataset; nodal prices are LP duals of the "
        "nodal balance constraints",
        "Modeled results for scenario analysis — not a validated blackout predictor or "
        "operational forecast",
    ]


def run_scenario(
    scenario: Scenario | dict,
    network_dir: Path | str,
    *,
    progress: ProgressFn | None = None,
) -> dict:
    """Execute ``scenario`` on ``<network_dir>/network.nc`` and return a gridstorm-result/1.0.

    Raises :class:`ScenarioRejected` for invalid/unsupported scenarios; other exceptions signal
    engine errors. Infeasible optimisation problems are results (``outcome: "infeasible"``).
    """
    started_at = utc_now_iso()

    def stage(name: str) -> None:
        if progress is not None:
            progress(name)

    if not isinstance(scenario, Scenario):
        try:
            scenario = Scenario.model_validate(scenario)
        except Exception as exc:  # pydantic.ValidationError
            report = stormspec.validate(scenario, {})  # converts to schema_error issues
            raise ScenarioRejected(report.errors) from exc
    network_dir = Path(network_dir)
    ex = scenario.execution
    if ex.engine != "pypsa":
        raise _reject(
            "unsupported_operation", "execution.engine", f"this adapter runs pypsa, not {ex.engine}"
        )
    opts = ex.solver_options
    if ex.deterministic and opts.threads != 1:
        raise _reject(
            "unsupported_operation",
            "execution.solver_options.threads",
            "deterministic execution requires threads = 1 with HiGHS",
        )

    stage("loading_network")
    nc_path = network_dir / "network.nc"
    if not nc_path.exists():
        raise FileNotFoundError(f"{nc_path} not found")
    dataset_sha = stormspec.file_sha256(nc_path)
    if scenario.dataset.sha256 is not None and scenario.dataset.sha256 != dataset_sha:
        raise _reject(
            "dataset_mismatch",
            "dataset.sha256",
            f"scenario pinned network.nc sha256 {scenario.dataset.sha256}, found {dataset_sha}",
        )
    network_id = _network_id(network_dir)
    n = load_network(network_dir)
    report = stormspec.validate(scenario, network_index(n, network_id))
    if not report.valid:
        raise ScenarioRejected(report.errors, report.warnings)
    result_warnings = [f"{w.code}: {w.message}" for w in report.warnings]

    stage("applying_scenario")
    h = scenario.horizon
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        n.set_snapshots(n.snapshots[h.start : h.end])
    applied = _Applied()
    _fix_capacities(n, applied)
    _drop_global_constraints(n, applied)
    _release_setpoints(n, applied)
    _apply_events(n, scenario, applied)

    stage("building_model")
    solver_options = {
        "time_limit": float(opts.time_limit_s),
        "threads": int(opts.threads),
        "random_seed": int(ex.seed),
        "output_flag": False,
    }
    if ex.deterministic:
        solver_options["parallel"] = "off"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        n.optimize.create_model()

    stage("solving")
    t0 = time.perf_counter()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        status, condition = n.optimize.solve_model(
            solver_name="highs",
            solver_options=solver_options,
            log_to_console=False,
            io_api="direct",
        )
    wall = time.perf_counter() - t0

    stage("postprocessing")
    status = str(status)
    condition = str(condition)
    if status == "ok" and condition == "optimal":
        outcome = "feasible"
    elif condition in {"infeasible", "infeasible_or_unbounded"}:
        outcome = "infeasible"
    else:
        outcome = "error"

    # Datetime snapshots -> ISO-8601; non-temporal labels (e.g. PGLib "now") are kept verbatim,
    # never parsed (pd.Timestamp("now") would invent the current time).
    snapshots_iso = [
        s.isoformat() if isinstance(s, pd.Timestamp) else str(s) for s in n.snapshots
    ]
    weights = _series(n.snapshot_weightings.generators.reindex(n.snapshots), METRIC_DECIMALS)
    result: dict[str, Any] = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "scenario_id": scenario.id,
        "scenario_hash": stormspec.scenario_hash(scenario),
        "network_id": network_id,
        "provenance": "modeled",
        "engine": {"name": "pypsa", "version": pypsa.__version__, "formulation": "lopf"},
        "solver": {
            "name": "highs",
            "version": _version("highspy"),
            "status": status if status in {"ok", "warning"} else "error",
            "termination_condition": condition,
            "objective_eur": _num(n.objective, METRIC_DECIMALS) if outcome == "feasible" else None,
            "wall_time_s": round(wall, 3),
        },
        "outcome": outcome,
        "snapshots": snapshots_iso,
        "snapshot_weightings_h": weights,
    }
    if outcome == "feasible":
        result.update(_postprocess(n, scenario, applied))
    else:
        result.update({"metrics": None, "series": None, "assets": None})
        if outcome == "infeasible":
            result_warnings.append(
                "The optimisation problem is infeasible: no dispatch satisfies demand and network "
                "limits under this scenario (enable load shedding to quantify unserved energy). "
                "No numbers are reported."
            )
        else:
            result_warnings.append(
                f"Solver finished with status {status!r}, termination {condition!r}: "
                "no valid solution, no numbers are reported."
            )
    result["assumptions"] = _base_assumptions() + applied.assumptions + list(
        scenario.assumptions
    )
    result["warnings"] = result_warnings + applied.warnings

    manifest = ExecutionManifest(
        scenario_hash=result["scenario_hash"],
        dataset_sha256=dataset_sha,
        engine_name="pypsa",
        engine_version=pypsa.__version__,
        solver_name="highs",
        solver_version=_version("highspy"),
        solver_options=solver_options,
        package_versions={
            k: v
            for k in ("pypsa", "linopy", "highspy", "numpy", "pandas", "xarray", "stormspec")
            if (v := _version(k))
        },
        started_at=started_at,
        finished_at=utc_now_iso(),
        result_sha256=stormspec.result_sha256(result),
        git_sha=detect_git_sha(network_dir),
    )
    result["manifest"] = manifest.model_dump(mode="json")
    stage("done")
    return result
