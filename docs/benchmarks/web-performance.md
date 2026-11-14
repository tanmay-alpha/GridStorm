# Live web performance and API latency

Measured: 2026-11-14 22:14–22:30 UTC against <https://gridstorm.vercel.app> (Vercel edge `bom1`) and
<https://gridstorm-api.onrender.com> (API `git_sha 887d217`, Render free tier, behind Cloudflare).
All numbers below come from the runs described here; they are lab measurements from a single
Windows workstation on an unthrottled connection, not field (CrUX) data.

## Method

- Playwright 1.65.1, headless Chromium 159.0.8154.6, desktop viewport 1440×900, no CPU/network throttling.
- **Cold**: new browser context (empty HTTP cache). **Warm**: a second tab in the same context
  (HTTP cache primed; the SPA still boots from scratch). 3 cold + 3 warm loads per route; tables show medians.
- Per load: `goto` (load) → `networkidle` (≤20 s) → 3 s settle, then read:
  - Navigation Timing (`responseStart` = TTFB, `domContentLoadedEventEnd`, `loadEventEnd`), ms from navigation start;
  - FCP (`paint`), LCP (last `largest-contentful-paint` entry), CLS from `layout-shift` entries without recent
    input — both the Core Web Vitals definition (largest session window: gap < 1 s, window ≤ 5 s) and the plain sum;
  - JS bytes from Resource Timing for `*.js`/`*.mjs` (`transferSize` = wire incl. headers, `decodedBodySize`);
  - map time: an init script wraps the `window.__gridstormMap` assignment in `NetworkMap.tsx` and records
    `performance.now()` at map creation and at MapLibre's first `load` and `idle` events.
- Cross-origin API responses report `transferSize = 0` (no `Timing-Allow-Origin`), so "same-origin bytes"
  excludes API payloads; those are measured separately with curl.

## Page load (medians of 3)

| Route | Mode | TTFB | FCP | DCL | LCP | CLS (CWV window) | CLS (sum) | JS files | JS wire | JS decoded | Same-origin bytes | Requests |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `/` | cold | 214 | 544 | 511 | 1032 | 0.028 | 0.028 | 7 | 816,462 B | 2,684,507 B | 834,312 B | 31 |
| `/` | warm | 71 | 176 | 137 | 652 | 0.028 | 0.028 | 7 | 0 (cache) | 2,684,507 B | 300 B | 31 |
| `/studio` | cold | 218 | 604 | 574 | 1100 | 0.006 | 0.006 | 6 | 368,597 B | 1,094,303 B | 386,447 B | 23 |
| `/studio` | warm | 69 | 156 | 129 | 648 | 0.006 | 0.006 | 6 | 0 (cache) | 1,094,303 B | 300 B | 23 |
| `/benchmarks` | cold | 108 | 332 | 301 | 636 | **0.327** | 0.527 | 6 | 464,017 B | 1,409,918 B | 489,941 B | 31 |
| `/benchmarks` | warm | 36 | 148 | 114 | 460 | **0.519** | 0.519 | 6 | 0 (cache) | 1,409,918 B | 300 B | 31 |

Times in ms. `loadEventEnd` equals DCL within 1 ms on every route (SPA with module scripts), so it is omitted.

Per-run values (cold LCP / warm LCP, ms): `/` 860, 1056, 1032 / 20048, 644, 652; `/studio` 1040, 1100, 1188 /
648, 648, 708; `/benchmarks` 640, 636, 628 / 460, 460, 464. CLS per run on `/benchmarks` (sum):
cold 0.335, 0.527, 0.623; warm 0.352, 0.692, 0.519.

**Outlier:** the first warm load of `/` had TTFB 19,413 ms (FCP 19,524, LCP 20,048) — the HTML document request stalled
~19 s once in 18 navigations; the cause (edge, local network) was not determined. The median excludes it.

### Reading against Core Web Vitals thresholds

- LCP is "good" (< 2.5 s) on all three routes, cold and warm. LCP elements are text paragraphs
  (`/`: `p.text-xs text-fg-muted`; `/studio` and `/benchmarks`: the page description `p.mt-0.5 max-w-3xl`).
- CLS is "good" (< 0.1) on `/` and `/studio` but **"poor" (> 0.25) on `/benchmarks`** in every run.

### `/benchmarks` layout shift — attribution

One cold load with `layout-shift` source attribution:

| t (ms) | value | shifted node |
|---:|---:|---|
| 1089 | 0.012 | `#cross-engine`, `#ac-reference` pushed down 48 px |
| 1105 | 0.019 | `#stormrisk`, `#cross-engine`, `#ac-reference` pushed down 48 px |
| 1303 | 0.084 | `#ac-reference` pushed out of the viewport |
| 2249 | 0.182 | `#cross-engine` pushed out of the viewport |
| 5498 | 0.327 | `#stormrisk` pushed out of the viewport |

Cause: the page fetches 22 API resources in a waterfall (health → 5 artifact listings at ~1.19 s → 17
artifact bodies) and panels grow as each body arrives. The last six — the full `pypsa/scigrid-de-*` result
artifacts — finish at 5.0–6.9 s. Each is 288–299 KB gzip / ~1.24 MB decoded; together 1,758,162 B on the wire,
fetched only to render summary rows.

## JS bundle (cold, per file, Brotli `encodedBodySize`)

| Chunk | Wire | Decoded | Loaded on |
|---|---:|---:|---|
| `index-DBmpEuvw.js` (entry) | 352,998 | 1,057,317 | all |
| `SchematicBadge-NkSDT8xA.js` (contains MapLibre GL — its stack frames appear in this chunk) | 299,052 | 1,075,494 | `/` |
| `maplibre-gl-worker-Boc9pDRP.mjs` | 149,696 | 519,547 | `/` |
| `research-tO8qcd0Z.js` | 103,909 | 341,052 | `/benchmarks` |
| `ExplorerPage-BVGb5mfm.js` | 7,084 | 20,378 | `/` |
| `StudioPage-DhE77Upe.js` | 8,157 | — | `/studio` |
| `jsx-runtime`, `scales`, `NetworkSelect`, `useMutation`, `play`, `pause` | 261–3,566 each | | various |

Caching: `/assets/*` is served `Content-Encoding: br`, `Cache-Control: public, max-age=31536000, immutable`
(hence 0 JS bytes warm); the HTML is `max-age=0, must-revalidate` with `X-Vercel-Cache: HIT`.

## Map time-to-loaded

`/` (Grid Explorer), ms from navigation start, medians of 3:

| Mode | map created | MapLibre `load` | first `idle` |
|---|---:|---:|---:|
| cold | 1309 | 2198 | 2313 |
| warm | 941 | 1384 | 1497 |

Cold `load` per run: 3267, 2198, 1854 ms.

`/runs/ac207ce7-a300-48d8-89b0-1ab393badb18` (6 desktop + 6 mobile cold loads): in the 4 healthy desktop loads
`load` fired at 2045–4543 ms. In 2 desktop loads the page crashed (`Style is not done loading`, see
`docs/audit/accessibility.md` M1). On mobile (Pixel 7) `load` fired at 3871–4187 ms in 3 loads and had not
fired within networkidle + 2 s in the other 3.

## API latency (curl, gzip accepted, 5 requests each, warm instance)

| Endpoint | Median total | Range | Wire | Decoded |
|---|---:|---:|---:|---:|
| `GET /health` | 280 ms | 258–554 ms | 99 B | 86 B |
| `GET /api/v1/networks` | 311 ms | 277–540 ms | 2,106 B | 6,345 B |
| `GET /api/v1/networks/scigrid-de/geojson` | 383 ms | 329–593 ms | 44,328 B | 464,252 B |

TCP connect to the Cloudflare edge took 49–75 ms and TLS completed at 96–117 ms (3 samples), so roughly
180–200 ms of each request is edge→Render origin plus server time. The GeoJSON response has no
`Cache-Control` or `ETag` header (`cf-cache-status: DYNAMIC`), so every map load refetches 44 KB.

**Cold start: not measured.** The instance was already warm at the first request of the session (282 ms);
it restarted twice for redeploys during the session but never idled long enough to spin down, so no
true Render cold start was observed. Measure it after ≥ 15 min of zero traffic.

## Recommendations (priority order)

1. `/benchmarks` CLS: reserve panel heights (fixed-height skeletons matching the loaded layout) and stop
   fetching six ~1.24 MB `pypsa/scigrid-de-*` artifacts for summary rows — serve a compact summary endpoint/artifact.
2. Fix the `/runs/<id>` map readiness race (crash in 2 of 6 desktop loads); see the accessibility audit M1.
3. Entry chunk is 353 KB Brotli / 1.06 MB decoded on every route. Its contents were not inspected; run a bundle
   visualizer and move libraries that `/studio` and `/benchmarks` do not need into lazy chunks. Also check the
   Rollup chunk naming that puts MapLibre in `SchematicBadge-*.js`.
4. Add `Cache-Control` (e.g. `public, max-age=3600`) and an `ETag` to the network GeoJSON response, which has
   neither. Artifact responses already send `Cache-Control: public, max-age=300` (no `ETag`;
   Cloudflare still reports `cf-cache-status: DYNAMIC`).
5. Add `Timing-Allow-Origin: https://gridstorm.vercel.app` on the API so Resource Timing can attribute API bytes in
   future measurements.

## Fixes applied (2026-11-15)

The live numbers above were **not** re-measured after these changes. The "local" figures below come from
the same workstation: HEAD `1247767` ("before") and the fixed build ("after"), both served by
`vite preview` and proxying to one local API (`uv run uvicorn gridstorm_api.main:app --port 8130`).
They used Playwright 1.65.1 with headless Chromium, 3 cold loads per cell, and CLS observed from
`layout-shift` entries for 3 s after `networkidle`. The local API answers in milliseconds, so one variant
holds every `/api/v1/**` request for 300 ms to approximate the live waterfall. They are not comparable
with the live table.

1. **`/benchmarks` CLS** (`features/research/pages/BenchmarksPage.tsx`):
   - **Reserved height:** while a panel shows its loading skeleton (`aria-busy="true"`), its body
     reserves one viewport height (`has-[[aria-busy=true]]:min-h-svh`). Loaded panels on this page are
     650–9,100 px tall depending on width (measured locally at 360–1920 px), so the panels below start
     off-screen. Their growth as artifacts arrive is therefore not a visible shift. The reservation drops
     as soon as content renders.
   - **Summary view:** the PyPSA preset table now requests
     `GET /api/v1/artifacts/pypsa/{id}?view=summary`, which returns `{artifact, summary}`. The header is
     unchanged, so provenance and the payload sha256 stay visible in the artifact metadata. The summary
     holds only `schema_version, scenario_id, scenario_hash, network_id, provenance, engine, solver,
     outcome, metrics, warnings`, with no `assets`, `series` or `snapshots`. It is only available for
     `kind=simulation`; other kinds get 422 `summary_view_unsupported`.

   | Local CLS (CWV window), 3 cold loads | before | after |
   |---|---|---|
   | desktop 1440×900, API +300 ms | 0.485, 0.467, 0.491 | 0.0002, 0.0002, 0.0002 |
   | Pixel 7, API +300 ms | 0.414, 0.443, 0.443 | 0, 0, 0 |
   | desktop 1440×900, no added delay | 0.302, 0.485, 0.485 | 0.0002, 0.0002, 0.0002 |

   | Local bytes per `/benchmarks` load (decoded response bodies, 21 API requests) | before | after |
   |---|---:|---:|
   | 11 `pypsa/*` artifact responses | 7,537,819 B | 28,900 B |
   | all API responses | 8,572,894 B | 1,063,975 B |

   `scigrid-de-baseline`: the full document is 1,242,689 B and its summary view is 2,764 B.
   Regression tests: `pages.test.tsx` "loads only the summary view of PyPSA simulations and keeps provenance
   and sha visible" and "reserves a viewport height in every panel while it is loading (CLS)". On the API
   side, `services/api/tests/test_http_caching.py` covers the summary view.
2. **`/runs/<id>` map crash.** Fixed by tracking readiness per map instance; see `docs/audit/accessibility.md` →
   *Fixes applied* (M1). With the networks list held until the first map has loaded
   (`e2e/run-map.spec.ts`), the before build showed "Something went wrong / Style is not done loading." (1 run)
   and the after build passed 4 of 4 runs.
3. **API caching** (`services/api/src/gridstorm_api/caching.py`):
   - `GET /api/v1/networks`, `/networks/{id}`, `/networks/{id}/assets`, `/networks/{id}/geojson`,
     `/artifacts` and `/artifacts/{engine}/{id}` (both views) send `Cache-Control: public, max-age=3600`
     and `ETag: "<sha256 of the response body>"`.
   - A matching `If-None-Match` returns an empty 304. The comparison is weak, so a `W/` tag that a proxy
     weakened after compression still matches. Error responses carry neither header.
   - Artifact responses previously sent `max-age=300` and no `ETag`.
   - Local check: the geojson, network detail, assets and artifact URLs each return `304` with 0 B for
     `If-None-Match: W/<etag>`.

   Whether Cloudflare in front of Render then caches these responses at the edge was not checked.

Not addressed here: the entry-chunk size (recommendation 3) and `Timing-Allow-Origin` (recommendation 5).
