"""Expected model inputs rebuilt independently from ``network.nc`` + a StormSpec scenario.

This module deliberately does NOT import ``gridstorm_pypsa``: PyPSA is used only as a file reader
(``pypsa.Network`` and ``get_switchable_as_dense``). Scenario semantics follow the StormSpec
contract (docs/architecture/contracts.md §3): windows are absolute snapshot indices
``[start, end)``, ``window: null`` = whole horizon, capacities are the dataset nominal values
(dispatch-only), outaged generators have zero availability inside their window.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import pypsa
from stormspec import Scenario

from paths import NETWORKS


@dataclass
class Gen:
    bus: str
    carrier: str
    p_nom: float
    pmax_pu: np.ndarray
    pmin_pu: np.ndarray
    mc: float
    efficiency: float
    variable: bool
    outaged: bool


@dataclass
class Branch:
    bus0: str
    bus1: str
    s_nom: float
    s_max_pu: np.ndarray
    outaged: bool


@dataclass
class Link:
    bus0: str
    bus1: str
    p_nom: float
    pmin_pu: np.ndarray
    pmax_pu: np.ndarray
    efficiency: np.ndarray
    mc: float
    extra_ports: list[str]
    outaged: bool


@dataclass
class StorageUnit:
    bus: str
    p_nom: float
    max_hours: float
    eff_store: float
    eff_dispatch: float
    standing_loss: np.ndarray
    inflow: np.ndarray
    pmax_pu: np.ndarray
    pmin_pu: np.ndarray
    cyclic: bool
    soc_initial: float
    mc: float
    mc_storage: float


@dataclass
class Expected:
    network_id: str
    snapshots: list[str]
    w_gen: np.ndarray
    w_obj: np.ndarray
    w_store: np.ndarray
    load_by_bus: pd.DataFrame  # snapshot x bus, demand after multipliers (MW, consumption > 0)
    gens: dict[str, Gen]
    branches: dict[str, dict[str, Branch]]  # "lines" | "transformers" -> id -> Branch
    links: dict[str, Link]
    storage: dict[str, StorageUnit]
    store_buses: set[str]
    store_mc_max: float
    carrier_co2: dict[str, float]
    shed_enabled: bool
    voll: float
    curtailment: bool
    storage_dispatch: bool
    mc_quadratic_max: float
    notes: list[str] = field(default_factory=list)


@lru_cache(maxsize=8)
def _network(network_id: str) -> pypsa.Network:
    logging.getLogger("pypsa").setLevel(logging.ERROR)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return pypsa.Network(str(Path(NETWORKS) / network_id / "network.nc"))


def _mask(k: int, h0: int, window) -> np.ndarray:
    if window is None:
        return np.ones(k, dtype=bool)
    idx = np.arange(h0, h0 + k)
    return (idx >= window.start) & (idx < window.end)


def _dense(n: pypsa.Network, comp: str, attr: str, snaps: pd.Index) -> pd.DataFrame:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return n.get_switchable_as_dense(comp, attr).loc[snaps]


def _iso(s) -> str:
    return s.isoformat() if isinstance(s, pd.Timestamp) else str(s)


def build(scenario: Scenario) -> Expected:
    n = _network(scenario.dataset.network_id)
    h = scenario.horizon
    snaps = n.snapshots[h.start : h.end]
    k = len(snaps)
    sw = n.snapshot_weightings.loc[snaps]
    mit = scenario.mitigation

    # ---- loads (demand multipliers multiply p_set; buses filter on the load's bus)
    p_set = _dense(n, "Load", "p_set", snaps).astype(float)
    sign = n.loads["sign"].astype(float) if "sign" in n.loads else pd.Series(-1.0, n.loads.index)
    demand = p_set * (-sign)
    load_bus = n.loads.bus.astype(str)
    # ---- generators
    gens_df = n.generators
    pmax = _dense(n, "Generator", "p_max_pu", snaps).astype(float)
    pmin = _dense(n, "Generator", "p_min_pu", snaps).astype(float)
    variable = set(map(str, n.generators_t.p_max_pu.columns))
    outaged_gens: set[str] = set()
    outaged_branches: set[tuple[str, str]] = set()
    outaged_links: set[str] = set()
    soc_override: dict[str, float] = {}
    for ev in scenario.events:
        m = _mask(k, h.start, getattr(ev, "window", None))
        if ev.type == "demand_multiplier":
            cols = [ld for ld in demand.columns if ev.buses is None or load_bus[ld] in ev.buses]
            demand.loc[m, cols] *= ev.value
        elif ev.type == "renewable_availability_multiplier":
            cols = [
                g
                for g in pmax.columns
                if g in variable and str(gens_df.at[g, "carrier"]) == ev.carrier
            ]
            pmax.loc[m, cols] *= ev.value
        elif ev.type == "generator_outage":
            pmax.loc[m, ev.asset_id] = 0.0
            pmin.loc[m, ev.asset_id] = 0.0
            outaged_gens.add(ev.asset_id)
        elif ev.type == "line_outage":
            outaged_branches.add(
                ("lines" if ev.component == "line" else "transformers", ev.asset_id)
            )
        elif ev.type == "link_outage":
            outaged_links.add(ev.asset_id)
        elif ev.type == "storage_state":
            su = n.storage_units
            e_nom = float(su.at[ev.asset_id, "p_nom"]) * float(su.at[ev.asset_id, "max_hours"])
            soc_override[ev.asset_id] = ev.initial_soc_fraction * e_nom
    if not mit.curtailment:
        for g in variable:
            pmin[g] = pmax[g]
    load_by_bus = demand.T.groupby(load_bus).sum().T

    mcq = 0.0
    if "marginal_cost_quadratic" in gens_df:
        mcq = float(gens_df.marginal_cost_quadratic.abs().max() or 0.0)
    if not n.generators_t.marginal_cost.empty:
        raise NotImplementedError("time-varying generator marginal cost not modelled by harness")
    gens = {
        str(g): Gen(
            bus=str(gens_df.at[g, "bus"]),
            carrier=str(gens_df.at[g, "carrier"]),
            p_nom=float(gens_df.at[g, "p_nom"]),
            pmax_pu=pmax[g].to_numpy(float),
            pmin_pu=pmin[g].to_numpy(float),
            mc=float(gens_df.at[g, "marginal_cost"]),
            efficiency=float(gens_df.at[g, "efficiency"]),
            variable=str(g) in variable,
            outaged=str(g) in outaged_gens,
        )
        for g in gens_df.index
    }

    branches: dict[str, dict[str, Branch]] = {"lines": {}, "transformers": {}}
    for list_name, comp in (("lines", "Line"), ("transformers", "Transformer")):
        df = getattr(n, list_name)
        if not len(df):
            continue
        smax = _dense(n, comp, "s_max_pu", snaps)
        for b in df.index:
            branches[list_name][str(b)] = Branch(
                bus0=str(df.at[b, "bus0"]),
                bus1=str(df.at[b, "bus1"]),
                s_nom=float(df.at[b, "s_nom"]),
                s_max_pu=smax[b].to_numpy(float),
                outaged=(list_name, str(b)) in outaged_branches,
            )

    links: dict[str, Link] = {}
    if len(n.links):
        lmin = _dense(n, "Link", "p_min_pu", snaps)
        lmax = _dense(n, "Link", "p_max_pu", snaps)
        leff = _dense(n, "Link", "efficiency", snaps)
        extra = [
            c for c in n.links.columns if c.startswith("bus") and c[3:].isdigit() and c[3:] > "1"
        ]
        for lk in n.links.index:
            links[str(lk)] = Link(
                bus0=str(n.links.at[lk, "bus0"]),
                bus1=str(n.links.at[lk, "bus1"]),
                p_nom=float(n.links.at[lk, "p_nom"]),
                pmin_pu=lmin[lk].to_numpy(float),
                pmax_pu=lmax[lk].to_numpy(float),
                efficiency=leff[lk].to_numpy(float),
                mc=float(n.links.at[lk, "marginal_cost"]),
                extra_ports=[str(n.links.at[lk, c]) for c in extra if str(n.links.at[lk, c])],
                outaged=str(lk) in outaged_links,
            )

    storage: dict[str, StorageUnit] = {}
    su = n.storage_units
    if len(su):
        s_pmax = _dense(n, "StorageUnit", "p_max_pu", snaps)
        s_pmin = _dense(n, "StorageUnit", "p_min_pu", snaps)
        s_inflow = _dense(n, "StorageUnit", "inflow", snaps)
        s_loss = _dense(n, "StorageUnit", "standing_loss", snaps)
        for s in su.index:
            off = not mit.storage_dispatch
            storage[str(s)] = StorageUnit(
                bus=str(su.at[s, "bus"]),
                p_nom=float(su.at[s, "p_nom"]),
                max_hours=float(su.at[s, "max_hours"]),
                eff_store=float(su.at[s, "efficiency_store"]),
                eff_dispatch=float(su.at[s, "efficiency_dispatch"]),
                standing_loss=s_loss[s].to_numpy(float),
                inflow=s_inflow[s].to_numpy(float),
                pmax_pu=np.zeros(k) if off else s_pmax[s].to_numpy(float),
                pmin_pu=np.zeros(k) if off else s_pmin[s].to_numpy(float),
                cyclic=bool(su.at[s, "cyclic_state_of_charge"]) and str(s) not in soc_override,
                soc_initial=soc_override.get(str(s), float(su.at[s, "state_of_charge_initial"])),
                mc=float(su.at[s, "marginal_cost"]),
                mc_storage=float(su.at[s, "marginal_cost_storage"])
                if "marginal_cost_storage" in su
                else 0.0,
            )

    store_mc = float(n.stores.marginal_cost.abs().max()) if len(n.stores) else 0.0
    co2 = {}
    if "co2_emissions" in n.carriers:
        co2 = {str(c): float(v) for c, v in n.carriers.co2_emissions.fillna(0.0).items()}
    return Expected(
        network_id=scenario.dataset.network_id,
        snapshots=[_iso(s) for s in snaps],
        w_gen=sw.generators.to_numpy(float),
        w_obj=sw.objective.to_numpy(float),
        w_store=sw.stores.to_numpy(float),
        load_by_bus=load_by_bus,
        gens=gens,
        branches=branches,
        links=links,
        storage=storage,
        store_buses={str(b) for b in n.stores.bus} if len(n.stores) else set(),
        store_mc_max=store_mc,
        carrier_co2=co2,
        shed_enabled=mit.load_shedding.enabled,
        voll=float(mit.load_shedding.voll_eur_per_mwh),
        curtailment=mit.curtailment,
        storage_dispatch=mit.storage_dispatch,
        mc_quadratic_max=mcq,
    )
