"""Both precomputed and API runs resolve money provenance beside network.nc."""

import json
from copy import deepcopy

import jsonschema
import pytest
import stormspec
from conftest import NETWORKS, REPO_ROOT, RESULT_SCHEMA, run_cached, scenario

from gridstorm_pypsa.runner import _cost_basis

DATASETS = ["ac-dc-meshed", "scigrid-de", "pglib-case14-ieee", "pglib-case118-ieee", "pypsa-eur-be"]


@pytest.mark.parametrize("network_id", DATASETS)
def test_adjacent_manifest_resolves_every_dataset_family(network_id):
    spec = stormspec.Scenario.model_validate(scenario(network_id, 1))
    basis = _cost_basis(NETWORKS / network_id, spec)
    manifest = json.loads((NETWORKS / network_id / "manifest.json").read_text(encoding="utf-8"))
    assert {k: v for k, v in basis.items() if k != "penalties"} == manifest["cost_basis"]
    assert basis["penalties"][0]["unit"] == f"{basis['money_unit']}/MWh"
    assert basis["penalties"][0]["value_per_mwh"] == 10000
    if network_id.startswith("pglib-"):
        assert basis["currency"] is None and basis["money_unit"] == "PGLib cost units"
    disabled = stormspec.Scenario.model_validate(
        scenario(network_id, 1, mitigation={"load_shedding": {"enabled": False}})
    )
    assert _cost_basis(NETWORKS / network_id, disabled)["penalties"] == []


def test_real_pglib_result_uses_benchmark_unit_in_assumptions():
    network_id = "pglib-case14-ieee"
    result = run_cached("cost-basis-pglib", scenario(network_id, 1), network_id)
    assert result["cost_basis"]["money_unit"] == "PGLib cost units"
    assert any("VOLL 10000 PGLib cost units/MWh" in text for text in result["assumptions"])
    assert not any(" EUR/MWh" in text for text in result["assumptions"])
    jsonschema.validate(result, json.loads(RESULT_SCHEMA.read_text(encoding="utf-8")))


def test_result_schema_is_backward_compatible_and_rejects_false_currency():
    path = REPO_ROOT / "data/artifacts/pypsa/pglib-case14-ieee-baseline.json"
    result = json.loads(path.read_text(encoding="utf-8"))["payload"]
    schema = json.loads(RESULT_SCHEMA.read_text(encoding="utf-8"))
    legacy = deepcopy(result)
    del legacy["cost_basis"]
    jsonschema.validate(legacy, schema)
    result["cost_basis"]["currency"] = "EUR"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(result, schema)


def test_missing_manifest_never_infers_eur(tmp_path):
    spec = stormspec.Scenario.model_validate(scenario("custom-network", 1))
    basis = _cost_basis(tmp_path, spec)
    assert basis["currency"] is None
    assert basis["money_unit"] == "cost units (basis unknown)"
