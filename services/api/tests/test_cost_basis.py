"""Dataset money units, incompatible comparisons, and legacy result fallback."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from conftest import NETWORK_ID, run_job, scenario
from gridstorm_api.catalog import NetworkCatalog
from gridstorm_api.comparisons import compare_results, unit_of
from gridstorm_api.config import REPO_ROOT
from gridstorm_api.jobs.results import load_result

CATALOG = NetworkCatalog(REPO_ROOT / "data" / "networks")
NETWORK_IDS = CATALOG.ids()


@pytest.mark.parametrize("network_id", NETWORK_IDS)
def test_network_summary_exposes_declared_money_basis(network_id):
    entry = CATALOG.get(network_id)
    assert entry.summary()["cost_basis"] == entry.manifest["cost_basis"]
    basis = entry.summary()["cost_basis"]
    assert unit_of("total_system_cost_eur", basis) == basis["money_unit"]
    assert unit_of("mean_marginal_price_eur_per_mwh", basis) == basis["price_unit"]
    if network_id.startswith("pglib-"):
        assert unit_of("generation_cost_eur", basis) == "PGLib cost units"


def test_no_currency_is_inferred_from_legacy_field_names():
    assert unit_of("total_system_cost_eur") == "cost units (basis unknown)"
    assert unit_of("mean_marginal_price_eur_per_mwh") == "cost units (basis unknown)/MWh"


def test_different_comparability_keys_withhold_all_monetary_deltas():
    basis = CATALOG.get("pglib-case14-ieee").manifest["cost_basis"]
    other = {**basis, "comparability_key": "incompatible-source"}
    baseline = {
        "outcome": "feasible",
        "cost_basis": basis,
        "metrics": {
            "total_system_cost_eur": 100,
            "generation_cost_eur": 90,
            "load_shedding_cost_eur": 10,
            "mean_marginal_price_eur_per_mwh": 2,
            "total_load_mwh": 50,
        },
    }
    scenario_result = deepcopy(baseline)
    scenario_result["cost_basis"] = other
    scenario_result["metrics"] = {k: v * 2 for k, v in baseline["metrics"].items()}
    report = compare_results(baseline, scenario_result)
    assert report["costs_comparable"] is False
    for row in report["metrics"]:
        if row["metric"] == "total_load_mwh":
            assert row["delta"] == 50 and row["unit"] == "MWh"
        else:
            assert row["delta"] is None and row["delta_pct"] is None
            assert row["unit"] is None
    assert report["warnings"]
    scenario_result["cost_basis"] = basis
    comparable = compare_results(baseline, scenario_result)
    assert comparable["costs_comparable"] is True
    assert (
        next(r for r in comparable["metrics"] if r["metric"] == "total_system_cost_eur")["delta"]
        == 100
    )


@pytest.mark.parametrize("network_id", NETWORK_IDS)
def test_legacy_result_falls_back_to_catalog_without_mutating_stored_bytes(monkeypatch, network_id):
    from gridstorm_api.jobs import results

    stored = {
        "schema_version": "gridstorm-result/1.0",
        "network_id": network_id,
        "assumptions": ["VOLL 12345 EUR/MWh"],
        "warnings": ["Penalty 12345 EUR/MWh"],
    }
    payload = json.dumps(stored).encode()
    monkeypatch.setattr(results, "load_result_bytes", lambda *_: payload)
    job = SimpleNamespace(
        network_id=network_id,
        spec={"mitigation": {"load_shedding": {"enabled": True, "voll_eur_per_mwh": 12345}}},
    )
    result = load_result(SimpleNamespace(catalog=CATALOG), None, job)
    assert (
        result["cost_basis"]["money_unit"]
        == CATALOG.get(network_id).manifest["cost_basis"]["money_unit"]
    )
    assert result["cost_basis"]["penalties"][0]["value_per_mwh"] == 12345
    assert result["cost_basis"]["penalties"][0]["unit"] == result["cost_basis"]["price_unit"]
    unit = result["cost_basis"]["price_unit"]
    assert result["assumptions"] == [f"VOLL 12345 {unit}"]
    assert result["warnings"] == [f"Penalty 12345 {unit}"]
    assert "cost_basis" not in json.loads(payload)
    assert "penalties" not in CATALOG.get(network_id).manifest["cost_basis"]


def test_http_network_and_legacy_comparison_reports_use_declared_units(client):
    ctx = client.app.state.ctx
    basis = deepcopy(CATALOG.get("pglib-case14-ieee").manifest["cost_basis"])
    ctx.catalog.get(NETWORK_ID).manifest["cost_basis"] = basis
    assert client.get("/api/v1/networks").json()["items"][0]["cost_basis"] == basis
    assert client.get(f"/api/v1/networks/{NETWORK_ID}").json()["cost_basis"] == basis
    baseline = run_job(client, scenario("basis-base"))
    stress = run_job(client, scenario("basis-stress", demand=1.5))
    comparison = client.post(
        "/api/v1/comparisons",
        json={"baseline_job_id": baseline["id"], "scenario_job_id": stress["id"]},
    )
    assert comparison.status_code == 201, comparison.text
    report = comparison.json()["report"]
    assert report["cost_basis"]["money_unit"] == "PGLib cost units"
    assert report["costs_comparable"] is True
    cost = next(r for r in report["metrics"] if r["metric"] == "total_system_cost_eur")
    assert cost["unit"] == "PGLib cost units" and cost["delta"] is not None
    for report_id in (comparison.json()["id"], baseline["id"]):
        md = client.get(f"/api/v1/reports/{report_id}?format=md")
        assert md.status_code == 200
        assert "PGLib cost units" in md.text
        assert "| EUR |" not in md.text


def test_stored_legacy_comparison_is_relabelled_without_mutating_document():
    from gridstorm_api.comparisons import legacy_report_cost_basis

    basis = CATALOG.get("pglib-case14-ieee").manifest["cost_basis"]
    legacy = {
        "baseline": {"job_id": "baseline"},
        "scenario": {"job_id": "scenario"},
        "metrics": [
            {
                "metric": "total_system_cost_eur",
                "unit": "EUR",
                "delta_unit": "EUR",
                "baseline": 100,
                "scenario": 120,
                "delta": 20,
                "delta_pct": 20,
            }
        ],
        "assumptions": ["VOLL 10000 EUR/MWh"],
        "warnings": [],
    }
    original = deepcopy(legacy)
    report = legacy_report_cost_basis(legacy, basis)
    assert legacy == original
    assert report["costs_comparable"] is True
    assert report["metrics"][0]["unit"] == "PGLib cost units"
    assert report["metrics"][0]["delta"] == 20
    assert report["assumptions"] == ["VOLL 10000 PGLib cost units/MWh"]
    unknown = legacy_report_cost_basis(legacy, None)
    assert unknown["costs_comparable"] is False
    assert unknown["metrics"][0]["delta"] is None
