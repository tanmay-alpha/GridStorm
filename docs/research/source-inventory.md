# Upstream source inventory

Audit date 2026-11-14. All 21 repositories were cloned read-only with
`git clone --filter=blob:none` into `D:/New folder (4)/upstream/<name>` (outside the GridStorm repo).
Machine-readable form: [`upstream-manifest.json`](upstream-manifest.json). Licence evidence and
obligations: [`license-audit.md`](license-audit.md).

How each column was obtained:

* **SHA / commit date** — `git -C <clone> rev-parse HEAD` and `git log -1 --format=%cI` on the clone.
* **Release** — `gh api repos/<owner>/<repo>/releases/latest` (tag + publish date); "—" = no GitHub release.
* **Language / last push** — `gh api repos/<owner>/<repo>` (`language`, `pushed_at`).
* **Tests** — number of tracked files matching `tests?/`, `test_*.py|jl` or `*.test.ts|js`
  (`git ls-files | grep -ciE ...`).
* **Key paths** — verified to exist with `git ls-files -- <path>` at the pinned SHA.

Verdicts: **reuse-code** (used as an unmodified dependency, data source or workflow),
**adapt-with-attribution** (code ported/adapted into GridStorm with headers + notices),
**concepts-only** (ideas only, no code/data copied), **do-not-use**.

## Summary

| # | Repository | Pinned SHA | Commit date | Latest release | Lang | Tests | Licence (SPDX) | Verdict |
|---|---|---|---|---|---|---|---|---|
| 1 | openinframap/openinframap | `780e6b96d9d465d9e8cd751db7ebcfc80230bfd6` | 2026-11-03 | — | TypeScript | 1 | BSD-3-Clause | adapt-with-attribution |
| 2 | oalles/pypsa-eur-map-viewer | `b73f584db986af9b05fdc1ada61238784b29cbb0` | 2026-02-09 | — | TypeScript | 0 | **none** (code); data ODbL-1.0 | concepts-only |
| 3 | Grid2op/grid2game | `d54084ddf387baa46870cce398e8a91f6281ee74` | 2022-07-05 | — | Python | 3 | MPL-2.0 | concepts-only |
| 4 | NVIDIA/energy-sdk-l2rpn | `e110d2eda69492c6be064d19e7cfbceb4fbe5ab4` | 2022-05-17 | — | Python | 0 | Apache-2.0 | concepts-only |
| 5 | jordanotomu/CoogGrid-Houston | `bc38e84a3cb1b63a3e129785a91c88bbfed3d7f3` | 2026-05-19 | — | TypeScript | 0 | MIT | concepts-only |
| 6 | PyPSA/PyPSA | `0b2a4c849a3e9a8cb617a5f3188e3eaa0f4317bf` | 2026-11-13 | v1.4.0 (2026-10-09) | Python | 331 | MIT (examples data CC-BY-4.0) | reuse-code |
| 7 | e2nIEE/pandapower | `1a5301a469d2278b97a4291c3d35cd472a7113ff` | 2026-11-13 | v3.5.6 (2026-10-07) | Python | 470 | BSD-3-Clause | reuse-code |
| 8 | Grid2op/grid2op | `07012c4f19cac81662df1df54122568c64d8fe09` | 2026-11-01 | v1.12.6 (2026-10-14) | Python | 224 | MPL-2.0 | reuse-code |
| 9 | lanl-ansi/PowerModels.jl | `4c14405670fe85596388a23320ad9d3660e1c033` | 2026-10-28 | v0.21.7 (2026-10-08) | Julia | 88 | BSD-3-Clause | concepts-only |
| 10 | e2nIEE/simbench | `876e7a7be470258cefa524a36eeb08293008b5dc` | 2026-09-22 | v1.6.3 (2026-09-22) | Python | 55 | BSD-3-Clause (code) + ODbL-1.0/DbCL-1.0 (data) | reuse-code |
| 11 | CURENT/andes | `eda5163c9ee8d19945a1dd5d1771fec5da608c27` | 2026-03-11 | v1.6.2 release object (2022-03-27); tag v2.0.0 on HEAD | Python | 56 | GPL-3.0-or-later | concepts-only |
| 12 | pypsa-meets-earth/pypsa-earth | `36192492955ce9bbb21faeceaba29301e14b281c` | 2026-11-13 | v0.10.0 (2026-10-22) | Python | 11 | AGPL-3.0-or-later (data CC-BY-4.0) | concepts-only |
| 13 | ORNL/power-grid-data-factory | `a7bd2c9622a3e60cbabc469c2a33591b8a65c997` | 2026-11-04 | — | Python | 46 | **none** | concepts-only |
| 14 | GOCompetition/Evaluation | `6449d3c58616a49be1787726b308ef00f42e7b10` | 2020-03-09 | — | Python | smoke scripts | **none** | concepts-only |
| 15 | lanl-ansi/GOC3Benchmark.jl | `588f3566ab29df240622a9a98c758af1bfc66bb1` | 2024-10-30 | — | Julia | 6 | BSD-3-Clause | concepts-only |
| 16 | open-energy-transition/demandcast | `c7d9f1dd32394b0a84001cc1dcc3410a73086e1d` | 2026-11-13 | v2.0.0 (2026-11-06) | Python | 197 | AGPL-3.0-only | do-not-use |
| 17 | open-energy-transition/PyPSA-Explorer | `c85252c98cab742b43245a18bcd310d095bab443` | 2026-09-03 | v0.1.2 (2026-09-03) | Python | 8 | MIT | adapt-with-attribution |
| 18 | PyPSA/pypsa-eur | `c8209014468dbb3bf43257f45d34abc6e3c8c898` | 2026-09-25 | v2026.09.0 (2026-09-25) | Python | 32 | MIT code; CC-BY-4.0 / CC-BY-SA-4.0 / CC0-1.0 docs+data (REUSE) | reuse-code (external workflow) |
| 19 | eklavyagoyal/energy-hackathon-2026-submission ("Warden") | `1e9ee209e9e00734343f9891e2033f43ce9d1f73` | 2026-06-14 | — | Python | 22 | MIT | concepts-only |
| 20 | Grid2op/grid2viz | `b416eba406b9ef45b103e546b5a593d846420b4f` | 2023-10-10 | 1.3 (2021-12-21) | Python | 146 | MPL-2.0 | concepts-only |
| 21 | power-grid-lib/pglib-opf | `dc6be4b2f85ca0e776952ec22cbd4c22396ea5a3` | 2023-07-24 | v23.07 (2023-07-24) | MATLAB | 0 | CC-BY-4.0 (data) + MIT (software) | reuse-code (data) |

Notes on the table:

* `pandapower` and `pypsa-earth`: `git describe --tags` on the HEAD of the default branch returns an
  older tag (`v3.4.0`, `v0.8.0`) because release tags live on release branches; the GitHub release API
  value is authoritative and matches PyPI (`pandapower 3.5.6`).
* `pypsa-eur` is checked out at the `v2026.09.0` release commit — the SHA pinned by
  `pipelines/pypsa-eur/build.sh` L10-11.
* Activity: inactive repos (no commit in > 2 years) are grid2game (2022-07), energy-sdk-l2rpn (2022-05),
  GOCompetition/Evaluation (2020-03), grid2viz (2023-10), pglib-opf (2023-07, stable benchmark release).

## Per repository

### 1. openinframap/openinframap — adapt-with-attribution
* Layout: `web/` (MapLibre front end, TypeScript), `web-backend/src/`, `tegola/` (vector-tile server
  config), `schema/`, `web-router/`.
* Key paths: `web/src/style/style_oim_power.ts` (`voltage_scale` L33, `special_voltages` L44,
  stepwise `voltage_color` L82-97), `web/src/style/style.ts` (sources + attribution strings L15-84).
* Assets: `web/public/fonts/` — 512 Noto Sans glyph PBF files without a licence file in the repo
  (Noto fonts are published under SIL OFL-1.1 [INFERENCE, not stated in this repo]);
  `web/src/icons/*.svg` covered by the repo BSD-3 licence.
* Data: the tiles served by openinframap.org are OpenStreetMap data (ODbL-1.0,
  `web/src/style/style.ts` L64 `© OpenStreetMap` attribution). GridStorm uses neither tiles nor data.
* Reusable: voltage → colour table (pure data). Risky: nothing; licence is permissive.
* GridStorm use: `apps/web/src/lib/scales.ts` L4-10 adapts the voltage colour table (header cites SHA
  and path).

### 2. oalles/pypsa-eur-map-viewer — concepts-only
* 79 tracked files: Vite/React app (`src/map/layers/acLinesLayer.ts`, `blackoutLayer.ts`,
  `busesLayer.ts`, `src/lib/graph.ts`, `src/hooks/*`), `scripts/fetch-data.mjs` (downloads from
  Zenodo record 14144752, L4), bundled `public/data/{buses,lines,links,transformers,converters}.csv`,
  `public/basemap-style.json`.
* **No software licence**: no LICENSE/COPYING file, no `license` in `package.json`, GitHub API
  `license: null`. The only licence statement is `README.md` L19 "License: MIT", inside the section
  "About the PyPSA-Eur Dataset" (L11-25) — it describes the dataset, not the viewer code, and it is
  wrong: Zenodo record 14144752 ("Prebuilt Electricity Network for PyPSA-Eur based on OpenStreetMap
  Data", v0.6, 2024-11-13) declares licence `odc-odbl` (queried via
  `https://zenodo.org/api/records/14144752`).
* Verdict: code is all-rights-reserved → do not copy; bundled CSVs are ODbL data.

### 3. Grid2op/grid2game — concepts-only
* Dash app: `grid2game/envs/env.py`, `grid2game/tree/envTree.py` (episode branching tree),
  `grid2game/plot/plot_grid.py`, `grid2game/_utils/*`.
* MPL-2.0; inactive. Reviewed in `docs/audit/grid2viz-audit.md`; nothing ported.

### 4. NVIDIA/energy-sdk-l2rpn — concepts-only
* `nvgridui/nvgrid/actionrecommender.py`, `nvgridui/nvgrid/app.py`, `nvgridui/nvapp/mapcomponent.py`
  (ipyleaflet map), `nvgridui/voila/` (vendored Voilà/Vue JS), `nvgridui/app-notebook.ipynb`.
* Apache-2.0 (`license.txt`; copy at `nvgridui/license.txt`); no NOTICE file. Dependency licences
  self-declared in `nvgridui/DEPENDENCIES.md` and `nvgridui/package-licenses.txt` (L76: pyzmq
  "BSD; LGPL").
* Jupyter/Voilà architecture does not fit GridStorm (FastAPI + React). Concept only: operator map with
  ranked remedial actions.

### 5. jordanotomu/CoogGrid-Houston — concepts-only
* Vite/React: `src/simulation/{engine,battery,solar,allocator,equity,p2p}.ts`,
  `src/components/map/NeighborhoodMap.tsx` (OSM raster tiles L59), `src/components/SimNarration.tsx`,
  `src/data/{neighborhoods,scenarios}.ts`, `public/fifth_ward_3d.html`.
* MIT. Distribution-level neighbourhood DER/battery sim; no tests. Not used by GridStorm.

### 6. PyPSA/PyPSA — reuse-code (dependency)
* Key paths: `pypsa/network/`, `pypsa/network/power_flow.py`, `pypsa/optimization/optimize.py`,
  `pypsa/optimization/abstract.py`, `pypsa/statistics/`, `pypsa/examples.py` (`scigrid_de` L147-174).
* Example networks: `examples/networks/{ac-dc-meshed,model-energy,scigrid-de,stochastic-network,storage-hvdc}`;
  REUSE.toml L21-29 licenses `examples/**.{csv,json,nc}` as CC-BY-4.0.
* GridStorm: `pypsa==1.4.0` in core/pipelines/stormrisk/observed envs; networks `ac-dc-meshed`,
  `scigrid-de` (contract §2).

### 7. e2nIEE/pandapower — reuse-code (dependency)
* Key paths: `pandapower/run.py`, `pandapower/contingency/`, `pandapower/converter/pypower/from_ppc.py`,
  `pandapower/networks/`, `pandapower/timeseries/`, `pandapower/shortcircuit/`, `pandapower/estimation/`.
* GridStorm: `pandapower==3.5.6` in pandapower/advisor/grid2op/distribution/stormbench/stormml envs;
  `from_ppc` used by `packages/stormbench/src/stormbench/pp_bridge.py` and
  `packages/stormml/src/stormml/cases.py`.

### 8. Grid2op/grid2op — reuse-code (dependency)
* Key paths: `grid2op/Environment/`, `grid2op/Runner/`, `grid2op/Backend/pandaPowerBackend.py`,
  `grid2op/Action/`, `grid2op/Observation/`, `grid2op/Agent/`, `grid2op/Episode/`.
* GridStorm: `grid2op==1.12.6` + `lightsim2grid==1.3.1` in `workers/grid2op`; dataset
  `l2rpn_case14_sandbox` downloaded at run time, not redistributed (`workers/grid2op/src/gridstorm_grid2op/env.py` L117-123).

### 9. lanl-ansi/PowerModels.jl — concepts-only
* `src/form/dcp.jl`, `src/form/acp.jl`, `src/prob/opf.jl`, `src/prob/pf.jl`, `src/io/matpower.jl`,
  `src/core/data.jl`. Formulation reference for DC/AC OPF; Julia, not used at run time.

### 10. e2nIEE/simbench — reuse-code (dependency + data)
* `simbench/networks/`, `simbench/converter/`. GridStorm: `simbench==1.6.3` in `workers/distribution`.
* Code BSD-3, database ODbL-1.0 + DbCL-1.0 (see licence audit).

### 11. CURENT/andes — concepts-only
* `andes/routines/pflow.py`, `andes/routines/tds.py`, `andes/models/`, `andes/cases/`.
* GPL-3.0-or-later — must not be imported into any GridStorm env.

### 12. pypsa-meets-earth/pypsa-earth — concepts-only
* `Snakefile`, `scripts/build_osm_network.py`, `scripts/base_network.py`, `scripts/solve_network.py`.
* AGPL-3.0-or-later code; not used.

### 13. ORNL/power-grid-data-factory — concepts-only
* `src/grid_data_factory/` (98 modules: `acquisition/`, `boundaries/`, `campaigns/`, `cli/`, ...),
  `configs/*.yaml`, `tests/`.
* No licence anywhere → all rights reserved. Ideas recorded in `docs/research/tool-decision-matrix.md`.

### 14. GOCompetition/Evaluation — concepts-only
* `evaluation.py`, `data.py`, `run.py`, `examples/case2/`. No licence; inactive since 2020.

### 15. lanl-ansi/GOC3Benchmark.jl — concepts-only
* `src/scheduler.jl`, `src/opf.jl`, `src/ac_uc_solver.jl`, `scripts/eval.jl`. BSD-3; Julia.

### 16. open-energy-transition/demandcast — do-not-use
* `demandcast/forecast.py`, `demandcast/ml_models/` (`lstm.py`, `evaluation.py`),
  `demandcast/retrievals/`, `demandcast/benchmark/`.
* AGPL-3.0. Demand data are not redistributable (README L45).

### 17. open-energy-transition/PyPSA-Explorer — adapt-with-attribution
* `src/pypsa_explorer/callbacks/visualizations.py`, `src/pypsa_explorer/utils/helpers.py`,
  `src/pypsa_explorer/utils/network_loader.py`, `src/pypsa_explorer/layouts/components.py`.
* GridStorm: analytics logic ported into `services/analytics/src/gridstorm_analytics/` (5 files with
  upstream headers).

### 18. PyPSA/pypsa-eur — reuse-code (external workflow)
* `Snakefile`, `rules/retrieve.smk`, `scripts/base_network.py`, `scripts/build_osm_network.py`,
  `scripts/solve_network.py`, `config/test/config.electricity.yaml`, `envs/environment.yaml`,
  `envs/default_*.pin.txt`.
* GridStorm: `pipelines/pypsa-eur/build.sh` executes the unmodified workflow at the pinned SHA in a
  pixi container; `config.gridstorm.yaml` is a no-op restatement.

### 19. Warden (eklavyagoyal/energy-hackathon-2026-submission) — concepts-only
* `src/engine/{scan,cascade,remediation,severity,network,preflight}.py`, `src/grid/pypsa_eur_loader.py`,
  `src/integrations/grid2op_adapter.py`, `src/timeseries/`, `src/api/` (FastAPI), `src/agent/` (LLM loop).
* MIT. Optional Anthropic LLM narration (`requirements.txt` L15-17, `src/config.py` L49-53) — conflicts
  with GridStorm's no-LLM rule. No GridStorm file derives from Warden (grep for `warden|energy-hackathon`
  over GridStorm code returns no hits).

### 20. Grid2op/grid2viz — concepts-only
* `grid2viz/src/kpi/{EpisodeAnalytics,EpisodeTrace,actions_model,observation_model}.py`,
  `grid2viz/src/simulation/`, `grid2viz/src/{overview,macro,micro,episodes}/`.
* MPL-2.0 file-level. KPI concepts re-implemented (not ported) in
  `workers/grid2op/src/gridstorm_grid2op/kpis.py`; full audit `docs/audit/grid2viz-audit.md`.

### 21. power-grid-lib/pglib-opf — reuse-code (data)
* `pglib_opf_case{14,30,57,118,300}_ieee.m` (+ `api/`, `sad/` variants, `BASELINE.md`).
* GridStorm: parsed by `pipelines/network-import/src/network_import/{matpower,pglib}.py`,
  `packages/stormbench/src/stormbench/matpower.py`, `packages/stormml/src/stormml/cases.py`
  (`PGLIB_FILES` L31-36). Parsers are written from the MATPOWER format spec (no code copied).
