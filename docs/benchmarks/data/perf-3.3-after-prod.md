Measured 2026-11-17T19:37:10.499Z · web https://gridstorm.vercel.app · API https://gridstorm-api.onrender.com (backend commit 565aea3) · medians of 3 (browser) / 5 (API)

**desktop** 1440×900, CPU 1×

| Route | HTTP | Content ms | LCP ms | CLS (total) | Grid ms | JS KB | Total KB | Requests (API) | Long tasks ms (n) | Settled ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `/` | 200 | 692 | 748 | 0.0011 (0.0011) | n/a | 174 | 203 | 20 (6) | 0 (0) | 2236 |
| `/explore?network=pglib-case14-ieee` | 200 | 644 | 880 | 0.0043 (0.0043) | 1096 | 183 | 217 | 20 (8) | 0 (0) | 2120 |
| `/explore?network=scigrid-de` | 200 | 643 | 852 | 0.0089 (0.0089) | 1676 | 473 | 2998 | 40 (4) | 727 (7) | 3952 |
| `/studio` | 200 | 955 | 1000 | 0.0002 (0.0002) | n/a | 180 | 215 | 19 (4) | 0 (0) | 1939 |
| `/runs/c328baa0-718e-4cad-9538-e376d2972df2` | 200 | 1054 | 1532 | 0.0002 (0.0002) | 1707 | 422 | 476 | 40 (15) | 120 (2) | 2743 |
| `/compare?comparison=4f5661ec-e6f1-4600-96ed-710709f10c36` | 200 | 755 | 1108 | 0.0165 (0.0165) | 1467 | 418 | 460 | 35 (11) | 98 (1) | 2597 |
| `/workbench` | 200 | 729 | 732 | 0.0002 (0.0002) | n/a | 185 | 230 | 13 (4) | 0 (0) | 2279 |
| `/benchmarks` | 200 | 745 | 756 | 0.0002 (0.0002) | n/a | 488 | 560 | 22 (8) | 74 (1) | 2352 |
| `/data` | 200 | 738 | 760 | 0.0002 (0.0002) | n/a | 160 | 193 | 9 (2) | 0 (0) | 1948 |
| `/data/opsd-de-load-forecast` | 200 | 996 | 1008 | 0.0002 (0.0002) | n/a | 402 | 455 | 26 (8) | 159 (2) | 2239 |

**mobile** 390×844, CPU 4×

| Route | HTTP | Content ms | LCP ms | CLS (total) | Grid ms | JS KB | Total KB | Requests (API) | Long tasks ms (n) | Settled ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `/` | 200 | 1389 | 1376 | 0.0021 (0.0021) | n/a | 174 | 203 | 20 (6) | 730 (4) | 2891 |
| `/explore?network=pglib-case14-ieee` | 200 | 1045 | 1240 | 0.0021 (0.0021) | 1545 | 183 | 217 | 20 (8) | 622 (7) | 2521 |
| `/explore?network=scigrid-de` | 200 | 1223 | 1496 | 0.0296 (0.0317) | 2947 | 473 | 1630 | 30 (4) | 2305 (17) | 4545 |
| `/studio` | 200 | 1327 | 1664 | 0.0021 (0.0021) | n/a | 180 | 215 | 19 (4) | 579 (4) | 2347 |
| `/runs/c328baa0-718e-4cad-9538-e376d2972df2` | 200 | 1413 | 1416 | 0.0021 (0.0021) | 2923 | 422 | 476 | 40 (15) | 1604 (10) | 3637 |
| `/compare?comparison=4f5661ec-e6f1-4600-96ed-710709f10c36` | 200 | 1046 | 1052 | 0.0021 (0.0038) | 2580 | 418 | 460 | 35 (11) | 1349 (8) | 3462 |
| `/workbench` | 200 | 1025 | 1012 | 0.0021 (0.0021) | n/a | 185 | 230 | 13 (4) | 562 (5) | 2629 |
| `/benchmarks` | 200 | 958 | 1120 | 0.0021 (0.0021) | n/a | 488 | 560 | 22 (8) | 1547 (11) | 3078 |
| `/data` | 200 | 1143 | 1140 | 0.0021 (0.0021) | n/a | 160 | 193 | 9 (2) | 557 (4) | 2347 |
| `/data/opsd-de-load-forecast` | 200 | 1835 | 1836 | 0.0021 (0.0021) | n/a | 402 | 455 | 26 (8) | 1715 (8) | 2988 |

**API** (first /health of the run: 359 ms, HTTP 200)

| Endpoint | HTTP | Median ms | Min–max ms | Median TTFB ms | Body bytes (decoded) | Encoding | Cache-Control |
|---|---|---:|---:|---:|---:|---|---|
| `/health` | 200 | 198 | 192–326 | 198 | 86 | br | — |
| `/api/v1/networks` | 200 | 198 | 192–218 | 197 | 13461 | gzip | public, max-age=3600 |
| `/api/v1/networks/pglib-case14-ieee/geojson` | 200 | 193 | 182–221 | 193 | 9738 | gzip | public, max-age=3600 |
| `/api/v1/networks/scigrid-de/geojson` | 200 | 298 | 272–364 | 275 | 464252 | gzip | public, max-age=3600 |
| `/api/v1/artifacts?include=header` | 200 | 205 | 202–207 | 202 | 93543 | gzip | public, max-age=3600 |
| `/api/v1/data/catalog` | 200 | 200 | 189–234 | 197 | 69848 | gzip | public, max-age=300 |
| `/api/v1/data/catalog/opsd-de-load-forecast` | 200 | 198 | 194–202 | 197 | 6685 | gzip | public, max-age=300 |
