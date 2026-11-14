# GridStorm TODO

Statuses: `BACKLOG → RESEARCHED → IMPLEMENTING → TESTING → VERIFIED → DEPLOYED`.
A task moves to VERIFIED only with recorded evidence (test output, artifact, screenshot) and to
DEPLOYED only when observed live. Priorities: P0 (blocking demo) · P1 (core) · P2 (valuable) · P3 (optional).
Owners: A Forensics · B Science (ScienceCore, ACValidation, CrisisAdvisor, StormBench, Sequential,
PypsaEurBuilder) · C Frontend · D Data (DataPipelines, Research) · E Backend/Infra · F Verification ·
I Integration owner.

Last updated: 2026-11-14

## Phase 0 — Research, audit, baseline

| ID | Task | Pri | Owner | Deps | Status | Acceptance criteria |
|---|---|---|---|---|---|---|
| P0-01 | Environment inspection (Python, Node, uv, Docker, Git, disk, gh/Vercel/Render auth) | P0 | I | — | VERIFIED | Python 3.11.9/3.13.1, Node 24.14.1, uv 0.11.32, Docker 29.9.2 (24 CPU), gh as tanmay-alpha, Vercel as tanmay-alpha (hobby), Render API key valid; Supabase env vars present but placeholders |
| P0-02 | Verify no existing GridStorm repo/folder | P0 | I | — | VERIFIED | `gh repo view tanmay-alpha/GridStorm` → not found; local folder empty |
| P0-03 | Interface contracts + architecture + ADR 0001 | P0 | I | — | VERIFIED | `docs/architecture/contracts.md`, `overview.md`, `docs/decisions/0001-*.md` exist |
| P0-04 | Upstream source inventory, SHAs, license audit, manifest | P0 | A | — | IMPLEMENTING | 21 repos audited with pinned SHAs; `source-inventory.md`, `license-audit.md`, `upstream-manifest.json` |
| P0-05 | Dependency compatibility matrix with resolver evidence | P0 | A | — | IMPLEMENTING | `compatibility-matrix.md` with `uv pip compile` outcomes per engine pair |
| P0-06 | PyPSA-Explorer unchanged baseline (run app + tests) | P0 | B/ExplorerPort | — | IMPLEMENTING | Test counts recorded; app served HTTP 200 with bundled network; `docs/audit/pypsa-explorer-baseline.md` |
| P0-07 | Research papers matrix (5 papers) | P1 | D/Research | — | IMPLEMENTING | `research-papers.md` with required columns, equations, limitations, links |
| P0-08 | Tool decision matrix (PowerModels, PGLib, SimBench, ANDES, PyPSA-Earth, ORNL, GO) | P1 | D/Research | — | IMPLEMENTING | `tool-decision-matrix.md` with decision + justification per tool |
| P0-09 | External data sources licensing (OPSD, ENTSO-E, ERA5, NASA POWER, GEM, OSM, CEA, EIA) | P1 | D/Research | — | IMPLEMENTING | `external-data-sources.md` with redistribution verdicts and cited URLs |

## Phase 1 — Functional foundation

| ID | Task | Pri | Owner | Deps | Status | Acceptance criteria |
|---|---|---|---|---|---|---|
| P1-01 | Public GitHub repo `tanmay-alpha/GridStorm` | P0 | I | P0-02 | IMPLEMENTING | Repo public, main pushed |
| P1-02 | canonical-grid schemas + network importers (ac-dc-meshed, scigrid-de, PGLib case14/118) | P0 | D/DataPipelines | P0-03 | IMPLEMENTING | `data/networks/<id>/{network.nc,canonical.json,manifest.json}` validated; catalog.json |
| P1-03 | Data catalog with provenance | P1 | D/DataPipelines | P1-02 | IMPLEMENTING | `data-catalog.md` lists all provenance fields per dataset |
| P1-04 | PyPSA-Eur reduced Belgium network | P2 | B/PypsaEurBuilder | — | IMPLEMENTING | Network built + LOPF solved, or reproducible blocker report |
| P1-05 | PyPSA-Explorer analytics port (`gridstorm_analytics`) | P1 | B/ExplorerPort | P0-06 | IMPLEMENTING | capacity/energy_balance/costs match independent recomputation |
| P1-06 | FastAPI API per contract §6 + OpenAPI | P0 | E/Backend | P0-03 | IMPLEMENTING | All endpoints tested; `/docs` served |
| P1-07 | Postgres schema, Supabase migrations, RLS | P0 | E/Backend | P1-06 | IMPLEMENTING | Migrations apply on postgres:16; RLS policies for owner rows |
| P1-08 | Frontend shell + Grid Explorer map with real network data | P0 | C/Frontend | P1-02, P1-06 | IMPLEMENTING | Map renders real assets; details panel shows units + provenance |

## Phase 2 — Crisis simulation

| ID | Task | Pri | Owner | Deps | Status | Acceptance criteria |
|---|---|---|---|---|---|---|
| P2-01 | StormSpec package (models, schema, hash, capabilities, validation, manifest) | P0 | B/ScienceCore | P0-03 | IMPLEMENTING | Schema exported; hash stable; unsupported ops rejected (tests) |
| P2-02 | PyPSA adapter (`gridstorm_pypsa`) + CLI | P0 | B/ScienceCore | P2-01 | IMPLEMENTING | Balance residual < 1e-3 MW; outage/demand/storage tests pass |
| P2-03 | Preset scenarios with real asset ids + precomputed artifacts | P0 | B/ScienceCore | P1-02, P2-02 | IMPLEMENTING | ≥ 4 presets solved; artifacts with manifests; peak RSS measured |
| P2-04 | Simulation jobs: persistent queue, subprocess, timeout, cancel, recovery | P0 | E/Backend | P1-06, P2-02 | IMPLEMENTING | Lifecycle tests pass (success/fail/timeout/cancel/restart) |
| P2-05 | Baseline vs crisis comparison + reports | P1 | E/Backend | P2-04 | IMPLEMENTING | Comparison math tests; MD/JSON report with manifests |
| P2-06 | Crisis Studio + Simulation Dashboard UI | P0 | C/Frontend | P2-04 | IMPLEMENTING | Run preset end-to-end in browser; real stages; no % progress |
| P2-07 | Scientific specification document | P1 | B/ScienceCore | P2-02 | IMPLEMENTING | `scientific-spec.md` with equations, units, citations |

## Phase 3 — Mapping and analytics

| ID | Task | Pri | Owner | Deps | Status | Acceptance criteria |
|---|---|---|---|---|---|---|
| P3-01 | Line-loading visualisation + time slider replay | P1 | C/Frontend | P2-06 | IMPLEMENTING | Map colours match result `loading_pct` for selected snapshot (test) |
| P3-02 | Compare & Replay, report export | P1 | C/Frontend | P2-05 | IMPLEMENTING | Two runs compared; export downloads report |
| P3-03 | Research Library (saved scenarios, jobs, datasets, manifests) | P2 | C/Frontend | P1-06 | IMPLEMENTING | Lists real records; downloads work |

## Phase 4 — Contingency and AC validation

| ID | Task | Pri | Owner | Deps | Status | Acceptance criteria |
|---|---|---|---|---|---|---|
| P4-01 | pandapower reference validation (case9–case300) | P1 | B/ACValidation | — | IMPLEMENTING | Max errors vs MATPOWER reference reported |
| P4-02 | N-1 engine with explicit classification + ranking | P1 | B/ACValidation | P1-02 | IMPLEMENTING | Artifacts for case14/118 with class counts |
| P4-03 | Warden audit | P2 | B/CrisisAdvisor | — | IMPLEMENTING | Reproduced vs unverified claims documented |
| P4-04 | Crisis Response Advisor (deterministic, solver-verified) | P1 | B/CrisisAdvisor | P4-02 | IMPLEMENTING | ≥ 3 artifacts with accepted/rejected candidates; tests |
| P4-05 | Cross-engine check PyPSA LPF vs pandapower DC PF on same PGLib case | P1 | F | P1-02, P4-01 | BACKLOG | Branch flow max abs diff reported (two envs, artifact exchange) |

## Phase 5 — Sequential operations and research

| ID | Task | Pri | Owner | Deps | Status | Acceptance criteria |
|---|---|---|---|---|---|---|
| P5-01 | Grid2Op episodes (≥ 3 agents × ≥ 2 chronics) + KPIs | P1 | B/Sequential | — | IMPLEMENTING | Deterministic trace hashes; artifacts |
| P5-02 | Grid2Viz audit (MPL-2.0) and KPI concepts | P2 | B/Sequential | — | IMPLEMENTING | `grid2viz-audit.md` |
| P5-03 | StormBench PTDF/LODF screening vs DC/AC exact N-1 | P1 | B/StormBench | — | IMPLEMENTING | ≥ 5 cases; recall/precision/runtime/memory measured |
| P5-04 | Operations replay + Benchmarks + Contingency UI pages | P1 | C/Frontend | P4-02, P5-01, P5-03 | IMPLEMENTING | Pages render real artifacts |
| P5-05 | Optional ML on simulation-derived labels | P3 | — | P5-03 | BACKLOG | Only with chronological/network-aware splits and heuristic baselines |

## Phase 6 — Deployment and hardening

| ID | Task | Pri | Owner | Deps | Status | Acceptance criteria |
|---|---|---|---|---|---|---|
| P6-01 | Dockerfile, docker-compose, render.yaml | P0 | E/Backend | P1-06 | IMPLEMENTING | Image builds; `/health` 200 in container |
| P6-02 | Supabase project (free) + migrations applied | P0 | I/E | P1-07 | BACKLOG | `/ready` database check ok against Supabase |
| P6-03 | Render deployment (free web service) | P0 | I/E | P6-01 | BACKLOG | Live `/health` and `/ready` |
| P6-04 | Vercel deployment of apps/web | P0 | I/C | P1-08 | BACKLOG | Live URL loads; API reachable (CORS) |
| P6-05 | Artifact storage (R2 if available, else local + committed artifacts) | P2 | E | P2-04 | BACKLOG | Documented choice; integrity test |
| P6-06 | GitHub Actions CI (lint, types, tests per env, web build, API smoke) | P0 | I | P1-06, P1-08 | BACKLOG | Green CI run on main |
| P6-07 | Independent verification + live browser audit | P0 | F | P6-03, P6-04 | BACKLOG | `docs/audit/verification-report.md` with evidence |
| P6-08 | Security: secret scan, dependency audit (pip-audit, npm audit), container scan | P1 | F | P6-01 | BACKLOG | Findings recorded and triaged |
