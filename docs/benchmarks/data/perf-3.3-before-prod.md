Measured 2026-11-17T11:33:15.047Z · web https://gridstorm.vercel.app · API https://gridstorm-api.onrender.com (backend commit f8b3c28) · medians of 3 (browser) / 5 (API)

**desktop** 1440×900, CPU 1×

| Route | HTTP | Content ms | LCP ms | CLS (total) | Grid ms | JS KB | Total KB | Requests (API) | Long tasks ms (n) | Settled ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `/` | 200 | 976 | 1204 | 0.0011 (0.0011) | n/a | 387 | 415 | 19 (6) | 64 (1) | 2362 |
| `/explore?network=pglib-case14-ieee` | 200 | 865 | 1084 | 0.0164 (0.0164) | 1306 | 393 | 427 | 19 (8) | 52 (1) | 2382 |
| `/explore?network=scigrid-de` | 200 | 796 | 1016 | 0.0171 (0.0171) | 1814 | 684 | 3208 | 39 (4) | 532 (6) | 3843 |
| `/studio` | 200 | 1127 | 1136 | 0.0218 (0.0218) | n/a | 393 | 428 | 18 (4) | 0 (0) | 2095 |
| `/runs/c328baa0-718e-4cad-9538-e376d2972df2` | 200 | 1021 | 1764 | 0.0013 (0.0013) | 1993 | 414 | 468 | 37 (15) | 202 (2) | 3047 |
| `/compare?comparison=4f5661ec-e6f1-4600-96ed-710709f10c36` | 200 | 955 | 1316 | 0.0165 (0.0165) | 1682 | 412 | 454 | 32 (11) | 204 (2) | 2735 |
| `/workbench` | 200 | 857 | 844 | 0.0002 (0.0002) | n/a | 398 | 443 | 13 (4) | 0 (0) | 2323 |
| `/benchmarks` | 200 | 740 | 740 | 0.0002 (0.0002) | n/a | 486 | 557 | 20 (8) | 114 (2) | 2403 |
| `/data` | 200 | 799 | 836 | 0.0002 (0.0002) | n/a | 372 | 404 | 8 (2) | 52 (1) | 2027 |
| `/data/opsd-de-load-forecast` | 200 | 991 | 996 | 0.0002 (0.0002) | n/a | 387 | 415 | 15 (4) | 55 (1) | 2250 |

**mobile** 390×844, CPU 4×

| Route | HTTP | Content ms | LCP ms | CLS (total) | Grid ms | JS KB | Total KB | Requests (API) | Long tasks ms (n) | Settled ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `/` | 200 | 1409 | 1400 | 0.0021 (0.0021) | n/a | 387 | 416 | 19 (6) | 815 (4) | 2904 |
| `/explore?network=pglib-case14-ieee` | 200 | 1672 | 2000 | 0.0021 (0.0021) | 2351 | 393 | 427 | 19 (8) | 1107 (8) | 2858 |
| `/explore?network=scigrid-de` | 200 | 1558 | 1752 | 0.0296 (0.0317) | 3472 | 684 | 1487 | 23 (4) | 1711 (13) | 3996 |
| `/studio` | 200 | 1769 | 2012 | 0.0021 (0.0021) | n/a | 393 | 428 | 18 (4) | 812 (4) | 2304 |
| `/runs/c328baa0-718e-4cad-9538-e376d2972df2` | 200 | 1570 | 1572 | 0.0021 (0.0021) | 3850 | 414 | 468 | 37 (15) | 2515 (10) | 4423 |
| `/compare?comparison=4f5661ec-e6f1-4600-96ed-710709f10c36` | 200 | 1198 | 1256 | 0.0021 (0.0021) | 3063 | 412 | 454 | 32 (11) | 1801 (7) | 3619 |
| `/workbench` | 200 | 1589 | 1588 | 0.0021 (0.0021) | n/a | 398 | 437 | 12 (3) | 791 (4) | 2112 |
| `/benchmarks` | 200 | 1576 | 1668 | 0.0021 (0.0021) | n/a | 486 | 528 | 14 (2) | 1011 (4) | 2091 |
| `/data` | 200 | 1468 | 1460 | 0.0021 (0.0021) | n/a | 372 | 404 | 8 (2) | 770 (4) | 1980 |
| `/data/opsd-de-load-forecast` | 200 | 2039 | 2044 | 0.0021 (0.0021) | n/a | 387 | 415 | 15 (4) | 1973 (6) | 2563 |

**API** (first /health of the run: 321 ms, HTTP 200)

| Endpoint | HTTP | Median ms | Min–max ms | Median TTFB ms | Body bytes (decoded) | Encoding | Cache-Control |
|---|---|---:|---:|---:|---:|---|---|
| `/health` | 200 | 192 | 184–205 | 192 | 86 | br | — |
| `/api/v1/networks` | 200 | 193 | 188–517 | 192 | 13461 | gzip | public, max-age=3600 |
| `/api/v1/networks/pglib-case14-ieee/geojson` | 200 | 192 | 185–201 | 192 | 9738 | gzip | public, max-age=3600 |
| `/api/v1/networks/scigrid-de/geojson` | 200 | 477 | 277–814 | 222 | 464252 | gzip | public, max-age=3600 |
| `/api/v1/artifacts?include=header` | 200 | 197 | 187–204 | 194 | 93543 | gzip | public, max-age=3600 |
| `/api/v1/data/catalog` | 200 | 193 | 190–205 | 192 | 60163 | gzip | public, max-age=300 |
| `/api/v1/data/catalog/opsd-de-load-forecast` | 200 | 186 | 183–189 | 186 | 6685 | gzip | public, max-age=300 |
