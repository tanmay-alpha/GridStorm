# GridStorm TODO

Statuses: `BACKLOG → RESEARCHED → IMPLEMENTING → TESTING → VERIFIED → DEPLOYED`.
A task moves to VERIFIED only with recorded evidence (test output, artifact, screenshot) and to
DEPLOYED only when observed live. Priorities: P0 (blocking demo) · P1 (core) · P2 (valuable) · P3 (optional).
Owners: A Forensics · B Science (ScienceCore, ACValidation, CrisisAdvisor, StormBench, Sequential,
PypsaEurBuilder, StormRisk, CrossEngine, SimBenchAC, StormML) · C Frontend (Frontend, FrontendResearch) ·
D Data (DataPipelines, Research, ObservedEvents, ExplorerPort, DocsWriter) · E Backend/Infra (Backend,
CIDevOps) · F Verification (Verifier) · I Integration owner.

Last updated: 2026-11-17

## Progress dashboard

**Original implementation scope:** 58/58 tasks complete (46 VERIFIED + 12 DEPLOYED). **Post-launch production recovery (2026-11-15):** 12 of 13 items deployed and tested on production (P0 artifact loss fixed and verified across a controlled restart); POST-13 closed as documented on 2026-11-17; re-verified on production `f8b3c28` the same day (see that section). **GridStorm 3.2:** see below.

| State | Count | Tasks |
|---|---|---|
| DEPLOYED (observed live) | 12 | API on Render, web on Vercel, live jobs, comparisons/reports, Studio + Run dashboard, line-loading replay, Explorer map, OOM fix, a11y/perf fixes, audit defect fixes, PyPSA-Eur BE live, Supabase Postgres |
| VERIFIED (evidence recorded) | 46 | research, licensing (incl. ENTSO-E remediation), all science engines, data, CI, verification, security, a11y/perf audit, EENS wording |

Live (since 2026-11-17): https://gridstorm.vercel.app (Vercel `dpl_HXJ6tmwRhBqWrqMQgasMBLkq4eMT`, Git build of `main` `f8b3c28`, PR #14) · https://gridstorm-api.onrender.com (`/health` git_sha `f8b3c28`; `/ready` postgres + supabase durable) · CI green on PR #14 (28/28, run 44006783223) and on `main` (run 44008687576); scientific reproducibility on `main` incl. full tests green (run 44009643558); production browser smoke (44009033246) and production smoke (44009037283) green; `scripts/probe_production.py` all PASS. Earlier: web `387f584` / API `127db27` (PR #12/#13), `cf482f2` (3.0).

## GridStorm 3.3 — database verification, refinement (started 2026-11-17)

Branch `release/gridstorm-3.3` from `main` `16e9f78`. Baseline: web Vercel build of `f8b3c28`, API git_sha `f8b3c28`.
Statuses as in 3.2. Refinement only: nothing from 3.0/3.2 is re-implemented.

| ID | Task | Pri | Status | Acceptance criteria | Evidence |
|---|---|---|---|---|---|
| G33-01 | Production DB + Storage inventory (completes G32-02) and least-privilege fix | P0 | LOCALLY TESTED | Real measured values; access findings fixed with an isolated-DB test and rollback | Credentials: `DATABASE_URL` of the GridStorm Render service via the (refreshed) Render API, read-only run 2026-11-17 11:17 UTC → [inventory](docs/data/production-inventory.md): migrations 0001–0003 sha-identical, 12 tables RLS on, 14 jobs all completed with metrics + result rows, 0 orphan objects, 0 sha/size mismatches, 8 broken refs = the 5 known legacy jobs, DB 13.1 MB (2.6 %), Storage 2.54 MB (0.25 %), bucket private. Findings: anon write grants unused by any policy; `worker_id`/`heartbeat_at` readable via PostgREST → `0004_client_role_least_privilege.sql` + docker test |
| G33-02 | Dependabot: `actions/checkout` v7 (#1), `gitleaks-action` v3 (#4) | P3 | IMPLEMENTING | Upstream notes reviewed; CI green before merge | #1: v5 Node 24, v6 credentials in a separate file, v7 blocks fork checkout only for `pull_request_target`/`workflow_run` (not used here); 28/28 checks → merged. #4: v3 = Node 24 runtime, no input changes; rebase requested |

## GridStorm 3.2 — data observatory, scientific reliability, product polish (started 2026-11-17)

Branch `release/gridstorm-3.2` from `main` `387f584`, merged as PR [#14](https://github.com/tanmay-alpha/GridStorm/pull/14) → `f8b3c28`. Separate count; **not** part of earlier tallies.
**Progress: 10/11 deployed (8 PROD TESTED, 2 DEPLOYED), 1 BLOCKED (G32-02 database/storage part: no authorized Supabase credentials in this environment; API-observable part documented).**
Rollback: no DB migration; web `vercel promote` the `387f584` production deployment; API Render manual deploy of `127db27`.
Statuses: `BACKLOG → IMPLEMENTING → LOCALLY TESTED → CI VERIFIED → DEPLOYED → PROD TESTED`, or `BLOCKED` / `DOCUMENTED`.
Owners: I coordinator · A Science · B DesignShell + Workflows (UI) · C DataPipeline + DbInventory · D ObservatoryApi · E ObservatoryUi + Docs · F Verifier.
Baseline (2026-11-17): live web Vercel `387f584` (READY), live API Render `/health` git_sha `127db27`; main CI run 43891187831 green;
production browser smoke 43890735975 green; scheduled scientific run 43868756005 **failed** (StormBench MISMATCH). UI baseline: `docs/audit/screenshots/round2-after/` (production, 2026-11-16).

| ID | Task | Pri | Owner | Status | Acceptance criteria | Evidence |
|---|---|---|---|---|---|---|
| G32-01 | StormBench reproducibility: root cause of Kendall τ / Spearman drift, tie-aware rank statistics, regenerated references, regression tests | P0 | A | PROD TESTED | Root cause documented; statistics invariant to round-off; `scientific.yml` green on a fresh runner | Root cause: severities equal in exact arithmetic differ by 1e-14…1e-13 pp across platforms (OpenBLAS `DYNAMIC_ARCH` kernel choice; reproduced locally with `OPENBLAS_CORETYPE=Sandybridge` → case30 τ 0.997861); their order decided τ/ρ. Fix (`029e016`): tie groups within `TOL_PCT` = 1e-6 pp (single linkage, order-invariant) before τ-b/ρ/recall@k; new `ties` field. Screening-vs-DC τ = ρ = 1 on all 6 cases (was 0.978–0.9997); AC τ shifts ≤ 0.011. 29 tests (12 new); local MATCH under 1/8 threads and Sandybridge kernel; **fresh runners: branch run 43959332222 and `main` run 44009643558 (incl. full slow/network tests) — pypsa, pandapower, stormbench MATCH**; production `/api/v1/artifacts/stormbench/stormbench-case14-ieee` serves τ = ρ = 1.0. [docs](docs/benchmarks/stormbench.md#reproducibility-and-ties) |
| G32-02 | Production data inventory (Supabase tables, rows, storage, RLS, indexes) | P0 | C | BLOCKED (DB) / DOCUMENTED (API) | `docs/data/production-inventory.md` with measured coverage matrix and classified gaps | API-observable inventory measured (12 public jobs, 7 results sha-verified, 5 HTTP 410; 55 precomputed artifacts); DB/Storage sections blocked: shell `SUPABASE_DB_*` are placeholders, Render CLI token expired, Supabase env intentionally unlinked from Vercel (POST-06). Read-only script `scripts/inventory/production_inventory.py` ready. [inventory](docs/data/production-inventory.md) |
| G32-03 | Curated observed-data publication pipeline (licence-gated bundle, manifests, quality reports); deploy path includes it | P0 | C + D | PROD TESTED | Only permitted series published; checksums verified at load; source change triggers publication check + API redeploy | `5f94920`: bundle 2.49 MB (5 entries), licence gate refuses actual load/generation/capacities, `--verify` + `observatory.yml` (green on `main`, run 44008687567); Render redeployed on merge via the `data/observatory/**` build filter; production `/api/v1/data/catalog` → 21 entries, bundle `2026-11-17.1` status `ok` |
| G32-04 | Data catalog API (`/api/v1/data/catalog…`: list, detail, bounded series, export) | P1 | D | PROD TESTED | Bounded, paginated, cached, typed errors; tests | `5f94920`: 38 new tests; API suite 203 / 2 skipped (was 165/2). Production: catalog 196 ms, detail 187 ms median, `max-age=300`; observed-analogue preset run on production → job `5dbb2e94` precomputed, unserved 2 721.006897 MWh, result sha `6d0c0805…` = local. [ADR 0003](docs/decisions/0003-file-backed-data-observatory.md) |
| G32-05 | Data Observatory UI (`/data`, `/data/:id`) | P1 | E | PROD TESTED | Browse/filter, coverage + quality, provenance drawer, UTC charts with gaps, export, validated "use in scenario" | `ba0cafa`; production journey: Use in a scenario → Studio precomputed → run; CSV export with licence header (177 lines); disabled export on metadata-only entries; drawer focus trap + return; 0 console errors on `/data` and `/data/opsd-de-load-forecast` |
| G32-06 | New source done well: NASA POWER hourly (UTC) weather + renewable resource for the analogue windows; EIA evaluated | P1 | C | DEPLOYED | Source scoring matrix; UTC requested explicitly; reanalysis labelled modeled-not-station | 8 requests with `time-standard=UTC` (API v2.10.4; MERRA-2 + CERES SYN1deg), 4 cities × (2015-01-17..23 + all 2017), T2M/WS10M/WS50M/GHI; T2M/WS10M match the older extract 4 032/4 032; EIA evaluated + deferred (keyless request 403 `API_KEY_MISSING`; US BA demand has no validated mapping to these networks). [sources](docs/data/sources-and-licensing.md) |
| G32-07 | Visual redesign: design tokens, home, Grid Explorer, schematic | P1 | B | PROD TESTED | Before/after screenshots at 5 viewports × 2 themes; no CLS regression | `1fde606`; production after vs before (same script): IEEE-14 Explorer CLS 0.0291 → 0.0172 (desktop), 0.0119 → 0.0021 (mobile); SciGRID 0.0309 → 0.0171 / 0.0476 → 0.0296; home ≤ 0.0021. Screenshots `docs/audit/screenshots/3.2-{before,after}/` |
| G32-08 | Workflow redesign: Studio, Results, Compare/Mitigation, Research Workbench | P1 | B | PROD TESTED | Conclusions above the fold; no fabricated values; mobile preserved | `2ab0f25`; production after vs before: /studio CLS 0.0253 → 0.0218 (desktop), run 0.0143 → 0.0013, mobile all 0.0021; compare desktop 0.0039 → 0.0161 (< 0.1); production browser smoke 44009033246 green |
| G32-09 | README redesign, user guide, architecture/data docs | P1 | E | DEPLOYED | Real screenshots; routes/counts verified | `cf38c3a`: README restructured with 6 current screenshots (`docs/media/`, each < 200 KB), datasets table, mermaid architecture; user guide `/explorer` → `/explore` + Data Observatory; counts checked against repo (5 networks, 15 presets, 58 precomputed artifacts, bundle 5 entries) |
| G32-10 | Performance before/after (data workflows, bundle, API) | P2 | F | PROD TESTED | Same script before/after | Same script on production before (`387f584`/`127db27`) and after (`f8b3c28`): mobile LCP SciGRID 2924 → 1304 ms, run 2484 → 1260 ms; regression desktop run LCP 1460 → 1668 ms; initial JS+CSS gzip 370.7 → 374.3 KiB (+1 %). [web-performance-3.2](docs/benchmarks/web-performance-3.2.md#after-production-gridstorm-32-release) |
| G32-11 | Independent verification + release (CI, scientific, e2e, a11y, prod smoke) | P0 | F + I | PROD TESTED | All gates green; deployed SHAs recorded | PR #14 CI 28/28; `main` CI, scientific (full), observatory, production browser smoke, production smoke all green; `probe_production.py` all PASS; deployed web `dpl_HXJ6tmwRhBqWrqMQgasMBLkq4eMT` + API git_sha `f8b3c28`. Local: axe 0 violations (36 runs), overflow 0/90 ([verification-3.2](docs/audit/verification-3.2.md)) |

## Production follow-up — recovery audit, round 2 (2026-11-15, PR #12 merged as `127db27`, follow-up PR #13)

Baseline (before changes): `main` `68dcc09`; Render API `cf482f2` (`/ready` postgres + supabase durable); `scripts/probe_production.py` all PASS; production Playwright smoke on `main` green (run 43720944322); 9 completed jobs with lost results (HTTP 410). A fresh read-only live audit (15 routes × 3 viewports × 2 themes, 0 page errors, 0 overflow) found 1 P1, 3 P2, 14 P3 defects (LA-01…LA-17): [report](docs/audit/live-2026-11-15-round2.md). PR [#12](https://github.com/tanmay-alpha/GridStorm/pull/12).
Statuses: `IMPLEMENTING → LOCALLY TESTED → CI VERIFIED → DEPLOYED → PROD TESTED`, or `BLOCKED` / `DOCUMENTED`.

| ID | Task | Pri | Status | Evidence |
|---|---|---|---|---|
| R2-01 | Restore lost legacy blobs byte-for-byte when the original bytes still exist (`gridstorm_api.jobs.restore`) | P0 | PROD TESTED | 4 SciGRID precomputed jobs (`5dafdc1a`, `f2fc0cf3`, `5323bc95`, `c800561d`) recorded sha `e3e3494b…` = canonical payload of the artifact committed at `96f3f3a`; restored on production → HTTP 200, body sha = recorded sha = header, MD report 200. 5 live IEEE-14 results stay 410: their bytes embed solver wall time, so no recompute can reproduce them |
| R2-02 | `/studio` CLS regression | P2 | PROD TESTED (desktop/tablet) | local 0.0505 → 0.0002; production 1440: 0.0002 light / 0.025 dark, 768: 0.0007. Mobile with slower requests 0.19 (summary aside appears then collapses) → fixed in PR #13 |
| R2-03 | Run page / Library layout shift (LA-04) | P2 | PROD TESTED | production after deploy: run c328 0.0145 / 0.0319 / 0.0000 (1440 / 768 / 390), was 0.27 / 0.56 / 0.71; Library ≤ 0.0007, was 0.18 / 0.69–0.77 / 0.59; 410 run ≤ 0.0154. `/compare?comparison=` mobile 0.19 → fixed in PR #13 |
| R2-04 | Compare metric table in reading order | P3 | DEPLOYED | `orderMetrics` + unit test |
| R2-05 | Legacy comparison MD export 500 (LA-01); 500s lacked CORS → "backend unreachable" | P1 | PROD TESTED | `/reports/4f5661ec…?format=md` 500 → 200 (8000 B); production 404 carries `access-control-allow-origin`; Export MD downloads in the browser |
| R2-06 | Downloads hash to the displayed sha (LA-02); comparison reuse (LA-09) | P2 | PROD TESTED (LA-02) / DEPLOYED (LA-09) | report JSON body sha = header (`30fe7e72…`); browser "Result JSON" file sha = header = job sha (`b4e6211f…`); reuse not exercised on production (no POSTs) |
| R2-08 | LA-03 legacy "EUR" assumption text; LA-05 stored-comparison view, CO₂ label; LA-07 error copy; LA-10 Benchmarks units; LA-12 timestamps / precomputed wall time; LA-15 4-sig-fig scaled money | P2/P3 | PROD TESTED | run 458fddab shows no "EUR" outside the legacy note; KPI "2.001 M"; "CO₂ emissions"; "Compare a different pair" |
| R2-09 | LA-06 Explorer search reset + focus; LA-08 one guide step list; LA-11 ≥ 24 px targets; LA-13 no "provenance n/a"; LA-14 plurals + custom-scenario name; LA-16 event-field aria-invalid; LA-17 themed scale bar | P3 | PROD TESTED (LA-06, 08, 11 sort headers) / DEPLOYED (rest) | search reopens empty; "step 1 of 5"; 0 sort headers < 24 px on mobile (was 16 px). Remaining < 24 px: Library job-id links (14 px) → PR #13 |
| R2-07 | Cached geographic network switch (~250–285 ms) | P3 | DOCUMENTED | Profiled in 3.0: 39–58 ms with basemap tiles aborted; the remainder is third-party basemap tile work, not GridStorm data loading. Not changed |
| R2-10 | PR #13: `/compare?comparison=` mobile CLS 0.19 → 0.002 (picker panel and comparison now render together); Studio summary aside deferred during grid loading; Library table-cell links ≥ 24 px on touch; Library artifact downloads keep server bytes; Benchmarks formatting tests; Workbench radios 24 px on touch | P2/P3 | PROD TESTED | production at 390×844 with 300 ms added API delay: /compare?comparison=4f5661ec, /studio, /library, /runs/c328baa0 all CLS 0.0021 (before: 0.19 / 0.19 / 0.59 / 0.71). Local 768/1440 ≤ 0.0083; e2e 24/24. Screenshots: `docs/audit/screenshots/round2-after/` |
| R2-11 | Dependabot GitHub Actions bumps | P3 | MERGED #2, #3, #5, #6; #1 rebasing; #4 (gitleaks v3) stale base, Dependabot unresponsive | Triage: all bumps compatible with the workflows' inputs; #4 needs a fresh CI run before merge |

## GridStorm 3.0 — science, product and research usability (started 2026-11-15)

Branch `release/gridstorm-3.0` from `main` `ae4ee9a`. Separate count; **not** part of the 58/58 or post-launch tallies.
Statuses: `BACKLOG → IMPLEMENTING → LOCALLY TESTED → CI VERIFIED → DEPLOYED → PROD TESTED`, or `BLOCKED` / `DEFERRED`.
Owners: I coordinator · ScienceCost (A) · ExplorerMaps, StudioDesign, ResultsCompare (B) · BackendSecurity (C) · ResearchWorkbench (D) · Verifier (E).

Baseline before changes (2026-11-15, local Windows, `ae4ee9a`): web lint 0 errors / 5 warnings, typecheck clean, vitest 128/128, build OK;
Python stormspec 30, pypsa 32, api 114 (+1 Linux-only skip), analytics 47, scientific 161, network-import 20, integration 98 (+90 network skips) — all pass.
Deployed before 3.0: web Vercel `dpl_fbnkrtGtHYTcVeMir2Psy9QgB3fB` (prebuilt CLI deploy, no git metadata); API Render `dd185d1`.
**Deployed 3.0 (2026-11-15):** PR #10 merged as `cf482f2`. API Render `/health` git_sha `cf482f2`, `/ready` postgres + supabase durable; web Vercel `dpl_27i7ivAn3GrRUpzKuXdHAtShVeoT` built by the Vercel GitHub integration from the merge, aliased gridstorm.vercel.app. Rollback: Vercel `vercel promote dpl_fbnkrtGtHYTcVeMir2Psy9QgB3fB`; Render redeploy `dd185d1` (no DB migration in this release).

**Progress: 14/14 deployed — 8 PROD TESTED (G3-01, 02, 03, 05, 09, 10, 13, 14), 6 DEPLOYED (G3-04 spoof resistance not exercised live, G3-06 partial, G3-07/08/11/12 loaded in production but not re-journeyed there).** Gemini models were requested but unavailable in this environment; docs and verification ran on GPT 6.1 Sol.
Production evidence: `scripts/probe_production.py` all PASS (durable storage, headers, CORS, 2 results sha-verified, 9 pre-fix results disclosed 410); production Playwright read-only 11/11 locally after the mobile-journey spec update; live guided journey on production job `c328baa0` (HiGHS optimal, 200 MWh unserved, money in PGLib cost units, VOLL shown as penalty) → comparison `ee5566d6` vs baseline `458fddab`; `/api/v1/networks` serves cost bases for all 5 datasets. Vitals: [web-performance-3.0](docs/benchmarks/web-performance-3.0.md#production-route-vitals-before--after-the-30-release).
Known follow-ups: `/studio` CLS 0.0002 → 0.0505 and cached geographic switch ~250–285 ms; observed-analogue studies not served as artifacts; compare metric table ordering alphabetical.

| ID | Task | Pri | Owner | Modules | Deps | Status | Acceptance criteria | Evidence |
|---|---|---|---|---|---|---|---|---|
| G3-01 | Cost-basis model; truthful money units on all 5 datasets; VOLL coherent with objective | P0 | ScienceCost | manifests, importers, workers/pypsa, stormspec schema, api catalog/comparisons, scientific tests | — | PROD TESTED | Every manifest declares a verified `cost_basis`; results embed it; PGLib never labelled EUR; incompatible bases rejected in comparisons; objectives reproduce | `49decd8`; 12 presets regenerated, objectives + 216 metrics identical; scientific 179 + slow 2, pypsa 40, analytics 53, api cost-basis tests; [audit](docs/research/cost-basis-audit.md); live `/networks` bases + job `c328baa0` |
| G3-02 | Money display via cost basis across web (results, compare, research) | P0 | ResultsCompare, ResearchWorkbench | `lib/money.ts`, runs, compare, research | G3-01 | PROD TESTED | No UI path shows PGLib/illustrative costs as EUR; unknown basis labelled explicitly | `cc39b08`, `3ca47d3`, `ee57075`, `5c40876`; production run + compare pages: only "EUR" is the "not EUR" disclaimer |
| G3-03 | Single-period replay label (was POST-12) | P3 | ResultsCompare | runs | — | PROD TESTED | PGLib replay shows "single period (no timestamp)" not `now` | `3ca47d3`, `846da4c`; seen on production run `c328baa0` |
| G3-04 | Trusted-proxy client identity for rate limits; security re-verification | P1 | BackendSecurity | `ratelimit.py`, render.yaml, docs/audit | — | DEPLOYED | Spoofed leading XFF cannot change bucket under Render topology; RLS/secrets/storage rechecked | `4f510e8`; 16 security tests; RLS 12 tables / 15 policies (rolled-back txn); bundle secret scan clean; [security-3.0](docs/audit/security-3.0.md); live spoof test not run (no load against prod) |
| G3-05 | Schematic network view (IEEE 14/118) + map polish; geographic MapLibre preserved | P1 | ExplorerMaps | components/map, network, explorer | — | PROD TESTED | Legible balanced IEEE-14 at 3 viewports; selection/filter correct; no misleading values | `5c40876`; `explorer-schematic.spec.ts`; production read-only 11/11 (schematic + all 5 networks render) |
| G3-06 | Cached network-switch regression + map performance | P2 | ExplorerMaps | map, explorer | G3-05 | DEPLOYED (partial) | Before/after measured with same script/conditions | IEEE-14 prod 680→419 KB, heap 9.9→5.7 MB, LCP 1120→836 ms; **cached geographic return still 249–285 ms (not fixed)**; [web-performance-3.0](docs/benchmarks/web-performance-3.0.md) |
| G3-07 | Studio compact preset cards, progression, drafts, keyboard, mobile | P1 | StudioDesign | studio | — | DEPLOYED | Compact mobile cards; details expandable; keyboard through 4 steps | `540fc47`; `studio-guided-demo.spec.ts` 6/6; prod mobile journey reaches presets; prod `/studio` CLS 0.0505 (follow-up) |
| G3-08 | Design-system primitives (headers, provenance, execution, cost basis, states) | P2 | StudioDesign | components/ui | — | DEPLOYED | Primitives documented + reused | `540fc47`, `78edabc` (a11y); [design-system](docs/architecture/design-system.md) |
| G3-09 | Guided IEEE-14 generator-outage journey (home → studio → run → compare → brief → download) | P1 | StudioDesign + ResultsCompare | home, studio, runs, compare | G3-07, G3-10 | PROD TESTED | Journey passes in browser end-to-end on real outputs | Production: home → guide (gen-1, bus-1, 340 MW from API) → job `c328baa0` → comparison `ee5566d6`, 0 page errors; download verified locally by Verifier |
| G3-10 | Results hierarchy + deterministic Grid Impact Brief | P1 | ResultsCompare | runs, brief | G3-02 | PROD TESTED | What happened / why / what changed above the fold; brief statements evidence-linked, no invented causality | `3ca47d3`; `brief.test.ts`; production brief "Feasible with 200 MWh unserved", VOLL statement labelled model economics |
| G3-11 | Compare improvements + baseline→crisis→mitigation workflow | P1 | ResultsCompare | compare, mitigation | G3-10 | DEPLOYED | ≥1 triple end-to-end on verified outputs; zero-baseline/pp/cost-basis handling tested | SciGRID storage off→on: unserved 190.2 MWh unchanged, objective −~342 k illustrative units, congested 33→30; `mitigation-studies.spec.ts`, `846da4c` (relative % + slider) |
| G3-12 | Research Workbench with references, assumptions, execution mode, reproduction manifests | P2 | ResearchWorkbench | research, workbench, api artifacts | — | DEPLOYED | Every study entry complete and truthful; manifest download works; summaries used | `ee57075`; 10 studies (observed analogues not listed); prod `/benchmarks` 23→8 API requests, `/contingency` CLS 0.229→0.002; live `/artifacts?include=header` |
| G3-13 | Docs consistency (README storage claim, deployment, user guide, audits superseded) | P1 | I + DocsWriter | docs, README | all | PROD TESTED | Docs describe deployed system; superseded findings marked | README, architecture/backend, deployment/backend + vercel (Git auto-deploy observed), user guide, glossary; 5 historical audits bannered |
| G3-14 | Independent verification + release (CI, browser, a11y, visual, prod smoke) | P0 | Verifier + I | all | all | PROD TESTED | CI green; deployed SHAs recorded; prod smoke passes | CI run 43699511938 green (incl. e2e 38 specs); Verifier: 291 unit, 30 axe audits (3 serious fixed in `78edabc`, 0 critical), 20 overflow checks; prod smoke + probe PASS; screenshots `docs/audit/screenshots/3.0/` |

## Post-launch production audit — 2026-11-15

Evidence: [production audit](docs/audit/production-2026-11-15.md) · [draft UX PR #7](https://github.com/tanmay-alpha/GridStorm/pull/7) · [P0 artifact loss issue #8](https://github.com/tanmay-alpha/GridStorm/issues/8).

These items are **not** included in the original 58/58 delivery count.

Statuses for this section: `BACKLOG → IMPLEMENTING → LOCALLY TESTED → CI VERIFIED → DEPLOYED → PROD TESTED`, or `BLOCKED`.
Integration branch: `release/production-recovery` (PR #7 head + recovery work). Coordinator: I. PR #7 merged and issue #8 closed on 2026-11-15.

**Re-verification against the production-recovery brief (2026-11-17, production `f8b3c28`):** `GET /api/v1/simulations/2d47898b…/result` → 410 (disclosed, recomputed as `458fddab`); `scripts/probe_production.py` all PASS after the 3.2 redeploy (instance replaced; 7 older results still sha-verified from Supabase Storage). One bounded live IEEE-14 solve (`pglib-case14-ieee-gen-1-outage`, `reuse: false`) → job `14735bbd`, HiGHS 1.16.0 `optimal`, 200 MWh unserved, objective 2 001 372.90 PGLib cost units, balance residual 0 MW; downloaded result bytes hash to `x-gridstorm-result-sha256` `f78a5bbb…`; comparison `746d4e14` vs baseline `458fddab`, JSON report body sha = `X-GridStorm-Report-SHA256` `f4c601eb…`, MD report 200 (8 697 B; the header identifies the canonical JSON report, by design). Only open item from that brief: Supabase DB/RLS re-audit, blocked on credentials (G32-02).

| ID | Task | Pri | Owner | Deps | Status | Acceptance criteria / evidence |
|---|---|---|---|---|---|---|
| POST-01 | Durable generated-result artifact storage (Render resets disk) | P0 | E/Storage | Supabase Storage bucket `gridstorm-artifacts` | PROD TESTED | Deployed `dd185d1`; `/ready` storage `supabase`, `durable: true`. Job `34424ec2` (IEEE-14, HiGHS optimal) sha256 `77bcc325…` verified; **controlled Render restart 01:19:33Z** → HTTP 200, identical bytes + sha; MD report 200 |
| POST-01b | Truthful missing-artifact semantics, owner-safe verified reuse, recompute recovery | P0 | E/Storage + C/UXWorkflow | POST-01 | PROD TESTED | Legacy `2d47898b` → HTTP 410 `artifact_unavailable` with recovery path; recomputed as `458fddab` (new sha `4bc42de8…`, `recomputed_from`), cost 2051.526309 EUR = committed precomputed baseline; lost checksum not reused |
| POST-02 | Crisis Studio unavailable-run guard, runnable example CTA, scoped presets | P1 | C/Frontend | — | PROD TESTED | Live: edited SciGRID scenario → Run disabled, 0 simulation POSTs (production Playwright) |
| POST-03 | Read-only public Vercel + Render checks + keep-alive | P1 | F/LiveAudit | — | PROD TESTED | `scripts/probe_production.py` all PASS (incl. durable job); production Playwright 11/11; `keepalive.yml` scheduled |
| POST-04 | GeoJSON-first map loading | P1 | C/UXShell | — | DEPLOYED | Requests 12/12/13 → 4; first-map medians 2591→1931 / 1642→1138 / 2296→2178 ms (local build vs live API); cached return-switch regressed 117→273 ms (documented) |
| POST-05 | Landing + grouped navigation + Explorer map-first redesign | P1 | C/UXShell | — | PROD TESTED | Live Overview page; "Try a sample crisis" → `/studio?network=pglib-case14-ieee&preset=pglib-case14-ieee-gen-1-outage` (review step, LIVE SOLVE); 0 console errors |
| POST-06 | Supabase RLS/policies/indexes/privileges; secrets hygiene | P1 | E/SecurityDB | — | DEPLOYED | RLS probe 38/38 (rolled back); 0003 applied; 16 Supabase vars removed from Vercel web project; bundle + gitleaks clean |
| POST-07 | Readiness distinguishes writable vs durable storage | P1 | E/Storage | POST-01 | PROD TESTED | Live `/ready.checks.storage = {backend: supabase, durable: true}` |
| POST-08 | Studio staged flow, results hierarchy, compare-with-baseline | P1 | C/UXWorkflow | — | PROD TESTED | Live run page: summary (outcome, unserved 200 MWh, cost, curtailment, max loading), map/replay, "Compare with baseline" |
| POST-09 | Deep functional audit (all routes, 3 viewports, 2 themes) | P1 | F/LiveAudit | — | PROD TESTED | F-01..F-09 fixed; production Playwright covers routes × viewports × themes |
| POST-10 | Scientific invariant regression suite | P1 | B/Science | — | PROD TESTED | 161 offline tests; live network test passes on retrievable live results |
| POST-11 | Percentage-point units for absolute deltas of % metrics | P2 | C/UXWorkflow + I | — | DEPLOYED | `delta_unit: "pp"` (API), UI "pp"; unit + hermetic e2e tests |
| POST-12 | Cosmetic: PGLib single-snapshot label shows PyPSA default `now` in replay | P3 | C | — | PROD TESTED (via G3-03) | Show "single period (no timestamp)" for networks without a time index |
| POST-13 | Transient mobile horizontal overflow seen once on `/library` cold load in CI (Linux, 390 px) | P3 | C | — | DOCUMENTED (closed) | Not reproducible locally or in the Linux Playwright image; header status pill made shrinkable + regression spec. The workflow has no schedule, so the "3 consecutive green scheduled runs" criterion became 3 consecutive green runs: 8 consecutive green `production-browser.yml` runs 2026-11-16…17 (latest 44009033246 on `f8b3c28`), plus 0/90 overflow checks in the 3.2 verification |

## Phase 0 — Research, audit, baseline

| ID | Task | Pri | Owner | Deps | Status | Acceptance criteria |
|---|---|---|---|---|---|---|
| P0-01 | Environment inspection (Python, Node, uv, Docker, Git, disk, gh/Vercel/Render auth) | P0 | I | — | VERIFIED | Python 3.11.9/3.13.1, Node 24.14.1, uv 0.11.32, Docker 29.9.2 (24 CPU), gh as tanmay-alpha, Vercel as tanmay-alpha (hobby), Render API key valid; Supabase env vars present but placeholders |
| P0-02 | Verify no existing GridStorm repo/folder | P0 | I | — | VERIFIED | `gh repo view tanmay-alpha/GridStorm` → not found; local folder empty |
| P0-03 | Interface contracts + architecture + ADR 0001 | P0 | I | — | VERIFIED | `docs/architecture/contracts.md`, `overview.md`, `docs/decisions/0001-*.md` exist |
| P0-04 | Upstream source inventory, SHAs, license audit, manifest | P0 | A | — | VERIFIED | 21 repos with pinned SHAs; manifest valid JSON; reused-file lists complete (commit `9b11299`). Open: psycopg-binary bundles libcrypt/libkeyutils without notices → optional mitigation: plain `psycopg` + system libpq |
| P0-05 | Dependency compatibility matrix with resolver evidence | P0 | A | — | VERIFIED | `compatibility-matrix.md` with real `uv pip compile` outcomes; isolated envs confirmed necessary |
| P0-06 | PyPSA-Explorer unchanged baseline (run app + tests) | P0 | B/ExplorerPort | — | VERIFIED | Upstream suite 105 passed / 3 skipped; `docs/audit/pypsa-explorer-baseline.md`; ADR 0002 keeps analytics, drops Dash runtime |
| P0-07 | Research papers matrix (5 papers) | P1 | D/Research | — | VERIFIED | `research-papers.md`: 8-column matrix + per-paper LaTeX equations for PyPSA, PyPSA-Eur, L2RPN, DemandCast, X-GridAgent; 27 links; full arXiv PDFs read |
| P0-08 | Tool decision matrix (PowerModels, PGLib, SimBench, ANDES, PyPSA-Earth, ORNL, GO) | P1 | D/Research | — | VERIFIED | `tool-decision-matrix.md`: PGLib data-only; ORNL/CoogGrid/NVIDIA/Grid2Game concepts-only; PowerModels/SimBench/ANDES/PyPSA-Earth/GOC3 deferred; GO Evaluation rejected (no licence) |
| P0-09 | External data sources licensing (OPSD, ENTSO-E, ERA5, NASA POWER, GEM, OSM, CEA, EIA) | P1 | D/Research | — | VERIFIED | `external-data-sources.md`: 10 sources checked 2026-11-14 (ERA5 CC BY 4.0 since 2025-07-02; EIA needs key (HTTP 403); CEA needs permission; ENTSO-E free re-use list appears to exclude actual load/generation) |
| P0-10 | Manually re-check ENTSO-E free re-use item numbers before any ingestion | P2 | D/EntsoeCheck → ObservedFix | P0-09 | VERIFIED | Actual load/generation not on CC BY list → demand now from day-ahead forecast (item #1, CC BY 4.0, attributed); renewables one MODELED daily multiplier; reconstruction test: actual load misses by ≥ 1 054 MW (old files: ≤ 2.5 MW); 38 tests (commit `9b7479f`) |
| P0-11 | "EENS" label only for probability-weighted scenario sets | P1 | B/StormRisk + C/Frontend | P2-08 | VERIFIED | StormRisk artifacts use `metric: "EENS"` only for weighted estimates; Run/Compare pages say "Unserved energy"; Studio test + live run page checked |

## Phase 1 — Functional foundation

| ID | Task | Pri | Owner | Deps | Status | Acceptance criteria |
|---|---|---|---|---|---|---|
| P1-01 | Public GitHub repo `tanmay-alpha/GridStorm` | P0 | I | P0-02 | VERIFIED | https://github.com/tanmay-alpha/GridStorm public; commit `ea921fc` pushed to `main` |
| P1-02 | canonical-grid schemas + network importers (ac-dc-meshed, scigrid-de, PGLib case14/118) | P0 | D/DataPipelines | P0-03 | VERIFIED | 4 networks validated (0 errors); DC balance case14 259 MW / case118 4242 MW, zero mismatch; network-import 20 + canonical-grid 17 tests pass (commits `866d985`, `309e9f7`) |
| P1-03 | Data catalog with provenance | P1 | D/DataPipelines | P1-02 | VERIFIED | `docs/research/data-catalog.md`; open caveat: original SciGRID release licence not recovered — PyPSA CC-BY grant + conservative ODbL obligations documented |
| P1-04 | PyPSA-Eur reduced Belgium network | P2 | B/PypsaEurBuilder | — | VERIFIED | Upstream build 58/58 rules in 912.6 s; 5 AC buses, 7 daily snapshots; validation 0 errors |
| P1-04b | Publish PyPSA-Eur BE build legally | P2 | I/EurLicence → EurPublish | P1-04 | DEPLOYED | ENTSO-E-derived load replaced by CC-BY-4.0 synthetic demand (Zenodo 10820928; 0/35 values equal old); ODbL-1.0 + attribution; LOPF optimal 49 392 841.28 EUR, peak 281 MiB → live-eligible. Live: `pypsa-eur-be-baseline` optimal 56 023 127.86 EUR = precomputed artifact (commit `63ae887`) |
| P1-05 | PyPSA-Explorer analytics port (`gridstorm_analytics`) | P1 | B/ExplorerPort | P0-06 | VERIFIED | 45 tests pass (commit `daa6f3e`); known gap: legacy demo CAPEX/OPEX differs from stored objective by ~2.3 %, cause unestablished |
| P1-06 | FastAPI API per contract §6 + OpenAPI | P0 | E/Backend | P0-03 | VERIFIED | 45 local tests pass, ruff clean; live `/api/v1/networks` lists 4 networks and `/api/v1/scenarios` lists 11 presets on Render |
| P1-07 | Postgres schema, Supabase migrations, RLS | P0 | E/Backend | P1-06 | VERIFIED | Migrations + RLS apply on postgres:16 (3 docker tests; 12 tables RLS-on, 15 policies); psql runbook in `docs/deployment/backend.md`; not yet applied to Supabase (P6-02) |
| P1-08 | Frontend shell + Grid Explorer map with real network data | P0 | C/Frontend | P1-02, P1-06 | DEPLOYED | https://gridstorm.vercel.app renders ac-dc-meshed from the live Render API (all API calls 200, 0 console errors); MapLibre worker-URL fix |

## Phase 2 — Crisis simulation

| ID | Task | Pri | Owner | Deps | Status | Acceptance criteria |
|---|---|---|---|---|---|---|
| P2-01 | StormSpec package (models, schema, hash, capabilities, validation, manifest) | P0 | B/ScienceCore | P0-03 | VERIFIED | 30 tests pass (commit `96f3f3a`); JSON schema exported; unsupported ops rejected |
| P2-02 | PyPSA adapter (`gridstorm_pypsa`) + CLI | P0 | B/ScienceCore | P2-01 | VERIFIED | 30 tests pass incl. balance residual, outage, demand scaling, storage SOC, infeasible, reproducibility |
| P2-03 | Preset scenarios with real asset ids + precomputed artifacts | P0 | B/ScienceCore | P1-02, P2-02 | VERIFIED | 11 presets solved with HiGHS → `data/artifacts/pypsa/`; peak RSS: scigrid-de 541–550 MiB (> Render 512 MB → precomputed only), small networks 277–280 MiB |
| P2-03b | Per-network live-execution policy (no live scigrid-de on 512 MB) | P0 | E/Backend + C/Frontend | P2-03 | VERIFIED | API: 422 `live_execution_unavailable` or labelled precomputed; Studio shows per-preset badges + verbatim 422; Playwright `studio-live-execution.spec.ts` passes |
| P2-04 | Simulation jobs: persistent queue, subprocess, timeout, cancel, recovery | P0 | E/Backend | P1-06, P2-02 | DEPLOYED | Live on Render: `ac-dc-meshed-dc-link-outage` → stages queued…done, HiGHS optimal, objective 131 950.19 EUR, wall 1.30 s, balance residual 0 MW. Known: SQLite ephemeral → jobs lost on redeploy (observed once) until Supabase |
| P2-05 | Baseline vs crisis comparison + reports | P1 | E/Backend | P2-04 | DEPLOYED | Live: comparison 201 (cost +3 271.61 EUR / +2.54 %, CO₂ +23.45 t); MD report 200, 6 948 chars, hash header matches. Minor: JSON says provenance `calculated`, MD says `modeled` |
| P2-06 | Crisis Studio + Simulation Dashboard UI | P0 | C/Frontend | P2-04 | DEPLOYED | Live browser: preset run on gridstorm.vercel.app → real stage timestamps queued→done, HiGHS optimal 1.29 s, metrics + charts; no % progress. Fixed snapshot-label timezone bug (regression test, TZ pinned) |
| P2-07 | Scientific specification document | P1 | B/ScienceCore | P2-02 | VERIFIED | `docs/architecture/scientific-spec.md` with equations, units, citations, measured memory limits |
| P2-08 | StormRisk: Monte Carlo outage sampling → EENS ± CI, LOLP, convergence | P1 | B/StormRisk | P2-02 | VERIFIED | ac-dc-meshed, seed-fixed: 1000 samples / 165 distinct solves, 0 infeasible; EENS 145.21 MWh (SE 35.76, 95 % CI 75.11–215.30), LOLP 0.087; outage rates MODELLED from IEEE RTS-96; 38 tests; scigrid-de not run |
| P2-09 | Observed-analogue scenarios (open ENTSO-E forecast → StormSpec events on scigrid-de) | P2 | D/ObservedFix | P1-02, P2-02 | VERIFIED | Re-solved optimal: unserved energy Dunkelflaute 2 721 / combined 4 731 / peak-load 4 429 MWh (were 3 237 / 20 500 / 5 648 using non-open actual data); validation passes |
| P2-10 | Distribution-grid AC time-series stress (SimBench LV/MV: heat wave, PV over-voltage, PV loss, mitigation) | P2 | B/SimBenchAC | — | VERIFIED | 9 studies, 672/672 steps converged; PV×1.5 → max 1.108 pu, 17 h over-voltage; 50 % cap → 8.25 h; Q(U) → 0 h but transformer up to 241 %; deterministic rerun; 10 tests; ruff clean |

## Phase 3 — Mapping and analytics

| ID | Task | Pri | Owner | Deps | Status | Acceptance criteria |
|---|---|---|---|---|---|---|
| P3-01 | Line-loading visualisation + time slider replay | P1 | C/Frontend | P2-06 | DEPLOYED | Live run page shows loading map + replay slider over 10 snapshots |
| P3-02 | Compare & Replay, report export | P1 | C/Frontend | P2-05 | VERIFIED | Playwright journey compares two runs and exports report (local backend) |
| P3-03 | Research Library (saved scenarios, jobs, datasets, manifests) | P2 | C/Frontend | P1-06 | VERIFIED | Playwright journey covers /library with real records |

## Phase 4 — Contingency and AC validation

| ID | Task | Pri | Owner | Deps | Status | Acceptance criteria |
|---|---|---|---|---|---|---|
| P4-01 | pandapower reference validation (case9–case300) | P1 | B/ACValidation | — | VERIFIED | 13 comparisons pass (max ΔVm 9.7e-11 pu, ΔVa 1.1e-8°, ΔP 8.8e-8 MW); only case9 vs MATPOWER stored solution is fully independent; fixed converter tap-side bug (case300 Ybus diff 4.6e-13) |
| P4-02 | N-1 engine with explicit classification + ranking | P1 | B/ACValidation | P1-02 | VERIFIED | AC-OPF bases match PGLib costs (2178.08 / 97213.61 / 565220.14 $/h); N-1: case14 20 (18 secure), case118 186 (56 secure, 119 thermal), case300 411 (18 non-convergent, classified); N-2 case14 10 pairs; 22 tests. Pin scipy<1.14 → pandapower 3.5.4 in this env only |
| P4-03 | Warden audit | P2 | B/CrisisAdvisor | — | VERIFIED | `docs/audit/warden-audit.md`; Warden suite reproduced 129 passed / 1 timing failure; competition claims kept as unverified |
| P4-04 | Crisis Response Advisor (deterministic, solver-verified) | P1 | B/CrisisAdvisor | P4-02 | VERIFIED | 5 PGLib crisis artifacts (3 with accepted recommendation, 2 honestly none accepted); 15 tests pass (commit `4fe25fb`) |
| P4-05 | Cross-engine check PyPSA LPF vs pandapower DC/AC PF on same PGLib case | P1 | B/CrossEngine | P1-02, P4-01 | VERIFIED | DC PF max abs diff 2.84e-13 MW (case14), 2.56e-12 MW (case118); AC-vs-DC linearisation 11.9 / 69.4 MW (expected); DC-OPF objective rel. diff ≤ 6.4e-11; `tests/cross_engine/run_all.py` 41.6 s; 10 harness tests pass (commit `49679ce`) |

## Phase 5 — Sequential operations and research

| ID | Task | Pri | Owner | Deps | Status | Acceptance criteria |
|---|---|---|---|---|---|---|
| P5-01 | Grid2Op episodes (≥ 3 agents × ≥ 2 chronics) + KPIs | P1 | B/Sequential | — | VERIFIED | 12 episodes (do_nothing/reco_powerline/greedy_simulate × 2 chronics × normal/line 1_3_3 outage), l2rpn_case14_sandbox, lightsim2grid; rerun trace hash identical (`050177c8…`); 20 tests pass; commit `c69a1dc` |
| P5-02 | Grid2Viz audit (MPL-2.0) and KPI concepts | P2 | B/Sequential | — | VERIFIED | `docs/audit/grid2viz-audit.md` (SHA `b416eba4`); KPIs re-implemented, no MPL code copied |
| P5-03 | StormBench PTDF/LODF screening vs DC/AC exact N-1 | P1 | B/StormBench | — | VERIFIED | 6 PGLib cases (14/30/57/118/300/1354-PEGASE); DC screening matches exact DC re-solve (max severity diff 2.4e-11 pp); metrics recomputed from per-contingency lists with 0 diffs; 17 tests; CI regeneration case14/30 matches at 1e-4 (commit `f91e96c`). Limits: AC ignores Q limits; full-case timings not re-measured |
| P5-04 | Operations replay + Benchmarks + Contingency + Methods UI pages | P1 | C/FrontendResearch | P4-02, P5-01, P5-03 | VERIFIED | `research.spec.ts` (Playwright) checks values against the same `data/artifacts` files; parser tests check CI = EENS ± 1.96·SE, class counts sum, ordering |
| P5-05 | ML contingency screening on simulator-derived labels vs DC-LODF/heuristic baselines | P3 | B/StormML | P5-03 | VERIFIED | 24 664 labelled outages from 158 AC-OPF operating points; within-network GB PR-AUC 0.973 vs DC-LODF 0.765 (mostly voltage violations DC cannot see); held-out case300 no reliable gain; calibration doesn't transfer; 15 tests. Labels are simulator-generated |
| P5-06 | User guide, engineering story, glossary, deployment docs | P1 | D/DocsWriter | all | VERIFIED | Commands/features checked against code (commit `130efd4`); Vercel URL to add |

## Phase 6 — Deployment and hardening

| ID | Task | Pri | Owner | Deps | Status | Acceptance criteria |
|---|---|---|---|---|---|---|
| P6-01 | Dockerfile, docker-compose, render.yaml | P0 | E/Backend | P1-06 | VERIFIED | Image builds on Render and serves `/health` (git_sha reported) |
| P6-02 | Supabase project (free plan via Vercel Marketplace) + migrations applied | P0 | I/E | P1-07 | DEPLOYED | `gridstorm-db` (eu-central-1, free) provisioned; migrations 0001–0002 applied (12 tables, RLS on all 12, 15 policies); 5 datasets seeded; Render `DATABASE_URL` = session pooler; live `/ready` → `postgres`; job `2d47898b` + metrics survived a Render restart |
| P6-03 | Render deployment (free web service, Docker, frankfurt) | P0 | I/E | P6-01 | DEPLOYED | https://gridstorm-api.onrender.com `/health` 200, `/ready` ready (database `sqlite-ephemeral`, highspy 1.16.0, pypsa 1.4.0, 4 datasets); cold start ≈ 28 s |
| P6-04 | Vercel deployment of apps/web | P0 | I/C | P1-08 | DEPLOYED | https://gridstorm.vercel.app (prebuilt deploy; Git auto-deploy not triggering — Vercel GitHub app likely not installed). Web: typecheck 0 errors, lint 0 errors, 72/72 unit, 8/8 Playwright (local) |
| P6-05 | Artifact storage (R2 if available, else local + committed artifacts) | P2 | E | P2-04 | VERIFIED (fallback) | No Cloudflare credentials → LocalFS store (`/tmp`, ephemeral on Render) + artifacts baked into image; S3/R2 adapter behind ArtifactStore interface. Render build filter set so doc-only pushes don't redeploy |
| P6-06 | GitHub Actions CI (lint, types, tests per env, web build, API smoke, actionlint) | P0 | E/CIDevOps | P1-06, P1-08 | VERIFIED | Run 43644788020 on `49ad242`: all jobs green (17 Python envs, web, e2e, api container smoke, gitleaks); actionlint clean; Trivy report-only |
| P6-07 | Independent verification (components, science spot checks, API black-box, live browser audit) | P0 | F/Verifier | all | VERIFIED | `docs/audit/verification-report.md`: 12 components VERIFIED, live integration 176 passed / 2 failed (real defects, since fixed in P6-09/P6-10) / 4 skipped; science recomputations match (unserved energy, balance, EENS CI, N-1 classes, Grid2Op hashes) |
| P6-08 | Security: secret scan, dependency audit (pip-audit, npm audit), container scan, authz tests | P1 | F/Verifier + E/CIDevOps | P6-01 | VERIFIED | gitleaks: 0 leaks (51 commits + bundles); CORS rejects foreign origins; 413 > 256 KiB; 10 path-traversal variants blocked; forged JWT 401; 429 + Retry-After. Prod CORS now excludes localhost (verified live). Job cap trial at 330 MB broke live jobs (memory_limit at loading_network) → reverted to 400 MB, live job `db70c183` optimal |
| P6-09 | Fix audit defects VER-006, 008, 009, 011, 012, 013, 014 | P1 | E+C/DefectFixer | P6-07 | DEPLOYED | Commit `e00d7d0`: each fix has a regression test that failed before. Live: HSTS + nosniff headers present, artifact kinds incl. timeseries/risk, case118 job created ≤ started ≤ finished, disclaimer footer visible at all widths |
| P6-10 | Root-cause VER-007 (API restart under live jobs; suspected OOM on 512 MB) | P1 | E/MemoryProbe → MemoryFix | P6-03 | DEPLOYED | Cause: pypsa imported in API (379–409 MB) + solver 348 MB > 512 MB. Fix (`c190e80`): precomputed analytics, solver oom_score_adj=1000, SIGKILL → `memory_limit`. Docker 512 MB: peak 350.7 MB, no OOM. Live: analytics `execution_mode: precomputed`; case118 live job optimal |
| P6-11 | Live accessibility (axe) + web performance (LCP/CLS, JS bytes, map load, API latency) | P2 | C/A11yPerf | P6-04 | VERIFIED | 0 critical axe violations; serious: contrast (#6b7686 at 4.1–4.2:1), TeX aria, link-in-text, target size; keyboard path to Run OK; LCP 0.46–1.1 s; /benchmarks CLS 0.33–0.52; run-page map crash 2/6 desktop loads |
| P6-12 | Fix a11y/perf findings (run-page map race, 404 state, CLS, contrast, ARIA, caching headers) | P1 | C+E/UIFixer | P6-11 | DEPLOYED | Live: /runs 5/5 loads no crash; "Job not found" page + titles; /benchmarks CLS 0.0002 (was 0.33–0.52); summary view 2.7 KB vs 1.24 MB; ETag + 304, HSTS + nosniff. Local axe: 0 violations on 11 routes; web 93 tests, API 86 |
| P2-11 | StormRisk Monte Carlo on scigrid-de (offline, reduced horizon) | P3 | B/RiskSciGrid | P2-08 | VERIFIED | 6 snapshots, 350 samples (all distinct, all feasible): EENS 400.68 MWh (SE 34.54, 95 % CI 332.97–468.38), LOLP 0.534; 22.8 min, peak 461.7 MiB → offline only; LOLP driven by modelled line rate 0.01 on 852 lines |
