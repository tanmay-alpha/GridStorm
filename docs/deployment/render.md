# API on Render

The API is a Docker web service; the React app is deployed separately on
[Vercel](vercel.md). Repository configuration is in [`render.yaml`](../../render.yaml)
and [`services/api/Dockerfile`](../../services/api/Dockerfile).

## Service configuration

| Setting | Value |
|---|---|
| Name | `gridstorm-api` |
| URL | <https://gridstorm-api.onrender.com> |
| Runtime / plan / region | Docker / Free / Frankfurt |
| Branch / automatic deployments | `main` / on commit |
| Dockerfile | `./services/api/Dockerfile` |
| Docker build context | Repository root (`.`); **not** `services/api` |
| Health check | `/health` |

The URL and service configuration are recorded deployment settings, not a claim that the
current deployment has passed a live check. In Render, import the repository as a Blueprint
using `render.yaml`, or configure a Docker Web Service with the settings above. Do not create a
second service if the existing `gridstorm-api` service is already linked.

The image installs the API, PyPSA worker and analytics path dependencies from the API lockfile,
bakes in admitted network/artifact data, runs as a non-root user, and starts **one** uvicorn
process. Render supplies `PORT`; the image listens on `0.0.0.0:$PORT`.

## Environment

The Blueprint sets these explicitly; these are deployment overrides, not all API defaults:

| Variable | Blueprint value / purpose |
|---|---|
| `GRIDSTORM_EXECUTION_MODE` | `live`; `precomputed` disables simulation computation and requires an exact stored scenario match |
| `GRIDSTORM_MAX_CONCURRENT_JOBS` | `1` |
| `GRIDSTORM_LIVE_NETWORKS` | `ac-dc-meshed,pglib-case14-ieee,pglib-case118-ieee,pypsa-eur-be` (measured solver peaks ≤ 348 MiB); SciGRID-DE (≈ 550 MiB) only serves exact precomputed matches, else 422 `live_execution_unavailable` |
| `GRIDSTORM_JOB_TIMEOUT_S` | `180` wall-clock seconds |
| `GRIDSTORM_JOB_MEMORY_MB` | `400` per engine subprocess; **not** a guarantee that total service memory fits 512 MB |
| `GRIDSTORM_CORS_ORIGINS` | Explicit comma-separated frontend origins; update for your Vercel production/preview domains |
| `DATABASE_URL` | Secret; supply the Supabase session-pooler URL with `sslmode=require`, or leave unset for ephemeral SQLite |
| `GRIDSTORM_ARTIFACT_STORE` | `supabase` |
| `GRIDSTORM_SUPABASE_BUCKET` | `gridstorm-artifacts`; create it private, with no public policies |
| `SUPABASE_URL` | Required Supabase project URL; `sync: false` |
| `SUPABASE_SERVICE_ROLE_KEY` | Required server-only storage credential; `sync: false` |
| `GRIDSTORM_STORAGE_CHECK_TTL_S` | `300`; cached storage readiness TTL in seconds |
| `GRIDSTORM_SUPABASE_STORAGE_TIMEOUT_S` | `30`; storage request timeout in seconds |
| `SUPABASE_JWT_SECRET` | Optional server-side JWT verification secret |

Supply `DATABASE_URL` for persistent metadata and the storage settings above for persistent
payloads. Without `DATABASE_URL`, the image falls back to `/tmp/gridstorm/gridstorm.db`, which
is **not durable**. These are operator requirements, not a claim about the current live
environment. Follow [Supabase setup](supabase.md), and apply migrations before using Postgres,
or explicitly enable `GRIDSTORM_DB_AUTO_MIGRATE=true` after reviewing them.

The image sets `GRIDSTORM_DATA_DIR=/app/data`, `GRIDSTORM_STATE_DIR=/tmp/gridstorm` and
`GRIDSTORM_MIGRATIONS_DIR=/app/database/migrations`. Do not replace these with relative paths copied
from a local shell. More options and defaults are defined in
`services/api/src/gridstorm_api/config.py`.

The Blueprint selects Supabase Storage, but does not create the bucket or credentials. Create
the private `gridstorm-artifacts` bucket with no public policies, then supply `SUPABASE_URL`
and `SUPABASE_SERVICE_ROLE_KEY` securely on the API service. Never put the service-role key in
`VITE_*`, browser code, or the engine subprocess environment. Local artifacts remain supported
for development but are never durable on Render; database persistence alone does not save them.

## Local image commands

From the repository root, with Docker running:

```bash
docker build -f services/api/Dockerfile -t gridstorm-api .
docker run --rm -p 8000:8000 --name gridstorm-api gridstorm-api
```

This uses SQLite and live execution defaults from the image/API, not the Blueprint overrides.
The complete persistent local Postgres setup is described in [local development](local-development.md).

## Verification after deployment

Check `/health` for HTTP process liveness and `/ready` for database, artifact-store, solver and
dataset readiness. A healthy HTTP process is not evidence that simulations work. Inspect the readiness
body and Render logs, load `/api/v1/networks`, then run a small validated preset and inspect its
status, scientific outcome and solver termination separately. These are operator verification
steps, not checks claimed to have been run by this document.

Inspect `checks.storage.backend` and `checks.storage.durable`. Supabase reports `durable: true`
only after writing, reading back and deleting a probe under `_ready`; results are cached for
300 seconds by default, with a 30-second storage request timeout. A configured bucket alone
does not establish readiness. Missing result/report/artifact blobs return 410
`artifact_unavailable` with recovery advice; integrity failures return 500
`artifact_integrity_error`. Job `result_available` is cached.

Use the rate-limited `POST /api/v1/simulations/{id}/recompute` with the same access checks, or
`python -m gridstorm_api.jobs.recover JOB_ID [--force]` from `services/api` with the API
environment. Both rerun the stored specification as a **new** job, retaining old metadata,
recording `recomputed_from_job_id` and the old checksum in the initial stage event's
`lost_result_sha256`. Never reuse missing/corrupt artifacts or inaccessible private jobs.
When the original bytes still exist (e.g. a committed precomputed artifact in git history),
`python -m gridstorm_api.jobs.restore JOB_ID... --source FILE` re-uploads them only if their
sha256 equals the recorded checksum, keeping the original job; see
[backend: lost or corrupt artifacts](backend.md#lost-or-corrupt-artifacts).

## Free-tier limits

Render documents **0.1 CPU / 512 MB RAM**, spin-down after **15 minutes** without inbound traffic,
about **one minute** to wake, and an **ephemeral filesystem** lost on restart, redeploy or spin-down.
Free services cannot attach a persistent disk or scale beyond one instance. The workspace receives
750 free instance-hours per calendar month; bandwidth/build limits also apply. See
[Render's free-service documentation](https://render.com/docs/free) for current limits.

Consequences:

- Keep concurrency at one; the API and the engine share the memory budget. A 400 MB
  subprocess limit does not reserve memory for the parent process or prevent platform OOM kills.
- Small live jobs are possible but their completion is not guaranteed within free-tier limits.
- `precomputed` is the low-compute demo mode. Unsupported scenario hashes return 409 rather than
  pretending to run; all returned jobs identify their execution mode.
- AC N-1, advisor, Grid2Op and benchmark studies are generated offline in isolated environments and
  served as labeled artifacts; they do not execute on Render per browser request.
- Neither a local SQLite database nor locally generated results survive a free-service reset.
  Baked-in read-only datasets and artifacts return with the image.
