"""Validate shipped presets and real precomputed results without another solver run."""

from __future__ import annotations

import json

import jsonschema
import pytest
import stormspec
from conftest import NETWORKS, REPO_ROOT, RESULT_SCHEMA

ARTIFACTS = REPO_ROOT / "data" / "artifacts" / "pypsa"
PRESETS = [
    p for p in stormspec.preset_paths() if stormspec.load_scenario(p).execution.engine == "pypsa"
]


@pytest.mark.parametrize("path", PRESETS, ids=lambda path: path.stem)
def test_preset_and_precomputed_artifact_contract(path):
    scenario = stormspec.load_scenario(path)
    network_dir = NETWORKS / scenario.dataset.network_id
    network = json.loads((network_dir / "canonical.json").read_text(encoding="utf-8"))
    report = stormspec.validate(scenario, network)
    assert report.valid, report.errors
    artifact_path = ARTIFACTS / f"{scenario.id}.json"
    assert artifact_path.stat().st_size < 5 * 1024 * 1024
    document = json.loads(artifact_path.read_text(encoding="utf-8"))
    header, result = document["artifact"], document["payload"]
    jsonschema.validate(result, json.loads(RESULT_SCHEMA.read_text(encoding="utf-8")))
    assert header["schema_version"] == "gridstorm-artifact/1.0"
    assert header["execution_mode"] == "precomputed"
    assert header["payload_sha256"] == stormspec.payload_sha256(result)
    assert header["scenario_hash"] == stormspec.scenario_hash(scenario) == result["scenario_hash"]
    assert result["manifest"]["result_sha256"] == stormspec.result_sha256(result)
    assert result["manifest"]["dataset_sha256"] == stormspec.file_sha256(network_dir / "network.nc")
    assert result["outcome"] in {"feasible", "infeasible"}
    assert header["measurements"]["peak_rss_mb"] > 0
    assert header["measurements"]["run_scenario_wall_time_s"] > 0
    for source in header["inputs"]:
        assert source["sha256"] == stormspec.file_sha256(REPO_ROOT / source["path"])
    if result["outcome"] == "feasible":
        assert result["metrics"]["balance_residual_max_mw"] < 1e-3
    index = json.loads((ARTIFACTS / "index.json").read_text(encoding="utf-8"))
    assert sum(entry["artifact_id"] == scenario.id for entry in index["artifacts"]) == 1


def test_transmission_outage_selection_matches_measured_baseline():
    result = json.loads((ARTIFACTS / "scigrid-de-baseline.json").read_text(encoding="utf-8"))[
        "payload"
    ]
    lines = result["assets"]["lines"]
    target = next(line for line in lines if line["id"] == "448")
    assert len(target["loading_pct"]) == 24
    assert all(loading == pytest.approx(100, abs=1e-3) for loading in target["loading_pct"])
    always_congested = [line for line in lines if min(line["loading_pct"]) >= 99.9]
    assert target["s_nom_mva"] == max(line["s_nom_mva"] for line in always_congested)


def test_storage_pair_changes_only_dispatch_toggle_and_improves_objective():
    scenarios = [
        stormspec.load_scenario(
            stormspec.PRESETS_DIR / f"scigrid-de-dunkelflaute-storage-{flag}.yaml"
        )
        for flag in ("off", "on")
    ]
    off, on = [scenario.model_dump(exclude={"id", "name", "description"}) for scenario in scenarios]
    assert off["mitigation"].pop("storage_dispatch") is False
    assert on["mitigation"].pop("storage_dispatch") is True
    assert off == on
    results = [
        json.loads((ARTIFACTS / f"{scenario.id}.json").read_text(encoding="utf-8"))["payload"]
        for scenario in scenarios
    ]
    disabled, enabled = results
    assert disabled["metrics"]["storage_discharge_mwh"] == 0
    assert disabled["metrics"]["storage_charge_mwh"] == 0
    assert enabled["assets"]["storage_units"]
    assert enabled["solver"]["objective_eur"] <= disabled["solver"]["objective_eur"] + 1e-3
