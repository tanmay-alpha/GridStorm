"""StormSpec -> Grid2Op mapping (engine ``grid2op``, formulation ``sequential``).

What is supported (and nothing else):

* ``dataset.network_id == "l2rpn-case14-sandbox"`` (the Grid2Op env ``l2rpn_case14_sandbox``).
  Asset ids are the Grid2Op names (``env.name_line``), unchanged.
* ``horizon``: snapshot ``i`` = Grid2Op time step ``i`` (5 min) of the selected chronic.
  ``horizon.start`` is applied with ``env.reset(options={"init ts": start})``; the trace has
  ``horizon.snapshots`` states (row 0 = state at ``horizon.start``), i.e. ``snapshots - 1``
  ``env.step`` calls.
* ``line_outage`` (lines and transformers are both Grid2Op "lines"): forced disconnection at
  ``window.start`` (``null`` window = whole horizon). At the horizon start it is applied through
  ``env.reset(options={"init state": ...})``; later it overrides the agent's action of that step
  with ``set_line_status = -1``. Until ``window.end`` agent attempts to reconnect the line are
  replaced by do-nothing (flagged ``blocked_by_scenario``). After ``window.end`` the agent MAY
  reconnect it (subject to Grid2Op cooldown rules) — Grid2Op never reconnects lines by itself.
* ``execution.solver``: ``null``/``"lightsim2grid"`` (LightSimBackend) or ``"pandapower"``.
* ``execution.seed`` seeds both the environment and the agent.

Rejected with ``unsupported_operation``: every other event type, notably ``demand_multiplier``
(Grid2Op 1.12 has no public API to scale load chronics consistently with the forecasts used by
``obs.simulate``, and the chronics' generator set-points are not re-dispatched, so the slack bus
would absorb the whole demand change), ``generator_outage``, ``renewable_availability_multiplier``,
``link_outage``, ``storage_state``; and ``mitigation.load_shedding.enabled = true``.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import grid2op
import stormspec
from stormspec.manifest import ExecutionManifest, detect_git_sha, utc_now_iso

from .agents import AGENTS
from .env import ENV_NAME, NETWORK_ID, env_info, grid_layout, make_env
from .episode import ForcedLineOutage, run_episode, sha256_json

STAGES = (
    "loading_network",
    "applying_scenario",
    "building_model",
    "solving",
    "postprocessing",
    "done",
)


class ScenarioRejected(ValueError):
    """Raised when a scenario cannot be represented by the Grid2Op adapter."""

    def __init__(self, issues: list[dict[str, str]]):
        self.issues = issues
        super().__init__("; ".join(f"{i['code']} at {i['path']}: {i['message']}" for i in issues))


def _issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def check_scenario(scenario: stormspec.Scenario, env=None) -> list[dict[str, str]]:
    """Return blocking issues (empty list = runnable). ``env`` enables asset/horizon checks."""
    issues = [i.model_dump() for i in stormspec.check_capabilities(scenario)]
    ex = scenario.execution
    if ex.engine != "grid2op":
        issues.append(
            _issue(
                "unsupported_operation",
                "execution.engine",
                f"this adapter runs engine 'grid2op', not {ex.engine!r}",
            )
        )
    if scenario.dataset.network_id != NETWORK_ID:
        issues.append(
            _issue(
                "network_mismatch",
                "dataset.network_id",
                f"Grid2Op adapter supports only {NETWORK_ID!r} "
                f"(env {ENV_NAME}), not {scenario.dataset.network_id!r}",
            )
        )
    if scenario.horizon.snapshots < 2:
        issues.append(
            _issue(
                "unsupported_operation",
                "horizon.snapshots",
                "a sequential episode needs at least 2 snapshots (1 env step)",
            )
        )
    for i, ev in enumerate(scenario.events):
        if ev.type != "line_outage":
            # Defence in depth: rejected even if the capability table were to list it.
            if not any(x["path"] == f"events[{i}].type" for x in issues):
                issues.append(
                    _issue(
                        "unsupported_operation",
                        f"events[{i}].type",
                        f"Grid2Op adapter does not support {ev.type!r}",
                    )
                )
            continue
        if env is not None and ev.asset_id not in {str(n) for n in env.name_line}:
            issues.append(
                _issue(
                    "unknown_asset",
                    f"events[{i}].asset_id",
                    f"no Grid2Op line {ev.asset_id!r} in {ENV_NAME}",
                )
            )
        w = ev.window
        if w is not None and not (
            scenario.horizon.start <= w.start < scenario.horizon.end
            and w.end <= scenario.horizon.end
        ):
            issues.append(
                _issue(
                    "window_outside_horizon",
                    f"events[{i}].window",
                    "window must lie inside the horizon",
                )
            )
    if env is not None:
        n_ts = int(env.chronics_handler.max_timestep())
        if n_ts > 0 and scenario.horizon.end > n_ts:
            issues.append(
                _issue(
                    "horizon_out_of_range",
                    "horizon",
                    f"horizon end {scenario.horizon.end} exceeds chronic length {n_ts}",
                )
            )
    return issues


def run_scenario(
    scenario: stormspec.Scenario | dict,
    *,
    agent: str = "reco_powerline",
    chronics_id: int = 0,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Run a StormSpec scenario as one bounded Grid2Op episode.

    ``agent`` and ``chronics_id`` are Grid2Op-specific run parameters not expressible in
    stormspec/1.0; they are recorded in the result. Raises :class:`ScenarioRejected` for
    unsupported scenarios (never approximates).
    """
    if agent not in AGENTS:
        raise ValueError(f"unknown agent {agent!r}; expected one of {AGENTS}")
    if not isinstance(scenario, stormspec.Scenario):
        scenario = stormspec.Scenario.model_validate(scenario)
    stage = progress or (lambda _s: None)
    issues = check_scenario(scenario)
    if issues:
        raise ScenarioRejected(issues)

    started = utc_now_iso()
    t0 = time.perf_counter()
    stage("loading_network")
    backend = scenario.execution.solver or "lightsim2grid"
    env = make_env(backend)
    try:
        stage("applying_scenario")
        env.set_id(int(chronics_id))
        env.reset(seed=int(scenario.execution.seed))
        issues = check_scenario(scenario, env)
        if issues:
            raise ScenarioRejected(issues)
        h = scenario.horizon
        outages = []
        for ev in scenario.events:  # only line_outage remains after checks
            w = ev.window
            start = (w.start if w is not None else h.start) - h.start
            end = (w.end - h.start) if w is not None else None
            outages.append(ForcedLineOutage(line=ev.asset_id, start_row=start, end_row=end))
        stage("building_model")
        info = env_info(env, backend)
        layout = grid_layout(env)
        stage("solving")
        payload = run_episode(
            env,
            agent,
            chronics_id=chronics_id,
            env_seed=scenario.execution.seed,
            agent_seed=scenario.execution.seed,
            max_steps=h.snapshots - 1,
            start_ts=h.start,
            outages=tuple(outages),
        )
    finally:
        env.close()
    stage("postprocessing")
    wall = time.perf_counter() - t0
    result = build_result(scenario, payload, info, layout, agent, wall)
    finished = utc_now_iso()
    manifest = ExecutionManifest(
        scenario_hash=result["scenario_hash"],
        dataset_sha256=info["dataset"]["extracted_dir_sha256"],
        engine_name="grid2op",
        engine_version=grid2op.__version__,
        solver_name=backend,
        solver_version=info["backend_version"],
        solver_options={"agent": agent, "chronics_id": int(chronics_id)},
        package_versions={k: v for k, v in {"pandapower": info["pandapower_version"]}.items() if v},
        started_at=started,
        finished_at=finished,
        result_sha256=sha256_json(result),
        git_sha=detect_git_sha(),
    )
    result["manifest"] = manifest.model_dump(mode="json")
    stage("done")
    return result


def build_result(scenario, payload, info, layout, agent, wall_time_s) -> dict[str, Any]:
    """Map an episode payload to the gridstorm-result/1.0 envelope.

    Quantities Grid2Op does not model here (costs, load shedding, curtailment, storage,
    prices, CO2) are ``null`` — never invented.
    """
    steps = payload["steps"]
    kpis = payload["kpis"]
    dt_h = info["delta_time_min"] / 60.0
    valid = [i for i, r in enumerate(steps["rho"]) if r is not None]
    names = [ln["id"] for ln in layout["lines"]]
    outaged = {c["line"] for c in payload["crisis"]}
    congested = set()
    for i in valid:
        for j, (r, on) in enumerate(zip(steps["rho"][i], steps["line_status"][i], strict=True)):
            if on and r >= 0.999:
                congested.add(j)
    total_load_mwh = round(sum(steps["load_mw"][i] for i in valid) * dt_h, 4)
    game_over = payload["game_over"]
    termination = payload["episode"]["episode_end"]
    return {
        "schema_version": "gridstorm-result/1.0",
        "scenario_id": scenario.id,
        "scenario_hash": stormspec.scenario_hash(scenario),
        "network_id": NETWORK_ID,
        "engine": {
            "name": "grid2op",
            "version": grid2op.__version__,
            "formulation": "sequential",
            "backend": info["backend"],
            "backend_version": info["backend_version"],
            "agent": agent,
            "chronics_id": payload["episode"]["chronics_id"],
        },
        "solver": {
            "name": info["backend"],
            "version": info["backend_version"],
            "status": "ok" if game_over is None else "warning",
            "termination_condition": termination,
            "objective_eur": None,
            "wall_time_s": round(wall_time_s, 3),
        },
        # A Grid2Op game over (blackout / non-convergent power flow) is reported as infeasible.
        "outcome": "feasible" if game_over is None else "infeasible",
        "snapshots": [steps["datetime"][i] for i in valid],
        "snapshot_weightings_h": [dt_h for _ in valid],
        "metrics": {
            "total_load_mwh": total_load_mwh,
            "served_load_mwh": None,
            "unserved_energy_mwh": None,
            "peak_load_shed_mw": None,
            "load_shed_hours": None,
            "total_system_cost_eur": None,
            "generation_cost_eur": None,
            "load_shedding_cost_eur": None,
            "generation_by_carrier_mwh": None,
            "curtailment_mwh": None,
            "curtailment_by_carrier_mwh": None,
            "max_line_loading_pct": None
            if kpis["max_rho"] is None
            else round(kpis["max_rho"] * 100, 2),
            "mean_line_loading_pct": None
            if kpis["mean_rho"] is None
            else round(kpis["mean_rho"] * 100, 2),
            "congested_line_count": len(congested),
            "storage_discharge_mwh": None,
            "storage_charge_mwh": None,
            "co2_emissions_t": None,
            "balance_residual_max_mw": None,
        },
        "series": {
            "load_mw": [steps["load_mw"][i] for i in valid],
            "generation_total_mw": [steps["gen_mw"][i] for i in valid],
        },
        "assets": {
            "lines": [
                {
                    "id": name,
                    "s_nom_mva": None,
                    "outaged": name in outaged,
                    "loading_pct": [round(steps["rho"][i][j] * 100, 2) for i in valid],
                    "connected": [steps["line_status"][i][j] for i in valid],
                }
                for j, name in enumerate(names)
            ],
        },
        "episode": {
            "kpis": kpis,
            "game_over": game_over,
            "layout": layout,
            "env": info,
            "trace": payload,
        },
        "assumptions": [
            "Sequential AC power flow (Grid2Op + backend) on synthetic l2rpn_case14_sandbox "
            "chronics; generator set-points come from the chronics, the slack absorbs imbalances",
            "line loading = rho = |I| / thermal limit (current-based), not MVA-based",
            "Grid2Op protections disconnect lines after NB_TIMESTEP_OVERFLOW_ALLOWED steps above "
            "the limit, or immediately above HARD_OVERFLOW_THRESHOLD",
            "A game over (blackout / diverged power flow) is reported as outcome 'infeasible'",
            "Costs, load shedding, curtailment, storage and prices are not modelled (null)",
            "Simulation survival is not evidence of operational safety (Marot et al. 2021, "
            "arXiv:2103.03104)",
        ],
        "warnings": list(payload["warnings"]),
    }
