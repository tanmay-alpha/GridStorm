# Backend deployment

## Local Python

Python 3.11 and uv are required. From `services/api`:

```sh
uv sync --locked
uv run uvicorn gridstorm_api.main:app --host 127.0.0.1 --port 8000
```

Optional environment settings are in `services/api/.env.example`. Copy it to `.env.local` and
use `uv run --env-file .env.local uvicorn gridstorm_api.main:app`; the application does not
implicitly load dotenv files. With no `DATABASE_URL`, SQLite is created under `var/` in the
checkout; local result artifacts go under `var/artifacts/`. `/docs` and `/openapi.json` describe
the HTTP interface. `/health` is liveness; `/ready` probes database connectivity, storage
writability, solver imports in a separate process, and catalog datasets.

## Docker (repository-root build context)

```sh
docker build -f services/api/Dockerfile -t gridstorm-api .
docker run --rm -p 8000:8000 gridstorm-api
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

The image is Python 3.11 slim, installs frozen uv dependencies, runs as uid/gid 10001, and binds
`0.0.0.0:$PORT` (default 8000). The build includes only API/core dependencies, migrations,
StormSpec presets, `data/networks`, and `data/artifacts`; no solver downloads occur at runtime.
Default state is `/tmp/gridstorm`, **not durable**. The healthcheck uses `/health`, not the
more expensive solver readiness probe. To persist local Docker state, mount a named volume at
`/state` and set `GRIDSTORM_STATE_DIR=/state` (the image seeds its ownership for the non-root user).

For Postgres and persistent local artifacts, from repository root:

```sh
docker compose up --build
# API: http://localhost:8000; Postgres: localhost:8055
# Stop without deleting the named data volumes:
docker compose down
```

Compose uses demo-only database credentials, bound to localhost; set `POSTGRES_PASSWORD` for
non-demo use. Its plain Postgres auth stub and automatic migrations are **local-only**.

## Render

`render.yaml` mirrors the existing `gridstorm-api` service (`srv-dbs8a30ae00c73cs4cog`),
<https://gridstorm-api.onrender.com>: free Docker, Frankfurt, main-branch auto-deploy,
`./services/api/Dockerfile`, context `.`, health path `/health`. Render injects `PORT`.
The blueprint sets live execution, one worker, a 180-second timeout, a 400-MB child-process-tree
RSS limit, and the two production frontend origins plus localhost. It contains no secrets.
Blank optional secret settings can remain unset until provisioning; do not insert dummy URLs.

`buildFilter` limits auto-deploys to commits touching image inputs (the `.dockerignore`
allow-list). The blueprint value only applies when the service is synced from `render.yaml`;
for the existing dashboard-created service, set the same paths under Settings → Build Filters.
Without it every push to `main` redeploys and, on SQLite, wipes all jobs (observed 2026-11-14:
jobs returned 404 seconds after creation while another workstream's commit was deploying).
Commits under `data/artifacts/` still redeploy because precomputed results are baked into the image.

Supabase is not provisioned automatically. Until `DATABASE_URL` is configured, the service uses
SQLite under `/tmp/gridstorm`; `/ready` explicitly returns `kind: sqlite-ephemeral`. Saved
scenarios, jobs, comparisons, and newly generated artifacts disappear on redeploy or instance
replacement. Committed catalog/preset/precomputed files survive because they are baked into the
image. This is a demo, not durable production persistence. Free Render services may cold-start.

For durable storage, provide a real Postgres connection URL and apply migrations (below), and
configure S3/R2 for artifacts. A Postgres database alone does not preserve local result files.
Set `GRIDSTORM_ARTIFACT_STORE=s3`, `GRIDSTORM_S3_BUCKET`, optional `GRIDSTORM_S3_ENDPOINT_URL`,
`GRIDSTORM_S3_REGION`, `GRIDSTORM_S3_PREFIX`, and boto3 credentials via secret environment
variables. Cloudflare R2 uses its S3-compatible endpoint. Never expose these in frontend envs.

## Postgres / Supabase schema and seed

Use a privileged backend connection URL, never an anonymous browser key. Plain `postgres://`
and `postgresql://` URLs are normalized to psycopg 3. From `services/api`, with `DATABASE_URL`
exported securely:

```sh
uv run python -m gridstorm_api.db.migrate
uv run python ../../database/seeds/seed_catalog.py
```

The catalog seed is idempotent and reads current catalog, canonical and manifest files; API
startup also performs this same synchronization and validates/seeds committed presets. For a
plain local Postgres only, add `--supabase-stub` to the migration command. Never enable the stub
on a real Supabase project. Automatic migrations are opt-in (`GRIDSTORM_DB_AUTO_MIGRATE=true`);
normal production operation expects a migrated schema. Migrations enable RLS with `auth.uid()`
owner checks. The privileged server connection bypasses RLS and the API independently enforces
visibility; never give that connection to a browser. See [backend architecture](../architecture/backend.md).

Live execution is restricted by `GRIDSTORM_LIVE_NETWORKS`, defaulting to `ac-dc-meshed`,
`pglib-case14-ieee`, and `pglib-case118-ieee`. SciGRID live presets exceed the free-tier memory
budget and are therefore not attempted. For an excluded network, an exact matching committed
simulation result is returned as `execution_mode: precomputed`; otherwise submission returns
422 `live_execution_unavailable`. List/detail network responses expose `live_execution`.
An explicitly empty allow-list disables all live networks. Expand it only on a larger host.

## Supabase runbook (psql via the pooler)

1. In Supabase → Connect, copy the **Session pooler** URI (IPv4, port 5432); the direct
   `db.<ref>.supabase.co` host is IPv6-only without Supabase's IPv4 add-on. Shape:
   `postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require`.
   Keep it out of shell history (e.g. `read -rs DB_URL; export DB_URL`).
2. From repository root, apply migrations in order, each file plus its bookkeeping row in one
   transaction. The rows use the same table and SHA-256 as `python -m gridstorm_api.db.migrate`,
   so either tool can be used later and already-applied files are skipped. Do **not** apply
   `database/dev/supabase_auth_stub.sql` on Supabase; `auth.uid()` and the roles already exist.

   ```sh
   psql "$DB_URL" -v ON_ERROR_STOP=1 -c "create table if not exists public.schema_migrations (version text primary key, sha256 text not null, applied_at timestamptz not null default now()); alter table public.schema_migrations enable row level security;"
   for f in database/migrations/*.sql; do
     v=$(basename "$f"); s=$(sha256sum "$f" | cut -d' ' -f1)
     if [ -n "$(psql "$DB_URL" -Atc "select 1 from public.schema_migrations where version = '$v'")" ]; then echo "skip $v"; continue; fi
     psql "$DB_URL" -v ON_ERROR_STOP=1 --single-transaction -f "$f" \
       -c "insert into public.schema_migrations (version, sha256) values ('$v', '$s')"
     echo "applied $v"
   done
   ```

3. Check: `psql "$DB_URL" -Atc "select version from public.schema_migrations order by 1"` lists
   `0001_core_schema.sql` and `0002_row_level_security.sql`; `select count(*) from pg_policies
   where schemaname = 'public'` returns 15; every `public` table has `relrowsecurity = true`.
4. Seed the catalog (optional; API startup performs the same sync):
   `cd services/api && DATABASE_URL="$DB_URL" uv run python ../../database/seeds/seed_catalog.py`.
5. On Render (service `srv-dbs8a30ae00c73cs4cog`) → Environment, set the secret `DATABASE_URL`
   to the pooler URI (session 5432, or transaction 6543: the engine disables server-side prepared
   statements, so pgbouncer transaction mode works). Leave `GRIDSTORM_DB_AUTO_MIGRATE` unset.
   Save and redeploy; `/ready` must then report `checks.database.kind: "postgres"` instead of
   `sqlite-ephemeral`. Set `SUPABASE_URL`/`SUPABASE_JWT_SECRET` too if user auth is enabled.

Verified locally on 2026-11-15 against `postgres:16` (with the auth stub applied first, as a
plain Postgres lacks Supabase's `auth` schema): first run `applied` both files, second run
`skip`ped both; 12/12 `public` tables had RLS enabled and 15 policies existed; afterwards
`python -m gridstorm_api.db.migrate` printed `applied 0 migration(s)` (checksums compatible) and
`seed_catalog.py` printed `seeded 4 network dataset(s)`. Not yet run against a real Supabase project.

## Operational limits

POST token buckets are per-IP, in-process: general requests refill 60/minute with burst 20;
simulation submission additionally refills 6/minute with burst 3. Limits return 429 and
`Retry-After`. Request bodies are limited to 262144 bytes by default (413 when exceeded).
Only trust forwarded client-IP headers behind a controlled ingress; the Render image is
configured for that proxy boundary. A public direct deployment should disable proxy trust.

Default Python settings allow 600 s / 2048 MB, whereas the Render blueprint and Compose use
180 s / 400 MB. The worker polls aggregate process-tree RSS roughly every 0.25 seconds (not a
kernel hard cap), kills over-limit jobs with `memory_limit`, and uses one BLAS/OpenMP thread.
Cancellation and timeout kill the child process tree. Startup recovery retries interrupted
jobs up to `GRIDSTORM_JOB_MAX_ATTEMPTS` (default 2 total attempts), then fails `worker_restart`.
Run one uvicorn process; do not multiply worker pools using `--workers`.

`GRIDSTORM_EXECUTION_MODE=precomputed` explicitly disables live solving and only accepts specs
whose exact hash has a committed simulation artifact; jobs and artifacts stay labelled
`execution_mode: precomputed`. Missing results return a typed conflict, never invented output.

## Live verification (https://gridstorm-api.onrender.com)

Run 2026-11-14 21:33–21:35 UTC against deployed commit `051deb9`, anonymous client, SQLite
ephemeral store (IDs below no longer exist after later redeploys):

| request | status | observed |
|---|---|---|
| `POST /api/v1/simulations {scenario_id: ac-dc-meshed-baseline, reuse: false}` | 202 | `cda379a2-…`, live; completed in 49 s wall (queue + load + solve); HiGHS optimal, objective 128,678.57 EUR, solve 1.395 s |
| `POST … {scenario_id: ac-dc-meshed-dc-link-outage}` | 202 | `7e487849-…`, live; queued behind the first (1 worker), completed 91 s after submission; objective 131,950.19 EUR, solve 1.407 s |
| `POST /simulations` (third job) then `POST /simulations/{id}/cancel` | 202, 200 | `status: cancelled`, `stage: queued`, error `cancelled` "cancelled before execution started" |
| second `POST …/cancel` on the same job | 409 | `job_not_cancellable` "job is already cancelled" |
| `POST /api/v1/comparisons {baseline_job_id, scenario_job_id}` | 201 | `9257ed4c-359c-4862-9001-a32f4b031981`, `gridstorm-comparison/1.0`, report SHA-256 `fed2f234…09a55eb` |
| `GET /api/v1/reports/9257ed4c-…?format=md` | 200 | `text/markdown; charset=utf-8`, 6,948 chars, `X-GridStorm-Report-SHA256` equal to the comparison's |
| `POST /simulations {scenario: <scigrid-de-wind-lull with wind ×0.25>}` | 422 | `live_execution_unavailable`, `live_networks: [ac-dc-meshed, pglib-case118-ieee, pglib-case14-ieee]` |

Comparison deltas (scenario − baseline, DC-link outage vs baseline): total system cost
+3,271.61 EUR (+2.54 %), CO2 +23.45 t (+0.11 %), max line loading 6.745 → 4.495 % (−33.4 %),
mean line loading −11.4 %; unserved energy, load shedding, curtailment and congested lines all 0
in both runs; generation by carrier unchanged (gas 3.115e4 MWh, wind 1,400 MWh). These are model
outputs on a toy network, not predictions.

Note: two earlier attempts in the same session lost their jobs (GET → 404 seconds after a 202)
because commits from other workstreams were redeploying the service; see `buildFilter` above.

## Validation commands

From `services/api`:

```sh
uvx ruff@0.14.0 check --fix . && uvx ruff@0.14.0 format .
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run pytest
```

The suite includes SQLite endpoint/auth/lifecycle/integrity/comparison tests, real PyPSA runs
on `ac-dc-meshed`, and SQL migrations/RLS/API checks on temporary `postgres:16`. The Postgres
tests skip with a reason if Docker is unavailable; the real-engine test skips only when its
package or committed inputs are absent. Container build/health validation is separate above.
