from __future__ import annotations

import pytest
from stormspec import Scenario


@pytest.fixture
def toy_network() -> dict:
    """Minimal canonical-grid/1.0-shaped dict (only the fields validation/sampling read)."""
    return {
        "schema_version": "canonical-grid/1.0",
        "network_id": "toy-net",
        "snapshots": {"count": 4},
        "buses": [{"id": "b1"}, {"id": "b2"}],
        "lines": [
            {"id": "L1", "bus0": "b1", "bus1": "b2", "carrier": "AC"},
            {"id": "L2", "bus0": "b1", "bus1": "b2", "carrier": "AC"},
        ],
        "transformers": [],
        "links": [],
        "generators": [
            {"id": "G1", "bus": "b1", "carrier": "gas", "is_variable": False},
            {"id": "G2", "bus": "b1", "carrier": "wind", "is_variable": True},
            {"id": "G3", "bus": "b2", "carrier": "oil", "is_variable": False},
        ],
        "loads": [{"id": "load-b2", "bus": "b2"}],
        "storage_units": [],
        "stores": [],
        "carriers": [{"id": "AC"}, {"id": "gas"}, {"id": "wind"}, {"id": "oil"}],
    }


@pytest.fixture
def base_scenario() -> Scenario:
    return Scenario.model_validate(
        {
            "id": "toy-base",
            "name": "Toy base",
            "dataset": {"network_id": "toy-net"},
            "horizon": {"start": 0, "snapshots": 4},
            "events": [],
            "execution": {"engine": "pypsa", "formulation": "lopf", "solver": "highs"},
        }
    )
