# Production data inventory (G32-02 → completed in GridStorm 3.3, G33-01)

**Status: COMPLETE (read-only), measured 2026-11-17 11:17 UTC.** One least-privilege migration
followed from the findings (`0004_client_role_least_privilege.sql`, § RLS and grants).

## Method

- Project: Supabase ref `tyyvdcournumpnfvplbh` (eu-central-1, session pooler), PostgreSQL 17.11.
  Identified from the `DATABASE_URL` configured on the GridStorm Render service
  (`srv-dbs8a30ae00c73cs4cog`, repo `tanmay-alpha/GridStorm`, branch `main`), read through the
  authorized Render API; the schema contents (12 GridStorm tables, `schema_migrations` with the three
  repo migrations and matching sha256) confirm it is the GridStorm database. No other project was
  touched; no credential value is written here or in the repo.
- Command (from `services/api`, credentials only in the process environment):
  `uv run --locked python ../../scripts/inventory/production_inventory.py --sections repo,api,db --out ../../var/inventory/production-inventory.json`
  (writes JSON + a full Markdown dump to the git-ignored `var/inventory/`).
- Every query ran inside `BEGIN READ ONLY … ROLLBACK` (`transaction_read_only = on` checked first).
  Client wall times include the ≈ 179 ms round trip from the measuring machine (median `SELECT 1`).

## Migrations

| File | Repo sha256 | Applied | Production sha256 |
|---|---|---|---|
| `0001_core_schema.sql` | `e2bb722c…` | 2026-11-14 23:38 UTC | identical |
| `0002_row_level_security.sql` | `6ef76be6…` | 2026-11-14 23:38 UTC | identical |
| `0003_job_indexes_and_client_grants.sql` | `2f82904e…` | 2026-11-15 00:34 UTC | identical |
| `0004_client_role_least_privilege.sql` | new in 3.3 | 2026-11-17 (after PR #15 CI 27/27) via `python -m gridstorm_api.db.migrate` | recorded in `schema_migrations` |

After 0004 on production: tables with any `anon` INSERT/UPDATE/DELETE privilege 12 → 0; `anon` and
`authenticated` lose SELECT on `simulation_jobs.worker_id` / `heartbeat_at` (a direct read as `anon`
fails with `InsufficientPrivilege`) and keep every other column (`select count(id)` → 14);
`authenticated` keeps its owner-scoped write grants; the default ACL for new `postgres`-owned tables
gives `anon` only `rm`. API unaffected: `/ready` database ok, job GET 200, `probe_production.py` 30
PASS lines, no failure.

## Tables, rows, size

All 12 public tables have RLS enabled (not forced; the API connects as the owner).

| Table | Rows | Total bytes |
|---|---:|---:|
| `simulation_jobs` | 14 | 335,872 |
| `comparison_reports` | 22 | 294,912 |
| `scenario_definitions` | 17 (15 presets + 2 public user scenarios) | 172,032 |
| `network_versions` | 10 (2 per network: pre/post 3.0 cost-basis manifests) | 122,880 |
| `simulation_metrics` | 14 | 114,688 |
| `audit_events` | 53 | 98,304 |
| `dataset_sources` | 10 | 98,304 |
| `simulation_artifacts` | 37 | 98,304 |
| `ingestion_runs` | 10 (all `succeeded`) | 65,536 |
| `network_datasets` | 5 | 32,768 |
| `profiles` | 0 (0 `auth.users`) | 32,768 |
| `schema_migrations` | 3 | 32,768 |

Database size 13,121,203 B (public schema 1.5 MB; the rest is Supabase system schemas).
Canonical network assets are file-backed by design (`data/networks/`, ADR 0003); their absence from
SQL is intentional, not a defect.

## Jobs, metrics, results

| Group | Jobs | Notes |
|---|---:|---|
| IEEE-14 live, solved (`reused = false`) | 7 | HiGHS; median solver 1.21 s, median job wall 42.5 s (queue + subprocess start + import) |
| IEEE-14 live, reused verified result | 2 | |
| SciGRID-DE precomputed | 5 | incl. observed-analogue job `5dbb2e94` (2026-11-17) |
| Not completed (queued / running / failed / cancelled / timeout) | 0 | |

- All 14 completed jobs have exactly one metrics row; 0 metrics on non-completed jobs; 0 job/metrics
  mismatches. `co2_emissions_t` is null on all 14 because no dataset carries CO₂ intensities (a data
  gap, labelled as such in the UI), every other headline metric is non-null.
- Artifact rows: 37 (14 scenario, 14 result, 9 log). 0 completed jobs without a result row, 0
  result-sha mismatches between job and artifact rows, 0 keys that are not content-addressed.

## Supabase Storage

- Bucket `gridstorm-artifacts`: **private**, 20 MiB file limit, MIME allow-list
  `application/json`, `text/markdown`, `text/plain`. No `storage.objects` policies for `anon` /
  `authenticated` (only the service role reads/writes, through the API).
- Objects: 14 under `sha256/` — 10 JSON (2,530,548 B) and 4 logs (6,900 B), 2026-11-15 → 2026-11-17.
- Reconciliation: 0 orphan objects (object without an artifact row), 0 size mismatches; 6 content
  keys are shared by several rows (deduplicated presets/results, expected).
- **Broken references: 8 artifact rows of 5 legacy jobs**, all `storage_backend = local` (written to
  Render's ephemeral disk before durable storage, issue #8): `2d47898b` (result + log), `0137980b`
  (result + log), `06b4f635` (result), `4104c5fc` (result + log), `25e3fb2a` (result). The API
  answers 410 `artifact_unavailable` for them; their metrics rows survive. `2d47898b` was recomputed
  as `458fddab`. Classification: Broken reference (bytes lost before POST-01; not recoverable).

## Comparisons

22 rows. 20 of them repeat two job pairs (`0137980b`/`06b4f635` ×13, `4104c5fc`/`25e3fb2a` ×7) and
were all created 2026-11-15 00:33–00:41 UTC by build `7c63cca`, i.e. before comparison reuse
(LA-09, deployed in `127db27`); none since. Their four input jobs are among the legacy jobs above,
so these reports stay readable (stored JSON) but cannot be rebuilt. The two later comparisons
(`ee5566d6`, `746d4e14`) reference durable results.

## RLS and grants

- Policies: 15 — 8 public/owner SELECT for `anon` + `authenticated`, 1 SELECT own profile, and
  owner-scoped INSERT/UPDATE/DELETE for `authenticated` (scenarios, comparisons delete, profiles).
  **No policy grants `anon` any write command.**
- Grants before 3.3: `anon` and `authenticated` held SELECT, INSERT, UPDATE, DELETE on 15 relations
  (Supabase defaults; 0003 already revoked TRUNCATE/TRIGGER/REFERENCES).
- `anon` SELECT probe (rows visible through PostgREST with the project's anon key): comparisons 22,
  scenarios 17, artifacts 37, jobs 14, metrics 14, networks 5, versions 10, sources 10; 0 for
  `audit_events`, `ingestion_runs`, `profiles`, `schema_migrations`, `storage.objects`,
  `storage.buckets`.
- Findings:
  1. **`simulation_jobs.worker_id` and `heartbeat_at` were client-readable.** `worker_id` encodes the
     Render service id, instance host name and pid (60–62 chars, 7 rows). The GridStorm API never
     returns these fields; only a direct PostgREST call with the anon key could. Low severity (no
     credential, no personal data), but unnecessary exposure of infrastructure identifiers.
  2. **Unused write grants for `anon`.** Writes were rejected by RLS alone.
  Fix: `0004_client_role_least_privilege.sql` revokes INSERT/UPDATE/DELETE from `anon` (incl.
  default privileges) and replaces the SELECT grant on `simulation_jobs` with a column grant that
  omits the two worker columns. Rollback statements are in the migration header. The API (table
  owner) is unaffected. Isolated test: `services/api/tests/test_postgres_migrations.py::test_client_roles_have_least_privilege`
  on `postgres:16` with the Supabase role stub.
- Only `public.set_updated_at()` is executable by `anon` (trigger function, not SECURITY DEFINER).

## Index use and query performance

Stats since 2026-11-11. Server execution of every API hot query is < 0.25 ms; the client wall time
is dominated by the network (≈ 179 ms per round trip).

| Query (API) | Plan | Server ms |
|---|---|---:|
| get job | Index Scan `pk_simulation_jobs` | 0.055 |
| list jobs page | Seq Scan + Sort (14 rows; planner prefers it at this size) | 0.099 |
| list jobs by network | Bitmap Index Scan `ix_simulation_jobs_network_id` | 0.206 |
| worker claim | Index Scan `ix_simulation_jobs_status_created_at` | 0.029 |
| reuse candidates | Index Scan `ix_simulation_jobs_network_version_id` | 0.169 |
| job metrics | Index Scan `pk_simulation_metrics` | 0.033 |
| comparison get | Index Scan `pk_comparison_reports` | 0.031 |

The most frequent statement is the worker's claim `UPDATE` (22,466 calls, mean 0.031 ms). Indexes
with 0 scans exist on tiny tables (`audit_events`, `dataset_sources`, `ingestion_runs`, …); at
these sizes the planner uses sequential scans, so the indexes are kept for growth. **No missing
index found; no index change recommended.**

## Free-tier quota

| Resource | Used | Free plan limit | Share |
|---|---:|---:|---:|
| Database (`pg_database_size`) | 13.1 MB | 500 MB | 2.6 % |
| Storage (`storage.objects` bytes) | 2.54 MB | 1 GB | 0.25 % |
| Largest single object | ≈ 1.24 MB | 50 MB per upload (bucket limit 20 MiB) | — |

## Coverage matrix

| Data family | Repo files | API image | Postgres | Supabase Storage | Exposed by API | UI |
|---|---|---|---|---|---|---|
| Networks ×5 (manifest, canonical, network file) | yes | yes | `network_datasets` 5, `network_versions` 10, `dataset_sources` 10; asset rows: Intentionally not ingested | no (File-backed instead of SQL-backed) | yes | Explorer, Studio, Data Observatory |
| StormSpec presets ×15 | yes | yes | `scenario_definitions` 15 presets | no | yes | Studio |
| Precomputed artifacts (PyPSA, pandapower, StormBench, …; 58 indexed) | yes | yes | no (File-backed instead of SQL-backed) | no | yes | research pages, Workbench |
| Data Observatory bundle (5 entries) | yes | yes | no (File-backed instead of SQL-backed; ADR 0003) | no | yes | `/data` |
| OPSD actual load / actual generation | no | no | no | no | no — Legally restricted | no |
| User jobs | — | — | 14 rows | 10 results + 4 logs | yes | Library, Run |
| Legacy results of 5 jobs | — | — | rows present | missing — Broken reference | 410 `artifact_unavailable` | disclosed unavailable state |
| Comparisons | — | — | 22 rows (JSON report stored in row) | no | yes | Compare |
| CO₂ emissions | — | — | null in 14/14 metrics — Not present in the source | — | null | "no CO₂ intensities" note |
| Ingestion runs, audit events, profiles | — | — | 10 / 53 / 0 rows | — | no — Stored but not exposed | no |

## Re-running

The script never writes. Re-run it with the commands above; if the shell holds Supabase
placeholders, it stops with an explicit `BLOCKED` message instead of guessing.
