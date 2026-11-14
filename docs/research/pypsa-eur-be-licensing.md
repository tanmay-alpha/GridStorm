# PyPSA-Eur Belgium network: licensing evidence and publication decision (P1-04b)

Status: research notes, checked 2026-11-15. Scope: `data/networks/pypsa-eur-be/network.nc` (sha256
`0648933ae2cbffdbf61bcd80df999a7af6eedc84cc56b69d0e9acdb65c532b36`, byte-identical to upstream
`resources/test-elec/networks/composed_2050.nc`) and the derived `canonical.json`. The build and pins are in
[pypsa-eur-build.md](pypsa-eur-build.md): upstream `v2026.09.0` / `c8209014`, tutorial config
`config/test/config.electricity.yaml`. Licences were read on the official pages linked below on 2026-11-15.
Anything not stated on those pages is marked [INFERENCE]. This is a research assessment, not legal advice.

## Verdict

**PUBLISH WITHOUT the load time series.** The current `network.nc`/`canonical.json` must **not** be published
as they are.

- Every input that reaches the file is redistributable with attribution **except the Belgian load**.
  `loads_t.p_set` is the ENTSO-E *Power Statistics* hourly load for Belgium (via OPSD), averaged to days and
  split across buses. ENTSO-E's website terms forbid redistributing or creating derivative works from site
  content without written permission (E7).
- The grid topology comes from the OSM-based PyPSA-Eur network (ODbL-1.0). The published file is therefore an
  ODbL **Derivative Database**. It must be published under ODbL-1.0, and ODbL §4.4.d forbids adding content
  whose terms conflict with that licence (E2).
- Remedy: replace `loads_t.p_set` with the CC-BY-4.0 *Interannual Electricity Demand Calculator* series for
  BE, 2013-03-01..07 (Zenodo 10820928, E9). Keep the existing per-bus split, label the load `modeled`
  (synthetic), then re-run validation and the LOPF. After that, publish under **ODbL-1.0** with the
  attribution block in [§4](#4-attribution-block-x-for-the-republished-dataset).
- Open caveats: NUTS/GISCO non-commercial clause (indirect use only), technology-data licence mismatch
  (GPL-3.0 on the Zenodo release vs CC-BY-4.0 in the PyPSA-Eur inventory), and the IAEA capacity factor
  (licence checked only through PyPSA-Eur's REUSE annotation). See §3.

## 1. Which inputs actually reach `network.nc`

The input list comes from the 24 `Retrieving from storage:` URLs in `build-pypsa-eur/build6.log` plus the
rule inputs in `build-pypsa-eur/out/snakemake.log`. Effects on the BE output were then checked in the pinned
scripts and in the Docker build volume `gridstorm-pypsa-eur-work`. Contents of the file (PyPSA 1.2.4,
read 2026-11-15):

- 5 AC + 5 H2 buses and 6 lines.
- `lines_t.s_max_pu` (7×5, dynamic line rating).
- 33 generators with `generators_t.p_max_pu` (7×18).
- `loads_t.p_set` (7×5).
- Storage, stores and links.
- One `CO2Limit`.
- `n.meta` (the tutorial config, CC0).

`n.shapes` is empty, so no region geometry is stored.

Verified facts that decide the table below:

- **Load = OPSD BE, exactly.** Upstream sets `load = entsoe.combine_first(opsd).combine_first(neso)`, then
  `combine_first(synthetic)` (`scripts/build_electricity_demand.py` L244-250, L309-316). The ENTSO-E raw file
  starts in 2015 (yearly row counts: first year 2015). The built `resources/test-elec/electricity_demand.csv`
  matches the OPSD raw `BE` column on all 168 hours: 0 NaN, max abs diff 0.0. So the synthetic, ENTSO-E
  Transparency and NESO files contribute nothing to BE.
- **The OPSD BE 2013 values come from ENTSO-E Power Statistics.** `scripts/retrieve_electricity_demand_opsd.py`
  concatenates OPSD packages 2019-06-05 and 2020-10-06. It takes `*_load_actual_entsoe_transparency` and
  fills gaps from `*_load_actual_entsoe_power_statistics`. In the 2019-06-05 datapackage,
  `BE_load_actual_entsoe_power_statistics` has source "ENTSO-E Data Portal and Power Statistics",
  `https://www.entsoe.eu/data/power-stats` (E5). For 2013 only that column exists.
- **The daily national load can be recovered exactly.** The per-bus `p_set` rows sum to the national daily
  mean, e.g. 2013-03-01: 1611.9 + 861.6 + 1867.6 + 1591.5 + 5178.7 = 11,111.3 MW. That is the peak snapshot
  reported in pypsa-eur-build.md.
- **Spatial load split = JRC Energy Atlas.** For EU27 countries, `energy_atlas_distribution_keys` takes
  precedence over the NUTS3 GDP/population keys (`scripts/build_electricity_demand_base.py` L64-97,
  L194-198). ARDECO, gridded GDP and WorldPop feed only the NUTS3 keys used as fallback or for non-NUTS
  countries (`scripts/build_nuts3_shapes.py` L155, L513). [INFERENCE] They do not affect BE values.
- **One TYNDP line is included.** `resources/test-elec/transmission_projects/new_lines.csv` contains
  `TYNDP2020_77` (in permitting, 380 kV, 90 km). It appears as line `1` (`build_year` 2024,
  `s_nom` 3396.21). All other projects lie outside the area, according to `logs/test-elec/build_transmission_projects.log`.
- **Nuclear `p_max_pu` = 0.781.** This is the BE 2013 value in `data/nuclear_p_max_pu.csv`.
- **Not used for this output:**
  - CO2 price file: `costs.emission_prices.enable/dynamic: false`, `scripts/prepare_network.py` L476-481.
  - Solar-rooftop potentials, hence World Bank urban population: used only in `prepare_sector_network.py`.
  - Hydro capacities: there are no hydro carriers in the output.
  - GEBCO: not retrieved, because the tutorial sets `max_depth: false`.
  - OSM-Boundaries: built only for MD/UA/BA/XK.
  - DESNZ/ONS/NESO: GB only.

## 2. Evidence table

"Derived redistribution" means publishing GridStorm's derived network values, not the raw input files. No raw
input file may be committed.

| Input (pinned version) | Reaches `network.nc` as | Licence (evidence) | Attribution required | Share-alike | Derived redistribution permitted? | Source URL |
|---|---|---|---|---|---|---|
| PyPSA-Eur OSM prebuilt grid v0.7 | Bus positions; line topology, length, `s_nom`, electrical parameters (after simplify/cluster) | **ODbL-1.0**: Zenodo record `license: odc-odbl`, "This processed dataset is provided under the … ODbL 1.0" (E1); OSM data ODbL (E2) | "© OpenStreetMap contributors", say the data are under ODbL with a link to the licence (E2); cite Xiong et al. 2025 (E1) | **Yes.** The published network is a Derivative Database: ODbL §4.2 notices, §4.4 share-alike, §4.6 offer the DB or the method (E2) | **Yes**, under ODbL-1.0 only | https://zenodo.org/records/18619025 |
| ENTSO-E Power Statistics hourly load BE 2013 (via OPSD `time_series` 2019-06-05, PyPSA archive 2026-02-02) | `loads_t.p_set` (daily means × bus shares); clustering weights | ENTSO-E site terms: content "owned and copyrighted by ENTSO-E … all rights reserved"; download "only for non-commercial, personal use"; "may not distribute, modify, … create derivative works … without ENTSO-E's written permission" (E7). OPSD datapackage has no `licenses` field (E5). The Power Statistics page states no licence (E6). PyPSA-Eur inventory: `unknown` (L19) | OPSD citation: "Open Power System Data. 2019. Data Package Time series. Version 2019-06-05. https://doi.org/10.25832/time_series/2019-06-05" (E5) | n/a | **No.** No grant, permission not obtained. Also incompatible with ODbL §4.4.d (E2). Cf. [entsoe-reuse-check.md](entsoe-reuse-check.md): even TP total load is not on the free re-use list | https://www.entsoe.eu/data/power-stats/ |
| JRC Energy Atlas `electricity_tot_demand_2019.tif` (archive 2026-02-16) | Per-bus load shares | **CC-BY-4.0**: "Any copyright and/or sui generis right on the dataset is licensed under … CC BY 4.0" (E12) | "© European Union, 1995-2026", indicate changes (E12) | No | **Yes** | https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/EIGL-Data/RASTER/copyright.txt |
| ERA5 cutout `be-03-2013-era5` v1.0 | Renewable `p_max_pu` profiles; DLR `lines_t.s_max_pu` | **CC-BY-4.0**: CDS STAC `license: CC-BY-4.0` (E10); replaced the Copernicus licence on 2025-07-02 (E11) | Cite per the CDS dataset "References" section (E11) | No | **Yes** | https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels |
| CORINE Land Cover (PyPSA archive v18_5) | Renewable eligibility → `p_nom_max`, profile weighting | **CLMS full, open and free access**: inform the public of the source, state modifications, no implied EU endorsement; "the user has all intellectual property rights to the products he/she has created" (E13). PyPSA-Eur inventory: "Custom similar to CC-BY" (L31) | "Generated using European Union's Copernicus Land Monitoring Service information; <DOI>" (E13) | No | **Yes**, with conditions | https://land.copernicus.eu/en/data-policy |
| Natura 2000 raster 2025-08-15 | Renewable eligibility | **CC-BY-4.0**: Zenodo record `cc-by-4.0`, Terms of Use = EEA legal notice (E14); EEA: re-use for commercial or non-commercial purposes, "EEA is always acknowledged as the original source" (E15) | Acknowledge the EEA; credit the Zenodo rasterisation (Hampp) | No | **Yes** | https://zenodo.org/records/16881818 |
| World Bank Global Shipping Traffic Density v5 | Offshore eligibility (`offwind-*` `p_nom_max`) | **CC-BY-4.0**: catalogue page "License: Creative Commons Attribution 4.0" (E16) | World Bank, "Global Shipping Traffic Density" | No | **Yes** | https://datacatalog.worldbank.org/search/dataset/0037580/Global-Shipping-Traffic-Density |
| Marine Regions World EEZ v12 (LR) | Offshore regions → offshore potentials and profiles | **CC-BY-4.0** since v11; "kindly request … not to make our products available for download elsewhere" (E17) | Flanders Marine Institute, MarineRegions.org | No | **Yes** (derived values; do not re-host the EEZ files) | https://www.marineregions.org/disclaimer.php |
| powerplantmatching `powerplants.csv` 0.8.1 | Existing capacities (CCGT, nuclear, biomass, oil, waste, onwind, offwind-ac, solar); bus mapping | **CC-BY-4.0**: "The default output data powerplants.csv … is released under CC BY 4.0"; REUSE annotation (E18) | "Contributors to powerplantmatching" | No | **Yes** | https://github.com/PyPSA/powerplantmatching/blob/v0.8.1/README.md |
| technology-data `costs_2050.csv` v0.15.0 (+ `data/custom_costs.csv`) | `capital_cost`, `marginal_cost`, efficiencies, lifetimes | **Ambiguous.** PyPSA-Eur inventory L42: CC-BY-4.0. The Zenodo v0.15.0 release record says `gpl-3.0` (E19). README/docs: code GPLv3, "different licenses and terms of use may apply to the various input data", no explicit output licence (E19). `custom_costs.csv`: CC-BY-4.0, PyPSA-Eur Authors (REUSE.toml L48-51) | "Contributors to technology-data" + DOI 10.5281/zenodo.3994163 | Possibly (if GPL) | **Yes**, either way (both allow redistribution). [INFERENCE] Numeric cost assumptions are largely facts; mixing with ODbL is a residual risk | https://zenodo.org/records/20999884 |
| IAEA nuclear capacity factors (`data/nuclear_p_max_pu.csv`) | Nuclear `p_max_pu` = 0.781 | CC-BY-4.0, "International Atomic Energy Agency (IAEA)", per PyPSA-Eur `REUSE.toml` L94-99 (pinned clone). IAEA's own terms **not verified** | IAEA (PRIS) | No | **Yes**, per the REUSE annotation | upstream `REUSE.toml` @ `c8209014` |
| TYNDP 2020 project list (`data/transmission_projects/tyndp2020/`) | Line `1` (`TYNDP2020_77`) | CC-BY-4.0, "The PyPSA-Eur Authors" (`REUSE.toml` L45, L50-51). The underlying sheet is on an ENTSO-E platform. [INFERENCE] Endpoints, voltage and status are facts; type and parallel count are PyPSA-Eur assumptions | PyPSA-Eur Authors; ENTSO-E TYNDP 2020 | No | **Yes** per REUSE. If you want to be strict, rebuild with `transmission_projects.enable: false` | upstream repo |
| NUTS 2021 (GISCO, 01M GeoJSON) | Indirect only: BE outline and admin shapes clip the Voronoi regions → potentials, clustering. No NUTS geometry or codes are stored (`n.shapes` empty) | GISCO NUTS page: "Specific download provisions apply … By downloading or using the data, you accept them" (E20). Those provisions: non-exclusive, non-transferable right of use; "the data will not be used for commercial purposes"; copyright notice required (E21). PyPSA-Eur inventory L11: "Reuse policy following 2011/833/EU" | "© EuroGeographics for the administrative boundaries" (E21) | No | **Yes for non-commercial use**. [INFERENCE] Numeric results are not a copy of the boundaries; commercial use of GridStorm would need a EuroGeographics licence or a different boundary source | https://gisco-services.ec.europa.eu/distribution/v2/nuts/ |
| PyPSA-Eur code/config/repo data (`unit_commitment.csv`, `custom_powerplants.csv`, config in `n.meta`) | Attributes, metadata | Code MIT, data files CC-BY-4.0, config CC0-1.0 (`doc/licenses.md`); `custom_powerplants.csv` CC0 (REUSE.toml L53-58) | "Contributors to PyPSA-Eur" | No | **Yes** | https://github.com/PyPSA/pypsa-eur/blob/c8209014468dbb3bf43257f45d34abc6e3c8c898/doc/licenses.md |
| **Retrieved but no effect on the BE output** | — | Synthetic demand v2 (CC-BY-4.0); ENTSO-E TP demand (rows start 2015); NESO / DESNZ / ONS (GB only); Instrat CO2 prices (`unknown`; emission prices disabled); ARDECO, gridded GDP, WorldPop (non-NUTS fallback, [INFERENCE]); World Bank urban population (sector rooftop only); OSM-Boundaries (MD/UA/BA/XK); `hydro_capacities.csv` (no hydro in output) | — | — | Not applicable. Do not list them in the manifest's `spdx` | data_inventory.csv rows 4, 7, 18, 20-21, 26-27, 36, 52, 54-55 |

## 3. Reasoning and residual risks

1. **Blocker: load.** ENTSO-E's terms (E7) apply to everything on "this Web site or any of our other Web
   sites", and the Power Statistics XLSX files sit under `entsoe.eu/publications/data/power-stats/` (E6).
   OPSD declares no licence (E5) and warns that some of its data "might be subject to copyright"
   ([external-data-sources.md](external-data-sources.md)).
   - The 7×5 daily values reconstruct the observed national daily-mean load exactly (§1).
   - [INFERENCE] Whether a few daily averages attract copyright or database right is unclear. Under the ODbL
     share-alike regime, GridStorm cannot grant the rights ODbL implies for this content (ODbL §4.4.d, E2).
     So the content must be removed rather than argued.
2. **The replacement is honest and narrow.**
   - The CC-BY-4.0 synthetic series (E9) is a temperature-regression model driven by ERA5. That is the same
     weather year as the cutout. The local file has BE values for 2013-03-01 (e.g. 10,103 MW at 00:00, vs
     OPSD 10,151 MW).
   - [INFERENCE] Its intra-day shape is sampled from OPSD historical days (E9). The 24 h averaging keeps only
     the modelled daily totals, so no OPSD/ENTSO-E hourly shape survives into the network.
   - [INFERENCE] The per-bus shares are time-invariant JRC Energy Atlas keys
     (`build_electricity_demand_base.py` L209-222). For a single country, the clustering weights are those
     shares times one national series, so topology and potentials do not change. Only `loads_t.p_set` and
     the solved results do.
   - Required labelling:
     - provenance `modeled` (synthetic load), with a quality flag stating that load is not observed 2013 demand;
     - a transformation note: "load replaced with the Frysztacki/van der Most/Neumann synthetic BE series,
       daily mean, distributed with upstream JRC Energy Atlas keys";
     - the objective, test thresholds and pypsa-eur-build.md figures (peak 11,111 MW, objective) must be
       regenerated, not reused.
3. **The ODbL makes the whole file share-alike.** The network must be published under ODbL-1.0, not
   CC-BY-4.0. Also required:
   - the licence URI inside the file and the docs (§4.2.b);
   - the method offer, i.e. the pinned build/import scripts (§4.6.b);
   - a Produced-Work notice wherever results are displayed (§4.3).

   [INFERENCE] CC-BY-4.0 inputs can be included because CC BY imposes no share-alike. Their attribution
   duties travel with the file.
4. **Caveats that do not block publication:**
   - NUTS non-commercial clause: indirect use only. Record it in the manifest. Revisit if GridStorm is used
     commercially.
   - technology-data licence mismatch: ask upstream, or keep the CC-BY-4.0 label from the PyPSA-Eur inventory
     and record the GPL-3.0 discrepancy.
   - IAEA terms not independently verified.
   - TYNDP project line.
5. **Do not publish** raw inputs, `solved_2050.nc`, the build logs, or the current
   `network.nc`/`canonical.json`. Update the manifest's `license.spdx` from the current composite
   (`… LicenseRef-ENTSOE-OPSD-unknown`) to `ODbL-1.0`, and list attributions per §4. Catalog and manifest
   edits are out of scope here.

## 4. Attribution block X (for the republished dataset)

> PyPSA-Eur Belgium tutorial network (5 clusters, 2013-03-01..07, daily), built with PyPSA-Eur v2026.09.0
> (commit c8209014; code MIT, © Contributors to PyPSA-Eur) and converted by GridStorm. Load replaced by a
> synthetic series; see the transformation history. **Licensed under the Open Database License (ODbL) 1.0,
> https://opendatacommons.org/licenses/odbl/1-0/.**
> Contains information from the *Prebuilt Electricity Network for PyPSA-Eur based on OpenStreetMap Data*
> v0.7 (Xiong et al., https://doi.org/10.5281/zenodo.18619025), © OpenStreetMap contributors, available under
> the ODbL (https://www.openstreetmap.org/copyright).
> Electricity demand: Frysztacki, van der Most, Neumann, *Interannual Electricity Demand Calculator*,
> https://doi.org/10.5281/zenodo.10820928 (CC BY 4.0), daily mean. Spatial split: JRC Energy Atlas,
> © European Union, 1995-2026 (CC BY 4.0). Modified.
> Weather: generated using Copernicus Climate Change Service ERA5 information (CC BY 4.0), via a PyPSA-Eur
> atlite cutout. Modified.
> Land cover: generated using European Union's Copernicus Land Monitoring Service information (CORINE Land
> Cover). Protected areas: Natura 2000, © European Environment Agency (CC BY 4.0), rasterised by J. Hampp
> (https://doi.org/10.5281/zenodo.16881818). Shipping density: World Bank, Global Shipping Traffic Density
> (CC BY 4.0). Maritime boundaries: Flanders Marine Institute, MarineRegions.org World EEZ v12 (CC BY 4.0).
> Power plants: powerplantmatching 0.8.1, Contributors to powerplantmatching (CC BY 4.0). Costs: PyPSA
> technology-data v0.15.0 (https://doi.org/10.5281/zenodo.3994163). Nuclear availability: IAEA, via PyPSA-Eur
> (CC BY 4.0). Transmission project TYNDP2020_77: PyPSA-Eur Authors / ENTSO-E TYNDP 2020 (CC BY 4.0).
> © EuroGeographics for the administrative boundaries (NUTS 2021, GISCO; non-commercial use).
> None of these providers endorses GridStorm. All values were modified by aggregation, clustering and
> modelling.

## 5. Evidence list (all read 2026-11-15)

Web:

- E1. Zenodo API, OSM prebuilt network v0.7: https://zenodo.org/api/records/18619025 (`license.id: odc-odbl`; description: "provided under the … ODbL 1.0"; references Xiong et al. 2025).
- E2. OSM copyright page https://www.openstreetmap.org/copyright ("How to credit"; "distribute the result only under the same licence"). ODbL 1.0 legal code https://opendatacommons.org/licenses/odbl/1-0/ §4.2, §4.3, §4.4 (incl. 4.4.d), §4.6.
- E5. OPSD time_series 2019-06-05: https://data.open-power-system-data.org/time_series/2019-06-05/datapackage.json (field `BE_load_actual_entsoe_power_statistics`, source "ENTSO-E Data Portal and Power Statistics", no `licenses` key). Package page https://data.open-power-system-data.org/time_series/2019-06-05 (citation string).
- E6. ENTSO-E Power Statistics page https://www.entsoe.eu/data/power-stats/ ("Monthly Hourly Load Values", 2006–2015 archive; no licence statement).
- E7. ENTSO-E Disclaimer / Terms of Use https://www.entsoe.eu/about/legal-and-regulatory/disclaimer/ §2 "Ownership of Content", §3 "Your Use of the Site".
- E9. Zenodo API, synthetic demand https://zenodo.org/api/records/10820928 (`cc-by-4.0`; "The file demand_hourly.csv is released under CC-BY-4.0 license"; method description).
- E10. CDS STAC collection https://cds.climate.copernicus.eu/api/catalogue/v1/collections/reanalysis-era5-single-levels (`license: CC-BY-4.0`).
- E11. ECMWF announcement https://forum.ecmwf.int/t/cc-by-licence-to-replace-licence-to-use-copernicus-products-on-02-july-2025/13464 (CC-BY from 2025-07-02; attribution per each dataset's "References" section).
- E12. JRC Energy Atlas copyright https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/EIGL-Data/RASTER/copyright.txt
- E13. Copernicus Land Monitoring Service data policy https://land.copernicus.eu/en/data-policy
- E14. Zenodo API, Natura raster https://zenodo.org/api/records/16881818 (`cc-by-4.0`; Terms of Use → EEA legal notice).
- E15. EEA legal notice https://www.eea.europa.eu/en/legal-notice ("Copyright notice").
- E16. World Bank catalogue page https://datacatalog.worldbank.org/search/dataset/0037580/Global-Shipping-Traffic-Density ("License: Creative Commons Attribution 4.0").
- E17. Marine Regions licence https://www.marineregions.org/disclaimer.php
- E18. powerplantmatching v0.8.1: https://raw.githubusercontent.com/PyPSA/powerplantmatching/v0.8.1/README.md ("Licence") and `REUSE.toml` (`powerplants.csv` → CC-BY-4.0).
- E19. technology-data v0.15.0: README "Licence" https://raw.githubusercontent.com/PyPSA/technology-data/v0.15.0/README.md; docs https://technology-data.readthedocs.io/en/latest/ ("Licence"); Zenodo release https://zenodo.org/api/records/20999884 (`license.id: gpl-3.0`).
- E20. GISCO NUTS distribution https://gisco-services.ec.europa.eu/distribution/v2/nuts/ ("Specific download provisions apply …").
- E21. GISCO provisions https://ec.europa.eu/eurostat/web/gisco/geodata/administrative-units ("Copyright information", "Copyright notice").

Local (pinned clone `D:/New folder (4)/upstream/pypsa-eur` @ `c8209014`, build volume `gridstorm-pypsa-eur-work`):

- `doc/licenses.md`; `doc/data_inventory.csv` rows 3, 7, 11, 18-21, 23-24, 26-27, 29, 31, 36, 40-42, 45, 52-55; `REUSE.toml` L37-58, L94-99; `data/versions.csv` L19-22, L37, L84-85, L99-103, L114-118, L153-154.
- `config/test/config.electricity.yaml`; `config/config.default.yaml` L464-477 (transmission_projects), L486-498 (load), L1151-1155 (emission_prices).
- Scripts: `build_electricity_demand.py` L232-316; `retrieve_electricity_demand_opsd.py`; `build_electricity_demand_base.py` L64-97, L176-225; `build_nuts3_shapes.py` L155-200, L513; `prepare_network.py` L476-481; `prepare_sector_network.py` L1331, L6380.
- Build outputs:
  - `build-pypsa-eur/build6.log` (24 retrieved URLs) and `build-pypsa-eur/out/snakemake.log` (rule inputs);
  - volume: `logs/test-elec/build_transmission_projects.log`, `resources/test-elec/transmission_projects/new_lines.csv`, `resources/test-elec/electricity_demand.csv` vs the OPSD raw `BE` column (168 h, diff 0.0), the ENTSO-E raw year counts (2015+), and the synthetic `load_synthetic_raw.csv` BE 2013-03-01 rows;
  - `composed_2050.nc` read back: component lists, line `1` = TYNDP2020_77, nuclear `p_max_pu` 0.781, `loads_t.p_set`, empty `n.shapes`.

## 6. Outcome (2026-11-15)

The remedy in the verdict was applied. The dataset is published under ODbL-1.0.

- **Load replaced.** `pipelines/pypsa-eur/replace_load.py` takes upstream `composed_2050.nc` (sha256
  `0648933a…2b36`) and `demand_hourly.csv` (Zenodo 10820928, CC-BY-4.0, 464,620,414 bytes, sha256
  `1c96ff5a041abbb85d6d24f880455e13a931c5cbaf0e54e3f7fc0f7644b12bc0`; md5 matches the Zenodo API).
  - It writes the 24 h means of the BE column × the upstream JRC Energy Atlas shares. The shares are
    time-invariant to 4.0e-10.
  - Only `loads_t_p_set` changes. Its checks: 0 of 35 values equal the OPSD-derived values, and none is
    within 1 MW. Max |diff| is 266.58 MW. Correlation is 0.702 for the national daily series and 0.998
    for per-bus values (shared shares).
  - Daily totals match the synthetic daily means to 1.8e-12 MW. Weighted energy is 1,728,907.786 MWh, the
    same as the 168 h synthetic sum.
- **Published file:** `data/networks/pypsa-eur-be/network.nc`, 310,377 bytes, sha256
  `7eaa427bd3437bb1c15e1135375f385cc72dd620bace9dfa8b82cfe0fc41f857`.
  - The NetCDF global attributes carry `license` ODbL-1.0, `license_url`, the §4 `attribution` block and
    the replacement provenance (§4.2.b).
  - Manifest: `license.spdx` `ODbL-1.0`, `redistribution: permitted`, the same attribution and loads
    `modeled`. Quality flags: "synthetic demand, not observed 2013 load", the NUTS non-commercial clause
    and the technology-data licence mismatch. Transformations: `build`, `replace_load`, `import`.
- **Method offer (§4.6.b):** `pipelines/pypsa-eur/` (build, replace, import scripts).
- **Regenerated numbers:** peak 11,178.9 MW and LOPF objective 49,392,841.28 EUR (HiGHS, `optimal`), in
  [pypsa-eur-build.md](pypsa-eur-build.md). The `pypsa-eur-be` dataset is listed in
  `data/networks/catalog.json` and has a baseline preset/artifact. Its `.gitignore` entries were removed.
- **Open caveats (non-blocking):** unchanged from §3.4.
