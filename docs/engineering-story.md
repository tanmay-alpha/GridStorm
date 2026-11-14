# GridStorm — the engineering story

An interview-grade walkthrough of how GridStorm is put together and which problems were hard.
Every claim points at a file in this repository; where a number matters, the file that produced it
is named.

## 0. The one-paragraph pitch

GridStorm lets a user pick a real, licensed power-network dataset, describe a crisis in a typed
scenario language (**StormSpec**: demand surges, renewable droughts, line/generator outages, storage
state), run it through a mature open-source engine, and inspect *honest* results: unserved energy,
congestion, curtailment, cost, with solver status and a reproducibility manifest. It reuses
**PyPSA** (linear optimal power flow), **pandapower** (AC power flow, N-1) and **Grid2Op**
(sequential operation) instead of re-implementing them; its own code is the scenario language,
adapters, validation, screening benchmark (**StormBench**), Monte Carlo risk (**StormRisk**), a
deterministic Crisis Response Advisor, provenance, API and UI
([`architecture/overview.md`](architecture/overview.md)). It is a research and teaching tool, not a
control system and not a blackout predictor.

```
apps/web (React SPA, Vercel) ──HTTPS JSON──▶ services/api (FastAPI, Render)
                                              ├─ StormSpec validation (packages/stormspec)
                                              ├─ persistent job table (Postgres/Supabase or SQLite)
                                              ├─ worker pool → subprocess: gridstorm_pypsa (PyPSA + HiGHS)
                                              └─ precomputed artifacts (data/artifacts/<engine>/)
offline, isolated envs: workers/pandapower, workers/advisor, workers/grid2op,
                        packages/stormbench, packages/stormrisk ──▶ versioned JSON artifacts
```

## 1. Dependency conflicts → one isolated environment per engine

**Problem.** The target versions of all three engines cannot share one Python environment.
PyPSA 1.4 requires pandas ≥ 3, while pandapower 3.5.6 and Grid2Op 1.12.6 require pandas < 3.
The [compatibility matrix](research/compatibility-matrix.md) records published requirements,
successful isolated resolutions and the combined resolver failures. pandapower and Grid2Op
*can* coexist; their separate environments are an isolation choice, not another proven conflict.
The committed lockfiles show the split as resolved by uv:

| Lockfile | pandas | Engine |
|---|---|---|
| `workers/pypsa/uv.lock`, `services/api/uv.lock`, `services/analytics/uv.lock`, `packages/stormrisk/uv.lock` | 3.1.1 | pypsa 1.4.0 |
| `workers/advisor/uv.lock`, `workers/distribution/uv.lock`, `packages/stormbench/uv.lock` | 2.3.3 | pandapower 3.5.6 |
| `workers/pandapower/uv.lock`, `packages/stormml/uv.lock` | 2.3.3 | pandapower 3.5.4 (pinned `scipy<1.14`: pandapower's OPF calls the sparse `.H` attribute removed in SciPy 1.14) |
| `workers/grid2op/uv.lock` | 2.3.3 | grid2op 1.12.6 (+ pandapower 3.5.6) |

The pins are declared in `workers/grid2op/pyproject.toml` (`pandas<3`) and
`workers/pandapower/pyproject.toml` (`pandas>=2.2,<3`).
Forcing a common resolution would mean pinning an old PyPSA or patching engines — both damage
reproducibility.

**Decision.** A monorepo with one `uv` project and one `uv.lock` per component
([`architecture/contracts.md` §1](architecture/contracts.md#1-python-environments-isolated-never-merged)):
`services/api` (FastAPI + the PyPSA worker as a path dependency), `workers/pypsa`,
`workers/pandapower`, `workers/advisor`, `workers/grid2op`, `packages/stormbench`,
`packages/stormrisk`, … Each has its own `uv.lock`; Python bounds live in `pyproject.toml`,
and most components additionally have `.python-version`.

**The trick that makes it work:** the shared packages `packages/stormspec` and
`packages/canonical-grid` depend only on `pydantic>=2` (no pandas), so every environment can import
the same scenario and network schemas as editable path dependencies
(`[tool.uv.sources] stormspec = { path = "../../packages/stormspec", editable = true }` in
`services/api/pyproject.toml`). Engines never import each other; they exchange **versioned
artifacts** (NetCDF networks, `canonical-grid/1.0` JSON, `gridstorm-result/1.0`, and the
`gridstorm-artifact/1.0` envelope, contracts §2–§5).

**Cost.** More lockfiles, one CI job per environment, and cross-engine claims must be tested by
running two environments and diffing artifacts (§6). `scripts/test_all.sh` runs every component's
tests in its own env sequentially (`uv sync --locked --python 3.11`, then
`uv run --no-sync pytest -m "not slow and not network and not docker"`).

## 2. Why partial-window line outages are rejected in LOPF

**Problem.** A natural scenario is "line X trips from hour 6 to hour 12". In PyPSA's linear OPF the
tempting implementation is to set the line's per-unit capacity `s_max_pu = 0` for those snapshots.
That is **wrong**: the line remains in the network's impedance model, and PyPSA enforces Kirchhoff's
Voltage Law through cycle constraints (Σ x·P around each cycle = 0). With capacity 0 the flow is
forced to 0 *but* KVL still couples the bus angles as if the line existed, so the other flows are
those of a network where the line carries zero flow while still present — a physically different
system from one where the line is open. The optimiser returns a plausible-looking but invalid
answer.

**Decision.** Capability declarations make this explicit. In
`packages/stormspec/src/stormspec/capabilities.py`, the PyPSA engine declares
`line_outage: "full_horizon"` and `link_outage: "full_horizon"`: an outage is a topology change that
must cover the whole horizon, while demand/renewable/generator events accept any window.
`stormspec.validate` rejects anything else with error code `unsupported_operation`
(`packages/stormspec/src/stormspec/validation.py`). Grid2Op, which really steps through time and
switches lines, declares `line_outage: "any"`; pandapower is single-snapshot (`"none"`).

**Principle:** unsupported operations are rejected, never silently approximated (contracts §3).
The same rule appears in the advisor: `Crisis.from_stormspec` rejects time windows and
renewable/storage/link events it cannot represent (`workers/advisor/src/gridstorm_advisor/crisis.py`).

## 3. Honest job states: infrastructure status ≠ solver termination

**Problem.** "The job succeeded" conflates two independent facts: did the *process* finish, and what
did the *optimiser* conclude? An infeasible scenario is a legitimate scientific outcome (the
configured constraints cannot all be satisfied), not a crash; a timeout is neither.

**Decision.** The Job contract (contracts §6) carries separate fields:

- `status` — infrastructure: `queued | running | completed | failed | cancelled | timeout`;
- `stage` — `queued, loading_network, applying_scenario, building_model, solving, postprocessing, done`
  (reported by the engine CLI as `STAGE <name>` lines; there is deliberately **no percentage
  progress**, because a MILP/LP solver cannot predict it);
- `outcome` — scientific: `feasible | infeasible | error`;
- `solver` — `{name, version, status, termination_condition, objective_eur, wall_time_s}`.

So a run can be `status=completed, outcome=infeasible, termination_condition=infeasible`. Infeasible
results carry **empty series, never fabricated numbers** (contracts §4). The API refuses to serve a
result for a job that is not `completed` (`services/api/src/gridstorm_api/jobs/results.py`). Jobs
run in a subprocess with a wall-clock timeout and memory limit (`GRIDSTORM_JOB_TIMEOUT_S`,
`GRIDSTORM_JOB_MEMORY_MB`), bounded concurrency (`GRIDSTORM_MAX_CONCURRENT_JOBS`, default 1),
bounded retries (`GRIDSTORM_JOB_MAX_ATTEMPTS`) and heartbeat-based stale-job detection
(`GRIDSTORM_JOB_STALE_AFTER_S`), all in `services/api/src/gridstorm_api/config.py`.

**Sanity check on feasible outputs:** `balance_residual_max_mw` is the maximum absolute nodal
balance residual over snapshots and buses, recomputed from solved component outputs
(`balance_residuals` in `workers/pypsa/src/gridstorm_pypsa/runner.py`). It should be near zero
within numerical tolerance; a large value indicates an inconsistency requiring investigation,
not a new physical phenomenon.

## 4. Reproducibility: hashes, manifests, provenance

- **Scenario hash.** `stormspec.canonical_json` serialises a scenario with sorted keys and no
  whitespace, *excluding* `name`/`description`; `scenario_hash` is its SHA-256
  (`packages/stormspec/src/stormspec/hashing.py`). Renaming a scenario does not change its identity;
  changing one multiplier does. Identical hashes with a completed result may be reused and are
  flagged `reused: true`.
- **Dataset manifests** (`dataset-manifest/1.0`, schema in
  `packages/canonical-grid/schema/dataset-manifest-1.0.schema.json`): source URL/version/commit,
  SHA-256 of every file, license with redistribution status, transformations applied and a
  provenance class. A scenario may pin `dataset.sha256`.
- **Execution manifest** (`execution-manifest/1.0`, `packages/stormspec/src/stormspec/manifest.py`):
  scenario hash, dataset hash, engine and solver name/version/options, Python/platform,
  timestamps, result SHA-256, git SHA.
- **Artifact envelope** (`gridstorm-artifact/1.0`, contracts §5): every offline result (N-1, advisor
  run, Grid2Op episode, benchmark) records the exact command, input hashes, platform and
  `payload_sha256` = SHA-256 of the canonical payload; each engine directory has an `index.json`.
  `scripts/compare_artifacts.py` compares artifacts.
- **Provenance vocabulary:** `observed | estimated | synthetic | modeled | calculated`
  (see [glossary](glossary.md#provenance-classes)). Dataset/field provenance and result assumptions
  carry context; not every displayed number has an individual provenance badge.

## 5. Screening vs exact contingency analysis

N-1 analysis on a meshed grid means one power flow per element. Two families of methods exist:

- **Screening (StormBench, `packages/stormbench`).** DC sensitivities from first principles —
  B matrices, PTDF `H = B_f B_bus⁻¹`, LODF `LODF[k,l] = H_ll[k,l] / (1 − H_ll[l,l])` — give all
  post-outage flows with one factorisation (`packages/stormbench/src/stormbench/dc.py`). Bridges
  (where `1 − H_ll = 0`) are detected structurally and classified `islanding` rather than divided
  through. Screening is fast but approximate: it ignores reactive power, voltages and losses.
- **Exact (pandapower AC N-1, `workers/pandapower`).** One Newton–Raphson AC power flow per outage;
  the reference against which screening is scored.

StormBench's job is to measure — not assume — how good screening is: which contingencies a DC
ranking misses relative to the AC reference. A screening method is never presented as an
equivalent of AC analysis. The Crisis Response Advisor uses the same idea with a hard rule: PTDF/LODF
are used **only to rank and size** candidate remedial actions; every candidate is re-evaluated with
a full AC power flow and DC numbers never decide acceptance
(`workers/advisor/src/gridstorm_advisor/sensitivity.py`, thermal limit 100 % in `state.py`).

## 6. Cross-engine verification

The executable harness in `tests/cross_engine/run_all.py` invokes separate PyPSA and pandapower
environments on aligned MATPOWER-derived cases. `tests/cross_engine/compare.py` compares DC
branch flows and bus angles, effective reactances, and OPF objectives/dispatch; it distinguishes
AC/DC model differences from implementation agreement. Its explicit tolerances include
`1e-6 MW` for DC branch-flow agreement, `1e-6` relative objective difference and `0.01 MW` dispatch
difference. Negative controls perturb modelling inputs to test whether the checks detect errors.
The harness publishes artifacts under `data/artifacts/cross-engine/`; the Benchmarks page reads
their per-check metrics, tolerances and verdicts. A published verdict applies only to its recorded
case and check, not to arbitrary future scenarios.

StormBench independently compares its DC sensitivities to pandapower through
`packages/stormbench/src/stormbench/pp_bridge.py`. Agreement is evidence to inspect, not a blanket
certification of either engine.

## 7. Render free tier → demo mode vs research mode

Render's free web service has 0.1 CPU / 512 MB RAM, spins down after 15 minutes without traffic
(about a minute to spin back up) and has an ephemeral filesystem lost on every restart, redeploy or
spin-down (<https://render.com/docs/free>). Consequences in the design:

- **Only PyPSA simulation jobs run live** in the API (ADR 0001 §3). The API also computes network
  analytics; pandapower, advisor, Grid2Op, StormBench and StormRisk studies run offline and are
  served from `data/artifacts/` through `services/api/src/gridstorm_api/precomputed.py`.
- **Execution mode switch.** `GRIDSTORM_EXECUTION_MODE=live|precomputed`
  (`services/api/src/gridstorm_api/config.py`); every Job records `execution_mode`, so the UI can
  label results honestly.
- **Durability is explicit, not automatic.** With `DATABASE_URL`, jobs/metadata use Postgres.
  The live API uses Supabase Postgres (session pooler); without `DATABASE_URL` the fallback is SQLite
  (`var/gridstorm.db` locally; `/tmp/gridstorm/gridstorm.db` in the image), with no Render
  durability. Generated payloads use an ArtifactStore (`GRIDSTORM_ARTIFACT_STORE=local|s3`);
  only an external store preserves them across free-service resets
  (`services/api/src/gridstorm_api/storage.py`).
- **Limits are explicit:** concurrency 1, per-job timeout and memory cap, a queue bound
  (`GRIDSTORM_MAX_QUEUED_JOBS`) and token-bucket rate limits on POSTs and simulations
  (`GRIDSTORM_RATE_LIMIT_*`, `services/api/src/gridstorm_api/ratelimit.py`).

## 8. Security and multi-tenancy

Supabase Row Level Security (`database/migrations/0002_row_level_security.sql`): public datasets are
readable by anyone; scenarios, jobs and comparisons are readable when public or owned
(`owner_id = auth.uid()`); clients cannot create jobs (only the API can); audit/ingestion tables have
no client policies. The API connects as table owner/service role and enforces the same rules itself;
user JWTs are verified with `SUPABASE_JWT_SECRET` (`services/api/src/gridstorm_api/auth.py`). The
service-role key never reaches the browser.

## 9. What I would say is still weak

- LOPF is DC-linearised: no voltages, reactive power or losses (stated in every result's
  `assumptions`).
- EENS/LOLP are only as good as the outage probabilities fed in; GridStorm does not estimate
  failure rates itself (`packages/stormspec/src/stormspec/eens.py`, `packages/stormrisk`).
- The free-tier demo is deliberately small; heavier studies are offline artifacts, which are
  reproducible but not interactive.
