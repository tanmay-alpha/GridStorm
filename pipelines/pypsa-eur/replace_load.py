"""Replace the Belgian load of the PyPSA-Eur tutorial network with CC-BY-4.0 synthetic demand.

The upstream ``composed_2050.nc`` carries the ENTSO-E Power Statistics hourly load for Belgium
(via OPSD), averaged to days and split across the 5 clustered buses with time-invariant JRC
Energy Atlas keys. ENTSO-E's terms forbid redistributing derivatives of that series
(docs/research/pypsa-eur-be-licensing.md), so this step swaps it for the BE column of the
*Interannual Electricity Demand Calculator* (Frysztacki, van der Most, Neumann; Zenodo 10820928,
CC BY 4.0), aggregated exactly like upstream:

* national series = mean of the 24 hourly synthetic values in each snapshot's 24 h window
  (upstream temporal averaging ``24h`` = ``resample("24h").mean()``);
* per-bus value = national daily mean x the bus's JRC Energy Atlas share. The shares are read
  back from the input network as ``p_set / p_set.sum(axis=1)``; they are asserted to be
  time-invariant (spread < 1e-8), i.e. pure spatial keys that carry no load information.

Only the ``loads_t_p_set`` variable changes; every other variable is asserted identical. Global
attributes record the ODbL-1.0 licence, the attribution block and the replacement provenance
(``gridstorm_load_replacement``, read by ``import_network.py``). Prints a JSON check report
(old-vs-new difference and correlation, totals vs. the synthetic source) on stdout.

Get the source file (464,620,414 bytes; md5 published by Zenodo, sha256 pinned below)::

    curl -L -o demand_hourly.csv https://zenodo.org/records/10820928/files/demand_hourly.csv

The PyPSA-Eur build also keeps a byte-identical copy in its volume at
``data/synthetic_electricity_demand/primary/v2/load_synthetic_raw.csv``. Run in the pipelines env::

    uv run --project pipelines/network-import python pipelines/pypsa-eur/replace_load.py \
        --network <build-out>/composed_2050.nc --synthetic demand_hourly.csv \
        --out <build-out>/composed_2050_synthetic_load.nc
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pypsa
import xarray as xr

COUNTRY = "BE"
SHARE_SPREAD_TOLERANCE = 1e-8
REPLACEMENT_ATTR = "gridstorm_load_replacement"

SYNTHETIC_SOURCE = {
    "title": "Interannual Electricity Demand Calculator, demand_hourly.csv",
    "url": "https://zenodo.org/records/10820928/files/demand_hourly.csv",
    "doi": "10.5281/zenodo.10820928",
    "version": "Zenodo record 10820928 (published 2024-03-15; PyPSA-Eur data/versions.csv 'v2')",
    "bytes": 464620414,
    "md5": "a9b59e5a32ad422bcd9e12fea5dc291a",
    "sha256": "1c96ff5a041abbb85d6d24f880455e13a931c5cbaf0e54e3f7fc0f7644b12bc0",
    "license": "CC-BY-4.0",
    "attribution": (
        "Frysztacki, M., van der Most, L., Neumann, F.: Interannual Electricity Demand Calculator, "
        "Zenodo, https://doi.org/10.5281/zenodo.10820928 (CC BY 4.0). Modified: BE column, "
        "2013-03-01..07, 24 h means, split across buses with JRC Energy Atlas keys."
    ),
}

LICENSE_SPDX = "ODbL-1.0"
LICENSE_URL = "https://opendatacommons.org/licenses/odbl/1-0/"
# docs/research/pypsa-eur-be-licensing.md §4 ("attribution block X").
ATTRIBUTION = (
    "PyPSA-Eur Belgium tutorial network (5 clusters, 2013-03-01..07, daily), built with PyPSA-Eur "
    "v2026.09.0 (commit c8209014; code MIT, © Contributors to PyPSA-Eur) and converted by "
    "GridStorm. Load replaced by a synthetic series; see the transformation history. Licensed "
    "under the Open Database License (ODbL) 1.0, https://opendatacommons.org/licenses/odbl/1-0/. "
    "Contains information from the Prebuilt Electricity Network for PyPSA-Eur based on "
    "OpenStreetMap Data v0.7 (Xiong et al., https://doi.org/10.5281/zenodo.18619025), "
    "© OpenStreetMap contributors, available under the ODbL "
    "(https://www.openstreetmap.org/copyright). Electricity demand: Frysztacki, van der Most, "
    "Neumann, Interannual Electricity Demand Calculator, https://doi.org/10.5281/zenodo.10820928 "
    "(CC BY 4.0), daily mean. Spatial split: JRC Energy Atlas, © European Union, 1995-2026 "
    "(CC BY 4.0). Modified. Weather: generated using Copernicus Climate Change Service ERA5 "
    "information (CC BY 4.0), via a PyPSA-Eur atlite cutout. Modified. Land cover: generated "
    "using European Union's Copernicus Land Monitoring Service information (CORINE Land Cover). "
    "Protected areas: Natura 2000, © European Environment Agency (CC BY 4.0), rasterised by "
    "J. Hampp (https://doi.org/10.5281/zenodo.16881818). Shipping density: World Bank, Global "
    "Shipping Traffic Density (CC BY 4.0). Maritime boundaries: Flanders Marine Institute, "
    "MarineRegions.org World EEZ v12 (CC BY 4.0). Power plants: powerplantmatching 0.8.1, "
    "Contributors to powerplantmatching (CC BY 4.0). Costs: PyPSA technology-data v0.15.0 "
    "(https://doi.org/10.5281/zenodo.3994163). Nuclear availability: IAEA, via PyPSA-Eur "
    "(CC BY 4.0). Transmission project TYNDP2020_77: PyPSA-Eur Authors / ENTSO-E TYNDP 2020 "
    "(CC BY 4.0). © EuroGeographics for the administrative boundaries (NUTS 2021, GISCO; "
    "non-commercial use). None of these providers endorses GridStorm. All values were modified "
    "by aggregation, clustering and modelling."
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def daily_synthetic(path: Path, snapshots: pd.DatetimeIndex) -> tuple[pd.Series, pd.Series]:
    """Hourly BE synthetic load covering the snapshots' 24 h windows, and its 24 h means."""
    header = pd.read_csv(path, nrows=0).columns
    column = header.get_loc(COUNTRY)
    hourly = pd.read_csv(path, usecols=[0, column], index_col=0, parse_dates=True)[COUNTRY]
    window = pd.date_range(snapshots[0], snapshots[-1] + pd.Timedelta(hours=23), freq="h")
    hourly = hourly.reindex(window)
    if hourly.isna().any() or not hourly.gt(0).all():
        raise SystemExit(f"synthetic {COUNTRY} series has gaps/non-positive values in the window")
    daily = hourly.resample("24h").mean()
    if not daily.index.equals(snapshots):
        raise SystemExit("snapshots are not consecutive 24 h windows starting at 00:00")
    return hourly, daily


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--network", type=Path, required=True, help="composed_2050.nc from build.sh")
    ap.add_argument("--synthetic", type=Path, required=True, help="Zenodo demand_hourly.csv")
    ap.add_argument("--out", type=Path, required=True, help="output network.nc")
    args = ap.parse_args()

    synthetic_sha = sha256_file(args.synthetic)
    if synthetic_sha != SYNTHETIC_SOURCE["sha256"]:
        raise SystemExit(f"{args.synthetic}: sha256 {synthetic_sha} != pinned source")

    with xr.open_dataset(args.network) as src:
        ds = src.load()
    snapshots = pd.DatetimeIndex(ds["snapshots_snapshot"].values)
    weights = pd.Series(ds["snapshots_objective"].values, index=snapshots)
    if not (weights == 24).all():
        raise SystemExit("expected 24 h snapshot weights (tutorial temporal averaging 24h)")
    loads = pd.DataFrame(
        {"bus": ds["loads_bus"].values, "carrier": ds["loads_carrier"].values},
        index=ds["loads_i"].values,
    )
    country = pd.Series(ds["buses_country"].values, index=ds["buses_i"].values)
    if set(country[loads.bus]) != {COUNTRY} or set(loads.carrier) != {"electricity"}:
        raise SystemExit(f"expected only {COUNTRY} electricity loads")
    old = ds["loads_t_p_set"].to_pandas()
    old.index = snapshots
    if set(old.columns) != set(loads.index):
        raise SystemExit("every load must have a p_set time series")

    shares_t = old.div(old.sum(axis=1), axis=0)
    share_spread = float((shares_t.max() - shares_t.min()).max())
    if share_spread > SHARE_SPREAD_TOLERANCE:
        raise SystemExit(f"bus shares vary over time ({share_spread}); not a static spatial key")
    shares = shares_t.mean() / shares_t.mean().sum()

    hourly, daily = daily_synthetic(args.synthetic, snapshots)
    new = pd.DataFrame(np.outer(daily, shares), index=snapshots, columns=shares.index)

    out_ds = ds.copy()
    out_ds["loads_t_p_set"] = (ds["loads_t_p_set"].dims, new[old.columns].to_numpy())
    out_ds["loads_t_p_set"].attrs = ds["loads_t_p_set"].attrs
    out_ds["loads_t_p_set"].encoding = ds["loads_t_p_set"].encoding
    replacement = {
        "step": "replace_load",
        "tool": "pipelines/pypsa-eur/replace_load.py",
        "source": {**SYNTHETIC_SOURCE, "column": COUNTRY},
        "input_network_sha256": sha256_file(args.network),
        "input_network_mtime": datetime.fromtimestamp(args.network.stat().st_mtime, UTC)
        .replace(microsecond=0)
        .isoformat(),
        "method": (
            f"loads_t.p_set[snapshot, bus] = mean of the 24 hourly synthetic {COUNTRY} values "
            "in [snapshot, snapshot + 24 h) x the bus's upstream JRC Energy Atlas share "
            "(time-invariant p_set / national total of the input network)."
        ),
        "bus_shares": {k: round(float(v), 12) for k, v in shares.items()},
    }
    out_ds.attrs.update(
        license=LICENSE_SPDX,
        license_url=LICENSE_URL,
        attribution=ATTRIBUTION,
        **{REPLACEMENT_ATTR: json.dumps(replacement)},
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_name(args.out.name + ".part")
    out_ds.to_netcdf(tmp)
    tmp.replace(args.out)

    # ---- checks on the written file
    with xr.open_dataset(args.out) as written:
        written = written.load()
    others = [v for v in ds.variables if v != "loads_t_p_set"]
    if set(written.variables) != set(ds.variables) or not all(
        written[v].equals(ds[v]) for v in others
    ):
        raise SystemExit("a variable other than loads_t_p_set changed")
    n = pypsa.Network(args.out)
    got = n.loads_t.p_set[old.columns]
    if not np.array_equal(got.to_numpy(), new[old.columns].to_numpy()):
        raise SystemExit("PyPSA read-back of loads_t.p_set differs from the written values")

    old_nat, new_nat = old.sum(axis=1), got.sum(axis=1)
    diff = (got - old).abs()
    synth_energy = float(hourly.sum())
    model_energy = float((new_nat * weights).sum())
    report = {
        "network_out": str(args.out),
        "network_out_bytes": args.out.stat().st_size,
        "network_out_sha256": sha256_file(args.out),
        "synthetic_sha256": synthetic_sha,
        "values": int(got.size),
        "values_equal_to_old": int((got.to_numpy() == old.to_numpy()).sum()),
        "values_within_1mw_of_old": int((diff.to_numpy() < 1.0).sum()),
        "max_abs_diff_mw": float(diff.to_numpy().max()),
        "min_abs_diff_mw": float(diff.to_numpy().min()),
        "corr_national_daily": float(np.corrcoef(old_nat, new_nat)[0, 1]),
        "corr_per_bus_values": float(
            np.corrcoef(old.to_numpy().ravel(), got.to_numpy().ravel())[0, 1]
        ),
        "share_spread_max": share_spread,
        "national_daily_mw": {str(k.date()): round(float(v), 3) for k, v in new_nat.items()},
        "max_abs_national_vs_synthetic_daily_mw": float((new_nat - daily).abs().max()),
        "energy_model_mwh": model_energy,
        "energy_synthetic_168h_mwh": synth_energy,
        "energy_rel_diff": (model_energy - synth_energy) / synth_energy,
        "peak_snapshot_mw": float(new_nat.max()),
    }
    if report["values_equal_to_old"] or report["max_abs_national_vs_synthetic_daily_mw"] > 1e-6:
        raise SystemExit(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
