from __future__ import annotations

import copy

import pytest

# Minimal canonical-grid/1.0 document (synthetic test fixture, not a real network).
NETWORK = {
    "schema_version": "canonical-grid/1.0",
    "network_id": "test-net",
    "name": "Synthetic 3-bus test network",
    "coordinate_kind": "schematic",
    "crs": None,
    "snapshots": {
        "count": 24,
        "start": "2020-01-01T00:00:00",
        "end": "2020-01-01T23:00:00",
        "resolution_h": 1.0,
    },
    "buses": [{"id": b} for b in ("b1", "b2", "b3")],
    "lines": [{"id": "l12", "bus0": "b1", "bus1": "b2"}, {"id": "l23", "bus0": "b2", "bus1": "b3"}],
    "transformers": [{"id": "t13", "bus0": "b1", "bus1": "b3"}],
    "links": [{"id": "dc1", "bus0": "b1", "bus1": "b3"}],
    "generators": [
        {"id": "g-gas", "bus": "b1", "carrier": "gas", "is_variable": False},
        {"id": "g-wind", "bus": "b2", "carrier": "wind", "is_variable": True},
    ],
    "loads": [{"id": "ld3", "bus": "b3"}],
    "storage_units": [{"id": "phs1", "bus": "b2", "carrier": "PHS"}],
    "stores": [],
    "carriers": [{"id": c} for c in ("gas", "wind", "PHS")],
}


def base_scenario(**overrides) -> dict:
    s = {
        "schema_version": "stormspec/1.0",
        "id": "test-scenario",
        "name": "Test",
        "dataset": {"network_id": "test-net", "sha256": None},
        "horizon": {"start": 0, "snapshots": 24},
        "events": [],
        "execution": {"engine": "pypsa", "formulation": "lopf"},
    }
    s.update(overrides)
    return s


@pytest.fixture
def network() -> dict:
    return copy.deepcopy(NETWORK)
