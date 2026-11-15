# Supabase (Postgres + private artifact storage + optional auth)

GridStorm uses Postgres for metadata, jobs, metrics, scenarios, comparisons and audit events,
and Supabase Storage for durable generated payloads. Provisioning instructions below are not
evidence of a verified live configuration or deployment. A database alone does not preserve
artifact files. Without `DATABASE_URL`, the API uses SQLite at
`<GRIDSTORM_STATE_DIR>/gridstorm.db` (default `var/gridstorm.db` from the repository root;
`/tmp/gridstorm/gridstorm.db` in Docker). Render's local filesystem is ephemeral; neither
SQLite nor local result files are durable there. Free plans are not a capacity guarantee.

## 1. Create the project

Either:

- **Via Vercel Marketplace:** in the Vercel dashboard, *Storage / Marketplace → Supabase → Install*,
  choose the free plan and connect it to the `gridstorm` project. Vercel provisions a Supabase
  project and injects its connection variables into the Vercel project. Those variables are for
  reference only — the web app does not read them; copy the pooler URL into the **API** service
  (Render) yourself.
- **Directly:** create a free project at <https://supabase.com/dashboard>.

## 2. Connection string

Supabase dashboard → *Connect* → copy the **pooler** connection string (Supavisor; IPv4-reachable
from Render) and append `sslmode=require`:

```
postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require
```

Use the session-mode pooler (port 5432) for migrations. Set this as `DATABASE_URL` on the API
(`services/api/src/gridstorm_api/config.py`; template in `.env.example`). Never commit it.

## 3. Apply migrations

Migrations live in `database/migrations/` and are applied in lexical order:

| File | Content |
|---|---|
| `0001_core_schema.sql` | tables (profiles, network datasets/versions/sources, ingestion runs, scenario definitions, simulation jobs/metrics/artifacts, comparison reports, audit events), `updated_at` triggers |
| `0002_row_level_security.sql` | enables RLS on every table + policies |

**Option A — the API's migrator** (records each file with its SHA-256 in
`public.schema_migrations`, never re-applies, takes an advisory lock):

```bash
cd services/api
uv sync --locked --python 3.11
DATABASE_URL='postgresql://...?sslmode=require' uv run python -m gridstorm_api.db.migrate
```

The API can also apply them on startup with `GRIDSTORM_DB_AUTO_MIGRATE=true`.

**Option B — psql:**

Run the following from the repository root (a separate shell from Option A). Substitute your
actual session-pooler URL; the example is not a working credential.

```bash
export DATABASE_URL='postgresql://...?sslmode=require'
for f in database/migrations/*.sql; do
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f "$f"
done
```

Option B does not write `schema_migrations`; do not mix A and B on the same database (the
migrator would try to re-apply files). The SQL editor in the Supabase dashboard works the same as
option B.

`database/dev/supabase_auth_stub.sql` (`--supabase-stub`) recreates Supabase's `auth` schema and
roles for **plain local Postgres only**. Never apply it to a real Supabase project.

## 4. Row Level Security

`0002_row_level_security.sql` enables RLS on every table. Rules:

- datasets / versions / sources: public read when the dataset is public;
- scenario definitions, simulation jobs, comparison reports: readable when `visibility = 'public'`
  or `owner_id = auth.uid()`; owners may update/delete their own scenarios and comparisons;
  clients cannot create jobs — only the API does;
- simulation metrics / artifacts: readable when the parent job is readable;
- profiles: a user reads/updates only their own row;
- ingestion runs, audit events, schema migrations: no client access (no policies).

The API connects as the table owner (`postgres`) via `DATABASE_URL`, which bypasses RLS; it
enforces the same rules in its own queries. RLS protects the data from anyone using the public
anon/authenticated keys directly against Supabase's REST endpoint.

## 5. Keys and auth

| Secret | Where it may live |
|---|---|
| `DATABASE_URL` (contains the DB password) | API server only (Render env var) |
| JWT secret (`SUPABASE_JWT_SECRET`) | API server only |
| `SUPABASE_SERVICE_ROLE_KEY` | API server only; required for private artifact storage. Never in the browser, `VITE_*`, engine subprocess environment, or source control. |
| anon key | public by design (protected by RLS) |

User authentication is optional. Anonymous requests can read public data and run demo jobs. When a
request carries `Authorization: Bearer <jwt>`, the API verifies it with `SUPABASE_JWT_SECRET`
(HS256) or the project's JWKS at `SUPABASE_URL/auth/v1/.well-known/jwks.json`; the audience must
equal `SUPABASE_JWT_AUDIENCE` (default `authenticated`). Invalid tokens get a 401 response and are
never treated as anonymous (`services/api/src/gridstorm_api/auth.py`). Setting either
`SUPABASE_URL` or `SUPABASE_JWT_SECRET` enables auth.

## Private artifact storage

In Supabase dashboard → Storage, create a bucket named **`gridstorm-artifacts`**. Keep it
**PRIVATE** and do not add public read/write policies. Clients retrieve authorized artifacts
through the API, not a public bucket URL. Configure the API server with exactly:

```text
GRIDSTORM_ARTIFACT_STORE=supabase
GRIDSTORM_SUPABASE_BUCKET=gridstorm-artifacts
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<server-only service-role key>
GRIDSTORM_STORAGE_CHECK_TTL_S=300
GRIDSTORM_SUPABASE_STORAGE_TIMEOUT_S=30
```

`render.yaml` declares `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` with `sync: false`;
operators must supply them securely. Keep `DATABASE_URL` configured for metadata persistence.
The default `GRIDSTORM_ARTIFACT_STORE=local` remains useful in development, never as durable
storage on Render. The key is for the API process only, not the engine subprocess.

After deployment, inspect `/ready`: `checks.storage.backend` identifies the backend, and
Supabase may report `checks.storage.durable: true` only after a verified write/read/delete
round trip under `_ready`. Merely setting the environment or creating a bucket is not enough.
Storage check results are cached for 300 seconds by default; requests time out after 30 seconds.
These are operator checks to perform, not observed results.

### Artifact loss and recovery

Job metadata is retained if a payload disappears. Job `result_available` is cached rather than
a fresh object lookup on every response. A missing result/report/artifact blob returns 410
`artifact_unavailable` with recovery advice; an integrity/checksum failure returns 500
`artifact_integrity_error`. Neither case permits reuse of the missing/corrupt result, and
private jobs invisible to the caller must never be reused.

Use `POST /api/v1/simulations/{id}/recompute` (same access checks and submission rate limits)
or, from `services/api` with the API environment:

```sh
python -m gridstorm_api.jobs.recover JOB_ID
python -m gridstorm_api.jobs.recover JOB_ID --force
```

Recovery reruns the stored specification as a **new** job, retaining the old metadata.
`--force` explicitly requests recomputation even when a result is available. The new job has
`recomputed_from_job_id`; its initial stage event includes the old checksum as
`lost_result_sha256`. Follow the new job and use its completed result to rebuild reports.

## 6. Free-plan notes

Supabase free projects have limited database size and are paused after a period of inactivity.
Check the current terms at <https://supabase.com/pricing>. A paused project makes `/ready` report
the database check as failing until you restore it from the dashboard.
