"""``gridstorm-artifact/1.0`` envelope (contracts.md §5) for advisor payloads and the
per-engine ``index.json``."""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandapower as pp

from gridstorm_advisor import __version__

ARTIFACT_SCHEMA = "gridstorm-artifact/1.0"
KIND = "advisor"
ENGINE = "advisor"


def canonical_json(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def payload_sha256(payload: dict) -> str:
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def envelope(
    artifact_id: str, network_id: str, payload: dict, *, command: str, inputs: list[dict]
) -> dict:
    """Header per contract §5. ``engine`` is the artifact directory name (``advisor``); the
    power-flow engine that verified every number is recorded in ``power_flow_engine``."""
    return {
        "artifact": {
            "schema_version": ARTIFACT_SCHEMA,
            "artifact_id": artifact_id,
            "kind": KIND,
            "engine": ENGINE,
            "engine_version": __version__,
            "power_flow_engine": {"name": "pandapower", "version": pp.__version__},
            "network_id": network_id,
            "created_at": datetime.now(UTC)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "command": command,
            "inputs": inputs,
            "platform": f"{platform.system()}-{platform.release()} Python {sys.version.split()[0]}",
            "execution_mode": "precomputed",
            "payload_sha256": payload_sha256(payload),
        },
        "payload": payload,
    }


def write_artifact(out_dir: Path, art: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{art['artifact']['artifact_id']}.json"
    path.write_text(
        json.dumps(art, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def write_index(out_dir: Path) -> Path:
    """Rebuild ``index.json`` from every artifact file in ``out_dir`` (sorted by id)."""
    items = []
    for path in sorted(out_dir.glob("*.json")):
        if path.name == "index.json":
            continue
        art = json.loads(path.read_text(encoding="utf-8"))
        head = art["artifact"]
        payload = art["payload"]
        items.append(
            {
                "artifact_id": head["artifact_id"],
                "kind": head["kind"],
                "network_id": head["network_id"],
                "title": payload.get("title")
                or payload["crisis"].get("title")
                or head["artifact_id"],
                "outcome": payload.get("outcome"),
                "payload_sha256": head["payload_sha256"],
            }
        )
    index = {
        "schema_version": "gridstorm-artifact-index/1.0",
        "engine": "advisor",
        "artifacts": items,
    }
    path = out_dir / "index.json"
    path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path
