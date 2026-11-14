# Upstream attribution

GridStorm builds on the open-source projects and open datasets below. For each: licence, the pinned
revision GridStorm was built against, what is used and how. Full licence texts and required notices:
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md). Audit trail (all 21 repositories reviewed,
including those **not** used): [`docs/research/license-audit.md`](docs/research/license-audit.md),
[`docs/research/source-inventory.md`](docs/research/source-inventory.md),
[`docs/research/upstream-manifest.json`](docs/research/upstream-manifest.json).

"Reused files" lists every GridStorm file that copies or adapts upstream code or data, as verified on
2026-11-14 by searching the repository for `Derived from` / `Adapted from` / `upstream repo:` headers,
`UPSTREAM_LICENSE*` files, and by byte-comparing committed data files with the upstream clones.
Integration owners append to these lists when they add derived files.

## Libraries and workflows used unmodified

### PyPSA — MIT
* Repo: https://github.com/PyPSA/PyPSA — release v1.4.0 (PyPI `pypsa==1.4.0`); audited HEAD
  `0b2a4c849a3e9a8cb617a5f3188e3eaa0f4317bf`.
* Use: power-system modelling and linear optimal power flow (`pypsa.Network`, `n.optimize`,
  `n.statistics`) in the core API, PyPSA worker, analytics, network-import, storm-risk and observed
  pipelines. Library is imported, never modified or vendored.
* Copyright (c) 2015-2026 PyPSA contributors.

### linopy — MIT · HiGHS / highspy — MIT
* `linopy==0.10.1` (optimisation model builder used by PyPSA), `highspy==1.16.0` (HiGHS LP/MIP
  solver). Used unmodified as PyPSA's modelling layer and solver.

### pandapower — BSD-3-Clause
* Repo: https://github.com/e2nIEE/pandapower — release v3.5.6 (PyPI `pandapower==3.5.6`); audited HEAD
  `1a5301a469d2278b97a4291c3d35cd472a7113ff`.
* Use: AC power flow, N-1 contingency analysis, MATPOWER/PYPOWER conversion
  (`pandapower.converter.pypower.from_ppc`) in `workers/pandapower`, `workers/advisor`,
  `workers/distribution`, `packages/stormbench`, `packages/stormml`. Unmodified.
* Copyright (c) 2016-2026 University of Kassel and Fraunhofer Institute for Energy Economics and Energy
  System Technology (IEE), Kassel.

### Grid2Op — MPL-2.0 · LightSim2Grid — MPL-2.0
* Repo: https://github.com/Grid2op/grid2op — release v1.12.6 (PyPI `grid2op==1.12.6`); audited HEAD
  `07012c4f19cac81662df1df54122568c64d8fe09`. `lightsim2grid==1.3.1` (https://github.com/Grid2op/lightsim2grid).
* Use: sequential operation episodes in `workers/grid2op` (environment, runner, agents). Used
  unmodified; MPL-2.0 source is available at the URLs above. No Grid2Op file is copied or modified.
* Copyright (c) 2019-2020 RTE (https://www.rte-france.com).

### SimBench (Python package) — BSD-3-Clause; SimBench data — ODbL-1.0 / DbCL-1.0
* Repo: https://github.com/e2nIEE/simbench — release v1.6.3 (`simbench==1.6.3`), audited HEAD
  `876e7a7be470258cefa524a36eeb08293008b5dc`.
* Use: distribution benchmark grids loaded at run time in `workers/distribution`.
* Copyright (c) 2019-2026 University of Kassel, TU Dortmund, RWTH Aachen University and Fraunhofer IEE.
  The SimBench database is made available under the Open Database License (ODbL-1.0); individual
  contents under the Database Contents License (DbCL-1.0). Any derived SimBench database published by
  GridStorm must credit SimBench and be offered under ODbL-1.0.

### PyPSA-Eur — MIT (code), CC-BY-4.0 / CC-BY-SA-4.0 / CC0-1.0 (docs, bundled data)
* Repo: https://github.com/PyPSA/pypsa-eur — tag `v2026.09.0`, commit
  `c8209014468dbb3bf43257f45d34abc6e3c8c898` (pinned in `pipelines/pypsa-eur/build.sh` L10-11).
* Use: `pipelines/pypsa-eur/build.sh` runs the **unmodified** upstream Snakemake workflow (Belgium
  tutorial electricity configuration; `pipelines/pypsa-eur/config.gridstorm.yaml` is a no-op
  restatement) inside a container and copies only the resulting network. No PyPSA-Eur source file is
  copied into GridStorm.
* Data in a built network: transmission grid from OpenStreetMap (`base_network: osm`; PyPSA-Eur
  `doc/data_inventory.csv` L3: ODbL-1.0) — "© OpenStreetMap contributors"; power plants
  (powerplantmatching, CC-BY-4.0), technology costs (technology-data, CC-BY-4.0) and other inputs per
  `doc/data_inventory.csv`.
* Copyright: Contributors to PyPSA-Eur (https://github.com/pypsa/pypsa-eur).

## Code adapted into GridStorm

### PyPSA-Explorer — MIT
* Repo: https://github.com/open-energy-transition/PyPSA-Explorer — commit
  `c85252c98cab742b43245a18bcd310d095bab443` (release v0.1.2).
* Use: analytical logic of the Dash callbacks (capacity, CAPEX/OPEX, energy balance, network summary,
  carrier/country helpers) ported onto `pypsa.Network.statistics` and returning JSON tables; all
  Plotly/Dash rendering removed. Each file states upstream paths, SHA and modifications.
* Copyright (c) 2025 OET Network Viewer contributors; modifications Copyright (c) 2026 GridStorm
  contributors (MIT).

#### Reused files
| GridStorm file | Upstream source (at `c85252c9…`) |
|---|---|
| `services/analytics/src/gridstorm_analytics/_common.py` | `src/pypsa_explorer/utils/helpers.py` (`get_carrier_nice_name`, `get_country_options`, `get_country_filter`), `src/pypsa_explorer/utils/network_loader.py` (`get_unique_carriers`) |
| `services/analytics/src/gridstorm_analytics/capacity.py` | `src/pypsa_explorer/callbacks/visualizations.py` (`update_capacity_charts`) |
| `services/analytics/src/gridstorm_analytics/costs.py` | `src/pypsa_explorer/callbacks/visualizations.py` (`update_capex_charts`, `update_opex_charts`) |
| `services/analytics/src/gridstorm_analytics/energy_balance.py` | `src/pypsa_explorer/callbacks/visualizations.py` (`create_energy_balance_callback`) |
| `services/analytics/src/gridstorm_analytics/summary.py` | `src/pypsa_explorer/layouts/components.py` (`create_header`), `src/pypsa_explorer/utils/helpers.py` (`summarize_network`, `get_bus_carrier_options`, …) |
| `services/analytics/src/gridstorm_analytics/UPSTREAM_LICENSE_PyPSA-Explorer.txt` | `LICENSE` (verbatim MIT text) |

### Open Infrastructure Map — BSD-3-Clause
* Repo: https://github.com/openinframap/openinframap — commit
  `780e6b96d9d465d9e8cd751db7ebcfc80230bfd6`.
* Use: the voltage → colour threshold table and the stepwise colour-expression idea from
  `web/src/style/style_oim_power.ts` (`voltage_scale`, `special_voltages`, `voltage_color`). No
  openinframap tiles, OSM data, fonts or other code are used.
* Copyright 2017-2021 Russ Garrett; Copyright Open Infrastructure Map contributors.

#### Reused files
| GridStorm file | Upstream source |
|---|---|
| `apps/web/src/lib/scales.ts` (`VOLTAGE_SCALE`, header L4-10) | `web/src/style/style_oim_power.ts` |

## Data used

### PGLib-OPF — CC-BY-4.0 (data), MIT (software)
* Repo: https://github.com/power-grid-lib/pglib-opf — release v23.07, commit
  `dc6be4b2f85ca0e776952ec22cbd4c22396ea5a3`.
* Use: OPF benchmark cases imported as GridStorm networks (`pipelines/network-import`), screened by
  StormBench, labelled by StormML and used as pandapower reference inputs. GridStorm's MATPOWER parsers
  are independent implementations from the MATPOWER format specification.
* Attribution: "IEEE PES Power Grid Library – Optimal Power Flow v23.07, IEEE PES Task Force on
  Benchmarks for Validation of Emerging Power System Algorithms, CC-BY-4.0." Per-case holders:
  * `pglib_opf_case14_ieee.m`, `case30_ieee`, `case57_ieee`, `case118_ieee`, `case300_ieee`:
    "Copyright (c) 1999 by Richard D. Christie, University of Washington Electrical Engineering.
    Licensed under the Creative Commons Attribution 4.0 International license."
  * `pglib_opf_case1354_pegase.m`: "Copyright (c) 2015 by Cédric Josz, Stéphane Fliscounakis, Jean
    Maeght, and Patrick Panciatici. Licensed under the Creative Commons Attribution 4.0 International
    license."

#### Reused files (byte-identical to the upstream files at `dc6be4b2…`, verified with `cmp`)
* `benchmarks/stormbench/cases/pglib_opf_case{14,30,57,118,300}_ieee.m`,
  `benchmarks/stormbench/cases/pglib_opf_case1354_pegase.m` (+ `LICENSE-pglib-opf`)
* `data/networks/pglib-case14-ieee/source/pglib_opf_case14_ieee.m`,
  `data/networks/pglib-case118-ieee/source/pglib_opf_case118_ieee.m`
* `workers/pandapower/reference_data/pglib/pglib_opf_case{14,118,300}_ieee.m`
* Derived: `data/networks/pglib-case{14,118}-ieee/{network.nc,canonical.json}` (manifest `license`
  block records CC-BY-4.0 and the attribution).

### PyPSA example networks (ac-dc-meshed, scigrid-de) — CC-BY-4.0
* Source: `https://data.pypsa.org/networks/examples/v1.4.0/{ac_dc_meshed,scigrid_de}.nc`, PyPSA commit
  `6c45594596cbc5612511ee9202a9e269e5001d88` (recorded in each dataset manifest); licensed CC-BY-4.0 by
  PyPSA `REUSE.toml` (`examples/**`).
* Attribution: "(c) PyPSA Contributors, CC-BY-4.0, https://github.com/PyPSA/PyPSA". For scigrid-de
  additionally: "grid topology from SciGRID v0.2 (DLR Institute of Networked Energy Systems, formerly
  NEXT ENERGY, www.scigrid.de) based on OpenStreetMap data © OpenStreetMap contributors, ODbL-1.0".

#### Reused files
* `data/networks/ac-dc-meshed/{network.nc,canonical.json,manifest.json}`
* `data/networks/scigrid-de/{network.nc,canonical.json,manifest.json}`

### MATPOWER test cases — case data (not BSD-covered)
* Repo: https://github.com/MATPOWER/matpower (release 8.1; master `952ebcb1a274cfeae2cebda617b4041d941cbc9e`).
  MATPOWER's `LICENSE` states that its code is BSD-3-Clause but "the MATPOWER case files distributed
  with MATPOWER are not covered by the BSD license"; the IEEE cases are conversions of the public
  University of Washington Power Systems Test Case Archive (https://labs.ece.uw.edu/pstca/).
* Use: reference inputs for pandapower validation tests.

#### Reused files
* `workers/pandapower/reference_data/matpower/case{9,14,30,57,118,300}.m`, `t_case9_pf.m`,
  `soln9_pf.mat` (headers state "MATPOWER" and the UW PSTCA source; not byte-compared because the local
  MATPOWER clone is a partial checkout).

### Grid2Op dataset `l2rpn_case14_sandbox` — MPL-2.0
* Indexed by https://github.com/Grid2op/grid2op-datasets (MPL-2.0); downloaded at run time, **not
  redistributed**. Only small derived episode traces are committed (`data/artifacts/grid2op/*.json`,
  each carrying a `dataset.license` block; see `workers/grid2op/src/gridstorm_grid2op/env.py` L117-123).

### Basemap — OpenFreeMap / OpenMapTiles / OpenStreetMap
* The web map loads `https://tiles.openfreemap.org/styles/{positron,dark}` at run time
  (`apps/web/src/components/map/NetworkMap.tsx` L33-40) and displays the attribution
  "OpenFreeMap · © OpenMapTiles · © OpenStreetMap contributors". No tiles are redistributed.

### Observed-event inputs
* Open Power System Data time series and NASA POWER hourly data, fetched by `pipelines/observed`
  (`pipelines/observed/src/gridstorm_observed/sources.py` L38-71, which carries the required citation
  strings). Licences and citations: `docs/research/external-data-sources.md`.

## Concepts only (no code or data copied)

| Project | Licence | What informed GridStorm |
|---|---|---|
| grid2viz (https://github.com/Grid2op/grid2viz @ `b416eba4`) | MPL-2.0 | Episode KPI definitions (overflow counts, ρ quantiles, action counts) re-implemented in `workers/grid2op/src/gridstorm_grid2op/kpis.py`; see `docs/audit/grid2viz-audit.md` |
| grid2game (@ `d54084dd`) | MPL-2.0 | Step-through episode exploration |
| Warden (eklavyagoyal/energy-hackathon-2026-submission @ `1e9ee209`) | MIT | N-1 scan → cascade → remediation pipeline shape (its LLM narration is not used) |
| ORNL power-grid-data-factory (@ `a7bd2c96`) | no licence | Manifest/checksum, deterministic-seed and status-taxonomy ideas (`docs/research/tool-decision-matrix.md`) |
| PowerModels.jl, GOC3Benchmark.jl | BSD-3-Clause | OPF formulation references |
| pypsa-eur-map-viewer, energy-sdk-l2rpn, CoogGrid-Houston | none / Apache-2.0 / MIT | UI ideas only |
