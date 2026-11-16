# Production data inventory (GridStorm 3.2, G32-02)

**Status: PARTIAL — database and Storage audit BLOCKED.** Everything below that comes from the
public API or the repository was measured on **2026-11-16 20:49:29 UTC** (local date 2026-11-17).
Every cell that needs a direct Postgres connection reads **BLOCKED: no authorized DB credentials
in this environment (2026-11-17)**; nothing in this document is estimated.

## Method

| Source | How | Writes |
|---|---|---|
| Repository | `scripts/inventory/production_inventory.py --sections repo` on `release/gridstorm-3.2`: file counts/bytes, canonical/manifest SHA-256, `.dockerignore` allow-list | none |
| Public API | same script, `--sections api`: anonymous `GET` on `https://gridstorm-api.onrender.com` (`/health`, `/ready`, `/api/v1/networks`, `/scenarios`, `/simulations` all pages, `/artifacts` all pages, per job `/result` + `/metrics` + `/artifacts`, the three comparison ids recorded in committed docs + their Markdown reports, `/api/v1/comparisons`); result bodies hashed and compared with the job's `result_sha256` | none (GET only) |
| Supabase Postgres + `storage` schema | same script, `--sections db` (see [How to complete](#how-to-complete)) | none by construction: autocommit connection, every query inside `BEGIN READ ONLY … ROLLBACK` with `transaction_read_only = on` asserted |
| Web UI | source references in `apps/web/src` (routes in `router.tsx`, `artifacts/<engine>` and API calls); not a live browser run | none |

**Why the DB section is blocked.** `SUPABASE_DB_HOST`, `SUPABASE_DB_USER` and
`SUPABASE_DB_PASSWORD` in this shell are literal placeholders (`YOUR_SUPABASE_DB_…`); only
`PORT`/`NAME` hold values. The coordinator confirmed no other authorized credential source:
the Render CLI token is expired, and the Supabase variables were intentionally removed from the
Vercel web project (POST-06). No other credential source was tried. The script's `db` section ran
and returned `BLOCKED: neither DATABASE_URL nor SUPABASE_DB_HOST/PORT/NAME/USER/PASSWORD holds
real credentials` without connecting to anything.

## Project identification

| Item | Value | Evidence |
|---|---|---|
| API build | `127db27` (`127db2755b83…`) | `GET /health` |
| Database backend | `postgres` | `GET /ready` → `checks.database = {status: ok, kind: postgres}` |
| Artifact storage | `supabase:gridstorm-artifacts`, `durable: true`, write/read/delete round trip ok | `GET /ready` → `checks.storage` |
| Catalog | 5 networks loaded | `GET /ready` → `checks.datasets` |
| Supabase project | `gridstorm-db`, eu-central-1, free plan | TODO P6-02 (recorded 2026-11-15); **project ref and schema contents not verified: BLOCKED** |

Confirming that the credentials point at GridStorm needs `public.schema_migrations` and the 12
`public` tables (`network_datasets`, `simulation_jobs`, …) to exist. The script checks both
before it reports anything else.

## Migrations

| Version | Repo | Applied in production |
|---|---|---|
| `0001_core_schema.sql` | present (291 lines) | BLOCKED; TODO P6-02 records it applied |
| `0002_row_level_security.sql` | present (90 lines) | BLOCKED; TODO P6-02 records it applied |
| `0003_job_indexes_and_client_grants.sql` | present (38 lines) | BLOCKED; TODO POST-06 records it applied |

Tracking: `public.schema_migrations(version, sha256, applied_at)`, written by
`gridstorm_api.db.migrate` and by the psql runbook in `docs/deployment/backend.md`.

## Tables, rows, size

Row counts, `pg_total_relation_size`, `pg_database_size`, `relrowsecurity`: **BLOCKED: no
authorized DB credentials in this environment (2026-11-17)**.

Values the anonymous API can see (lower bounds, public rows only):

| Table | Lower bound visible via API | How |
|---|---|---|
| `network_datasets` | 5 public datasets | `/api/v1/networks` total |
| `scenario_definitions` | 12 public presets, 0 public saved scenarios | `/api/v1/scenarios` (anonymous callers see presets only) |
| `simulation_jobs` | 12 public jobs | `/api/v1/simulations` total |
| `simulation_metrics` | ≥ 12 rows (every public job's `/metrics` returned 200) | per-job GET |
| `simulation_artifacts` | ≥ 17 rows: 7 jobs × (result + scenario) + 3 logs (via `/artifacts`); the 5 lost jobs return 410, so their rows were not readable | per-job GET |
| `comparison_reports` | ≥ 1 (`4f5661ec`) | GET by id |
| `network_versions`, `dataset_sources`, `ingestion_runs`, `profiles`, `audit_events`, `schema_migrations` | not exposed by the API | BLOCKED |

## Datasets (catalog networks)

| Network | Repo files / bytes | canonical.json sha256 | manifest.json sha256 | Provenance | Licence | API buses | Live execution | Engines |
|---|---|---|---|---|---|---|---|---|
| `ac-dc-meshed` | 9 / 139,404 | `c974af9fe4ed…` | `ec676097a770…` | synthetic | CC-BY-4.0 | 9 | yes | pypsa |
| `pglib-case118-ieee` | 12 / 369,460 | `3405e1344255…` | `89908030d6a7…` | synthetic | CC-BY-4.0 | 118 | yes | pypsa, pandapower |
| `pglib-case14-ieee` | 12 / 128,560 | `ea1f3ef81898…` | `3f782154c305…` | synthetic | CC-BY-4.0 | 14 | yes | pypsa, pandapower |
| `pypsa-eur-be` | 8 / 357,347 | `751a50281380…` | `760763ad07b5…` | modeled | ODbL-1.0 | 10 | yes | pypsa |
| `scigrid-de` | 9 / 2,304,293 | `3053614c8dc3…` | `3172e6f23d7c…` | modeled | CC-BY-4.0 | 585 | **no** (precomputed only) | pypsa |

`network_versions` rows should match the (canonical, manifest) SHA pairs above, because
`sync.py` registers a new version and a succeeded `ingestion_runs` row whenever a pair changes.
Whether they match is BLOCKED. Asset rows are never in SQL: `network_assets` is intentionally not
created (`0001_core_schema.sql` header), so assets are served from `canonical.json` in the image.

## Jobs, metrics, results (public jobs via API)

All 12 public jobs: `status = completed`, `outcome = feasible`, solver `highs`, `visibility =
public`, `owner_id = null` (anonymous), created 2026-11-14 23:40:35Z → 2026-11-15 09:39:10Z.
There are no failed, cancelled, timed-out or queued public jobs. Private and owned jobs are
BLOCKED.

| Network | Mode | Jobs | Result HTTP 200 (body sha = `result_sha256`) | Result HTTP 410 | Metrics 200 |
|---|---|---|---|---|---|
| `pglib-case14-ieee` | live | 8 (2 `reused`, 1 `recomputed_from`) | 3 (`34424ec2`, `458fddab`, `c328baa0`) | 5 | 8 |
| `scigrid-de` | precomputed | 4 | 4 (`c800561d`, `5323bc95`, `f2fc0cf3`, `5dafdc1a`; one shared blob `e3e3494b…`, 1,241,443 B) | 0 | 4 |

All 7 available result bodies were downloaded and hashed: 7/7 match the recorded
`result_sha256`. Lineage: `4104c5fc` reused `0137980b`; `25e3fb2a` reused `06b4f635`;
`458fddab` recomputed `2d47898b`.

Artifact references of the 7 available jobs (from `/api/v1/simulations/{id}/artifacts`, all
`storage_backend = supabase`, content-addressed `sha256/<hash>.<ext>`):

| Kind | Rows | Distinct keys | Bytes (distinct keys, as recorded in SQL) |
|---|---|---|---|
| result | 7 | 4 | 1,267,419 |
| scenario | 7 | 3 | 2,581 |
| log | 3 | 3 | 5,175 |
| **total** | 17 | 10 | **1,275,175** |

The 4 precomputed jobs have no `log` artifact. Of the three live IEEE-14 scenario blobs, two jobs
share one (`dbd89795…`).

Observation: the 4 restored SciGRID jobs serve the `96f3f3a`-era baseline payload (1,241,443 B,
sha `e3e3494b…`). The currently committed `data/artifacts/pypsa/scigrid-de-baseline.json` is
1,244,046 B. That is expected, because R2-01 restores the bytes recorded for the job, but a
reader of a job and of the current artifact sees two different payload versions.

## Supabase Storage objects

Bucket list, object count, total bytes from `metadata->>'size'`, mimetypes, eTags, orphan objects
and key-to-object reconciliation: **BLOCKED: no authorized DB credentials in this environment
(2026-11-17)**.

Measured indirectly: `/ready` proves the bucket `gridstorm-artifacts` accepts write/read/delete
(probe under `_ready`). The 10 distinct keys above exist and verify, because their 7 result
bodies hashed correctly and the jobs report `result_available: true`. Storage stores no checksum
metadata of its own (the API keeps sha256 in `simulation_artifacts.sha256`, and the key itself is
the sha256), so integrity is verified on read.

## Broken / missing references

| Ref | Job | Network / scenario | Recorded `result_sha256` | API | Class |
|---|---|---|---|---|---|
| result blob | `2d47898b-8546-420e-a382-acc29f14d3d4` | case14 / baseline | `f6a74d7c232e…` | `/result` 410 `artifact_unavailable`, `/artifacts` 410; recomputed as `458fddab` | Broken reference |
| result blob | `0137980b-a106-49ed-a292-7fa1bacf7813` | case14 / baseline | `87386d4782ff…` | 410 / 410 | Broken reference |
| result blob | `06b4f635-4eb8-4d34-99ca-362d53b88e6c` | case14 / gen-1-outage | `63a3817850ee…` | 410 / 410 | Broken reference |
| result blob | `4104c5fc-a7cc-4857-b074-e865a4afd80d` | case14 / baseline (reused `0137980b`) | `87386d4782ff…` | 410 / 410 | Broken reference |
| result blob | `25e3fb2a-8fcb-40f2-b6f7-5dc4676cc304` | case14 / gen-1-outage (reused `06b4f635`) | `63a3817850ee…` | 410 / 410 | Broken reference |
| comparison | `9257ed4c-359c-4862-9001-a32f4b031981` (`docs/deployment/backend.md`) | — | — | 404 `comparison_not_found`; created on the SQLite-ephemeral store on 2026-11-14 | Broken reference (documented id of a record that no longer exists) |
| comparison | `a3ef641c-7748-40fd-867a-75b4696f6cf2` (`docs/audit/data/journey-3.0-local.json`) | — | — | 404; local-run id, never in production | Not present in the source |
| comparison | `ee5566d6…` (TODO G3-09) | — | — | only the prefix is recorded, so it cannot be fetched | Stored but not exposed (no list endpoint) |

Of the 9 legacy jobs, 4 were restored (R2-01) and **5 remain HTTP 410**. Their metadata and
metrics are intact (`/metrics` 200). The 5 lost blobs cover only 3 distinct result hashes. Because
live results embed solver wall time, those bytes cannot be reproduced.

The stored comparison `4f5661ec-e6f1-4600-96ed-710709f10c36` (case14, report sha
`30fe7e725fcc…`) still returns 200, and its Markdown report returns 200 (8,000 B). Its baseline
(`0137980b`) and scenario (`06b4f635`) are both lost jobs: the report survives because
`comparison_reports.report` is self-contained JSONB, but it can no longer be rebuilt or
re-verified from its inputs.

Not measured (BLOCKED): `simulation_artifacts` rows whose key has no `storage.objects` row,
size mismatches, orphan objects, completed jobs without a result row, and metrics on non-completed
jobs. The script computes all of these.

## RLS, policies, grants

Live `pg_class.relrowsecurity`, `pg_policies`, `role_table_grants` and the `SET LOCAL ROLE anon`
SELECT probe: **BLOCKED: no authorized DB credentials in this environment (2026-11-17)**.

Expected state from the repo (what the script verifies):

- RLS is enabled on all 12 `public` tables (11 in 0002 + `schema_migrations` in the bootstrap).
  There are 15 policies: profiles 3 (own row); datasets/versions/sources 3 public-read; scenarios
  4; jobs 1 read; metrics 1 and artifacts 1 (read when the parent job is readable); comparisons 2
  (read, delete own). `ingestion_runs`, `audit_events` and `schema_migrations` have no policies,
  so clients have no access.
- 0003 revokes TRUNCATE, TRIGGER and REFERENCES from `anon`/`authenticated`.
- The API connects as the owner and bypasses RLS; it applies `visible()` itself.

Concerns to check once measurable (repo-derived, not yet observed):

1. Supabase's default grants leave `INSERT/UPDATE/DELETE` to `anon` on every `public` table. Only
   the absence of a policy blocks writes. Revoking DML from `anon` (and from `authenticated` where
   no write policy exists) would be defence in depth. Do not apply until grants are measured.
2. `simulation_jobs_read`, `simulation_artifacts_read` and `comparison_reports_read` expose public
   rows to `anon` through PostgREST, including `spec`, `stage_history`, `error`, `worker_id` and
   `storage_key`. This matches the public API's data, but `worker_id`/`heartbeat_at` are
   operational fields that the API itself does not return.
3. Storage: the bucket must be private with no `storage.objects` policies for `anon`. Today only
   the doc claims this (backend.md); the script reads `storage.buckets.public` and `pg_policies`
   for schema `storage`.

## Index use and query performance

`pg_stat_user_indexes`, `pg_stat_user_tables`, `pg_stat_statements`, `EXPLAIN (ANALYZE, BUFFERS)`
and the `SELECT 1` round trip: **BLOCKED: no authorized DB credentials in this environment
(2026-11-17)**.

API end-to-end latency from this machine (5 samples each, median; includes TLS, Render/Cloudflare,
and API ↔ Supabase round trips):

| Request | Median ms | Samples ms |
|---|---|---|
| `/health` (no DB; network baseline) | 272.3 | 285.7, 266.5, 272.3, 265.8, 310.6 |
| `/api/v1/simulations?limit=50` (count + page + `result_available` batch) | 475.5 | 796.2, 475.5, 438.5, 758.6, 321.1 |
| `/api/v1/simulations/{id}` | 316.9 | 302.7, 617.3, 295.0, 327.6, 316.9 |
| `/api/v1/simulations/{id}/metrics` | 310.6 | 331.0, 295.4, 310.6, 331.4, 302.9 |
| `/api/v1/networks` (file-backed) | 283.0 | 260.6, 292.5, 278.0, 303.3, 283.0 |
| `/api/v1/scenarios` | 298.6 | 331.4, 336.9, 298.6, 290.3, 296.0 |

The first `/health` of the run took 766.1 ms and `/ready` took 668.3 ms; the earlier run at
20:47Z took 25,301 ms for `/ready`, with a cold solver/Storage probe. DB-backed single-row
endpoints (job, metrics, scenarios) add about 25–45 ms over `/health`. The job list adds about 200 ms and has two slow
outliers (≈ 760–800 ms). That fits its extra Storage existence check (`exists_many`), which
`result_available` caches, rather than SQL time, but the split is not measured.

Queries the script EXPLAINs (from `routers/simulations.py`, `routers/scenarios.py`,
`routers/comparisons.py`, `jobs/service.py`, `jobs/results.py`, `jobs/worker.py`): public job
count, newest-first page, per-network page, `mine` (anonymous), get job, metrics by job,
artifacts by job, `result_available` batch, reuse candidates, worker claim candidate (without
`FOR UPDATE`, which a read-only transaction forbids), active-job count, comparison
existing-report lookup, comparison by id, preset list.

## Free-tier quota

Limits from <https://supabase.com/pricing> (read 2026-11-17), Free plan: 500 MB database
size, 1 GB file storage, 5 GB egress, 50 MB maximum upload size, and projects paused after 1 week
of inactivity.

| Resource | Used | Limit | Share |
|---|---|---|---|
| Database (`pg_database_size`) | BLOCKED | 500 MB | — |
| Storage (sum of `storage.objects` size) | BLOCKED. Lower bound: ≥ 1,275,175 B referenced by the 7 available public jobs (SQL-recorded sizes, read via API) | 1 GB | ≥ 0.12 % |
| Largest single object seen | 1,241,443 B (SciGRID result) | 50 MB upload | < 3 % |

## Coverage matrix

Columns: **Repo** = committed files · **Image** = shipped in the API image (`.dockerignore`
allow-list: `data/networks/`, `data/artifacts/`, `packages/stormspec/presets/`,
`database/migrations|dev|seeds/`, source trees) · **Postgres** · **Storage** = Supabase bucket
`gridstorm-artifacts` · **API** = served by the public API (measured) · **UI** = referenced by
`apps/web/src`. For each "no", the reason uses exactly one of the eight classes.

| Data family | Repo | Image | Postgres | Storage | API | UI |
|---|---|---|---|---|---|---|
| Networks ×5 (manifest, canonical, network file) | yes: 50 files, 3,299,064 B | yes | dataset/version/source rows expected via `sync_catalog` (BLOCKED); asset rows: no, Intentionally not ingested | no, File-backed instead of SQL-backed | yes: 5 networks, counts, cost basis, `live_execution` (4 true, scigrid-de false) | yes: Explorer, Studio |
| StormSpec presets | yes: 12 files, 11,245 B | yes | `scenario_definitions` `is_preset` expected via `sync_presets` (BLOCKED) | no, File-backed instead of SQL-backed | yes: 12 presets | yes: Studio |
| Live runs of SciGRID-DE presets | — | — | — | — | no: 422 `live_execution_unavailable`. Unsupported modeling capability (exceeds free-tier memory) | precomputed path only |
| Precomputed PyPSA simulations (`data/artifacts/pypsa`) | yes: 13 files, 7,583,675 B | yes | no, File-backed instead of SQL-backed (a job row exists only when a user submits one: 4 scigrid jobs) | only blobs copied into jobs (1 distinct result) | yes: 12 artifacts, 7,572,487 B | yes: Benchmarks, Workbench, Mitigation |
| OPSD-derived hourly demand + daily renewable multipliers (`data/observed/opsd-de`) | yes: 2 files, 22,617 B | no, Stored but not exposed | no, File-backed instead of SQL-backed | no, File-backed instead of SQL-backed | no, Stored but not exposed | no, Stored but not exposed |
| OPSD / ENTSO-E actual load and actual generation hourly series | no, Legally restricted (not on the ENTSO-E free re-use list; manifest `redistribution: derived-only`) | no, Legally restricted | no, Legally restricted | no, Legally restricted | no, Legally restricted | no, Legally restricted |
| NASA POWER hourly T2M/WS10M extract (`data/observed/nasa-power-de`) | yes: 2 files, 82,124 B (CSV 2,017 lines incl. header) | no, Stored but not exposed | no, File-backed instead of SQL-backed | no, File-backed instead of SQL-backed | no, Stored but not exposed | no, Stored but not exposed |
| Observed-analogue scenarios (`data/scenarios/observed`) | yes: 3 YAML, 21,284 B | no, Stored but not exposed | no, Intentionally not ingested (not presets; `sync_presets` reads only `packages/stormspec/presets`) | no, File-backed instead of SQL-backed | no, Stored but not exposed | no, Stored but not exposed (Workbench lists 10 studies, analogues excluded per G3-12) |
| Observed-analogue results (`data/observed/analogue-results.json`, 4 runs on scigrid-de, provenance `modeled`) | yes: 13,264 B | no, Stored but not exposed | no, File-backed instead of SQL-backed | no, File-backed instead of SQL-backed | no, Stored but not exposed | no, Stored but not exposed |
| PGLib StormBench (`stormbench`, cases 14…1354-pegase) | yes: 8 files, 1,648,245 B | yes | no, File-backed instead of SQL-backed | no, File-backed instead of SQL-backed | yes: 7 artifacts, 1,646,829 B | yes: Benchmarks |
| Live jobs on PGLib case30/57/300/1354 | no network in catalog | — | — | — | no, Unsupported modeling capability (catalog limited to 5 networks; results exist only as StormBench/pandapower/stormml artifacts) | — |
| pandapower N-1 + AC reference (`pandapower`) | yes: 5 files, 749,103 B | yes | no, File-backed instead of SQL-backed | no, File-backed instead of SQL-backed | yes: 4 artifacts, 748,181 B | yes: Contingency, Benchmarks |
| grid2op l2rpn-case14-sandbox episodes (`grid2op`) | yes: 13 files, 6,718,401 B | yes | no, File-backed instead of SQL-backed | no, File-backed instead of SQL-backed | yes: 12 artifacts, 6,704,667 B | yes: Operations |
| SimBench LV-rural1 time series (`distribution`) | yes: 10 files, 703,307 B | yes | no, File-backed instead of SQL-backed | no, File-backed instead of SQL-backed | yes: 9 artifacts, 700,251 B | yes: Workbench |
| StormRisk (`stormrisk`) | yes: 3 files, 1,133,016 B | yes | no, File-backed instead of SQL-backed | no, File-backed instead of SQL-backed | yes: 2 artifacts, 1,132,155 B | yes: Benchmarks |
| Advisor (`advisor`) | yes: 6 files, 430,070 B | yes | no, File-backed instead of SQL-backed | no, File-backed instead of SQL-backed | yes: 5 artifacts, 428,225 B | yes: Contingency, Mitigation |
| Cross-engine (`cross-engine`) | yes: 3 files, 44,105 B | yes | no, File-backed instead of SQL-backed | no, File-backed instead of SQL-backed | yes: 2 artifacts, 43,245 B | yes: Benchmarks |
| StormML JSON (`stormml`) | yes: 2 JSON, 228,530 B | yes | no, File-backed instead of SQL-backed | no, File-backed instead of SQL-backed | yes: 2 artifacts, 228,530 B | yes: Workbench |
| StormML `dataset.npz` (listed in `files` of `ml-screening-dataset`) | yes: 971,895 B | yes | no, File-backed instead of SQL-backed | no, File-backed instead of SQL-backed | no, Stored but not exposed (only `<artifact_id>.json` is served) | no, Stored but not exposed |
| User jobs (rows) | — | — | yes: ≥ 12 public (total BLOCKED) | — | yes: 12 public jobs | yes: Library, Run page |
| User job metrics | — | — | yes: ≥ 12 rows | — | yes: 12/12 `/metrics` 200 | yes: Run page |
| User job result/scenario/log blobs | — | — | refs: ≥ 17 rows | yes for 7 jobs (10 keys, 1,275,175 B); **no for 5 jobs: Broken reference** | 7 × 200 (sha verified), 5 × 410 | yes / 410 recovery banner |
| Saved scenarios, private/owned jobs, profiles | — | — | BLOCKED | — | not visible to anonymous callers (by design) | signed-in only |
| Comparisons | — | — | yes: ≥ 1 (`4f5661ec`) | no, Intentionally not ingested (report JSONB lives in SQL; Markdown is rendered on request) | by id only; `GET /api/v1/comparisons` → 405. Listing: Stored but not exposed | `/compare?comparison=<id>` only |
| Ingestion runs, audit events, schema migrations | — | — | BLOCKED (expected) | — | no, Stored but not exposed (no client policies, no API route) | no, Stored but not exposed |

Column totals: repo `data/artifacts` = 65 files, 20,210,961 B (9 families; each `index.json`
is metadata). The API serves 55 artifacts, 19,204,570 B. All 55 report `available: true`.

## How to complete

Run this with an authorized, read-capable Supabase connection (Session pooler URI from Supabase →
Connect). Do not paste the URI into shell history or into this document:

```sh
cd services/api
read -rs DATABASE_URL && export DATABASE_URL   # postgresql://postgres.<ref>:…@aws-0-eu-central-1.pooler.supabase.com:5432/postgres?sslmode=require
uv run --locked python ../../scripts/inventory/production_inventory.py \
    --sections repo,api,db --out ../../var/inventory/production-inventory.json
unset DATABASE_URL
```

Instead of `DATABASE_URL`, the script also accepts `SUPABASE_DB_HOST/PORT/NAME/USER/PASSWORD`. It
writes `var/inventory/production-inventory.json` and a Markdown rendering (`.md`, git-ignored)
with: project ref, migrations, every table (rows, total/heap/index bytes, RLS), datasets/versions/
sources, ingestion runs, scenarios, jobs by status/outcome/mode/network/solver, failures,
metrics null-coverage and integrity, artifacts by kind/backend, buckets, objects by
prefix/mimetype/bytes, missing/orphan/size-mismatched objects, comparisons with their
reproducibility git SHA, audit events, policies, grants, the anon SELECT probe, table/index
stats, `pg_stat_statements` (if installed), the `SELECT 1` round trip, and EXPLAIN ANALYZE plus
client wall time for the 14 API queries above. Then replace every BLOCKED cell here with the
measured value.

## Schema / index recommendation

**No change recommended now.** The evidence is too thin to justify one. The public job table
holds 12 rows, so any plan is trivially fast. 0003 already added the newest-first, owner,
and partial FK indexes for the hot paths, and the API's single-row endpoints cost about 25–45 ms
above the network baseline. Re-evaluate after the `db` section runs: look for unused indexes
(`idx_scan = 0`) and for `seq_scan` on `simulation_jobs` with the list query. The grant
tightening under "RLS, policies, grants" item 1 is the only candidate, and it needs measured
grants first.
