"""Build a PyPSA network from a PGLib-OPF / MATPOWER case with GridStorm asset ids.

Asset ids (contract): buses ``bus-<BUS_I>``, branches ``branch-<1-based row in mpc.branch>``,
generators ``gen-<1-based row in mpc.gen>``, loads ``load-<BUS_I>``; bus shunts (Gs/Bs) become
PyPSA ShuntImpedances ``shunt-<BUS_I>`` (not part of canonical-grid/1.0, used only by AC power flow).

Unit conversion (MATPOWER per-unit on ``baseMVA`` and bus ``baseKV`` -> PyPSA):

* Lines (same baseKV at both ends, ratio in {0, 1}, shift 0):
  ``x_ohm = x_pu * baseKV**2 / baseMVA``, ``r_ohm`` likewise, ``b_siemens = b_pu * baseMVA / baseKV**2``.
  PyPSA then computes ``x_pu(1 MVA) = x_ohm / v_nom**2 = x_pu / baseMVA`` — identical impedance.
* Transformers (ratio not in {0, 1}, or shift != 0, or different baseKV at the two ends):
  PyPSA transformer impedances are per unit on ``s_nom``, so ``x = x_pu * s_nom / baseMVA``,
  ``r`` likewise, ``b = b_pu * baseMVA / s_nom``; ``tap_ratio = ratio`` (1 if 0) on bus0 (= MATPOWER
  from-bus, ``tap_side = 0``), ``phase_shift = angle`` (degrees, same sign convention as MATPOWER
  makeYbus/makeBdc), ``model = "pi"`` (MATPOWER uses the pi model).
* ``RATE_A = 0`` means "no limit" in MATPOWER. PyPSA needs a finite ``s_nom`` so we set
  ``UNLIMITED_RATING_MVA`` in ``network.nc``, emit ``s_nom_mva = null`` in canonical.json and list the
  branch ids in the quality flags. No limit is ever invented.
* Generators: ``p_nom = Pmax``, ``p_min_pu = Pmin / Pmax`` (0 if Pmax = 0), ``p_set = Pg``,
  ``q_set = Qg``; ``status = 0`` -> ``active = False``. Control: first generator at the reference bus
  (type 3) is ``Slack``; generators at PV buses ``PV``; others ``PQ``.
* Costs: polynomial (model 2) ``c2*P^2 + c1*P + c0``. PyPSA's LOPF here is kept linear, so the
  marginal cost is the secant slope over ``[0, Pmax]``: ``c1 + c2 * Pmax`` (exact when c2 = 0; the
  fixed cost c0 is dropped). Labelled ``modeled``. Piecewise-linear costs (model 1) are rejected.
* Branch angle limits (angmin/angmax), RATE_B/RATE_C and bus voltage limits are not used by PyPSA's
  linear model; voltage limits are stored as ``v_mag_pu_min/max``.
* PGLib cases are single-period: one snapshot (PyPSA default ``"now"``, weighting 1 h).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx
import pandas as pd
import pypsa

from network_import.matpower import MatpowerCase

UNLIMITED_RATING_MVA = 1.0e5

# PGLib generator fuel codes (EIA-860 energy source codes used in PGLib comments).
FUEL_NAMES = {
    "NG": "Natural gas",
    "COW": "Coal",
    "PEL": "Petroleum (liquid)",
    "NUC": "Nuclear",
    "HYD": "Hydro",
    "WND": "Wind",
    "SUN": "Solar",
    "SYNC": "Synchronous condenser",
    "UNKNOWN": "Unknown fuel (no PGLib label)",
}


@dataclass
class BuildReport:
    n_lines: int = 0
    n_transformers: int = 0
    unlimited_branches: list[str] = field(default_factory=list)
    out_of_service_branches: list[str] = field(default_factory=list)
    out_of_service_gens: list[str] = field(default_factory=list)
    isolated_buses: list[str] = field(default_factory=list)
    quadratic_cost_gens: list[str] = field(default_factory=list)
    nonzero_gs_buses: list[str] = field(default_factory=list)
    voltage_change_lines: list[str] = field(default_factory=list)


def bus_id(i: float) -> str:
    return f"bus-{int(i)}"


def _gencost_linear(row: list[float], pmax: float) -> tuple[float, float]:
    """Return (secant marginal cost, c2) for a polynomial cost row."""
    model = int(row[0])
    if model != 2:
        raise ValueError(f"unsupported MATPOWER cost model {model} (only polynomial model 2)")
    ncost = int(row[3])
    coeffs = row[4 : 4 + ncost]  # highest order first
    if len(coeffs) != ncost:
        raise ValueError(f"gencost row has {len(coeffs)} coefficients, expected {ncost}")
    if ncost > 3:
        raise ValueError(f"polynomial cost of degree {ncost - 1} not supported")
    padded = [0.0] * (3 - ncost) + list(coeffs)  # c2, c1, c0
    c2, c1 = padded[0], padded[1]
    return c1 + c2 * max(pmax, 0.0), c2


def build_network(case: MatpowerCase, name: str) -> tuple[pypsa.Network, BuildReport]:
    rep = BuildReport()
    n = pypsa.Network(name=name)
    base = case.base_mva

    bus_kv: dict[str, float] = {}
    for idx, b in enumerate(case.bus):
        bid = bus_id(b["bus_i"])
        kv = b["base_kv"]
        if kv <= 0:
            raise ValueError(f"{bid}: baseKV {kv} <= 0; cannot convert impedances")
        bus_kv[bid] = kv
        if int(b["type"]) == 4:
            rep.isolated_buses.append(bid)
        n.add("Bus", bid, v_nom=kv, carrier="AC",
              v_mag_pu_min=b["vmin"], v_mag_pu_max=b["vmax"], v_mag_pu_set=b["vm"])
        if case.bus_name:
            n.c.buses.static.loc[bid, "location"] = case.bus_name[idx]
        if b["pd"] != 0 or b["qd"] != 0:
            n.add("Load", f"load-{int(b['bus_i'])}", bus=bid, p_set=b["pd"], q_set=b["qd"],
                  carrier="AC")
        if b["gs"] != 0 or b["bs"] != 0:
            # MATPOWER Gs/Bs are MW/MVAr at V = 1 p.u.; PyPSA shunt g/b in siemens: P = g * V_kV^2.
            n.add("ShuntImpedance", f"shunt-{int(b['bus_i'])}", bus=bid,
                  g=b["gs"] / kv**2, b=b["bs"] / kv**2)
            if b["gs"] != 0:
                rep.nonzero_gs_buses.append(bid)

    ref_buses = {bus_id(b["bus_i"]) for b in case.bus if int(b["type"]) == 3}
    pv_buses = {bus_id(b["bus_i"]) for b in case.bus if int(b["type"]) == 2}

    for row, br in enumerate(case.branch, start=1):
        bid = f"branch-{row}"
        b0, b1 = bus_id(br["fbus"]), bus_id(br["tbus"])
        if b0 not in bus_kv or b1 not in bus_kv:
            raise ValueError(f"{bid} references unknown bus")
        rate = br["rate_a"]
        if rate < 0:
            raise ValueError(f"{bid}: negative RATE_A {rate}")
        if rate == 0:
            rep.unlimited_branches.append(bid)
            rate = UNLIMITED_RATING_MVA
        active = int(br["status"]) != 0
        if not active:
            rep.out_of_service_branches.append(bid)
        ratio, shift = br["ratio"], br["angle"]
        is_trafo = (ratio not in (0.0, 1.0)) or shift != 0.0 or bus_kv[b0] != bus_kv[b1]
        if is_trafo:
            rep.n_transformers += 1
            n.add("Transformer", bid, bus0=b0, bus1=b1, model="pi", s_nom=rate,
                  x=br["x"] * rate / base, r=br["r"] * rate / base, b=br["b"] * base / rate,
                  g=0.0, tap_ratio=ratio if ratio != 0 else 1.0, tap_side=0,
                  phase_shift=shift, active=active)
        else:
            rep.n_lines += 1
            kv = bus_kv[b0]
            n.add("Line", bid, bus0=b0, bus1=b1, s_nom=rate,
                  x=br["x"] * kv**2 / base, r=br["r"] * kv**2 / base, b=br["b"] * base / kv**2,
                  g=0.0, length=0.0, num_parallel=1.0, carrier="AC", active=active)

    slack_assigned: set[str] = set()
    carriers: set[str] = {"AC"}
    for row, g in enumerate(case.gen, start=1):
        gid = f"gen-{row}"
        bid = bus_id(g["bus"])
        if bid not in bus_kv:
            raise ValueError(f"{gid} references unknown bus")
        pmax, pmin = g["pmax"], g["pmin"]
        if pmax < 0:
            raise ValueError(f"{gid}: negative Pmax {pmax} is not supported")
        comment = case.gen_comments[row - 1].split()
        carrier = comment[0] if comment else "UNKNOWN"
        carriers.add(carrier)
        if bid in ref_buses and bid not in slack_assigned:
            control = "Slack"
            slack_assigned.add(bid)
        elif bid in pv_buses or bid in ref_buses:
            control = "PV"
        else:
            control = "PQ"
        if case.gencost:
            mc, c2 = _gencost_linear(case.gencost[row - 1], pmax)
            if c2 != 0:
                rep.quadratic_cost_gens.append(gid)
        else:
            mc = 0.0
        active = int(g["status"]) != 0
        if not active:
            rep.out_of_service_gens.append(gid)
        n.add("Generator", gid, bus=bid, carrier=carrier, control=control, p_nom=pmax,
              p_min_pu=(pmin / pmax) if pmax > 0 else 0.0, p_max_pu=1.0, p_set=g["pg"],
              q_set=g["qg"], marginal_cost=mc, active=active)

    for car in sorted(carriers):
        n.add("Carrier", car, nice_name=FUEL_NAMES.get(car, car) if car != "AC" else "AC")
    return n, rep


def schematic_layout(n: pypsa.Network, decimals: int = 4) -> pd.DataFrame:
    """Deterministic Kamada-Kawai layout of the bus graph (parallel branches collapsed).

    Kamada-Kawai starts from ``circular_layout`` (no randomness); coordinates are rounded so
    results are stable across platforms. Returns a DataFrame with columns ``x``, ``y``.
    """
    g = nx.Graph()
    g.add_nodes_from(sorted(n.c.buses.static.index))
    for comp in (n.c.lines, n.c.transformers, n.c.links):
        for b0, b1 in zip(comp.static.bus0, comp.static.bus1, strict=True):
            g.add_edge(b0, b1)
    pos = nx.kamada_kawai_layout(g, scale=1.0)
    return pd.DataFrame(
        {"x": [round(float(pos[b][0]), decimals) for b in n.c.buses.static.index],
         "y": [round(float(pos[b][1]), decimals) for b in n.c.buses.static.index]},
        index=n.c.buses.static.index,
    )
