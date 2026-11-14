"""Pydantic v2 models for canonical-grid/1.0, dataset-manifest/1.0 and network-catalog/1.0.

Shapes follow ``docs/architecture/contracts.md`` section 2 exactly. Unknown keys are rejected
(``extra="forbid"``), missing physical values are ``null`` and never invented, and NaN/inf are
rejected because JSON cannot represent them.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CANONICAL_SCHEMA_VERSION = "canonical-grid/1.0"
MANIFEST_SCHEMA_VERSION = "dataset-manifest/1.0"
CATALOG_SCHEMA_VERSION = "network-catalog/1.0"

Provenance = Literal["observed", "estimated", "synthetic", "modeled", "calculated"]
DatasetProvenance = Literal["observed", "estimated", "synthetic", "modeled"]
Engine = Literal["pypsa", "pandapower", "grid2op"]

AssetId = Annotated[str, Field(min_length=1)]
PositiveFloat = Annotated[float, Field(gt=0)]
NonNegFloat = Annotated[float, Field(ge=0)]
Efficiency = Annotated[float, Field(gt=0, le=1)]

_NETWORK_ID = r"^[a-z0-9][a-z0-9-]{1,63}$"
_SHA256 = r"^[0-9a-f]{64}$"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


# --------------------------------------------------------------------------- canonical-grid/1.0


class Snapshots(_Model):
    count: int = Field(ge=1)
    start: str | None = Field(
        description="ISO-8601 timestamp of the first snapshot; null if the snapshot index is not "
        "a datetime (e.g. PyPSA's default single snapshot 'now')."
    )
    end: str | None
    resolution_h: PositiveFloat | None = Field(
        description="Snapshot weighting in hours (uniform); null if weightings are not uniform."
    )

    @field_validator("start", "end")
    @classmethod
    def _iso(cls, v: str | None) -> str | None:
        if v is not None:
            datetime.fromisoformat(v)
        return v


class Bus(_Model):
    id: AssetId
    name: str | None
    x: float | None = Field(description="Longitude (geographic) or layout x (schematic).")
    y: float | None = Field(description="Latitude (geographic) or layout y (schematic).")
    v_nom_kv: PositiveFloat | None
    carrier: str | None
    country: str | None


class Line(_Model):
    id: AssetId
    bus0: AssetId
    bus1: AssetId
    v_nom_kv: PositiveFloat | None
    s_nom_mva: NonNegFloat | None = Field(
        description="Thermal rating; null when the source declares no limit "
        "(e.g. MATPOWER RATE_A=0)."
    )
    x_ohm: float | None
    r_ohm: float | None
    length_km: NonNegFloat | None
    num_parallel: NonNegFloat | None
    carrier: str | None


class Transformer(_Model):
    id: AssetId
    bus0: AssetId
    bus1: AssetId
    s_nom_mva: NonNegFloat | None
    x_pu: float | None = Field(description="Series reactance in p.u. on s_nom_mva.")
    r_pu: float | None = Field(description="Series resistance in p.u. on s_nom_mva.")
    tap_ratio: PositiveFloat | None


class Link(_Model):
    id: AssetId
    bus0: AssetId
    bus1: AssetId
    p_nom_mw: NonNegFloat | None
    efficiency: Efficiency | None
    carrier: str | None


class Generator(_Model):
    id: AssetId
    bus: AssetId
    carrier: str | None
    p_nom_mw: NonNegFloat | None
    marginal_cost_eur_per_mwh: float | None
    p_nom_extendable: bool | None
    is_variable: bool | None = Field(
        description="True if the generator has a time-varying availability profile "
        "(p_max_pu series)."
    )


class Load(_Model):
    id: AssetId
    bus: AssetId
    p_peak_mw: float | None
    p_mean_mw: float | None
    energy_mwh: float | None


class StorageUnit(_Model):
    id: AssetId
    bus: AssetId
    carrier: str | None
    p_nom_mw: NonNegFloat | None
    max_hours: NonNegFloat | None
    efficiency_store: Efficiency | None
    efficiency_dispatch: Efficiency | None


class Store(_Model):
    id: AssetId
    bus: AssetId
    carrier: str | None
    e_nom_mwh: NonNegFloat | None


class Carrier(_Model):
    id: AssetId
    color: str | None
    co2_emissions_t_per_mwh: float | None
    nice_name: str | None


class Summary(_Model):
    counts: dict[str, int]
    capacity_by_carrier_mw: dict[str, float]
    peak_load_mw: float | None = Field(description="Coincident system peak load over snapshots.")
    total_load_mwh: float | None = Field(description="Sum over snapshots of load x weighting.")


COMPONENT_MODELS: dict[str, type[_Model]] = {
    "buses": Bus,
    "lines": Line,
    "transformers": Transformer,
    "links": Link,
    "generators": Generator,
    "loads": Load,
    "storage_units": StorageUnit,
    "stores": Store,
    "carriers": Carrier,
}

_BUS_REFS: dict[str, tuple[str, ...]] = {
    "lines": ("bus0", "bus1"),
    "transformers": ("bus0", "bus1"),
    "links": ("bus0", "bus1"),
    "generators": ("bus",),
    "loads": ("bus",),
    "storage_units": ("bus",),
    "stores": ("bus",),
}


class CanonicalNetwork(_Model):
    schema_version: Literal["canonical-grid/1.0"] = CANONICAL_SCHEMA_VERSION
    network_id: str = Field(pattern=_NETWORK_ID)
    name: str = Field(min_length=1)
    coordinate_kind: Literal["geographic", "schematic"]
    crs: str | None
    snapshots: Snapshots
    buses: list[Bus]
    lines: list[Line]
    transformers: list[Transformer]
    links: list[Link]
    generators: list[Generator]
    loads: list[Load]
    storage_units: list[StorageUnit]
    stores: list[Store]
    carriers: list[Carrier]
    summary: Summary
    field_provenance: dict[str, Provenance]
    assumptions: list[str]

    @model_validator(mode="after")
    def _check_consistency(self) -> CanonicalNetwork:
        errors: list[str] = []
        if self.coordinate_kind == "geographic" and not self.crs:
            errors.append("coordinate_kind 'geographic' requires a crs")
        if self.coordinate_kind == "schematic" and self.crs is not None:
            errors.append("coordinate_kind 'schematic' requires crs = null")

        for comp in COMPONENT_MODELS:
            dupes = [i for i, c in Counter(r.id for r in getattr(self, comp)).items() if c > 1]
            if dupes:
                errors.append(f"duplicate {comp} ids: {sorted(dupes)[:10]}")

        bus_ids = {b.id for b in self.buses}
        for comp, attrs in _BUS_REFS.items():
            for row in getattr(self, comp):
                for attr in attrs:
                    ref = getattr(row, attr)
                    if ref not in bus_ids:
                        errors.append(f"{comp}[{row.id}].{attr} references unknown bus {ref!r}")

        for comp in COMPONENT_MODELS:
            n = len(getattr(self, comp))
            if self.summary.counts.get(comp, n) != n:
                errors.append(
                    f"summary.counts[{comp}]={self.summary.counts[comp]} but {n} rows present"
                )

        for key in self.field_provenance:
            comp, _, fld = key.partition(".")
            model = COMPONENT_MODELS.get(comp)
            if model is None or fld not in model.model_fields:
                errors.append(f"field_provenance key {key!r} is not '<component>.<field>'")

        if errors:
            raise ValueError("; ".join(errors[:50]))
        return self


# --------------------------------------------------------------------------- dataset-manifest/1.0


class Source(_Model):
    url: str = Field(min_length=1)
    version: str = Field(min_length=1)
    publication_date: str | None
    upstream_commit: str | None


class FileEntry(_Model):
    path: str = Field(min_length=1, description="POSIX path relative to the dataset directory.")
    sha256: str = Field(pattern=_SHA256)
    bytes: int = Field(ge=0)

    @field_validator("path")
    @classmethod
    def _relative_posix(cls, v: str) -> str:
        if "\\" in v or v.startswith("/") or re.match(r"^[A-Za-z]:", v) or ".." in v.split("/"):
            raise ValueError("path must be a relative POSIX path inside the dataset directory")
        return v


class License(_Model):
    spdx: str = Field(min_length=1)
    url: str = Field(min_length=1)
    attribution: str = Field(min_length=1)
    redistribution: Literal["permitted", "restricted", "unknown"]


class Coverage(_Model):
    geographic: str
    temporal: str


class Transformation(_Model):
    step: str = Field(min_length=1)
    tool: str = Field(min_length=1)
    version: str = Field(min_length=1)
    description: str = Field(min_length=1)


class DatasetManifest(_Model):
    schema_version: Literal["dataset-manifest/1.0"] = MANIFEST_SCHEMA_VERSION
    network_id: str = Field(pattern=_NETWORK_ID)
    name: str = Field(min_length=1)
    description: str
    source: Source
    retrieved_at: str
    files: list[FileEntry] = Field(min_length=1)
    license: License
    coverage: Coverage
    units: dict[str, str]
    missing_value_policy: str = Field(min_length=1)
    quality_flags: list[str]
    transformations: list[Transformation]
    engines: list[Engine]
    provenance_class: DatasetProvenance

    @field_validator("retrieved_at")
    @classmethod
    def _iso(cls, v: str) -> str:
        datetime.fromisoformat(v)
        return v

    @model_validator(mode="after")
    def _unique_files(self) -> DatasetManifest:
        dupes = [p for p, c in Counter(f.path for f in self.files).items() if c > 1]
        if dupes:
            raise ValueError(f"duplicate file entries: {dupes}")
        return self


# --------------------------------------------------------------------------- network-catalog/1.0


class CatalogEntry(_Model):
    id: str = Field(pattern=_NETWORK_ID)
    path: str = Field(min_length=1, description="Directory relative to data/networks/.")


class NetworkCatalog(_Model):
    schema_version: Literal["network-catalog/1.0"] = CATALOG_SCHEMA_VERSION
    networks: list[CatalogEntry]

    @model_validator(mode="after")
    def _unique(self) -> NetworkCatalog:
        dupes = [i for i, c in Counter(e.id for e in self.networks).items() if c > 1]
        if dupes:
            raise ValueError(f"duplicate catalog ids: {dupes}")
        return self
