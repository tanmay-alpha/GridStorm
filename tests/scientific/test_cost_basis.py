"""Money provenance is part of scientific interpretation, never a currency conversion."""

import json

import pytest

from paths import ARTIFACTS, NETWORKS, artifact_paths

DATASETS = ["ac-dc-meshed", "scigrid-de", "pglib-case14-ieee", "pglib-case118-ieee", "pypsa-eur-be"]


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("network_id", DATASETS)
def test_every_dataset_declares_a_coherent_cost_basis(network_id):
    manifest = load(NETWORKS / network_id / "manifest.json")
    basis = manifest["cost_basis"]
    assert basis["schema_version"] == "gridstorm-cost-basis/1.0"
    assert basis["price_unit"] == f"{basis['money_unit']}/MWh"
    assert basis["comparability_key"] and basis["provenance"] and basis["assumptions"]
    if network_id.startswith("pglib-"):
        assert basis["kind"] == "benchmark_nominal"
        assert basis["money_unit"] == "PGLib cost units"
        assert basis["currency"] is None and basis["currency_year"] is None
    elif network_id == "pypsa-eur-be":
        assert (basis["kind"], basis["currency"], basis["currency_year"]) == (
            "currency_verified",
            "EUR",
            2025,
        )
    else:
        assert basis["kind"] == "illustrative" and basis["currency"] is None


@pytest.mark.parametrize("path", artifact_paths(), ids=lambda p: p.stem)
def test_results_embed_dataset_basis_and_penalty_units(path):
    result = load(path)["payload"]
    basis = result["cost_basis"]
    declared = load(NETWORKS / result["network_id"] / "manifest.json")["cost_basis"]
    assert {k: v for k, v in basis.items() if k != "penalties"} == declared
    for penalty in basis["penalties"]:
        assert penalty["term"] == "load_shedding" and penalty["nature"] == "penalty"
        assert penalty["unit"] == basis["price_unit"]
        assert result["metrics"]["load_shedding_cost_eur"] == pytest.approx(
            result["metrics"]["unserved_energy_mwh"] * penalty["value_per_mwh"],
            rel=1e-7,
            abs=1e-5,
        )
    if result["network_id"].startswith("pglib-"):
        assert not any(" EUR/MWh" in text for text in result["assumptions"] + result["warnings"])


def test_pglib_outage_objective_is_benchmark_generation_plus_penalty():
    result = load(ARTIFACTS / "pglib-case14-ieee-gen-1-outage.json")["payload"]
    metrics = result["metrics"]
    assert metrics["unserved_energy_mwh"] == 200
    assert metrics["load_shedding_cost_eur"] == 200 * 10000
    assert metrics["generation_cost_eur"] == pytest.approx(1372.900146, abs=1e-6)
    assert result["solver"]["objective_eur"] == pytest.approx(2001372.900146, abs=1e-6)
