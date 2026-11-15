# GridStorm independent verification report

> **Status 2026-11-15 (GridStorm 3.0 review): historical record of the first deployment.** The API no longer runs on ephemeral SQLite: production uses Supabase Postgres (P6-02) and Supabase Storage (POST-01). Statements about `sqlite-ephemeral` and `auth_not_configured` describe that earlier deployment only.

Verifier: Agent F (independent of every component owner). Defects with reproduction commands are in
[`issues.md`](issues.md). Black-box API tests are in [`tests/integration/`](../../tests/integration/).

**Live deployment under test**

| Surface | URL | Build seen |
|---|---|---|
| Web (Vercel) | https://gridstorm.vercel.app | `/assets/index-DBmpEuvw.js` |
| API (Render free, Frankfurt) | https://gridstorm-api.onrender.com | `/health` `git_sha` c8c6f21 (c2ef2ea before a 21:49 UTC redeploy) |

The API runs SQLite in ephemeral mode (`/ready` → `sqlite-ephemeral`). Jobs and saved scenarios vanish on
restart or redeploy, as documented. SciGRID-DE is precomputed-only on the live API. Supabase is not
provisioned (user action), so the API answers every `Authorization` header with `401
auth_not_configured`. Cross-user isolation therefore cannot be tested live.

Verdicts:
* **VERIFIED**: the component's claims were reproduced with independent code or re-runs.
* **ISSUES**: open S1/S2 defects (see `issues.md`).
* **NOT VERIFIABLE**: the component cannot be exercised from here.

All commands ran on Windows (x64), Python 3.11 via `uv`, `OMP/OPENBLAS_NUM_THREADS=1`. Verifier probe
scripts are in `D:/New folder (4)/_verifier_tmp/` (outside the repo).

## Round log

| Round | Time | Repo HEAD | Scope |
|---|---|---|---|
| 1 | 2026-11-14 ~21:00 IST | `ec541b2` | contracts, stormspec/API code review, integration test scaffold, secret scan |
| 2 | 2026-11-14 21:33–21:50 IST | `1e9282a` | test suites, independent physics re-solve, LODF check, Grid2Op re-run, references |
| 3 | 2026-11-15 (Verifier3) | local API | integration suite against a local API, benchmark evidence tests, local web e2e |
| 4 | 2026-11-14 21:40–22:30 UTC | `d441d31` (origin/main `49ad242`) | **live** API + web, science spot checks, security, gitleaks |

## Round 4 results

### 1. Integration tests against the live API

```bash
cd tests/integration && GRIDSTORM_API_URL=https://gridstorm-api.onrender.com \
  GRIDSTORM_TEST_ALLOWED_ORIGIN=https://gridstorm.vercel.app GRIDSTORM_LIVE_JOBS=1 uv run pytest -q
```

Final run (22:01–22:04 UTC): **176 passed, 2 failed, 4 skipped**.
* Failures, both real defects: `test_index_entries` (VER-008: artifact kinds outside contract) and
  `test_job_lifecycle_and_result` (VER-009: `created_at` later than `finished_at` on reused jobs).
* Skips:
  * Two by the hosting edge: Cloudflare WAF answered HTML 403 to `x' OR '1'='1` and
    `buses;DROP TABLE jobs` before they reached the API. The suite now skips these explicitly.
  * `test_cross_user_isolation`: needs the server JWT secret; auth is not configured live.
  * `test_post_rate_limit`: opt-in; run separately below and passed.
* Live jobs ran on ac-dc-meshed: lifecycle, physics recomputed from the returned series, identical-scenario
  reuse, cancel, comparison and reports. A single `ac-dc-meshed-baseline` job finished in 40 s with
  objective 128 678.57336 EUR, identical to the committed artifact.
* An earlier live run (21:52–21:56 UTC) crashed the instance: 502s, dropped connections, job list wiped,
  `worker_restart` requeue → **VER-007**.
* Offline tests (`test_offline_data.py`, `test_benchmark_evidence.py`, no API): **92 passed**.

Test-harness changes this round (`tests/integration/`):
* `conftest.py`: simulation POSTs that get 429 are retried after the server's `retry_after_s`
  (burst 3, 6/min), so the suite respects the live limiter instead of failing on it. Without this,
  the first run had 3 spurious 429 failures.
* `gs_helpers.py`: `skip_if_edge_blocked` (Cloudflare HTML 403/400 → skip with reason). `assert_job_shape`
  now accepts the documented `queued (reason: worker_restart)` requeue as a new monotonic segment.

### 2. Science spot checks (independent code on committed artifacts)

| Check | Method | Result |
|---|---|---|
| PyPSA unserved energy = Σ shed·Δt | `$VT/pypsa_balance.py` (stdlib only) on 4 artifacts | `scigrid-de-high-demand`: metric 446.659815 MWh vs Σ bus shed·Δt 446.6599 (4-dp rounding of rows); `scigrid-de-dunkelflaute-storage-on`: 190.215174 vs 190.2151; `pglib-case14-ieee-gen-1-outage`: 200.0 vs 200.0; `ac-dc-meshed-dc-link-outage`: 0 vs 0. Total load recomputes exactly in all four. |
| PyPSA power balance | Σ gen p + Σ storage p + Σ shed − link losses − load per snapshot (link efficiency 1.0 from canonical.json) | max residual 1.4e-3 MW (SciGRID, 586 generators × 4-dp rounding), 1e-4 MW (ac-dc-meshed), 0 (case14); generation never exceeds `available_mw`; `payload_sha256` recomputes for all 4 |
| PyPSA curtailment (VER-002 fix) | jq Σ(avail − p)·Δt over VRE units | 50 439.7623 vs 50 439.762022 MWh; 1 484.6423 vs 1 484.642288 MWh |
| StormRisk CI | `$VT/sr_ci.py`: expand `states` × `sample_state_index` (1000 samples), unbiased variance | EENS 145.2079 MWh (art. 145.208); SE 35.7634 (art. 35.7634); CI [75.112, 215.304] vs art. [75.113, 215.303]. The 1e-3 difference is z = 1.95996 vs 1.96. LOLP 0.087, SE_LOLP 0.008912, max 19 956.8 all match; state counts match the index histogram. |
| pandapower N-1 (case14) | `$VT/pp_n1.py`: own AC-OPF base (`pp.runopp`, ext_grid → slack gen), own MVA loading = max(\|S_from\|,\|S_to\|)/RATE_A, own islanding/limit classification; no GridStorm code | Own OPF cost 2178.08 (PGLib 2178.1, artifact 2178.08). branch-1: thermal_overload, 264.36 % on branch-2, vmin 0.9607 = artifact. branch-14: islanding bus 8, 64.84 %, vmin 1.0036 = artifact. branch-3: secure 80.58 % = artifact. branch-9 (trafo): secure 65.10 % = artifact. |
| Grid2Op determinism | recompute `trace_sha256` = sha256(canonical {steps, game_over}) and `payload_sha256` for all 12 artifacts and compare with `index.json`; re-run `case14-sandbox-c0-outage-1-3-3-greedy-simulate` from its recorded seeds (`$VT/g2o_rerun.py`) | 12/12 trace and payload hashes match file headers and index. Re-run trace `050177c8…6109` is identical; KPIs are identical. (The index carries a KPI subset by design.) |

### 3. Live browser audit (https://gridstorm.vercel.app)

Tooling: Playwright 1.65 Chromium, launched from `apps/web/node_modules` by scripts outside the repo:
`$VT/browser/audit.cjs` covers every route × {1440×900, 1024×768, 390×844}, console errors, page errors,
HTTP ≥ 400, the disclaimer, unit-less numbers, and click-every-control. `recheck.cjs` re-checks
routes, and `compare.cjs` runs the Compare flow end to end. Run window: 21:51–22:15 UTC.

| Route | 1440 | 1024 | 390 | Notes |
|---|---|---|---|---|
| `/` Grid Explorer | ok | ok | ok* | 10 controls clicked, all react |
| `/studio` Crisis Studio | ok | ok* | ok* | 16 controls clicked, all react |
| `/compare` Compare & Replay | ok | ok | ok | Picking baseline `57a7acec` and scenario `fc6c5fef` enables Compare. It creates comparison `2bbf0a5d` and renders deltas with units; total system cost 128 679 → 131 950 EUR matches the two PyPSA artifacts (128 678.57 / 131 950.19). |
| `/library` | ok | ok | ok | 60 of 116 controls clicked, all react |
| `/runs/:id` (job `3c9de5b6`) | ok | — | — | 20 controls clicked, all react |
| `/contingency`, `/operations`, `/benchmarks`, `/methods` | ok | ok | ok | |
| unknown route | "Page not found" | ok | ok | SPA 404 page, no error boundary |

"ok" means HTTP 200, the expected `<h1>`, no console errors, no page errors, and no failed requests.

\* The starred cells fell in the 21:54–21:56 UTC API outage (VER-007). `/` and `/studio` at 390 px logged
CORS-blocked fetches, because Render's 502 page carries no ACAO header. `/studio` at 1024 px did not load
within 90 s. A re-check at 22:07 UTC was clean on all three.

* **Dead buttons:** none. Every enabled control on Explorer, Studio, Run, and Library changed the DOM or
  URL, or issued a request. The click audit missed Compare because its only button is disabled until
  two runs are selected; the flow above exercised it instead.
* **Units:** no physical quantity without a unit. The flagged unit-less numbers are counts
  (contingencies, candidates, samples, pages), package versions, step indices, and KaTeX equation
  digits. Nit: VER-014.
* **Disclaimer:** visible on every route at 1440 px. Hidden at 1024 and 390 px except in the Methods body
  (VER-012).
* Crisis Studio lists anonymous saved scenarios to everyone (VER-013).

### 4. Security (live)

| Probe | Result |
|---|---|
| CORS, foreign origin | `Origin: https://evil.example` GET → no ACAO; preflight → 400 without ACAO. `gridstorm-evil.vercel.app`, `gridstorm.vercel.app.evil.com`, `null` → no ACAO. Allowed origin `https://gridstorm.vercel.app` → ACAO echoed, no credentials. Dev origin `http://localhost:5173` is also allowed (VER-010, S4). |
| Body size limit | 3 MB with Content-Length → 413 `payload_too_large` (`max_bytes` 262144); 3 MB chunked (no Content-Length) → 413; 300 KB → 413. |
| Path traversal `/api/v1/artifacts/{engine}/{id}` | `..%2F..%2Fetc%2Fpasswd`, `%2e%2e%2f…`, `..\..\`, `....//`, `PYPSA/…`, `…/..%2F..%2Fpyproject`, `pypsa/index` → 404 contract error; `%00` → Cloudflare 400. The suite's 7 traversal cases pass. No file content leaked. |
| Forged JWT | wrong-secret HS256, `alg: none`, garbage, expired → 401 `auth_not_configured` (auth not provisioned). Suite `test_forged_tokens_never_grant_identity` ×4 passes. Signature/claim validation was code-reviewed in round 1; it cannot be exercised live until Supabase exists. |
| Rate limit | `test_post_rate_limit` (GRIDSTORM_TEST_RATE_LIMIT=1) passed: 429 with `Retry-After` and contract error body. Simulation POST bucket observed `422 429 429 422 429` with `retry_after_s` in details. |
| Injection surfaces | 6 suite cases < 500. The SQL-like ones are blocked by Cloudflare WAF before the app. |
| Error leakage | malformed JSON → 4xx without traceback/site-packages/sqlalchemy strings |
| Secret scan | `docker run zricethezav/gitleaks:latest git /repo` → 51 commits, 28.5 MB, **no leaks**. `gitleaks dir` on `.vercel/output/static` and `apps/web/dist` (deployed bundle) → no leaks. No untracked non-ignored files. `.vercel/.env.production.local` (Vercel CLI build env) is git-ignored and not in history. |
| Transport headers | no HSTS / nosniff on the API (VER-011, S4) |

## Per-component verdicts

| Component | Verdict | Evidence (summary) |
|---|---|---|
| `packages/stormspec` | VERIFIED | VER-003 fixed (11 presets, preset test passes). Hash recompute verified in round 2; live `test_preset_hash_is_canonical` passes. |
| `packages/canonical-grid` | VERIFIED | Round 2: 16 passed. Offline consistency tests pass. |
| `packages/stormrisk` | VERIFIED | Independent EENS/SE/CI/LOLP recomputation matches (§2). VER-001 fixed. |
| `packages/stormbench` | VERIFIED | Round 2 LODF vs exact re-solve (≤1.5e-9 MW). Benchmark evidence tests pass; 7 results served live. |
| `packages/stormml` | NOT VERIFIABLE (this round) | Being regenerated by StormML4 during this round (uncommitted local changes, origin/main `c8c6f21`). Artifacts serve with valid hashes live. Claims were not re-derived. |
| `workers/pypsa` | VERIFIED (VER-006 S4 open) | UE/balance/curtailment recomputed on 4 artifacts; live job objective equals artifact; VER-002/VER-004 fixed. |
| `workers/pandapower` | VERIFIED | Independent case14 OPF + 4 N-1 contingencies reproduce classification, loading, islanding, vmin exactly. |
| `workers/grid2op` | VERIFIED | 12/12 trace and payload hashes match the index. A fresh re-run of `case14-sandbox-c0-outage-1-3-3-greedy-simulate` from recorded seeds reproduces the trace hash and KPIs. |
| `workers/advisor` | VERIFIED (code + test) | VER-005 fixed; regression test passes. Candidate quality was not re-derived. |
| `workers/distribution` | ISSUES (VER-008) | 9 artifacts serve with valid hashes, but `kind: timeseries` is outside the contract. Physics was not re-derived this round. |
| `data/artifacts/cross-engine` | VERIFIED (consistency) | `test_cross_engine_summary_matches_checks` passes offline. |
| `services/api` | ISSUES (VER-007, VER-008; VER-009/010/011/013 minor) | Live suite: 176 passed, 2 failed (VER-008, VER-009), 4 skipped. Security probes pass (§4). The instance restarted under live-job load (VER-007). |
| `services/analytics` | VERIFIED (live endpoints) | Live `analytics/{capacity,energy_balance,costs}` tests pass. Attribution headers present (round 2). |
| `pipelines/network-import` | VERIFIED | Offline manifest sha256 and canonical consistency: 92 offline tests pass. |
| `pipelines/observed` | NOT VERIFIABLE | Not exercised this round; no live surface. |
| `apps/web` (live) | ISSUES (VER-012 S3, VER-013 S3, VER-014 S4) | All routes load clean at 3 viewports, no dead controls, and Compare works end to end with correct numbers (§3). The safety disclaimer is hidden below 1280 px. |
| Supabase / auth | NOT VERIFIABLE | Not provisioned; the API reports `auth_not_configured`. |
| Secrets | VERIFIED clean | gitleaks: git history + built bundles, no leaks (§4). |
| `docs/research` | VERIFIED (references) | Round 2: 11 DOIs + 7 arXiv ids resolve to the cited works. |
