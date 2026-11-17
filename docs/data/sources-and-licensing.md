# Data sources and licensing

Status: 2026-11-17, GridStorm 3.2 (TODO G32-03, G32-06). Covers every shipped network
(`data/networks/*/manifest.json`) and every dataset in the Data Observatory bundle
(`data/observatory/`, bundle `2026-11-17.1`). Checksums below are those of that bundle; the
authoritative values are always the manifests (`data/observatory/manifest.json`,
`data/networks/<id>/manifest.json`). How the bundle is built and verified:
[observatory-pipeline.md](observatory-pipeline.md). Claims marked **[INFERENCE]** are reasoning,
not text from a source. This is not legal advice.

Provenance vocabulary (`docs/glossary.md`): `observed`, `estimated` (derived from observed data by
a documented estimation method), `synthetic`, `modeled` (model parameters or model outputs),
`calculated`.

## 1. Network models

The API turns each network into a `network_model` catalog entry; nothing is copied into the
observatory bundle.

| Field | ac-dc-meshed | scigrid-de | pglib-case14-ieee | pglib-case118-ieee | pypsa-eur-be |
|---|---|---|---|---|---|
| Source name | PyPSA example network `ac_dc_meshed` | PyPSA example network `scigrid_de` (SciGRID v0.2) | PGLib-OPF `pglib_opf_case14_ieee.m` | PGLib-OPF `pglib_opf_case118_ieee.m` | PyPSA-Eur Belgium tutorial (`config/test/config.electricity.yaml`) |
| Original URL | <https://data.pypsa.org/networks/examples/v1.4.0/ac_dc_meshed.nc> | <https://data.pypsa.org/networks/examples/v1.4.0/scigrid_de.nc> | [pglib-opf @ dc6be4b2](https://raw.githubusercontent.com/power-grid-lib/pglib-opf/dc6be4b2f85ca0e776952ec22cbd4c22396ea5a3/pglib_opf_case14_ieee.m) | [pglib-opf @ dc6be4b2](https://raw.githubusercontent.com/power-grid-lib/pglib-opf/dc6be4b2f85ca0e776952ec22cbd4c22396ea5a3/pglib_opf_case118_ieee.m) | <https://github.com/PyPSA/pypsa-eur> (commit `c8209014`) |
| Publisher | PyPSA contributors | PyPSA contributors; SciGRID (DLR, formerly NEXT ENERGY); © OpenStreetMap contributors | IEEE PES Task Force on Benchmarks (PGLib-OPF) | same | Contributors to PyPSA-Eur; OSM-based prebuilt network (Xiong et al.) |
| Licence | CC-BY-4.0 ([REUSE.toml](https://github.com/PyPSA/PyPSA/blob/6c45594596cbc5612511ee9202a9e269e5001d88/REUSE.toml)) | CC-BY-4.0 (PyPSA REUSE.toml) + OSM ODbL notice retained | CC-BY-4.0 data ([LICENSE](https://github.com/power-grid-lib/pglib-opf/blob/dc6be4b2f85ca0e776952ec22cbd4c22396ea5a3/LICENSE)) | CC-BY-4.0 data | ODbL-1.0 |
| Redistribution | permitted (attribution, change notice) | permitted (CC BY + ODbL obligations treated conservatively) | permitted | permitted | permitted (share-alike) |
| Source version | PyPSA v1.4.0 example | PyPSA v1.4.0 example | PGLib-OPF v23.07 | PGLib-OPF v23.07 | PyPSA-Eur v2026.09.0 |
| Data type / provenance | network model, `synthetic` | network model, `modeled` | benchmark case, `synthetic` | benchmark case, `synthetic` | network model, `modeled`; load `synthetic` |
| Geographic scope | illustrative UK/DE/NO nodes | Germany 220/380 kV | none (schematic) | none (schematic) | Belgium, 5 clustered buses |
| Date range | 2015-01-01 00:00–09:00 (synthetic) | 2011-01-01 00:00–23:00 | single undated operating point | single undated operating point | 2013-03-01..2013-03-07 |
| Temporal resolution | 1 h (10 snapshots) | 1 h (24 snapshots) | 1 snapshot | 1 snapshot | 24 h (7 snapshots) |
| Units | kV, MVA, MW, MWh, ohm; illustrative cost units | kV, MVA, MW, MWh, km, ohm; illustrative cost units | kV, MVA, MW; PGLib cost units (**not EUR**) | same as case14 | kV, MVA, MW, MWh, km, ohm; EUR 2025 |
| Timezone | none declared in the source (snapshot labels as in the manifest coverage) | none declared; the observed-analogue mapping treats the snapshots as UTC | n/a | n/a | none declared (daily snapshots) |
| Missing-value policy | absent values → `null` in canonical.json, never invented | same | same; RATE_A=0 → rating `null` | same | `null` in canonical.json; nothing imputed |
| Quality indicators | `synthetic_network`, `line_length_missing`, zero impedances | `line_rating_estimated`, `transformer_parameters_placeholder`, `marginal_cost_placeholder`, `co2_factors_missing` | `schematic_coordinates`, `single_snapshot`, `cost_currency_not_eur` | same | synthetic demand, 24 h averages |
| Source checksum (sha256) | `62e4e53555e2219a2ae48b7f91e576e2ea383cadd2f61db9919f3592503c932f` | `284850c8e922414f9da69ffda0623431148e0c28a3380ba370e4135ac5236500` | raw `.m` `bd5c568621de65e4b0922317010868bc7fa94173807faa10ea8fdbbe77c28106` | raw `.m` `b1af0833849040c04babc3700631cff0d9afa66b79c5d3e13ae79bdf516cec78` | built locally from commit `c8209014`; no single upstream file |
| Transformation version | network_import 1.0.0 + pypsa 1.4.0 canonicalize | same | network_import 1.0.0 (MATPOWER parser, layout) | same | pypsa-eur v2026.09.0 build; replace_load (sha `1c96ff5a…`); import pypsa 1.4.0 |
| Published artifact sha256 (`network.nc`) | `62e4e53555e2219a2ae48b7f91e576e2ea383cadd2f61db9919f3592503c932f` (byte-identical upstream) | `284850c8e922414f9da69ffda0623431148e0c28a3380ba370e4135ac5236500` (byte-identical upstream) | `52424e30e5375a7d8b57d66704b2c0b258c21cad65d47c223e02bad0cb056a42` | `f355e7888f8864231e3f113d339d08efd647ead9bcb9f2b77fc4e3171d2dcdad` | `7eaa427bd3437bb1c15e1135375f385cc72dd620bace9dfa8b82cfe0fc41f857` |

Full per-file checksums and the cost basis of each network are in its manifest and in
[docs/research/data-catalog.md](../research/data-catalog.md).

## 2. Data Observatory datasets (`data/observatory/`)

| Field | `opsd-de-load-forecast` | `nasa-power-de-weather` | `nasa-power-de-renewable-resource` | `opsd-de-derived-multipliers` | `observed-analogue-scenarios` |
|---|---|---|---|---|---|
| Source name | OPSD Time series, column `DE_load_forecast_entsoe_transparency` | NASA POWER Hourly API, `T2M`, `WS10M` | NASA POWER Hourly API, `WS50M`, `ALLSKY_SFC_SW_DWN` | `data/observed/opsd-de/derived-multipliers.json` | `data/scenarios/observed/*.yaml` + `data/observed/analogue-results.json` |
| Original URL | <https://data.open-power-system-data.org/time_series/2020-10-06/time_series_60min_singleindex.csv> | <https://power.larc.nasa.gov/api/temporal/hourly/point> (8 request URLs in `data/observed/nasa-power-de/power-hourly-requests.json`) | same | repository file | repository files |
| Publisher | Open Power System Data; primary: ENTSO-E Transparency Platform (German TSOs) | NASA LaRC POWER Project | same | GridStorm (`pipelines/observed`) | GridStorm |
| Licence | CC-BY-4.0 (ENTSO-E free re-use list 2023-10-18, item #1) | NASA open data: no restriction marked (Earthdata guidance: unmarked NASA-led mission data are CC0) + POWER referencing guide | same | CC-BY-4.0 (derived only from the CC BY forecast and the CC BY network load) | mixed; renewable daily multipliers derived from non-open ENTSO-E actual generation |
| Redistribution | permitted (attribution + change notice) | permitted (acknowledgement; no endorsement) | permitted | permitted | derived-only → metadata only, `exportable: false` |
| Source version | 2020-10-06 (DOI 10.25832/time_series/2020-10-06) | Hourly API v2.10.4 | v2.10.4 | `gridstorm-observed-derived/2.0` | `gridstorm-observed-derived/2.0` manifest |
| Data type / provenance | `historical_demand`, **`estimated`** (TSO forecast, not measured) | `weather_reanalysis`, **`modeled`** (MERRA-2) | `renewable_resource`, **`modeled`** (MERRA-2; CERES SYN1deg) | `derived_research`, `modeled` | `synthetic_scenario_input`, `modeled` |
| Geographic scope | Germany (country) | 4 grid cells containing Berlin 52.52/13.405, Hamburg 53.551/9.994, Cologne 50.938/6.96, Munich 48.137/11.575 | same | Germany via scigrid-de | scigrid-de |
| Date range (UTC, inclusive) | 2015-01-01T00:00Z–2020-09-30T23:00Z | 2015-01-17..2015-01-23 and 2017-01-01..2017-12-31 | same | model day 2011-01-01 (snapshot axis; not observation time) | stress days 2015-01-20, 2017-01-24, 2017-12-13 |
| Temporal resolution | PT1H | PT1H | PT1H | PT1H | PT1H (24 h per scenario) |
| Units | MW (whole MW) | °C, m/s | m/s; Wh/m² per hour (= mean W/m²) | dimensionless | — |
| Timezone | UTC (source `utc_timestamp`) | UTC (`time-standard=UTC` requested; API default is local solar time) | UTC | UTC (model snapshots) | UTC days |
| Missing-value policy | empty cell = missing; never filled | POWER fill −999 → empty; never interpolated | same | none missing | n/a |
| Quality indicators | 99.952 % complete; one 24 h gap 2018-09-23T22Z–2018-09-24T21Z; DST-free UTC check (11 CET/CEST changes); range 28 824–75 912 MW | 100 % complete (8 928 h × 8 series); values identical to the 2026-11-14 extract (4 032/4 032) | 100 % complete; ranges checked | 100 %; equals the YAML events; no clipping | YAML hashes = manifest; results validated + optimal; Studio presets byte-identical |
| Source checksum (sha256) | `6a7f2bc571314cbf9c321cc03437691cd4be95c3a6f075e60ff99e8035c704c8` | request record `046b98fe0a9def8385529eec2fc961082ff75149b33430c5540ef93bd7a9b652` (pins 8 response hashes) | same | `af06b0c0c7f8022d9ccc3be71c1d5210c02b6b1505c03ce6b9dbcae2f452a181` | `data/observed/opsd-de/manifest.json` `d9d5ed6c6c1635953a603e4957764a0d90b14cc17a45f58854a6f2f502f8c7d1` |
| Transformation version | `opsd-de-load-forecast/1.0.0` | `nasa-power-de-weather/1.0.0` | `nasa-power-de-renewable-resource/1.0.0` | `opsd-de-derived-multipliers/1.0.0` | `observed-analogue-scenarios/1.0.0` |
| Published artifact sha256 | `7c9d5743d47439d26926ef229712614ce7131788e8c590ce0d1b3edc1cb6363a` (1 360 701 B) | `d7943b500753f7f335910d6dd96e72a2007644f622e0a564001184d7e9bbe585` (558 439 B) | `92b02004aefed52b3a5b0d9c058f312d610be2e70deaa03a5fbe1cc92497f644` (514 964 B) | `1fd4afdaecc8f94e60fe953714034346cbec263c630ba9477ccc10e509af85b4` (1 080 B) | none (metadata-only) |

### 2.1 What is not published, and why

The OPSD CSV also contains German actual load (Reg. 543/2013 Art. 6.1.a), actual wind/solar
generation (Art. 16.1) and capacities (OPSD calculations on BNetzA/netztransparenz.de). The first
two are not on ENTSO-E's free re-use list; the capacities carry no declared licence
([entsoe-reuse-check.md](../research/entsoe-reuse-check.md)). The pipeline's licence gate
(`pipelines/observed/src/gridstorm_observed/licence.py`) refuses any series whose source key is not
on an explicit allow-list, and refuses `*load_actual*`, `*generation_actual*` and `*capacity*`
even if someone adds them to it. `tests/test_observatory.py` checks that the published forecast
equals the source forecast exactly, and that even an oracle affine fit of it to the actual load
misses by more than 1 GW RMS and by more than 500 MW in most hours and on every stress day: the
forecast does not reconstruct actual load.

### 2.2 Attribution texts

- **ENTSO-E / OPSD forecast** (CC BY 4.0, in the entry's `source.attribution`): "Day-ahead
  forecast of the total load per market time unit, Germany (Reg. (EU) 543/2013 Art. 6.1.b),
  ENTSO-E Transparency Platform (https://transparency.entsoe.eu/), obtained via Open Power System
  Data, Time series 2020-10-06 (https://doi.org/10.25832/time_series/2020-10-06), column
  DE_load_forecast_entsoe_transparency. Licensed under CC BY 4.0 … item #1. Modified by
  GridStorm: column extracted; restricted to UTC calendar days 2015-01-01..2020-09-30; timestamps
  reformatted; whole-MW values written without decimals. No value altered, filled or
  interpolated."
- **NASA POWER.** The [POWER referencing guide](https://power.larc.nasa.gov/docs/referencing/)
  (read 2026-11-17) asks for both of these: "The data was obtained from National Aeronautics and
  Space Administration (NASA) Langley Research Center's Prediction Of Worldwide Energy Resources
  (POWER) project funded through the NASA Earth Science Division." and "The data was obtained
  from the POWER Project's Hourly 2.x.x version on YYYY/MM/DD." The bundle fills in `v2.10.4` and
  `2026/11/16` (UTC date of retrieval). The guide also requests notification of redistribution
  (`larc-power-project@mail.nasa.gov`). The [Earthdata data-use
  guidance](https://www.earthdata.nasa.gov/engage/open-data-services-software-policies/data-use-guidance)
  says: "Unless the content is marked with a use restriction or license, data provided from a
  NASA-led mission are licensed as Creative Commons Zero (CC0)", asks that NASA be acknowledged and
  forbids implying endorsement. **[INFERENCE]** POWER pages mark no restriction, so the CC0 default
  applies; the bundle records the licence as `LicenseRef-NASA-POWER` rather than asserting CC0.

### 2.3 NASA POWER source facts (verified 2026-11-17)

- Hourly API docs: "Hourly API defaults to providing LST; to change the time standard please
  include time-standard=UTC"; "Provides parameters by hour with average values"; "All parameters
  are available in their original source spatial resolution"; at most 15 parameters per request.
  Every request sets `time-standard=UTC`; every response header says `"time_standard": "UTC"`.
- Meteorology (T2M, WS10M, WS50M): GMAO MERRA-2, "½° latitude by ⅝° longitude grid"; "All of the
  MERRA-2 parameters represent the average value over the spatial grid"; wind "at 2 m, 10 m, and
  50 m above the average elevation of the grid".
- Solar (ALLSKY_SFC_SW_DWN = GHI): CERES SYN1deg Edition 4.2 from 2001-01-01 to ~3–4 months before
  real time, 1° × 1°; CERES FLASHFlux 4A fills only the most recent months (not used for 2015/2017).
  Response headers list sources `MERRA2`, `SYN1DEG`, `POWER`; HTTP header `x-app-version: v2.10.4`.
- Hour labels are POWER's `YYYYMMDDHH` in UTC, written as hour start. The alignment of the
  averaging interval within the hour is not stated on the pages read and was not verified.

## 3. Candidate-source scoring matrix

Scores 1 (poor) – 5 (excellent) for GridStorm's use. "Compatibility" = with the shipped networks
(scigrid-de, pypsa-eur-be, PGLib/IEEE cases, ac-dc-meshed).

| Source | Scientific usefulness | Licence | Reliability | Quality | Coverage | Ingestion complexity (5 = simple) | Compute cost (5 = cheap) | UI usefulness | Compatibility | Decision |
|---|---|---|---|---|---|---|---|---|---|---|
| NASA POWER (hourly) | 4: hourly weather + resource around the analogue days | 5: no restriction marked; acknowledgement | 4: no key; fast (<3 s per point-year); HTTP 429 when rate limited | 3: reanalysis/satellite grid cells, not stations; documented validation statistics | 5: global, 2001–NRT hourly | 5: JSON, no key | 5 | 4: maps/charts at named points | 3: points, no validated weather→availability model | **Use now** (published; `modeled`) |
| EIA Open Data (API v2, EIA-930) | 3: hourly US BA demand/generation | 5: public domain ("may use and/or distribute any of our data") | 4: key-gated API, throttled per key | 4: mandatory reporting; revisions within days | 4: US only, BA level | 3: free key, 5 000-row pages, `offset` paging | 5 | 3 | 1: no US network in GridStorm; no validated BA→bus mapping | **Evaluated, deferred** (§3.1) |
| OPSD Time series 2020-10-06 | 4: curated European hourly series | 2: per column; only listed ENTSO-E items are open | 4: DOI-pinned, sha256 published | 4: documented gaps, consistent UTC | 3: ends 2020-09-30 | 4: one 130 MB CSV | 5 | 4 | 3: scigrid-de via analogue mapping | **Use now**: forecast column only |
| ENTSO-E Transparency (direct) | 5: authoritative EU load/generation | 2: only listed items CC BY; actual load/generation not | 4: token, ~3 working days | 4 | 5: EU, current | 2: token + XML API | 4 | 4 | 3 | **Defer**: token needed; only listed items publishable |
| PGLib-OPF | 5: standard OPF benchmarks | 5: CC BY 4.0 data | 5: commit-pinned | 4: benchmark, not real grids; costs not EUR | 3: single snapshot | 5 | 5 | 3 | 5: shipped (case14, case118) | **Use now** (networks) |
| SimBench 1.6.3 | 4: German LV–EHV synthetic grids + 15-min profiles | 4: ODbL / DbCL (share-alike) | 4: pinned release | 4: synthetic | 4: one synthetic year | 3: converter + CSV | 3: large grids | 3 | 2: distribution focus; separate worker | **Defer** for the catalog (used by `workers/distribution` studies) |
| PyPSA-Eur | 5: open European model | 4: ODbL + per-input licences | 4: pinned commit | 4: modeled; tutorial scale here | 4 | 1: snakemake build, external data | 2: build hours | 4 | 5: shipped as pypsa-eur-be | **Use now** (BE tutorial network); no extra series |
| IEEE 30-bus (PGLib `case30_ieee`) | 4: StormBench reference case | 5: CC BY 4.0 | 5 | 4: benchmark | 2: single snapshot | 5 | 5 | 2: no geography | 4: PGLib importer path exists | **Use in StormBench only**; no catalog network entry this release |

### 3.1 EIA Open Data: evaluated, deferred

Checked 2026-11-17 on <https://www.eia.gov/opendata/>, the
[API v2 documentation](https://www.eia.gov/opendata/documentation.php),
[Copyrights and Reuse](https://www.eia.gov/about/copyrights_reuse.php) and the
[EIA-930 instructions](https://www.eia.gov/survey/form/eia_930/instructions.pdf).

- **Key.** "To call our API, you must use the unique API key assigned to you" (free, by email). A
  keyless request to `api.eia.gov/v2/electricity/rto/region-data/data/` returned HTTP 403
  `API_KEY_MISSING` (2026-11-17). No key is available in this environment.
- **Paging.** "our API only returns a maximum of 5,000 rows … using offset to paginate results."
  Keys are throttled per second/hour and suspended temporarily if exceeded.
- **Cadence.** EIA-930 balancing authorities submit same-day hourly demand within 60 minutes of the
  operating hour and daily files (demand forecast, demand, net generation, interchange) by 07:00
  Eastern; estimates may be resubmitted within 3 days, larger corrections within 30 days. Values
  are hourly integrated MW by **hour ending**, timestamps in UTC.
- **Terms.** "U.S. government publications are in the public domain … You may use and/or distribute
  any of our data"; cite EIA as the source; third-party content excepted.
- **Why deferred.** GridStorm has no US network model. US balancing-authority demand has no
  validated mapping to SciGRID-DE, PyPSA-Eur BE or the IEEE/PGLib benchmark buses (the IEEE cases
  derive from historic AEP systems but carry no BA or date). Publishing it would add a series
  nobody can use in a scenario.
- **Ingestion design (when a US network or validated mapping exists).**
  1. Secret `EIA_API_KEY` in the fetch environment only (never in the repo or manifests).
  2. Route `electricity/rto/region-data/data/`, `frequency=hourly`, `data[0]=value`,
     `facets[respondent][]=<BA>`, `facets[type][]=D` (demand) and `DF` (day-ahead forecast),
     explicit `start`/`end` in UTC (`YYYY-MM-DDTHH`), `sort[0][column]=period`, `length=5000`,
     `offset` loop until fewer than 5 000 rows; sequential with a pause.
  3. Record per page: URL without the key, response sha256, `response.total`, API version;
     convert hour-ending periods to hour-start UTC (−1 h) and say so in `transformations`.
  4. Licence gate: allow-list `eia:<BA>:D` and `eia:<BA>:DF` (public domain); provenance
     `observed` for D, `estimated` for DF; quality: gaps, duplicates, revisions (re-fetch and diff
     within 30 days), range.
  5. Entry category `historical_demand`, `use_in_scenario.available=false` until a network mapping
     is validated.
