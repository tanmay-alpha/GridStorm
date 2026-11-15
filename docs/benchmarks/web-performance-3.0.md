# Explorer performance — GridStorm 3.0 (2026-11-15)

Local production builds (`npx vite build`) served with `vite preview`, proxying `/api` to the same
local API (`services/api`, SQLite, 127.0.0.1:8130, shared with other agents during the run). Same
workstation (Windows, 24 logical CPUs), Chromium headless with SwiftShader WebGL, 1440×900, no
throttling. The basemap for geographic networks is the live OpenFreeMap tile server (internet).

- **Before**: the working tree at the start of this work (base `ae4ee9a`; Explorer/map code unchanged) (`.dist-ExplorerMaps-before`, port 5174).
- **After**: the 3.0 Explorer (`.dist-ExplorerMaps`, port 4174).

Reproduce (each build served with `GRIDSTORM_API_PROXY=http://127.0.0.1:8130 npx vite preview --outDir <dir> --port <p>`):

```sh
cd apps/web
node scripts/explorer-perf.mjs --base http://127.0.0.1:<p> --reps 3 --label <before|after> --out <file>.json
```

Raw results: [`data/explorer-perf-3.0-before.json`](data/explorer-perf-3.0-before.json),
[`data/explorer-perf-3.0-after.json`](data/explorer-perf-3.0-after.json). Tables show medians of 3.

**Time to useful map (TTUM)** = navigation (or select change) → the target network is drawn: for
MapLibre, rendered buses all belong to the target and cover ≥ 90 % of its buses; for the schematic,
the SVG reports `data-ready="true"` for that network with every bus element present. Requests and
transferred bytes (Playwright `request.sizes()`, body + headers) settle at network idle and include
JS, styles, map style/sprites/glyphs/tiles. Heap = `usedJSHeapSize` after forced GC.

## What changed

1. **Schematic networks (IEEE 14/118) no longer load MapLibre.** They render through an SVG
   schematic (`components/map/schematic/`). MapLibre (≈1.07 MB JS, worker, basemap style) is now a
   lazy chunk (`LazyNetworkMap`) fetched only for geographic networks.
2. **Network layers are added on `style.load`, not `load`.** MapLibre's `load` waits for every
   initial basemap tile; the network (local GeoJSON) therefore appeared only after the tile server
   answered. Geographic TTUM no longer depends on tile latency.
3. **The MapLibre instance is kept alive (hidden) across schematic networks**, so returning to a
   geographic network reuses its WebGL context, style and tiles instead of rebuilding the map.
4. **Run/compare maps (`BranchValueMap`) read coordinate kind from the catalog** and fetch GeoJSON
   + the unit tables they draw instead of all nine canonical tables; nothing is created under a
   guessed kind (the old schematic→geographic map re-creation is gone).

Trade-off: schematic networks now fetch their generator, storage-unit, load and carrier tables up
front (4 small requests: +4.0 kB API wire for IEEE 14, +4.2 kB for IEEE 118) to draw units at buses.
The drawing itself is ready from the GeoJSON alone; units appear when their tables arrive.

## Cold load (fresh context per rep)

| Network | TTUM before → after | Requests before → after | Wire (all) before → after | API wire before → after | Heap before → after |
|---|---:|---:|---:|---:|---:|
| pglib-case14-ieee | 574 → 459 ms | 13 → 16 | 678,190 → 415,819 B | 9,349 → 13,372 B | 11.1 → 6.5 MB |
| pglib-case118-ieee | 593 → 478 ms | 13 → 16 | 683,223 → 421,073 B | 14,382 → 18,626 B | 11.5 → 8.1 MB |
| ac-dc-meshed | 12,853 → 1,045 ms | 27 → 28 | 2,004,951 → 2,028,813 B | 8,291 → 8,291 B | 17.2 → 16.2 MB |
| scigrid-de | 6,328 → 1,059 ms | 32 → 33 | 2,802,679 → 2,826,466 B | 52,433 → 52,433 B | 21.0 → 19.8 MB |
| pypsa-eur-be | 25,483 → 1,063 ms | 26 → 27 | 2,170,605 → 2,194,095 B | 9,968 → 9,968 B | 16.6 → 16.2 MB |

TTUM samples (ms): case14 610/572/574 → 736/447/459; case118 593/588/600 → 437/482/478;
ac-dc-meshed 12,853/13,460/7,884 → 1,520/1,045/1,003; scigrid-de 37,369/1,682/6,328 → 1,055/1,142/1,059;
pypsa-eur-be 20,656/30,203/25,483 → 1,023/1,064/1,063.

**Caveat on geographic cold loads.** The before run was ~15 minutes earlier than the after run and
OpenFreeMap tile latency was visibly high then (seconds per tile batch). Because the before build
gated the network on `load` (all initial tiles), its geographic TTUM measures the tile server as much
as GridStorm; the after build is independent of tile latency by construction. The size of the
improvement is therefore condition-dependent; the direction is structural. Not claimed: a field
latency distribution, or that all-request bytes improved for geographic networks (they did not:
same tiles, +1 request for the lazy MapLibre chunk).

## Network switching (one page: ac-dc-meshed → …)

| # | Target | Before | After | API requests before → after |
|---:|---|---:|---:|---:|
| 1 | pglib-case118-ieee | 189 ms | 133 ms | 2 → 6 |
| 2 | scigrid-de | 31,865 ms | 243 ms | 3 → 2 |
| 3 | ac-dc-meshed (cached) | 302 ms | 249 ms | 1 → 0 |
| 4 | pglib-case14-ieee | 290 ms | 175 ms | 2 → 6 |
| 5 | pglib-case118-ieee (cached) | 55 ms | 63 ms | 1 → 0 |
| 6 | scigrid-de (cached) | 632 ms | 217 ms | 1 → 0 |
| 7 | ac-dc-meshed (cached) | 257 ms | 285 ms | 0 → 0 |

Before, switch #2 rebuilt the MapLibre map (schematic → geographic kind change) and waited for its
basemap tiles; after, the map created for ac-dc-meshed is reused (#2, #6).

**Cached geographic → geographic switch (the earlier 117 → 273 ms regression).** It is not
eliminated: 249–285 ms after vs 257–302 ms before in this run, with zero API requests. A probe on the
after build (switching ac-dc-meshed ↔ scigrid-de repeatedly on one page) measured 86–214 ms with the
live basemap and **39–58 ms with basemap tile requests aborted**. The remaining cost is MapLibre
loading/parsing basemap tiles for the new viewport in the same worker pool as the network GeoJSON
tiles, not GridStorm data loading or React. Further reduction would need per-network GeoJSON sources
(kept tiled) or a lighter basemap; not done here.

## Leak check after the switch walk

Exactly one MapLibre container and one WebGL canvas after every walk, no page errors; post-GC heap
23.8 / 23.8 / 23.8 MB before → 21.3 / 22.4 / 22.7 MB after.

## Production route vitals before / after the 3.0 release

`apps/web/scripts/measure-routes.mjs` against https://gridstorm.vercel.app + https://gridstorm-api.onrender.com
(warm API), Chromium headless, 1440×900, no throttling, fresh context per rep, discarded warm-up
navigation, medians of 3. Before: web `dpl_fbnkrtGtHYTcVeMir2Psy9QgB3fB` / API `dd185d1`
([data](data/routes-before-prod.json)). After: web from `main` `cf482f2` / API `cf482f2`
([data](data/routes-after-prod.json)). Same machine and network, about 50 minutes apart; public
internet and basemap-tile latency vary, so differences under ~150 ms in FCP/LCP are noise.

| Route | FCP ms | LCP ms | CLS | Requests (API) | KB | Heap MB |
|---|---|---|---|---|---|---|
| `/` | 540 → 652 | 860 → 956 | 0.0002 → 0.0002 | 7 (1) → 10 (1) | 371 → 390 | 4.4 → 4.5 |
| `/explore` IEEE-14 | 632 → 344 | 1120 → 836 | 0.0275 → 0.0254 | 13 (4) → 17 (8) | 680 → 419 | 9.9 → 5.7 |
| `/explore` SciGRID | 568 → 332 | 1060 → 868 | 0.0309 → 0.0309 | 32 (4) → 29 (4) | 2754 → 2498 | 17.9 → 15.6 |
| `/studio` | 524 → 612 | 1012 → 1448 | 0.0002 → **0.0505** | 14 (4) → 17 (4) | 392 → 417 | 4.9 → 5.3 |
| `/benchmarks` | 612 → 544 | 924 → 860 | 0.0002 → 0.0002 | 32 (23) → 18 (8) | 605 → 540 | 9.9 → 9.6 |
| `/contingency` | 628 → 548 | 1504 → 1448 | **0.2288 → 0.0021** | 15 (6) → 16 (6) | 508 → 543 | 7.0 → 7.3 |
| `/methods` | 624 → 980 | 984 → 1336 | 0.0003 → 0.0003 | 29 (15) → 18 (3) | 763 → 593 | 8.2 → 6.8 |
| `/workbench` (new) | — → 532 | — → 844 | — → 0.0044 | — → 12 (4) | — → 437 | — → 5.3 |
| `/mitigation` (new) | — → 608 | — → 920 | — → 0.0002 | — → 17 (1) | — → 425 | — → 4.7 |

Improvements: `/contingency` layout shift fixed; IEEE-14 Explorer transfers 38 % less and uses
42 % less heap; `/benchmarks` and `/methods` API fan-out cut from 23 → 8 and 15 → 3 requests.
Regressions: `/studio` CLS 0.0002 → 0.0505 (still "good" < 0.1; cause not yet profiled) and LCP
+436 ms; `/methods` FCP/LCP +350 ms in this sample. IEEE-14
makes 4 more small API requests (unit tables for schematic symbols). The SciGRID "settled" time is
dominated by basemap tiles (11.9 s and 30.3 s in two samples) and is not a page-readiness metric.
The cached geographic network switch is unchanged (see above).
