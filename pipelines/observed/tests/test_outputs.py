"""Committed outputs: scenario validity, consistency with derived parameters, manifest checksums."""

from __future__ import annotations

import json
import math

import pytest
import stormspec

from gridstorm_observed import sources

SCENARIOS = sorted(sources.SCENARIO_OUT_DIR.glob("*.yaml"))
DERIVED = json.loads((sources.OPSD_OUT_DIR / "derived-multipliers.json").read_text("utf-8"))
OPSD_MANIFEST = json.loads((sources.OPSD_OUT_DIR / "manifest.json").read_text("utf-8"))
POWER_MANIFEST = json.loads((sources.POWER_OUT_DIR / "manifest.json").read_text("utf-8"))
CANONICAL = sources.NETWORK_DIR / "canonical.json"


def test_at_least_two_scenarios():
    assert len(SCENARIOS) >= 2


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: p.stem)
def test_scenario_valid_hourly_demand_daily_renewables(path):
    scen = stormspec.load_scenario(path)
    assert scen.id == path.stem
    assert scen.dataset.network_id == "scigrid-de"
    assert scen.dataset.sha256 == DERIVED["network"]["network_nc_sha256"]
    canon = json.loads(CANONICAL.read_text("utf-8"))
    report = stormspec.validate(scen, canon)
    assert report.valid, report.errors
    demand = [e for e in scen.events if e.type == "demand_multiplier"]
    assert [(e.window.start, e.window.end) for e in demand] == [(h, h + 1) for h in range(24)]
    for e in scen.events:
        if e.type == "renewable_availability_multiplier":
            assert (e.window.start, e.window.end) == (0, 24)


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: p.stem)
def test_scenario_matches_derived_parameters(path):
    scen = stormspec.load_scenario(path)
    rec = next(s for s in DERIVED["scenarios"] if s["scenario_id"] == scen.id)
    demand = [e.value for e in scen.events if e.type == "demand_multiplier"]
    assert demand == rec["demand"]["multipliers"]
    for carrier, r in rec["renewables"].items():
        got = [
            e.value
            for e in scen.events
            if e.type == "renewable_availability_multiplier" and e.carrier == carrier
        ]
        assert got == ([] if r["daily_multiplier"] == 1.0 else [r["daily_multiplier"]])
        assert not r["clipped_at_1"] or r["daily_multiplier"] == 1.0
        assert r["modeled_daily_mean_cf"] == pytest.approx(
            r["daily_multiplier"] * r["network_daily_mean_cf"], abs=1e-4
        )
    assert rec["events"] == len(scen.events)


def test_opsd_manifest_checksums_and_license():
    for rel, sha in OPSD_MANIFEST["scenario_files"].items():
        assert sources.sha256_file(sources.REPO_ROOT / rel) == sha, rel
    for name, sha in OPSD_MANIFEST["derived_files"].items():
        assert sources.sha256_file(sources.OPSD_OUT_DIR / name) == sha, name
    for rec in DERIVED["scenarios"]:
        rel = f"data/scenarios/observed/{rec['scenario_id']}.yaml"
        assert OPSD_MANIFEST["scenario_files"][rel] == rec["scenario_sha256"]
    src = OPSD_MANIFEST["source"]
    assert src["sha256"] == sources.OPSD_CSV_SHA256
    assert src["url"] == sources.OPSD_CSV_URL
    lic = OPSD_MANIFEST["license"]
    assert lic["redistribution"] == "derived-only"
    assert lic["load_forecast_license"] == "CC-BY-4.0"
    assert lic["load_forecast_attribution"] == sources.LOAD_FORECAST_ATTRIBUTION
    assert "CC BY 4.0" in lic["load_forecast_attribution"]
    assert "Changes made by GridStorm" in lic["load_forecast_attribution"]
    assert set(src["column_sources"]) == set(sources.OPSD_DE_COLUMNS)
    assert src["column_reuse"] == sources.OPSD_COLUMN_REUSE
    assert "BNetzA" in src["column_sources"]["DE_solar_capacity"]["name"]
    for col in sources.OPSD_DE_COLUMNS:
        if col.endswith(("_entsoe_transparency", "_generation_actual")):
            assert "ENTSO-E" in src["column_sources"][col]["name"], col
    assert set(OPSD_MANIFEST["quality_flags"]) == {r["scenario_id"] for r in DERIVED["scenarios"]}


def test_no_observed_opsd_series_committed():
    # Only JSON (derived parameters + manifest) may live in data/observed/opsd-de; the
    # information content of these files is checked in test_reuse.py.
    files = sorted(p.name for p in sources.OPSD_OUT_DIR.iterdir())
    assert files == ["derived-multipliers.json", "manifest.json"]


def test_power_manifest_checksum():
    for name, sha in POWER_MANIFEST["files"].items():
        assert sources.sha256_file(sources.POWER_OUT_DIR / name) == sha, name
    assert "reanalysis" in POWER_MANIFEST["provenance"]


def test_solved_results_reproduce_inputs_and_conserve_energy():
    results = json.loads((sources.OBSERVED_DIR / "analogue-results.json").read_text("utf-8"))
    assert results["network_nc_sha256"] == sources.sha256_file(sources.NETWORK_DIR / "network.nc")
    runs = {r["scenario_id"]: r for r in results["runs"]}
    assert len(runs) == len(DERIVED["scenarios"]) + 1
    network_load = DERIVED["network"]["load_mw"]
    for run in runs.values():
        assert run["outcome"] == "feasible"
        assert run["solver"]["termination_condition"] == "optimal"
        assert all(v["valid"] for v in run["validation"].values())
        m, integral = run["metrics"], run["series_integrals_mwh"]
        assert all(math.isfinite(v) for v in integral.values())
        # The adapter serializes each hourly MW series to four decimals. These scenarios
        # have 24 one-hour snapshots: each integral has at most 24 * 0.5e-4 MWh roundoff.
        integral_roundoff = 24 * 0.5e-4
        assert integral["load"] == pytest.approx(m["total_load_mwh"], abs=integral_roundoff + 5e-7)
        assert integral["load_shed"] == pytest.approx(
            m["unserved_energy_mwh"], abs=integral_roundoff + 5e-7
        )
        # Generation integrates one rounded series per carrier, plus net storage dispatch.
        balance_roundoff = (len(run["generation_by_carrier_mwh"]) + 1) * integral_roundoff + 5e-7
        assert integral["generation"] + integral["storage_dispatch"] == pytest.approx(
            m["served_load_mwh"], abs=balance_roundoff
        )
        assert m["served_load_mwh"] + m["unserved_energy_mwh"] == pytest.approx(
            m["total_load_mwh"], abs=1e-3
        )
        assert m["balance_residual_max_mw"] < 1e-5
        assert m["max_line_loading_pct"] <= 100.0001
        assert m["load_shedding_cost_eur"] == pytest.approx(
            10000 * m["unserved_energy_mwh"], abs=0.02
        )
        if run["role"] == "observed_analogue":
            scen = stormspec.load_scenario(sources.REPO_ROOT / run["scenario_file"])
            assert run["scenario_hash"] == stormspec.scenario_hash(scen)
            assert run["scenario_sha256"] == sources.sha256_file(
                sources.REPO_ROOT / run["scenario_file"]
            )
            rec = next(r for r in DERIVED["scenarios"] if r["scenario_id"] == scen.id)
            # Network profile is stored to 0.001 MW, hence allow 24*h rounding accumulation.
            expected_load = sum(
                p * multiplier
                for p, multiplier in zip(network_load, rec["demand"]["multipliers"], strict=True)
            )
            assert integral["load"] == pytest.approx(expected_load, abs=0.03)
