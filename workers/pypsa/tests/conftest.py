from __future__ import annotations

import copy
import logging
import os
from pathlib import Path

import pytest

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
logging.getLogger("linopy").setLevel(logging.WARNING)
logging.getLogger("pypsa").setLevel(logging.WARNING)

REPO_ROOT = Path(__file__).resolve().parents[3]
NETWORKS = REPO_ROOT / "data" / "networks"
RESULT_SCHEMA = REPO_ROOT / "packages" / "stormspec" / "schema" / "gridstorm-result-1.0.schema.json"


def network_dir(network_id: str) -> Path:
    d = NETWORKS / network_id
    if not (d / "network.nc").is_file():
        pytest.skip(f"{d / 'network.nc'} missing (run the network-import pipeline first)")
    return d


def scenario(network_id: str, snapshots: int, events=(), sid="test-run", **overrides) -> dict:
    s = {
        "schema_version": "stormspec/1.0",
        "id": sid,
        "name": "test",
        "dataset": {"network_id": network_id, "sha256": None},
        "horizon": {"start": 0, "snapshots": snapshots},
        "events": list(events),
        "execution": {"engine": "pypsa", "formulation": "lopf", "solver": "highs"},
    }
    for k, v in overrides.items():
        s[k] = copy.deepcopy(v)
    return s


_CACHE: dict[str, dict] = {}


def run_cached(key: str, spec: dict, network_id: str) -> dict:
    """Run once per test session (solves are the expensive part)."""
    from gridstorm_pypsa import run_scenario

    if key not in _CACHE:
        _CACHE[key] = run_scenario(spec, network_dir(network_id))
    return _CACHE[key]
