"""Committed outputs: scenario validity, consistency with derived parameters, manifest checksums."""

from __future__ import annotations

import json

import pytest
import stormspec

from gridstorm_observed import sources

SCENARIOS = sorted(sources.SCENARIO_OUT_DIR.glob("*.yaml"))
DERIVED = json.loads((sources.OPSD_OUT_DIR / "derived-multipliers.json").read_text("utf-8"))
OPSD_MANIFEST = json.loads((sources.OPSD_OUT_DIR / "manifest.json").read_text("utf-8"))
POWER_MANIFEST = json.loads((sources.POWER_OUT_DIR / "manifest.json").read_text("utf-8"))
CANONICAL = sources.NETWORK_DIR / "canonical.json"


def _minimal_network() -> dict:
    """canonical-grid-shaped index from the network facts recorded in the derived file."""
    net = DERIVED["network"]
    return {
        "schema_version": "canonical-grid/1.0",
        "network_id": net["network_id"],
        "snapshots": {"count": 24},
        "buses": [{"id": "1"}],
        "generators": [
            {"id": f"g-{c}", "carrier": c, "is_variable": True}
            for c in net["variable_generators"]
        ],
        "loads": [{"id": "1", "bus": "1"}],
        "carriers": [{"id": c} for c in net["variable_generators"]],
    }


def test_at_least_two_scenarios():
    assert len(SCENARIOS) >= 2


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: p.stem)
def test_scenario_valid_and_hourly(path):
    scen = stormspec.load_scenario(path)
    assert scen.id == path.stem
    assert scen.dataset.network_id == "scigrid-de"
    assert scen.dataset.sha256 == DERIVED["network"]["network_nc_sha256"]
    report = stormspec.validate(scen, _minimal_network())
    assert report.valid, report.errors
    if CANONICAL.exists():
        canon = json.loads(CANONICAL.read_text("utf-8"))
        report = stormspec.validate(scen, canon)
        assert report.valid, report.errors
    demand = [e for e in scen.events if e.type == "demand_multiplier"]
    assert [(e.window.start, e.window.end) for e in demand] == [(h, h + 1) for h in range(24)]
    for e in scen.events:
        assert e.window is not None and e.window.end - e.window.start == 1


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: p.stem)
def test_scenario_matches_derived_parameters(path):
    scen = stormspec.load_scenario(path)
    rec = next(s for s in DERIVED["scenarios"] if s["scenario_id"] == scen.id)
    demand = [e.value for e in scen.events if e.type == "demand_multiplier"]
    assert demand == rec["demand"]["multipliers"]
    for carrier, r in rec["renewables"].items():
        got = {e.window.start: e.value for e in scen.events
               if e.type == "renewable_availability_multiplier" and e.carrier == carrier}
        want = {h: w for h, w in enumerate(r["multipliers"]) if w is not None and w != 1.0}
        assert got == want
        assert all(r["multipliers"][h] is None for h in r["undefined_hours"])
        assert all(r["multipliers"][h] == 1.0 for h in r["clipped_hours"])
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
    assert OPSD_MANIFEST["license"]["redistribution"] == "restricted"


def test_no_observed_opsd_series_committed():
    # Redistribution of the ENTSO-E-derived hourly columns is not established: only JSON
    # (derived parameters + manifest) may live in data/observed/opsd-de.
    files = sorted(p.name for p in sources.OPSD_OUT_DIR.iterdir())
    assert files == ["derived-multipliers.json", "manifest.json"]
    text = (sources.OPSD_OUT_DIR / "derived-multipliers.json").read_text("utf-8")
    assert "target_load_mw" not in text and "observed_cf\"" not in text


def test_power_manifest_checksum():
    for name, sha in POWER_MANIFEST["files"].items():
        assert sources.sha256_file(sources.POWER_OUT_DIR / name) == sha, name
    assert "reanalysis" in POWER_MANIFEST["provenance"]
