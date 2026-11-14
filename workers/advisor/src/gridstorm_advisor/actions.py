"""Remedial action primitives and their application to a pandapower net copy.

Action dicts (JSON-native, asset ids only):
- ``{"type": "redispatch", "gen_up": id, "gen_down": id, "delta_mw": x}``: raise ``gen_up`` and
  lower ``gen_down`` by ``x`` MW. A slack generator is never given a setpoint: it absorbs the
  change (plus any change in losses) through the power-flow balance.
- ``{"type": "load_shed", "loads": [{"load_id": id, "shed_mw": x}, ...]}``: reduce active and
  reactive demand of each load by the same fraction (constant power factor).
- ``{"type": "open_branch", "branch_id": id}``: switch a line/transformer out of service.
"""

from __future__ import annotations

import pandapower as pp

from gridstorm_advisor.network import AdvisorNetwork, ElementRef

SCALABLE = ("redispatch", "load_shed")


def is_slack(net: pp.pandapowerNet, ref: ElementRef) -> bool:
    if ref.table == "ext_grid":
        return True
    return ref.table == "gen" and bool(net.gen.at[ref.index, "slack"])


def load_p_mw(adv: AdvisorNetwork, net: pp.pandapowerNet, load_id: str) -> float:
    idx = adv.loads[load_id]
    ld = net.load.loc[idx]
    return float((ld.p_mw * ld.scaling)[ld.in_service].sum())


def scaled(action: dict, lam: float) -> dict:
    """Copy of ``action`` with its MW amounts multiplied by ``lam`` (switching is unchanged)."""
    if action["type"] == "redispatch":
        return {**action, "delta_mw": action["delta_mw"] * lam}
    if action["type"] == "load_shed":
        return {
            **action,
            "loads": [{**e, "shed_mw": e["shed_mw"] * lam} for e in action["loads"]],
        }
    return dict(action)


def apply(adv: AdvisorNetwork, net: pp.pandapowerNet, actions: list[dict]) -> None:
    """Apply ``actions`` to ``net`` in place (callers pass a deep copy)."""
    for a in actions:
        kind = a["type"]
        if kind == "open_branch":
            ref = adv.branches[a["branch_id"]]
            net[ref.table].loc[ref.index, "in_service"] = False
        elif kind == "redispatch":
            for gid, sign in ((a["gen_up"], 1.0), (a["gen_down"], -1.0)):
                ref = adv.generators[gid]
                if is_slack(net, ref):
                    continue
                net[ref.table].loc[ref.index, "p_mw"] += sign * a["delta_mw"]
        elif kind == "load_shed":
            for entry in a["loads"]:
                idx = adv.loads[entry["load_id"]]
                total = load_p_mw(adv, net, entry["load_id"])
                if total <= 0:
                    continue
                keep = max(0.0, 1.0 - entry["shed_mw"] / total)
                net.load.loc[idx, "p_mw"] *= keep
                net.load.loc[idx, "q_mvar"] *= keep
        else:
            raise ValueError(f"unknown action type {kind!r}")


def shed_mw(actions: list[dict]) -> float:
    return float(
        sum(e["shed_mw"] for a in actions if a["type"] == "load_shed" for e in a["loads"])
    )


def n_switching(actions: list[dict]) -> int:
    return sum(1 for a in actions if a["type"] == "open_branch")


def describe(adv: AdvisorNetwork, action: dict) -> str:
    kind = action["type"]
    if kind == "open_branch":
        return f"open {action['branch_id']}"
    if kind == "redispatch":
        return (
            f"shift {action['delta_mw']:.1f} MW from {action['gen_down']} to {action['gen_up']}"
        )
    parts = ", ".join(f"{e['shed_mw']:.1f} MW at {e['load_id']}" for e in action["loads"])
    return f"shed {parts}"
