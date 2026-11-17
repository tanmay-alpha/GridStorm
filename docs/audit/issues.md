# GridStorm verification issue log

> Historical issue log (first deployment). The two entries still marked OPEN were resolved later: VER-007 by TODO P6-10 (API memory fix, `c190e80`) and VER-010 by TODO P6-08 (production CORS excludes localhost, verified live); see [TODO.md](../../TODO.md).

Maintained by the independent verifier (Agent F). Every entry has reproducible evidence.
Severity: **S1** blocks a claim/demo or is a security hole · **S2** wrong/misleading output or
contract deviation · **S3** quality/robustness · **S4** nit.
Status: OPEN · FIXED (verified by re-running the repro) · WONTFIX (owner rationale recorded) ·
OBSOLETE.

Paths are relative to the repository root; commands are run from the repository root in bash.
Verifier probe scripts live outside the repository in `D:/New folder (4)/_verifier_tmp/` (referred
to as `$VT`); their full source is reproduced in the details where they are short.

| ID | Sev | Component | Summary | Status |
|---|---|---|---|---|
| VER-001 | S1 | packages/stormrisk | Sampled transformer outages emitted as line outages; base outages excluded same-id assets of every component type | FIXED |
| VER-002 | S1 | workers/pypsa | Curtailment metrics count unused capacity of dispatchable (gas) generators whenever a generator event is applied | FIXED |
| VER-003 | S2 | packages/stormspec | No preset scenarios in `packages/stormspec/presets/`; own test `test_presets_parse_and_are_unique` fails | FIXED |
| VER-004 | S2 | workers/pypsa | No test suite (`workers/pypsa/tests/` empty) although TODO P2-02 acceptance requires outage/demand/storage tests | FIXED |
| VER-005 | S3 | workers/advisor | DC sensitivity failure silently yields zero candidates (no warning in the payload) | FIXED |
| VER-006 | S4 | workers/pypsa | `generation_cost_eur` also contains link/storage marginal costs; `solver.objective_eur` omits `objective_constant` while `total_system_cost_eur` includes it | FIXED |
| VER-007 | S2 | services/api (Render deploy) | Live API restarted while live jobs ran under the integration suite: 502s, dropped connections, job list wiped, one job requeued with `worker_restart` | OPEN |
| VER-008 | S2 | data/artifacts, services/api | Artifact `kind` values `timeseries` (distribution) and `risk` (stormrisk) are outside the contract §5 enum | FIXED |
| VER-009 | S4 | services/api | Reused/precomputed jobs report `created_at` later than `started_at`/`finished_at` | FIXED |
| VER-010 | S4 | render.yaml | Production CORS allow-list includes the dev origin `http://localhost:5173` | OPEN |
| VER-011 | S4 | services/api (deploy) | API responses carry no `Strict-Transport-Security` / `X-Content-Type-Options` headers | FIXED |
| VER-012 | S3 | apps/web | "Not a real-time control system" disclaimer is hidden below 1280 px wide (only `xl:inline` in the header) | FIXED |
| VER-013 | S3 | services/api, apps/web | Anonymous `POST /api/v1/scenarios` saves are listed to every visitor in Crisis Studio (owner `null`); test/junk scenarios appear in the public list | FIXED |
| VER-014 | S4 | apps/web | Compare table label shows the unit twice: "Unserved energy (MWh) [MWh]" | FIXED |

## Details

### VER-001 — stormrisk: component lost for colliding ids (S1, FIXED)

Contract §3: asset ids are unique only per component type; `line_outage.component` selects
`line | transformer`. `stormrisk.sampling.state_scenario` emitted every `line_outage` without
`component` (→ default `line`), and `_base_outaged_assets` keyed outages by `asset_id` only.

Repro (`$VT/sr_probe.py`: toy network with line `5`, transformer `5`, generator `5`; base scenario
outages transformer `5`; sampling classes for lines, generators, and transformers):

```bash
cd packages/stormrisk && uv run python "D:/New folder (4)/_verifier_tmp/sr_probe.py"
```

Before the fix: `population: []`, `excluded_base_outaged=('5',)` (line 5 and generator 5 wrongly
dropped) and `transformer sample -> [{'type': 'line_outage', 'asset_id': '5', 'component': 'line'}]`
(a transformer outage silently applied to the line with the same id).

Fix (StormRisk owner): `PopulationAsset.event()` emits `component`; base outages keyed by
`(component, asset_id)`; regression test `tests/test_study.py::test_ids_colliding_across_components`.
Re-verified: probe now prints `population: [('generator', '5'), ('line', '5')]`,
`excluded_base_outaged=()`, and `component: 'transformer'`; `uv run pytest -q` → `28 passed`.

### VER-002 — pypsa: curtailment includes dispatchable generators (S1, FIXED)

`gridstorm_pypsa.runner.variable_generators(n)` returns the columns of `n.generators_t.p_max_pu`.
`_apply_events` replaces that frame with the dense frame of **all** generators whenever a
`generator_outage`, `renewable_availability_multiplier`, or `curtailment: false` is applied, so after
the solve every gas unit is "variable" and `curtailment_mwh`, `curtailment_by_carrier_mwh`, and
`series.curtailment_mw` count unused gas capacity.

Repro (`$VT/pypsa/stress.json`: ac-dc-meshed, demand ×1.6, wind ×0.3 on [2,8), line `0` out,
`Manchester Gas` out on [3,7), load shedding on):

```bash
cd workers/pypsa && uv run python -m gridstorm_pypsa run \
  --scenario "D:/New folder (4)/_verifier_tmp/pypsa/stress.json" \
  --network-dir ../../data/networks/ac-dc-meshed --out /tmp/stress.result.json
jq -c '.series.curtailment_mw, [.assets.generators[] | select(.carrier=="wind") | .available_mw]' /tmp/stress.result.json
```

Observed: `curtailment_mw` = `[145166, 143800, 147320, 94844, …]` MW. The wind farms only have ~6–97 MW
each available per snapshot. 145 166 = 150 000 MW gas `p_nom` (50 000 + 20 000 + 80 000) − 4 835 MW gas
dispatch at t=0. `curtailment_mwh` = 1 251 614 MWh, which is 24× the 52 076 MWh total load. The same
network with no events (`$VT/pypsa/base.json`) reports curtailment 0.

Suggested fix: determine the variable-generator set once from the unmodified network, or from canonical
`is_variable`, before `_apply_events`. Carry it in `_Applied` and use it in `_generation_metrics`. Add a
regression test that applies a generator outage and asserts curtailment ≤ Σ available wind/solar −
dispatched wind/solar.

Everything else checked on the same result passes:
* An independent plain-PyPSA re-solve (`$VT/pypsa/indep.py`, no GridStorm code) gives objective
  28 477 328.814 EUR. The runner gives 28 477 328.8135 EUR.
* Unserved energy is 2 826.8713 MWh in both, and the shed series is identical.
* Σ shed·Δt = metric; Σ bus shed = metric; generation ≤ available (max excess 0).
* The outaged generator has p = 0 inside its window; `balance_residual_max_mw` = 0.
* `max_line_loading_pct` matches recomputation from asset rows.
* Partial-window line outage (`$VT/pypsa/partial.json`) is rejected with `unsupported_operation`.

Fix verified (round 4, HEAD `d441d31`): `runner.py` captures `variable_generators(n)` before
`_apply_events` (`applied.variable_generators`) and uses it in the metrics. Regression test
`workers/pypsa/tests/test_runner.py::test_curtailment_counts_only_variable_generators` passes
(`uv run pytest -q -k "curtailment or unserved or balance"` → 3 passed). On the committed artifacts,
`curtailment_by_carrier_mwh` only has Solar/Wind carriers. An independent jq recomputation of
Σ(available − p)·Δt over wind/solar units gives 50 439.7623 MWh for `scigrid-de-high-demand`
(metric 50 439.762022) and 1 484.6423 MWh for `scigrid-de-wind-lull` (metric 1 484.642288).

### VER-003 — stormspec: presets missing (S2, FIXED)

```bash
cd packages/stormspec && uv run pytest -q
```
→ `FAILED tests/test_stormspec.py::test_presets_parse_and_are_unique - assert 0 >= 4` (29 passed,
1 failed). `packages/stormspec/presets/` is empty; contract §3 and TODO P2-03 require ≥ 4 presets that
reference real asset ids. This blocks the API preset/job integration tests (`acdc_preset` fixture).

Fix verified (round 4): 11 presets exist in `packages/stormspec/presets/`.
`uv run pytest -q -k presets` → 1 passed. The offline integration test
`test_presets_reference_real_assets` passes for all 11 presets.

### VER-004 — pypsa worker without tests (S2, FIXED)

`ls workers/pypsa/tests` → empty. Nothing guards the claims in TODO P2-02 (balance residual,
outage/demand/storage). VER-002 would have been caught by a single generator-outage test.

Fix verified (round 4): `workers/pypsa/tests/test_runner.py` (17 tests: balance residual, generator
bounds, demand multiplier, line/link outage, unserved-energy formula, curtailment, storage SoC
recursion, CLI) and `test_presets.py`. A subset was re-run (see VER-002); the full suite was not
re-run in this round.

### VER-005 — advisor: silent empty candidate set (S3, FIXED)

`workers/advisor/src/gridstorm_advisor/sensitivity.py::compute` returns `None` on any `pp.rundcpp`
exception (`except Exception: return None`). `advisor.py` (around line 379) then skips all candidate
generation (`if sens is not None:`), adds no warning, and the payload reads as if no remedial action
existed. Check: `grep -n "sens is None\|warnings" workers/advisor/src/gridstorm_advisor/advisor.py` →
no handling. Suggested fix: record a warning/status such as `dc_sensitivity_failed` with the
exception type in the payload, and add a test.

Fix verified (round 4): `advisor.py` writes `payload.candidate_generation = {status: ok|unavailable,
warnings: [...]}`. `uv run pytest -q -k sensitivity_failure` (workers/advisor) → 1 passed
(`test_sensitivity_failure_is_explicit` asserts `status == "unavailable"` and the warning text).

### VER-006 — pypsa: cost labels (S4, FIXED)

`runner.py` `_postprocess`: `generation_cost_eur = objective - shed_cost`, which also includes
link/storage marginal costs. `solver.objective_eur = n.objective`, while `total_system_cost_eur =
n.objective + n.objective_constant`. On ac-dc-meshed both are equal (the constant is 0 after fixing
capacities), but the definitions differ. Suggested fix: rename or document the field as "operating cost
excluding load shedding" and use one objective definition.

Round 4: unchanged. `runner.py:552` (`objective = n.objective + objective_constant`), `:608`
(`generation_cost_eur = objective − shed_cost`), `:827` (`solver.objective_eur = n.objective`).

Fix (round 5, local; not yet deployed): `runner.py::objective_eur(n)` (= `n.objective +
objective_constant`) is now the single definition used for both `solver.objective_eur` and
`metrics.total_system_cost_eur`. Committed artifact numbers are unchanged: in all 11
`data/artifacts/pypsa/*.json`, `solver.objective_eur == metrics.total_system_cost_eur` already held
(the constant is 0 because capacities are fixed), so nothing was regenerated. The field
`generation_cost_eur` keeps its contract name (§4). Its meaning, objective − load-shedding cost
including link/storage operating terms, is already documented in `docs/architecture/scientific-spec.md:49`
and `docs/user-guide.md:218`. The Run page metric card now carries the hint "total system cost −
load-shedding cost". Tests (workers/pypsa): `test_objective_includes_objective_constant` (stub
network, 10 + 2.5 → 12.5; fails before because the helper did not exist) and
`test_reproducible_objective_and_result_hash`, which now also asserts `solver.objective_eur ==
metrics.total_system_cost_eur`.

### VER-007 — live API restarts during live jobs on Render free (S2, OPEN)

Target: https://gridstorm-api.onrender.com (`plan: free`, 512 MB). `render.yaml` sets
`GRIDSTORM_JOB_MEMORY_MB=400`, `GRIDSTORM_MAX_CONCURRENT_JOBS=1`, and live networks
ac-dc-meshed/case14/case118.

Repro (round 4, 2026-11-14 21:52–21:56 UTC, `git_sha` c8c6f21 throughout):

```bash
cd tests/integration && GRIDSTORM_API_URL=https://gridstorm-api.onrender.com \
  GRIDSTORM_TEST_ALLOWED_ORIGIN=https://gridstorm.vercel.app GRIDSTORM_LIVE_JOBS=1 uv run pytest -q
```

Observed in that run: `httpx.RemoteProtocolError: Server disconnected without sending a response`.
`POST /api/v1/simulations` and `POST /api/v1/comparisons` → **502 Bad Gateway** (Render error page).
`GET /health` → 502 at 21:55:36 and 200 again at 21:55:52 with the **same** `git_sha`, so this was not
a redeploy. Jobs submitted earlier in the run were gone afterwards (`GET /api/v1/simulations` →
`total: 1`). The remaining job `3c9de5b6` has the stage history
`queued → loading_network → queued (reason: worker_restart) → … → done`.

The outage was user-visible. The live browser audit, running at the same time, logged on `/` and
`/studio` (390 px pass): "Access to fetch at 'https://gridstorm-api.onrender.com/health' … blocked by
CORS policy: No 'Access-Control-Allow-Origin' header". Render's 502 page carries no ACAO header, so the
browser reports the outage as a CORS failure. `/studio` at 1024 px did not finish loading within 90 s.
A re-check of the same routes at 22:07 UTC was clean (no console errors, no failed requests).

Not reproduced on a single job: one `ac-dc-meshed-baseline` job at 21:57 completed in 40 s, and its
objective of 128 678.57336 EUR equals the committed artifact. A second full live run (22:01–22:04 UTC)
also passed without a restart. So the failure is intermittent under suite load. A suite run means
sequential jobs, a cancel test with queued jobs, and all 53 artifacts downloaded.

[INFERENCE] The likely cause is container OOM. The 400 MB per-job cap plus the API process can
exceed Render's 512 MB, and the container is then killed before the worker's own memory watchdog
fires. Owner action: read the Render service events/metrics for 21:54–21:56 UTC. If OOM is
confirmed, lower `GRIDSTORM_JOB_MEMORY_MB` to fit inside 512 MB together with the API RSS.

### VER-008 — artifact kinds outside the contract (S2, FIXED)

Contract §5 (`docs/architecture/contracts.md:189`) fixes
`kind: n_minus_1|advisor|episode|benchmark|simulation`. The committed indexes and the live API use
`timeseries` (`data/artifacts/distribution/index.json`, 9 artifacts) and `risk`
(`data/artifacts/stormrisk/index.json`).

```bash
curl -s "https://gridstorm-api.onrender.com/api/v1/artifacts?limit=100" | jq -c '[.items[].kind]|unique'
```
→ `["advisor","benchmark","episode","n_minus_1","risk","simulation","timeseries"]`. The integration test
`test_artifacts.py::test_index_entries` fails for this reason. Fix: either extend the contract enum
(and the API docs), or map these artifacts to existing kinds.

Fix (round 5, local; not yet deployed): contract §5 now lists
`n_minus_1|advisor|episode|benchmark|simulation|timeseries|risk`. The API has one enum,
`schemas.ArtifactKind`, used by three things. `PrecomputedArtifact.kind` takes it as the response
type. `GET /api/v1/artifacts?kind=` uses it to validate the parameter, so an unknown kind now
returns 422 where it used to return 200 with an empty list. `PrecomputedArtifacts` uses it through
`ARTIFACT_KINDS` and skips index entries with an unknown kind, logging an error. The web
`ArtifactKind` type was extended to match. Test:
`services/api/tests/test_comparisons_artifacts.py::test_artifact_kinds_match_contract_and_committed_data`
parses contract §5 and compares it with the API enum. It also checks that every committed
`data/artifacts/*/index.json` kind is accepted and that all committed entries are served. Pre-fix
it fails on import (no enum). `test_precomputed_artifact_index_and_documents` asserts the 422.
Remaining: `tests/integration/test_artifacts.py` still hard-codes the old five-kind `KINDS` set.
That file was outside this fix's scope and must add `timeseries` and `risk`.

### VER-009 — reused job timestamps out of order (S4, FIXED)

`services/api/src/gridstorm_api/jobs/service.py::_complete_from` (and `_complete_precomputed`) set
`job.started_at = job.finished_at = utcnow()` before the INSERT flush. `created_at` comes from the
column default (`db/models.py:96`, `default=utcnow`), which is evaluated at flush time, so it is later.
Live evidence: job `6cd6355c` has `created_at 21:58:44.946175Z`, `started_at = finished_at
21:58:44.945414Z`. The second run gave `22:03:49.007430Z` vs `22:03:49.007159Z`. Failing test:
`test_simulations.py::test_job_lifecycle_and_result` (`finished_at >= created_at`). Fix: set
`created_at` explicitly when the job object is created, or take `now` after the flush.

Fix (round 5, local; not yet deployed): `jobs/service.py::_new_job` sets `created_at`,
`updated_at` and the `queued` stage event from one explicit `utcnow()`. It no longer relies on the
column default evaluated at flush time, so `created_at <= started_at <= finished_at` also holds for
reused and precomputed completions. Tests: `services/api/tests/test_jobs.py::test_reused_job_timestamps_are_ordered`
(new) and an added assertion in `test_precomputed_mode`. Both failed before the fix, e.g.
`created_at …56.304774` > `started_at …56.303135`, and both pass after it.

### VER-010 — dev origin in production CORS (S4, OPEN)

`render.yaml` sets `GRIDSTORM_CORS_ORIGINS=…,http://localhost:5173`.
`curl -s -D - -o /dev/null -H "Origin: http://localhost:5173" https://gridstorm-api.onrender.com/api/v1/networks`
→ `access-control-allow-origin: http://localhost:5173`. Credentials are not allowed (no
`Access-Control-Allow-Credentials`), and the API is anonymous, so the impact is low. Foreign origins
(`https://evil.example`, `https://gridstorm-evil.vercel.app`, `https://gridstorm.vercel.app.evil.com`,
`null`) correctly receive no ACAO, and their preflight gets 400.

### VER-011 — no transport-security headers on the API (S4, FIXED)

`curl -s -D - -o /dev/null https://gridstorm-api.onrender.com/health` shows no
`Strict-Transport-Security`, `X-Content-Type-Options`, or `X-Frame-Options`. The API serves only JSON, and
Render/Cloudflare enforce HTTPS, so this is defence-in-depth only.

Fix (round 5, local; not yet deployed): new `security_headers.py::SecurityHeadersMiddleware` is the
outermost middleware. Every HTTP response, including errors and 413s, gets `X-Content-Type-Options:
nosniff`, `Referrer-Policy: no-referrer` and `X-Frame-Options: DENY`.
`Strict-Transport-Security: max-age=31536000; includeSubDomains` is added only for HTTPS
requests: the ASGI scheme is `https`, or `GRIDSTORM_TRUST_PROXY=true` (set in the Dockerfile) and
the first `X-Forwarded-Proto` hop is `https`. Test:
`services/api/tests/test_networks.py::test_security_headers` covers plain HTTP, HTTPS, a spoofed
`X-Forwarded-Proto` without trusted-proxy mode, and a trusted proxy. Pre-fix it fails with
`KeyError: 'x-content-type-options'`.

### VER-012 — safety disclaimer hidden on narrower screens (S3, FIXED)

`apps/web/src/components/layout/AppLayout.tsx:111`:
`<span className="hidden … xl:inline">Research tool · not a real-time control system</span>`.
In the live audit (`$VT/browser/audit.cjs`, `$VT/browser/recheck.cjs`, Playwright Chromium against
https://gridstorm.vercel.app), the disclaimer was visible on all 10 routes at 1440×900. At 1024×768
and 390×844 it was not visible on any route except `/methods`, whose body carries its own "Not a
real-time control system." paragraph. Common laptop widths (1024–1279 px) and every phone therefore
never see it on Explorer/Studio/Run/Compare. Fix: keep a short form visible at all breakpoints, for
example in the mobile menu or a footer line.

Fix (round 5, local; not yet deployed): the header span is gone. `AppLayout` now renders a one-line
`<footer data-testid="safety-disclaimer">Research tool · not a real-time control system</footer>`
below `<main>`, with no breakpoint classes, so it shows at every width and on every route. Test:
`apps/web/src/components/layout/AppLayout.test.tsx` asserts that exactly one disclaimer exists and
that neither it nor any ancestor has the Tailwind `hidden` class. Pre-fix it fails. No real-browser
check at 390/1024 px has been run yet.

### VER-013 — anonymous saved scenarios are public (S3, FIXED)

With auth not configured (live), `POST /api/v1/scenarios` stores scenarios with `owner_id: null`, and
`GET /api/v1/scenarios` returns them to everyone. Crisis Studio lists them next to the presets:

```bash
curl -s "https://gridstorm-api.onrender.com/api/v1/scenarios?limit=100" | jq -c '[.items[]|select(.preset|not)|{name,owner_id}]'
```
→ 4 entries, including "Integration test copy" ×2 written by `tests/integration` (they vanish on
the next restart because SQLite is ephemeral). `docs/deployment/supabase.md:97` only says anonymous
users can "read public data and run demo jobs"; it does not document public anonymous saves. Fix:
document this, or keep anonymous saves client-side, or hide `owner_id: null` non-presets from the list.
The POST rate limit (20 burst, 60/min) bounds the spam rate.

Fix (round 5, local; not yet deployed): `GET /api/v1/scenarios` now lists only presets plus the
caller's own saves (`owner_id == caller`). Anonymous saves and other users' public saves are no
longer listed. Public records stay readable via `GET /api/v1/scenarios/{id}`. `ScenarioRecord`
gains `listed: bool`, which is `false` for anonymous saves. Crisis Studio opens `?preset=<id>` by
id when the record is not in the list. After an unlisted save it says "Unlisted: … reopen it via
this link". Tests: `services/api/tests/test_scenarios_auth.py::test_save_scenario_anonymous_is_unlisted`
and `::test_public_saves_are_listed_to_their_owner_only` (both fail before the fix), and
`apps/web/src/features/studio/StudioPage.test.tsx` › "Unlisted (anonymous) saved scenarios" (2 tests,
both fail before the fix). `docs/architecture/backend.md:43` still says "anonymous saved records are
public". They are still public by id, but no longer listed, and that doc was outside this fix's
scope.

### VER-014 — duplicated unit in Compare (S4, FIXED)

`apps/web/src/features/compare/ComparePage.tsx:39` hard-codes the label `'Unserved energy (MWh)'`,
and the table appends `[MWh]`. Live Compare (baseline `57a7acec` vs `fc6c5fef`) renders
"Unserved energy (MWh) [MWh]". Every other row reads "Name [unit]".

Fix (round 5, local; not yet deployed): the hard-coded label is gone. Rows use
`compare.ts::metricLabel(metric, unit)`, which gives "Name [unit]" with the unit suffix stripped
from the field name, e.g. "Unserved energy [MWh]". Test: `apps/web/src/features/compare/compare.test.ts`.
