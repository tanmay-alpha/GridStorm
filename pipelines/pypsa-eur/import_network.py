"""Import the reduced PyPSA-Eur Belgium tutorial network into ``data/networks/pypsa-eur-be/``.

Input is the output of ``replace_load.py``: the *unsolved* upstream ``composed_2050.nc``
(clustered, temporally averaged, all carriers attached, before ``solve_network``) with
``loads_t.p_set`` replaced by the CC-BY-4.0 synthetic demand series. Networks without the
``gridstorm_load_replacement`` attribute (i.e. still carrying the ENTSO-E/OPSD load) are
rejected. The file is copied byte-for-byte, loaded with the GridStorm PyPSA (1.4.x) to prove
compatibility, converted with ``network_import.canonical.from_pypsa`` and described by a
``dataset-manifest/1.0`` (ODbL-1.0).

Run in the pipelines env::

    uv run --project pipelines/network-import python pipelines/pypsa-eur/import_network.py \
        --network <build-out>/composed_2050_synthetic_load.nc
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import pypsa
import xarray as xr
from canonical_grid import (
    Coverage,
    DatasetManifest,
    FileEntry,
    License,
    Source,
    Transformation,
    dump_json,
)
from network_import.canonical import from_pypsa
from network_import.manifest import file_entries
from network_import.paths import networks_dir, sha256_file, write_text
from replace_load import ATTRIBUTION, LICENSE_SPDX, LICENSE_URL, REPLACEMENT_ATTR

NETWORK_ID = "pypsa-eur-be"
NAME = "PyPSA-Eur Belgium tutorial (5 clusters, 2013-03-01..07, 24 h)"
PYPSA_EUR_TAG = "v2026.09.0"
PYPSA_EUR_SHA = "c8209014468dbb3bf43257f45d34abc6e3c8c898"
PYPSA_EUR_RELEASE_DATE = "2026-09"
MAX_BYTES = 10 * 1024 * 1024

FIELD_PROVENANCE = {
    # Cluster buses sit at the representative OSM substation of each k-means cluster.
    "buses.x": "calculated",
    "buses.y": "calculated",
    "buses.v_nom_kv": "modeled",
    "buses.carrier": "modeled",
    "buses.country": "observed",
    # Clustered lines are equivalents of aggregated OSM lines with standard line types.
    "lines.s_nom_mva": "modeled",
    "lines.x_ohm": "modeled",
    "lines.r_ohm": "modeled",
    "lines.length_km": "calculated",
    "lines.num_parallel": "modeled",
    "lines.carrier": "modeled",
    "links.p_nom_mw": "modeled",
    "links.efficiency": "modeled",
    "links.carrier": "modeled",
    # Existing conventional and renewable capacities use powerplantmatching under
    # the pinned tutorial's from_powerplantmatching: true configuration.
    "generators.p_nom_mw": "estimated",
    "generators.carrier": "observed",
    "generators.marginal_cost_eur_per_mwh": "modeled",
    "generators.p_nom_extendable": "modeled",
    "storage_units.p_nom_mw": "estimated",
    "storage_units.carrier": "observed",
    "storage_units.max_hours": "modeled",
    "storage_units.efficiency_store": "modeled",
    "storage_units.efficiency_dispatch": "modeled",
    "stores.e_nom_mwh": "modeled",
    "stores.carrier": "modeled",
    "carriers.color": "modeled",
    "carriers.co2_emissions_t_per_mwh": "modeled",
    "carriers.nice_name": "modeled",
    # Load is the synthetic (temperature-regression model) series, not observed demand.
    "loads.p_peak_mw": "modeled",
    "loads.p_mean_mw": "modeled",
    "loads.energy_mwh": "modeled",
}

ASSUMPTIONS = [
    "Built with the upstream PyPSA-Eur tutorial configuration config/test/config.electricity.yaml "
    f"({PYPSA_EUR_TAG}, {PYPSA_EUR_SHA[:12]}) without changes: BE only, 5 clusters, snapshots "
    "2013-03-01..2013-03-08 averaged to 24 h, renewable profiles from the pre-built ERA5 cutout "
    "be-03-2013-era5.",
    "network.nc is the composed network before solve_network: extendable generators, storage, "
    "H2 store/links and lines (transmission_limit vopt) carry capital costs; a plain "
    "n.optimize() therefore solves capacity expansion, not fixed-capacity dispatch.",
    "Line ratings include dynamic line rating (max_line_rating 1.3) as time-varying s_max_pu; "
    "canonical s_nom_mva is the static nominal rating.",
    "Buses are k-means clusters of the OSM-derived transmission grid; coordinates are cluster "
    "representative points, not individual substations.",
]

QUALITY_FLAGS = [
    "synthetic demand, not observed 2013 load",
    "Load is the Interannual Electricity Demand Calculator BE series (temperature-regression "
    "model on ERA5 2013 weather, Zenodo 10820928) averaged to 24 h and split across buses with "
    "the upstream JRC Energy Atlas keys; the upstream ENTSO-E/OPSD load was removed.",
    "Snapshots are 24 h averages; intra-day peaks are smoothed out.",
    "Capital-cost-bearing extendable components: a plain n.optimize() is a capacity-expansion "
    "LOPF, not a dispatch run.",
    "NUTS 2021 (GISCO) boundaries shaped the clustering and potentials indirectly; their "
    "download provisions exclude commercial use (no NUTS geometry is stored).",
    "technology-data v0.15.0 cost assumptions: CC-BY-4.0 per the PyPSA-Eur data inventory, "
    "GPL-3.0 on the Zenodo release record.",
]

LICENSE = License(
    spdx=LICENSE_SPDX,
    url=LICENSE_URL,
    attribution=ATTRIBUTION,
    redistribution="permitted",
)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--network", type=Path, required=True, help="replace_load.py output (synthetic load)"
    )
    ap.add_argument("--out", type=Path, default=networks_dir() / NETWORK_ID)
    args = ap.parse_args()

    src: Path = args.network
    size = src.stat().st_size
    if size > MAX_BYTES:
        raise SystemExit(f"{src} is {size} bytes > 10 MB contract limit")
    with xr.open_dataset(src) as ds:
        attrs = dict(ds.attrs)
    if REPLACEMENT_ATTR not in attrs or attrs.get("license") != LICENSE_SPDX:
        raise SystemExit(f"{src} was not produced by replace_load.py (ENTSO-E/OPSD load)")
    replacement = json.loads(attrs[REPLACEMENT_ATTR])
    source = replacement["source"]

    n = pypsa.Network(src)
    print(f"loaded with pypsa {pypsa.__version__}: {n}")

    canonical = from_pypsa(
        n,
        NETWORK_ID,
        NAME,
        field_provenance=FIELD_PROVENANCE,
        assumptions=ASSUMPTIONS,
    )
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    nc = out / "network.nc"
    shutil.copyfile(src, nc)
    write_text(out / "canonical.json", dump_json(canonical))

    snaps = canonical.snapshots
    manifest = DatasetManifest(
        network_id=NETWORK_ID,
        name=NAME,
        description=(
            "Reduced PyPSA-Eur electricity-only model of Belgium built from the upstream tutorial "
            "configuration: OSM-based transmission grid clustered to 5 buses, conventional and "
            "renewable generators, battery/H2 storage, one week of March 2013 at daily resolution."
        ),
        source=Source(
            url="https://github.com/PyPSA/pypsa-eur",
            version=PYPSA_EUR_TAG,
            publication_date=PYPSA_EUR_RELEASE_DATE,
            upstream_commit=PYPSA_EUR_SHA,
        ),
        retrieved_at=replacement["input_network_mtime"],
        files=[
            FileEntry(**entry)
            for entry in file_entries(out)
            if entry["path"] in {"network.nc", "canonical.json"}
        ],
        license=LICENSE,
        coverage=Coverage(
            geographic="Belgium (BE), 5 clustered transmission buses",
            temporal=f"{snaps.start} .. {snaps.end}, {snaps.count} snapshots at "
            f"{snaps.resolution_h} h",
        ),
        units={
            "v_nom": "kV",
            "p_nom": "MW",
            "s_nom": "MVA",
            "e_nom": "MWh",
            "x": "ohm (lines)",
            "r": "ohm (lines)",
            "length": "km",
            "marginal_cost": "EUR/MWh",
            "capital_cost": "EUR/MW/a (annuitised, per snapshot-weighted horizon)",
            "co2_emissions": "t/MWh",
        },
        missing_value_policy=(
            "Values PyPSA-Eur does not provide are null in canonical.json; nothing is imputed by "
            "GridStorm. The synthetic BE load has no gaps in the 168 h window (checked by "
            "replace_load.py)."
        ),
        quality_flags=QUALITY_FLAGS,
        transformations=[
            Transformation(
                step="build",
                tool="pypsa-eur (snakemake, pixi env)",
                version=f"{PYPSA_EUR_TAG} ({PYPSA_EUR_SHA[:12]})",
                description=(
                    "pipelines/pypsa-eur/build.sh: snakemake results/test-elec/networks/"
                    "solved_2050.nc with config/test/config.electricity.yaml; "
                    "resources/test-elec/networks/composed_2050.nc taken before solving."
                ),
            ),
            Transformation(
                step=replacement["step"],
                tool=replacement["tool"],
                version=f"synthetic demand sha256 {source['sha256']}",
                description=(
                    "Removed the upstream ENTSO-E Power Statistics/OPSD BE load (not "
                    f"redistributable). {replacement['method']} Source: {source['url']} "
                    f"(doi:{source['doi']}, {source['license']}, {source['bytes']} bytes). "
                    f"Input composed_2050.nc sha256 {replacement['input_network_sha256']}; "
                    "all other variables unchanged; ODbL-1.0 licence and attribution stored "
                    "as NetCDF global attributes."
                ),
            ),
            Transformation(
                step="import",
                tool="pipelines/pypsa-eur/import_network.py + network_import.canonical",
                version=f"pypsa {pypsa.__version__}",
                description="File copied unchanged; canonical.json derived via from_pypsa.",
            ),
        ],
        engines=["pypsa"],
        provenance_class="modeled",
    )
    write_text(out / "manifest.json", dump_json(manifest))
    print(f"wrote {out} ({size} bytes network.nc, sha256 {sha256_file(nc)})")


if __name__ == "__main__":
    main()
