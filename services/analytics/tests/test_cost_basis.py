"""Cost tables use supplied dataset units, not a guessed EUR currency."""

import json
from pathlib import Path

import pypsa
import pytest

import gridstorm_analytics as ga

NETWORKS = Path(__file__).resolve().parents[3] / "data/networks"
DATASETS = ["ac-dc-meshed", "scigrid-de", "pglib-case14-ieee", "pglib-case118-ieee", "pypsa-eur-be"]


@pytest.mark.parametrize("network_id", DATASETS)
def test_costs_use_each_manifest_basis(network_id):
    directory = NETWORKS / network_id
    basis = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))["cost_basis"]
    network = pypsa.Network(str(directory / "network.nc"))
    result = ga.compute("costs", network, cost_basis=basis)
    assert all(
        unit == basis["money_unit"]
        for key, unit in result["units"].items()
        if key != "objective_weighted_hours_h"
    )
    assert f"Declared money unit: {basis['money_unit']}." in result["assumptions"]
    assert not any("assumes EUR" in text for text in result["assumptions"])
    committed = json.loads((directory / "analytics/costs.json").read_text(encoding="utf-8"))
    assert committed == result


def test_missing_basis_is_not_assumed_eur(ac_dc):
    result = ga.compute("costs", ac_dc)
    assert result["units"]["totals.*"] == "cost units (basis unknown)"
