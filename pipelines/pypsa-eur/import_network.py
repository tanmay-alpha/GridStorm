"""Import the reduced PyPSA-Eur Belgium tutorial network into ``data/networks/pypsa-eur-be/``.

Input is the *unsolved* network produced by ``build.sh`` (``composed_2050.nc``: clustered,
temporally averaged, all carriers attached, before ``solve_network``). The file is copied
byte-for-byte (so its sha256 is traceable to the upstream build), loaded with the GridStorm
PyPSA (1.4.x) to prove compatibility, converted with ``network_import.canonical.from_pypsa`` and
described by a ``dataset-manifest/1.0``.

Run in the pipelines env::

    uv run --project pipelines/network-import python pipelines/pypsa-eur/import_network.py \
        --network <build-out>/composed_2050.nc
"""

from __future__ import annotations

import argparse
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pypsa
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
from network_import.paths import networks_dir, sha256_file, write_text

NETWORK_ID = "pypsa-eur-be"
NAME = "PyPSA-Eur Belgium tutorial (5 clusters, 2013-03-01..08, 24 h)"
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
    # Conventional capacities from powerplantmatching; renewables from the
    # estimate_renewable_capacities step (IRENA statistics distributed by potential).
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
}

ASSUMPTIONS = [
    "Built with the upstream PyPSA-Eur tutorial configuration config/test/config.electricity.yaml "
    f"({PYPSA_EUR_TAG}, {PYPSA_EUR_SHA[:12]}) without changes: BE only, 5 clusters, snapshots "
    "2013-03-01..2013-03-08 averaged to 24 h, renewable profiles from the pre-built ERA5 cutout "
    "be-03-2013-era5.",
    "network.nc is the composed network before solve_network: extendable generators, storage, "
    "H2 store/links and lines (transmission_limit vopt) carry capital costs; GridStorm dispatch "
    "runs fix extendable capacities at their current p_nom.",
    "Line ratings include dynamic line rating (max_line_rating 1.3) as time-varying s_max_pu; "
    "canonical s_nom_mva is the static nominal rating.",
    "Buses are k-means clusters of the OSM-derived transmission grid; coordinates are cluster "
    "representative points, not individual substations.",
]

QUALITY_FLAGS = [
    "Snapshots are 24 h averages (8 snapshots); intra-day peaks are smoothed out.",
    "Load time series for BE 2013 come from OPSD/ENTSO-E (licence 'unknown' in the PyPSA-Eur data "
    "inventory); see license.redistribution.",
    "Capital-cost-bearing extendable components: a plain n.optimize() is a capacity-expansion "
    "LOPF, not a dispatch run.",
]

LICENSE = License(
    spdx="ODbL-1.0 AND CC-BY-4.0 AND LicenseRef-ENTSOE-OPSD-unknown",
    url="https://pypsa-eur.readthedocs.io/en/latest/data_sources/",
    attribution=(
        "PyPSA-Eur contributors (code MIT, https://github.com/PyPSA/pypsa-eur); grid topology "
        "© OpenStreetMap contributors (ODbL-1.0) via the PyPSA-Eur OSM prebuilt network; power "
        "plants: powerplantmatching (CC-BY-4.0); costs: PyPSA technology-data (CC-BY-4.0); "
        "weather: Copernicus Climate Change Service ERA5 (CC-BY-4.0); land cover: Copernicus "
        "CORINE; protected areas: EEA Natura 2000 (CC-BY-4.0); electricity demand: Open Power "
        "System Data time series / ENTSO-E."
    ),
    redistribution="unknown",
)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--network", type=Path, required=True, help="composed_2050.nc from build.sh")
    ap.add_argument("--out", type=Path, default=networks_dir() / NETWORK_ID)
    args = ap.parse_args()

    src: Path = args.network
    size = src.stat().st_size
    if size > MAX_BYTES:
        raise SystemExit(f"{src} is {size} bytes > 10 MB contract limit")
    built_at = datetime.fromtimestamp(src.stat().st_mtime, UTC).replace(microsecond=0)

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    nc = out / "network.nc"
    shutil.copyfile(src, nc)

    n = pypsa.Network(nc)
    print(f"loaded with pypsa {pypsa.__version__}: {n}")

    canonical = from_pypsa(
        n, NETWORK_ID, NAME,
        field_provenance=FIELD_PROVENANCE,
        assumptions=ASSUMPTIONS,
    )
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
        retrieved_at=built_at.isoformat(),
        files=[FileEntry(path="network.nc", sha256=sha256_file(nc), bytes=nc.stat().st_size)],
        license=LICENSE,
        coverage=Coverage(
            geographic="Belgium (BE), 5 clustered transmission buses",
            temporal=f"{snaps.start} .. {snaps.end}, {snaps.count} snapshots at "
                     f"{snaps.resolution_h} h",
        ),
        units={
            "v_nom": "kV", "p_nom": "MW", "s_nom": "MVA", "e_nom": "MWh", "x": "ohm (lines)",
            "r": "ohm (lines)", "length": "km", "marginal_cost": "EUR/MWh",
            "capital_cost": "EUR/MW/a (annuitised, per snapshot-weighted horizon)",
            "co2_emissions": "t/MWh",
        },
        missing_value_policy=(
            "Values PyPSA-Eur does not provide are null in canonical.json; nothing is imputed by "
            "GridStorm. Gaps in upstream load data were filled by PyPSA-Eur (interpolation, time "
            "shift, synthetic supplement) before import."
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
    print(f"wrote {out} ({size} bytes network.nc, sha256 {manifest.files[0].sha256})")


if __name__ == "__main__":
    main()
