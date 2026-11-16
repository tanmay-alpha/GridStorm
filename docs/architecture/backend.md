# Backend architecture

The interface authority is [contracts.md §6](contracts.md#6-http-api--servicesapi-fastapi-base-path-apiv1).
`gridstorm_api.main:app` exports FastAPI with typed Pydantic response/error models. Routers cover
catalog/assets/GeoJSON/analytics, scenarios, jobs/results, comparisons/reports, precomputed
artifacts and the Data Observatory catalog. Pagination uses `{items,total,limit,offset}`; errors use `{error:{code,message,details}}`.
OpenAPI is available at `/openapi.json`, Swagger UI at `/docs`.

## Reference data and analytics

`NetworkCatalog` lazily caches `data/networks/catalog.json` entries, canonical data and manifests;
filesystem paths must remain inside the dataset root. Canonical asset rows are not copied into
a database `network_assets` table: that unused table is intentionally absent. Dataset versions
retain canonical/manifest hashes, network.nc hash and manifest. Dataset source metadata and
ingestion runs retain lineage. Startup idempotently synchronizes these and validates/seeds
StormSpec presets. A standalone catalog seed is in `database/seeds/seed_catalog.py`.

GeoJSON identifies assets with both `properties.component` and `properties.id`; a line and
transformer may share an id. Schematic coordinates are labelled `coordinate_kind: schematic`
and are not geographic longitude/latitude. Analytics are precomputed with `gridstorm_analytics.compute`
by `services/analytics/scripts/precompute_analytics.py` into `data/networks/<id>/analytics/`
(`<kind>.json` plus `index.json` with the `network.nc` sha256, per-file sha256 and source versions).
The API serves those files and never imports PyPSA (it cost ~300 MB RSS, see
`docs/benchmarks/api-memory.md`). Carrier/country filters are derived exactly from the unfiltered
rows, otherwise 422 `analytics_filter_not_precomputed`; a missing or stale index is a 503.

## Data Observatory catalog (`/api/v1/data`)

`gridstorm_api.observatory.DataObservatory` serves one research-data catalog merged at runtime from
three file-backed sources, without copying payloads ([ADR 0003](../decisions/0003-file-backed-data-observatory.md)):

1. the curated bundle `data/observatory/` (`catalog.json`, `series/<id>.csv`, `manifest.json`),
   produced by the licence-gated publication pipeline and baked into the image like `data/networks/`;
2. one `network_model` entry per network of the `NetworkCatalog` (id `network-<network_id>`; manifest
   licence, source, coverage; `spatial.kind = network`, no coordinates are invented; region only when
   grounded — one bus country, the manifest coverage, or `benchmark` for schematic cases without
   countries; `use_in_scenario` → `/studio?network=<id>` when the network runs live or has valid presets);
3. one `precomputed_experiment` entry per Research Workbench study group of the artifact index (id
   `study-<study id>`, linking to `/benchmarks`, `/contingency`, `/operations`, `/workbench` or, for the
   observed-analogue presets, Crisis Studio).

| Route | Purpose |
|---|---|
| `GET /api/v1/data/catalog` | `Page` of summaries (no `description`, `transformations`, `quality.checks`) with `category`, `provenance`, `region` (code), `source` (name) and `q` filters; `facets` over the whole catalog; `bundle` load/verification status |
| `GET /api/v1/data/catalog/{id}` | Full entry; 404 `not_found` |
| `GET /api/v1/data/catalog/{id}/series` | Bounded series: `start`/`end` (UTC, end exclusive; default = first documented window, else the last 31 days), > 3 years → 422 `range_too_large`; `resolution=auto` picks the finest of raw/PT3H/P1D/P7D with ≤ `max_points` (default 1500, max 2000); raw or a fixed bucket over the limit → 422 `range_too_large`; 409 `not_a_series_dataset`; 422 `unknown_series`; 503 `dataset_unverified` |
| `GET /api/v1/data/catalog/{id}/export` | Raw CSV attachment of the same window with `#` source/licence/attribution/sha256 header; 403 `export_not_permitted` when the licence does not permit redistribution |

Buckets are UTC-aligned (PT3H at 00/03/…/21 UTC, P1D at 00:00 UTC, P7D from Monday 00:00 UTC) and
labelled by their start. A raw slot or bucket without an observed value is `null`, never 0; absent
timestamps are not interpolated. Catalog `temporal.end_utc` and `windows[].end_utc` name the last
covered timestamp. Responses use the shared caching helpers with `Cache-Control: public,
max-age=300` and a strong body-hash `ETag` (the body embeds bundle version and file sha256), so a
redeployed bundle changes every tag.

The bundle is loaded lazily once per process under a lock. Every file listed in `manifest.json`
(`files[].path/sha256/bytes`) is hashed; an unverifiable `catalog.json` or manifest drops the whole
bundle (`bundle.status = error`), a mismatching series file marks only that dataset (`quality.checks`
`checksum: fail`, series/export 503). Entries are validated against the `DatasetEntry` schema; a
declared `use_in_scenario.available = true` is kept only when its network and `preset_id` exist in
this deployment, otherwise it is downgraded with a quality warning. CSVs are parsed into `array`
columns (8 bytes per value, NaN = missing): the 2.5 MB 3.2 bundle costs ≈ 3.4 MiB RSS, the merged
catalog ≈ 2 MiB more. A missing `data/observatory/` leaves network and study entries available and
does not affect `/ready`.

## Persistence and ownership

SQLAlchemy 2 models mirror `database/migrations/0001_core_schema.sql`; PostgreSQL RLS policies
are in `0002_row_level_security.sql`. SQLite uses the same ORM metadata with foreign keys,
WAL and a busy timeout. PostgreSQL uses psycopg 3 and disables prepared statements for Supabase
transaction-pooler compatibility. Migration versions and content hashes are recorded under an
advisory transaction lock. Local plain Postgres can install `database/dev/supabase_auth_stub.sql`;
this must never run on Supabase.

Tables: profiles, network_datasets, network_versions, scenario_definitions, simulation_jobs,
simulation_metrics, simulation_artifacts, comparison_reports, dataset_sources, ingestion_runs,
audit_events. Primary/foreign keys, timestamps, constraints and indexes are represented in both
ORM and SQL. Asset data remains in canonical files, not a duplicate database schema.

The API uses an optional Supabase bearer JWT verifier: HS256 with `SUPABASE_JWT_SECRET`, or
asymmetric JWKS at `SUPABASE_URL/auth/v1/.well-known/jwks.json`. Expiry, UUID subject, signature
and audience (`authenticated` by default) are checked. Invalid/expired supplied credentials
return 401, never anonymous fallback. Tokens are not logged. With no credentials, public data
and demo submission remain available; anonymous saved scenarios are readable by id but unlisted
(`listed: false`, never returned by `GET /scenarios`), and anonymous jobs
are cancellable by anyone. Authenticated records default to private. Reads enforce public-or-
owner visibility and modifications enforce ownership; private misses return 404. RLS mirrors
ownership for direct database clients; the privileged backend connection bypasses RLS, so API
query checks remain necessary. Never expose backend database credentials to clients.

## Execution lifecycle

Submission validates StormSpec against the canonical network and engine capabilities before
persisting a job. Workers default to concurrency 1. PostgreSQL claims rows with `FOR UPDATE
SKIP LOCKED`; SQLite claims with an atomic update/returning operation. Jobs keep hashes,
execution mode, scientific outcome, solver summary, stages with timestamps, heartbeat,
attempts and typed infrastructure errors. There is no fabricated percentage progress.

Each live job invokes `python -m gridstorm_pypsa run` in a temporary directory, receives
`STAGE <name>` lines, and reads the real result JSON. Command templates can override the engine
for tests without shell execution. The worker enforces wall timeout and a psutil process-tree
RSS watchdog (roughly 0.25-second sampling), and kills descendants on cancellation/limit.
It does not use RLIMIT_AS because scientific libraries reserve large virtual address spaces.
Child BLAS/OpenMP thread counts are fixed to 1. Result scenario hashes must match the queued
spec. Temporary directories are removed, bounded log tails and result artifacts are retained.

Interrupted running jobs are recovered at startup (SQLite single instance), or when their
heartbeat is stale (PostgreSQL); retry is bounded by `GRIDSTORM_JOB_MAX_ATTEMPTS` (2 total by
default). Exhaustion fails with `worker_restart`. Cancellation requests survive in the DB.
Completed feasible/infeasible results can be reused by exact scenario hash and dataset version,
with `reused: true`. Infrastructure status and scientific outcome are separate: infeasible is
a scientific result, not a server crash. Precomputed mode only resolves exact committed hashes
and always identifies itself explicitly.

## Artifacts and reproducibility

ArtifactStore supports LocalFS, S3-compatible storage (including R2) and Supabase Storage (private
bucket, server-side service-role credential; the production backend since `dd185d1`). Keys are immutable,
content-addressed `sha256/<digest>.json` (logs use `.txt`), recorded with sha256, size and content
type. Reads verify expected hashes. Precomputed files additionally verify their canonical
payload hash. No missing or corrupt artifact is replaced by synthetic data.

Comparisons require completed jobs on the same network and retain metric/per-carrier deltas
and maximum-over-time branch loading deltas, keyed by component and id. JSON and Markdown
reports include scenario specs/hashes, dataset hashes, engine and solver metadata, assumptions
and result hashes. Unweighted deterministic unserved energy is never described as EENS.

## Deployment boundary

One uvicorn process owns an in-process worker pool and rate-limit buckets. This is intentionally
a small demo service, not a distributed durable queue. Use the [deployment guide](../deployment/backend.md)
for Docker/Render, Postgres migration and artifact-storage settings. Production uses Supabase
Postgres for metadata and the private Supabase Storage bucket `gridstorm-artifacts` for result
payloads (`/ready` → `storage.backend: supabase`, `durable: true`). SQLite and local artifacts
remain available for development but are ephemeral on Render, and `/ready` reports
`sqlite-ephemeral` / `durable: false` honestly in that configuration. `/health` is a cheap
liveness signal, not proof that a database, solver or catalog is ready.

Tests in `services/api/tests` exercise endpoints, JWT/owner isolation, lifecycle and recovery,
limits, integrity, comparisons, real ac-dc-meshed PyPSA solves, and real Postgres migrations/RLS.
