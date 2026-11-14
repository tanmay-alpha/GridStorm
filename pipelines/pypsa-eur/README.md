# PyPSA-Eur Belgium tutorial network (`pypsa-eur-be`)

Reproducible build of the reduced PyPSA-Eur electricity model of Belgium and its import into
`data/networks/pypsa-eur-be/`. Full write-up (versions, licences, timings, results):
[`docs/research/pypsa-eur-build.md`](../../docs/research/pypsa-eur-build.md).

| File | Purpose |
|---|---|
| `build.sh` | Runs the upstream Snakemake workflow in a Linux container (`ghcr.io/prefix-dev/pixi:0.81.0`), pinned to PyPSA-Eur `v2026.09.0` (`c8209014468d`), config `config/test/config.electricity.yaml` + `config.gridstorm.yaml`. State (clone, pixi env, package cache, downloaded data) lives in the Docker volume `gridstorm-pypsa-eur-work`, so reruns resume. |
| `config.gridstorm.yaml` | GridStorm overlay — intentionally only restates `run.name`; the tutorial settings are used unchanged. |
| `replace_load.py` | Replaces the upstream ENTSO-E/OPSD Belgian load (not redistributable) with the CC-BY-4.0 synthetic BE series (Zenodo 10820928, sha256-pinned): 24 h means × the upstream JRC Energy Atlas bus shares. Changes only `loads_t_p_set`, adds ODbL-1.0 licence/attribution global attributes, prints a JSON check report (no value equal to the old load, max \|diff\|, correlations, totals vs. source). |
| `import_network.py` | Copies the `replace_load.py` output (rejects networks without the replacement attribute) to `data/networks/pypsa-eur-be/network.nc`, loads it with PyPSA 1.4, writes `canonical.json` (via `network_import.canonical.from_pypsa`) and `manifest.json` (ODbL-1.0). |
| `solve_check.py` | One LOPF over the full horizon with HiGHS (threads=1) in the core env; prints objective, wall time, peak RSS, nodal-balance residual as JSON on stdout. |
| `test_solve_check.py`, `test_dataset.py`, `pyproject.toml` | Checker regression (hand-computed two-bus objective) and dataset validation (manifest hashes, ODbL licence, synthetic load totals, BE scope, physical ranges, optimal LOPF objective); run with `uv run pytest -q` in this directory. `test_dataset.py` skips when the dataset is absent. |

## Reproduce

Requires Docker and a bash (Git Bash/WSL on Windows); the volume measured 6.0 GB after a full build.
If a build is interrupted, delete any truncated file under `.snakemake/storage/cached-http/` in the
volume and run `snakemake --unlock` before resuming (see the research note).

```bash
# 1. upstream clone (read-only input to the container)
git clone https://github.com/PyPSA/pypsa-eur ../upstream/pypsa-eur
git -C ../upstream/pypsa-eur checkout v2026.09.0

# 2. build (CORES=1 by default; outputs *.nc + snakemake.log into the out dir)
bash pipelines/pypsa-eur/build.sh ../upstream/pypsa-eur ../build-pypsa-eur/out

# 3. replace the load with the CC-BY-4.0 synthetic series (464,620,414-byte download)
curl -L -o ../build-pypsa-eur/inputs/demand_hourly.csv \
    https://zenodo.org/records/10820928/files/demand_hourly.csv
uv run --project pipelines/network-import python pipelines/pypsa-eur/replace_load.py \
    --network ../build-pypsa-eur/out/composed_2050.nc \
    --synthetic ../build-pypsa-eur/inputs/demand_hourly.csv \
    --out ../build-pypsa-eur/out/composed_2050_synthetic_load.nc

# 4. import into data/networks/pypsa-eur-be/, then validate
uv run --project pipelines/network-import python pipelines/pypsa-eur/import_network.py \
    --network ../build-pypsa-eur/out/composed_2050_synthetic_load.nc
(cd pipelines/network-import && uv run python -m network_import validate pypsa-eur-be)

# 5. prove it solves in the core env
uv run --project services/api python pipelines/pypsa-eur/solve_check.py \
    --upstream-solved ../build-pypsa-eur/out/solved_2050.nc
```

The container downloads PyPSA-Eur input data from `data.pypsa.org` / Zenodo at build time; none of
it is committed. The published dataset is licensed **ODbL-1.0** (an ODbL Derivative Database of the
OSM-based grid); the attribution block is in the manifest, the NetCDF global attributes and
[`docs/research/pypsa-eur-be-licensing.md`](../../docs/research/pypsa-eur-be-licensing.md) §4.
