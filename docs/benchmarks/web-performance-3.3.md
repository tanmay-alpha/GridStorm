# Web performance — GridStorm 3.3 (refinement)

Follows [web-performance-3.2.md](web-performance-3.2.md) (same scripts, machine and browser conditions;
method and noise thresholds there). 3.3 changes the entry chunk only; nothing from 3.0/3.2 is redone.

## Summary

- **Entry chunk −59 % gzip** (351.7 → 144.6 KiB; initial JS + CSS every route downloads 374.4 → 167.4 KiB).
  57 % of the old entry was ECharts + zrender, pulled in by `router.tsx` → `components/ui` barrel →
  `Chart.tsx`, whose module-level `echarts.use([...])` is a side effect the bundler must keep.
  The engine is now a lazy chunk, loaded by the first chart (and preloaded by chart routes).
- Routes without charts (home, Explorer, Studio, Data catalogue, Workbench, Library, Methods) no longer
  download or parse ECharts: **JS transferred −207 KB** on each.
- Home's 6 API requests are 6 distinct, needed requests (no duplicate); see [Home](#b-home-api-requests).
- Desktop run-page LCP: the LCP element is the Grid Impact Brief's scenario statement, which waits for a
  4th sequential API round trip. Fix proposed to the runs/ owner (not implemented here); see
  [Run page](#c-desktop-run-page-lcp).
- No route requests the same API URL twice ([per-route requests](#d-api-requests-per-route)).

## Method

Scripts: [`scripts/perf/measure.mjs`](../../scripts/perf/measure.mjs),
[`scripts/perf/bundle-sizes.mjs`](../../scripts/perf/bundle-sizes.mjs) — conditions as in 3.2 (Playwright
Chromium headless, fresh context per rep, desktop 1440×900 CPU 1×, mobile 390×844 DPR 3 CPU 4×, no network
throttling). Changes to `measure.mjs` in 3.3:

1. **Content wait.** The 3.2 script settled on network idle (500 ms quiet). At 4× CPU the old entry chunk
   executed for > 500 ms without network activity, so on 4 mobile routes the run ended before the lazy route
   chunk was requested: the first 3.3 production run recorded `/`, `/studio`, `/workbench`, `/benchmarks`
   with 1–2 API requests instead of 4–8 and an LCP from the shell
   ([`perf-3.3-before-prod-script32.json`](data/perf-3.3-before-prod-script32.json), kept for the record).
   The script now waits for the route's `h1` (every page renders one; the Suspense skeleton does not) before
   network idle, and reports it as **Content ms**. Mobile medians in 3.2 for those routes may have the same
   bias; compare 3.3 numbers with 3.3 numbers only.
2. `lcp_element` (tag, test id, classes, size, text) and `api_urls` (path + query, in request order) per sample.
3. A same-origin API (local `vite preview` proxy, `--api` = `--web`) is recognised by path (`/api/*`,
   `/health`, `/ready`) instead of counting every same-origin request.

**Machine load.** Other agents were building and running browsers on the same machine during these runs.
The production numbers below are the *same deployment* as the 3.2 "after" run (entry `index-r79SFz1b.js`)
yet mobile long tasks roughly doubled (e.g. run page 910 → 2515 ms): absolute timings are inflated and noisier
than in 3.2. The local before/after comparison is therefore **interleaved** (below), and timing differences
are only claimed where they exceed both the 3.2 thresholds (≈ 150 ms browser) and the spread between rounds.

## Before — production (3.3 baseline)

- **When**: 2026-11-17T11:33Z. **What**: https://gridstorm.vercel.app (Vercel build of `f8b3c28`, entry
  `index-r79SFz1b.js`), API `/health` git_sha `f8b3c28`. 3 reps per route × viewport, GETs only.
- **Raw data**: [`data/perf-3.3-before-prod.json`](data/perf-3.3-before-prod.json),
  [`data/perf-3.3-before-prod.md`](data/perf-3.3-before-prod.md). No page errors, no failed requests, every
  grid drawn.

| Route | Viewport | Content ms | LCP ms | CLS | Grid ms | JS KB | Requests (API) | Long tasks ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `/` | desktop | 976 | 1204 | 0.0011 | n/a | 387 | 19 (6) | 64 |
| `/explore` IEEE-14 | desktop | 865 | 1084 | 0.0164 | 1306 | 393 | 19 (8) | 52 |
| `/explore` SciGRID | desktop | 796 | 1016 | 0.0171 | 1814 | 684 | 39 (4) | 532 |
| `/studio` | desktop | 1127 | 1136 | 0.0218 | n/a | 393 | 18 (4) | 0 |
| `/runs/c328baa0-…` | desktop | 1021 | 1764 | 0.0013 | 1993 | 414 | 37 (15) | 202 |
| `/compare?comparison=4f5661ec-…` | desktop | 955 | 1316 | 0.0165 | 1682 | 412 | 32 (11) | 204 |
| `/workbench` | desktop | 857 | 844 | 0.0002 | n/a | 398 | 13 (4) | 0 |
| `/benchmarks` | desktop | 740 | 740 | 0.0002 | n/a | 486 | 20 (8) | 114 |
| `/data` | desktop | 799 | 836 | 0.0002 | n/a | 372 | 8 (2) | 52 |
| `/data/opsd-de-load-forecast` | desktop | 991 | 996 | 0.0002 | n/a | 387 | 15 (4) | 55 |
| `/` | mobile | 1409 | 1400 | 0.0021 | n/a | 387 | 19 (6) | 815 |
| `/explore` IEEE-14 | mobile | 1672 | 2000 | 0.0021 | 2351 | 393 | 19 (8) | 1107 |
| `/explore` SciGRID | mobile | 1558 | 1752 | 0.0296 | 3472 | 684 | 23 (4) | 1711 |
| `/studio` | mobile | 1769 | 2012 | 0.0021 | n/a | 393 | 18 (4) | 812 |
| `/runs/c328baa0-…` | mobile | 1570 | 1572 | 0.0021 | 3850 | 414 | 37 (15) | 2515 |
| `/compare?comparison=4f5661ec-…` | mobile | 1198 | 1256 | 0.0021 | 3063 | 412 | 32 (11) | 1801 |
| `/workbench` | mobile | 1589 | 1588 | 0.0021 | n/a | 398 | 12 (3) | 791 |
| `/benchmarks` | mobile | 1576 | 1668 | 0.0021 | n/a | 486 | 14 (2) | 1011 |
| `/data` | mobile | 1468 | 1460 | 0.0021 | n/a | 372 | 8 (2) | 770 |
| `/data/opsd-de-load-forecast` | mobile | 2039 | 2044 | 0.0021 | n/a | 387 | 15 (4) | 1973 |

API medians (5 samples): `/health` 192 ms, `/api/v1/networks` 193, IEEE-14 GeoJSON 192, SciGRID GeoJSON 477
(277–814, one slow outlier pulls the median), artifact index 197, data catalog 193, dataset 186 — unchanged
from 3.2 within noise.

## Investigation

### (a) What is in the entry chunk

Built with source maps (`build.sourcemap: true` already), then minified bytes attributed to source files by
walking the source-map segments (scratch script, not committed). Entry `index-*.js` of the release tree,
1,113,404 B raw:

| Package / area | Raw KiB | Share |
|---|---:|---:|
| `echarts` | 451.1 | 41.5 % |
| `react-dom` | 202.6 | 18.6 % |
| `zrender` (ECharts renderer) | 169.8 | 15.6 % |
| `react-router` | 93.1 | 8.6 % |
| `@tanstack/query-core` + `react-query` | 35.3 | 3.2 % |
| `src/components/ui` (barrel: every shared primitive) | 28.7 | 2.6 % |
| `@radix-ui/*` + `@floating-ui/*` + `react-remove-scroll` (Dialog in the shell, Popover via the barrel) | ≈ 55 | ≈ 5 % |
| `src/api`, `src/lib`, `src/components/layout`, `router.tsx`, `main.tsx` | 20.2 | 1.8 % |
| `lucide-react` (17 icons used by the shell/barrel) | 6.2 | 0.6 % |

KaTeX and MapLibre were **not** in the entry (already lazy: `research` and `NetworkMap` chunks). The path that
pulled ECharts in: `router.tsx` imports `SkeletonBlock` from `components/ui` (the barrel) → the barrel
re-exports `./Chart` → `Chart.tsx` runs `echarts.use([...])` at module level. A side-effecting module
reachable from the entry is kept in the entry even though no entry code renders a chart. The rest of the
barrel (≈ 29 KiB raw) stays in the entry: every route chunk imports it, so moving it would only add a request.

### (b) Home API requests

Production home, every sample: `/health` (shell status), `/api/v1/networks?limit=200` (dataset cards and the
preview's summary), then for the IEEE 14-bus preview `geojson` plus `assets?type=generators|loads|carriers`
— 6 requests, 6 distinct URLs, no duplicate. The preview needs geometry (GeoJSON, 9.7 kB), generator and load
rows (unit glyphs at their buses) and carrier colours; the API has no combined endpoint, so a single smaller
request would need a new API route (out of scope here; services/api is not owned by this change). Deferring
is not useful either: the preview is above the fold at 1440×900 *and* at 390×844 (it is the first thing
below the hero text on the production 390×844 screenshot), it is already a lazy chunk behind a
fixed-height slot (`h-64 sm:h-80 lg:h-96`, CLS 0.0011 / 0.0021), its queries share cache keys with the
Explorer (a later `/explore?network=pglib-case14-ieee` reuses all four), and LCP on home is the hero `h1`
(desktop) / intro paragraph (mobile), not the preview. Left as is.

### (c) Desktop run-page LCP

Production waterfall (scratch probe, `/runs/c328baa0-…`, desktop, 2 reps, ms from navigation start; rep 0):

| Start → end | Request |
|---|---|
| 206 → 407 | entry `index-*.js` (363 KB) |
| 520 → 619 | `RunPage` chunk + 17 small route chunks |
| 830 → 1065 | `GET /simulations/c328baa0-…` (job) |
| 1071 → 1446 | `GET /simulations/c328baa0-…/result` (9.7 kB) and `/networks/pglib-case14-ieee` |
| 1448 → 1630 | long task 182 ms: first render of `CompletedRun` |
| 1486 → 1933 | scenarios list, jobs list, networks list, `artifacts?kind=simulation`, generators |
| 1630 → 2030 | **`GET /scenarios/pglib-case14-ieee-gen-1-outage`**, job artifacts; then GeoJSON, loads, storage units |
| 1943 → 2233 | baseline result `458fddab…/result` |

LCP candidates: footer 772 → page subtitle 1120 → "Key assumptions" line 1672 → **Grid Impact Brief scenario
statement** ("Scenario “PGLib IEEE 14-bus — loss of the main unit gen-1 …” applies …", 744×57 px at y≈836)
at **2072 ms**. That statement is built from the scenario record, which `CompletedRun` only requests after the
result has arrived and rendered: job → result → render → scenario is four sequential round trips of
≈ 200–400 ms each to Render. Payloads are small (job 1.3 kB, result 9.7 kB, scenario 1.4 kB): the page is
latency-bound, not bandwidth-bound. Rep 1 shows the same order (LCP 3892 ms on a slow entry download).

**Change (implemented by the runs/ owner in `b292ba7`)**: once the job record
is known, start the job-dependent queries in parallel with `/result` — call
`useScenario(j.scenario_record_id ?? j.scenario_id, …)` and `useBaselinePlan(j)` in `RunPage` (same query
keys, so `CompletedRun` reuses the cache). The scenario then arrives with the result, so the brief statement
can paint with the first `CompletedRun` render (≈ 1.5–1.7 s instead of ≈ 2.0 s here), and the baseline
result moves one round trip earlier. Optional: reserve the statement's height. To be measured after deploy.

### (d) API requests per route

From `api_urls` of the production run (desktop rep 0): **no route requests the same URL twice.** Counts are
distinct requests: home 6, Explorer IEEE-14 8 (networks, network, GeoJSON, 4 unit tables, health), SciGRID 4,
Studio 4, run 15, compare 11, Workbench 4, Benchmarks 8 (one per published artifact shown), Data 2,
dataset 4 (two `series` windows = the period comparison A and B). The run page's 15 are the job, its result,
its artifacts, the baseline plan inputs (scenarios list 36.5 kB, jobs list 16.8 kB), the baseline job's
result (`458fddab…`, 8 kB: the "what changed" panel and brief), the network detail and list, 3 unit tables,
GeoJSON, `artifacts?kind=simulation` (execution policy) and `/health`. The reducible cost is the sequencing
above, not the count; [INFERENCE] an API filter (e.g. jobs by scenario and status) would avoid the 16.8 kB
jobs list but needs an API change.

## Changes (this release)

| File | Change |
|---|---|
| `apps/web/src/components/ui/chartRuntime.ts` (new) | ECharts modules + `echarts.use([...])` + `initChart()`; only ever imported dynamically. |
| `apps/web/src/components/ui/chartLoader.ts` (new) | One cached `import('./chartRuntime')` (reset on failure so a later mount retries); `preloadChartRuntime()`. |
| `apps/web/src/components/ui/Chart.tsx` | Initialises the chart once the runtime has loaded (same fixed-height box, so no layout shift); options effect keyed on the instance; on a failed download the box says "Chart engine could not be loaded — reload the page to retry." |
| `apps/web/src/router.tsx` | Chart routes (`/runs/:id`, `/compare`, `/mitigation`, `/data/:id`, `/operations`, `/benchmarks`) start the engine download together with their route chunk, so it is parsed while the API requests are in flight instead of after the data arrives. |
| `apps/web/src/api/hooks.ts` | `useNetworks`, `useNetwork`, `useArtifactIndex`: `staleTime` 1 h (`CATALOG_STALE_MS`) instead of 30 s — these responses are immutable per API deployment (`Cache-Control: public, max-age=3600`). No effect on cold loads (not claimed as a measured gain); avoids refetch + re-render when a route is revisited after 30 s. |
| `scripts/perf/measure.mjs` | Content wait, `lcp_element`, `api_urls`, same-origin API rule (see Method). |

`observatory/charts.ts` imports `echarts/core` statically to register `MarkAreaComponent`; the bundler puts
the shared ECharts core in a chunk named after one of its modules (`MarkerView-*.js`), loaded by the dataset
page and by the chart runtime. A Rolldown `codeSplitting` group forcing one `echarts` chunk was tried and
rejected: the entry grew by 4.7 KiB gzip.

## Bundle — before → after

Both builds from the same snapshot of the working tree (other agents' concurrent edits included in both),
differing only in the files above; `node scripts/perf/bundle-sizes.mjs`. KiB, gzip level 6 / brotli q 11.
Raw: [`data/bundle-3.3-before.json`](data/bundle-3.3-before.json), [`data/bundle-3.3-after.json`](data/bundle-3.3-after.json).

| | Before gzip | After gzip | Δ | Before brotli | After brotli |
|---|---:|---:|---:|---:|---:|
| Entry `index-*.js` | 351.69 | 144.64 | −207.05 (−58.9 %) | 296.19 | 125.23 |
| Initial JS + CSS (every route) | 374.41 | 167.36 | −207.05 (−55.3 %) | 314.97 | 144.01 |
| `chartRuntime-*.js` (new, lazy) | — | 95.03 | | — | 81.27 |
| `MarkerView-*.js` (new, lazy: shared ECharts core) | — | 114.00 | | — | 97.19 |
| Total JS (42 → 44 files) | 1017.88 | 1019.71 | +1.83 | 852.37 | 859.88 |

## Local before → after (same preview server and local API, interleaved)

`perf-3.3-local-{before,after}.json`: the two builds served alternately on the same port against one local
API (3 rounds × 2 reps each), so network and CPU conditions are shared. The local "after" build contains the
chart split and catalog `staleTime` only (it predates the run-page request change). Medians, ms.

| Route | Desktop LCP | Desktop JS KB | Mobile (4× CPU) LCP | Mobile long tasks |
|---|---:|---:|---:|---:|
| `/` | 868 → 1094 | 377 → 169 | 1386 → 952 | 1050 → 694 |
| `/explore` IEEE-14 | 480 → 436 | 384 → 177 | 1494 → 864 | 1163 → 583 |
| `/explore` SciGRID | 478 → 460 | 667 → 460 | 1488 → 870 | 2072 → 1923 |
| `/studio` | 496 → 512 | 382 → 175 | 1464 → 1032 | 818 → 631 |
| `/runs/<id>` | 580 → 734 | 408 → 411 | 1136 → 892 | 1260 → 1055 |
| `/compare?comparison=` | 604 → 692 | 405 → 407 | 1064 → 662 | 2115 → 1174 |
| `/workbench` | 482 → 442 | 387 → 180 | 1122 → 652 | 850 → 434 |
| `/benchmarks` | 480 → 558 | 472 → 475 | 1204 → 798 | 998 → 1483 |
| `/data` | 462 → 492 | 361 → 154 | 1064 → 710 | 785 → 596 |
| `/data/opsd-de-load-forecast` | 548 → 514 | 377 → 379 | 1030 → 972 | 1273 → 1073 |

Reading: on the 4× CPU phone profile every route paints earlier (−60 … −630 ms LCP), because the entry no
longer parses ECharts. On the unthrottled desktop most differences are within the 150 ms noise threshold;
three are above it in the wrong direction and are reported, not explained away: home +226 ms (its route
content appears earlier, 492 → 440 ms; the LCP element moves later, [INFERENCE] the preview's lazy schematic),
run +154 ms and compare +88 ms (chart routes now fetch the engine as a second chunk instead of with the
entry). Production after-deploy numbers decide whether these persist.


## Open items

- Production after-measurement: once deployed, rerun
  `node ../../scripts/perf/measure.mjs --web https://gridstorm.vercel.app --api https://gridstorm-api.onrender.com --data-id opsd-de-load-forecast --out ../../docs/benchmarks/data/perf-3.3-after-prod.json --md ../../docs/benchmarks/data/perf-3.3-after-prod.md`
  from `apps/web` and compare with the production table above.
- Run-page proposal (c) belongs to the runs/ owner.
