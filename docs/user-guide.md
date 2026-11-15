# GridStorm user guide

GridStorm is a research and teaching tool for power-grid crisis scenarios. It is **not** a
real-time control system, an operational security assessment or a validated blackout predictor.
Every number in the UI is a model output on a research dataset and carries the assumptions it was
computed under.

Terms are defined in the [glossary](glossary.md); the architecture is explained in the
[engineering story](engineering-story.md).

## Contents

1. [The demo story](#1-the-demo-story)
2. [Pages](#2-pages)
3. [Metrics: meaning, units, formulas](#3-metrics-meaning-units-formulas)
4. [Execution modes: live vs precomputed](#4-execution-modes-live-vs-precomputed)
5. [Job states](#5-job-states)
6. [Limitations](#6-limitations)

## 1. The demo story

From **Home** (`/`), choose **Start the guided demo**. It opens
`/studio?network=pglib-case14-ieee&preset=pglib-case14-ieee-gen-1-outage&guide=1`:
the IEEE 14-bus loss of generator `gen-1` (`studio/flow.ts`, `GuidePanel.tsx`).

| Step | Where | What you do |
|---|---|---|
| 1. Fail a generator | **Crisis Studio** | Read which generator fails, the remaining installed capacity and the investigation question. Choose *Run this crisis*, or *Open the verified result* when only the matching precomputed result is available. |
| 2. Read the result | `/runs/<id>?guide=1` | Read the outcome and summary facts. The numbered guide links to the result, baseline comparison, brief and downloads. |
| 3. Compare with baseline | **Compare with baseline** | Opens `/compare?a=<baseline>&b=<scenario>&auto=1&guide=1`. A compatible completed baseline is reused; otherwise *Run baseline & compare* is offered when a live baseline solve is available. `auto=1` creates the comparison on arrival. |
| 4. Read the Grid Impact Brief | **Run / Compare** | Expand the evidence behind the mechanically derived statements; co-occurrence is not proof of cause. |
| 5. Download evidence | **Run page → Downloads**; **Compare → Export MD/JSON** | Save result JSON, execution manifest and reports. |

For custom investigations, explore a dataset in **Grid Explorer** (`/explorer`), compose a
scenario in Studio, then compare completed runs on the same network. Saved scenarios appear
in Studio and the Library. Compare's per-snapshot map slider replays loading through the horizon.

The header shows the backend status (*API &lt;version&gt;*, *Checking backend…* or *Backend
unreachable*). On a free-tier backend the first request after an idle period can take about a
minute while the service wakes up; the app retries unreachable requests with backoff meanwhile
(`apps/web/src/main.tsx`).

## 2. Pages

### Grid Explorer (`/explorer`)

- **Network** selector: every network in the backend catalog (`GET /api/v1/networks`); schematic
  networks are marked "— schematic".
- **Asset search** (Ctrl+K): find buses, lines, transformers, links, generators, storage by id or
  name.
- **Layers**: buses, lines, links, generators, storage, with counts.
- **Filters**: *Voltage filter [kV]* (min/max, optionally including assets with unknown voltage),
  *Carriers* (generators and storage), *Countries* (none checked = all).
- **Map**: geographic networks use MapLibre. IEEE 14/118 and other schematic networks use the
  dedicated SVG `components/map/schematic/SchematicView.tsx`, not a geographic basemap.
  Schematic positions have no geographic meaning. Branches are coloured by nominal voltage;
  assets without coordinates are counted under "Not drawn (no coordinates)".
- **Asset details**: all fields with units, a provenance badge per field when the manifest
  provides one, and the list of connected assets.
- **Dataset** panel: coordinate kind, provenance class, license (SPDX) and redistribution status,
  source URL, version, upstream commit, retrieval date, attribution, `network.nc` SHA-256, snapshot
  count × resolution and period, peak/total load, supported engines, quality flags and dataset
  assumptions (from the `dataset-manifest/1.0`).

### Crisis Studio (`/studio`)

Composes a StormSpec (`stormspec/1.0`) scenario.

- **Steps**: *Choose grid → Choose crisis → Review settings → Run*. Use Back/Next or an
  available step button; later steps require the preceding selections. Tab reaches controls;
  arrow keys move/select within the grid radio group. Focus moves to the new step's content
  after user navigation (`Stepper.tsx`, `GridStep.tsx`, `StudioPage.tsx`).
- **Preset cards**: compact summaries show the question and execution badge. Expand *Details & ids*
  for the full description, scenario/network ids, hash, events and horizon (`PresetList.tsx`).
- **Drafts**: one unsaved draft is kept in this browser's localStorage across navigation/reloads.
  Discarding edits or successfully saving clears it. Disabled/full browser storage prevents
  persistence but does not discard the in-memory edit (`draft.ts`).
- **Execution availability**: *live* means this network permits live solves; *precomputed* requires
  a verified result with the exact scenario hash; *unavailable* means neither is possible.
  A checking state is shown while the necessary server data is loading (`flow.ts`).
- **Scenarios**: *Presets* (shipped with the backend) and *Saved* scenarios. Picking one loads it;
  any change marks it *edited* (*Discard edits* reverts).
- **Scenario**: network, scenario id (lowercase letters, digits, hyphens; 3–64 chars), name,
  description. Name and description do not affect the scenario hash.
- **Horizon**: start snapshot index and number of snapshots; the panel shows the network's snapshot
  count, resolution and period, and the resulting duration in hours.
- **Events** (only types the selected network supports are offered):

  | Event | Parameters |
  |---|---|
  | Line / transformer outage | component (`line` or `transformer`), asset, window |
  | Link outage | link, window |
  | Generator outage | generator, window |
  | Demand multiplier | multiplier (optionally per bus), window |
  | Renewable availability multiplier | carrier, multiplier, window |
  | Storage initial state of charge | storage unit, initial SOC fraction |

  *Whole horizon* is the default window; unchecked, a window is the half-open interval
  `[start, end)` of absolute snapshot indices. With the PyPSA engine, line/transformer and link
  outages must cover the whole horizon; a partial window is rejected with `unsupported_operation`
  (see [engineering story §2](engineering-story.md#2-why-partial-window-line-outages-are-rejected-in-lopf)).
  A scenario without events runs the network as-is and is the natural baseline.
- **Mitigation & execution**: *Storage dispatch* (off: storage held at zero), *Allow renewable
  curtailment* (off: variable renewables must produce all available power), *Load shedding* (adds
  load-shedding generators priced at VOLL), *Value of lost load (VOLL)* [dataset money unit/MWh],
  *Solver time limit* [s]. Engine/formulation and solver settings are shown.
- **Validation**: errors and warnings from `POST /api/v1/scenarios/validate` (asset ids exist with
  the right component type, carriers exist, horizon and windows in range, multiplier ranges, engine
  capability). *Run simulation* and *Save scenario* are disabled while errors remain.
  Each message names the field, retains its exact path/code and links to the step to fix it;
  pending validation is not presented as valid (`ValidationMessages.tsx`).
- **Run**: *Run simulation* submits the job and opens its run page; *Save scenario* stores it and
  reports the saved id and hash.
  HTTP 429 `too_many_active_jobs` shows *Too many simulations are already running*: wait for
  a run to finish or cancel one, then retry. The scenario is unchanged; the message links to
  active runs in the Library (`RunError.tsx`).
- **StormSpec JSON**: the exact document that is validated, saved and run.

### Run page (`/runs/:id`)

- **Summary facts**: outcome, unserved energy, demand served, congestion and operating cost;
  a cost-basis badge identifies how monetary values must be read (`runs/result.ts`, `RunPage.tsx`).
- **Grid Impact Brief**: deterministic rules summarise the stored result, scenario and available
  baseline/mitigation evidence. Every statement records source fields and values; no language
  model is involved. Coinciding shedding and binding limits describe association, not causation
  (`features/brief/brief.ts`).
- **Single-period cases**: a lone snapshot without a calendar time index is labelled
  *single period (no timestamp)*, not a fabricated date (`runs/result.ts`).
- **Header**: scenario id, job status, scientific outcome, execution-mode badge (*live run* or
  *precomputed*), a *reused* badge when an identical completed run was reused, *Cancel* while the
  job is not finished, *Compare* when it is.
- **Status**: stage timeline (`queued → loading_network → applying_scenario → building_model →
  solving → postprocessing → done`), polled every second. There is no percentage progress bar: a
  solver cannot predict its remaining time.
- **Solver**: name, version, status, termination condition, objective, wall time.
- **Diagnostics** (only when something needs attention): error code/message, infeasibility
  explanation, timeout, solver termination, result warnings.
- **Downloads**: *Result JSON* (`gridstorm-result/1.0`), *Manifest* (`execution-manifest/1.0`),
  *Report MD* / *Report JSON* (`GET /api/v1/reports/{job_id}`), plus the stored artifacts with
  size and SHA-256.
- **Key metrics** (cards): unserved energy, peak load shed, load-shed hours, total system cost,
  max line loading (highlighted at ≥ 99.9 %), congested branches, total load, served load,
  curtailment, generation cost, CO₂ emissions, mean line loading. See [§3](#3-metrics-meaning-units-formulas).
- **Charts**: generation by carrier (stacked, MW) with demand as a dashed line; load shed [MW];
  storage dispatch [MW] and state of charge [MWh] (when the network has storage); mean nodal
  marginal price [dataset money unit/MWh]; generation by carrier (energy, MWh).
- **Line loading map** with a snapshot slider: colour bands 0–50 %, 50–70 %, 70–90 %,
  90–99.9 %, ≥ 99.9 % (congested); grey = out of service / no value.
- **Branches** table: type, id, `s_nom` [MVA], max |flow| [MW], max loading, outage status — the
  maximum over the horizon; clicking a row highlights the branch on the map.
- **Assumptions** (from the result) and **Engine & reproducibility**: engine name/version/
  formulation, scenario id and hash, snapshot range, result SHA-256, balance residual.

If the job did not complete, no result is shown — "No result is available for a *status* job".

### Compare & Replay (`/compare`)

- **Select runs**: *Baseline run* and *Scenario run* from completed jobs; both must use the same
  network (the API rejects other pairs). *Compare* creates a comparison (`POST /api/v1/comparisons`).
- **Header**: provenance badge (`calculated`), links to both runs with their outcomes, *Export MD* /
  *Export JSON* (`GET /api/v1/reports/{comparison_id}`).
- **Warnings**: e.g. when a run's outcome is not `feasible`, its metrics may be empty and the
  affected deltas are null.
- **Metric deltas**: Δ = scenario − baseline. Loading percentages use **percentage points (pp)**,
  not relative percent change. Other relative deltas use Δ / |baseline| · 100; baseline zero is
  shown as **n/a (baseline 0)**. Missing values are never treated as zero (`compare/compare.ts`).
- **Cost deltas**: withheld unless the two runs share the same nonempty cost-basis
  `comparability_key`; physical energy/loading deltas remain available.
- **Line loading difference** map with four views: *Δ max loading over horizon [pp]*, *Δ loading
  at snapshot [pp]*, *Scenario loading at snapshot [%]*, *Baseline loading at snapshot [%]*. The
  per-snapshot views have a snapshot slider (the replay). Δ colour bands: ≤ −20, −20 to −5,
  −5 to +5, +5 to +20, ≥ +20 percentage points; grey = no value in one run.
- **Generation by carrier Δ** [MWh] (chart and table) and **Branch loading Δ** table (max over the
  horizon of |loading|, sorted by |Δ|; for links, |flow| / p_nom · 100).
- **Assumptions** of the comparison.

### Mitigation comparison (`/mitigation`)

The study list (`features/mitigation/studies.ts`) contains exactly:

| Study | What it shows |
|---|---|
| SciGRID Germany — cold dark lull: does dispatching storage avoid load shedding? | Baseline day, demand ×1.15 / wind ×0.3 / solar ×0.5 with storage held at zero, and the same crisis with storage dispatched. Only `mitigation.storage_dispatch` differs between crisis and mitigation; compare unserved energy, costs and storage dispatch. |
| IEEE 14-bus — loss of branch-3: AC-validated corrective action | Pre-crisis, crisis and recommended-action AC states; asks whether an action clears every violation after the branch outage and bus-3 under-voltage. |
| IEEE 14-bus — loss of generator gen-1: is any corrective action accepted? | Loss of the slack generator with insufficient remaining capacity; reports whether any candidate passes the AC acceptance rules, including an explicit no-accepted-action state. |

Committed precomputed results are the default. The SciGRID study can select the latest completed
live runs with identical scenario hashes only when all three exist; advisor studies remain
precomputed. `/mitigation?baseline=<id>&crisis=<id>&mitigation=<id>` also compares three completed
runs on the same network (`MitigationPage.tsx`).

### Research Workbench (`/workbench`)

Select a research network, then a published study (multi-network artifacts have their own group).
Read artifact-backed results, documented assumptions/limitations, references, engine/solver
information and reproduction commands. Detailed research pages are linked rather than duplicated.

Execution labels distinguish *live re-run available*, *precomputed only* and *offline study*.
Even when a live re-run is available, the workbench numbers are the published precomputed artifact.
**Download reproduction manifest** saves `gridstorm-reproduction-manifest/1.0`: study references,
network hash/source/cost basis, execution mode, result/input artifact headers and API paths,
commands and payload-hash verification instructions (`workbench/catalog.ts`, `manifest.ts`;
[workbench reference](research/workbench.md)).

### Library (`/library`)

*Research Library*: simulation runs (job, scenario, network, status, outcome, mode, wall time,
created), scenarios (preset/saved, network, event count, hash, spec download), datasets
(coordinates, provenance, license, buses, snapshots, `network.nc` SHA-256, manifest download) and
precomputed artifacts (title, engine, kind, network, JSON download).

### Contingency (`/contingency`)

Reads precomputed artifacts only (`GET /api/v1/artifacts`); disclaimer: "Steady-state AC
power-flow screening on research networks. Not an operational security assessment or instruction."

- **AC N-1 contingency study (pandapower)**: counts per class, the number of single-branch
  contingencies, runtime, base-case loading/voltage, and a ranked table (rank, outage, class,
  severity as recorded in the artifact, max loading, min/max voltage magnitude [p.u.], islanded
  load [MW]). Selecting a contingency lists its overloaded branches and voltage violations.
  The network schematic highlights the selected outage and affected branches. If the artifact
  includes a top-K N-2 study, the page also shows its ranked pair-outage table; this is not an
  exhaustive N-2 security certificate.
- **Crisis Response Advisor**: crisis description, violations in the crisis state, the ranking
  objective, the acceptance rules (verbatim from the artifact), the recommendation (objective
  [dataset money unit], load shed [MW], generation cost Δ [dataset money unit], switching actions),
  crisis state vs state after the recommendation, baselines vs advisor, candidates and rejection reasons, and
  the artifact's verification-scope statement.

### Operations (`/operations`)

*Operations replay* of precomputed Grid2Op episodes (baseline agents operating a sandbox grid).
Disclaimer: "Simulation success ≠ operational safety." Shows **KPIs per agent** (survival,
overloaded line-steps, disconnections, actions, illegal actions, max ρ, cumulative reward) and an
**Episode replay** with play/pause, a step slider, per-line ρ on the substation layout and an
actions timeline. *KPI definitions* are shipped inside each artifact.

### Benchmarks (`/benchmarks`)

Measured results from published artifacts; "they do not generalise beyond" the listed test cases
and hardware.

- **StormBench — DC contingency screening vs exact N-1**: per case, contingencies, islanding count,
  overloading contingencies (screening / DC exact / AC exact), precision and recall of screening vs
  DC and vs AC, Kendall τ vs AC, max flow error vs DC, runtimes and speed-up vs AC, peak memory, AC
  non-convergence, new voltage violations missed by screening.
- **StormRisk — Monte Carlo EENS**: EENS with standard error and coefficient of variation, LOLP
  with its standard error, p95 and max unserved energy, outage classes (unavailability, matched
  assets, provenance, source) and asset importance (share of unserved energy).
- **Cross-engine agreement**: per check, engines compared, n, metrics, tolerance and verdict.
- **PyPSA preset runs**: preset, network, outcome, objective, unserved energy, solver wall time,
  recorded resources.

Sections without published artifacts show an explicit empty state.

### Methods (`/methods`)

Modelling assumptions, limitations, equations (rendered with KaTeX), provenance classes, dataset
provenance from the manifests, engine environments, engine versions found in artifacts, links to
repository documents and references.

## 3. Metrics: meaning, units, formulas

Notation: snapshot *t* with weight Δt [h] (`snapshot_weightings_h`); all sums run over the
scenario horizon. Implemented in `workers/pypsa/src/gridstorm_pypsa/runner.py` unless noted.

### Cost basis

Money is dataset-specific, not universally EUR. The
[cost-basis audit](research/cost-basis-audit.md) records:

| Dataset | Money unit |
|---|---|
| `ac-dc-meshed` | illustrative cost units |
| `scigrid-de` | illustrative cost units (a different comparability key from the toy grid) |
| `pglib-case14-ieee`, `pglib-case118-ieee` | PGLib cost units: nominal benchmark costs, not EUR or verified-year USD |
| `pypsa-eur-be` | 2025 EUR model assumptions, not observed prices |

VOLL is a chosen load-shedding penalty in the dataset's own money unit/MWh, not calibrated
economic damage. Legacy `_eur`, `objective_eur` and `_eur_per_mwh` field names remain for
compatibility and stable scenario hashes; they do not assert a currency. Unknown imported bases
are shown as *cost units (basis unknown)*. No exchange-rate conversion is implied.
Matching nonempty comparability keys permit numerical cost deltas, not comparisons of
real-world economic welfare. Dispatch freezes capacities; installed CAPEX is not part of its
operating objective and must not be added to OPEX as a full year's expenditure.

### Simulation (PyPSA LOPF) metrics

| Metric (field) | Unit | Definition |
|---|---|---|
| Total load (`total_load_mwh`) | MWh | Σ_t P_load,t · Δt |
| Unserved energy (`unserved_energy_mwh`) | MWh | E_unserved = Σ_t P_shed,t · Δt. Load shedding is a dispatchable generator per load bus (carrier `load_shedding`, marginal cost = VOLL). |
| Served load (`served_load_mwh`) | MWh | total load − unserved energy |
| Peak load shed (`peak_load_shed_mw`) | MW | max_t P_shed,t |
| Load-shed hours (`load_shed_hours`) | h | Σ Δt over snapshots with P_shed,t > 0.001 MW |
| Total system cost (`total_system_cost_eur`) | dataset money unit | Solved dispatch objective, including generator, storage/link and other operating-cost terms present in the model, plus load shedding at VOLL; not merely a fuel-cost total |
| Load-shedding cost (`load_shedding_cost_eur`) | dataset money unit | Σ_t Σ_shed P_shed · VOLL · Δt |
| Generation cost (`generation_cost_eur`) | dataset money unit | total system cost − load-shedding cost; this field name includes any other non-shedding operating-cost terms in the objective |
| Generation by carrier (`generation_by_carrier_mwh`) | MWh | Σ_t P_g,t · Δt per carrier (excluding shedding) |
| Curtailment (`curtailment_mwh`, per carrier) | MWh | Σ_t max(0, p_max_pu · p_nom − P_dispatched) · Δt over variable generators |
| Line loading (`loading_pct`; `max_/mean_line_loading_pct`) | % | 100 · \|p0\| / (s_nom · s_max_pu) per in-service line/transformer and snapshot; max and mean over all of them |
| Congested branches (`congested_line_count`) | count | branches whose loading reaches ≥ 99.9 % at any snapshot |
| Storage discharge / charge (`storage_discharge_mwh`, `storage_charge_mwh`) | MWh | Σ_t Σ_storage p_dispatch,t · Δt / Σ_t Σ_storage p_store,t · Δt, from the separate nonnegative discharge/charge variables (not the positive/negative parts of net fleet dispatch) |
| CO₂ emissions (`co2_emissions_t`) | t | Σ_t Σ_g P_g,t · intensity(carrier) / efficiency · Δt; **null** (with a warning) when the dataset has no CO₂ intensities — a data gap, not "zero emissions" |
| Mean marginal price (series) | dataset money unit/MWh | mean over buses of the nodal-balance dual |
| Balance residual (`balance_residual_max_mw`) | MW | maximum absolute nodal balance residual over snapshots and buses, recomputed from solved outputs; should be near zero within numerical tolerance |

### Probabilistic metrics

| Metric | Unit | Definition |
|---|---|---|
| EENS | MWh | Σ_s p_s · E_unserved,s over a complete, mutually exclusive scenario set (Σ p_s = 1); infeasible scenarios must not be included (`packages/stormspec/src/stormspec/eens.py`). In StormRisk Monte Carlo studies, p_s are sample weights. |
| LOLP | – | Σ_s p_s · 1[E_unserved,s > tol]; Monte Carlo standard error √(LOLP(1 − LOLP)/N) (`packages/stormrisk/src/stormrisk/estimators.py`) |
| SE(EENS), 95 % CI, CV | MWh, MWh, – | sample standard error of the estimator, EENS ± 1.96·SE (lower bound clipped at 0), SE/EENS |

StormRisk uses frequency weights `p_s = c_s/N`, where `c_s` is the sampled state's count.
Its sample variance is `S² = Σ_s c_s(E_s − EENS)²/(N − 1)` and `SE(EENS) = S/√N`.
For `N = 1` the EENS standard error/interval are undefined; CV is also undefined when EENS is
zero. The interval is a normal/CLT approximation, not a rare-event guarantee. Asset-importance
shares describe co-occurrence with shedding, not causal attribution; multiple outages can make
their shares sum to more than one.

Both are only as meaningful as the outage probabilities supplied; GridStorm does not estimate
failure rates itself.

### N-1 classes (Contingency page)

Each single-branch outage is solved with an AC power flow and classified as one of
`secure`, `thermal_overload`, `voltage_violation`, `islanding`, `non_convergent`, `error`
(`apps/web/src/features/research/lib/n1.ts` reads the class written into the artifact). Thermal
overload means loading > 100 % of the branch rating (`100 · |I| / I_max`); voltage violation means a
bus voltage magnitude outside its [VMIN, VMAX] band [p.u.]; islanding means the outage disconnects
part of the network, whose load is reported as islanded load [MW]; non-convergent means the
Newton–Raphson power flow did not converge, so no post-contingency state is reported.

In StormBench, screening classifies a branch outage as `islanding` when the branch is a bridge
(LODF undefined because 1 − H_ll = 0), detected structurally and cross-checked numerically
(`packages/stormbench/src/stormbench/dc.py`). Precision = flagged-and-true / flagged; recall =
flagged-and-true / true, where "true" is the exact DC or AC result.

### Crisis Response Advisor acceptance rules

The advisor (`workers/advisor/src/gridstorm_advisor/advisor.py`) is deterministic (no LLM). DC
PTDF/LODF sensitivities are used only to shortlist and initially size candidate actions; every
candidate is re-evaluated with a full AC power flow. A candidate is **accepted** only if all hold:

1. The AC power flow (pandapower Newton–Raphson, generator Q limits enforced) converges.
2. Every violation present in the crisis state is cleared.
3. No new violation appears (thermal loading above 100 % of rating, bus voltage outside its
   VMIN/VMAX band, slack active power outside [Pmin, Pmax]; the small numerical tolerances are
   listed verbatim in each artifact's `acceptance_rules`).
4. The action does not increase islanded (unsupplied) load.

Otherwise it is **rejected** with explicit reasons ("violation remains: …", "new violation: …",
"AC power flow did not converge", "islands additional load (… MW)").

Ranking objective [dataset money unit; legacy field names retained]:

```
objective_eur = generation_cost_eur                         (post-action AC dispatch × assumed_duration_h)
              + voll_eur_per_mwh · load_shed_mw · assumed_duration_h
              + switching_penalty_eur · n_switching_actions
```

Accepted candidates are sorted by (objective, max branch loading after, candidate id). The top
accepted candidates are re-checked with AC N-1; the page states whether that check was done.
Baselines (do nothing, proportional load shed) are shown for comparison.

### Grid2Op KPIs (Operations page)

From `workers/grid2op/src/gridstorm_grid2op/kpis.py` (definitions also shipped in every episode
artifact):

| KPI | Definition |
|---|---|
| ρ (rho) | \|I\| / I_thermal per line; ρ > 1 counts as overload |
| Survival | steps played before game over (game over at step *k* ⇒ *k* − 1), out of `max_steps`; *survived* = no game over within `max_steps` |
| Overloaded line-steps | Σ over played steps of the number of connected lines with ρ > 1 |
| Steps with overload | played steps with at least one connected line at ρ > 1 |
| Disconnections / reconnections | connected→disconnected (resp. reverse) line transitions between consecutive valid states |
| Actions | legal, non-do-nothing agent actions (illegal and scenario-forced actions excluded) |
| Illegal actions | agent actions Grid2Op declared illegal (replaced by do-nothing) |
| Blocked actions | agent actions replaced by do-nothing because they tried to reconnect a line within a scenario outage window |
| Forced events | steps whose action was imposed by the scenario rather than chosen by the agent |
| Cumulative reward | Σ of the environment reward over played steps, including the game-over step |
| Mean / max ρ | over connected lines and valid played states |
| Max topological distance | max over states of #disconnected lines + #substations with any element on bus 2 |

## 4. Execution modes: live vs precomputed

| | Live | Precomputed |
|---|---|---|
| Set by | `GRIDSTORM_EXECUTION_MODE=live` (default) | `GRIDSTORM_EXECUTION_MODE=precomputed` |
| Simulations | Queued job; the PyPSA engine runs in a subprocess with time and memory limits | No simulation computation: loads a committed `kind: simulation` artifact matching the scenario hash. No match returns HTTP 409 (`precomputed_result_unavailable`); a declared payload hash mismatch returns 503 (`artifact_integrity_error`). |
| Badge | *live run* | *precomputed* — "Loaded from a stored, reproducible artifact — not computed for this request" |
| Network gate | Only networks in `GRIDSTORM_LIVE_NETWORKS` (default `ac-dc-meshed,pglib-case14-ieee,pglib-case118-ieee,pypsa-eur-be`) solve live. Other networks complete as *precomputed* when a stored artifact matches the scenario hash; otherwise HTTP 422 (`live_execution_unavailable`). Network responses expose `live_execution`. | — |

Every job records its `execution_mode`. The Contingency, Operations and Benchmarks pages are always
precomputed: pandapower N-1, the advisor, Grid2Op, StormBench and StormRisk run offline in their own
environments and publish `gridstorm-artifact/1.0` files under `data/artifacts/<engine>/`.

**Result reuse.** In live mode, when reuse is enabled, a new job whose scenario hash, network
(and dataset version) and execution mode match an earlier completed job with outcome `feasible`
or `infeasible` may complete from that job and is flagged *reused*. Precomputed mode loads the
matching published artifact directly; it does not use the live-job reuse branch
(`services/api/src/gridstorm_api/jobs/service.py`).

## 5. Job states

| Field | Values | Meaning |
|---|---|---|
| `status` | `queued`, `running`, `completed`, `failed`, `cancelled`, `timeout` | infrastructure: did the process finish? |
| `stage` | `queued`, `loading_network`, `applying_scenario`, `building_model`, `solving`, `postprocessing`, `done` | last stage reported by the engine |
| `outcome` | `feasible`, `infeasible`, `error` | scientific: what did the optimiser conclude? |
| `solver.termination_condition` | e.g. `optimal`, `infeasible`, `time_limit` | raw solver verdict |

`status = completed` with `outcome = infeasible` is legitimate: the configured constraints could
not all be satisfied (enabling load shedding or relaxing events may help). Such results do not
provide dispatch metrics/series/assets; missing values must not be read as zero. Results are
served only for `completed` jobs.

## 6. Limitations

- **DC-linearised LOPF**: no reactive power, voltage magnitudes or losses; perfect foresight over the
  horizon; costs are short-run marginal costs from the dataset. Every result lists its assumptions.
- **Line/link outages in PyPSA must span the whole horizon**; partial windows are rejected, not
  approximated.
- **Only PyPSA simulation jobs run live.** Network analytics are precomputed per network. AC N-1,
  advisor, Grid2Op, StormBench and StormRisk studies are precomputed, not recomputed on request.
- **Comparisons are pairwise** and require two completed runs on the same network.
- **Probabilistic metrics** (EENS, LOLP) depend entirely on the assumed outage probabilities.
- **Grid2Op** episodes run on sandbox environments; survival is not evidence of operational safety.
- **Schematic networks** have no geographic meaning.
- **Free-tier hosting**: the backend may sleep when idle (≈ 1 min wake-up), runs one simulation at a
  time with a per-job time and memory limit, and rate-limits POST requests and simulations
  (see [deployment/render.md](deployment/render.md)).
