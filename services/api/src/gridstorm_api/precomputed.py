"""Read-only access to precomputed engine artifacts in ``<data>/artifacts/<engine>/`` (contract §5).

Each engine directory holds ``index.json`` (list of ``{artifact_id, kind, network_id, title}``,
either a bare list or ``{"artifacts": [...]}``) and ``<artifact_id>.json`` files with an
``artifact`` header and a ``payload``. Payload integrity (``payload_sha256`` = sha256 of canonical
JSON of ``payload``) is verified on first read and reported, never assumed.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from pathlib import Path
from typing import Any, get_args

from .errors import NotFound
from .schemas import ArtifactKind

log = logging.getLogger("gridstorm_api.precomputed")

_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
ARTIFACT_KINDS: tuple[str, ...] = get_args(ArtifactKind)


def canonical_sha256(obj: Any) -> str:
    data = json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


class PrecomputedArtifacts:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._lock = threading.Lock()
        self._index: list[dict[str, Any]] | None = None
        self._verified: dict[tuple[str, str], bool | None] = {}
        self._by_hash: dict[str, tuple[str, str]] | None = None

    def reload(self) -> None:
        with self._lock:
            self._index = None
            self._by_hash = None
            self._verified.clear()

    def index(self) -> list[dict[str, Any]]:
        with self._lock:
            if self._index is None:
                self._index = self._load_index()
            return self._index

    def _load_index(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        if not self.root.is_dir():
            return items
        for engine_dir in sorted(p for p in self.root.iterdir() if p.is_dir()):
            index_path = engine_dir / "index.json"
            if not index_path.is_file():
                continue
            try:
                raw = json.loads(index_path.read_text(encoding="utf-8"))
            except ValueError as exc:
                log.error("invalid artifact index %s: %s", index_path, exc)
                continue
            entries = raw.get("artifacts", []) if isinstance(raw, dict) else raw
            for entry in entries or []:
                if not isinstance(entry, dict) or not _SAFE.match(str(entry.get("artifact_id"))):
                    continue
                if entry.get("kind") not in ARTIFACT_KINDS:
                    log.error(
                        "skipping %s/%s: kind %r is not a contract §5 artifact kind %s",
                        engine_dir.name,
                        entry["artifact_id"],
                        entry.get("kind"),
                        ARTIFACT_KINDS,
                    )
                    continue
                artifact_id = str(entry["artifact_id"])
                path = engine_dir / f"{artifact_id}.json"
                items.append(
                    {
                        **entry,
                        "engine": engine_dir.name,
                        "artifact_id": artifact_id,
                        "kind": entry.get("kind"),
                        "network_id": entry.get("network_id"),
                        "title": entry.get("title"),
                        "bytes": path.stat().st_size if path.is_file() else None,
                        "available": path.is_file(),
                    }
                )
        return items

    def _path(self, engine: str, artifact_id: str) -> Path:
        if not (_SAFE.match(engine) and _SAFE.match(artifact_id)):
            raise NotFound("unknown artifact", code="artifact_not_found")
        listed = any(
            i["engine"] == engine and i["artifact_id"] == artifact_id and i["available"]
            for i in self.index()
        )
        path = self.root / engine / f"{artifact_id}.json"
        if not listed or not path.is_file():
            raise NotFound(
                f"artifact {engine}/{artifact_id} not found",
                code="artifact_not_found",
                details={"engine": engine, "artifact_id": artifact_id},
            )
        return path

    def load(self, engine: str, artifact_id: str) -> tuple[bytes, dict[str, Any], bool | None]:
        """Return (raw bytes, parsed document, payload_sha256 verified?)."""
        path = self._path(engine, artifact_id)
        raw = path.read_bytes()
        doc = json.loads(raw)
        key = (engine, artifact_id)
        if key not in self._verified:
            declared = (doc.get("artifact") or {}).get("payload_sha256")
            if declared is None or "payload" not in doc:
                self._verified[key] = None
            else:
                self._verified[key] = canonical_sha256(doc["payload"]) == declared
        return raw, doc, self._verified[key]

    def find_simulation(self, scenario_hash: str) -> tuple[str, str] | None:
        """Locate a precomputed ``kind=simulation`` artifact whose result matches the hash."""
        with self._lock:
            by_hash = self._by_hash
        if by_hash is None:
            by_hash = {}
            for item in self.index():
                if item["kind"] != "simulation" or not item["available"]:
                    continue
                try:
                    _, doc, _ = self.load(item["engine"], item["artifact_id"])
                except (OSError, ValueError, NotFound):
                    continue
                h = (doc.get("payload") or {}).get("scenario_hash")
                if isinstance(h, str):
                    by_hash.setdefault(h, (item["engine"], item["artifact_id"]))
            with self._lock:
                self._by_hash = by_hash
        return by_hash.get(scenario_hash)
