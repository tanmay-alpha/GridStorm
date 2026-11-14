# PyPSA-Eur Belgium tutorial network (`pypsa-eur-be`)

Reproducible build of the reduced PyPSA-Eur electricity model of Belgium and its import into
`data/networks/pypsa-eur-be/`. Full write-up (versions, licences, timings, results):
[`docs/research/pypsa-eur-build.md`](../../docs/research/pypsa-eur-build.md).

| File | Purpose |
|---|---|
| `build.sh` | Runs the upstream Snakemake workflow in a Linux container (`ghcr.io/prefix-dev/pixi:0.81.0`), pinned to PyPSA-Eur `v2026.09.0` (`c8209014468d`), config `config/test/config.electricity.yaml` + `config.gridstorm.yaml`. State (clone, pixi env, package cache, downloaded data) lives in the Docker volume `gridstorm-pypsa-eur-work`, so reruns resume. |
| `config.gridstorm.yaml` | GridStorm overlay — intentionally only restates `run.name`; the tutorial settings are used unchanged. |
| `import_network.py` | Copies `composed_2050.nc` (unsolved) to `data/networks/pypsa-eur-be/network.nc`, loads it with PyPSA 1.4, writes `canonical.json` (via `network_import.canonical.from_pypsa`) and `manifest.json`. |
| `solve_check.py` | One LOPF over the full horizon with HiGHS (threads=1) in the core env; prints objective, wall time, peak RSS. |

## Reproduce

Requires Docker and a bash (Git Bash/WSL on Windows), ~6 GB free disk for the volume.

```bash
# 1. upstream clone (read-only input to the container)
git clone https://github.com/PyPSA/pypsa-eur ../upstream/pypsa-eur
git -C ../upstream/pypsa-eur checkout v2026.09.0

# 2. build (CORES=1 by default; outputs *.nc + snakemake.log into the out dir)
bash pipelines/pypsa-eur/build.sh ../upstream/pypsa-eur ../build-pypsa-eur/out

# 3. import into data/networks/pypsa-eur-be/
uv run --project pipelines/network-import python pipelines/pypsa-eur/import_network.py \
    --network ../build-pypsa-eur/out/composed_2050.nc

# 4. prove it solves in the core env
uv run --project services/api python pipelines/pypsa-eur/solve_check.py \
    --upstream-solved ../build-pypsa-eur/out/solved_2050.nc
```

The container downloads PyPSA-Eur input data from `data.pypsa.org` / Zenodo at build time. The
licence of the resulting dataset is mixed (ODbL-1.0 grid topology, CC-BY-4.0 inputs, load data of
unknown licence) — see the manifest and the research note before redistributing.
