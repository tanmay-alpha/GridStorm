"""Baseline agents used by GridStorm's sequential experiments.

* ``do_nothing`` — Grid2Op ``DoNothingAgent``: never acts.
* ``reco_powerline`` — Grid2Op ``RecoPowerlineAgent``: each step, uses ``obs.simulate`` to compare
  do-nothing against reconnecting each disconnected line whose cooldown has expired, and applies
  the best-rewarded one.
* ``greedy_simulate`` — GridStorm's transparent baseline (:class:`GreedySimulateAgent`).

All agents are deterministic given the environment seed (``agent.seed`` is still called with a
fixed seed for completeness).
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from grid2op.Agent import BaseAgent, DoNothingAgent, RecoPowerlineAgent

AGENTS = ("do_nothing", "reco_powerline", "greedy_simulate")

AGENT_DESCRIPTIONS = {
    "do_nothing": "Grid2Op DoNothingAgent: never takes an action.",
    "reco_powerline": "Grid2Op RecoPowerlineAgent: simulates do-nothing and the reconnection of "
    "each reconnectable disconnected line (cooldown expired) and applies the one with the best "
    "simulated reward.",
    "greedy_simulate": "GridStorm GreedySimulateAgent: if max rho < 0.95, reconnects a "
    "disconnected line when the one-step simulation keeps max rho < 0.95, else does nothing. If "
    "max rho >= 0.95 it simulates (obs.simulate, forecast-based) do-nothing, line reconnections, "
    "every unitary substation topology (get_all_unitary_topologies_set) and +/- max-ramp "
    "redispatch of each redispatchable generator, and applies the legal candidate with the lowest "
    "simulated max rho (+1 per additionally disconnected line; simulated game over = excluded). "
    "Ties keep the earliest candidate (do-nothing first).",
}


class GreedySimulateAgent(BaseAgent):
    """Transparent greedy one-step look-ahead over a small, enumerable action set.

    The score of a candidate is ``max(sim_obs.rho) + n_new_disconnections``; candidates whose
    simulation is game over, illegal or ambiguous are discarded. The simulated values are
    *estimates* based on Grid2Op forecasts, not observed outcomes.
    """

    def __init__(self, action_space, rho_threshold: float = 0.95):
        super().__init__(action_space)
        self.rho_threshold = float(rho_threshold)
        self.topo_actions = list(action_space.get_all_unitary_topologies_set(action_space))
        self.redisp_actions = []
        gen_ids = np.flatnonzero(action_space.gen_redispatchable)
        for gid in gen_ids:
            ramp_up = float(action_space.gen_max_ramp_up[gid])
            ramp_down = float(action_space.gen_max_ramp_down[gid])
            if ramp_up > 0:
                self.redisp_actions.append(action_space({"redispatch": [(int(gid), ramp_up)]}))
            if ramp_down > 0:
                self.redisp_actions.append(action_space({"redispatch": [(int(gid), -ramp_down)]}))
        self.blocked_lines: Callable[[], set[int]] = set
        self.last_decision: dict | None = None

    def n_candidates(self) -> int:
        return 1 + len(self.topo_actions) + len(self.redisp_actions)

    def _reconnections(self, obs) -> list:
        blocked = self.blocked_lines()
        acts = []
        for lid in np.flatnonzero(~obs.line_status):
            if int(lid) in blocked or obs.time_before_cooldown_line[lid] > 0:
                continue
            acts.append(self.action_space({"set_line_status": [(int(lid), 1)]}))
        return acts

    def _score(self, obs, act) -> float | None:
        sim_obs, _r, sim_done, sim_info = obs.simulate(act)
        if sim_done or sim_info.get("is_illegal") or sim_info.get("is_ambiguous"):
            return None
        if sim_info.get("exception"):
            return None
        new_disc = int(np.sum(obs.line_status & ~sim_obs.line_status))
        return float(np.max(sim_obs.rho)) + new_disc

    def act(self, observation, reward, done=False):
        obs = observation
        do_nothing = self.action_space({})
        max_rho = float(np.max(obs.rho))
        recos = self._reconnections(obs)
        if max_rho < self.rho_threshold:
            best, best_score = do_nothing, None
            for a in recos:
                s = self._score(obs, a)
                if (
                    s is not None
                    and s < self.rho_threshold
                    and (best_score is None or s < best_score)
                ):
                    best, best_score = a, s
            self.last_decision = {
                "mode": "safe",
                "observed_max_rho": round(max_rho, 4),
                "candidates": len(recos),
                "simulated_max_rho": None if best_score is None else round(best_score, 4),
            }
            return best
        candidates = [do_nothing, *recos, *self.topo_actions, *self.redisp_actions]
        best, best_score = do_nothing, None
        for a in candidates:
            s = self._score(obs, a)
            if s is not None and (best_score is None or s < best_score):
                best, best_score = a, s
        self.last_decision = {
            "mode": "alert",
            "observed_max_rho": round(max_rho, 4),
            "candidates": len(candidates),
            "simulated_max_rho": None if best_score is None else round(best_score, 4),
        }
        return best


def make_agent(name: str, env, seed: int):
    if name == "do_nothing":
        agent = DoNothingAgent(env.action_space)
    elif name == "reco_powerline":
        agent = RecoPowerlineAgent(env.action_space)
    elif name == "greedy_simulate":
        agent = GreedySimulateAgent(env.action_space)
    else:
        raise ValueError(f"unknown agent {name!r}; expected one of {AGENTS}")
    agent.seed(int(seed))
    return agent
