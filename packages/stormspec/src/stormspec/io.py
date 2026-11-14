"""Scenario loading helpers (YAML via optional ``pyyaml``; JSON via stdlib)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Scenario

#: Preset directory in a source checkout (``packages/stormspec/presets``).
PRESETS_DIR = Path(__file__).resolve().parents[2] / "presets"


def _load_yaml(text: str) -> Any:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ImportError(
            "Loading YAML scenarios requires PyYAML: install `stormspec[yaml]`"
        ) from exc
    return yaml.safe_load(text)


def load_scenario_dict(path: str | Path) -> dict:
    """Read a ``.yaml``/``.yml``/``.json`` file into a plain dict (not validated)."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    suffix = p.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        data = _load_yaml(text)
    elif suffix == ".json":
        data = json.loads(text)
    else:
        raise ValueError(f"unsupported scenario file extension {suffix!r} (use .yaml/.yml/.json)")
    if not isinstance(data, dict):
        raise ValueError(f"{p}: scenario document must be a mapping")
    return data


def load_scenario(path: str | Path) -> Scenario:
    """Load and structurally validate a scenario file."""
    return Scenario.model_validate(load_scenario_dict(path))


def preset_paths(directory: str | Path | None = None) -> list[Path]:
    d = Path(directory) if directory is not None else PRESETS_DIR
    return sorted([*d.glob("*.yaml"), *d.glob("*.yml"), *d.glob("*.json")])


def load_presets(directory: str | Path | None = None) -> list[Scenario]:
    """Load every preset scenario (sorted by file name)."""
    return [load_scenario(p) for p in preset_paths(directory)]
