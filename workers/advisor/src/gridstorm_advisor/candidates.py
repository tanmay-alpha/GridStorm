"""Candidate generation: DC-sensitivity-ranked redispatch pairs, targeted load shedding,
non-islanding branch switching, and pairwise combinations.

Everything here is a heuristic SHORTLIST. Amounts are provisional upper bounds ("caps"); the
advisor sizes scalable actions with AC power flows and accepts nothing without a full AC check.
"""

from __future__ import annotations

import copy
import itertools
import math
from dataclasses import dataclass, field

import numpy as np
import pandapower as pp
import pandapower.topology as top

from gridstorm_advisor.actions import is_slack, load_p_mw
from gridstorm_advisor.network import AdvisorNetwork
from gridstorm_advisor.sensitivity import DCSensitivity

TARGET_LOADING_PCT = 98.0  # DC sizing target for overloaded branches (estimate only)
MIN_RELIEF = 1e-3  # MW of flow relief per MW of action below which a lever is ignored
MIN_AMOUNT_MW = 0.5


@dataclass
class Limits:
    max_redispatch: int = 6
    max_shed: int = 5
    max_switch: int = 5
    combo_pool_per_type: int = 3


@dataclass
class Draft:
    """A candidate before AC sizing/evaluation."""

    actions: list[dict]
    origin: str  # redispatch | load_shed | switching | combination
    dc_estimate: dict = field(default_factory=dict)
    rank_key: tuple = ()


def rating_mva(adv: AdvisorNetwork, net: pp.pandapowerNet, bid: str) -> float | None:
    if adv.loading_basis != "pandapower_loading_percent":
        return adv.branch_rating_mva.get(bid)
    ref = adv.branches[bid]
    if ref.table == "trafo":
        return float(net.trafo.at[ref.index, "sn_mva"])
    row = net.line.loc[ref.index]
    vn = float(net.bus.at[int(row.from_bus), "vn_kv"])
    return float(row.max_i_ka * row.df * row.parallel * vn * math.sqrt(3))


@dataclass
class Targets:
    thermal: dict[str, float]  # branch id -> excess MW above TARGET_LOADING_PCT
    direction: dict[str, float]  # branch id -> sign of DC flow (from->to)
    low_voltage_buses: list[str]
    slack_excess_mw: float  # slack above Pmax (>0) or below Pmin (<0)
    slack_ids: list[str]
    non_converged: bool


def find_targets(adv, net, state: dict, sens: DCSensitivity) -> Targets:
    thermal: dict[str, float] = {}
    if state["converged"]:
        for v in state["violations"]:
            if v["kind"] == "thermal" and v["asset_id"] in sens.dc_flow_mw:
                rate = rating_mva(adv, net, v["asset_id"])
                thermal[v["asset_id"]] = (v["value"] - TARGET_LOADING_PCT) / 100.0 * rate
    else:  # AC failed: use DC loading of rated branches to point the levers
        for bid, flow in sens.dc_flow_mw.items():
            rate = rating_mva(adv, net, bid)
            if rate and abs(flow) > rate:
                thermal[bid] = abs(flow) - TARGET_LOADING_PCT / 100.0 * rate
    direction = {b: (1.0 if sens.dc_flow_mw[b] >= 0 else -1.0) for b in thermal}
    low_v = sorted(
        (v for v in state["violations"] if v["kind"] == "voltage_low"),
        key=lambda v: (v["value"], v["asset_id"]),
    )
    slack_excess = 0.0
    slack_ids = []
    for v in state["violations"]:
        if v["kind"] == "slack_p_max":
            slack_excess += v["value"] - v["limit"]
            slack_ids.append(v["asset_id"])
        elif v["kind"] == "slack_p_min":
            slack_excess += v["value"] - v["limit"]
            slack_ids.append(v["asset_id"])
    return Targets(
        thermal=dict(sorted(thermal.items())),
        direction=direction,
        low_voltage_buses=[v["asset_id"] for v in low_v],
        slack_excess_mw=slack_excess,
        slack_ids=slack_ids,
        non_converged=not state["converged"],
    )


def _relief(sens: DCSensitivity, tg: Targets, bus_up: str, bus_down: str | None) -> dict[str, float]:
    """MW of flow reduction on each thermal target per MW injected at bus_up, withdrawn at
    bus_down (None = slack)."""
    out = {}
    for bid in tg.thermal:
        row = sens.row(bid)
        sigma = row[bus_up] - (row[bus_down] if bus_down else 0.0)
        out[bid] = -tg.direction[bid] * sigma
    return out


def _dc_max_loading(adv, net, sens: DCSensitivity, delta: np.ndarray) -> tuple[float, str | None]:
    """Max DC loading (%) over rated branches after adding ``delta`` (aligned with branch_ids)."""
    best, best_id = 0.0, None
    for i, bid in enumerate(sens.branch_ids):
        rate = rating_mva(adv, net, bid)
        if not rate:
            continue
        val = abs(sens.dc_flow_mw[bid] + delta[i]) / rate * 100.0
        if val > best:
            best, best_id = val, bid
    return best, best_id


def _gen_table(adv: AdvisorNetwork, net, state: dict, sens: DCSensitivity) -> list[dict]:
    rows = []
    for gid, ref in sorted(adv.generators.items()):
        if not bool(net[ref.table].at[ref.index, "in_service"]):
            continue
        bus = adv.bus_id_of(int(net[ref.table].at[ref.index, "bus"]))
        if bus not in sens.bus_ids:
            continue
        slack = is_slack(net, ref)
        if slack:
            p = state["gen_p_mw"].get(gid) if state["converged"] else None
        else:
            p = float(net[ref.table].at[ref.index, "p_mw"])
        pmax = float(net[ref.table].at[ref.index, "max_p_mw"])
        pmin = float(net[ref.table].at[ref.index, "min_p_mw"])
        if p is None or math.isnan(pmax) or math.isnan(pmin):
            continue
        cost = adv.gen_cost.get(gid)
        rows.append({
            "id": gid, "bus": bus, "slack": slack, "p": p,
            "up": max(0.0, pmax - p), "down": max(0.0, p - pmin),
            "mc": cost.marginal(p) if cost else 0.0,
        })
    return rows


def redispatch_drafts(adv, net, state, sens, tg: Targets, limits: Limits) -> list[Draft]:
    if not tg.thermal and tg.slack_excess_mw == 0.0:
        return []
    gens = _gen_table(adv, net, state, sens)
    drafts: list[Draft] = []
    for up, down in itertools.permutations(gens, 2):
        if up["bus"] == down["bus"]:
            continue
        cap = min(up["up"], down["down"])
        if cap < MIN_AMOUNT_MW:
            continue
        needed = 0.0
        covers_all = True
        if tg.thermal:
            # the reference (slack) bus has an all-zero PTDF column, so no special case is needed
            relief = _relief(sens, tg, up["bus"], down["bus"])
            helped = [b for b in tg.thermal if relief[b] > MIN_RELIEF]
            if not helped:
                continue
            covers_all = len(helped) == len(tg.thermal)
            needed = max(tg.thermal[b] / relief[b] for b in helped)
        if tg.slack_excess_mw > 0:  # slack above Pmax: must move generation off the slack
            if not down["slack"]:
                continue
            needed = max(needed, tg.slack_excess_mw)
        elif tg.slack_excess_mw < 0:  # slack below Pmin: must move generation onto the slack
            if not up["slack"]:
                continue
            needed = max(needed, -tg.slack_excess_mw)
        amount = min(cap, needed * 1.05)
        delta = sens.bus_col(up["bus"]) - sens.bus_col(down["bus"])
        est, est_id = _dc_max_loading(adv, net, sens, delta * amount)
        drafts.append(Draft(
            actions=[{"type": "redispatch", "gen_up": up["id"], "gen_down": down["id"],
                      "delta_mw": cap}],
            origin="redispatch",
            dc_estimate={"needed_mw": round(needed, 3), "cap_mw": round(cap, 3),
                         "relieves_all_overloads_dc": covers_all,
                         "est_max_loading_pct": round(est, 3), "est_max_branch_id": est_id},
            rank_key=(0 if covers_all else 1, 0 if needed <= cap else 1, round(est, 6),
                      round((up["mc"] - down["mc"]) * min(cap, needed), 6), up["id"], down["id"]),
        ))
    drafts.sort(key=lambda d: d.rank_key)
    return drafts[: limits.max_redispatch]


def _supplied_loads(adv, net, sens) -> list[tuple[str, str, float]]:
    out = []
    for lid in sorted(adv.loads):
        p = load_p_mw(adv, net, lid)
        if p <= 0:
            continue
        bus = adv.bus_id_of(int(net.load.at[adv.loads[lid][0], "bus"]))
        if bus in sens.bus_ids:
            out.append((lid, bus, p))
    return out


def _hops_from(net, adv: AdvisorNetwork, bus_id: str) -> dict[str, int]:
    import networkx as nx

    g = top.create_nxgraph(net, respect_switches=True)
    lengths = nx.single_source_shortest_path_length(g, adv.buses[bus_id])
    return {adv.bus_id_of(b): d for b, d in lengths.items()}


def shed_drafts(adv, net, state, sens, tg: Targets, limits: Limits) -> list[Draft]:
    loads = _supplied_loads(adv, net, sens)
    drafts: list[Draft] = []
    seen: set[str] = set()

    def add(entries: list[tuple[str, float]], origin_note: str, key: tuple) -> None:
        sig = "|".join(sorted(e[0] for e in entries))
        if sig in seen or not entries:
            return
        seen.add(sig)
        drafts.append(Draft(
            actions=[{"type": "load_shed",
                      "loads": [{"load_id": lid, "shed_mw": p} for lid, p in sorted(entries)]}],
            origin="load_shed",
            dc_estimate={"selection": origin_note},
            rank_key=key,
        ))

    if tg.thermal:
        scored = []
        for lid, bus, p in loads:
            relief = _relief(sens, tg, bus, None)
            helped = [b for b in tg.thermal if relief[b] > MIN_RELIEF]
            if not helped:
                continue
            needed = max(tg.thermal[b] / relief[b] for b in helped)
            covers = 0 if len(helped) == len(tg.thermal) else 1
            scored.append((covers, 0 if needed <= p else 1, round(needed, 6), lid, p))
        scored.sort()
        for covers, feasible, needed, lid, p in scored[: limits.max_shed]:
            add([(lid, p)], f"dc_relief_rank needed~{needed:.1f}MW",
                (0, covers, feasible, needed, lid))
        if len(scored) > 1:  # targeted group: the most effective loads, shed by one fraction
            group = scored[: limits.max_shed]
            add([(e[3], e[4]) for e in group], "dc_relief_group", (1, 0, 0, 0.0, "group"))
    for bus in tg.low_voltage_buses[:3]:
        hops = _hops_from(net, adv, bus)
        near = sorted(
            ((hops[b], lid, p) for lid, b, p in loads if b in hops),
            key=lambda t: (t[0], -t[2], t[1]),
        )[:3]
        if near:
            add([(lid, p) for _, lid, p in near], f"nearest_loads_to_{bus}", (2, 0, 0, 0.0, bus))
    if tg.slack_excess_mw > 0 or tg.non_converged or not drafts:
        largest = sorted(loads, key=lambda t: (-t[2], t[0]))[:3]
        for lid, _, p in largest:
            add([(lid, p)], "largest_load", (3, 0, 0, -p, lid))
    drafts.sort(key=lambda d: d.rank_key)
    return drafts[: limits.max_shed + 4]


def _islands_anything(adv: AdvisorNetwork, net, bid: str, base_unsupplied: set[int]) -> bool:
    work = copy.copy(net)
    ref = adv.branches[bid]
    work[ref.table] = net[ref.table].copy()
    work[ref.table].loc[ref.index, "in_service"] = False
    unsup = set(top.unsupplied_buses(work, respect_switches=True)) - base_unsupplied
    if not unsup:
        return False
    has_load = bool((net.load.in_service & net.load.bus.isin(unsup)).any())
    has_gen = bool((net.gen.in_service & net.gen.bus.isin(unsup)).any())
    has_sgen = bool((net.sgen.in_service & net.sgen.bus.isin(unsup)).any()) if len(net.sgen) else False
    return has_load or has_gen or has_sgen


def switching_drafts(adv, net, state, sens, tg: Targets, limits: Limits) -> list[Draft]:
    if not tg.thermal:
        return []
    base_unsup = set(top.unsupplied_buses(net, respect_switches=True))
    target_idx = [sens.branch_ids.index(b) for b in tg.thermal]
    current = max(
        abs(sens.dc_flow_mw[b]) / rating_mva(adv, net, b) * 100.0 for b in tg.thermal
    )
    drafts = []
    for k, bid in enumerate(sens.branch_ids):
        if bid in tg.thermal:
            continue
        lodf = sens.lodf_column(bid)
        if lodf is None:
            continue
        delta = lodf * sens.dc_flow_mw[bid]
        delta[k] = -sens.dc_flow_mw[bid]
        est_targets = max(
            abs(sens.dc_flow_mw[sens.branch_ids[i]] + delta[i])
            / rating_mva(adv, net, sens.branch_ids[i]) * 100.0
            for i in target_idx
        )
        if est_targets >= current - 1e-6:
            continue
        if _islands_anything(adv, net, bid, base_unsup):
            continue
        est, est_id = _dc_max_loading(adv, net, sens, delta)
        drafts.append(Draft(
            actions=[{"type": "open_branch", "branch_id": bid}],
            origin="switching",
            dc_estimate={"est_target_max_loading_pct": round(est_targets, 3),
                         "est_max_loading_pct": round(est, 3), "est_max_branch_id": est_id},
            rank_key=(round(max(est, est_targets), 6), bid),
        ))
    drafts.sort(key=lambda d: d.rank_key)
    return drafts[: limits.max_switch]


def combination_drafts(singles: dict[str, list[Draft]], limits: Limits) -> list[Draft]:
    pool: list[Draft] = []
    for kind in ("switching", "redispatch", "load_shed"):
        pool.extend(singles.get(kind, [])[: limits.combo_pool_per_type])
    out = []
    for a, b in itertools.combinations(pool, 2):
        if a.origin == "load_shed" and b.origin == "load_shed":
            continue
        acts = a.actions + b.actions
        if a.origin == b.origin == "redispatch":
            gens_a = {a.actions[0]["gen_up"], a.actions[0]["gen_down"]}
            gens_b = {b.actions[0]["gen_up"], b.actions[0]["gen_down"]}
            if gens_a & gens_b:
                continue
        out.append(Draft(actions=acts, origin="combination",
                         dc_estimate={"components": [a.origin, b.origin]}))
    return out
