"""Network catalog: ``<data>/networks/catalog.json`` + per-network canonical/manifest (cached)."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import NotFound, ServiceUnavailable

log = logging.getLogger("gridstorm_api.catalog")

ASSET_TYPES = (
    "buses",
    "lines",
    "transformers",
    "links",
    "generators",
    "loads",
    "storage_units",
    "stores",
    "carriers",
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class NetworkEntry:
    id: str
    directory: Path
    canonical: dict[str, Any]
    manifest: dict[str, Any]
    canonical_sha256: str
    manifest_sha256: str
    _asset_index: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict, repr=False)

    @property
    def network_nc(self) -> Path:
        return self.directory / "network.nc"

    @property
    def network_sha256(self) -> str | None:
        for f in self.manifest.get("files") or []:
            if f.get("path") == "network.nc":
                return f.get("sha256")
        return None

    @property
    def coordinate_kind(self) -> str:
        return self.canonical.get("coordinate_kind") or "schematic"

    @property
    def name(self) -> str:
        return self.canonical.get("name") or self.manifest.get("name") or self.id

    def asset_ids(self, asset_type: str) -> dict[str, dict[str, Any]]:
        if asset_type not in self._asset_index:
            rows = self.canonical.get(asset_type) or []
            self._asset_index[asset_type] = {str(r.get("id")): r for r in rows}
        return self._asset_index[asset_type]

    def summary(self) -> dict[str, Any]:
        c, m = self.canonical, self.manifest
        summary = c.get("summary") or {}
        lic = m.get("license") or {}
        return {
            "id": self.id,
            "name": self.name,
            "description": m.get("description"),
            "coordinate_kind": self.coordinate_kind,
            "crs": c.get("crs"),
            "snapshots": c.get("snapshots"),
            "counts": summary.get("counts") or {t: len(c.get(t) or []) for t in ASSET_TYPES},
            "capacity_by_carrier_mw": summary.get("capacity_by_carrier_mw") or {},
            "peak_load_mw": summary.get("peak_load_mw"),
            "total_load_mwh": summary.get("total_load_mwh"),
            "license": {
                "spdx": lic.get("spdx"),
                "url": lic.get("url"),
                "attribution": lic.get("attribution"),
                "redistribution": lic.get("redistribution"),
            },
            "provenance_class": m.get("provenance_class"),
            "engines": m.get("engines") or [],
            "network_sha256": self.network_sha256,
            "has_network_file": self.network_nc.is_file(),
            "source": m.get("source"),
        }


class NetworkCatalog:
    """Read-only, cached view of ``data/networks``. Thread-safe lazy (re)load."""

    def __init__(self, networks_dir: Path) -> None:
        self.networks_dir = networks_dir
        self._lock = threading.Lock()
        self._entries: dict[str, NetworkEntry] | None = None
        self._errors: dict[str, str] = {}

    @property
    def catalog_path(self) -> Path:
        return self.networks_dir / "catalog.json"

    def _resolve_dir(self, net_id: str, path: str | None) -> Path:
        """``path`` may be relative to the networks dir or to the repo root (``data/networks/x``)."""
        candidates: list[Path] = []
        if path:
            p = Path(path)
            if p.is_absolute():
                candidates.append(p)
            else:
                candidates += [self.networks_dir / p, self.networks_dir.parent.parent / p]
        candidates.append(self.networks_dir / net_id)
        for cand in candidates:
            if (cand / "canonical.json").is_file():
                return cand.resolve()
        return (self.networks_dir / net_id).resolve()

    def _load(self) -> dict[str, NetworkEntry]:
        entries: dict[str, NetworkEntry] = {}
        errors: dict[str, str] = {}
        if not self.catalog_path.is_file():
            log.warning("network catalog missing: %s", self.catalog_path)
            self._errors = {"catalog": f"missing {self.catalog_path.name}"}
            return entries
        catalog = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        for item in catalog.get("networks", []):
            net_id = str(item.get("id"))
            directory = self._resolve_dir(net_id, item.get("path"))
            try:
                canonical_path = directory / "canonical.json"
                manifest_path = directory / "manifest.json"
                canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                entries[net_id] = NetworkEntry(
                    id=net_id,
                    directory=directory,
                    canonical=canonical,
                    manifest=manifest,
                    canonical_sha256=sha256_file(canonical_path),
                    manifest_sha256=sha256_file(manifest_path),
                )
            except (OSError, ValueError) as exc:
                log.error("network %s unusable: %s", net_id, exc)
                errors[net_id] = f"{type(exc).__name__}: {exc}"
        self._errors = errors
        return entries

    def entries(self) -> dict[str, NetworkEntry]:
        with self._lock:
            if self._entries is None:
                self._entries = self._load()
            return self._entries

    def reload(self) -> None:
        with self._lock:
            self._entries = None

    @property
    def errors(self) -> dict[str, str]:
        self.entries()
        return dict(self._errors)

    def get(self, net_id: str) -> NetworkEntry:
        entries = self.entries()
        if net_id not in entries:
            if net_id in self._errors:
                raise ServiceUnavailable(
                    f"network {net_id!r} is listed but its files could not be loaded",
                    code="network_unavailable",
                    details={"network_id": net_id},
                )
            raise NotFound(
                f"unknown network {net_id!r}",
                code="network_not_found",
                details={"network_id": net_id},
            )
        return entries[net_id]

    def ids(self) -> list[str]:
        return sorted(self.entries())
