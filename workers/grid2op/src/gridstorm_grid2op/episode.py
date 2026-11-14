"""Run one bounded Grid2Op episode and export a compact, columnar trace with KPIs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import numpy as np

from .agents import AGENT_DESCRIPTIONS, GreedySimulateAgent, make_agent
from .kpis import KPI_DEFINITIONS, compute_kpis

TRACE_SCHEMA = "gridstorm-grid2op-episode/1.0"


@dataclass(frozen=True)
class ForcedLineOutage:
    """Scenario-imposed disconnection of ``line`` (Grid2Op line name).

    ``start_row`` is the trace row (0 = initial state) from which the line is out. Row 0 is
    realised through ``env.reset(options={"init state": ...})``; row k >= 1 by overriding the
    agent's action of the k-th ``env.step`` with ``set_line_status = -1``. Until ``end_row``
    (exclusive; ``None`` = end of episode) agent actions that would reconnect the line are replaced
    by do-nothing and flagged ``blocked_by_scenario``.
    """

    line: str
    start_row: int
    end_row: int | None = None

    def active_at_step(self, k: int) -> bool:
        """True if the reconnection must be blocked for the k-th env.step (producing row k)."""
        return k > self.start_row and (self.end_row is None or k < self.end_row)


def canonical_dumps(obj: Any) -> bytes:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def sha256_json(obj: Any) -> str:
    return hashlib.sha256(canonical_dumps(obj)).hexdigest()


def trace_hash(payload: dict[str, Any]) -> str:
    """Hash of the simulated content (steps + game over), independent of metadata/timestamps."""
    return sha256_json({"steps": payload["steps"], "game_over": payload["game_over"]})


def _r4(x) -> float:
    return round(float(x), 4)


def action_summary(act, name_line, name_gen, name_sub) -> dict[str, Any]:
    """Type + targets of a Grid2Op action, derived from ``act.impact_on_objects()``."""
    imp = act.impact_on_objects()
    types: list[str] = []
    targets: list[str] = []
    fl = imp["force_line"]
    reco = [int(i) for i in fl["reconnections"]["powerlines"]]
    disc = [int(i) for i in fl["disconnections"]["powerlines"]]
    switch = [int(i) for i in imp["switch_line"]["powerlines"]]
    if reco:
        types.append("reconnect_line")
        targets += [str(name_line[i]) for i in reco]
    if disc:
        types.append("disconnect_line")
        targets += [str(name_line[i]) for i in disc]
    if switch:
        types.append("switch_line")
        targets += [str(name_line[i]) for i in switch]
    topo = imp["topology"]
    if topo["changed"]:
        subs = sorted(
            {
                int(e["substation"])
                for key in ("bus_switch", "assigned_bus", "disconnect_bus")
                for e in topo[key]
            }
        )
        types.append("topology")
        targets += [str(name_sub[s]) for s in subs]
    red = imp["redispatch"]
    redispatch_mw = {}
    if red["changed"]:
        types.append("redispatch")
        for g in red["generators"]:
            gid = int(g["gen_id"])
            targets.append(str(name_gen[gid]))
            redispatch_mw[str(name_gen[gid])] = _r4(g["amount"])
    other = [k for k in ("injection", "curtailment", "storage") if imp.get(k, {}).get("changed")]
    types += other
    out: dict[str, Any] = {"type": "+".join(types) if types else "do_nothing", "targets": targets}
    if redispatch_mw:
        out["redispatch_mw"] = redispatch_mw
    return out


def _reconnects(act, line_id: int) -> bool:
    imp = act.impact_on_objects()
    return line_id in {int(i) for i in imp["force_line"]["reconnections"]["powerlines"]} or (
        line_id in {int(i) for i in imp["switch_line"]["powerlines"]}
    )


def _topo_distance(obs) -> int:
    n_split = 0
    for s in range(obs.n_sub):
        if np.any(obs.sub_topology(s) == 2):
            n_split += 1
    return int(np.sum(~obs.line_status)) + n_split


def _state_row(obs) -> dict[str, Any]:
    return {
        "datetime": obs.get_time_stamp().isoformat(),
        "rho": [_r4(x) for x in obs.rho],
        "line_status": [bool(x) for x in obs.line_status],
        "load_mw": _r4(np.sum(obs.load_p)),
        "gen_mw": _r4(np.sum(obs.gen_p)),
        "topo_distance": _topo_distance(obs),
    }


def run_episode(
    env,
    agent_name: str,
    *,
    chronics_id: int,
    env_seed: int,
    agent_seed: int,
    max_steps: int,
    start_ts: int = 0,
    outages: tuple[ForcedLineOutage, ...] = (),
) -> dict[str, Any]:
    """Run one episode of at most ``max_steps`` env steps and return the artifact payload."""
    name_line = [str(x) for x in env.name_line]
    line_index = {n: i for i, n in enumerate(name_line)}
    for o in outages:
        if o.line not in line_index:
            raise ValueError(f"unknown Grid2Op line {o.line!r}")
        if o.start_row > max_steps:
            raise ValueError(f"outage start row {o.start_row} beyond episode ({max_steps} steps)")

    options: dict[str, Any] = {"time serie id": int(chronics_id)}
    if start_ts:
        options["init ts"] = int(start_ts)
    init_out = [line_index[o.line] for o in outages if o.start_row == 0]
    if init_out:
        options["init state"] = {"set_line_status": [(i, -1) for i in init_out]}
    obs = env.reset(seed=int(env_seed), options=options)
    agent = make_agent(agent_name, env, agent_seed)
    blocked_now: set[int] = set()
    if isinstance(agent, GreedySimulateAgent):
        agent.blocked_lines = lambda: set(blocked_now)

    steps: dict[str, list] = {
        k: []
        for k in (
            "t",
            "datetime",
            "rho",
            "line_status",
            "action",
            "reward",
            "load_mw",
            "gen_mw",
            "topo_distance",
        )
    }

    def push(t, row, action, reward):
        steps["t"].append(t)
        for k in ("datetime", "rho", "line_status", "load_mw", "gen_mw", "topo_distance"):
            steps[k].append(row[k] if row is not None else None)
        steps["action"].append(action)
        steps["reward"].append(reward)

    push(0, _state_row(obs), None, None)
    chronics_name = str(env.chronics_handler.get_name())
    reward, done, game_over, episode_end = 0.0, False, None, "max_steps"
    warnings: list[str] = []
    do_nothing = env.action_space({})
    for k in range(1, max_steps + 1):
        blocked_now.clear()
        blocked_now.update(line_index[o.line] for o in outages if o.active_at_step(k))
        proposed = agent.act(obs, reward, done)
        applied, source, blocked = proposed, "agent", False
        forced = [o for o in outages if o.start_row == k]
        if forced:
            applied = env.action_space(
                {"set_line_status": [(line_index[o.line], -1) for o in forced]}
            )
            source = "scenario"
        elif any(_reconnects(proposed, lid) for lid in blocked_now):
            applied, blocked = do_nothing, True
        summary = action_summary(applied, name_line, env.name_gen, env.name_sub)
        if blocked:
            summary["blocked_by_scenario"] = True
            summary["proposed"] = action_summary(proposed, name_line, env.name_gen, env.name_sub)
        summary["source"] = source
        if source == "agent" and isinstance(agent, GreedySimulateAgent) and agent.last_decision:
            summary["decision"] = dict(agent.last_decision)
        obs, reward, done, info = env.step(applied)
        summary["illegal"] = bool(info.get("is_illegal", False))
        summary["ambiguous"] = bool(info.get("is_ambiguous", False))
        if source == "scenario" and summary["illegal"]:
            warnings.append(
                f"step {k}: forced outage of {[o.line for o in forced]} was declared illegal by "
                "Grid2Op (line cooldown) and not applied"
            )
        exceptions = [f"{type(e).__name__}: {e}" for e in info.get("exception", []) or []]
        if done and exceptions:
            push(k, None, summary, _r4(reward))
            game_over = {"step": k, "reasons": exceptions}
            episode_end = "game_over"
            break
        push(k, _state_row(obs), summary, _r4(reward))
        if done:
            episode_end = "chronics_end"
            break

    payload: dict[str, Any] = {
        "schema_version": TRACE_SCHEMA,
        "provenance": {
            "inputs": "synthetic",
            "trace": "modeled",
            "kpis": "calculated",
            "note": "Chronics of l2rpn_case14_sandbox are synthetic time series; every state is a "
            "Grid2Op/backend AC power-flow result (modeled), not a measurement.",
        },
        "episode": {
            "chronics_id": int(chronics_id),
            "chronics_name": chronics_name,
            "env_seed": int(env_seed),
            "agent_seed": int(agent_seed),
            "start_ts": int(start_ts),
            "max_steps": int(max_steps),
            "steps_recorded": len(steps["t"]) - 1,
            "episode_end": episode_end,
        },
        "agent": {"name": agent_name, "description": AGENT_DESCRIPTIONS[agent_name]},
        "crisis": [
            {
                "type": "forced_line_outage",
                "line": o.line,
                "start_row": o.start_row,
                "end_row": o.end_row,
            }
            for o in outages
        ],
        "steps": steps,
        "game_over": game_over,
        "warnings": warnings,
        "kpi_definitions": KPI_DEFINITIONS,
    }
    payload["kpis"] = compute_kpis(steps, game_over, max_steps)
    payload["trace_sha256"] = trace_hash(payload)
    return payload
