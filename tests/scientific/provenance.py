"""Hash / provenance invariants of committed PyPSA artifacts (contract §3, §5)."""

from __future__ import annotations

import json

import stormspec

from invariants import Report
from paths import NETWORKS, PRESETS, REPO_ROOT


def check_provenance(doc: dict, rep: Report) -> stormspec.Scenario:
    """Recompute every hash an artifact records; return the preset scenario it was built from."""
    name = "provenance"
    head, res = doc["artifact"], doc["payload"]
    preset = PRESETS / f"{head['preset_id']}.yaml"
    scenario = stormspec.load_scenario(preset)
    h = stormspec.scenario_hash(scenario)
    for where, value in (
        ("payload.scenario_hash", res["scenario_hash"]),
        ("artifact.scenario_hash", head["scenario_hash"]),
        ("manifest.scenario_hash", res["manifest"]["scenario_hash"]),
    ):
        rep.require(name, value == h, f"{where} {value} != recomputed scenario_hash {h}")
    rep.require(
        name,
        res["scenario_id"] == scenario.id == head["artifact_id"] == head["preset_id"],
        "scenario/artifact/preset ids disagree",
    )
    net = scenario.dataset.network_id
    rep.require(
        name,
        res["network_id"] == head["network_id"] == net,
        f"network ids disagree: {res['network_id']} / {head['network_id']} / {net}",
    )

    nc = NETWORKS / net / "network.nc"
    file_sha = stormspec.file_sha256(nc)
    manifest = json.loads((NETWORKS / net / "manifest.json").read_text(encoding="utf-8"))
    listed = {f["path"]: f["sha256"] for f in manifest["files"]}
    inputs = {i["path"]: i["sha256"] for i in head["inputs"]}
    nc_rel = nc.relative_to(REPO_ROOT).as_posix()
    preset_rel = preset.relative_to(REPO_ROOT).as_posix()
    for where, value in (
        ("result manifest.dataset_sha256", res["manifest"]["dataset_sha256"]),
        ("artifact inputs network.nc", inputs.get(nc_rel)),
        ("dataset manifest.json files[network.nc]", listed.get("network.nc")),
    ):
        rep.require(name, value == file_sha, f"{where} {value} != sha256({nc_rel}) {file_sha}")
    if scenario.dataset.sha256 is not None:
        rep.require(
            name,
            scenario.dataset.sha256 == file_sha,
            f"preset pins dataset sha {scenario.dataset.sha256} != {file_sha}",
        )
    rep.require(
        name,
        inputs.get(preset_rel) == stormspec.file_sha256(preset),
        f"artifact input sha of {preset_rel} is stale (preset edited after precompute)",
    )
    rep.require(
        name,
        head["payload_sha256"] == stormspec.payload_sha256(res),
        "artifact.payload_sha256 != sha256(canonical payload)",
    )
    rep.require(
        name,
        res["manifest"]["result_sha256"] == stormspec.result_sha256(res),
        "manifest.result_sha256 != stormspec.result_sha256(payload)",
    )
    rep.require(
        name,
        res["engine"]["version"] == head["engine_version"] == res["manifest"]["engine_version"],
        "engine version disagrees between payload, header and manifest",
    )
    rep.require(
        name, head["outcome"] == res["outcome"], "artifact header outcome != payload outcome"
    )
    rep.facts["scenario_hash"] = h
    rep.facts["dataset_sha256"] = file_sha
    return scenario
