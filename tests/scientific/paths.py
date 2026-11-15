"""Repository paths used by the scientific harness."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = REPO_ROOT / "data" / "artifacts" / "pypsa"
NETWORKS = REPO_ROOT / "data" / "networks"
PRESETS = REPO_ROOT / "packages" / "stormspec" / "presets"


def artifact_paths() -> list[Path]:
    return sorted(p for p in ARTIFACTS.glob("*.json") if p.name != "index.json")
