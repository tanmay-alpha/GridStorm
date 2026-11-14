# GridStorm TODO

Statuses: `BACKLOG → RESEARCHED → IMPLEMENTING → TESTING → VERIFIED → DEPLOYED`.
A task moves to VERIFIED only with recorded evidence (test output, artifact, screenshot) and to
DEPLOYED only when observed live. Priorities: P0 (blocking demo) · P1 (core) · P2 (valuable) · P3 (optional).
Owners: A Forensics · B Science (ScienceCore, ACValidation, CrisisAdvisor, StormBench, Sequential,
PypsaEurBuilder, StormRisk, CrossEngine, SimBenchAC, StormML) · C Frontend (Frontend, FrontendResearch) ·
D Data (DataPipelines, Research, ObservedEvents, ExplorerPort, DocsWriter) · E Backend/Infra (Backend,
CIDevOps) · F Verification (Verifier) · I Integration owner.

Last updated: 2026-11-14

## Phase 0 — Research, audit, baseline

| ID | Task | Pri | Owner | Deps | Status | Acceptance criteria |
|---|---|---|---|---|---|---|
| P0-01 | Environment inspection (Python, Node, uv, Docker, Git, disk, gh/Vercel/Render auth) | P0 | I | — | VERIFIED | Python 3.11.9/3.13.1, Node 24.14.1, uv 0.11.32, Docker 29.9.2 (24 CPU), gh as tanmay-alpha, Vercel as tanmay-alpha (hobby), Render API key valid; Supabase env vars present but placeholders |
| P0-02 | Verify no existing GridStorm repo/folder | P0 | I | — | VERIFIED | `gh repo view tanmay-alpha/GridStorm` → not found; local folder empty |
| P0-03 | Interface contracts + architecture + ADR 0001 | P0 | I | — | VERIFIED | `docs/architecture/contracts.md`, `overview.md`, `docs/decisions/0001-*.md` exist |
| P0-04 | Upstream source inventory, SHAs, license audit, manifest | P0 | A | — | IMPLEMENTING | 21 repos audited with pinned SHAs; `source-inventory.md`, `license-audit.md`, `upstream-manifest.json` |
| P0-05 | Dependency compatibility matrix with resolver evidence | P0 | A | — | IMPLEMENTING | `compatibility-matrix.md` with `uv pip compile` outcomes per engine pair |
| P0-06 | PyPSA-Explorer unchanged baseline (run app + tests) | P0 | B/ExplorerPort | — | VERIFIED | Upstream suite 105 passed / 3 skipped; `docs/audit/pypsa-explorer-baseline.md`; ADR 0002 keeps analytics, drops Dash runtime |
| P0-07 | Research papers matrix (5 papers) | P1 | D/Research | — | VERIFIED | `research-papers.md`: 8-column matrix + per-paper LaTeX equations for PyPSA, PyPSA-Eur, L2RPN, DemandCast, X-GridAgent; 27 links; full arXiv PDFs read |
| P0-08 | Tool decision matrix (PowerModels, PGLib, SimBench, ANDES, PyPSA-Earth, ORNL, GO) | P1 | D/Research | — | VERIFIED | `tool-decision-matrix.md`: PGLib data-only; ORNL/CoogGrid/NVIDIA/Grid2Game concepts-only; PowerModels/SimBench/ANDES/PyPSA-Earth/GOC3 deferred; GO Evaluation rejected (no licence) |
| P0-09 | External data sources licensing (OPSD, ENTSO-E, ERA5, NASA POWER, GEM, OSM, CEA, EIA) | P1 | D/Research | — | VERIFIED | `external-data-sources.md`: 10 sources checked 2026-11-14 (ERA5 CC BY 4.0 since 2025-07-02; EIA needs key (HTTP 403); CEA needs permission; ENTSO-E free re-use list appears to exclude actual load/generation) |
| P0-10 | Manually re-check ENTSO-E free re-use item numbers before any ingestion | P2 | D/ObservedEvents | P0-09 | BACKLOG | Each ENTSO-E-derived column used has a manifest licence entry matching the current re-use list, else only derived parameters are committed |
| P0-11 | "EENS" label only for probability-weighted scenario sets | P1 | B/StormRisk + C/Frontend | P2-08 | IMPLEMENTING | Test shows single-scenario outputs never carry the EENS label; UI uses "Unserved energy" for single runs |

## Phase 1 — Functional foundation

| ID | Task | Pri | Owner | Deps | Status | Acceptance criteria |
|---|---|---|---|---|---|---|
| P1-01 | Public GitHub repo `tanmay-alpha/GridStorm` | P0 | I | P0-02 | VERIFIED | https://github.com/tanmay-alpha/GridStorm public; commit `ea921fc` pushed to `main` |
| P1-02 | canonical-grid schemas + network importers (ac-dc-meshed, scigrid-de, PGLib case14/118) | P0 | D/DataPipelines | P0-03 | VERIFIED | 4 networks validated (0 errors); DC balance case14 259 MW / case118 4242 MW, zero mismatch; network-import 20 + canonical-grid 17 tests pass (commits `866d985`, `309e9f7`) |
| P1-03 | Data catalog with provenance | P1 | D/DataPipelines | P1-02 | VERIFIED | `docs/research/data-catalog.md`; open caveat: original SciGRID release licence not recovered — PyPSA CC-BY grant + conservative ODbL obligations documented |
| P1-04 | PyPSA-Eur reduced Belgium network | P2 | B/PypsaEurBuilder | — | IMPLEMENTING | Network built + LOPF solved, or reproducible blocker report |
| P1-05 | PyPSA-Explorer analytics port (`gridstorm_analytics`) | P1 | B/ExplorerPort | P0-06 | VERIFIED | 45 tests pass (commit `daa6f3e`); known gap: legacy demo CAPEX/OPEX differs from stored objective by ~2.3 %, cause unestablished |
| P1-06 | FastAPI API per contract §6 + OpenAPI | P0 | E/Backend | P0-03 | VERIFIED | 45 local tests pass, ruff clean; live `/api/v1/networks` lists 4 networks and `/api/v1/scenarios` lists 11 presets on Render |
| P1-07 | Postgres schema, Supabase migrations, RLS | P0 | E/Backend | P1-06 | IMPLEMENTING | Migrations apply on postgres:16; RLS policies for owner rows |
| P1-08 | Frontend shell + Grid Explorer map with real network data | P0 | C/Frontend | P1-02, P1-06 | IMPLEMENTING | Map renders real assets; details panel shows units + provenance |

## Phase 2 — Crisis simulation

| ID | Task | Pri | Owner | Deps | Status | Acceptance criteria |
|---|---|---|---|---|---|---|
| P2-01 | StormSpec package (models, schema, hash, capabilities, validation, manifest) | P0 | B/ScienceCore | P0-03 | VERIFIED | 30 tests pass (commit `96f3f3a`); JSON schema exported; unsupported ops rejected |
| P2-02 | PyPSA adapter (`gridstorm_pypsa`) + CLI | P0 | B/ScienceCore | P2-01 | VERIFIED | 30 tests pass incl. balance residual, outage, demand scaling, storage SOC, infeasible, reproducibility |
| P2-03 | Preset scenarios with real asset ids + precomputed artifacts | P0 | B/ScienceCore | P1-02, P2-02 | VERIFIED | 11 presets solved with HiGHS → `data/artifacts/pypsa/`; peak RSS: scigrid-de 541–550 MiB (> Render 512 MB → precomputed only), small networks 277–280 MiB |
| P2-03b | Per-network live-execution policy (no live scigrid-de on 512 MB) | P0 | E/Backend + C/Frontend | P2-03 | TESTING | Backend: `GRIDSTORM_LIVE_NETWORKS` + 422 `live_execution_unavailable` or labelled precomputed (`jobs/service.py`); UI wording check pending |
| P2-04 | Simulation jobs: persistent queue, subprocess, timeout, cancel, recovery | P0 | E/Backend | P1-06, P2-02 | DEPLOYED | Live on Render: `ac-dc-meshed-dc-link-outage` → stages queued…done, HiGHS optimal, objective 131 950.19 EUR, wall 1.30 s, balance residual 0 MW. Known: SQLite ephemeral → jobs lost on redeploy (observed once) until Supabase |
| P2-05 | Baseline vs crisis comparison + reports | P1 | E/Backend | P2-04 | IMPLEMENTING | Comparison math tests; MD/JSON report with manifests |
| P2-06 | Crisis Studio + Simulation Dashboard UI | P0 | C/Frontend | P2-04 | IMPLEMENTING | Run preset end-to-end in browser; real stages; no % progress |
| P2-07 | Scientific specification document | P1 | B/ScienceCore | P2-02 | VERIFIED | `docs/architecture/scientific-spec.md` with equations, units, citations, measured memory limits |
| P2-08 | StormRisk: Monte Carlo outage sampling → EENS ± CI, LOLP, convergence | P1 | B/StormRisk | P2-02 | IMPLEMENTING | Deterministic (seeded) study artifact; estimator tests vs hand-computed values |
| P2-09 | Observed-analogue scenarios (OPSD load/wind/solar → StormSpec events on scigrid-de) | P2 | D/ObservedEvents | P1-02, P2-02 | VERIFIED | 3 scenarios solved optimal; unserved energy baseline 0 / Dunkelflaute 3 237.1 / peak-load 5 647.7 / combined 20 499.7 MWh; residual ≤ 3.2e-7 MW; no raw ENTSO-E data committed; 25 tests (commit `4f944b5`) |
| P2-10 | Distribution-grid AC time-series stress (SimBench LV/MV: heat wave, PV over-voltage, PV loss, mitigation) | P2 | B/SimBenchAC | — | IMPLEMENTING | Partial work committed (`ece4887`); agent stopped at provider limit; ≥ 4 artifacts with per-step vm/loading; tests |

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
| P4-03 | Warden audit | P2 | B/CrisisAdvisor | — | VERIFIED | `docs/audit/warden-audit.md`; Warden suite reproduced 129 passed / 1 timing failure; competition claims kept as unverified |
| P4-04 | Crisis Response Advisor (deterministic, solver-verified) | P1 | B/CrisisAdvisor | P4-02 | VERIFIED | 5 PGLib crisis artifacts (3 with accepted recommendation, 2 honestly none accepted); 15 tests pass (commit `4fe25fb`) |
| P4-05 | Cross-engine check PyPSA LPF vs pandapower DC/AC PF on same PGLib case | P1 | B/CrossEngine | P1-02, P4-01 | VERIFIED | DC PF max abs diff 2.84e-13 MW (case14), 2.56e-12 MW (case118); AC-vs-DC linearisation 11.9 / 69.4 MW (expected); DC-OPF objective rel. diff ≤ 6.4e-11; `tests/cross_engine/run_all.py` 41.6 s; 10 harness tests pass (commit `49679ce`) |

## Phase 5 — Sequential operations and research

| ID | Task | Pri | Owner | Deps | Status | Acceptance criteria |
|---|---|---|---|---|---|---|
| P5-01 | Grid2Op episodes (≥ 3 agents × ≥ 2 chronics) + KPIs | P1 | B/Sequential | — | VERIFIED | 12 episodes (do_nothing/reco_powerline/greedy_simulate × 2 chronics × normal/line 1_3_3 outage), l2rpn_case14_sandbox, lightsim2grid; rerun trace hash identical (`050177c8…`); 20 tests pass; commit `c69a1dc` |
| P5-02 | Grid2Viz audit (MPL-2.0) and KPI concepts | P2 | B/Sequential | — | VERIFIED | `docs/audit/grid2viz-audit.md` (SHA `b416eba4`); KPIs re-implemented, no MPL code copied |
| P5-03 | StormBench PTDF/LODF screening vs DC/AC exact N-1 | P1 | B/StormBench | — | IMPLEMENTING | ≥ 5 cases; recall/precision/runtime/memory measured |
| P5-04 | Operations replay + Benchmarks + Contingency + Methods UI pages | P1 | C/FrontendResearch | P4-02, P5-01, P5-03 | IMPLEMENTING | Pages render real artifacts; unit tests use fixtures copied from real artifacts |
| P5-05 | ML contingency screening on simulator-derived labels vs DC-LODF/heuristic baselines | P3 | B/StormML | P5-03 | IMPLEMENTING | Operating-point and leave-one-network-out splits; bootstrap CIs; honest verdict vs baselines |
| P5-06 | User guide, engineering story, glossary, deployment docs | P1 | D/DocsWriter | all | IMPLEMENTING | Every documented command/feature exists in code at finish |

## Phase 6 — Deployment and hardening

| ID | Task | Pri | Owner | Deps | Status | Acceptance criteria |
|---|---|---|---|---|---|---|
| P6-01 | Dockerfile, docker-compose, render.yaml | P0 | E/Backend | P1-06 | VERIFIED | Image builds on Render and serves `/health` (git_sha reported) |
| P6-02 | Supabase project (free plan via Vercel Marketplace, fra1) + migrations applied | P0 | I/E | P1-07 | BLOCKED (user action) | Terms acceptance needed at vercel.com/…/accept-terms/supabase; then `/ready` database check ok against Supabase |
| P6-03 | Render deployment (free web service, Docker, frankfurt) | P0 | I/E | P6-01 | DEPLOYED | https://gridstorm-api.onrender.com `/health` 200, `/ready` ready (database `sqlite-ephemeral`, highspy 1.16.0, pypsa 1.4.0, 4 datasets); cold start ≈ 28 s |
| P6-04 | Vercel deployment of apps/web | P0 | I/C | P1-08 | IMPLEMENTING | Web: typecheck ok, lint 0 errors, 62/62 unit tests, build ok; `VITE_API_BASE_URL` set (prod+preview); production deploy in progress |
| P6-05 | Artifact storage (R2 if available, else local + committed artifacts) | P2 | E | P2-04 | RESEARCHED | No Cloudflare credentials available → LocalFS store + artifacts baked into image (ephemeral on Render free); S3/R2 adapter behind ArtifactStore interface; integrity test |
| P6-06 | GitHub Actions CI (lint, types, tests per env, web build, API smoke, actionlint) | P0 | E/CIDevOps | P1-06, P1-08 | TESTING | Run on `ece4887`: 15 jobs green; failing: pandapower, stormml, stormrisk, tests/integration, api container smoke — being fixed |
| P6-07 | Independent verification (components, science spot checks, API black-box, live browser audit) | P0 | F/Verifier | all | IMPLEMENTING | `docs/audit/verification-report.md` + `issues.md` with reproducible evidence |
| P6-08 | Security: secret scan, dependency audit (pip-audit, npm audit), container scan, authz tests | P1 | F/Verifier + E/CIDevOps | P6-01 | IMPLEMENTING | Findings recorded and triaged in `docs/audit/issues.md` |
