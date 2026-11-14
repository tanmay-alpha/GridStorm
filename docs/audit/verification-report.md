# GridStorm independent verification report

Verifier: Agent F (independent of every component owner). Defects with reproduction commands are in
[`issues.md`](issues.md). Black-box API tests are in [`tests/integration/`](../../tests/integration/).

Verdicts:
* **VERIFIED**: the component's claims were reproduced with independent code or re-runs.
* **ISSUES**: open S1/S2 defects (see `issues.md`).
* **NOT VERIFIABLE**: the component has not landed, or it cannot run yet.

All commands ran on Windows 10 (x64), Python 3.11 via `uv`, `OMP/OPENBLAS_NUM_THREADS=1`.

## Round log

| Round | Time (IST) | Repo HEAD | Scope |
|---|---|---|---|
| 1 | 2026-11-14 ~21:00 | `ec541b2` | contracts read, stormspec/API code review, integration test scaffold, secret scan |
| 2 | 2026-11-14 21:33–21:50 | `1e9282a` | test suites, independent physics re-solve, LODF check, Grid2Op re-run, research references |

## Per-component verdicts

| Component | Verdict | Evidence (summary) |
|---|---|---|
| `packages/stormspec` | ISSUES (VER-003) | 29/30 tests pass; the only failure is missing presets. Independent hash recompute matches: name, description, and key order are excluded; omitted and explicit defaults hash equal. Partial-window line outage is rejected for PyPSA. |
| `packages/canonical-grid` | VERIFIED | `uv run pytest -q` → 16 passed, 1 skipped. Model fields match contract §2. |
| `packages/stormrisk` | VERIFIED (after VER-001 fix) | 28 passed. The VER-001 probe re-run is correct. Estimators reviewed against the stated formulas: frequency-weighted mean, unbiased variance, CLT CI, Bernoulli SE for LOLP. |
| `packages/stormbench` | VERIFIED (DC core); results pending | Independent dense per-outage DC re-solve vs `f + LODF·f`: max error 6.8e-13 MW (case14), 6.1e-12 MW (case118), 1.5e-9 MW (case300). Islanding classification matches a rank test (1 / 9 / 89 bridges, 0 mismatches). Base flows match `pp.rundcpp` to 1e-12 MW (case14/118). `benchmarks/stormbench/results/` is still empty. |
| `workers/pypsa` | ISSUES (VER-002 S1, VER-004, VER-006) | An independent plain-PyPSA re-solve of a 4-event stress scenario reproduces the objective (28 477 328.81 EUR) and unserved energy (2 826.8713 MWh) exactly. Shed series, balance residual, generator bounds, and windowed outage all check out. Curtailment is wrong (VER-002). No tests. |
| `workers/grid2op` | VERIFIED | 20 tests pass (146 s), including a fresh-environment same-seed trace-hash test. A committed artifact `case14-sandbox-c1-outage-1-3-3-reco-powerline` was re-run from its recorded parameters: trace_sha256 `1b5fdde6…` is identical, KPIs are identical, and payload_sha256 recomputes. |
| `workers/advisor` | pending (VER-005) | Code review only so far. |
| `workers/pandapower` | NOT VERIFIABLE (in progress) | No tests, no N-1 artifacts yet. |
| `workers/distribution` | pending | |
| `services/analytics` | pending | MIT attribution headers and `UPSTREAM_LICENSE_PyPSA-Explorer.txt` present on every derived file. |
| `services/api` | NOT VERIFIABLE (in progress) | No FastAPI app factory or scenario/simulation routers yet. Reviewed so far: JWT (HS256 + JWKS, `exp`/`sub`/`aud` required, `alg` allow-list), artifact path allow-list (regex + index membership), body-size and rate-limit middleware — no defects found. |
| `pipelines/network-import` | VERIFIED (ac-dc-meshed) | Offline integration tests: files match manifest sha256, canonical consistent. The manifest flags placeholder `p_nom` honestly; values are identical to upstream PyPSA CSV. |
| `pipelines/observed` | pending | |
| `apps/web` | pending | `tsc -b --noEmit` passes. No test files (`vitest run` → "No test files found"). A grep for mock/fake/random/TODO in `src/` finds nothing. |
| `docs/research` | VERIFIED (references) | All 11 DOIs resolve via Crossref/DataCite to the cited titles and years. All 7 arXiv ids resolve to the cited titles. Equations spot-checked against the PyPSA paper structure. |
| Secrets | VERIFIED clean | A grep-based scan (JWT, Stripe, AWS, GitHub, Slack, private keys, Render, Vercel, Supabase, URL credentials, generic key=value) over tracked and untracked files (excluding `.venv`/`node_modules`) finds only the documented placeholder `postgresql://postgres.<project-ref>:<password>@…` in `docs/deployment/supabase.md`. `.env.example` has empty values only. |
