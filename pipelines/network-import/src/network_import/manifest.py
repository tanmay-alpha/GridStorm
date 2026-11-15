"""Write ``canonical.json``, ``manifest.json`` and ``data/networks/catalog.json``."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import pypsa
import xarray as xr
from canonical_grid import (
    CanonicalNetwork,
    CatalogEntry,
    DatasetManifest,
    NetworkCatalog,
    dump_json,
    load_canonical,
    load_manifest,
)

from network_import.cost_basis import dataset_cost_basis
from network_import.paths import networks_dir, sha256_file, write_text

MAX_NETCDF_BYTES = 10 * 1024 * 1024

BASE_UNITS: dict[str, str] = {
    "buses.v_nom_kv": "kV",
    "lines.v_nom_kv": "kV",
    "lines.s_nom_mva": "MVA",
    "lines.x_ohm": "ohm",
    "lines.r_ohm": "ohm",
    "lines.length_km": "km",
    "transformers.s_nom_mva": "MVA",
    "transformers.x_pu": "p.u. on transformers.s_nom_mva",
    "transformers.r_pu": "p.u. on transformers.s_nom_mva",
    "transformers.tap_ratio": "p.u. (dimensionless)",
    "links.p_nom_mw": "MW",
    "links.efficiency": "dimensionless (0,1]",
    "generators.p_nom_mw": "MW",
    "generators.marginal_cost_eur_per_mwh": "cost units (basis unknown)/MWh",
    "loads.p_peak_mw": "MW",
    "loads.p_mean_mw": "MW",
    "loads.energy_mwh": "MWh",
    "storage_units.p_nom_mw": "MW",
    "storage_units.max_hours": "h",
    "stores.e_nom_mwh": "MWh",
    "carriers.co2_emissions_t_per_mwh": "t/MWh (thermal input)",
    "snapshots.resolution_h": "h",
}

MISSING_VALUE_POLICY = (
    "Values the source does not provide are null in canonical.json and are never invented. "
    "PyPSA component defaults that would masquerade as data (e.g. line length 0) are emitted as "
    "null and listed in canonical.json assumptions. NaN/inf never appear in JSON. network.nc keeps "
    "PyPSA defaults because PyPSA requires finite values; flagged substitutions are listed in "
    "quality_flags."
)

MANIFEST_NAME = "manifest.json"
CANONICAL_NAME = "canonical.json"


def write_canonical(dataset_dir: Path, canonical: CanonicalNetwork) -> bool:
    return write_text(dataset_dir / CANONICAL_NAME, dump_json(canonical))


def export_netcdf(n: pypsa.Network, path: Path) -> bool:
    """Export ``n`` to ``path``; keep the existing file if its content is identical.

    HDF5 output is not byte-reproducible across exports (internal object layout), so "identical"
    means ``xarray.Dataset.identical`` (same variables, values, coords and attributes). This keeps
    the committed file and its sha256 stable on re-runs.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp.nc")
    n.export_to_netcdf(tmp)
    if path.exists():
        with xr.open_dataset(path) as old, xr.open_dataset(tmp) as new:
            same = old.identical(new)
        if same:
            tmp.unlink()
            return False
    tmp.replace(path)
    return True


#: Derived per-network outputs written after the manifest (precomputed analytics). They carry their
#: own sha256 index that pins network.nc and manifest.json, so listing them here would be circular.
DERIVED_SUBDIRS = ("analytics",)


def file_entries(dataset_dir: Path) -> list[dict[str, Any]]:
    """sha256 + size of every dataset file except the manifest itself and derived subdirectories."""
    out = []
    for p in sorted(dataset_dir.rglob("*")):
        if not p.is_file() or p.name == MANIFEST_NAME and p.parent == dataset_dir:
            continue
        if p.relative_to(dataset_dir).parts[0] in DERIVED_SUBDIRS:
            continue
        if p.name.endswith((".part", ".tmp.nc")):
            raise RuntimeError(f"stray temporary file {p}; remove it and re-run")
        out.append(
            {
                "path": p.relative_to(dataset_dir).as_posix(),
                "sha256": sha256_file(p),
                "bytes": p.stat().st_size,
            }
        )
    return out


def write_manifest(
    dataset_dir: Path,
    *,
    network_id: str,
    name: str,
    description: str,
    source: Mapping[str, Any],
    retrieved_at: str,
    license: Mapping[str, Any],
    coverage: Mapping[str, str],
    quality_flags: Iterable[str],
    transformations: Iterable[Mapping[str, str]],
    engines: Iterable[str],
    provenance_class: str,
    units: Mapping[str, str] | None = None,
    missing_value_policy: str = MISSING_VALUE_POLICY,
) -> DatasetManifest:
    nc = dataset_dir / "network.nc"
    if nc.exists() and nc.stat().st_size > MAX_NETCDF_BYTES:
        raise RuntimeError(f"{nc} is {nc.stat().st_size} bytes > 10 MB; must not be committed")
    basis = dataset_cost_basis(network_id)
    declared_units = dict(units if units is not None else BASE_UNITS)
    declared_units["generators.marginal_cost_eur_per_mwh"] = basis["price_unit"]
    manifest = DatasetManifest.model_validate(
        {
            "network_id": network_id,
            "name": name,
            "description": description,
            "source": dict(source),
            "retrieved_at": retrieved_at,
            "files": file_entries(dataset_dir),
            "license": dict(license),
            "coverage": dict(coverage),
            "missing_value_policy": missing_value_policy,
            "units": declared_units,
            "cost_basis": basis,
            "quality_flags": list(quality_flags),
            "transformations": [dict(t) for t in transformations],
            "engines": list(engines),
            "provenance_class": provenance_class,
        }
    )
    write_text(dataset_dir / MANIFEST_NAME, dump_json(manifest))
    return manifest


def update_catalog(root: Path | None = None) -> NetworkCatalog:
    """Rebuild ``catalog.json`` from every dataset directory holding a valid canonical.json and
    manifest.json (directories still being built by other tools are skipped)."""
    root = root or networks_dir()
    entries = []
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        if not ((d / CANONICAL_NAME).exists() and (d / MANIFEST_NAME).exists()):
            continue
        manifest = load_manifest(d / MANIFEST_NAME)
        canonical = load_canonical(d / CANONICAL_NAME)
        if manifest.network_id != d.name or canonical.network_id != d.name:
            raise RuntimeError(f"{d}: network_id does not match directory name")
        entries.append(CatalogEntry(id=d.name, path=d.name))
    catalog = NetworkCatalog(networks=entries)
    write_text(root / "catalog.json", dump_json(catalog))
    return catalog
