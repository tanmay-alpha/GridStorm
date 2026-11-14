"""Deterministic Crisis Response Advisor (no LLM).

Pipeline: (1) AC power flow of the crisis state; (2) violations; (3) candidate shortlist from DC
sensitivities; (4) AC sizing (bisection) and full AC evaluation of every candidate on a deep copy;
(5) acceptance = converged AND zero violations AND no additional islanded load; (6) ranking by a
documented objective; (7) structured explanation; optional AC N-1 re-check of the top candidates.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass, field

import pandapower as pp

from gridstorm_advisor import actions as act
from gridstorm_advisor import candidates as cand
from gridstorm_advisor import sensitivity
from gridstorm_advisor.crisis import Crisis, apply_crisis
from gridstorm_advisor.network import AdvisorNetwork
from gridstorm_advisor.state import (
    PF_OPTIONS,
    SLACK_P_TOL_MW,
    THERMAL_TOL_PCT,
    VOLTAGE_TOL_PU,
    evaluate_state,
    violation_keys,
)

SCHEMA_VERSION = "gridstorm-advisor/1.0"


@dataclass
class AdvisorConfig:
    voll_eur_per_mwh: float = 10000.0
    switching_penalty_eur: float = 1000.0
    assumed_duration_h: float = 1.0
    bisection_iterations: int = 14
    # Sizing target: originally overloaded branches must end at or below this loading. Leaves a
    # small margin to the 100 % acceptance limit; it does not change the acceptance rules.
    sizing_target_pct: float = 99.5
    amount_resolution_mw: float = 0.01
    n_minus_1_top: int = 3
    limits: cand.Limits = field(default_factory=cand.Limits)

    def to_dict(self) -> dict:
        return {
            "voll_eur_per_mwh": self.voll_eur_per_mwh,
            "switching_penalty_eur": self.switching_penalty_eur,
            "assumed_duration_h": self.assumed_duration_h,
            "bisection_iterations": self.bisection_iterations,
            "sizing_target_pct": self.sizing_target_pct,
            "amount_resolution_mw": self.amount_resolution_mw,
            "n_minus_1_top": self.n_minus_1_top,
            "max_redispatch_candidates": self.limits.max_redispatch,
            "max_load_shed_candidates": self.limits.max_shed,
            "max_switching_candidates": self.limits.max_switch,
            "combination_pool_per_type": self.limits.combo_pool_per_type,
        }


ACCEPTANCE_RULES = [
    "AC power flow (pandapower Newton-Raphson, generator Q limits enforced) converges.",
    "Every violation present in the crisis state is cleared.",
    f"No new violation appears (thermal > 100 % of rating + {THERMAL_TOL_PCT} % tolerance, bus "
    f"voltage outside its VMIN/VMAX band with {VOLTAGE_TOL_PU} p.u. tolerance, slack active "
    f"power outside [Pmin, Pmax] with {SLACK_P_TOL_MW} MW tolerance).",
    "The action does not increase islanded (unsupplied) load.",
]


def _r(x, nd=4):
    return None if x is None else float(round(float(x), nd))


def _summary(state: dict, top_n: int = 5) -> dict:
    """Compact state summary for artifacts (per-element vectors only for the top-loaded)."""
    loading = state.get("branch_loading_pct", {})
    top = sorted(loading.items(), key=lambda kv: (-kv[1], kv[0]))[:top_n]
    keys = (
        "converged", "max_branch_loading_pct", "max_branch_id", "min_vm_pu", "max_vm_pu",
        "slack_p_mw", "losses_mw", "generation_cost_eur_per_h", "supplied_load_mw",
        "islanded_load_mw", "islanded_buses", "violations",
    )
    out = {k: state[k] for k in keys}
    out["n_violations"] = len(state["violations"])
    out["top_loaded_branches"] = [{"branch_id": b, "loading_pct": v} for b, v in top]
    return out


def _solve(adv: AdvisorNetwork, crisis_net: pp.pandapowerNet, actions: list[dict]) -> dict:
    net = copy.deepcopy(crisis_net)
    act.apply(adv, net, actions)
    return evaluate_state(adv, net)


def _meets_target(state: dict, original: set, target_pct: float) -> bool:
    """Converged, no original violation left, and every originally overloaded branch at or
    below ``target_pct``."""
    if not state["converged"] or violation_keys(state) & original:
        return False
    loading = state["branch_loading_pct"]
    return all(loading.get(aid, 0.0) <= target_pct for kind, aid in original if kind == "thermal")


def _round_up(x: float, res: float) -> float:
    return math.ceil(x / res - 1e-9) * res


def _size(adv, crisis_net, actions: list[dict], original: set, cfg: AdvisorConfig):
    """Smallest uniform scale lam in (0, 1] of the scalable amounts that clears every original
    violation in AC with originally overloaded branches at or below ``cfg.sizing_target_pct``
    (bisection; assumes monotonicity, which is NOT guaranteed — the final evaluation is
    authoritative). Returns (sized actions, sizing note)."""
    if not any(a["type"] in act.SCALABLE for a in actions):
        return actions, {"method": "fixed"}

    def at(lam: float) -> list[dict]:
        out = []
        for a in actions:
            s = act.scaled(a, lam)
            if s["type"] == "redispatch":
                s["delta_mw"] = round(_round_up(s["delta_mw"], cfg.amount_resolution_mw), 6)
            elif s["type"] == "load_shed":
                s["loads"] = [
                    {**e, "shed_mw": round(_round_up(e["shed_mw"], cfg.amount_resolution_mw), 6)}
                    for e in s["loads"]
                ]
            out.append(s)
        return out

    target = cfg.sizing_target_pct
    if not _meets_target(_solve(adv, crisis_net, at(1.0)), original, target):
        return at(1.0), {"method": "ac_bisection", "target_met_at_cap": False, "scale": 1.0}
    lo, hi = 0.0, 1.0
    for _ in range(cfg.bisection_iterations):
        mid = 0.5 * (lo + hi)
        if _meets_target(_solve(adv, crisis_net, at(mid)), original, target):
            hi = mid
        else:
            lo = mid
    return at(hi), {"method": "ac_bisection", "target_met_at_cap": True, "scale": _r(hi, 6)}


def _objective(adv, state: dict, actions: list[dict], cfg: AdvisorConfig, ref_cost) -> dict:
    gen_cost = state["generation_cost_eur_per_h"]
    gen_cost_eur = None if gen_cost is None else gen_cost * cfg.assumed_duration_h
    shed = act.shed_mw(actions)
    shed_cost = cfg.voll_eur_per_mwh * shed * cfg.assumed_duration_h
    switch_cost = cfg.switching_penalty_eur * act.n_switching(actions)
    total = None if gen_cost_eur is None else gen_cost_eur + shed_cost + switch_cost
    delta = None
    if gen_cost_eur is not None and ref_cost is not None:
        delta = gen_cost_eur - ref_cost * cfg.assumed_duration_h
    return {
        "generation_cost_eur": _r(gen_cost_eur, 2),
        "generation_cost_delta_eur": _r(delta, 2),
        "load_shed_mw": _r(shed, 3),
        "load_shed_cost_eur": _r(shed_cost, 2),
        "switching_actions": act.n_switching(actions),
        "switching_penalty_eur": _r(switch_cost, 2),
        "objective_eur": _r(total, 2),
    }


def _verdict(state: dict, original: set, islanded_before: float) -> tuple[bool, list[str], dict]:
    after = violation_keys(state)
    cleared = sorted(original - after, key=str)
    remaining = sorted(original & after, key=str)
    new = sorted(after - original, key=str)
    reasons: list[str] = []
    if not state["converged"]:
        reasons.append("AC power flow did not converge")
    else:
        by_key = {(v["kind"], v["asset_id"]): v for v in state["violations"]}
        for k in remaining:
            v = by_key[k]
            reasons.append(f"violation remains: {_fmt_violation(v)}")
        for k in new:
            v = by_key[k]
            reasons.append(f"new violation: {_fmt_violation(v)}")
    if state["islanded_load_mw"] > islanded_before + 1e-6:
        reasons.append(
            f"islands additional load ({state['islanded_load_mw'] - islanded_before:.2f} MW)"
        )
    detail = {
        "cleared": [list(k) for k in cleared],
        "remaining": [list(k) for k in remaining] if state["converged"] else None,
        "new": [list(k) for k in new] if state["converged"] else None,
    }
    return not reasons, reasons, detail


def _fmt_violation(v: dict) -> str:
    if v["kind"] == "thermal":
        return f"{v['asset_id']} loading {v['value']:.2f}% > {v['limit']:.0f}%"
    if v["kind"] == "voltage_low":
        return f"{v['asset_id']} voltage {v['value']:.4f} < {v['limit']:.4f} p.u."
    if v["kind"] == "voltage_high":
        return f"{v['asset_id']} voltage {v['value']:.4f} > {v['limit']:.4f} p.u."
    if v["kind"] == "slack_p_max":
        return f"slack {v['asset_id']} P {v['value']:.2f} MW > Pmax {v['limit']:.2f} MW"
    if v["kind"] == "slack_p_min":
        return f"slack {v['asset_id']} P {v['value']:.2f} MW < Pmin {v['limit']:.2f} MW"
    return "power flow did not converge"


def _candidate_id(actions: list[dict]) -> str:
    sig = json.dumps(
        [{k: v for k, v in a.items() if k not in ("delta_mw", "loads")}
         | ({"loads": sorted(e["load_id"] for e in a["loads"])} if "loads" in a else {})
         for a in actions],
        sort_keys=True,
    )
    return "cand-" + hashlib.sha256(sig.encode()).hexdigest()[:10]


def _explain(adv, actions, crisis_state, state, accepted, reasons, objective) -> str:
    what = "; ".join(act.describe(adv, a) for a in actions)
    if not state["converged"]:
        return f"{what}. Result: AC power flow did not converge -> rejected."
    before = crisis_state.get("max_branch_loading_pct")
    after = state["max_branch_loading_pct"]
    parts = [f"{what}."]
    if before is not None:
        parts.append(
            f"Max branch loading {before:.1f}% ({crisis_state['max_branch_id']}) -> "
            f"{after:.1f}% ({state['max_branch_id']});"
        )
    else:
        parts.append(f"Crisis state did not converge; after action max loading {after:.1f}%;")
    parts.append(f"min voltage {state['min_vm_pu']:.4f} p.u.;")
    parts.append(f"{len(state['violations'])} violation(s) after.")
    if accepted:
        parts.append(
            f"Accepted: objective {objective['objective_eur']} EUR "
            f"(shed {objective['load_shed_mw']} MW)."
        )
    else:
        parts.append("Rejected: " + "; ".join(reasons) + ".")
    return " ".join(parts)


def _evaluate_draft(adv, crisis_net, crisis_state, draft, original, cfg, ref_cost) -> dict:
    sized, sizing = _size(adv, crisis_net, draft.actions, original, cfg)
    state = _solve(adv, crisis_net, sized)
    accepted, reasons, detail = _verdict(state, original, crisis_state["islanded_load_mw"])
    objective = _objective(adv, state, sized, cfg, ref_cost)
    if objective["objective_eur"] is None and state["converged"]:
        objective["objective_eur"] = _r(
            objective["load_shed_cost_eur"] + objective["switching_penalty_eur"], 2
        )
    return {
        "candidate_id": _candidate_id(sized),
        "origin": draft.origin,
        "size": len(sized),
        "actions": sized,
        "generation": {"dc_estimate": draft.dc_estimate, "sizing": sizing},
        "status": "accepted" if accepted else "rejected",
        "rejection_reasons": reasons,
        "violations": detail,
        "after": _summary(state),
        "objective": objective,
        "explanation": _explain(adv, sized, crisis_state, state, accepted, reasons, objective),
        "rank": None,
        "_state": state,
    }


def n_minus_1(adv: AdvisorNetwork, net: pp.pandapowerNet, exclude: set[str]) -> dict:
    """AC N-1 over every in-service branch of ``net`` (not mutated)."""
    rows = []
    for bid, ref in sorted(adv.branches.items()):
        if bid in exclude or not bool(net[ref.table].at[ref.index, "in_service"]):
            continue
        work = copy.deepcopy(net)
        work[ref.table].loc[ref.index, "in_service"] = False
        st = evaluate_state(adv, work)
        rows.append({
            "outage_branch_id": bid,
            "converged": st["converged"],
            "n_violations": len(st["violations"]) if st["converged"] else None,
            "max_branch_loading_pct": st["max_branch_loading_pct"],
            "min_vm_pu": st["min_vm_pu"],
            "islanded_load_mw": st["islanded_load_mw"],
            "violations": st["violations"][:5],
        })
    insecure = [r for r in rows if not r["converged"] or r["n_violations"] or r["islanded_load_mw"]]
    worst = sorted(
        insecure,
        key=lambda r: (r["converged"], -(r["islanded_load_mw"] or 0),
                       -(r["max_branch_loading_pct"] or 0), r["outage_branch_id"]),
    )[:10]
    return {
        "n_contingencies": len(rows),
        "n_secure": len(rows) - len(insecure),
        "n_with_violations": sum(1 for r in rows if r["converged"] and r["n_violations"]),
        "n_non_converged": sum(1 for r in rows if not r["converged"]),
        "n_islanding": sum(1 for r in rows if r["islanded_load_mw"]),
        "worst": worst,
        "criteria": "AC power flow per single branch outage; same violation rules as acceptance; "
                    "no remedial action assumed after the second outage.",
    }


def evaluate_actions(
    adv: AdvisorNetwork, crisis: Crisis, actions: list[dict], cfg: AdvisorConfig | None = None
) -> dict:
    """Evaluate ONE fixed action list (no sizing) against ``crisis`` with the same AC checks and
    acceptance rules as :func:`advise`. Returns the candidate record."""
    cfg = cfg or AdvisorConfig()
    crisis_net, _ = apply_crisis(adv, crisis)
    crisis_state = evaluate_state(adv, copy.deepcopy(crisis_net))
    original = violation_keys(crisis_state)
    state = _solve(adv, crisis_net, actions)
    accepted, reasons, detail = _verdict(state, original, crisis_state["islanded_load_mw"])
    objective = _objective(adv, state, actions, cfg, crisis_state["generation_cost_eur_per_h"])
    return {
        "candidate_id": _candidate_id(actions),
        "actions": actions,
        "status": "accepted" if accepted else "rejected",
        "rejection_reasons": reasons,
        "violations": detail,
        "before": _summary(crisis_state),
        "after": _summary(state),
        "objective": objective,
        "explanation": _explain(adv, actions, crisis_state, state, accepted, reasons, objective),
    }


def proportional_shed_baseline(adv, crisis_net, crisis_state, original, cfg, ref_cost) -> dict:
    """Baseline: shed the same fraction of every supplied load (AC-bisected minimal fraction)."""
    supplied = [
        lid for lid in sorted(adv.loads)
        if act.load_p_mw(adv, crisis_net, lid) > 0
        and adv.bus_id_of(int(crisis_net.load.at[adv.loads[lid][0], "bus"]))
        not in set(crisis_state["islanded_buses"])
    ]
    cap = [{"load_id": lid, "shed_mw": act.load_p_mw(adv, crisis_net, lid) * 0.99}
           for lid in supplied]
    draft = cand.Draft(actions=[{"type": "load_shed", "loads": cap}], origin="baseline")
    row = _evaluate_draft(adv, crisis_net, crisis_state, draft, original, cfg, ref_cost)
    row.pop("_state")
    total = sum(act.load_p_mw(adv, crisis_net, lid) for lid in supplied)
    shed = row["objective"]["load_shed_mw"]
    return {
        "policy": "proportional_load_shed",
        "description": "Uniform fraction of every supplied load shed (constant power factor); "
                       "fraction found by AC bisection, max 99 %.",
        "shed_fraction": _r(shed / total, 6) if total else None,
        "status": row["status"],
        "rejection_reasons": row["rejection_reasons"],
        "after": row["after"],
        "objective": row["objective"],
    }


def advise(
    adv: AdvisorNetwork, crisis: Crisis, cfg: AdvisorConfig | None = None
) -> dict:
    """Run the advisor and return the deterministic ``gridstorm-advisor/1.0`` payload."""
    cfg = cfg or AdvisorConfig()
    base_net = adv.copy_net()
    base_state = evaluate_state(adv, base_net)
    crisis_net, notes = apply_crisis(adv, crisis)
    crisis_state = evaluate_state(adv, copy.deepcopy(crisis_net))
    original = violation_keys(crisis_state)
    base_keys = violation_keys(base_state)
    ref_cost = crisis_state["generation_cost_eur_per_h"]

    crisis_summary = _summary(crisis_state)
    for v in crisis_summary["violations"]:
        v["pre_existing_in_base_case"] = (v["kind"], v["asset_id"]) in base_keys
    crisis_summary["branch_loading_pct"] = crisis_state["branch_loading_pct"]
    crisis_summary["bus_vm_pu"] = crisis_state["bus_vm_pu"]

    payload = {
        "schema_version": SCHEMA_VERSION,
        "network_id": adv.network_id,
        "crisis": crisis.to_dict(),
        "crisis_notes": notes,
        "provenance": "calculated",
        "operating_point": adv.operating_point,
        "method": {
            "engine": "pandapower",
            "engine_version": pp.__version__,
            "power_flow": {k: v for k, v in PF_OPTIONS.items()} | {"init": "dc, retry flat"},
            "loading_basis": adv.loading_basis,
            "candidate_sensitivities": "DC PTDF/LODF (ranking and initial sizing only)",
            "config": cfg.to_dict(),
        },
        "objective": {
            "definition": "objective_eur = generation_cost_eur (MATPOWER gencost of the "
                          "post-action AC dispatch incl. slack, over assumed_duration_h) + "
                          "voll_eur_per_mwh * load_shed_mw * assumed_duration_h + "
                          "switching_penalty_eur * n_switching_actions",
            "ranking": "accepted candidates sorted by (objective_eur, max branch loading after, "
                       "candidate_id)",
            "voll_eur_per_mwh": cfg.voll_eur_per_mwh,
            "switching_penalty_eur": cfg.switching_penalty_eur,
            "assumed_duration_h": cfg.assumed_duration_h,
            "notes": "VOLL and switching penalty are modelling conventions, not market data.",
        },
        "acceptance_rules": ACCEPTANCE_RULES,
        "base_state": _summary(base_state),
        "crisis_state": crisis_summary,
    }

    if not original:
        payload.update({
            "outcome": "no_violation",
            "candidates": [], "ranking": [], "recommendation": None,
            "baselines": {"do_nothing": {"policy": "do_nothing", "status": "accepted",
                                         "after": _summary(crisis_state)}},
            "n_minus_1": None,
            "security_statement": "The crisis state has no thermal/voltage/slack violation in "
                                  "the AC steady state; no action proposed. N-1 not checked.",
            "assumptions": adv.assumptions,
        })
        return payload

    sens = sensitivity.compute(adv, crisis_net)
    drafts: list[cand.Draft] = []
    singles: dict[str, list[cand.Draft]] = {}
    if sens is not None:
        tg = cand.find_targets(adv, crisis_net, crisis_state, sens)
        singles = {
            "switching": cand.switching_drafts(adv, crisis_net, crisis_state, sens, tg, cfg.limits),
            "redispatch": cand.redispatch_drafts(
                adv, crisis_net, crisis_state, sens, tg, cfg.limits),
            "load_shed": cand.shed_drafts(adv, crisis_net, crisis_state, sens, tg, cfg.limits),
        }
        for kind in ("switching", "redispatch", "load_shed"):
            drafts.extend(singles[kind])
        drafts.extend(cand.combination_drafts(singles, cfg.limits))

    evaluated: list[dict] = []
    seen: set[str] = set()
    for d in drafts:
        row = _evaluate_draft(adv, crisis_net, crisis_state, d, original, cfg, ref_cost)
        if row["candidate_id"] in seen:
            continue
        seen.add(row["candidate_id"])
        evaluated.append(row)

    accepted = sorted(
        (c for c in evaluated if c["status"] == "accepted"),
        key=lambda c: (c["objective"]["objective_eur"], c["after"]["max_branch_loading_pct"],
                       c["candidate_id"]),
    )
    for i, c in enumerate(accepted, start=1):
        c["rank"] = i

    exclude = set(crisis.line_outages)
    n1 = []
    for c in accepted[: cfg.n_minus_1_top]:
        net = copy.deepcopy(crisis_net)
        act.apply(adv, net, c["actions"])
        res = n_minus_1(adv, net, exclude)
        c["n_minus_1"] = {k: res[k] for k in ("n_contingencies", "n_secure", "n_with_violations",
                                               "n_non_converged", "n_islanding")}
        n1.append({"candidate_id": c["candidate_id"], **res})
    base_n1 = n_minus_1(adv, adv.copy_net(), set())

    for c in evaluated:
        c.pop("_state")
    evaluated.sort(key=lambda c: (c["rank"] is None, c["rank"] or 0, c["origin"],
                                  c["candidate_id"]))

    baselines = {
        "do_nothing": {
            "policy": "do_nothing",
            "status": "rejected",
            "rejection_reasons": [_fmt_violation(v) for v in crisis_state["violations"]],
            "after": _summary(crisis_state),
            "objective": _objective(adv, crisis_state, [], cfg, ref_cost),
        },
        "proportional_load_shed": proportional_shed_baseline(
            adv, crisis_net, crisis_state, original, cfg, ref_cost),
    }
    top = accepted[0] if accepted else None
    n1_note = (
        f"AC N-1 re-checked for the top {len(n1)} accepted candidate(s) (single branch outages)."
        if n1 else "N-1 of the resulting state NOT checked (no accepted candidate)."
    )
    payload.update({
        "outcome": "recommended" if top else "no_accepted_candidate",
        "candidates": evaluated,
        "ranking": [c["candidate_id"] for c in accepted],
        "recommendation": None if top is None else {
            "candidate_id": top["candidate_id"],
            "actions": top["actions"],
            "objective": top["objective"],
            "explanation": top["explanation"],
            "n_minus_1": top.get("n_minus_1"),
        },
        "baselines": baselines,
        "comparison": _comparison(baselines, top),
        "n_minus_1": {"candidates": n1, "base_case_pre_crisis": base_n1},
        "counts": {
            "candidates_evaluated": len(evaluated),
            "accepted": len(accepted),
            "rejected": len(evaluated) - len(accepted),
            "by_origin": {k: sum(1 for c in evaluated if c["origin"] == k)
                          for k in ("switching", "redispatch", "load_shed", "combination")},
        },
        "security_statement": (
            "'Accepted' means: clears all thermal/voltage/slack-limit violations in the "
            "post-crisis AC steady state (single snapshot). " + n1_note + " Not checked: "
            "dynamic/transient stability, protection settings, ramp rates, reactive reserve "
            "adequacy beyond generator Q limits, time coupling. Not an operational instruction."
        ),
        "assumptions": adv.assumptions + [
            "Single-slack balancing: the slack generator absorbs all imbalance and loss changes.",
            "Load shedding reduces P and Q proportionally (constant power factor).",
            "Amounts are the smallest AC-bisected scale (to the configured resolution) that "
            "clears the original violations with originally overloaded branches at or below "
            f"{cfg.sizing_target_pct} % loading; post-action loadings close to that are expected.",
        ],
    })
    return payload


def _comparison(baselines: dict, top: dict | None) -> list[dict]:
    rows = []
    for key in ("do_nothing", "proportional_load_shed"):
        b = baselines[key]
        rows.append({
            "policy": key,
            "status": b["status"],
            "n_violations_after": b["after"]["n_violations"],
            "max_branch_loading_pct": b["after"]["max_branch_loading_pct"],
            "min_vm_pu": b["after"]["min_vm_pu"],
            "load_shed_mw": b["objective"]["load_shed_mw"],
            "objective_eur": b["objective"]["objective_eur"],
        })
    if top is not None:
        rows.append({
            "policy": "advisor_top_candidate",
            "candidate_id": top["candidate_id"],
            "status": top["status"],
            "n_violations_after": top["after"]["n_violations"],
            "max_branch_loading_pct": top["after"]["max_branch_loading_pct"],
            "min_vm_pu": top["after"]["min_vm_pu"],
            "load_shed_mw": top["objective"]["load_shed_mw"],
            "objective_eur": top["objective"]["objective_eur"],
        })
    return rows
