"""``from-netcdf``: canonicalise an existing PyPSA NetCDF (e.g. the PyPSA-Eur ``pypsa-eur-be`` build).

The NetCDF is copied to ``data/networks/<id>/network.nc`` unchanged (unless it already is that
file); canonical.json + manifest.json are generated and the catalog is refreshed. All field
provenance not declared by the caller is left unlabelled except the fields ``from_pypsa``
calculates itself.
"""

from __future__ import annotations

import argparse
import shutil
from datetime import UTC, datetime

import pypsa
from canonical_grid import load_manifest

from network_import.canonical import from_pypsa
from network_import.manifest import (
    BASE_UNITS,
    MANIFEST_NAME,
    update_catalog,
    write_canonical,
    write_manifest,
)
from network_import.paths import networks_dir, sha256_file


def _retrieved_at(a: argparse.Namespace, manifest_path) -> str:
    """Explicit --retrieved-at, else the value already recorded (re-runs stay byte-stable), else
    now."""
    if a.retrieved_at:
        return datetime.fromisoformat(a.retrieved_at).isoformat()
    if manifest_path.exists():
        return load_manifest(manifest_path).retrieved_at
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def import_netcdf(a: argparse.Namespace) -> None:
    d = networks_dir() / a.network_id
    dest = d / "network.nc"
    src = a.path.resolve()
    if src != dest.resolve() and not (dest.exists() and sha256_file(dest) == sha256_file(src)):
        d.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
    n = pypsa.Network(dest)
    canonical = from_pypsa(
        n, a.network_id, a.name,
        coordinate_kind="schematic" if a.schematic else "geographic",
        crs=None if a.schematic else f"EPSG:{int(n.srid)}",
        field_provenance=dict(kv.split("=", 1) for kv in a.field_provenance),
        assumptions=a.assumption,
        null_fields=a.null_field,
    )
    write_canonical(d, canonical)
    write_manifest(
        d,
        network_id=a.network_id,
        name=a.name,
        description=a.description or a.name,
        source={"url": a.source_url, "version": a.source_version,
                "publication_date": None, "upstream_commit": a.upstream_commit},
        retrieved_at=_retrieved_at(a, d / MANIFEST_NAME),
        license={"spdx": a.license, "url": a.license_url, "attribution": a.attribution,
                 "redistribution": a.redistribution},
        coverage={"geographic": a.geographic, "temporal": a.temporal},
        quality_flags=a.quality_flag,
        transformations=[
            {"step": "copy", "tool": "network_import from-netcdf", "version": "1.0.0",
             "description": f"Copied PyPSA NetCDF {src.name} unchanged to network.nc."},
            {"step": "canonicalize", "tool": "network_import.canonical.from_pypsa",
             "version": f"pypsa {pypsa.__version__}",
             "description": "Converted to canonical-grid/1.0."},
        ],
        engines=["pypsa"],
        provenance_class=a.provenance_class,
        units=BASE_UNITS,
    )
    update_catalog()
