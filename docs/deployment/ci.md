# Continuous integration

Workflows live in `.github/workflows/`. All Python components are independent uv projects
(`pyproject.toml` + `uv.lock`, Python 3.11); CI never shares an environment between them.

## `ci.yml` — every push to `main`, every PR, manual

| Job | What it does | Blocking? |
|-----|--------------|-----------|
| `discover` | Lists every `packages/*`, `workers/*`, `services/*`, `pipelines/*`, `tests/*` directory that has a `uv.lock`; feeds the matrix. New components join CI automatically once they commit a lockfile. | yes |
| `python` (matrix) | `uv sync --locked`; `ruff check` + `ruff format --check` (ruff 0.14.0, component's own `[tool.ruff]` config); `pytest -m "not slow and not network and not docker"` (exit code 5 = no tests collected → warning, not failure); `pip-audit` on the exported lock. | yes, except pip-audit (warning) |
| `scripts` | ruff + shellcheck on `scripts/`, self-test of `scripts/compare_artifacts.py`. | yes |
| `web` | `apps/web`: `npm ci`, `lint`, `typecheck`, `test` (vitest), `build`; `npm audit --omit=dev` (warning only). | yes, except audit |
| `e2e` | Only if `apps/web/playwright.config.*` and `*.spec.ts`/`*.e2e.ts` exist: starts the API (`uvicorn gridstorm_api.main:app` on :8000), builds the web app with `VITE_API_BASE_URL=http://127.0.0.1:8000`, serves it with `vite preview` (:4173), runs `npm run e2e`. | not on PRs (`continue-on-error`) |
| `api-container` | Builds `services/api/Dockerfile` (context = repo root), runs it with `PORT=8000`, requires `/health` and `/api/v1/networks` to return 2xx and prints `/ready` (which may honestly report a missing database). Runs `tests/integration` against the container (informational). Trivy scan (CRITICAL/HIGH, unfixed ignored), report-only; SARIF uploaded to code scanning on non-PR runs. | build + smoke yes; Trivy/integration no |
| `secrets` | gitleaks over full history (`gitleaks/gitleaks-action@v2`, free for personal repos). | yes |

Test markers (registered by each component's owner): `slow` (> ~30 s), `network` (downloads
data), `docker` (starts containers). Components may define more (e.g. services/api `postgres`,
`e2e`); unmarked tests always run in CI, so anything needing network/Docker must be marked.

## `scientific.yml` — weekly (Mon 04:17 UTC) + manual

- `regenerate`: `scripts/regenerate_reference.sh` runs each engine's generator with
  `--out-dir DIR` (pypsa: `workers/pypsa/scripts/precompute_presets.py`; pandapower:
  `workers/pandapower/scripts/run_studies.py --cases pglib-case14-ieee`; stormbench:
  `packages/stormbench/scripts/generate_artifacts.py --cases case14_ieee,case30_ieee`) and compares
  the output against the committed `data/artifacts/<engine>/` with `scripts/compare_artifacts.py`
  (subset runs use `--allow-missing --exclude index.json`; runtime keys `*_s`, memory, hashes
  ignored per engine). Engines without a generator or committed reference are reported
  `NOT-CONFIGURED` (warning), never counted as matching. Regenerated files are uploaded as a
  workflow artifact for inspection.
- `full-tests` (schedule, or manual with `full_tests: true`): `scripts/test_all.sh --all`
  including slow/network tests; logs uploaded.

Comparison rules (`compare_artifacts.py`): numeric leaves must satisfy
`|a-b| <= max(abs_tol, rel_tol*max(|a|,|b|))`; strings/bools/null exact; structure exact
(missing keys and list-length changes fail). Volatile keys (`created_at`, `platform`,
`git_sha`, durations, …; see `DEFAULT_IGNORE`) plus `--ignore KEY` / `--ignore-suffix SUF` are
skipped anywhere in the tree; `--exclude NAME` skips reference files by name. Exit 0 match /
1 mismatch / 2 usage error.

## Dependabot

`.github/dependabot.yml`: uv (every project dir listed explicitly — add new components when they
commit a `uv.lock`; weekly, minor/patch grouped; PyPSA, pandapower, Grid2Op, linopy, highspy
minor/major bumps ignored — bump by hand and re-run `scientific.yml`), npm (`apps/web`), GitHub
Actions, Docker (`services/api`).

## Running locally

```bash
scripts/test_all.sh                 # every component, CI marker set, summary table
scripts/test_all.sh --all           # include slow/network/docker tests
scripts/test_all.sh --no-sync workers/pypsa packages/stormspec
scripts/regenerate_reference.sh /tmp/regen pandapower
python scripts/compare_artifacts.py data/artifacts/pypsa /tmp/regen/pypsa --rel-tol 1e-4
uvx ruff@0.14.0 check <component> && uvx ruff@0.14.0 format --check <component>
uvx pre-commit run --all-files      # ruff, yaml/json checks, gitleaks
docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest   # workflow lint
```

On Windows run the scripts from Git Bash/MSYS (plain `bash` may resolve to WSL). Per-component
logs from `test_all.sh` go to `.test-logs/`.

The root `ruff.toml` is the shared baseline (line length 100, py311, `E,F,W,I,B,UP,SIM`); ruff uses
the nearest config, so components with their own `[tool.ruff]` table keep theirs.
