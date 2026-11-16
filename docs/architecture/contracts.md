# GridStorm interface contracts (v1)

Single source of truth for cross-component interfaces. Component owners MUST implement these shapes
exactly; changes go through the integration owner and are recorded in `docs/decisions/`.

All JSON uses `snake_case`. Physical quantities carry the unit in the field name
(`_mw`, `_mwh`, `_mva`, `_kv`, `_pct`, `_eur`, `_eur_per_mwh`, `_h`, `_s`, `_t`).
Monetary suffixes `_eur`, `_eur_per_mwh` (and `_eur_per_h` in legacy research artifacts) are
backward-compatible names, **not currency guarantees**: use `cost_basis` for the actual money unit.
Every payload that holds numbers derived from data carries a `provenance` class from:
`observed | estimated | synthetic | modeled | calculated`.

## 1. Python environments (isolated, never merged)

| Env | Root pyproject | Contents | Key pins |
|---|---|---|---|
| core | `services/api/pyproject.toml` | FastAPI API + `stormspec` + `canonical_grid` + `gridstorm_pypsa` + `gridstorm_analytics` (path deps) | Python 3.11, PyPSA 1.4.x, linopy, highspy, pandas 3 |
| pandapower | `workers/pandapower/pyproject.toml` | `gridstorm_pandapower` + `stormspec` + `canonical_grid` | pandapower 3.5.x (pandas 2.x) |
| advisor | `workers/advisor/pyproject.toml` | `gridstorm_advisor` (Crisis Response Advisor) | pandapower 3.5.x |
| grid2op | `workers/grid2op/pyproject.toml` | `gridstorm_grid2op` | grid2op 1.12.x (pandas < 3) |
| stormbench | `packages/stormbench/pyproject.toml` | `stormbench` | numpy, scipy, pandapower |
| pipelines | `pipelines/network-import/pyproject.toml` | network importers | PyPSA 1.4.x |

Tooling: `uv` per component (`uv sync`, `uv run pytest`), Python 3.11, each component has its own
`uv.lock`. Path dependencies via `[tool.uv.sources] stormspec = { path = "../../packages/stormspec", editable = true }`.
`stormspec` and `canonical_grid` depend only on `pydantic>=2` (no pandas) so every env can import them.

Engines exchange data only through versioned JSON / NetCDF artifacts described below.

## 2. Network datasets — `data/networks/<network_id>/`

```
data/networks/catalog.json            # {"schema_version":"network-catalog/1.0","networks":[{"id","path"}]}
data/networks/<id>/network.nc         # PyPSA NetCDF input model (unsolved), committed only if <= 10 MB
data/networks/<id>/canonical.json     # canonical-grid/1.0 (below)
data/networks/<id>/manifest.json      # dataset-manifest/1.0 (below)
```

Network ids (initial): `ac-dc-meshed`, `scigrid-de`, `pglib-case14-ieee` (or another verified PGLib case),
`pypsa-eur-be` (only if the reduced PyPSA-Eur Belgium build succeeds).

Asset ids are the PyPSA component names, as strings, unchanged. The same ids are used by StormSpec
selectors, results, the API, and the map. Never re-key.

### canonical-grid/1.0

```jsonc
{
  "schema_version": "canonical-grid/1.0",
  "network_id": "scigrid-de",
  "name": "SciGRID Germany (PyPSA example)",
  "coordinate_kind": "geographic" | "schematic",   // schematic => x/y are layout coords, NOT lon/lat
  "crs": "EPSG:4326" | null,
  "snapshots": {"count": 24, "start": "2011-01-01T00:00:00", "end": "2011-01-01T23:00:00", "resolution_h": 1.0},
  "buses":          [{"id","name","x","y","v_nom_kv","carrier","country"}],
  "lines":          [{"id","bus0","bus1","v_nom_kv","s_nom_mva","x_ohm","r_ohm","length_km","num_parallel","carrier"}],
  "transformers":   [{"id","bus0","bus1","s_nom_mva","x_pu","r_pu","tap_ratio"}],
  "links":          [{"id","bus0","bus1","p_nom_mw","efficiency","carrier"}],
  "generators":     [{"id","bus","carrier","p_nom_mw","marginal_cost_eur_per_mwh","p_nom_extendable","is_variable"}],
  "loads":          [{"id","bus","p_peak_mw","p_mean_mw","energy_mwh"}],
  "storage_units":  [{"id","bus","carrier","p_nom_mw","max_hours","efficiency_store","efficiency_dispatch"}],
  "stores":         [{"id","bus","carrier","e_nom_mwh"}],
  "carriers":       [{"id","color","co2_emissions_t_per_mwh","nice_name"}],
  "summary": {"counts": {...}, "capacity_by_carrier_mw": {...}, "peak_load_mw": 0.0, "total_load_mwh": 0.0},
  "field_provenance": {"buses.x": "observed", "generators.marginal_cost_eur_per_mwh": "modeled", ...},
  "assumptions": ["..."]
}
```
Missing values are `null`, never invented. Units: kV, MW, MVA, MWh, ohm, km,
`cost_basis.price_unit`, t/MWh.

### dataset-manifest/1.0

```jsonc
{
  "schema_version": "dataset-manifest/1.0",
  "network_id": "...", "name": "...", "description": "...",
  "source": {"url": "...", "version": "...", "publication_date": "...", "upstream_commit": "..."},
  "retrieved_at": "ISO-8601", "files": [{"path": "network.nc", "sha256": "...", "bytes": 0}],
  "license": {"spdx": "...", "url": "...", "attribution": "...", "redistribution": "permitted|restricted|unknown"},
  "coverage": {"geographic": "...", "temporal": "..."},
  "units": {...}, "missing_value_policy": "...",
  "quality_flags": ["..."], "transformations": [{"step", "tool", "version", "description"}],
  "engines": ["pypsa", "pandapower", "grid2op"],
  "provenance_class": "observed|estimated|synthetic|modeled"
}
```

### Cost basis — `gridstorm-cost-basis/1.0`

Optional on historical manifests/results for backward compatibility; declared by all five bundled
datasets and embedded by new PyPSA results. Network summary/detail expose the manifest basis.

```jsonc
{
  "schema_version": "gridstorm-cost-basis/1.0",
  "kind": "currency_verified|benchmark_nominal|illustrative",
  "currency": "EUR",                 // null unless currency_verified
  "currency_year": 2025,             // null if not verified; not weather/planning year
  "money_unit": "EUR",               // or "PGLib cost units", "illustrative cost units"
  "price_unit": "EUR/MWh",           // exactly money_unit + "/MWh"
  "comparability_key": "source-and-currency-basis identifier",
  "provenance": "Coefficient source and transformation evidence.",
  "assumptions": ["..."],
  "penalties": [                    // result only; [] if load shedding is disabled
    {"term": "load_shedding", "value_per_mwh": 10000, "unit": "EUR/MWh",
     "nature": "penalty", "description": "Scenario VOLL in the dataset money unit."}
  ]
}
```

All monetary objective terms, including VOLL, are in the dataset basis. The legacy scenario
`voll_eur_per_mwh` is interpreted in that basis, not converted from EUR. Comparison reports expose
`cost_basis` and `costs_comparable`, and each run reference carries its own basis. Only equal,
non-empty `comparability_key` values permit monetary deltas; otherwise monetary `delta` and
`delta_pct` are `null`. Markdown and analytics unit labels use the same basis. Legacy stored
results used to build reports fall back to the catalog basis without rewriting their hashed
result bytes. Historical stored comparisons are hydrated on read, with a response hash for the
hydrated representation. Unknown provenance is labelled "cost units (basis unknown)", never EUR.

See [the coefficient audit](../research/cost-basis-audit.md).


## 3. StormSpec — `packages/stormspec` (Python package `stormspec`, `stormspec/1.0`)

Pydantic v2 models, exported JSON Schema at `packages/stormspec/schema/stormspec-1.0.schema.json`.

```yaml
schema_version: stormspec/1.0
id: winter-stress-001            # slug ^[a-z0-9][a-z0-9-]{2,63}$
name: Winter stress
description: ...
dataset: {network_id: scigrid-de, sha256: <network.nc sha256 | null>}
horizon: {start: 0, snapshots: 24}            # snapshot indices into the network
events:                                       # discriminated union on `type`
  - {type: demand_multiplier, value: 1.18, buses: null, window: null}
  - {type: renewable_availability_multiplier, carrier: wind, value: 0.55, window: {start: 0, end: 12}}
  - {type: line_outage, asset_id: "<real line id>", component: line}  # component: line | transformer (ids may collide across lists, e.g. scigrid-de)
  - {type: link_outage, asset_id: "..."}
  - {type: generator_outage, asset_id: "...", window: null}
  - {type: storage_state, asset_id: "...", initial_soc_fraction: 0.2}
mitigation:
  storage_dispatch: true
  curtailment: true
  load_shedding: {enabled: true, voll_eur_per_mwh: 10000}
execution:
  engine: pypsa                    # pypsa | pandapower | grid2op
  formulation: lopf                # lopf | ac_pf | n_minus_1 | sequential
  solver: highs
  solver_options: {time_limit_s: 120, threads: 1}
  deterministic: true
  seed: 0
assumptions: ["..."]
```

Public API (Python):
- `stormspec.Scenario` (root model), event models, `Mitigation`, `Execution`.
- `stormspec.canonical_json(scenario) -> bytes` (sorted keys, no whitespace, excluding `name`/`description`)
  and `stormspec.scenario_hash(scenario) -> str` (sha256 hex of canonical json).
- `stormspec.capabilities.EngineCapabilities` + `CAPABILITIES: dict[str, EngineCapabilities]`
  declaring per engine: supported formulations, event types, whether events accept `window`.
- `stormspec.validate(scenario, network: canonical_grid.CanonicalNetwork | dict) -> ValidationReport`
  `ValidationReport{valid: bool, errors: [Issue], warnings: [Issue]}`, `Issue{code, path, message}`.
  Checks: asset ids exist with the right component type, carriers exist, horizon within snapshots,
  windows within horizon, multiplier ranges, engine capability (unsupported => error `unsupported_operation`).
- `stormspec.manifest.ExecutionManifest` (`execution-manifest/1.0`): scenario_hash, dataset sha256,
  engine name/version, solver name/version/options, python/platform, started_at, finished_at,
  result_sha256, git_sha.
- Unsupported operations are REJECTED, never silently approximated (e.g. PyPSA line outage with a
  partial time window cannot be represented by s_max_pu=0 because KVL would still bind the angles —
  reject unless the window covers the whole horizon).

Preset scenarios live in `packages/stormspec/presets/*.yaml` and must reference real asset ids.

## 4. Simulation result — `gridstorm-result/1.0`

Produced by `gridstorm_pypsa.run_scenario(scenario: Scenario, network_dir: Path, *, progress=None) -> dict`
(also CLI `python -m gridstorm_pypsa run --scenario s.json --network-dir data/networks/<id> --out result.json`,
which writes the result and prints stage lines `STAGE <name>` to stdout). `progress` is an optional
callable `progress(stage: str)`. Stages, in order:
`loading_network, applying_scenario, building_model, solving, postprocessing, done`.

```jsonc
{
  "schema_version": "gridstorm-result/1.0",
  "scenario_id": "...", "scenario_hash": "...", "network_id": "...",
  "engine": {"name": "pypsa", "version": "1.4.0", "formulation": "lopf"},
  "solver": {"name": "highs", "version": "...", "status": "ok|warning|error",
             "termination_condition": "optimal|infeasible|infeasible_or_unbounded|time_limit|...",
             "objective_eur": 0.0, "wall_time_s": 0.0},
  "outcome": "feasible|infeasible|error",
  "snapshots": ["ISO-8601", ...], "snapshot_weightings_h": [1.0, ...],
  "metrics": {
    "total_load_mwh", "served_load_mwh", "unserved_energy_mwh", "peak_load_shed_mw",
    "load_shed_hours", "total_system_cost_eur", "generation_cost_eur", "load_shedding_cost_eur",
    "generation_by_carrier_mwh": {}, "curtailment_mwh", "curtailment_by_carrier_mwh": {},
    "max_line_loading_pct", "mean_line_loading_pct", "congested_line_count",   // >= 99.9 % at any snapshot
    "storage_discharge_mwh", "storage_charge_mwh", "co2_emissions_t",
    "balance_residual_max_mw"     // max |sum injections| per snapshot, must be ~0
  },
  "series": {
    "load_mw": [], "load_shed_mw": [], "generation_by_carrier_mw": {"wind": []},
    "storage_dispatch_mw": [], "storage_soc_mwh": [], "curtailment_mw": [],
    "mean_marginal_price_eur_per_mwh": []
  },
  "assets": {
    "lines":   [{"id", "s_nom_mva", "outaged", "flow_mw": [], "loading_pct": []}],
    "links":   [{"id", "p_nom_mw", "outaged", "flow_mw": []}],
    "buses":   [{"id", "marginal_price_eur_per_mwh": [], "load_shed_mw": []}],
    "generators": [{"id", "carrier", "p_mw": [], "available_mw": [], "outaged"}],
    "storage_units": [{"id", "p_mw": [], "soc_mwh": []}]
  },
  "assumptions": ["DC linearised power flow (LOPF) — no reactive power, voltage magnitudes or losses", ...],
  "warnings": [],
  "manifest": { /* execution-manifest/1.0 */ }
}
```
Load shedding is modelled as a dispatchable generator per load bus (carrier `load_shedding`,
marginal cost = VOLL in `cost_basis.price_unit`).
`E_unserved = Σ_t P_shed,t · Δt` with Δt from snapshot weightings.
Infeasible scenarios return `outcome: infeasible` with empty series — never fabricated numbers.

## 5. Precomputed engine artifacts — `data/artifacts/<engine>/<artifact_id>.json`

Every artifact (pandapower N-1, advisor runs, grid2op episodes, stormbench results, precomputed PyPSA
results, distribution time series, stormrisk outage risk) is a JSON object with a top-level `artifact`
header:
```jsonc
{"artifact": {"schema_version": "gridstorm-artifact/1.0", "artifact_id": "...", "kind": "n_minus_1|advisor|episode|benchmark|simulation|timeseries|risk",
              "engine": "pandapower", "engine_version": "...", "network_id": "...", "created_at": "...",
              "command": "uv run python -m ...", "inputs": [{"path", "sha256"}], "platform": "...",
              "execution_mode": "precomputed", "payload_sha256": "..."},
 "payload": { ... kind-specific ... }}
```
`payload_sha256` = sha256 of canonical JSON (sorted keys, compact separators) of `payload`.
Each engine directory has an `index.json` listing its artifacts (`artifact_id`, `kind`, `network_id`, `title`).
Artifacts must be small (< 5 MB each); downsample/round floats to 4 significant decimals where needed.

## 6. HTTP API — `services/api` (FastAPI, base path `/api/v1`)

Errors: `{"error": {"code": "string", "message": "string", "details": {}}}` with correct HTTP status.
Pagination: `?limit=&offset=` → `{"items": [...], "total": n, "limit": n, "offset": n}`.

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | liveness `{status, version, git_sha}` |
| GET | `/ready` | `{status, checks: {database, storage, solver, datasets}}` |
| GET | `/api/v1/networks` | NetworkSummary page |
| GET | `/api/v1/networks/{id}` | summary + manifest + assumptions |
| GET | `/api/v1/networks/{id}/assets?type=buses\|lines\|...` | canonical rows page |
| GET | `/api/v1/networks/{id}/geojson` | FeatureCollection of buses (Point) and lines/links (LineString), `properties.id` = asset id |
| GET | `/api/v1/networks/{id}/analytics/{kind}` | PyPSA-Explorer-derived analytics (capacity, energy_balance, costs) |
| GET | `/api/v1/scenarios` | presets + saved |
| POST | `/api/v1/scenarios/validate` | ValidationReport |
| POST | `/api/v1/scenarios` | save (validates) → ScenarioRecord `{id, hash, spec, preset, owner_id, created_at}` |
| GET | `/api/v1/scenarios/{id}` | |
| POST | `/api/v1/simulations` | `{scenario_id}` or `{scenario: spec}` → 202 Job; identical hash + completed result may be reused (flagged `reused: true`) |
| GET | `/api/v1/simulations` | job page |
| GET | `/api/v1/simulations/{id}` | Job |
| POST | `/api/v1/simulations/{id}/cancel` | |
| POST | `/api/v1/simulations/{id}/recompute` | re-runs the stored scenario of a completed job whose result blob is gone (live-eligible networks only); writes a NEW artifact with `recomputed_from` provenance; never reuses the lost checksum |
| GET | `/api/v1/simulations/{id}/metrics` | result.metrics + solver |
| GET | `/api/v1/simulations/{id}/result` | full gridstorm-result, sha256-verified on read; **410 `artifact_unavailable`** if the durable blob is gone, **500 `artifact_integrity_error`** on checksum mismatch |
| GET | `/api/v1/simulations/{id}/artifacts` | stored artifact list with sha256 |
| POST | `/api/v1/comparisons` | `{baseline_job_id, scenario_job_id}` → Comparison |
| GET | `/api/v1/comparisons/{id}` | |
| GET | `/api/v1/reports/{id}?format=json\|md` | reproducible report for a comparison or job |
| GET | `/api/v1/artifacts?engine=&kind=&network_id=` | precomputed artifact index |
| GET | `/api/v1/artifacts/{engine}/{artifact_id}` | precomputed artifact |
| GET | `/api/v1/data/catalog?category=&provenance=&region=&source=&q=` | Data Observatory page of dataset summaries + `facets` (whole catalog) + `bundle` status; merges `data/observatory/`, one `network-<id>` entry per network, one `study-<id>` entry per research study group |
| GET | `/api/v1/data/catalog/{id}` | full dataset entry (quality checks incl. load-time sha256 verification, transformations); 404 `not_found` |
| GET | `/api/v1/data/catalog/{id}/series?series=&start=&end=&resolution=auto\|raw\|PT3H\|P1D\|P7D&agg=mean\|min\|max&max_points=` | bounded series (≤ 3 years, ≤ 2000 points, UTC-aligned buckets, missing = `null`); 409 `not_a_series_dataset`, 422 `range_too_large`/`unknown_series`, 503 `dataset_unverified` |
| GET | `/api/v1/data/catalog/{id}/export?series=&start=&end=` | raw CSV attachment with `#` source/licence/attribution/sha256 header; 403 `export_not_permitted` |

Data catalog routes: `Cache-Control: public, max-age=300` + body-hash `ETag`; details in
[backend.md](backend.md#data-observatory-catalog-apiv1data), rationale in
[ADR 0003](../decisions/0003-file-backed-data-observatory.md).

Job:
```jsonc
{"id", "scenario_id", "scenario_hash", "network_id", "execution_mode": "live|precomputed", "reused": false,
 "status": "queued|running|completed|failed|cancelled|timeout",          // infrastructure status
 "stage": "queued|loading_network|applying_scenario|building_model|solving|postprocessing|done",
 "stage_history": [{"stage", "at"}],
 "outcome": "feasible|infeasible|error|null",                            // scientific outcome
 "solver": {"name", "version", "status", "termination_condition", "objective_eur", "wall_time_s"} | null,
 "error": {"code", "message"} | null,
 "created_at", "started_at", "finished_at", "result_sha256", "result_available", "owner_id"}
```
No percentage progress. Execution runs in a subprocess with timeout and memory limit, bounded
concurrency (default 1), persisted job table, stale-`running` recovery on startup.

## 7. Frontend — `apps/web`

React + TypeScript + Vite + Tailwind + MapLibre GL (+ deck.gl only if needed) + ECharts, TanStack Query,
react-router. `VITE_API_BASE_URL` selects the backend. Basemap without API keys (OpenFreeMap / OSM
attribution). Schematic networks (`coordinate_kind: schematic`) render on a blank canvas labelled
"Schematic layout — not geographic". Routes: `/` explorer, `/studio`, `/runs/:id`, `/compare`,
`/library`, `/contingency`, `/operations`, `/benchmarks`, `/methods`.
