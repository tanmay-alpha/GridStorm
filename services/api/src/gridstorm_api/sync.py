"""Startup synchronisation of file-based reference data into the database.

* ``sync_catalog``: one ``network_datasets`` row per catalog entry, a ``network_versions`` row per
  distinct (canonical.json sha256, manifest.json sha256) with its ``dataset_sources`` row, and an
  ``ingestion_runs`` row whenever a new version is registered (or a catalog entry fails to load).
* ``sync_presets``: StormSpec presets (``packages/stormspec/presets``) → ``scenario_definitions``
  (``is_preset = true``, public). Presets that fail validation are skipped and logged — never
  served as runnable.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .catalog import NetworkCatalog, NetworkEntry
from .db.models import (
    DatasetSource,
    IngestionRun,
    NetworkDataset,
    NetworkVersion,
    ScenarioDefinition,
    utcnow,
)
from .validation import validate_spec

log = logging.getLogger("gridstorm_api.sync")

TOOL = "gridstorm_api.catalog_sync"


def _dataset_values(entry: NetworkEntry) -> dict[str, Any]:
    m = entry.manifest
    lic = m.get("license") or {}
    return {
        "name": entry.name,
        "description": m.get("description"),
        "coordinate_kind": entry.coordinate_kind,
        "provenance_class": m.get("provenance_class"),
        "license_spdx": lic.get("spdx"),
        "redistribution": lic.get("redistribution"),
    }


def current_version(session: Session, entry: NetworkEntry) -> NetworkVersion | None:
    return session.scalar(
        select(NetworkVersion).where(
            NetworkVersion.network_id == entry.id,
            NetworkVersion.canonical_sha256 == entry.canonical_sha256,
            NetworkVersion.manifest_sha256 == entry.manifest_sha256,
        )
    )


def sync_catalog(session: Session, catalog: NetworkCatalog) -> dict[str, uuid.UUID]:
    """Upsert datasets/versions. Returns ``{network_id: current network_versions.id}``."""
    versions: dict[str, uuid.UUID] = {}
    for net_id, entry in catalog.entries().items():
        started = utcnow()
        ds = session.get(NetworkDataset, net_id)
        values = _dataset_values(entry)
        if ds is None:
            session.add(NetworkDataset(id=net_id, is_public=True, **values))
        else:
            for k, v in values.items():
                if getattr(ds, k) != v:
                    setattr(ds, k, v)
        session.flush()
        version = current_version(session, entry)
        if version is None:
            version = NetworkVersion(
                network_id=net_id,
                network_sha256=entry.network_sha256,
                canonical_sha256=entry.canonical_sha256,
                manifest_sha256=entry.manifest_sha256,
                manifest=entry.manifest,
                retrieved_at=entry.manifest.get("retrieved_at"),
            )
            session.add(version)
            session.flush()
            src = entry.manifest.get("source") or {}
            lic = entry.manifest.get("license") or {}
            session.add(
                DatasetSource(
                    network_id=net_id,
                    network_version_id=version.id,
                    url=src.get("url"),
                    version=src.get("version"),
                    publication_date=src.get("publication_date"),
                    upstream_commit=src.get("upstream_commit"),
                    license_spdx=lic.get("spdx"),
                    license_url=lic.get("url"),
                    attribution=lic.get("attribution"),
                    redistribution=lic.get("redistribution"),
                )
            )
            session.add(
                IngestionRun(
                    network_id=net_id,
                    network_version_id=version.id,
                    tool=TOOL,
                    status="succeeded",
                    started_at=started,
                    finished_at=utcnow(),
                    details={
                        "directory": entry.directory.name,
                        "canonical_sha256": entry.canonical_sha256,
                        "manifest_sha256": entry.manifest_sha256,
                        "network_sha256": entry.network_sha256,
                    },
                )
            )
        versions[net_id] = version.id
    for net_id, error in catalog.errors.items():
        if net_id == "catalog" or session.get(NetworkDataset, net_id) is None:
            log.error("catalog entry %s not ingested: %s", net_id, error)
            continue
        session.add(
            IngestionRun(
                network_id=net_id,
                tool=TOOL,
                status="failed",
                started_at=utcnow(),
                finished_at=utcnow(),
                details={"error": error},
            )
        )
    session.commit()
    return versions


def load_preset_specs(presets_dir: Any) -> list[tuple[str, dict[str, Any]]]:
    from stormspec.io import load_scenario_dict, preset_paths

    out: list[tuple[str, dict[str, Any]]] = []
    if presets_dir is None or not presets_dir.is_dir():
        log.warning("preset directory missing: %s", presets_dir)
        return out
    for path in preset_paths(presets_dir):
        try:
            out.append((path.name, load_scenario_dict(path)))
        except (OSError, ValueError, ImportError) as exc:
            log.error("preset %s unreadable: %s", path.name, exc)
    return out


def sync_presets(session: Session, catalog: NetworkCatalog, presets_dir: Any) -> list[str]:
    """Upsert valid presets. Returns the ids of presets that were rejected."""
    rejected: list[str] = []
    seen: set[str] = set()
    for filename, spec in load_preset_specs(presets_dir):
        outcome = validate_spec(spec, catalog, for_execution=False)
        if not outcome.valid or outcome.scenario is None:
            log.error("preset %s rejected: %s", filename, outcome.errors)
            rejected.append(filename)
            continue
        sc = outcome.scenario
        if sc.id in seen:
            log.error("duplicate preset id %s in %s", sc.id, filename)
            rejected.append(filename)
            continue
        seen.add(sc.id)
        normalized = sc.model_dump(mode="json")
        row = session.get(ScenarioDefinition, sc.id)
        if row is None:
            session.add(
                ScenarioDefinition(
                    id=sc.id,
                    spec_id=sc.id,
                    name=sc.name,
                    network_id=sc.dataset.network_id,
                    scenario_hash=outcome.scenario_hash,
                    spec=normalized,
                    is_preset=True,
                    visibility="public",
                    owner_id=None,
                )
            )
        elif not row.is_preset:
            log.error("preset id %s collides with a saved scenario; skipped", sc.id)
            rejected.append(filename)
        elif row.scenario_hash != outcome.scenario_hash or row.spec != normalized:
            row.name, row.spec, row.scenario_hash = sc.name, normalized, outcome.scenario_hash
            row.network_id = sc.dataset.network_id
    session.flush()
    for stale in session.scalars(
        select(ScenarioDefinition).where(ScenarioDefinition.is_preset.is_(True))
    ).all():
        if stale.id not in seen:
            log.warning("preset %s no longer present/valid; removed from catalog", stale.id)
            session.delete(stale)
    session.commit()
    return rejected
