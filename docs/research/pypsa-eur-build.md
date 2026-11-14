# PyPSA-Eur Belgium tutorial build

## Scope and status

**Status: built, load replaced, imported, validated, LOPF-solved and published (2026-11-15).** This is the actual upstream Belgium electricity tutorial, not a hand-constructed substitute. All gates passed: upstream composed network built (58/58 Snakemake jobs); the non-redistributable ENTSO-E/OPSD load was replaced by the CC-BY-4.0 synthetic demand series (`pipelines/pypsa-eur/replace_load.py`, see [the licensing note](pypsa-eur-be-licensing.md)); the result loads under PyPSA 1.4.0, `network.nc` is 310,377 bytes (≤ 10 MB), `network_import validate` reports no errors, and a HiGHS LOPF terminates `optimal`. The dataset is licensed ODbL-1.0 and listed in `data/networks/catalog.json`.

## Pinned inputs and environment

- Upstream release: `v2026.09.0`, commit `c8209014468dbb3bf43257f45d34abc6e3c8c898`.
- Read-only upstream clone: `D:/New folder (4)/upstream/pypsa-eur`.
- Build state: Docker volume `gridstorm-pypsa-eur-work`, working tree `/work/pypsa-eur`; never builds inside the GridStorm source tree.
- Container: `ghcr.io/prefix-dev/pixi:0.81.0`, observed repository digest `sha256:788ae451641666e2d1f79d3dbe35392dfc7e9b394b16a3acb75c347f3badb2ab`.
- Installed locked upstream environment, queried with `importlib.metadata.version`: Python 3.13.15 (workflow banner), PyPSA 1.2.4, linopy 0.8.0, highspy 1.13.1, Snakemake 9.27.0, HTTP storage plugin 0.3.1, cached-HTTP storage plugin 0.0.0.
- Container platform reported by Snakemake: Linux / WSL2 x86-64, glibc 2.39. Host: Windows x64.
- Core test environment observed in solver CLI output: Python 3.11.15, linopy 0.10.1, highspy 1.16.0. Upstream-build and GridStorm-core environments are intentionally separate.
- `pixi install -e default --locked` completed successfully in the resumed attempt. After the successful build, `du -sh` inside the volume measured `.pixi` 3.3G, `data` 2.2G (downloaded archives plus extracted copies), `resources` 10.6M, `results` 408K, rattler cache 3.4G; the whole volume measured 6.0G (the cache and `.pixi` share hardlinks, so the parts do not add up). These are observed rounded disk sizes, not minimum requirements.

## Configuration and modeling assumptions

The only GridStorm overlay is `run.name: test-elec`, which repeats the upstream setting. Scientific configuration is unchanged from `config/test/config.electricity.yaml` at the pinned commit:

- `tutorial: true`, Belgium only (`BE`), five spatial clusters.
- Snapshot bounds `2013-03-01` through `2013-03-08`; temporal averaging `24h`. Bounds alone are not evidence of the final snapshot count or weights.
- Reduced prebuilt weather cutout `be-03-2013-era5`; renewable availability/potentials are calculated by atlite from weather, land-cover/protected-area exclusions, and offshore shipping constraints, not fabricated constant capacity factors.
- Electricity-only, no sector coupling; capacity expansion includes renewable/conventional generators, batteries, H2 stores/links, and transmission (`transmission_limit: vopt`). Existing renewable-capacity estimation uses `from_powerplantmatching: true`.
- Dynamic line rating enabled, maximum multiplier 1.3; transmission losses zero; no conventional unit commitment.
- HiGHS, upstream `highs-default` options with `threads: 1`; Snakemake `--cores 1`; `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`.
- The desired import is `resources/test-elec/networks/composed_2050.nc` **before** `solve_network`, not the solved expansion result. A plain `n.optimize()` on that file is a capacity-expansion LOPF, not fixed-capacity dispatch. It does not automatically recreate PyPSA-Eur's extra constraints/callbacks. The optional comparison to the upstream solved objective is therefore descriptive, not an equivalence assertion.

## Commands and interruption recovery

From the GridStorm repository in a Bash-compatible shell:

```bash
bash pipelines/pypsa-eur/build.sh ../upstream/pypsa-eur ../build-pypsa-eur/out
```

The script verifies the pinned SHA, installs the locked pixi environment, and runs:

```bash
pixi run -e default snakemake --cores 1 \
  results/test-elec/networks/solved_2050.nc \
  --configfile config/test/config.electricity.yaml /cfg/config.gridstorm.yaml
```

`BUILD_TIMEOUT_S` defaults to 2400 seconds and bounds the entire container command, including installation; timeout sends TERM and then KILL after a 30-second grace period. Logs are streamed to the external output directory. Named-volume state survives container removal. A timeout/interruption can leave a stale Snakemake lock and partial remote downloads; resuming is **not** a guarantee that every cached file is intact.

First inspect `docker ps -a` and the old container's logs. Only after establishing that no build container/process remains, remove the stale lock with:

```bash
MSYS_NO_PATHCONV=1 docker run --rm \
  -v gridstorm-pypsa-eur-work:/work \
  -v "$(pwd)/pipelines/pypsa-eur:/cfg:ro" \
  ghcr.io/prefix-dev/pixi:0.81.0 bash -c '
    cd /work/pypsa-eur
    pixi run -e default snakemake --unlock \
      --configfile config/test/config.electricity.yaml /cfg/config.gridstorm.yaml
  '
```

Do not run `--unlock` against a live workflow. Do not change the read-only upstream clone to work around downloaded-data problems.

After the upstream build, the remaining commands are:

```bash
uv run --project pipelines/network-import python pipelines/pypsa-eur/replace_load.py \
  --network ../build-pypsa-eur/out/composed_2050.nc \
  --synthetic ../build-pypsa-eur/inputs/demand_hourly.csv \
  --out ../build-pypsa-eur/out/composed_2050_synthetic_load.nc
uv run --project pipelines/network-import python pipelines/pypsa-eur/import_network.py \
  --network ../build-pypsa-eur/out/composed_2050_synthetic_load.nc
uv run --project services/api python pipelines/pypsa-eur/solve_check.py \
  --upstream-solved ../build-pypsa-eur/out/solved_2050.nc
```

The importer uses the existing `network_import.canonical.from_pypsa` converter without modifying it. The solve checker rejects nonoptimal termination, nonfinite objectives, and maximum nodal active-power balance residual above `1e-4 MW`; it reports actual objective, optimization wall time, process peak RSS in MiB, versions, and snapshot-weight sum. Its small two-bus regression is utility validation only, **not** evidence that the Belgium dataset was built or solved.

## Observed attempts

All timestamps below come from the command output / host clock (2026-11-14 UTC), not an assumed wall-clock date.

1. Initial continuation inspection: `docker ps -a` listed only three unrelated exited containers; the previous build container `b6b57374081a` was absent (`No such container`). The prior `build2.log` ended at `retrieve_eu_nuts_2021`. Persistent workflow log `2026-11-14T161219.383511.snakemake.log` showed one of 59 steps completed, then retrieval of the NUTS archive. A filesystem search found no NetCDF outputs under `resources` or `results`.
2. First bounded resume: locked pixi installation succeeded, but Snakemake failed with `LockException: Directory cannot be locked`, exit code 1; observed command wall time 69.18 s. After confirming no live build with `docker ps`, explicit `snakemake --unlock` returned `Unlocked working directory` (9.87 s).
3. Unlocked resume: Snakemake ran `retrieve_eu_nuts_2021` and failed at `rules/retrieve.smk:329` with `ReadError: data/eu_nuts2021/archive/2021-01-01/ref-nuts-2021-01m.geojson.zip is not a zip file`. Exit code 1, workflow elapsed 18.232698 s, enclosing command wall time 66.20 s. The workflow removed the local storage copy on exit. This is an observed corrupt/incomplete local input, not proof that the upstream archive itself is invalid.
4. Independent HTTP probe of `https://data.pypsa.org/workflows/eur/eu_nuts2021/2021-01-01/ref-nuts-2021-01m.geojson.zip`: HTTP 200, `Content-Length: 184483756`; first 65,536 bytes received in 1.97 s. A later ranged request returned HTTP 206, `Content-Range: bytes 0-127/184483756`, and ZIP magic `PK\x03\x04`. Neither probe validates the entire archive. The subsequent retry starts after Snakemake removed its failed cached copy.
5. Interrupted resume: a later run, killed when its controlling session ended, left a stale lock and a truncated 210,345,984-byte cached `shipdensity_global.zip` (the archive is 534,907,254 bytes). After confirming `docker ps -a` showed no build container, the truncated cache file was deleted (`.snakemake/storage/cached-http/data.pypsa.orgworkflows/eur/ship_raster/v5/shipdensity_global.zip`) and `snakemake --unlock` returned `Unlocked working directory`. [INFERENCE] Deleting the partial file matters: the truncated cache file survived the interruption, and a truncated cached archive is the likely cause of the attempt-3 `not a zip file` error.
6. **Successful run** (`build6.log`): `bash pipelines/pypsa-eur/build.sh ../upstream/pypsa-eur ../build-pypsa-eur/out` from 21:10:50 to 21:26:02 UTC, exit 0, 912.6 s command wall time including container setup and the `pixi install` check. Snakemake reported `58 of 58 steps (100%) done`, `Elapsed time: 0:14:33.222657`; the script recorded `snakemake_wall_s=876`. The log has 24 `Retrieving from storage:` lines (all `data.pypsa.org` except the synthetic demand file from `zenodo.org/records/10820928`); the largest is the 534,907,254-byte shipping raster. Outputs copied to `build-pypsa-eur/out/`: `base.nc`, `base_extended.nc`, `simplified.nc`, `clustered.nc`, `composed_2050.nc` (250,126 B), `solved_2050.nc` (371,763 B).

External attempt logs: `D:/New folder (4)/build-pypsa-eur/build2.log` … `build6.log`; the latest workflow log is `build-pypsa-eur/out/snakemake.log`. They are external working files, not promised redistributable repository artifacts.

## Upstream solve (inside the build)

Upstream `solve_network` (PyPSA 1.2.4, linopy 0.8.0, HiGHS 1.13.1 IPM, `run_crossover: off`, `threads: 1`) built a 1201-row, 570-column LP, added the solar-potential extra constraint, and reported objective **50,009,017.34 EUR** (`5.0009017340e+07`). HiGHS's own final status was **`Unknown`, not `Optimal`**: after the interior-point solve it found 5 relative dual-residual errors up to 2.98e-07 (tolerance 1e-07) and a relative primal-dual objective error of 3e-05, and downgraded the status. linopy then logged `Solution status unknown. Trying to parse solution.` / `Solution parsed successfully.` and returned `Termination condition: unknown`. The upstream benchmark file recorded 4.89 s and max RSS 744.79 MB for the whole `solve_network` job. The upstream objective is therefore a near-optimal IPM point without crossover, not a certified optimum.

## Imported dataset and GridStorm LOPF

`replace_load.py` (pipelines env, PyPSA 1.4.0, xarray 2026.9.0, pandas 3.1.1) input: `composed_2050.nc` (sha256 `0648933ae2cbffdbf61bcd80df999a7af6eedc84cc56b69d0e9acdb65c532b36`) and `demand_hourly.csv` from Zenodo record 10820928 (published 2024-03-15, CC-BY-4.0; 464,620,414 bytes; md5 `a9b59e5a32ad422bcd9e12fea5dc291a` = the md5 the Zenodo API publishes; sha256 `1c96ff5a041abbb85d6d24f880455e13a931c5cbaf0e54e3f7fc0f7644b12bc0`). That file was copied out of the build volume (`data/synthetic_electricity_demand/primary/v2/load_synthetic_raw.csv`, a `copy2` of the Zenodo download). Method and checks:

- The upstream per-bus `p_set` is national 24 h mean × time-invariant JRC Energy Atlas share. Measured share spread across the 7 days: 4.02e-10. The old national daily means equal `resample("24h").mean()` of the built hourly OPSD BE series within 3.5e-6 MW, which confirms the aggregation convention.
- New `p_set` = mean of the 24 hourly synthetic BE values in each snapshot window × the same shares (BE0 0AC 0.145069, BE0 1AC 0.077544, BE0 2AC 0.168082, BE0 3AC 0.143233, BE0 4AC 0.466072). Only `loads_t_p_set` changes; every other NetCDF variable is asserted identical. Global attributes `license`, `license_url`, `attribution` and `gridstorm_load_replacement` were added.
- New vs old (OPSD) series, 35 values: 0 equal values, 0 within 1 MW; |diff| between 1.47 and 266.58 MW. Pearson correlation of the national daily series 0.702; across all 35 per-bus values 0.998, which mostly reflects the shared bus shares.
- Totals vs source: max |national daily − synthetic daily mean| 1.8e-12 MW. Weighted energy 1,728,907.786 MWh vs 168 h synthetic sum 1,728,907.786 MWh (relative diff 2.7e-16).
- National daily means (MW): 03-01 11,178.892; 03-02 10,000.780; 03-03 9,920.443; 03-04 10,791.649; 03-05 10,158.634; 03-06 9,941.437; 03-07 10,045.990.

Import (pipelines env) of `composed_2050_synthetic_load.nc` logged `Importing network from PyPSA version v1.2.4 while current version is v1.4.0` as a warning and loaded without error. `data/networks/pypsa-eur-be/`:

- `network.nc`: 310,377 bytes, sha256 `7eaa427bd3437bb1c15e1135375f385cc72dd620bace9dfa8b82cfe0fc41f857`. The size grew by the attribution attributes.
- Contents, read back with PyPSA 1.4.0: 5 AC buses at 380 kV (all `country == BE`, x 4.27–5.61 °E, y 50.47–51.23 °N) plus 5 H2 buses; 6 lines (all `s_nom_extendable`); 33 generators; 5 battery storage units; 5 H2 stores; 5 electrolysis + 5 fuel-cell links; one `CO2Limit` global constraint (primary energy ≤ 1,917,808 t). 7 daily snapshots, 2013-03-01 to 2013-03-07, each with objective weight 24 h (168 h total).
- Existing capacity by carrier (`canonical.json` summary, MW): CCGT 6634.2, nuclear 4096.0, offwind-ac 2752.2, onwind 1724.0, solar 937.6, waste 293.8, oil 130.2, biomass 113.0; offwind-dc / offwind-float / solar-hsat / battery 0 (extendable only). Peak snapshot load 11,178.9 MW; weighted load energy 1,728,908 MWh (mean 10.29 GW). Load fields carry provenance `modeled`.
- Manifest: `license.spdx` `ODbL-1.0`, `redistribution: permitted`, attribution block from the licensing note §4; quality flag `synthetic demand, not observed 2013 load`; transformations `build`, `replace_load`, `import`.
- `network_import validate pypsa-eur-be`: `errors: []`; one warning, `6 sub-networks … bus counts [5, 1, 1, 1, 1, 1]`. Expected: the five H2 buses are connected only by links, which do not form passive-branch sub-networks.

`uv run --project services/api python pipelines/pypsa-eur/solve_check.py --upstream-solved ../build-pypsa-eur/out/solved_2050.nc` (core env: Python 3.11.15, PyPSA 1.4.0, linopy 0.10.1, highspy 1.16.0, Windows 10.0.26300, `threads=1`; HiGHS default simplex with crossover):

| Metric | Value |
|---|---|
| Status / termination | `ok` / `optimal` |
| Objective | 49,392,841.28 EUR (was 49,987,630.77 EUR with the OPSD load) |
| `n.optimize` wall time | 1.46 s (first run), 1.33 s (repeat) |
| Process peak RSS (Windows `peak_wset`) | 299.6 MiB (first run), 300.0 MiB (repeat) |
| Max nodal balance residual | 1.14e-12 MW |
| Snapshots / weight sum | 7 / 168 h |
| Relative difference to upstream objective | −1.23e-2 (upstream solved the OPSD load, so this is not like-for-like) |

The plain `n.optimize()` LP has 1203 constraint duals versus 1208 upstream; the 5 extra upstream rows coincide with the five clusters' solar-potential constraints. [INFERENCE] The GridStorm LP is thus a relaxation of the upstream problem. With the OPSD load its objective was 0.043 % below upstream. Since the load replacement the two runs have different demand, so the comparison is descriptive only.

StormSpec preset `pypsa-eur-be-baseline` (dispatch-only: extendables fixed at nominal capacity, `CO2Limit` dropped, load shedding at VOLL 10,000 EUR/MWh; `workers/pypsa/scripts/precompute_presets.py --only pypsa-eur-be-baseline`): `feasible`, objective 56,023,127.86 EUR, unserved energy 0 MWh, solver 0.152 s, `run_scenario` 4.108 s, child-process peak RSS 281.0 MiB (`psutil peak_wset`). That is below the 350 MiB live-execution threshold; the API configuration was not changed. Analytics: `services/analytics/scripts/precompute_analytics.py --network pypsa-eur-be` wrote `capacity`, `costs`, `energy_balance`, `summary` and `index.json`.

Tests: `cd pipelines/pypsa-eur && uv run pytest -q` (own `pyproject.toml`; PyPSA 1.4.0, linopy 0.10.1, highspy 1.16.0): `test_solve_check.py` (two-bus weighted merit-order objective computed by hand; infeasible case rejected) and `test_dataset.py` (manifest sha256/bytes, ≤ 10 MB, ODbL-1.0/permitted, attribution and quality flag, transformation steps, synthetic source sha256, national daily totals and weighted energy within 1e-3, `modeled` load provenance, 5 BE AC buses inside Belgium's bounding box, 24 h weights, daily totals 9,900–11,200 MW, `0 ≤ p_max_pu ≤ 1`, canonical/NetCDF counts agree, LOPF `optimal` with balance residual < 1e-4 MW and objective 49,392,841.28 EUR ± 1e-6 relative): `8 passed`.

## Input sizes and redistribution assessment

The tutorial still has substantial shared data dependencies; a reduced weather cutout is not a complete prebuilt model. HEAD probes observed the following individual archive sizes (bytes): NUTS 184,483,756; CORINE 34,618,548; GDP 4,014,594; WorldPop 15,441,408; EEZ 26,358,854; Natura 2025-08-15 27,852,863; shipping raster 534,907,254; synthetic demand v2 464,620,414; ENTSO-E demand 28,816,465. These are preflight HTTP metadata, **not downloaded-volume or final-network measurements**. No multi-GB input archive was deliberately requested as a fallback.

Licenses are not uniformly MIT. Sources below refer to the pinned upstream [license summary](https://github.com/PyPSA/pypsa-eur/blob/c8209014468dbb3bf43257f45d34abc6e3c8c898/doc/licenses.md), [data inventory](https://github.com/PyPSA/pypsa-eur/blob/c8209014468dbb3bf43257f45d34abc6e3c8c898/doc/data_inventory.csv), and [data-source/versioning documentation](https://github.com/PyPSA/pypsa-eur/blob/c8209014468dbb3bf43257f45d34abc6e3c8c898/doc/data_sources.md):

| Input/category | Upstream license statement / caveat |
|---|---|
| Original code / docs / most config | MIT / CC-BY-4.0 / CC0-1.0 respectively; not a license for all downloaded inputs |
| OSM electricity topology / OSM boundaries | ODbL-1.0 / ODbL; attribution and database obligations must be assessed for derived clustered data |
| powerplantmatching / technology-data | CC-BY-4.0 |
| WorldPop / gridded GDP / EEZ / shipping density / synthetic demand / Natura 2000 | CC-BY-4.0 according to the input inventory |
| CORINE | `Custom similar to CC-BY`; must retain the actual Copernicus terms, not relabel as plain CC-BY |
| NUTS 2021 | Reuse policy following 2011/833/EU |
| JRC ARDECO | `similar to CC-BY` |
| OPSD / ENTSO-E electricity demand | `unknown` in the inventory; the tutorial does retrieve both demand datasets |
| NESO / DESNZ / ONS dependencies | NESO Open Data License v1.0 / Open Government Licence v3.0 / Open Government Licence v.3.0; retrieval by a general rule does not imply UK records survive in the Belgium output |
| ERA5-derived cutout | Weather-derived modeled profiles; specific cutout/ERA5 redistribution terms require checking before public redistribution |

**Redistribution decision (superseded 2026-11-15):** the only blocking input, the ENTSO-E/OPSD load, was removed by `replace_load.py`. The dataset is published under ODbL-1.0 with `license.redistribution: permitted`. The decision and the remaining caveats (NUTS non-commercial clause, technology-data licence mismatch, IAEA terms) are in [pypsa-eur-be-licensing.md](pypsa-eur-be-licensing.md). Restricted inputs elsewhere in the upstream inventory (LAU, aquifer data) were not in the observed electricity tutorial DAG. Raw downloaded inputs are still never committed.
