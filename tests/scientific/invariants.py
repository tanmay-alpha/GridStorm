"""Independent scientific invariants of a PyPSA ``gridstorm-result/1.0`` document.

Every check recomputes a reported quantity from the result's own primitive series/assets and from
the model inputs rebuilt by :mod:`netmodel` (never from ``gridstorm_pypsa`` post-processing).

Tolerances are derived from the documented rounding of the result (contract §4 / runner):
series and asset values are rounded to 4 decimals (|error| <= 5e-5), metrics to 6 decimals
(|error| <= 5e-7). A sum of ``m`` rounded terms therefore carries at most ``m * 5e-5``. On top
of rounding, solver feasibility slack of ``1e-6`` relative (min 1e-5 MW absolute) is allowed for
bound/balance constraints (HiGHS default primal feasibility tolerance is 1e-7 on the scaled LP).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from netmodel import Expected

SER = 5e-5  # half unit of the 4th decimal (series / asset values)
MET = 5e-7  # half unit of the 6th decimal (metrics)
SOLVER_ABS = 1e-5  # MW
SOLVER_REL = 1e-6
CONGESTION_THRESHOLD_PCT = 99.9  # contract §4: congested = loading >= 99.9 % at any snapshot
SHED_EPS_MW = 1e-3  # load_shed_hours counts snapshots with shed > 1e-3 MW
BALANCE_RESIDUAL_LIMIT_MW = 1e-3  # metric balance_residual_max_mw must be ~0 (contract §4)
NO_CO2_WARNING = "co2_emissions_t is null (data gap, not a zero-emission finding)"

CHECKS = (
    "outcome_mapping",
    "snapshots_weights",
    "demand_multipliers",
    "energy_accounting",
    "power_balance",
    "generator_limits",
    "branch_limits",
    "storage",
    "outage_events",
    "objective",
    "co2",
)


def a(x) -> np.ndarray:
    return np.asarray([np.nan if v is None else v for v in x], dtype=float)


@dataclass
class Outcome:
    status: str = "pass"  # pass | fail | skip | n/a
    max_dev: float = 0.0  # largest |observed - expected| over compared values
    worst_ratio: float = 0.0  # largest dev / tol (<= 1 passes)
    compared: int = 0
    messages: list[str] = field(default_factory=list)


class Report:
    def __init__(self, label: str) -> None:
        self.label = label
        self.checks: dict[str, Outcome] = {}
        self.facts: dict[str, object] = {}

    def _o(self, name: str) -> Outcome:
        return self.checks.setdefault(name, Outcome())

    def compare(self, name: str, what: str, observed, expected, tol) -> None:
        o = self._o(name)
        obs = np.atleast_1d(np.asarray(observed, dtype=float))
        exp = np.atleast_1d(np.asarray(expected, dtype=float))
        tol = np.broadcast_to(
            np.asarray(tol, dtype=float), np.broadcast_shapes(obs.shape, exp.shape)
        )
        nan_mismatch = np.isnan(obs) != np.isnan(exp)
        with np.errstate(invalid="ignore"):
            dev = np.where(np.isnan(obs) & np.isnan(exp), 0.0, np.abs(obs - exp))
        dev = np.where(nan_mismatch | np.isinf(obs) | np.isinf(exp), np.inf, dev)
        o.compared += int(dev.size)
        if dev.size:
            o.max_dev = max(o.max_dev, float(np.nanmax(np.where(np.isinf(dev), 0, dev))))
            o.worst_ratio = max(o.worst_ratio, float(np.max(dev / np.maximum(tol, 1e-300))))
        bad = np.flatnonzero(dev.ravel() > tol.ravel())
        if bad.size:
            i = int(bad[0])
            o.status = "fail"
            o.messages.append(
                f"{what}: {bad.size} value(s) off; first at flat index {i}: observed "
                f"{obs.ravel()[i % obs.size]!r}, expected {exp.ravel()[i % exp.size]!r}, "
                f"tol {tol.ravel()[i]:.3g}"
            )

    def bound(self, name: str, what: str, value, upper, tol) -> None:
        """value <= upper + tol (elementwise)."""
        v = np.atleast_1d(np.asarray(value, dtype=float))
        u = np.broadcast_to(np.asarray(upper, dtype=float), v.shape)
        t = np.broadcast_to(np.asarray(tol, dtype=float), v.shape)
        o = self._o(name)
        o.compared += int(v.size)
        excess = v - u
        if v.size:
            o.worst_ratio = max(o.worst_ratio, float(np.max(np.maximum(excess, 0) / t)))
        bad = np.flatnonzero(~np.isfinite(v) | ~np.isfinite(u) | (excess > t))
        if bad.size:
            i = int(bad[0])
            o.status = "fail"
            o.messages.append(
                f"{what}: {bad.size} value(s) exceed bound; first at index {i}: {v[i]!r} > "
                f"{u[i]!r} (+tol {t[i]:.3g})"
            )

    def require(self, name: str, cond: bool, msg: str) -> None:
        o = self._o(name)
        o.compared += 1
        if not cond:
            o.status = "fail"
            o.messages.append(msg)

    def skip(self, name: str, reason: str, status: str = "skip") -> None:
        o = self._o(name)
        if o.status == "pass" and o.compared == 0:
            o.status = status
        o.messages.append(reason)

    def failures(self) -> dict[str, list[str]]:
        return {k: v.messages for k, v in self.checks.items() if v.status == "fail"}


def _tol(mag, terms: int = 1) -> np.ndarray:
    mag = np.abs(np.asarray(mag, dtype=float))
    return terms * SER + np.maximum(SOLVER_ABS, SOLVER_REL * mag)


# ------------------------------------------------------------------------------------- checks


def check_outcome_mapping(res: dict, rep: Report) -> None:
    name = "outcome_mapping"
    s = res["solver"]
    if s["status"] == "ok" and s["termination_condition"] == "optimal":
        want = "feasible"
    elif s["termination_condition"] in {"infeasible", "infeasible_or_unbounded"}:
        want = "infeasible"
    else:
        want = "error"
    rep.require(
        name, res["outcome"] == want, f"outcome {res['outcome']!r} but solver {s} -> {want}"
    )
    rep.require(name, s["status"] in {"ok", "warning", "error"}, f"solver.status {s['status']!r}")
    if res["outcome"] == "feasible":
        rep.require(name, s["objective_eur"] is not None, "feasible result without objective")
        for key in ("metrics", "series", "assets"):
            rep.require(name, isinstance(res.get(key), dict), f"feasible result missing {key}")
    else:
        rep.require(name, s["objective_eur"] is None, "non-feasible result reports an objective")
        for key in ("metrics", "series", "assets"):
            rep.require(name, res.get(key) is None, f"non-feasible result reports {key}")


def check_snapshots_weights(res: dict, exp: Expected, rep: Report) -> None:
    name = "snapshots_weights"
    rep.require(
        name,
        res["snapshots"] == exp.snapshots,
        f"snapshots {res['snapshots'][:3]}… != network horizon {exp.snapshots[:3]}…",
    )
    rep.compare(name, "snapshot_weightings_h", a(res["snapshot_weightings_h"]), exp.w_gen, MET)
    rep.facts["weights_h"] = sorted(set(map(float, exp.w_gen)))
    if not np.array_equal(exp.w_obj, exp.w_gen):
        rep.facts["note_weights"] = "objective weighting differs from generator weighting"


def check_demand_multipliers(res: dict, exp: Expected, rep: Report) -> None:
    want = exp.load_by_bus.sum(axis=1).to_numpy(float)
    rep.compare(
        "demand_multipliers", "series.load_mw", a(res["series"]["load_mw"]), want, _tol(want)
    )


def check_energy_accounting(res: dict, exp: Expected, rep: Report) -> None:
    name = "energy_accounting"
    m, s, assets = res["metrics"], res["series"], res["assets"]
    w = exp.w_gen
    sw = float(w.sum())
    k = len(w)

    load = a(s["load_mw"])
    shed = a(s["load_shed_mw"])
    rep.compare(
        name, "total_load_mwh=Σ load·w", m["total_load_mwh"], (load * w).sum(), sw * SER + MET
    )
    rep.compare(
        name,
        "unserved_energy_mwh=Σ shed·w",
        m["unserved_energy_mwh"],
        (shed * w).sum(),
        sw * SER + MET,
    )
    rep.compare(
        name,
        "served_load_mwh=total-unserved",
        m["served_load_mwh"],
        m["total_load_mwh"] - m["unserved_energy_mwh"],
        3 * MET,
    )
    rep.compare(name, "peak_load_shed_mw", m["peak_load_shed_mw"], shed.max(), SER + MET)
    clear = np.abs(shed - SHED_EPS_MW) > SER  # skip snapshots on the rounding boundary
    rep.compare(
        name,
        "load_shed_hours=Σ w[shed>1e-3]",
        m["load_shed_hours"],
        float(w[(shed > SHED_EPS_MW) & clear].sum()),
        float(w[~clear].sum()) + MET,
    )
    bus_shed = np.sum([a(b["load_shed_mw"]) for b in assets["buses"]], axis=0)
    rep.compare(
        name, "series.load_shed_mw=Σ bus shed", shed, bus_shed, _tol(shed, len(assets["buses"]) + 1)
    )

    by_c: dict[str, list[np.ndarray]] = {}
    for g in assets["generators"]:
        by_c.setdefault(g["carrier"], []).append(a(g["p_mw"]))
    rep.require(
        name,
        set(by_c) == set(s["generation_by_carrier_mw"]) == set(m["generation_by_carrier_mwh"]),
        "carrier sets differ between assets, series and metrics",
    )
    for c, rows in by_c.items():
        ser = a(s["generation_by_carrier_mw"].get(c, [np.nan] * k))
        rep.compare(
            name, f"series gen[{c}]=Σ asset p", ser, np.sum(rows, axis=0), _tol(ser, len(rows) + 1)
        )
        rep.compare(
            name,
            f"generation_by_carrier_mwh[{c}]=Σ series·w",
            m["generation_by_carrier_mwh"].get(c, np.nan),
            (ser * w).sum(),
            sw * SER + MET + SOLVER_REL * abs((ser * w).sum()),
        )

    # curtailment = Σ over variable generators of (available - p)+, weighted
    curt_c: dict[str, np.ndarray] = {}
    for g in assets["generators"]:
        if exp.gens[g["id"]].variable:
            c = g["carrier"]
            curt_c[c] = curt_c.get(c, 0) + np.clip(a(g["available_mw"]) - a(g["p_mw"]), 0, None)
    rep.require(
        name,
        set(curt_c) == set(m["curtailment_by_carrier_mwh"]),
        f"curtailment carriers {sorted(m['curtailment_by_carrier_mwh'])} != variable "
        f"carriers {sorted(curt_c)}",
    )
    nvar = max(1, sum(g.variable for g in exp.gens.values()))
    total_curt = np.zeros(k)
    for c, arr in curt_c.items():
        total_curt = total_curt + arr
        rep.compare(
            name,
            f"curtailment_by_carrier_mwh[{c}]",
            m["curtailment_by_carrier_mwh"].get(c, np.nan),
            (arr * w).sum(),
            2 * nvar * sw * SER + MET,
        )
    rep.compare(
        name, "series.curtailment_mw", a(s["curtailment_mw"]), total_curt, 2 * nvar * SER + SER
    )
    rep.compare(
        name,
        "curtailment_mwh",
        m["curtailment_mwh"],
        (total_curt * w).sum(),
        2 * nvar * sw * SER + MET,
    )

    sus = assets["storage_units"]
    if sus:
        ns = len(sus)
        p = np.sum([a(x["p_mw"]) for x in sus], axis=0)
        soc = np.sum([a(x["soc_mwh"]) for x in sus], axis=0)
        dis = np.sum([a(x["p_dispatch_mw"]) for x in sus], axis=0)
        chg = np.sum([a(x["p_store_mw"]) for x in sus], axis=0)
        rep.compare(
            name,
            "series.storage_dispatch_mw=Σ su p",
            a(s["storage_dispatch_mw"]),
            p,
            _tol(p, ns + 1),
        )
        rep.compare(
            name, "series.storage_soc_mwh=Σ su soc", a(s["storage_soc_mwh"]), soc, _tol(soc, ns + 1)
        )
        rep.compare(
            name,
            "storage_discharge_mwh",
            m["storage_discharge_mwh"],
            (dis * w).sum(),
            ns * sw * SER + MET,
        )
        rep.compare(
            name,
            "storage_charge_mwh",
            m["storage_charge_mwh"],
            (chg * w).sum(),
            ns * sw * SER + MET,
        )
    else:
        rep.compare(name, "storage_discharge_mwh (no units)", m["storage_discharge_mwh"], 0.0, MET)
        rep.compare(name, "storage_charge_mwh (no units)", m["storage_charge_mwh"], 0.0, MET)


def check_power_balance(res: dict, exp: Expected, rep: Report) -> None:
    """Nodal balance per bus and snapshot from asset outputs; system balance = Σ over buses."""
    name = "power_balance"
    assets = res["assets"]
    k = len(exp.w_gen)
    inj: dict[str, np.ndarray] = {b["id"]: np.zeros(k) for b in assets["buses"]}
    terms: dict[str, int] = dict.fromkeys(inj, 0)
    mag: dict[str, np.ndarray] = {b: np.zeros(k) for b in inj}

    def add(bus: str, x: np.ndarray) -> None:
        inj[bus] = inj[bus] + x
        terms[bus] += 1
        mag[bus] = mag[bus] + np.abs(x)

    for g in assets["generators"]:
        add(g["bus"], a(g["p_mw"]))
    for su in assets["storage_units"]:
        add(su["bus"], a(su["p_mw"]))
    for b in assets["buses"]:
        add(b["id"], a(b["load_shed_mw"]))
    for bus in exp.load_by_bus.columns:
        x = exp.load_by_bus[bus].to_numpy(float)
        inj[bus] = inj[bus] - x
        mag[bus] = mag[bus] + np.abs(x)
    for list_name in ("lines", "transformers"):
        for br in assets.get(list_name, []):
            f = a(br["flow_mw"])
            add(br["bus0"], -f)
            add(br["bus1"], f)
    unbalanced_ok: set[str] = set(exp.store_buses)
    link_loss = np.zeros(k)
    for lk in assets["links"]:
        f = a(lk["flow_mw"])
        eff = exp.links[lk["id"]].efficiency
        add(lk["bus0"], -f)
        add(lk["bus1"], eff * f)
        link_loss += (1 - eff) * f
        if exp.links[lk["id"]].extra_ports and np.any(f != 0):
            unbalanced_ok.update(exp.links[lk["id"]].extra_ports)
    checked = [b for b in inj if b not in unbalanced_ok]
    if unbalanced_ok:
        # Store outputs are not part of gridstorm-result/1.0: buses with stores cannot be closed.
        rep.facts["balance_unchecked_buses"] = sorted(unbalanced_ok)
    worst = 0.0
    for b in checked:
        tol = terms[b] * SER + np.maximum(SOLVER_ABS, SOLVER_REL * mag[b])
        rep.compare(name, f"nodal balance at bus {b!r}", inj[b], 0.0, tol)
        worst = max(worst, float(np.max(np.abs(inj[b]))))
    rep.facts["nodal_residual_max_mw"] = worst
    system = np.sum([inj[b] for b in checked], axis=0)
    tol = sum(terms[b] for b in checked) * SER + SOLVER_ABS * len(checked)
    rep.compare(name, "system balance Σ_buses", system, 0.0, tol)
    rep.facts["system_residual_max_mw"] = float(np.max(np.abs(system)))
    rep.facts["link_loss_max_mw"] = float(np.max(np.abs(link_loss))) if assets["links"] else 0.0
    rep.bound(
        name,
        "metrics.balance_residual_max_mw",
        res["metrics"]["balance_residual_max_mw"],
        BALANCE_RESIDUAL_LIMIT_MW,
        1e-12,
    )


def check_generator_limits(res: dict, exp: Expected, rep: Report) -> None:
    name = "generator_limits"
    assets = res["assets"]
    ids = {g["id"] for g in assets["generators"]}
    rep.require(
        name,
        ids == set(exp.gens),
        f"generator assets {len(ids)} != network generators {len(exp.gens)} "
        f"(missing {sorted(set(exp.gens) - ids)[:5]}, extra {sorted(ids - set(exp.gens))[:5]})",
    )
    for g in assets["generators"]:
        e = exp.gens.get(g["id"])
        if e is None:
            continue
        rep.require(
            name, g["carrier"] == e.carrier and g["bus"] == e.bus, f"{g['id']}: carrier/bus"
        )
        avail_exp = e.pmax_pu * e.p_nom
        p = a(g["p_mw"])
        avail = a(g["available_mw"])
        rep.compare(
            name, f"{g['id']} available_mw=p_max_pu·p_nom", avail, avail_exp, _tol(avail_exp)
        )
        rep.bound(name, f"{g['id']} p<=available", p, avail_exp, _tol(avail_exp))
        floor = e.pmin_pu * e.p_nom
        rep.bound(name, f"{g['id']} p>=p_min_pu·p_nom", -p, -floor, _tol(floor))
    for b in assets["buses"]:
        sh = a(b["load_shed_mw"])
        dem = (
            exp.load_by_bus[b["id"]].to_numpy(float)
            if b["id"] in exp.load_by_bus.columns
            else np.zeros(len(sh))
        )
        cap = dem if exp.shed_enabled else np.zeros(len(sh))
        rep.bound(name, f"bus {b['id']} shed<=demand", sh, np.clip(cap, 0, None), _tol(cap))
        rep.bound(name, f"bus {b['id']} shed>=0", -sh, 0.0, _tol(0.0))


def check_branch_limits(res: dict, exp: Expected, rep: Report) -> None:
    name = "branch_limits"
    assets, m = res["assets"], res["metrics"]
    in_service_max: list[float] = []
    in_service_all: list[np.ndarray] = []
    boundary = 0
    lines_only = 0
    for list_name in ("lines", "transformers"):
        rows = assets.get(list_name, [])
        rep.require(
            name,
            {r["id"] for r in rows} == set(exp.branches[list_name]),
            f"{list_name}: asset ids differ from network",
        )
        for r in rows:
            e = exp.branches[list_name][r["id"]]
            rep.compare(name, f"{list_name}/{r['id']} s_nom_mva", r["s_nom_mva"], e.s_nom, SER)
            rep.require(name, r["outaged"] == e.outaged, f"{list_name}/{r['id']} outaged flag")
            flow = a(r["flow_mw"])
            load = a(r["loading_pct"])
            if e.outaged:
                continue  # outage_events verifies zero flow/loading
            lim = e.s_nom * e.s_max_pu
            with np.errstate(divide="ignore", invalid="ignore"):
                want = np.where(lim > 0, np.abs(flow) / lim * 100.0, np.nan)
                tol_pct = SER + np.where(lim > 0, SER / lim * 100.0, 0.0)
            rep.compare(
                name, f"{list_name}/{r['id']} loading=|flow|/(s_nom·s_max_pu)", load, want, tol_pct
            )
            rep.bound(
                name, f"{list_name}/{r['id']} |flow|<=s_nom·s_max_pu", np.abs(flow), lim, _tol(lim)
            )
            peak = float(np.nanmax(load)) if np.isfinite(load).any() else np.nan
            in_service_max.append(peak)
            in_service_all.append(load)
            if abs(peak - CONGESTION_THRESHOLD_PCT) <= 2 * SER:
                boundary += 1
            if peak >= CONGESTION_THRESHOLD_PCT and list_name == "lines":
                lines_only += 1
    peaks = np.asarray(in_service_max)
    congested = int(np.sum(peaks >= CONGESTION_THRESHOLD_PCT))
    rep.compare(
        name,
        "congested_line_count (branches ≥ 99.9 %)",
        m["congested_line_count"],
        congested,
        boundary + 0.5,
    )
    rep.facts["congested_branches"] = congested
    rep.facts["congested_lines_only"] = lines_only
    allv = np.concatenate(in_service_all) if in_service_all else np.zeros(0)
    if allv.size:
        rep.compare(name, "max_line_loading_pct", m["max_line_loading_pct"], np.nanmax(allv), 1e-3)
        rep.compare(
            name, "mean_line_loading_pct", m["mean_line_loading_pct"], np.nanmean(allv), 1e-3
        )
        rep.facts["max_loading_pct"] = float(np.nanmax(allv))
    for lk in assets["links"]:
        e = exp.links[lk["id"]]
        rep.compare(name, f"link {lk['id']} p_nom_mw", lk["p_nom_mw"], e.p_nom, SER)
        rep.require(name, lk["outaged"] == e.outaged, f"link {lk['id']} outaged flag")
        if e.outaged:
            continue
        f = a(lk["flow_mw"])
        hi, lo = e.pmax_pu * e.p_nom, e.pmin_pu * e.p_nom
        rep.bound(name, f"link {lk['id']} p0<=p_max_pu·p_nom", f, hi, _tol(hi))
        rep.bound(name, f"link {lk['id']} p0>=p_min_pu·p_nom", -f, -lo, _tol(lo))


def check_storage(res: dict, exp: Expected, rep: Report) -> None:
    name = "storage"
    sus = res["assets"]["storage_units"]
    if not exp.storage:
        rep.skip(name, "network has no storage units", status="n/a")
        return
    rep.require(name, {s["id"] for s in sus} == set(exp.storage), "storage unit ids differ")
    w = exp.w_store
    for s in sus:
        e = exp.storage[s["id"]]
        p, pd_, ps = a(s["p_mw"]), a(s["p_dispatch_mw"]), a(s["p_store_mw"])
        spill, soc = a(s["spill_mw"]), a(s["soc_mwh"])
        sid = s["id"]
        rep.compare(name, f"{sid} p=p_dispatch-p_store", p, pd_ - ps, 3 * SER)
        rep.bound(
            name, f"{sid} p_dispatch<=p_max_pu·p_nom", pd_, e.pmax_pu * e.p_nom, _tol(e.p_nom)
        )
        rep.bound(name, f"{sid} p_store<=-p_min_pu·p_nom", ps, -e.pmin_pu * e.p_nom, _tol(e.p_nom))
        rep.bound(name, f"{sid} p_dispatch>=0", -pd_, 0.0, _tol(0.0))
        rep.bound(name, f"{sid} p_store>=0", -ps, 0.0, _tol(0.0))
        rep.bound(name, f"{sid} spill>=0", -spill, 0.0, _tol(0.0))
        rep.bound(name, f"{sid} spill<=inflow", spill, e.inflow, _tol(e.inflow))
        e_nom = e.p_nom * e.max_hours
        rep.bound(name, f"{sid} soc<=p_nom·max_hours", soc, e_nom, _tol(e_nom))
        rep.bound(name, f"{sid} soc>=0", -soc, 0.0, _tol(0.0))
        prev = np.concatenate([[soc[-1] if e.cyclic else e.soc_initial], soc[:-1]])
        keep = (1.0 - e.standing_loss) ** w
        want = prev * keep + w * (e.eff_store * ps - pd_ / e.eff_dispatch + e.inflow - spill)
        tol = SER * (1 + keep) + w * SER * (e.eff_store + 1 / e.eff_dispatch + 1) + _tol(e_nom)
        rep.compare(name, f"{sid} SOC recursion", soc, want, tol)


def check_outage_events(res: dict, exp: Expected, rep: Report, scenario) -> None:
    name = "outage_events"
    assets = res["assets"]
    k = len(exp.w_gen)
    h0 = scenario.horizon.start
    gens = {g["id"]: g for g in assets["generators"]}
    branches = {(ln, r["id"]): r for ln in ("lines", "transformers") for r in assets.get(ln, [])}
    links = {r["id"]: r for r in assets["links"]}
    n_events = 0
    for ev in scenario.events:
        if ev.type == "generator_outage":
            n_events += 1
            g = gens[ev.asset_id]
            idx = np.arange(h0, h0 + k)
            win = (
                np.ones(k, bool)
                if ev.window is None
                else (idx >= ev.window.start) & (idx < ev.window.end)
            )
            rep.require(name, g["outaged"] is True, f"generator {ev.asset_id} not flagged outaged")
            rep.compare(name, f"generator {ev.asset_id} p=0 in window", a(g["p_mw"])[win], 0.0, SER)
            rep.compare(
                name,
                f"generator {ev.asset_id} available=0 in window",
                a(g["available_mw"])[win],
                0.0,
                SER,
            )
        elif ev.type == "line_outage":
            n_events += 1
            ln = "lines" if ev.component == "line" else "transformers"
            r = branches[(ln, ev.asset_id)]
            rep.require(name, r["outaged"] is True, f"{ln} {ev.asset_id} not flagged outaged")
            rep.compare(name, f"{ln} {ev.asset_id} flow=0", a(r["flow_mw"]), 0.0, 0.0)
            rep.compare(name, f"{ln} {ev.asset_id} loading=0", a(r["loading_pct"]), 0.0, 0.0)
        elif ev.type == "link_outage":
            n_events += 1
            r = links[ev.asset_id]
            rep.require(name, r["outaged"] is True, f"link {ev.asset_id} not flagged outaged")
            rep.compare(name, f"link {ev.asset_id} flow=0", a(r["flow_mw"]), 0.0, 0.0)
    flagged = (
        {g for g, r in gens.items() if r["outaged"]}
        | {f"{ln}/{i}" for (ln, i), r in branches.items() if r["outaged"]}
        | {f"link/{i}" for i, r in links.items() if r["outaged"]}
    )
    expected_flags = (
        {e.asset_id for e in scenario.events if e.type == "generator_outage"}
        | {
            f"{'lines' if e.component == 'line' else 'transformers'}/{e.asset_id}"
            for e in scenario.events
            if e.type == "line_outage"
        }
        | {f"link/{e.asset_id}" for e in scenario.events if e.type == "link_outage"}
    )
    rep.require(
        name, flagged == expected_flags, f"outaged flags {flagged} != events {expected_flags}"
    )
    if n_events == 0:
        rep.skip(name, "scenario has no outage events (flags verified all false)", status="pass")


def check_objective(res: dict, exp: Expected, rep: Report) -> None:
    name = "objective"
    m, assets = res["metrics"], res["assets"]
    obj = res["solver"]["objective_eur"]
    rep.compare(
        name, "total_system_cost_eur == solver.objective_eur", m["total_system_cost_eur"], obj, 0.0
    )
    w, wo = exp.w_gen, exp.w_obj
    shed_mw = np.sum([a(b["load_shed_mw"]) for b in assets["buses"]], axis=0)
    shed_cost = float((shed_mw * exp.voll * w).sum())
    nb = len(assets["buses"])
    rep.compare(
        name,
        "load_shedding_cost_eur = VOLL·Σ shed·w",
        m["load_shedding_cost_eur"],
        shed_cost,
        exp.voll * nb * float(w.sum()) * SER + MET + 1e-9 * abs(shed_cost),
    )
    rep.compare(
        name,
        "generation_cost_eur = total - shedding (VER-006)",
        m["generation_cost_eur"],
        m["total_system_cost_eur"] - m["load_shedding_cost_eur"],
        3 * MET,
    )
    if exp.mc_quadratic_max or exp.store_mc_max or any(s.mc_storage for s in exp.storage.values()):
        rep.skip(name, "quadratic/store/storage-energy costs present: LP objective not recomputed")
        return
    per_t = np.zeros(len(w))
    err = np.zeros(len(w))
    for g in assets["generators"]:
        mc = exp.gens[g["id"]].mc
        per_t += mc * a(g["p_mw"])
        err += abs(mc) * SER
    per_t += exp.voll * shed_mw
    err += exp.voll * nb * SER
    for s in assets["storage_units"]:
        mc = exp.storage[s["id"]].mc
        per_t += mc * a(s["p_dispatch_mw"])
        err += abs(mc) * SER
    for lk in assets["links"]:
        mc = exp.links[lk["id"]].mc
        per_t += mc * a(lk["flow_mw"])
        err += abs(mc) * SER
    recomputed = float((per_t * wo).sum())
    tol = float((err * wo).sum()) + SOLVER_REL * abs(recomputed) + MET
    rep.compare(name, "objective = Σ_t w·(Σ mc·p + VOLL·shed)", obj, recomputed, tol)
    rep.facts["objective_recomputed_eur"] = recomputed


def check_co2(res: dict, exp: Expected, rep: Report) -> None:
    name = "co2"
    reported = res["metrics"]["co2_emissions_t"]
    emitting = {c for c, v in exp.carrier_co2.items() if v}
    if not emitting:
        rep.require(
            name, reported is None, f"no CO2 intensities in dataset but co2_emissions_t={reported}"
        )
        rep.require(
            name,
            any(NO_CO2_WARNING in wtxt for wtxt in res["warnings"]),
            "null co2_emissions_t lacks the data-gap warning",
        )
        rep.facts["co2"] = "null (no intensities)"
        return
    rep.require(
        name, reported is not None, "dataset has CO2 intensities but co2_emissions_t is null"
    )
    if reported is None:
        return
    w = exp.w_gen
    tot = 0.0
    err = 0.0
    for g in res["assets"]["generators"]:
        e = exp.gens[g["id"]]
        f = exp.carrier_co2.get(e.carrier, 0.0) / e.efficiency if e.efficiency else 0.0
        tot += float((a(g["p_mw"]) * f * w).sum())
        err += abs(f) * SER * float(w.sum())
    rep.compare(name, "co2 = Σ p·intensity/eff·w", reported, tot, err + MET + 1e-9 * abs(tot))
    rep.facts["co2"] = f"{reported} t"


def run_all(res: dict, exp: Expected | None, scenario, label: str) -> Report:
    rep = Report(label)
    check_outcome_mapping(res, rep)
    if res["outcome"] != "feasible":
        for c in CHECKS[1:]:
            rep.skip(c, f"outcome {res['outcome']}: no numbers reported", status="n/a")
        return rep
    assert exp is not None
    check_snapshots_weights(res, exp, rep)
    check_demand_multipliers(res, exp, rep)
    check_energy_accounting(res, exp, rep)
    check_power_balance(res, exp, rep)
    check_generator_limits(res, exp, rep)
    check_branch_limits(res, exp, rep)
    check_storage(res, exp, rep)
    check_outage_events(res, exp, rep, scenario)
    check_objective(res, exp, rep)
    check_co2(res, exp, rep)
    return rep
