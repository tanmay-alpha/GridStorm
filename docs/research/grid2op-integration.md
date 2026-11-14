# Grid2Op integration (engine `grid2op`, formulation `sequential`)

Package: `workers/grid2op` (`gridstorm_grid2op`). Reproduction script:
`workers/grid2op/scripts/run_experiments.py`. Artifacts: `data/artifacts/grid2op/` (contract §5,
kind `episode`) with `index.json`. Upstream audit: [`docs/audit/grid2viz-audit.md`](../audit/grid2viz-audit.md).

## Environment and versions

| Item | Value |
|---|---|
| Grid2Op | 1.12.6 |
| Backend | lightsim2grid 1.3.1 (`LightSimBackend`); `pandapower` backend selectable (`--backend pandapower`, `execution.solver = "pandapower"`) |
| Python / OS | CPython 3.11, Windows 10 (wheels; nothing built from source) |
| Environment | `l2rpn_case14_sandbox` (IEEE-14-derived, 20 lines incl. transformers, 14 substations, 5-min steps, 2016 steps/chronic = 1 week) |
| Dataset index | https://github.com/Grid2Op/grid2op-datasets/blob/master/datasets.json |
| Archive URL | https://huggingface.co/datasets/grid2op/l2rpn-datasets/resolve/main/l2rpn_case14_sandbox.tar.bz2 |
| Archive sha256 (published, verified locally) | `1c3b2d73bcfda03c2fc0e977e16e695f303e856752d8b280443accb7248b5827` |
| Extracted dir sha256 (GridStorm's sorted path+content hash) | `94ebcd26b7adda0b22bcb89b2f895be0609f57cd84b056a4e14666b4e29f3fcb` (10 044 files, 1004 chronics) |
| Licence | grid2op-datasets repo: MPL-2.0; the HF dataset card declares none. Not redistributed — only derived traces are committed. |
| Provenance class | `synthetic` |

The dataset lives at `~/data_grid2op/l2rpn_case14_sandbox` (outside the repo), downloaded by
`grid2op.make`.

## Agents

| id | Description |
|---|---|
| `do_nothing` | Grid2Op `DoNothingAgent`. |
| `reco_powerline` | Grid2Op `RecoPowerlineAgent`: `obs.simulate` of do-nothing vs. reconnecting each reconnectable line; best simulated reward. |
| `greedy_simulate` | GridStorm `GreedySimulateAgent` (transparent): below max rho 0.95 only reconnects lines if simulation keeps max rho < 0.95; at/above 0.95 simulates do-nothing, reconnections, all unitary substation topologies (`get_all_unitary_topologies_set`) and ±max-ramp redispatch per redispatchable generator, picks the legal candidate with minimum `max(sim rho) + #new disconnections` (simulated game-over excluded; ties → earliest, do-nothing first). |

Crisis variant: line `1_3_3` forcibly disconnected at trace row 12 (`set_line_status=-1` overriding
the agent action of that step); agent reconnection attempts are blocked (replaced by do-nothing,
flagged `blocked_by_scenario`) until row 300 (288 steps = 24 h), after which agents may reconnect it
subject to Grid2Op cooldowns.

## Results (seed 0, chronics 0 and 1, max 2016 steps, lightsim2grid)

Command: `uv run python scripts/run_experiments.py --max-steps 2016` (from `workers/grid2op`).
Numbers copied from `data/artifacts/grid2op/index.json`.

| Chronic | Variant | Agent | Survival / 2016 | Overload line-steps (rho>1) | Disconnection events | Actions | Cumulative reward | Mean rho | Max rho |
|---|---|---|---|---|---|---|---|---|---|
| 0 | base | do_nothing | 1090 | 2 | 0 | 0 | 69236.51 | 0.4291 | 1.0104 |
| 0 | base | reco_powerline | 1090 | 2 | 0 | 0 | 69236.51 | 0.4291 | 1.0104 |
| 0 | base | greedy_simulate | **2016** | 9 | 0 | 32 | 122266.21 | 0.4325 | 1.0607 |
| 0 | outage 1_3_3 | do_nothing | 806 | 15 | 3 | 0 | 52158.65 | 0.4831 | 1.8663 |
| 0 | outage 1_3_3 | reco_powerline | 1090 | 4 | 2 | 2 | 69215.77 | 0.4458 | 1.0104 |
| 0 | outage 1_3_3 | greedy_simulate | **2016** | 1 | 1 | 5 | 125461.90 | 0.4213 | 1.0067 |
| 1 | base | do_nothing | 806 | 2 | 0 | 0 | 51564.48 | 0.4238 | 1.0022 |
| 1 | base | reco_powerline | 806 | 2 | 0 | 0 | 51564.48 | 0.4238 | 1.0022 |
| 1 | base | greedy_simulate | **2016** | 0 | 0 | 2 | 126147.33 | 0.4322 | 0.9569 |
| 1 | outage 1_3_3 | do_nothing | 797 | 16 | 3 | 0 | 51012.89 | 0.4923 | 1.9233 |
| 1 | outage 1_3_3 | reco_powerline | 806 | 4 | 2 | 2 | 51542.76 | 0.4470 | 1.2339 |
| 1 | outage 1_3_3 | greedy_simulate | **2016** | 1 | 1 | 4 | 126156.58 | 0.4391 | 1.2339 |

Observations: without the outage `reco_powerline` is identical to `do_nothing` (nothing to
reconnect). In the crisis, `do_nothing` suffers cascading overload trips (max rho 1.87–1.92, 3
disconnection events) and fails earlier; `reco_powerline` restores the base-case survival by
reconnecting after the block ends; `greedy_simulate` survives the full week in all four runs.
Survival 2016 means "reached the step cap", not that the agent would survive indefinitely.
Artifacts are 0.31–0.96 MB each (limit 5 MB). KPI definitions are in
`gridstorm_grid2op.kpis.KPI_DEFINITIONS` and embedded in every artifact.

## Reproducibility

- Seeds: `env.reset(seed=seed, options={"time serie id": chronic})` and `agent.seed(seed)`;
  all agents are deterministic.
- `trace_sha256` = sha256 of canonical JSON of `{steps, game_over}` (excludes timestamps and
  wall times).
- Determinism check (in the script): `case14-sandbox-c0-outage-1-3-3-greedy-simulate` re-run in a
  fresh environment → `050177c84915e2baf8d1ae602d166185b3a57389e397e754c7f8bfd4d9e36109` both
  times (`identical: true`). The test `test_same_seed_same_trace_hash` repeats this for
  `reco_powerline` and `greedy_simulate` on a 48-step crisis episode.
- Hashes are expected to be stable for the same Grid2Op/lightsim2grid versions and platform;
  cross-backend or cross-version bit equality is not claimed.

## StormSpec mapping (`gridstorm_grid2op.run_scenario`)

Supported: `network_id = "l2rpn-case14-sandbox"`; snapshot *i* = Grid2Op step *i* of the chronic
(`horizon.start` via `env.reset(options={"init ts": ...})`); `line_outage` (component `line` or
`transformer` — both are Grid2Op lines, ids = `env.name_line`) as a forced disconnection at
`window.start`, reconnection blocked until `window.end`; `execution.solver` `null`/`lightsim2grid`/
`pandapower`; `execution.seed` seeds env and agent.

Rejected with `unsupported_operation`: `demand_multiplier` (no public Grid2Op 1.12 API to scale
load chronics consistently with the forecasts used by `obs.simulate`; generator set-points would
not be re-dispatched, so the slack would absorb the change), `generator_outage`,
`renewable_availability_multiplier`, `link_outage`, `storage_state`, and
`mitigation.load_shedding.enabled = true`. Unknown line ids are rejected too.

## Tests

`uv run pytest -q` in `workers/grid2op`: **20 passed** (114.6 s), covering KPI computation on a
synthetic trace (`test_kpis.py`), unsupported-event rejection (`test_scenario_rejection.py`), and
real-environment determinism / forced-outage / scenario runs (`test_episodes.py`, marked
`network`+`slow`; deselect offline with `-m "not slow and not network"`).

## Limitations

- **Simulation success ≠ operational safety.** Grid2Op is a research environment: a DC/AC
  power-flow per 5-min step, simplified protection (overload counters), no dynamics, voltage
  stability or real operator procedures. `obs.simulate` uses forecasts, so the greedy agent's
  choices are model-based estimates. See the L2RPN retrospective, Marot et al., *Learning to run a
  power network challenge: a retrospective analysis*, arXiv:2103.03104.
- Small synthetic 14-bus grid; 2 chronics × 1 seed — illustrative, not statistically significant.
- No opponent; the crisis is one scripted outage.
- Substation coordinates come from the env `grid_layout.json` (schematic, not geographic).
