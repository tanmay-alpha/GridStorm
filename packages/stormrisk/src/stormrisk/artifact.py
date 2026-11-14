"""Artifact envelope (contract §5, ``gridstorm-artifact/1.0``) and ``index.json`` maintenance."""

from __future__ import annotations

import json
import math
import platform
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from stormspec import payload_sha256

ARTIFACT_SCHEMA_VERSION = "gridstorm-artifact/1.0"
ARTIFACT_KIND = "risk"
ARTIFACT_ENGINE = "stormrisk"


def round_floats(obj: Any, sig: int = 6) -> Any:
    """Round every float to ``sig`` significant digits (keeps artifacts small and stable)."""
    if isinstance(obj, float):
        if obj == 0.0 or not math.isfinite(obj):
            return obj
        return float(f"{obj:.{sig}g}")
    if isinstance(obj, dict):
        return {k: round_floats(v, sig) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [round_floats(v, sig) for v in obj]
    return obj


def build_artifact(
    payload: dict[str, Any],
    *,
    artifact_id: str,
    network_id: str,
    engine_version: str | None,
    command: str,
    inputs: list[dict[str, str]],
) -> dict[str, Any]:
    payload = round_floats(payload)
    return {
        "artifact": {
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "artifact_id": artifact_id,
            "kind": ARTIFACT_KIND,
            "engine": ARTIFACT_ENGINE,
            "engine_version": engine_version,
            "network_id": network_id,
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "command": command,
            "inputs": inputs,
            "platform": platform.platform(),
            "execution_mode": "precomputed",
            "payload_sha256": payload_sha256(payload),
        },
        "payload": payload,
    }


def write_artifact(artifact: dict[str, Any], out_dir: Path, *, title: str) -> Path:
    """Write ``<artifact_id>.json`` and upsert its entry in ``index.json``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    head = artifact["artifact"]
    path = out_dir / f"{head['artifact_id']}.json"
    path.write_text(json.dumps(artifact, indent=1, ensure_ascii=False, allow_nan=False) + "\n",
                    encoding="utf-8")
    index_path = out_dir / "index.json"
    entries: list[dict[str, Any]] = []
    if index_path.exists():
        entries = json.loads(index_path.read_text(encoding="utf-8")).get("artifacts", [])
    entries = [e for e in entries if e.get("artifact_id") != head["artifact_id"]]
    entries.append({"artifact_id": head["artifact_id"], "kind": head["kind"],
                    "network_id": head["network_id"], "title": title,
                    "path": path.name, "payload_sha256": head["payload_sha256"]})
    entries.sort(key=lambda e: e["artifact_id"])
    index_path.write_text(
        json.dumps({"schema_version": "gridstorm-artifact-index/1.0", "engine": ARTIFACT_ENGINE,
                    "artifacts": entries}, indent=1) + "\n",
        encoding="utf-8",
    )
    return path
