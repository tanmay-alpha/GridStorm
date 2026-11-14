"""Episode KPIs computed from a compact GridStorm episode trace.

The KPI *concepts* follow grid2viz (survival over max steps, overflow counts, action counts,
cumulative reward, usage-rate statistics, topological distance) but this is an independent
implementation (see docs/audit/grid2viz-audit.md); no grid2viz code is used.

Trace layout (columnar, row ``i`` = state after step ``t[i]``; row 0 is the initial state):

* ``t``: step index (0 = initial observation, k = state after the k-th ``env.step``).
* ``rho``: per-line loading ratio ``|I| / I_thermal`` or ``None`` on the game-over row.
* ``line_status``: per-line connection status (bool) or ``None`` on the game-over row.
* ``action``: ``None`` on row 0, else ``{"type", "targets", "source", "illegal", ...}``.
* ``reward``: ``None`` on row 0, else the env reward of that step.
* ``topo_distance``: #disconnected lines + #substations with any element on bus 2 (or ``None``).

This module has no Grid2Op dependency so it can be tested on synthetic traces.
"""

from __future__ import annotations

from typing import Any

#: rho strictly above this value counts as an overload (thermal limit exceeded).
OVERLOAD_RHO = 1.0


def _r(x: float) -> float:
    return round(float(x), 4)


def survival_steps(steps: dict[str, Any], game_over: dict[str, Any] | None) -> int:
    """Number of steps played without game over.

    If the game is over at step ``k`` (the k-th ``env.step`` produced an invalid grid), the
    operator survived ``k - 1`` steps. Otherwise every recorded step survived.
    """
    if game_over is not None:
        return int(game_over["step"]) - 1
    return len(steps["t"]) - 1


def compute_kpis(
    steps: dict[str, Any], game_over: dict[str, Any] | None, max_steps: int
) -> dict[str, Any]:
    """Compute episode KPIs. All values are ``calculated`` from the (modeled) trace."""
    n_rows = len(steps["t"])
    for key in ("rho", "line_status", "action", "reward"):
        if len(steps[key]) != n_rows:
            raise ValueError(f"trace column {key!r} has {len(steps[key])} rows, expected {n_rows}")

    surv = survival_steps(steps, game_over)

    overload_line_steps = 0
    steps_with_overload = 0
    rho_sum = 0.0
    rho_n = 0
    rho_max: float | None = None
    max_rho_line: int | None = None
    # Usage statistics over states produced by the operator's actions (rows t >= 1).
    for i in range(1, n_rows):
        rho = steps["rho"][i]
        status = steps["line_status"][i]
        if rho is None or status is None:
            continue
        n_over = 0
        for j, (r, on) in enumerate(zip(rho, status, strict=True)):
            if not on:
                continue
            rho_sum += r
            rho_n += 1
            if rho_max is None or r > rho_max:
                rho_max = r
                max_rho_line = j
            if r > OVERLOAD_RHO:
                n_over += 1
        overload_line_steps += n_over
        steps_with_overload += 1 if n_over else 0

    disconnection_events = 0
    reconnection_events = 0
    prev = steps["line_status"][0]
    for i in range(1, n_rows):
        cur = steps["line_status"][i]
        if cur is None:
            continue
        if prev is not None:
            for a, b in zip(prev, cur, strict=True):
                if a and not b:
                    disconnection_events += 1
                elif b and not a:
                    reconnection_events += 1
        prev = cur

    actions_count = 0
    actions_by_type: dict[str, int] = {}
    illegal_actions = 0
    blocked_actions = 0
    forced_events = 0
    for act in steps["action"][1:]:
        if act is None:
            continue
        if act.get("source") == "scenario":
            forced_events += 1
            continue
        if act.get("blocked_by_scenario"):
            blocked_actions += 1
        if act.get("illegal"):
            illegal_actions += 1
            continue
        if act["type"] != "do_nothing":
            actions_count += 1
            actions_by_type[act["type"]] = actions_by_type.get(act["type"], 0) + 1

    rewards = [r for r in steps["reward"][1:] if r is not None]
    dists = [d for d in steps.get("topo_distance", []) if d is not None]

    return {
        "survival_steps": surv,
        "max_steps": int(max_steps),
        "survived": game_over is None and surv >= max_steps,
        "survival_ratio": _r(surv / max_steps) if max_steps else None,
        "overload_line_steps": overload_line_steps,
        "steps_with_overload": steps_with_overload,
        "disconnection_events": disconnection_events,
        "reconnection_events": reconnection_events,
        "actions_count": actions_count,
        "actions_by_type": dict(sorted(actions_by_type.items())),
        "illegal_actions": illegal_actions,
        "blocked_actions": blocked_actions,
        "forced_events": forced_events,
        "cumulative_reward": _r(sum(rewards)) if rewards else 0.0,
        "mean_rho": _r(rho_sum / rho_n) if rho_n else None,
        "max_rho": _r(rho_max) if rho_max is not None else None,
        "max_rho_line_index": max_rho_line,
        "max_topological_distance": max(dists) if dists else None,
        "game_over_reasons": list(game_over["reasons"]) if game_over else [],
    }


#: Human-readable definitions shipped inside every artifact so numbers are self-describing.
KPI_DEFINITIONS: dict[str, str] = {
    "survival_steps": "env steps played before game over (game over at step k => k-1); "
    "equals max_steps if the bounded episode completed",
    "survived": "true iff no game over within max_steps",
    "overload_line_steps": "sum over played steps of the number of connected lines with rho > 1",
    "steps_with_overload": "number of played steps with at least one connected line at rho > 1",
    "disconnection_events": "connected->disconnected line transitions between consecutive valid "
    "states (protection trips, forced outages, maintenance or agent actions)",
    "reconnection_events": "disconnected->connected line transitions",
    "actions_count": "agent steps whose applied action is legal and not do-nothing (illegal "
    "and scenario-forced actions excluded)",
    "illegal_actions": "agent actions Grid2Op declared illegal (replaced by do-nothing by the env)",
    "blocked_actions": "agent actions replaced by do-nothing because they tried to reconnect a "
    "line inside a scenario outage window",
    "forced_events": "steps whose action was imposed by the scenario (forced line outage)",
    "cumulative_reward": "sum of the environment reward over played steps, including the "
    "game-over step (reward class recorded in env.reward_class)",
    "mean_rho": "mean rho over connected lines and valid played states",
    "max_rho": "max rho over connected lines and valid played states",
    "max_topological_distance": "max over states of #disconnected lines + #substations with any "
    "element on bus 2",
}
