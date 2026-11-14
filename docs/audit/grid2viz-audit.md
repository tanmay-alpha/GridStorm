# Audit: Grid2op/grid2viz (and a glance at Grid2op/grid2game)

Purpose: decide what GridStorm's Grid2Op worker (`workers/grid2op`, package `gridstorm_grid2op`)
should take from the reference episode-analysis tool for Grid2Op, and under which licence terms.

## Sources audited

| Repo | URL | Commit (pinned) | Commit date | Licence |
|---|---|---|---|---|
| grid2viz | https://github.com/Grid2op/grid2viz | `b416eba406b9ef45b103e546b5a593d846420b4f` | 2023-10-10 | MPL-2.0 (`LICENSE`, SPDX headers in every audited file) |
| grid2game | https://github.com/Grid2op/grid2game | `d54084ddf387baa46870cce398e8a91f6281ee74` | 2022-07-05 | MPL-2.0 |

Local read-only clones: `D:/New folder (4)/upstream/grid2viz`, `D:/New folder (4)/upstream/grid2game`
(`git clone --filter=blob:none`). Nothing from these clones is copied into the GridStorm repo.

## Licence conclusion

MPL-2.0 is a file-level copyleft: a ported file would have to remain a separate file carrying the
MPL-2.0 header, with modifications noted, and its source made available. **No grid2viz or grid2game
code was ported.** GridStorm re-implements the KPI *concepts* below from their definitions (they are
simple aggregates over Grid2Op observations); the implementation lives in
`workers/grid2op/src/gridstorm_grid2op/kpis.py` under the repository licence. If a future change ports
code, it must go into its own file with the MPL-2.0 header (upstream repo, SHA, original path) and be
listed in the licence inventory.

## `grid2viz/src/kpi/` (943 + 410 + ~350 lines)

| File | What it does | Relevance to GridStorm |
|---|---|---|
| `EpisodeAnalytics.py` | Loads a stored `grid2op.Episode.EpisodeData` (runner output on disk) and builds pandas DataFrames: per-step load/production/rho (long format), action table (lines/subs/redispatch/curtail/storage counts per step, ids/names touched), instantaneous and cumulative reward, flows/voltages per line end, target/actual redispatch, attacks (opponent), hazards and maintenance. Computes a *topological distance* to the reference topology = `#disconnected lines + #substations with any element on bus 2` (`get_distance_from_obs`). Raises if the first observation is not fully on bus 1. | Concepts reused (re-implemented): per-step action summary (type + targets), cumulative reward, line status trace, topological distance. Not reused: pandas long-format tables (too large for 5 MB artifacts), `float16` downcasting of rho (loses precision — GridStorm rounds to 4 decimals instead), reliance on `EpisodeData` on disk. |
| `EpisodeTrace.py` | Plotly trace builders. `get_total_overflow_ts` counts lines with `obs.timestep_overflow > 0` per step ("Nb of overflows"); `get_usage_rate_trace` plots rho quantiles (10/25/median/75/90/max) per step. | Concepts reused: overflow count per step; GridStorm defines an overload as `rho > 1` on the *observation* (documented) and additionally reports mean/max rho. Quantile bands are left to the frontend (per-line rho is in the trace). |
| `observation_model.py` | Pivot helpers + `get_usage_rate` (rho quantiles by timestamp). | Same as above. |
| `actions_model.py` | Counts actions per line/substation/generator ("Nb Actions" = `action_line + action_subs + action_redisp`). | Concept reused: actions count KPI (GridStorm counts steps whose action is not do-nothing, and breaks down by type). |
| `consumption_profiles.py`, `maintenances.py`, `env_actions.py` | Load profile clustering, maintenance duration/hazard counts from `EpisodeData.env_actions`. | Not needed for v1 (no maintenance in our bounded episodes is asserted; the trace records line status so maintenance-caused disconnections are still visible). |

## `grid2viz/src/simulation/`

| File | What it does | Relevance |
|---|---|---|
| `simulation_utils.py` | Builds Grid2Op action dicts from UI selections (`set_line_status`, `change_line_status`, `set_bus`, `change_bus`, `redispatch`). | Confirms the action-dict vocabulary GridStorm uses for its action summaries and forced outages (`{"set_line_status": [(line_id, -1)]}`). |
| `simulation_clbk.py` | Dash callbacks: user composes an action at a past step, grid2viz *reboots* the env at that step (`reboot.py`) and calls `obs.simulate(action, time_step=0)` to display the resulting rho/flows. | Concept reused: `obs.simulate` as a one-step look-ahead used by the GridStorm "greedy simulate" baseline. Important caveat recorded in our docs: `simulate` uses forecasts, so a good simulated outcome is a *model-based estimate*, not an observed outcome. |
| `ExpertAssist.py` | Wraps the external ExpertOp4Grid expert system; `get_ranked_overloads` ranks overloaded lines (critical = `timestep_overflow == 3`, hard-coded instead of `NB_TIMESTEP_OVERFLOW_ALLOWED`, see the inline comment). | Not reused (extra dependency, hard-coded threshold). The hard-coding is noted as an example of why GridStorm reads thresholds from `env.parameters`. |
| `reboot.py`, `simulation_assist.py`, `simulation_lyt.py` | Env reboot plumbing, plugin interface for assistants, Dash layout. | Not reused (UI-specific). |

## `grid2viz/src/episodes/`

`episodes_clbk.py` / `episodes_lyt.py`: scenario cards that show, per chronic, the best agent's
*survival* (`nb_timestep_played / chronics_max_timestep` from the runner meta JSON), cumulative reward
and maintenance duration. Concept reused: survival steps / max steps and cumulative reward as the
headline KPIs of each GridStorm episode artifact.

## grid2game (glance)

`grid2game/envs/env.py` wraps a Grid2Op env for interactive play: step / back (a state tree in
`grid2game/tree`), `simulate`, a timeline, `seed`/`reset(chronics_id, seed)`, optional "assistant"
agent proposing the next action, and `_stop_if_alarm`. Concepts noted for the GridStorm
`/operations` page: explicit `(env_seed, chronics_id)` pairs for reproducible replays; distinguishing
"action proposed by assistant" vs "action applied". GridStorm v1 only replays precomputed traces;
interactive stepping is out of scope.

## KPI definitions adopted by GridStorm (re-implemented, not copied)

| KPI | Definition in GridStorm | grid2viz analogue |
|---|---|---|
| `survival_steps` / `max_steps` | Steps successfully played before game over, bounded by the episode cap | scenario card "time steps played / max" |
| `survived` | `survival_steps == max_steps` | — |
| `overload_line_steps` | Σ_t #lines with `rho > 1` | "Nb of overflows" (uses `timestep_overflow > 0`) |
| `steps_with_overload` | #steps with at least one line `rho > 1` | — |
| `disconnection_events` | #transitions connected→disconnected of any line (forced, protection, maintenance or agent) | hazards + line actions |
| `actions_count` (+ by type) | #steps where the agent's action is not do-nothing | "Nb Actions" |
| `cumulative_reward` | Σ rewards of played steps (env default reward, documented per artifact) | cum_rewards |
| `mean_rho`, `max_rho` | Mean / max of rho over connected lines and played steps | usage-rate quantiles/max |
| `max_topological_distance` | max_t (#disconnected lines + #substations with an element on bus 2) | `get_distance_from_obs` |
