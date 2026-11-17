# GridStorm 3.2 — independent verification (local release build)

Date: 2026-11-17 (UTC 2026-11-16 evening). Branch `release/gridstorm-3.2`, PR #14.
Environment: Windows 11 (10.0.26300), Node 24, Chromium (Playwright 1.65), `@axe-core/playwright` in a
scratch project outside the repo. Web: `vite build` of the branch served with `vite preview`
(`GRIDSTORM_API_PROXY` → local API). API: `uvicorn gridstorm_api.main:app` from the branch with a scratch
`GRIDSTORM_STATE_DIR` (SQLite + local artifact store); local jobs: IEEE-14 baseline `bef2c7fc`, gen-1
outage `3b1e8c37`, comparison `3caf8b4c`. Production was only read (GET).

Scripts (scratch, not committed): `audit.cjs` (axe + console/failed requests per route × theme at
1440×900; overflow of `document.scrollingElement` and `main` per route × viewport, offending elements
listed), `journey.cjs` (use-in-scenario journey, export, keyboard, reduced motion, 200 % zoom).

## Gates

| Gate | Result | Evidence |
|---|---|---|
| axe (WCAG 2.0/2.1/2.2 A+AA + best-practice), 18 routes × light/dark | **pass**: 0 violations in 36 runs (56 "incomplete" items = manual-review contrast over canvases/gradients) | final run after fixes; before fixes: `target-size` (serious) on `/data/nasa-power-de-weather` series checkboxes → fixed in `e3e418b` |
| Horizontal overflow, 18 routes × 1440/1280/768/390/360 | **pass**: 0 of 90 checks overflow (`doc` and `main` scroll width = viewport) | before fixes: Methods engine table, sr-only table headers escaping the scroll clip, long checksum/path strings at 360 px → fixed in `e3e418b` |
| Console errors / page errors / failed requests / HTTP ≥ 400 | **pass**: 0 on all 36 route × theme loads | `audit.cjs` |
| 200 % zoom (CSS zoom, 1440 → 720 CSS px) on `/data/opsd-de-load-forecast`, `/data/nasa-power-de-weather`, `/data/network-pglib-case14-ieee`, `/studio` | **pass**: no overflow, h1 visible | `journey.cjs` `zoom200` + screenshots inspected |
| Reduced motion | **pass**: with `prefers-reduced-motion: reduce` every computed transition/animation on `/`, `/data`, `/studio`, `/data/opsd-de-load-forecast` is 0 s and no animation runs; without it the longest is 150 ms (colour transitions) | `journey.cjs` `motion_*` |
| Keyboard: `/data` | **pass**: skip link → nav → theme → search → category/provenance/region/source filters → first card (focus ring drawn on the card's `::after`); dataset page → "Provenance & licence" (2 tabs) → drawer traps focus, Escape closes it, focus returns to the trigger | `journey.cjs` `kb_*` |
| Keyboard: Studio grid → crisis → review → run | **pass** | `e2e/studio-guided-demo.spec.ts` "keyboard only" (local + CI) |
| Use in a scenario | **pass**: `/data/observed-analogue-scenarios` → "Use in a scenario" → `/studio?network=scigrid-de&preset=observed-dunkelflaute-2015-01-20` lands on Review, labelled *verified precomputed result*; Run → job `execution_mode: precomputed`, feasible, unserved **2 721 MWh** (2.721 GWh), scenario hash `66d25e27…` = `analogue-results.json` | `journey.cjs` |
| Export | **pass**: `opsd-de-load-forecast` CSV `…_2015-01-17_2015-01-24.csv`, 177 lines, `# license: CC-BY-4.0 …` header, `utc,de_load_forecast`; metadata-only entries (`observed-analogue-scenarios`, `network-pglib-case14-ieee`, `study-stormbench`) show a disabled export with the reason | `journey.cjs` |
| Web unit suite | **pass**: tsc clean, eslint 0 errors (5 pre-existing warnings), vitest 42 files / 386 tests (baseline 38 / 306) | `npx tsc -b --noEmit`, `npx eslint .`, `npx vitest run` (after all fixes) |
| CI on PR #14 (`d61425d`) | **pass**: 28/28 checks incl. 17 Python components, web, web e2e (Playwright, real API), api container + Trivy, gitleaks, observatory bundle verify, Vercel preview + responsive Playwright | GitHub Actions run 44006783223 |
| e2e (local, real API) | **pass** for the specs run locally: journey, studio-live-execution, studio-guided-demo, header-overflow, integrated-findings, explorer-schematic (coordinator); research, observatory, results-compare, run-map, mitigation-studies, workbench-manifest, landing-explorer (UI agents) | Playwright against `vite preview` (`E2E_PORT`) |
| API spot checks | **pass**: catalog paging (`limit=2&offset=2` → 2 items, total 21) with category facets; `ETag` + `Cache-Control: public, max-age=300`; `If-None-Match` → 304; export of a non-exportable entry → 403; raw series 2015-01-01…2019-01-01 → 422 `range_too_large` (`max_days` 1096) | curl against the local API; 38 API tests in `services/api/tests/test_data_catalog.py` |

## Defects found during verification

| ID | Severity | Finding | Status |
|---|---|---|---|
| V32-01 | serious (axe `target-size`) | Observatory series checkboxes < 24 px apart | fixed `e3e418b`, re-checked: 0 violations |
| V32-02 | minor (overflow 360 px) | Methods engine-version table and sr-only `<th>` text widened `main`; long checksums/paths did not wrap | fixed `e3e418b`, re-checked: 0 / 90 overflow |
| V32-03 | P2 (CI-only e2e failure) | The "Advanced research" `<details>` menu stayed open after following one of its links; with the new *Data* nav item it covered Studio's "Current grid only" toggle under Linux font metrics (`journey.spec.ts:33` timeout) | fixed `d61425d` (menu closes on navigation, regression unit test) |
| V32-04 | info | 2 CI expectations pinned the old preset count (`tests/scientific` 12 → 15 PyPSA artifacts; `studio-live-execution` 6 → 9 SciGRID-DE presets); gitleaks flagged a public commit SHA under the key `api_git_sha` | fixed `96294d8` |

## Production (after merge `f8b3c28`, 2026-11-17)

- Web: Vercel `dpl_HXJ6tmwRhBqWrqMQgasMBLkq4eMT` (Git build of `f8b3c28`) aliased to gridstorm.vercel.app; API `/health` git_sha `f8b3c28`, `/ready` postgres + supabase durable.
- `scripts/probe_production.py`: all PASS (15 visible scenarios, 58 precomputed artifacts, 7 results sha-verified, 5 lost legacy results disclosed as 410).
- GitHub Actions on `main`: CI 44008687576, Data Observatory bundle 44008687567, scientific reproducibility incl. full slow/network tests 44009643558 (pypsa / pandapower / stormbench MATCH), public browser smoke 44009033246, production smoke 44009037283 — all success.
- Live journey (one bounded production write: a precomputed job, no solver run): `/data/observed-analogue-scenarios` → Use in a scenario → Studio *verified precomputed result* → job `5dbb2e94-600c-4cc3-a5b7-eb4f5be55b19`, `execution_mode: precomputed`, unserved 2 721.006897 MWh, result sha `6d0c0805…` (identical to the local run); CSV export with licence header; disabled export on metadata-only entries; drawer focus trap and focus return; 0 console errors on `/data` and `/data/opsd-de-load-forecast`.
- `/api/v1/artifacts/stormbench/stormbench-case14-ieee`: `screening_vs_dc.kendall_tau = spearman = 1.0`.
- Performance after vs before with the same script: [web-performance-3.2](../benchmarks/web-performance-3.2.md#after-production-gridstorm-32-release).

## Not covered here

- Supabase database/storage inventory — blocked by credentials ([production inventory](../data/production-inventory.md)).
- axe/overflow matrix was run on the local release build, not re-run against production (same build inputs; production browser smoke covers responsive checks).
