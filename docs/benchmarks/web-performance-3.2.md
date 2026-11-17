# Web and API performance — GridStorm 3.2 (TODO G32-10)

Same script, same routes, same conditions before and after the 3.2 release. Earlier work (not
repeated here): [web-performance-3.0.md](web-performance-3.0.md) (schematic networks without
MapLibre, lazy MapLibre chunk, `style.load` gating, kept-alive map, `include=header` artifact index)
and the round-2 CLS fixes in `TODO.md` (R2-02, R2-03, R2-10: `/studio`, run page, Library,
`/compare?comparison=` mobile CLS ≤ 0.002).

## Method

Scripts (committed, reusable):

- [`scripts/perf/measure.mjs`](../../scripts/perf/measure.mjs) — browser route metrics + API latency
  for one web origin and one API origin. Read-only (GET only). Run from `apps/web` so
  `@playwright/test` resolves:

  ```sh
  cd apps/web
  node ../../scripts/perf/measure.mjs --web https://gridstorm.vercel.app --api https://gridstorm-api.onrender.com \
    --label after --out ../../docs/benchmarks/data/perf-3.2-after.json --md ../../docs/benchmarks/data/perf-3.2-after.md
  ```

  Defaults: 3 reps per route × viewport (medians), 5 samples per API endpoint (medians), geographic
  network `scigrid-de`, run `c328baa0-718e-4cad-9538-e376d2972df2` (IEEE-14 live job), comparison
  `4f5661ec-e6f1-4600-96ed-710709f10c36`; the `/data/<id>` dataset is the first item of
  `GET /api/v1/data/catalog` (skipped when the endpoint 404s). `--routes`, `--viewports`, `--reps`,
  `--run-id`, `--comparison-id`, `--data-id`, `--geo-network` override them; the header comment in the
  script documents every metric.
- [`scripts/perf/bundle-sizes.mjs`](../../scripts/perf/bundle-sizes.mjs) — per-chunk raw / gzip
  (zlib default level) / brotli (q 11) sizes of a Vite `dist/`, and the "initial" set referenced by
  `index.html`: `node scripts/perf/bundle-sizes.mjs --dist apps/web/dist --out <file>.json --md <file>.md`.

Browser conditions: Playwright Chromium headless, fresh context per rep (cold HTTP cache), one
discarded warm-up navigation per viewport.

| Viewport | Size | DPR | CPU | Network |
|---|---|---|---|---|
| desktop | 1440×900 | 1 | no throttling | unthrottled (machine's internet) |
| mobile | 390×844, touch | 3 | 4× slowdown (CDP `Emulation.setCPUThrottlingRate`) | unthrottled |

Metrics (ms from navigation start):

- **LCP** — last `largest-contentful-paint` entry when the page settles.
- **CLS** — web-vitals definition (largest session window: gaps < 1 s, window ≤ 5 s); the plain sum
  (the figure quoted in the 3.0 and round-2 notes) is shown in brackets.
- **Grid** — first time a visible, ready grid drawing exists: `[data-testid=network-schematic][data-ready=true]`
  or `[data-testid=network-map][data-map-ready=true]` (the selectors the e2e specs use), polled every
  50 ms in the page. Only for routes that draw a grid (`/explore`, run, compare); "n/a" elsewhere.
- **JS KB** — transferred script bytes (encoded body + headers, Playwright `request.sizes()`);
  **Total KB** — all requests, including basemap tiles for geographic maps.
- **Requests (API)** — finished requests until settled; API = requests to the API origin (fan-out);
  the distinct API paths per sample are in the raw JSON.
- **Long tasks** — total duration (count) of `longtask` entries until settled.
- **Settled** — wall time until load + grid drawn (grid routes) + network idle (500 ms quiet, capped at
  20 s) + 500 ms.
- **API** — Node `fetch` (keep-alive, `accept-encoding` negotiated by undici), wall time to the full
  body; median, min–max and TTFB of 5 samples. "First /health" is the very first request of the run:
  it is a Render cold start only if the instance happened to be asleep (it was not in the before run).

Network and third-party (Vercel edge, Render, OpenFreeMap basemap tiles) latency varies between
runs; differences below ~150 ms in LCP/grid time and ~20 ms in API medians are noise at 3/5 samples.

## Before (production, 3.2 baseline)

- **When**: 2026-11-16T20:53Z (2026-11-17 local), single run, ~3 min.
- **What**: https://gridstorm.vercel.app = `main` `387f584` (entry assets `index-CFVBxCSl.js`,
  `jsx-runtime-Wy9s6hX0.js`, `index-Dwq7vG7-.css`); https://gridstorm-api.onrender.com `/health`
  git_sha `127db27`.
- **Machine**: Windows 11 (10.0.26300), Intel Core i7-14650HX (24 logical CPUs), Node v24.14.1,
  Playwright Chromium 159.0.8154.6, residential internet.
- **Raw data**: [`data/perf-3.2-before.json`](data/perf-3.2-before.json) (meta, medians, every sample with
  API paths), [`data/bundle-3.2-before.json`](data/bundle-3.2-before.json).
- No page errors and no failed requests in any sample; every grid route drew its grid in all reps.

### Routes — desktop 1440×900, CPU 1×

| Route | HTTP | LCP ms | CLS (sum) | Grid ms | JS KB | Total KB | Requests (API) | Long tasks ms (n) | Settled ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `/` | 200 | 780 | 0.0002 (0.0002) | n/a | 370 | 390 | 10 (1) | 0 (0) | 1743 |
| `/explore?network=pglib-case14-ieee` | 200 | 1152 | 0.0291 (0.0291) | 1388 | 387 | 419 | 17 (8) | 50 (1) | 2397 |
| `/explore?network=scigrid-de` | 200 | 1152 | 0.0309 (0.0309) | 2031 | 677 | 2782 | 34 (4) | 455 (5) | 4034 |
| `/studio` | 200 | 1272 | 0.0253 (0.0253) | n/a | 388 | 418 | 18 (4) | 0 (0) | 2233 |
| `/runs/c328baa0-…` | 200 | 1460 | 0.0143 (0.0145) | 1801 | 408 | 458 | 36 (15) | 147 (1) | 3059 |
| `/compare?comparison=4f5661ec-…` | 200 | 1212 | 0.0039 (0.0039) | 1526 | 403 | 443 | 29 (11) | 98 (1) | 2682 |
| `/workbench` | 200 | 784 | 0.0044 (0.0044) | n/a | 395 | 437 | 12 (4) | 0 (0) | 2251 |
| `/benchmarks` | 200 | 1188 | 0.0002 (0.0002) | n/a | 472 | 541 | 19 (8) | 59 (1) | 3000 |
| `/data` | 200 (app "Page not found") | 840 | 0.0002 (0.0002) | n/a | 365 | 385 | 6 (1) | 55 (1) | 1761 |
| `/data/<id>` | not measured: `GET /api/v1/data/catalog` → 404 on the baseline API | | | | | | | | |

### Routes — mobile 390×844, CPU 4×

| Route | HTTP | LCP ms | CLS (sum) | Grid ms | JS KB | Total KB | Requests (API) | Long tasks ms (n) | Settled ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `/` | 200 | 1388 | 0.0021 (0.0021) | n/a | 370 | 390 | 10 (1) | 464 (2) | 2261 |
| `/explore?network=pglib-case14-ieee` | 200 | 1468 | 0.0119 (0.0119) | 1988 | 387 | 418 | 17 (8) | 505 (4) | 2938 |
| `/explore?network=scigrid-de` | 200 | 2924 | 0.0476 (0.0476) | 2613 | 677 | 1833 | 27 (4) | 1340 (12) | 4350 |
| `/studio` | 200 | 1548 | 0.0021 (0.0021) | n/a | 388 | 418 | 18 (4) | 413 (3) | 2368 |
| `/runs/c328baa0-…` | 200 | 2484 | 0.0021 (0.0021) | 2899 | 408 | 458 | 36 (15) | 1393 (7) | 3415 |
| `/compare?comparison=4f5661ec-…` | 200 | 1216 | 0.0021 (0.0021) | 2735 | 403 | 443 | 29 (11) | 1160 (6) | 3240 |
| `/workbench` | 200 | 1468 | 0.0021 (0.0021) | n/a | 395 | 437 | 12 (4) | 580 (3) | 2790 |
| `/benchmarks` | 200 | 1156 | 0.0021 (0.0021) | n/a | 472 | 539 | 19 (8) | 1273 (8) | 3432 |
| `/data` | 200 (app "Page not found") | 1252 | 0.0021 (0.0021) | n/a | 365 | 385 | 6 (1) | 413 (2) | 2264 |
| `/data/<id>` | not measured (as above) | | | | | | | | |

### API latency (median of 5, keep-alive)

First `/health` of the run: 337 ms, HTTP 200 (instance already awake: warm, not a cold start; a
Render cold start was not provoked).

| Endpoint | HTTP | Median ms | Min–max ms | Median TTFB ms | Body bytes (decoded) | Encoding | Cache-Control |
|---|---|---:|---:|---:|---:|---|---|
| `/health` | 200 | 203 | 190–225 | 203 | 86 | br | — |
| `/api/v1/networks` | 200 | 207 | 195–217 | 206 | 13,461 | gzip | public, max-age=3600 |
| `/api/v1/networks/pglib-case14-ieee/geojson` | 200 | 204 | 192–220 | 203 | 9,738 | gzip | public, max-age=3600 |
| `/api/v1/networks/scigrid-de/geojson` | 200 | 303 | 292–806 | 278 | 464,252 | gzip | public, max-age=3600 |
| `/api/v1/artifacts?include=header` | 200 | 217 | 203–254 | 216 | 89,631 | gzip | public, max-age=3600 |
| `/api/v1/data/catalog` | 404 | 191 | 184–210 | 191 | 65 | br | — |
| `/api/v1/data/catalog/<id>` | not measured (no catalog) | | | | | | |

`/health` at ~200 ms is the floor from this machine to Render (network round trip + edge), so the
catalog routes add ≤ 15 ms server time except the 464 kB SciGRID GeoJSON (+~100 ms transfer).

### Production-build bundle (local build of `387f584`)

`git worktree add --detach ../gs-perf-baseline 387f584`, then in `apps/web`: `npm ci && npm run build`
(Vite build 1.29 s), `node scripts/perf/bundle-sizes.mjs`, then `git worktree remove`. The local
entry chunk (`index-DwU3V3Ry.js`, 1,105,723 B) differs from the production one (`index-CFVBxCSl.js`,
1,105,757 B) by 34 bytes, presumably the build-time `VITE_API_BASE_URL` (the production chunk embeds
`https://gridstorm-api.onrender.com`; not diffed byte-wise); the other initial assets have identical hashes.
Sizes in KiB (Vite's own report prints decimal kB, e.g. 361.09 kB gzip for the entry). Fonts (KaTeX)
and source maps excluded.

| Chunk | Initial | Raw KiB | gzip KiB | brotli KiB |
|---|---|---:|---:|---:|
| `index-DwU3V3Ry.js` (entry) | yes | 1079.81 | 349.34 | 294.56 |
| `NetworkMap-e1vkxd4N.js` (MapLibre, geographic maps only) | | 1042.16 | 282.45 | 230.76 |
| `maplibre-gl-worker-Boc9pDRP.mjs` | | 507.37 | 144.72 | 118.61 |
| `research---xc_tLe.js` | | 309.02 | 91.26 | 75.30 |
| `index-Dwq7vG7-.css` | yes | 108.14 | 18.03 | 14.72 |
| `StudioPage-37-dxByM.js` | | 50.62 | 15.29 | 13.76 |
| `workbench-DJgfUENu.js` | | 49.01 | 17.36 | 15.23 |
| `compare-CukTHOe5.js` | | 36.63 | 12.23 | 11.00 |
| `research-Bv5fr4tV.css` | | 29.10 | 7.79 | 6.74 |
| `methods-DyA2rA9G.js` | | 27.05 | 10.14 | 8.99 |
| `SchematicView-BnIpsLe9.js` | | 26.62 | 9.53 | 8.62 |
| `ExplorerPage-Z7OQx5OQ.js` | | 26.11 | 8.64 | 7.75 |
| `MitigationPage-D435MQkE.js` | | 22.65 | 7.10 | 6.39 |
| `RunPage-CmUJhxVr.js` | | 20.25 | 6.97 | 6.20 |
| `ComparePage-BcnSnIUK.js` | | 15.29 | 5.35 | 4.77 |
| `jsx-runtime-Wy9s6hX0.js` | yes | 8.75 | 3.34 | 3.00 |
| `RunOverview-3ZC0u2gS.js` | | 7.67 | 2.69 | 2.38 |
| `LibraryPage-DUF5I-dE.js` | | 6.94 | 2.25 | 1.98 |
| `HomePage-Cw4QhxBw.js` | | 5.62 | 2.25 | 1.94 |
| 17 smaller chunks (icons, hooks, `NotFound`, …; each < 2.6 KiB raw) | | 15.42 | 8.52 | 7.54 |
| **Total JS** (34 files) | | 3256.99 | 979.44 | 818.79 |
| **Total CSS** (2 files) | | 137.25 | 25.82 | 21.46 |
| **Initial JS + CSS** (3 files, every route) | | 1196.70 | 370.71 | 312.29 |

Every chunk is listed in [`data/bundle-3.2-before.json`](data/bundle-3.2-before.json).

### Observations (baseline; no changes made by this measurement)

- The entry chunk is 349 KiB gzip and is downloaded by every route; route chunks are small. This is
  the largest single lever for JS transferred (≈ 365–410 KB of script on every non-geographic route).
- Run page fan-out: 15 API requests (13 distinct paths) including `/api/v1/simulations`, `/api/v1/scenarios`
  and the result of another job (`458fddab…/result`); compare: 11 requests incl. both job results.
  Mobile long tasks on run/compare/benchmarks are 1.2–1.4 s total at 4× CPU.
- Geographic Explorer (SciGRID): 2.0 s (desktop) / 2.6 s (mobile) to a ready map; transferred bytes
  are dominated by MapLibre (≈ 290 KB) and basemap tiles, as already analysed in 3.0.
- CLS is "good" (< 0.1) on every route and viewport; highest is SciGRID Explorer mobile 0.048.

## After (to be measured on the release build)

Rerun both scripts with the same arguments against the deployed 3.2 release (web + API SHAs recorded
here), then add the same tables with before → after deltas, including `/data` and `/data/<id>` and
`/api/v1/data/catalog[/<id>]`, which did not exist on the baseline.
