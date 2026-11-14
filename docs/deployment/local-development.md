# Local development

Run commands from the repository root unless a `cd` is shown. Shell examples use Bash
(Git Bash on Windows); environment-assignment syntax is not PowerShell syntax. Requirements:
Python 3.11, [uv](https://docs.astral.sh/uv/), Node.js 24 LTS with npm, and optionally Docker with
Compose v2. Python components are independent projects: **do not combine their environments**.
See the [compatibility evidence](../research/compatibility-matrix.md).

## API and web (SQLite, no Docker required)

First terminal:

```bash
cd services/api
uv sync --locked --python 3.11
uv run uvicorn gridstorm_api.main:app --host 127.0.0.1 --port 8000
```

The API resolves dataset/preset paths relative to the repository, so starting in `services/api`
is supported. Without `DATABASE_URL`, SQLite is created at `var/gridstorm.db` and generated
payloads at `var/artifacts/`. These are runtime state, not datasets. `data/networks/` contains
network inputs; `data/artifacts/` contains published offline results.

Second terminal, starting again at the repository root:

```bash
cd apps/web
npm ci
npm run dev
```

Open <http://localhost:5173>. The Vite server proxies `/api`, `/health` and `/ready` to
`http://127.0.0.1:8000`; its strict port is 5173. Override the backend target with
`GRIDSTORM_API_PROXY` when needed. Alternatively set `VITE_API_BASE_URL` in
`apps/web/.env.local`; Vite inlines it at build time. An explicit cross-origin URL requires a
matching `GRIDSTORM_CORS_ORIGINS` on the API.

The root `.env.example` is a reference template, **not automatically loaded by the API**:
`Settings.from_env()` reads the process environment. Export required variables in the launching
shell or use your process manager. Prefer absolute paths when overriding `GRIDSTORM_DATA_DIR`,
`GRIDSTORM_STATE_DIR` or `GRIDSTORM_ARTIFACT_DIR` from another working directory. Keep secrets out
of source control and out of `VITE_*` variables. For S3 configuration use the actual
`GRIDSTORM_S3_*` settings in `services/api/src/gridstorm_api/config.py`, not unprefixed aliases.

## Docker Compose (local Postgres + API)

The root [`docker-compose.yml`](../../docker-compose.yml) builds the same
[`services/api/Dockerfile`](../../services/api/Dockerfile) used by Render, with repository-root
build context:

```bash
docker compose up --build
```

- API: <http://localhost:8000>; web development still runs separately on :5173.
- Postgres 16: `127.0.0.1:8055`, database/user `gridstorm`.
- The default password `gridstorm-local-only` is **local-demo-only**. Set `POSTGRES_PASSWORD`
  before the first start to change it. Changing it later does not change an existing database's
  password automatically.
- `postgres-data` stores Postgres data; `api-state` stores generated payloads under `/state`.
- The API waits for the Postgres health check and enables migrations plus the **local-only**
  Supabase auth stub. Never enable `GRIDSTORM_DB_SUPABASE_STUB` on a real Supabase project.
- Live jobs are limited to one concurrently, 180 seconds and 400 MB per subprocess. The API and
  other processes need additional memory.

Stop without removing named volumes:

```bash
docker compose down
```

Do not use `down -v` unless you deliberately want to delete the local database and generated
state. For external Supabase, follow [the database guide](supabase.md) instead of applying the
local stub.

## Per-component uv setup

Each row is an existing directory with `pyproject.toml` and `uv.lock`. From the repository root,
use `uv sync --project PATH --locked --python 3.11`, substituting a listed path. uv creates that
component's own `.venv`; running `uv sync` inside that directory is equivalent.

| Component | PATH | Role |
|---|---|---|
| API | `services/api` | FastAPI, job orchestration, PyPSA path dependency |
| Analytics | `services/analytics` | Network analytics |
| PyPSA | `workers/pypsa` | Linear dispatch / simulations |
| pandapower | `workers/pandapower` | AC studies |
| Advisor | `workers/advisor` | Deterministic remedial-action evaluation |
| Grid2Op | `workers/grid2op` | Sequential-operation experiments |
| Distribution | `workers/distribution` | Distribution-network studies |
| StormSpec | `packages/stormspec` | Scenario schemas, validation and hashes |
| Canonical grid | `packages/canonical-grid` | Engine-independent network/manifest schemas |
| StormBench | `packages/stormbench` | Contingency-screening benchmark |
| StormRisk | `packages/stormrisk` | Monte Carlo risk estimation |
| StormML | `packages/stormml` | Screening research |
| Network import | `pipelines/network-import` | Dataset import/validation |
| Observed analogues | `pipelines/observed` | Observed-data scenario pipeline |
| Integration tests | `tests/integration` | API integration checks |

For example:

```bash
uv sync --project workers/pypsa --locked --python 3.11
uv sync --project workers/pandapower --locked --python 3.11
uv sync --project workers/grid2op --locked --python 3.11
```

PyPSA uses pandas 3; pandapower/Grid2Op use pandas 2. The independent PyPSA-Eur workflow is
**not** another uv component: see `pipelines/pypsa-eur/README.md` and its `build.sh` for the
separate upstream/container environment. Do not install it into the API environment.

Offline artifact entrypoints present in this checkout include:

- `workers/pypsa/scripts/precompute_presets.py`
- `workers/advisor/scripts/build_artifacts.py`
- `workers/grid2op/scripts/run_experiments.py`
- `workers/distribution/scripts/run_studies.py`
- `packages/stormbench/scripts/generate_artifacts.py`
- `packages/stormrisk/scripts/run_study.py`
- `pipelines/observed/scripts/run_analogues.py`

Read each entrypoint's arguments before running; studies may be expensive or require downloads.
They are not automatically recomputed when a browser opens a research page.

## Execution modes and diagnostics

Set `GRIDSTORM_EXECUTION_MODE=precomputed` in the API process environment for stored simulation
results only. An exact scenario-hash match is required; an unmatched scenario returns 409.
If a payload hash is declared, a mismatch is rejected with 503; a missing hash is not evidence
of verified integrity. Default `live` queues a PyPSA subprocess. Both modes are labeled in jobs
and the UI; the research pages read offline artifacts in either mode.

`/health` is liveness; `/ready` reports dependency readiness. Examine its checks rather than
assuming that HTTP liveness means the database or solver works. For a run, distinguish
infrastructure status from scientific outcome and solver termination (see [user guide](../user-guide.md)).

The existing frontend scripts are `npm run typecheck`, `npm run lint`, `npm test`,
`npm run build`, and `npm run e2e` (from `apps/web`). `npm run preview` serves the built app on
4173 and also has the local API proxy. Python checks and the component test runner are documented
in [CI](ci.md); cross-engine verification has its own harness at `tests/cross_engine/run_all.py`.
These are available commands, not a claim that they passed on your machine.
