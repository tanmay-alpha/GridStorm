# Backend architecture

The interface authority is [contracts.md §6](contracts.md#6-http-api--servicesapi-fastapi-base-path-apiv1).
`gridstorm_api.main:app` exports FastAPI with typed Pydantic response/error models. Routers cover
catalog/assets/GeoJSON/analytics, scenarios, jobs/results, comparisons/reports and precomputed
artifacts. Pagination uses `{items,total,limit,offset}`; errors use `{error:{code,message,details}}`.
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

ArtifactStore supports LocalFS and S3-compatible storage (including R2). Keys are immutable,
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
for Docker/Render, Postgres migration and artifact-storage settings. SQLite and local artifacts
on Render are ephemeral, and `/ready` reports `sqlite-ephemeral` honestly. `/health` is a cheap
liveness signal, not proof that a database, solver or catalog is ready.

Tests in `services/api/tests` exercise endpoints, JWT/owner isolation, lifecycle and recovery,
limits, integrity, comparisons, real ac-dc-meshed PyPSA solves, and real Postgres migrations/RLS.
