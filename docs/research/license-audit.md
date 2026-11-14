# Licence audit — upstream repositories and runtime dependencies

Audit date 2026-11-14. Repo SHAs: [`source-inventory.md`](source-inventory.md) /
[`upstream-manifest.json`](upstream-manifest.json). Every claim below cites the file and line(s)
inspected in the clone at `D:/New folder (4)/upstream/<name>` at the pinned SHA, or the metadata
file of the installed package. GridStorm's root licence is MIT (`LICENSE` L1-3); individual packages
may declare other terms (e.g. `apps/web/package.json` declares Apache-2.0), so the root licence is
not a replacement for component or third-party notices.

Not legal advice; this is an engineering compliance record.

## 1. Upstream repositories

| Repo | Licence evidence (file : lines) | SPDX | NOTICE file | Obligations if GridStorm reuses | Verdict |
|---|---|---|---|---|---|
| openinframap | `LICENSE` L1-11 ("Copyright Open Infrastructure Map contributors", BSD 3-clause conditions); `web/LICENSE` L1-5 ("Copyright 2017-2021 Russ Garrett", same terms) | BSD-3-Clause | none | Keep copyright + conditions + disclaimer with the reused table | adapt-with-attribution |
| pypsa-eur-map-viewer | no LICENSE/COPYING in `git ls-files` (79 files); `package.json` has no `license`; GitHub API `license: null`; `README.md` L19 "License: MIT" under "About the PyPSA-Eur Dataset" (L11) | none (code) | none | None granted → cannot copy code | concepts-only |
| grid2game | `LICENSE` L1 "Mozilla Public License Version 2.0" (373 lines) | MPL-2.0 | none | File-level copyleft on ported files | concepts-only |
| energy-sdk-l2rpn | `license.txt` L1-3 Apache 2.0, appendix L190 "Copyright 2022 NVIDIA Corporation"; `nvgridui/license.txt` identical; deps `nvgridui/DEPENDENCIES.md` L1-15, `nvgridui/package-licenses.txt` L76 (pyzmq BSD/LGPL) | Apache-2.0 | none | Apache §4 notice + state changes | concepts-only |
| CoogGrid-Houston | `LICENSE` L1 "MIT License", L3 "Copyright (c) 2026 Jordan Otomu and CoogGrid Houston contributors"; `README.md` L188-190 | MIT | none | Keep notice | concepts-only |
| PyPSA | `LICENSE` L1 "MIT License", L3 "Copyright (c) 2015-2026 PyPSA contributors"; `REUSE.toml` L21-29 `examples/**.{csv,json,nc}` → CC-BY-4.0; headers e.g. `pypsa/__init__.py` L1-3 SPDX MIT | MIT; examples CC-BY-4.0 | none | MIT notice (dependency, unmodified); CC-BY attribution for example networks | reuse-code |
| pandapower | `LICENSE` L1 "BSD 3-Clause License", L3-5 "Copyright (c) 2016-2026 University of Kassel, 2016-2026 Fraunhofer IEE", L10 ff. BSD-3 conditions; `pyproject.toml` L18, L26 | BSD-3-Clause (GitHub: NOASSERTION, multi-holder) | none | Notice on redistribution | reuse-code |
| grid2op | `LICENSE.md` L1 MPL-2.0; `LicensesInformation.md` L5-11 SPDX MPL-2.0; per-file header `grid2op/__init__.py` (first comment block: RTE copyright + `SPDX-License-Identifier: MPL-2.0`) | MPL-2.0 | none | Unmodified dependency: provide source pointer; modified MPL files stay MPL | reuse-code |
| PowerModels.jl | `LICENSE.md` L1-5 (Los Alamos National Security LLC, DE-AC52-06NA25396; L5 "redistribution and use in source and binary forms..." BSD-3 conditions) | BSD-3-Clause (GitHub: NOASSERTION) | none | — (not used) | concepts-only |
| simbench | `LICENSE` L1 copyright (Univ. Kassel, TU Dortmund, RWTH Aachen, Fraunhofer IEE); L5-6 database "Open Database License"; L7-8 contents "Database Contents License"; L11-33 code 3-clause BSD | BSD-3-Clause (code) AND ODbL-1.0 + DbCL-1.0 (data) | none | Code: BSD notice. Data: ODbL attribution; derived databases distributed publicly must be ODbL (share-alike) | reuse-code |
| andes | `LICENSE` L3 "Copyright (c) 2015-2026 Hantao Cui", L6-8 "GNU General Public License ... either version 3 of the License, or (at your option) any later version"; `pyproject.toml` L10 `GPL-3.0-or-later` | GPL-3.0-or-later | none | Distribution of a derivative combined work may require GPL terms; GridStorm policy excludes this runtime | concepts-only (never import) |
| pypsa-earth | no root LICENSE; `REUSE.toml` L3 `AGPL-3.0-or-later`, L23-26 `data/**` CC-BY-4.0; `scripts/solve_network.py` L2-4 SPDX AGPL-3.0-or-later; `LICENSES/` AGPL-3.0-or-later, CC-BY-4.0, CC0-1.0 | AGPL-3.0-or-later (code) | none | Network-service copyleft | concepts-only |
| power-grid-data-factory | no licence file in 398 tracked files; `grep -i licen` over `pyproject.toml`, `README.md` → no hits; GitHub API `license: null` | none | none | None granted | concepts-only |
| GOCompetition/Evaluation | 34 tracked files, none a licence; `grep -ri "licen\|copyright"` over *.py/*.md/*.txt → no hits; GitHub API `license: null` | none | none | None granted | concepts-only |
| GOC3Benchmark.jl | `LICENSE.md` L1 "Copyright © 2019, Triad National Security, LLC", L6 "This program is open source under the BSD-3 License." | BSD-3-Clause | none | — (not used) | concepts-only |
| demandcast | `LICENSE` L1-2 "GNU AFFERO GENERAL PUBLIC LICENSE Version 3" (661 lines); `README.md` L10 badge, L92-94 "licensed under the GNU Affero General Public License v3.0 (AGPL-3.0)" — no "or later" grant | AGPL-3.0-only | none | Copyleft and network-source requirements for covered/derivative works; excluded by project policy | do-not-use |
| PyPSA-Explorer | `LICENSE` L1 "MIT License", L3 "Copyright (c) 2025 OET Network Viewer contributors"; `pyproject.toml` L13 `license = "MIT"` | MIT | none | Keep notice in ported files + THIRD_PARTY_NOTICES | adapt-with-attribution |
| pypsa-eur | no root LICENSE; `REUSE.toml` L1-4 package info, L6-13 docs/test data CC-BY-4.0, L15-27 config/env files CC0-1.0, L32-51 `data/*` CC-BY-4.0, L53-58 CC0-1.0, further blocks CC-BY-4.0 and one CC-BY-SA-4.0 (L124-129, `data/ch_cantons.csv`, Wikipedia contributors); code headers e.g. `scripts/solve_network.py` L1-3, `Snakefile` L1-3 SPDX MIT; `LICENSES/{MIT,CC-BY-4.0,CC-BY-SA-4.0,CC0-1.0}.txt` | MIT (code) AND CC-BY-4.0 AND CC-BY-SA-4.0 AND CC0-1.0 | none | Run unmodified → no code obligations; downloaded data per `doc/data_inventory.csv` (L3 `osm` ODbL-1.0; L41 powerplants, L42 costs, L45 natura CC-BY-4.0; L10-11 NUTS EU reuse policy) | reuse-code (external workflow) |
| Warden | `LICENSE` L1 "MIT License", L3 "Copyright (c) 2026 Eklavya Goyal" | MIT | none | Keep notice if reused | concepts-only |
| grid2viz | `LICENSE` L1 MPL-2.0; `LicensesInformation.md` L1-11 (RTE copyright, SPDX MPL-2.0); per-file e.g. `grid2viz/src/kpi/EpisodeAnalytics.py` L1-3 | MPL-2.0 | none | File-level copyleft on ported files | concepts-only |
| pglib-opf | `LICENSE` L1-6 "Data License: Creative Commons Attribution 4.0", L9-30 "Software License: MIT ... Copyright (c) 2017 A Library of IEEE PES Power Grid Benchmarks"; per-case e.g. `pglib_opf_case14_ieee.m` L17-19 "Copyright (c) 1999 by Richard D. Christie, University of Washington ... Creative Commons Attribution 4.0" | CC-BY-4.0 (data) AND MIT (software) | none | CC-BY attribution of each case file used | reuse-code (data) |

No repository ships a `NOTICE` file (checked with `git ls-files | grep -i notice`). Apache-2.0 §4(d)
therefore imposes no NOTICE propagation for energy-sdk-l2rpn (which is not reused anyway).

## 2. Focus items

### pypsa-eur-map-viewer — code vs data
* **Code**: no licence. Under default copyright the code may be read but not copied, modified or
  redistributed. GridStorm copies nothing (no hits for `map-viewer` in GridStorm code).
* **Data**: `public/data/*.csv` are fetched by `scripts/fetch-data.mjs` L4 from Zenodo record
  14144752. The README (L19) calls this "MIT", but the authoritative Zenodo metadata
  (`https://zenodo.org/api/records/14144752` → `license.id = "odc-odbl"`) is **ODbL-1.0**, consistent
  with the data being OpenStreetMap-derived. Any use of those CSVs needs "© OpenStreetMap contributors"
  attribution and ODbL share-alike for derived databases.

### grid2viz / grid2game — MPL-2.0 file-level
MPL-2.0 §3 binds only the *covered files*: a ported file must remain MPL-2.0 with its header and its
source available; the rest of GridStorm stays MIT. GridStorm ported nothing; it re-implemented KPI
definitions (`docs/audit/grid2viz-audit.md`; `workers/grid2op/src/gridstorm_grid2op/kpis.py`).
Using `grid2op` and `lightsim2grid` unmodified does not relicense GridStorm's separate files.
When distributing executable covered software, MPL §3.2 also requires making the covered source
available and informing recipients how to obtain it; a source pointer must lead to the matching source.

### demandcast — AGPL
AGPL-3.0 §13 requires a modified program that supports remote interaction to offer its corresponding
source to remote users. Whether a larger service is a derivative work depends on how code is
incorporated; importing code does not automatically relicense unrelated programs. GridStorm's
policy excludes demandcast code rather than depending on that boundary. Verdict **do-not-use**;
additionally its README L45 states the retrieved demand data are not redistributable.

### openinframap — web code vs styles vs data
* Root `LICENSE` and `web/LICENSE` are both BSD-3-Clause. `web/package.json` L18 says `"ISC"` — an
  inconsistency in upstream metadata; the explicit `web/LICENSE` text governs, and GridStorm reproduces
  that BSD-3 text in `THIRD_PARTY_NOTICES.md`.
* The style definitions (`web/src/style/*.ts`) are part of the BSD-3 web code. GridStorm adapts only
  the voltage colour table from `web/src/style/style_oim_power.ts`.
* Fonts: `web/public/fonts/` Noto Sans glyph PBFs, no licence file in the repo (Noto is SIL OFL-1.1
  upstream [INFERENCE]). Not used by GridStorm.
* Data: openinframap.org tiles are OSM (ODbL-1.0); attribution `© OpenStreetMap` in
  `web/src/style/style.ts` L64. GridStorm does not use these tiles; its basemap is OpenFreeMap
  (`apps/web/src/components/map/NetworkMap.tsx` L33-40, with OpenFreeMap / OpenMapTiles / OSM
  attribution).

### energy-sdk-l2rpn — Apache-2.0 + deps
Apache-2.0 (`license.txt`). Dependencies per `nvgridui/DEPENDENCIES.md`: ipyvuetify, ipyleaflet (MIT),
notebook, voila (BSD), matplotlib (PSF-style), ipympl, numba (BSD-2), black (MIT), grid2op and
lightsim2grid (MPL-2.0). The frozen list `nvgridui/package-licenses.txt` contains one LGPL entry (L76,
pyzmq "BSD; LGPL"). `nvgridui/voila/` vendors minified JS. Not reused.

### Warden — MIT (verified)
`LICENSE` L1/L3 MIT, Eklavya Goyal 2026. Reuse would be legally fine with notice, but its agent path
calls the Anthropic API (`requirements.txt` L17 `anthropic>=0.25`, `src/config.py` L53), which GridStorm
forbids. Nothing reused.

### CoogGrid-Houston — MIT (verified)
`LICENSE` L1/L3 MIT; README L188-190 confirms. Its map uses `tile.openstreetmap.org` raster tiles
(`src/components/map/NeighborhoodMap.tsx` L59), which would require OSM attribution and compliance with
the OSMF tile usage policy. Nothing reused.

### SciGRID example network (PyPSA)
PyPSA's `REUSE.toml` L21-29 licenses example data under CC-BY-4.0 (PyPSA Contributors). The
scigrid-de notebook (`docs/examples/scigrid-lopf-then-pf.ipynb`, "Data sources") states the grid is
"Based on SciGRID which is based on OpenStreetMap". OSM data are ODbL-1.0, so GridStorm attributes both
PyPSA (CC-BY-4.0) and "© OpenStreetMap contributors" for `scigrid-de` [INFERENCE: whether ODbL
obligations survive SciGRID's processing was not confirmed from a SciGRID primary source; attributing
OSM is the conservative choice].

## 3. Runtime dependencies (verified from installed metadata)

Python: `License-Expression` / `License` / classifier fields of `*.dist-info/METADATA` in the GridStorm
component venvs (`<component>/.venv/Lib/site-packages`). JavaScript: `license` field of
`apps/web/node_modules/<pkg>/package.json`.

| Package | Version | Env | Licence (metadata) |
|---|---|---|---|
| pypsa | 1.4.0 | core, pipelines | MIT (`License: MIT License`) |
| linopy | 0.10.1 | core | MIT (classifier) |
| highspy (HiGHS) | 1.16.0 | core | MIT (`License-Expression`); ships `THIRD_PARTY_NOTICES.md` |
| pandas | 3.1.1 / 2.3.3 | core / pandapower-family | BSD-3-Clause |
| numpy | 2.4.6 | all | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| scipy | 1.17.1 | all | BSD (classifier) |
| xarray | 2026.9.0 | core | Apache-2.0 |
| netcdf4 | 1.7.5.1.post1 | core | MIT |
| networkx | 3.6.1 | all | BSD-3-Clause |
| geopandas / shapely / pyproj / pyogrio | 1.2.0 / 2.2.0 / 3.7.2 / 0.13.0 | core | BSD-3 / BSD-3 / MIT / MIT |
| dask | 2026.8.0 | core | BSD-3-Clause |
| matplotlib | 3.11.2 | core | PSF-style matplotlib licence |
| pyarrow | 26.0.1 | core | Apache-2.0 (ships NOTICE.txt) |
| polars | 2.1.0 | core | MIT |
| pandapower | 3.5.6 | pandapower, advisor, grid2op, distribution, stormbench, stormml | BSD (classifier) |
| pandera | 0.36.0 | pandapower-family | MIT |
| numba | 0.68.1 | pandapower-family | BSD |
| matpowercaseframes | 2.1.1 | pandapower | metadata says MIT; bundled `LICENSE.rst` is the BSD-style "MATPOWER Case Frames License" (PSST/AMES fork, Battelle) |
| grid2op | 1.12.6 | grid2op | MPL-2.0 |
| lightsim2grid | 1.3.1 | grid2op | MPL-2.0 (classifier) |
| simbench | 1.6.3 | distribution | BSD (code); data ODbL-1.0 |
| scikit-learn / joblib | 1.9.1 / 1.6.0 | stormml | BSD-3-Clause |
| fastapi | 0.162.7 | core | MIT |
| starlette / uvicorn | 1.10.0 / 0.54.0 | core | BSD-3-Clause |
| pydantic / pydantic-core | 2.14.3 / 2.50.4 | all | MIT |
| sqlalchemy | 2.0.57 | core | MIT |
| **psycopg / psycopg-binary** | 3.3.9 | core | **LGPL-3.0-only** — used unmodified via dynamic import; LGPL permits this; keep it replaceable (it is a normal wheel dependency) |
| pyjwt / cryptography | 2.15.1 / 50.0.2 | core | MIT / Apache-2.0 OR BSD-3-Clause |
| boto3 / botocore / s3transfer | 1.44.3 / 1.44.3 / 0.19.3 | core | Apache-2.0 |
| pyyaml | 6.0.3 | core | MIT |
| httpx | 0.28.1 | core | BSD-3-Clause |
| requests | 2.34.2 | grid2op | Apache-2.0 (ships NOTICE) |
| tqdm | 4.70.1 | all | MPL-2.0 AND MIT |
| psutil | 7.2.2 | core | BSD-3-Clause |
| react / react-dom | 19.3.1 | web | MIT |
| maplibre-gl | 6.18.0 | web | BSD-3-Clause (`LICENSE.txt`; includes mapbox-gl-js ≤ v1.13 BSD-3 notice L32-36) |
| echarts | 6.1.0 | web | Apache-2.0 (`LICENSE`, `NOTICE`) |
| zrender | 6.1.0 | web | BSD-3-Clause |
| @tanstack/react-query | 5.107.1 | web | MIT |
| katex | 0.19.1 | web | MIT |
| lucide-react | 1.73.0 | web | ISC |
| radix-ui | 1.8.1 | web | MIT |
| react-router | 8.5.1 | web | MIT |
| tailwindcss / vite (build only) | 4.3.5 / 8.3.8 | web | MIT |
| tslib | 2.3.0 | web (echarts dep) | 0BSD |

The audited direct runtime packages above do not declare GPL/AGPL as their primary package licence.
This does **not** establish absence of copyleft in bundled native code. In addition to MPL-covered
Grid2Op/LightSim2Grid/tqdm and LGPL-3.0 psycopg, Shapely bundles GEOS (LGPL-2.1), and offline
LightSim2Grid bundles LGPL-2.1-or-later SuiteSparse components. See deployment scope below.

## 4. Data and service licences used at run time

| Source | Licence | Where | Attribution shown |
|---|---|---|---|
| PyPSA example networks (ac-dc-meshed, scigrid-de) | CC-BY-4.0 (PyPSA `REUSE.toml` L21-29); scigrid-de OSM-derived | `data/networks/` via network-import | dataset manifest `license` block; UPSTREAM_ATTRIBUTION.md |
| PGLib-OPF v23.07 cases | CC-BY-4.0 (per-file copyright holders) | network-import, stormbench, stormml | UPSTREAM_ATTRIBUTION.md |
| MATPOWER IEEE case files (case9-case300) | MATPOWER `LICENSE`: case files "not covered by the BSD license"; IEEE cases from UW PSTCA | `workers/pandapower/reference_data/matpower/` (validation inputs only) | UPSTREAM_ATTRIBUTION.md |
| PyPSA-Eur Belgium tutorial build | OSM grid ODbL-1.0 + CC-BY-4.0 inputs | `pipelines/pypsa-eur` | UPSTREAM_ATTRIBUTION.md |
| SimBench | ODbL-1.0 / DbCL-1.0 | `workers/distribution`; derived results `data/artifacts/distribution/*.json` embed `source.license` | UPSTREAM_ATTRIBUTION.md |
| Grid2Op `l2rpn_case14_sandbox` | MPL-2.0 (grid2op-datasets repo), downloaded, not redistributed | `workers/grid2op/src/gridstorm_grid2op/env.py` L116-123 | artifact `dataset.license` |
| OpenFreeMap tiles (OpenMapTiles schema, OSM data) | OSM ODbL-1.0; OpenMapTiles attribution | `apps/web/src/components/map/NetworkMap.tsx` L40-47 | map attribution control |
| OPSD time series 2020-10-06 / NASA POWER Hourly API v2.10.4 | per `pipelines/observed/src/gridstorm_observed/sources.py` L35-71; OPSD datapackage declares no data licence and ENTSO-E-derived redistribution permission is **not established** (`data/observed/opsd-de/manifest.json`) | `data/observed/` | manifest `license`/`attribution` fields; `docs/research/external-data-sources.md` |

`services/api/Dockerfile` L60 and L63 copy `database/` and `data/` into the Render image, but the
root `.dockerignore` allow-list sends only `data/networks/` and `data/artifacts/` (plus
`database/{migrations,dev,seeds}/`) to the build context. The image therefore redistributes the
committed PGLib, PyPSA-example (incl. OSM-derived SciGRID), SimBench-derived and Grid2Op-derived
files with their manifest/artifact licence blocks; `data/observed/` is **not** in the image.

## 5. Deployment scope and bundled native code (2026-11-15)

`services/api/Dockerfile` L18-26 and L34-35 performs frozen, non-development syncs of the API
lockfile; L59 copies the installed environment unchanged. It does not install the offline Grid2Op,
pandapower or distribution worker environments. The following distinction is material:

| Component | Evidence | Core API Docker dependency payload? |
|---|---|---|
| psycopg / psycopg-binary 3.3.9 | `services/api/uv.lock` packages `psycopg` and `psycopg-binary`; each wheel's `licenses/LICENSE.txt` L1-2 LGPL v3 | Yes; unmodified wheel installation |
| GEOS 3.14.1 bundled by Shapely 2.2.0 | core lock package `shapely`; Linux wheel `shapely-2.2.0.dist-info/licenses/LICENSE_GEOS` L1-6 identifies GEOS, LGPLv2.1; wheel contains `libgeos-*.so.3.14.1` and `libgeos_c-*.so.1.20.5` | Yes; unmodified bundled shared libraries |
| SuiteSparse BTF / CXSparse / KLU bundled by LightSim2Grid 1.3.1 | installed `lightsim2grid-1.3.1.dist-info/licenses/SuiteSparse/{BTF,CXSparse,KLU}/Doc/License.txt`, each introductory grant names LGPL 2.1 or later (BTF L8-11, CXSparse L8-11, KLU L11-14); accompanying `lesser.txt` contains full LGPLv2.1 | No; offline Grid2Op environment only |

Matching CPython 3.11 manylinux x86_64 wheels for Shapely, psycopg-binary, Pyogrio and Pyproj were
downloaded and inspected as ZIP archives. Exact filenames, SHA-256s, licence texts and notices are
in `THIRD_PARTY_NOTICES.md` under "Linux deployment wheel". This is lockfile/wheel evidence, not
an inspection of the running Render image or of every Debian base-image package.

The wheel licences/notices remain installed in `site-packages/*.dist-info/licenses`; nothing in
the Dockerfile strips them. Unmodified usage does not remove binary-redistribution obligations:
preserve applicable corresponding-source access and replacement/relinking rights. Root notices
are provided separately; the Dockerfile currently copies only its explicit app/data paths, not
the root notice document.

**Open binary-provenance item (bounded inspection):** the psycopg-binary Linux wheel contains
`libcrypt-bc2db45e.so.1` and `libkeyutils-dfe70bd6.so.1.5` but no individual notices identifying
their exact source builds. Libxcrypt's upstream
[`LICENSING` L3-5](https://github.com/besser82/libxcrypt/blob/develop/LICENSING) grants LGPL-2.1-or-later;
the keyutils library's
[`keyutils.c` L3-9](https://github.com/Distrotech/keyutils/blob/master/keyutils.c) credits Red Hat /
David Howells and grants LGPL version 2 or later. Mapping those upstream grants to these exact
binary builds is unverified. Do not claim psycopg and GEOS exhaust all LGPL contents of the image.
Mitigation option: use non-binary `psycopg` plus system `libpq` in Docker and retain the system
distribution's corresponding copyright/source records. That option is recorded, not implemented.

Pyogrio's inspected Linux wheel contains `gdal_data/LICENSE.TXT`, `gdal_data/copyright`,
`proj_data/copyright` and its own MIT licence; Pyproj contains its MIT/PROJ notices. Those inspected
texts contain no LGPL grant. This observation is not a blanket licence claim about every optional
GDAL driver or future wheel.

