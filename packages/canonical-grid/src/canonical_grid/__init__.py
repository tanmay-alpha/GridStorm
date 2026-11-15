"""GridStorm canonical network data models (canonical-grid/1.0, dataset-manifest/1.0).

Depends only on pydantic so every GridStorm environment can import it.
"""

from __future__ import annotations

import json
from pathlib import Path

from canonical_grid.models import (
    CANONICAL_SCHEMA_VERSION,
    CATALOG_SCHEMA_VERSION,
    COMPONENT_MODELS,
    MANIFEST_SCHEMA_VERSION,
    Bus,
    CanonicalNetwork,
    Carrier,
    CatalogEntry,
    CostBasis,
    Coverage,
    DatasetManifest,
    FileEntry,
    Generator,
    License,
    Line,
    Link,
    Load,
    NetworkCatalog,
    Provenance,
    Snapshots,
    Source,
    StorageUnit,
    Store,
    Summary,
    Transformation,
    Transformer,
)

__version__ = "1.0.0"


def load_canonical(path: str | Path) -> CanonicalNetwork:
    """Load and validate a ``canonical.json`` file."""
    return CanonicalNetwork.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


def load_manifest(path: str | Path) -> DatasetManifest:
    """Load and validate a ``manifest.json`` file."""
    return DatasetManifest.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


def load_catalog(path: str | Path) -> NetworkCatalog:
    """Load and validate ``data/networks/catalog.json``."""
    return NetworkCatalog.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


def dump_json(model: CanonicalNetwork | DatasetManifest | NetworkCatalog) -> str:
    """Deterministic JSON serialisation (2-space indent, key order = model field order, trailing
    newline) used for every committed file."""
    return json.dumps(model.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"


__all__ = [
    "CANONICAL_SCHEMA_VERSION",
    "CATALOG_SCHEMA_VERSION",
    "COMPONENT_MODELS",
    "MANIFEST_SCHEMA_VERSION",
    "Bus",
    "CanonicalNetwork",
    "Carrier",
    "CatalogEntry",
    "Coverage",
    "CostBasis",
    "DatasetManifest",
    "FileEntry",
    "Generator",
    "License",
    "Line",
    "Link",
    "Load",
    "NetworkCatalog",
    "Provenance",
    "Snapshots",
    "Source",
    "StorageUnit",
    "Store",
    "Summary",
    "Transformation",
    "Transformer",
    "dump_json",
    "load_canonical",
    "load_catalog",
    "load_manifest",
]
