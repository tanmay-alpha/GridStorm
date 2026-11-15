# Research Workbench (`/workbench`)

The workbench is the entry point to GridStorm's published research. Pick a **research network**,
then a **published study**; the page shows, for the selected artifact:

| Section | Source |
|---|---|
| Scenario and assumptions, limitations | verbatim quotes from the study's doc (`apps/web/src/features/workbench/studies.ts`) |
| Results (headline metrics, method/agent/policy comparisons) | the artifact payload at run time (`GET /api/v1/artifacts/{engine}/{id}`, summary view where available) |
| Execution mode | `offline-only` for every engine except PyPSA (`LIVE_ENGINES = ("pypsa",)`); PyPSA presets are `live` when the network's `live_execution` is true, else `precomputed` |
| Engine and solver | artifact header (`engine_version`, `platform`, `power_flow_engine`) plus the documented environment |
| Dataset and network version | network `network_sha256` / `source` from `GET /networks`, artifact `inputs` with sha256, documented dataset version |
| References | citations copied from the repository docs (mostly `docs/research/research-papers.md` and each study's doc) |
| Reproduce | documented commands and working directory, plus the header `command` of the artifact |

Detailed pages are linked instead of duplicated (`/benchmarks#…`, `/contingency#…`, `/operations`).
Money (Crisis Advisor objectives, PyPSA preset objectives) is formatted in the network's cost basis
via `lib/money.ts`; PGLib and illustrative costs are never labelled EUR.

## Studies

StormBench, StormRisk, Crisis Response Advisor, Grid2Op baseline agents, pandapower AC N-1,
pandapower AC reference validation, SimBench LV time series, cross-engine agreement, StormML and
the PyPSA preset runs. Studies whose artifacts span several networks (`network_id` null,
`multiple` or `multi:…`) are grouped under *Multi-network studies*.

The observed-analogue SciGRID-DE runs ([observed-analogue-scenarios.md](observed-analogue-scenarios.md))
are not listed: their results (`data/observed/analogue-results.json`) are not published as
`gridstorm-artifact/1.0` files, so the API cannot serve them.

`studies.test.ts` keeps the registry honest: every quote, citation and command must appear in the
named file, every doc anchor must exist, every study must match committed artifacts, every engine
with artifacts must have a study, and only engines in `LIVE_ENGINES` may be labelled live.

## Reproduction manifest

*Download reproduction manifest* saves `gridstorm-manifest-<study>-<network>.json`
(`gridstorm-reproduction-manifest/1.0`): study id, docs and references; network id, name,
`network_sha256`, source and cost basis; execution mode; every artifact of the study on that
network (role `result` or `input`) with its header verbatim — `engine_version`, `created_at`,
`command`, `inputs[{path, sha256}]`, `platform`, `execution_mode`, `payload_sha256` — and the API
path of the full document; the documented commands; and how to verify `payload_sha256` (SHA-256 of
the canonical JSON payload: sorted keys, `,`/`:` separators, UTF-8). It is built in the browser
from the artifact catalog; no extra request is made.

## API used

- `GET /api/v1/artifacts?include=header&limit=500` — every index row plus the file's `artifact`
  header (`header: null` if the file is missing). One cached request serves the workbench,
  `/benchmarks`, `/contingency`, `/operations` and `/methods`.
- `GET /api/v1/artifacts/{engine}/{id}?view=summary` — header unchanged, payload without bulky
  per-item fields: `simulation` (whitelist), `benchmark` (no `contingencies`, also inside
  `cases[]`), `risk` (no `states`, `sample_state_index`), `episode` (no `steps`), `timeseries`
  (no `series`). `n_minus_1` and `advisor` answer 422 `summary_view_unsupported` and are fetched in
  full. Against an API without these extensions the web falls back to the full document and shows
  "header not served (needs API ≥ 3.0)" where header fields are missing.

## Transfer sizes (local API, gzip, cold)

| Route | Before: requests / KB (raw KB) | After: requests / KB (raw KB) |
|---|---|---|
| `/benchmarks` | 22 / 119 (1,042) | 7 / 39 (208) |
| `/methods` | 14 / 202 (1,559) | 2 / 17 (106) + 5 manifests when the data table scrolls into view |
| `/operations` | 4 / 267 (1,763) | 5 / 91 (530) |
| `/workbench` (IEEE 14, advisor) | — | 3 / 22 (126) |

Before, `/methods` requested only the first 50 index rows and so missed the StormML and StormRisk
engines; the catalog request now covers all artifacts.

## Reproduce the checks

```sh
cd apps/web
npx vitest run src/features/workbench src/features/research
npx playwright test e2e/workbench-manifest.spec.ts   # needs the local API on :8000 (or GRIDSTORM_API_PROXY)
cd ../../services/api
uv run pytest -q tests/test_artifact_summary_views.py tests/test_http_caching.py
```
