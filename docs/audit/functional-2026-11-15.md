# Functional production audit — 2026-11-15

> **Status 2026-11-15 (GridStorm 3.0 review): historical, before-recovery record.** Findings F-01..F-09 were fixed and verified in production (TODO POST-09); see [TODO.md](../../TODO.md) for the current state.

## Target and evidence boundaries

Audited the actual public deployment at https://gridstorm.vercel.app against https://gridstorm-api.onrender.com, not the recovery branch or a local preview. Browser evidence is in [2026-11-15-before](screenshots/2026-11-15-before/). These are **before-recovery** observations; source changes by other workstreams are not proof of deployed remediation.

The visitor journey covers Explorer, Studio, Run, Compare, Library, Contingency, Operations, Benchmarks and Methods. Initial route sweeps used fresh pages at 1440×900, 768×1024 and 390×844, each in light and dark themes: 54 screenshots and corresponding `requests-{desktop,tablet,mobile}.json` records. Every initial route had zero document horizontal overflow and zero uncaught JavaScript errors. A rendered page is not, by itself, evidence that its underlying calculations or every interaction passed.

Exactly two live IEEE-14 jobs were created with `reuse=false` (no further live solves):

| Case | Job | Outcome | Solver termination | Objective EUR | Unserved MWh |
| --- | --- | --- | --- | ---: | ---: |
| Baseline | `0137980b-a106-49ed-a292-7fa1bacf7813` | feasible | optimal | 2051.526309 | 0 |
| Generator 1 outage | `06b4f635-4eb8-4d34-99ca-362d53b88e6c` | feasible | optimal | 2001372.900146 | 200 |

Both completed with recorded worker stages and retrievable full results during this session. This establishes immediate retrieval, **not persistence across a restart**. Both have one snapshot weighted at 1 h; baseline demand/served energy is 259/259 MWh, outage demand/served energy 259/59 MWh. The outage's feasible/optimal labels do not imply safe operation: 200 MWh is shed at VOLL 10,000 EUR/MWh, yielding shedding cost 2,000,000 EUR. Downloaded results, manifests and JSON/Markdown reports are retained beside the screenshots.

## Findings

| ID | Severity | Route | Reproduction | Expected | Actual before recovery | Owner |
| --- | --- | --- | --- | --- | --- | --- |
| F-01 | P0 | `/runs/2d47898b-8546-420e-a382-acc29f14d3d4` | Open the historic completed baseline; request its `/result` | Completed result remains retrievable, or explicit unavailable-artifact state with recovery action | `/result` HTTP 500 `artifact_missing`; result/manifest buttons disabled; numerical area remains an indefinite skeleton | Storage / UXWorkflow |
| F-02 | P1 | Same Run route | Observe completed/feasible/live badges alongside missing details | Clearly distinguish metadata, solver outcome and unavailable numerical evidence | Header says completed/feasible but gives no visible explanation of missing detail in the captured page | UXWorkflow |
| F-03 | P2 | Explorer, mobile | Load `/` at 390×844, dark theme | One compact map attribution control | Duplicate attribution text blocks cover the bottom portion of the map | UXShell |
| F-04 | P2 | Explorer, dark | Load Explorer in dark theme; inspect console | All referenced style images resolve | MapLibre warns `Image "circle-11" could not be loaded` at all three audited viewport sizes | UXShell |
| F-05 | P2 | Explorer | Fresh load of default AC/DC network | Avoid redundant heavy asset fan-out before first useful map | 12 API requests during the initial route sweep, including asset loading | UXShell |
| F-06 | P2 | `/compare?comparison=4f5661ec-e6f1-4600-96ed-710709f10c36` | Compare loading 60.656764% → 8.827726% | Absolute loading difference labelled −51.83 percentage points; relative difference −85.45% | Absolute delta displayed −51.83%, conflating percent with percentage points | Science / UXWorkflow |
| F-07 | P1 | `/studio?preset=pglib-case14-ieee-baseline` | Clear the VOLL number input | Invalid-input feedback; application stays usable | React error #301 (render loop); validation/run controls disappear | UXShell shared NumberField / UXWorkflow regression |
| F-08 | P1 | `/studio?preset=scigrid-de-baseline` | Add demand multiplier 1.2; wait for validation; click Run | Disable submission before any simulation POST when no exact precomputed result exists | Forecast predicts server refusal, but Run remains enabled and attempts POST; audit blocked the request | UXWorkflow |
| F-09 | P2 | Explorer | Ctrl+K → search `load-3` on IEEE-14 → select result → Escape → wait 500 ms | Escape dismisses asset details | Drawer remains visible; explicit Close works | UXShell |

F-01/F-02 were reported to Storage and UXWorkflow by the original audit worker; the continuation reported F-03/F-04/F-09 to UXShell, F-06 to Science, and F-07/F-08 to UXWorkflow. GPU `ReadPixels` warnings in headless Chromium are recorded as rendering-environment warnings, not claimed as application failures. Scientific text containing “error” on Operations/Benchmarks refers to model diagnostics; a text match is not classified as an HTTP or JavaScript error.

## Initial-route request observations

Counts include initial navigation and a short settling window, not an interaction-wide performance budget. Independent pages were opened in shared per-theme browser contexts; cache effects are possible. JSON records preserve exact route/theme counts, timing, console warnings and failures.

| Route | API requests per initial page | Total requests, desktop light | Failed HTTP requests |
| --- | ---: | ---: | --- |
| Explorer | 12 | 35 | none |
| Studio | 15 | 23 | none |
| Historic missing-artifact Run | 5 | 18 | result GET 500 |
| Compare, empty selection | 2 | 14 | none |
| Library | 5 | 13 | none |
| Contingency | 6 | 15 | none |
| Operations | 5 | 14 | none |
| Benchmarks | 23 | 32 | none |
| Methods | 15 | 29 | none |

These API counts were identical across all six initial viewport/theme combinations. Explorer total requests were 35/33 (desktop light/dark), 35/33 (tablet), 36/34 (mobile). Only the missing-artifact route produced an HTTP failure and console error in the initial sweeps.

## Production regression coverage

`cd apps/web && npx playwright test -c playwright.production.config.ts` ran against the public URLs: **9 passed, 1 failed, 1.1 minutes**. The failure is intentional evidence of an unresolved production defect, not an expected-failure annotation: the completed historic job's result returned 500 instead of 200. No existing assertions were removed or weakened.

The suite now checks all five catalog networks and rendered map features, baseline Studio validation, mobile navigation, research-route labels/overflow in all six viewport/theme combinations, and result availability for recent completed jobs plus the historic lost-artifact job. Persistent API mutations are blocked and asserted absent; the pure `/scenarios/validate` POST remains allowed. Artifact checks verify schema and SHA256 metadata/bytes. Final additions after the recorded run include the byte-digest assertion, explicit HTTP 410 recovery contract, durability environment input, edited-SciGRID pre-submit regression, and navigation through the recovery Studio wizard; Main must execute final verification on the merged deployment.

The Python public probe now requires all five networks, exactly 14 IEEE-14 buses, at least one completed job, and verified availability for recent completed results plus the known historic job rather than letting a fresh good run hide an older broken one. It was not rerun merely to reconfirm the already-established historical failure.

The browser workflow retains nested traces/screenshots rather than only top-level PNG files. The new read-only readiness keepalive runs at 08:17 UTC every third day-of-month and manually on demand, checks `/ready` plus Postgres identity, and uses no credentials. Calendar cron has shorter gaps across some month boundaries. It can exercise the Supabase connection but cannot guarantee that Supabase or GitHub will never pause/delay a service.

The final probe contract accepts only SHA256-verified bytes or an explicit `result_available=false` plus HTTP 410 `artifact_unavailable`; it does not accept a generic 500 or silently omit lost jobs. The historic `2d47898b…` is checked explicitly even when newer results exist. At least one actual result must remain available. Recomputed jobs use their newly recorded digest and must preserve `recomputed_from_job_id` in stage provenance; no historical digest is hard-coded.

For the post-deployment restart acceptance, Main supplies a completed **post-deploy** job through `GRIDSTORM_DURABLE_JOB_ID` to either command, before and after a controlled API restart. That particular job must be available and its returned bytes must match its recorded SHA256; the missing-artifact exception is not allowed for it. Both workflow-dispatch forms expose `durable_job_id`. These read-only checks neither perform the restart nor prove when a supplied job was created. Final source also migrates the mobile navigation assertion to the recovery shell's `Simulate` label.

## Advanced user results

- Opened both new live Run pages and downloaded full result JSON, manifest, report JSON and report Markdown for each. Full-page screenshots preserve metrics, units, charts and status/solver panels.
- Created comparison `4f5661ec-e6f1-4600-96ed-710709f10c36` from the two live jobs; the shared URL and JSON/Markdown exports worked. Checked every numeric absolute delta against scenario minus baseline with `math.isclose`; all passed. Unserved energy is 0 → 200 MWh (delta +200 MWh), with undefined percentage displayed as `—`, not infinity or a fabricated zero. System cost delta is +1,999,321.373837 EUR. Loading-unit ambiguity is separately recorded as F-06.
- Opened SciGRID baseline as **precomputed**, job `c800561d-20d4-4407-af6c-f2d774986a4a` (no third live solve). A real cross-network comparison request against IEEE-14 returned HTTP 422 `network_mismatch`, with the two network identifiers.
- Advanced research controls: changed Contingency network/study selections, Operations chronic/agent selections and replay slider, and the Benchmark selector. No HTTP failures or uncaught JS errors occurred in the comparison/research interaction record (`results-audit.json`, 129 requests across those resumed interactions). Choosing the unsupported Crisis Advisor/network combination explicitly says “No artifact for this network”, rather than inventing results. A subsequent real `Play replay` → `Pause replay` interaction advanced the Operations slider from 0 to 4 and returned to the paused state; its screenshot is retained.
- Independently checked relative percentages against `(scenario − baseline) / abs(baseline) × 100`: six nonzero-baseline metrics passed; all nine zero-baseline metrics explicitly contain `delta_pct=null`.
- IEEE-14 is a single-snapshot dataset: these two live runs cannot establish multi-snapshot simulation replay behavior. The precomputed Operations replay is the separate temporal interaction exercised here.


## Research labelling

Operations explicitly says “Precomputed Grid2Op episodes”, identifies synthetic inputs/modeled trace/calculated KPIs, and warns that simulation survival is not operational safety. Methods states that only PyPSA runs live and the other engines/studies are published as labelled precomputed artifacts; it documents DC approximation, missing AC voltage/reactive-power/stability constraints, and research-only use. Research routes passed the production browser assertions for explicit precomputed text in both themes at all three sizes.

## Explorer and Studio interaction detail

The five Explorer network switches showed matching API/UI counts (lines below include transformers): AC/DC 9 buses, 7 branches, 4 links, 6 generators, 0 storage; IEEE-14 14/20/0/5/0; IEEE-118 118/186/0/54/0; Belgium 10/6/10/33/5; SciGRID 585/948/0/1423/38. IEEE networks displayed schematic badges and no geographic basemap; the three geographic networks displayed basemap/provenance information. Legends were visible on desktop. Layer-click details were observed for buses, lines, transformers, links, generators and storage, and keyboard search selected a load with MW/MWh and provenance. Overlapping geographic symbols sometimes selected a co-located generator/storage asset rather than the intended bus; those clicks are not claimed as successful bus selections. Not all counted links/transformers have distinct rendered geographic geometry, so rendered-feature counts are not equivalent to catalog totals.

Ctrl+K focused “Asset search query”; matching assets, ArrowDown/Enter selection and “No matching assets” were observed. Belgium carrier filtering reduced rendered generators from 33 to 28 when CCGT was disabled; hiding the generator layer reduced them to zero. Escape failure is F-09. The raw interaction transcript retains the first runner's search-overlay interception timeout; its unfinished filter case was resumed from a fresh page, not counted as a successful original run. No hover tooltip was positively observed by that runner; tooltip completeness is not established.

All 12 presets across all five datasets validated. Added every offered event type: IEEE-14 demand/line/generator events and Belgium demand/renewable/line/link/generator/storage-state events; validation remained true for the default event values. Empty name, zero snapshots, negative VOLL and negative demand multiplier produced validation errors and disabled Run. Clearing VOLL instead crashed the render (F-07). A real anonymous save created unlisted record `405881fc-cd0c-4a01-b22a-9b9b2416492b`; reopening its returned Studio link restored the edited name. Name-only edits preserve the canonical scenario hash and therefore still match precomputed results; the authoritative blocked-physics case is demand ×1.2 (F-08), not the earlier name-only probe recorded in `studio-audit.json`.

Audit requests intentionally blocked simulation POSTs in the Studio edit probes; `ERR_BLOCKED_BY_CLIENT` there is audit instrumentation, not a production transport failure. Only the separately documented two IEEE-14 jobs solved live. The original long interaction runner and its navigation-timeout continuation are preserved in evidence; their timeouts are not claimed as application failures or passes.

## Re-verification on integrated branch

Re-tested the integrated frontend as a **local production build**, not the old Vercel deployment. Built with `VITE_API_BASE_URL` unset; `GRIDSTORM_API_PROXY=https://gridstorm-api.onrender.com npx vite preview --host 127.0.0.1 --port 4190 --strictPort` served the actual built bundles. Explorer is now `/explore` (`/` is the landing page). Playwright used the real public API for read-only catalog, geometry, comparison and scenario-validation responses. Historic job metadata/result/metrics were intercepted specifically to exercise the pending HTTP 410 contract, not to claim that the backend recovery deployment has happened.

Reproduction command from `apps/web`: `unset VITE_API_BASE_URL; npm run build && GRIDSTORM_API_PROXY=https://gridstorm-api.onrender.com npx playwright test -c playwright.audit.config.ts`. The config starts/reuses the port-4190 preview. Persistent API mutations are intercepted and aborted; any attempted mutation fails the suite. Only the pure `/scenarios/validate` POST is allowed through. **No simulation, recomputation, save or comparison-creation POST reached production.**

Final result: **9 Playwright tests passed (17.9 s)**. Typecheck, lint, unit tests and production build also passed; unit tests: **128 passed across 25 files**. Lint reported five existing Fast Refresh warnings, zero errors. [Machine-readable final results](screenshots/2026-11-15-integrated/results.json), per-case PNG/JSON evidence and [pre-fix F-04 failure results](screenshots/2026-11-15-integrated/f04-before-results.json) are retained in [2026-11-15-integrated](screenshots/2026-11-15-integrated/). The earlier runner assertions incorrectly assumed MapLibre 6 compact controls start collapsed and omitted the relative-percent display's separating space; these audit assertions were corrected to the real contract (one toggleable control and correctly distinguished units), not treated as application defects.

| Finding | Integrated status | Reproduction and observed evidence |
| --- | --- | --- |
| F-01 | **FIXED — UI against mocked 410; backend deploy still unverified here** | Historic Run at 1440×900, light and dark: intercepted `/result` returns HTTP 410 `artifact_unavailable`. “Result file unavailable” explicitly explains lost detail, enables “Re-run this scenario”, disables result/manifest downloads, and removes the loading-result skeleton. Recovery was not clicked because that would mutate production. [Light](screenshots/2026-11-15-integrated/f01-f02-light.png), [dark](screenshots/2026-11-15-integrated/f01-f02-dark.png), [410 response observation](screenshots/2026-11-15-integrated/f01-f02-light.json). |
| F-02 | **FIXED — UI against mocked 410; backend deploy still unverified here** | Same two 1440×900 Run cases retain completed/feasible/live metadata while prominently saying “This simulation completed, but its detailed result file is no longer available” and “Numerical series cannot be recovered from metadata alone”. See F-01 evidence; no inference of available numerical detail from the badges. |
| F-03 | **FIXED** | Default AC/DC Explorer at 390×844 dark has exactly **one** compact attribution control and one attribution text block; its toggle collapses it. MapLibre 6 initially expands even compact controls, but there are no duplicate blocks. [Mobile screenshot](screenshots/2026-11-15-integrated/f03-f05-mobile-dark.png). |
| F-04 | **FIXED in this re-verification** | Reproduced the `circle-11` warning on the integrated build at 1440×900, 768×1024 and 390×844 dark despite `hasImage` eventually becoming true. Root cause: MapLibre 6's `styleimagemissing` notification is too late to satisfy that image request. Replaced the listener with `setMissingStyleImageResolver`, preserving the actual visible circle image. The same three production-browser cases now report `resolved: true`, **zero console messages and zero page errors**. Added a unit regression for resolver registration, visible/transparent marker pixels, unknown images and duplicate resolution. [Desktop](screenshots/2026-11-15-integrated/f03-f05-desktop-dark.json), [tablet](screenshots/2026-11-15-integrated/f03-f05-tablet-dark.json), [mobile](screenshots/2026-11-15-integrated/f03-f05-mobile-dark.json). |
| F-05 | **FIXED** | Fresh default AC/DC Explorer in the three dark viewport cases renders bus features after exactly **three `/api/v1` requests**: catalog, network metadata, GeoJSON; **zero asset-table requests**, versus 12 API requests in the old audit. Counts exclude separate health/readiness requests and cover navigation through first loaded/rendered map, not later interactions. See the three F-04 JSON request records. |
| F-06 | **FIXED** | Opened the original stored comparison at 1440×900 light with its real API response. Max line loading row reads `60.66 → 8.83`, absolute `−51.83 pp`, relative `−85.45 %`. [Rendered row](screenshots/2026-11-15-integrated/f06-loading-units.json), [screenshot](screenshots/2026-11-15-integrated/f06-loading-units.png). |
| F-07 | **FIXED** | IEEE-14 baseline Studio at 1440×900 light: cleared VOLL, retained an empty editable field, reached Run with invalid validation (“1 error”) and disabled submission; restoring the original value returned valid validation and enabled Run. Zero page errors throughout; no render loop. [Invalid-state evidence](screenshots/2026-11-15-integrated/f07-cleared-voll.json), [screenshot](screenshots/2026-11-15-integrated/f07-cleared-voll.png). |
| F-08 | **FIXED** | SciGRID baseline Studio at 1440×900 light: added demand multiplier **1.2**, waited for successful validation, observed unavailable execution forecast and disabled Run. A forced native click on the disabled control left the user in Studio, with **zero simulation POST attempts** recorded; the mutation guard would abort any regression before a POST reached production. [Request-interception evidence](screenshots/2026-11-15-integrated/f08-no-simulation-post.json), [screenshot](screenshots/2026-11-15-integrated/f08-no-simulation-post.png). |
| F-09 | **FIXED** | IEEE-14 Explorer at 1440×900 light: enabled the now-explicit full-asset search, pressed Ctrl+K, searched `load-3`, selected its result, verified its details, pressed Escape, and verified the drawer was absent immediately and after 500 ms. Zero page errors. [Evidence](screenshots/2026-11-15-integrated/f09-escape-dismissal.json), [screenshot](screenshots/2026-11-15-integrated/f09-escape-dismissal.png). |

These results establish integrated frontend behavior and the UI's HTTP 410 handling only. They do not supersede the old-production observations above, establish production deployment, test an actual recomputation, or prove artifact persistence across a backend restart.
