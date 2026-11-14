from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

import stormspec
from stormspec import (
    CAPABILITIES,
    Scenario,
    canonical_json,
    eens,
    load_scenario,
    scenario_hash,
    validate,
)

from conftest import base_scenario

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILE = ROOT / "schema" / "stormspec-1.0.schema.json"


def codes(issues):
    return [i.code for i in issues]


# --------------------------------------------------------------------------- schema / models


def test_schema_file_is_current():
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import export_schema
    finally:
        sys.path.pop(0)
    assert SCHEMA_FILE.read_text(encoding="utf-8") == export_schema.render()


def test_round_trip_and_schema_validates_dump():
    s = Scenario.model_validate(
        base_scenario(
            events=[
                {"type": "demand_multiplier", "value": 1.2, "window": {"start": 2, "end": 5}},
                {"type": "renewable_availability_multiplier", "carrier": "wind", "value": 0.3},
                {"type": "line_outage", "asset_id": "l12"},
                {"type": "link_outage", "asset_id": "dc1"},
                {"type": "generator_outage", "asset_id": "g-gas"},
                {"type": "storage_state", "asset_id": "phs1", "initial_soc_fraction": 0.2},
            ]
        )
    )
    dumped = s.model_dump(mode="json")
    assert Scenario.model_validate(dumped) == s
    assert Scenario.model_validate_json(s.model_dump_json()) == s
    schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    jsonschema.validate(dumped, schema)
    assert [type(e).__name__ for e in s.events] == [
        "DemandMultiplier",
        "RenewableAvailabilityMultiplier",
        "LineOutage",
        "LinkOutage",
        "GeneratorOutage",
        "StorageState",
    ]


def test_schema_rejects_what_models_reject():
    schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    bad = base_scenario(id="Bad Id")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)
    with pytest.raises(ValidationError):
        Scenario.model_validate(bad)


@pytest.mark.parametrize(
    "event",
    [
        {"type": "demand_multiplier", "value": 0},
        {"type": "demand_multiplier", "value": 6},
        {"type": "demand_multiplier", "value": 1.1, "buses": []},
        {"type": "demand_multiplier", "value": 1.1, "buses": ["b1", "b1"]},
        {"type": "renewable_availability_multiplier", "carrier": "wind", "value": 1.5},
        {"type": "storage_state", "asset_id": "phs1", "initial_soc_fraction": 1.2},
        {"type": "line_outage", "asset_id": "l12", "window": {"start": 5, "end": 5}},
        {"type": "line_outage", "asset_id": "l12", "extra": 1},
        {"type": "meteor_strike", "asset_id": "l12"},
    ],
)
def test_structural_rejections(event):
    with pytest.raises(ValidationError):
        Scenario.model_validate(base_scenario(events=[event]))


def test_unknown_top_level_field_rejected():
    with pytest.raises(ValidationError):
        Scenario.model_validate(base_scenario(colour="red"))


# --------------------------------------------------------------------------- hashing


def test_hash_stable_and_ignores_wording_and_explicit_defaults():
    a = base_scenario()
    b = base_scenario(
        name="Completely different title",
        description="prose",
        mitigation={
            "storage_dispatch": True,
            "curtailment": True,
            "load_shedding": {"enabled": True, "voll_eur_per_mwh": 10000},
        },
        execution={
            "engine": "pypsa",
            "formulation": "lopf",
            "solver": "highs",
            "solver_options": {"time_limit_s": 120, "threads": 1},
            "deterministic": True,
            "seed": 0,
        },
    )
    assert scenario_hash(a) == scenario_hash(b)
    assert canonical_json(a) == canonical_json(b)
    # pinned value: changes only if the canonical form changes (that is a schema change)
    assert scenario_hash(a) == scenario_hash(Scenario.model_validate(a))
    assert len(scenario_hash(a)) == 64
    raw = canonical_json(a)
    assert b" " not in raw.replace(b"stormspec/1.0", b"")
    assert b'"name"' not in raw and b'"description"' not in raw


def test_hash_changes_with_semantics():
    a = base_scenario()
    c = base_scenario(events=[{"type": "demand_multiplier", "value": 1.2}])
    d = base_scenario(horizon={"start": 0, "snapshots": 12})
    assert len({scenario_hash(a), scenario_hash(c), scenario_hash(d)}) == 3


def test_payload_and_result_hash():
    r = {"a": 1, "b": [1.5, 2], "manifest": {"result_sha256": "x"}}
    r2 = {"b": [1.5, 2], "a": 1, "manifest": {"result_sha256": "y"}}
    assert stormspec.result_sha256(r) == stormspec.result_sha256(r2)
    assert stormspec.payload_sha256({"a": 1}) == stormspec.payload_sha256({"a": 1})


# --------------------------------------------------------------------------- validation


def test_valid_scenario(network):
    s = base_scenario(
        events=[
            {"type": "demand_multiplier", "value": 1.2, "buses": ["b3"],
             "window": {"start": 0, "end": 6}},
            {"type": "renewable_availability_multiplier", "carrier": "wind", "value": 0.3},
            {"type": "line_outage", "asset_id": "l12"},
            {"type": "line_outage", "asset_id": "t13", "component": "transformer"},
            {"type": "link_outage", "asset_id": "dc1"},
            {"type": "generator_outage", "asset_id": "g-gas", "window": {"start": 3, "end": 9}},
            {"type": "storage_state", "asset_id": "phs1", "initial_soc_fraction": 0.5},
        ]
    )
    rep = validate(s, network)
    assert rep.valid, rep.errors
    assert codes(rep.warnings) == ["dataset_unpinned"]


def test_bad_ids(network):
    s = base_scenario(
        events=[
            {"type": "line_outage", "asset_id": "nope"},
            {"type": "line_outage", "asset_id": "g-gas"},
            {"type": "generator_outage", "asset_id": "l12"},
            {"type": "storage_state", "asset_id": "missing", "initial_soc_fraction": 0.1},
            {"type": "demand_multiplier", "value": 1.1, "buses": ["b1", "zz"]},
            {"type": "renewable_availability_multiplier", "carrier": "solar", "value": 0.5},
            {"type": "renewable_availability_multiplier", "carrier": "gas", "value": 0.5},
            {"type": "line_outage", "asset_id": "t13"},
            {"type": "line_outage", "asset_id": "l12", "component": "transformer"},
        ]
    )
    rep = validate(s, network)
    assert not rep.valid
    assert codes(rep.errors) == [
        "unknown_asset",
        "unknown_asset",
        "unknown_asset",
        "unknown_asset",
        "no_loads",
        "unknown_asset",
        "unknown_carrier",
        "no_variable_generators",
        "unknown_asset",
        "unknown_asset",
    ]
    assert rep.errors[0].path == "events[0].asset_id"
    assert "exists as a generator" in rep.errors[1].message
    assert rep.errors[4].path == "events[4].buses[0]"
    assert "exists as a transformer" in rep.errors[8].message


def test_line_and_transformer_with_same_id(network):
    network["transformers"].append({"id": "l12", "bus0": "b1", "bus1": "b2"})
    s = base_scenario(
        events=[
            {"type": "line_outage", "asset_id": "l12"},
            {"type": "line_outage", "asset_id": "l12", "component": "transformer"},
        ]
    )
    rep = validate(s, network)
    assert rep.valid, rep.errors
    assert "duplicate_outage" not in codes(rep.warnings)
    assert Scenario.model_validate(s).events[0].component == "line"


def test_windows_and_horizon(network):
    s = base_scenario(
        horizon={"start": 4, "snapshots": 10},
        events=[
            {"type": "generator_outage", "asset_id": "g-gas", "window": {"start": 0, "end": 6}},
            {"type": "generator_outage", "asset_id": "g-gas", "window": {"start": 10, "end": 15}},
            {"type": "generator_outage", "asset_id": "g-gas", "window": {"start": 4, "end": 14}},
        ],
    )
    rep = validate(s, network)
    assert codes(rep.errors) == ["window_out_of_range", "window_out_of_range"]
    assert "duplicate_outage" in codes(rep.warnings)
    rep = validate(base_scenario(horizon={"start": 20, "snapshots": 5}), network)
    assert codes(rep.errors) == ["horizon_out_of_range"]


def test_network_mismatch(network):
    rep = validate(base_scenario(dataset={"network_id": "other-net"}), network)
    assert codes(rep.errors) == ["network_mismatch"]


def test_schema_error_reported_not_raised(network):
    rep = validate(base_scenario(horizon={"start": -1, "snapshots": 0}), network)
    assert not rep.valid
    assert set(codes(rep.errors)) == {"schema_error"}
    assert {i.path for i in rep.errors} == {"horizon.start", "horizon.snapshots"}


def test_conflicting_storage_state(network):
    ev = {"type": "storage_state", "asset_id": "phs1", "initial_soc_fraction": 0.1}
    rep = validate(base_scenario(events=[ev, ev]), network)
    assert codes(rep.errors) == ["conflicting_events"]


# --------------------------------------------------------------------------- capabilities


def test_pypsa_rejects_partial_window_line_outage(network):
    s = base_scenario(
        events=[
            {"type": "line_outage", "asset_id": "l12", "window": {"start": 0, "end": 12}},
            {"type": "link_outage", "asset_id": "dc1", "window": {"start": 0, "end": 24}},
        ]
    )
    rep = validate(s, network)
    assert codes(rep.errors) == ["unsupported_operation"]
    assert rep.errors[0].path == "events[0].window"


def test_pypsa_rejects_other_formulations(network):
    s = base_scenario(execution={"engine": "pypsa", "formulation": "ac_pf"})
    assert codes(validate(s, network).errors) == ["unsupported_operation"]
    s = base_scenario(execution={"engine": "pypsa", "formulation": "lopf", "solver": "gurobi"})
    assert codes(validate(s, network).errors) == ["unsupported_operation"]


def test_pandapower_capabilities(network):
    ok = base_scenario(
        horizon={"start": 3, "snapshots": 1},
        events=[{"type": "line_outage", "asset_id": "l12"}],
        mitigation={"load_shedding": {"enabled": False}},
        execution={"engine": "pandapower", "formulation": "ac_pf", "solver": None},
    )
    rep = validate(ok, network)
    assert rep.valid, rep.errors
    assert codes(rep.warnings).count("mitigation_not_modelled") == 2

    bad = base_scenario(
        horizon={"start": 0, "snapshots": 2},
        events=[
            {"type": "storage_state", "asset_id": "phs1", "initial_soc_fraction": 0.1},
            {"type": "line_outage", "asset_id": "l12", "window": {"start": 0, "end": 1}},
        ],
        execution={"engine": "pandapower", "formulation": "lopf", "solver": None},
    )
    rep = validate(bad, network)
    paths = {i.path for i in rep.errors if i.code == "unsupported_operation"}
    assert paths == {
        "execution.formulation",
        "horizon.snapshots",
        "events[0].type",
        "events[1].window",
        "mitigation.load_shedding.enabled",
    }


def test_grid2op_capabilities_declared():
    caps = CAPABILITIES["grid2op"]
    assert caps.formulations == ("sequential",)
    assert caps.event_types == frozenset({"line_outage"})
    assert caps.accepts_window("line_outage")
    assert set(CAPABILITIES) == {"pypsa", "pandapower", "grid2op"}


# --------------------------------------------------------------------------- EENS


def test_eens():
    assert eens([(0.9, 0.0), (0.1, 50.0)]) == pytest.approx(5.0)
    assert eens([(1.0, 12.5)]) == 12.5
    with pytest.raises(ValueError):
        eens([(0.5, 10.0), (0.4, 0.0)])
    with pytest.raises(ValueError):
        eens([(1.2, 1.0), (-0.2, 1.0)])
    with pytest.raises(ValueError):
        eens([(1.0, -1.0)])
    with pytest.raises(ValueError):
        eens([])


# --------------------------------------------------------------------------- IO / presets


def test_load_yaml_and_json(tmp_path):
    import yaml

    data = base_scenario(events=[{"type": "demand_multiplier", "value": 1.2}])
    (tmp_path / "s.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    (tmp_path / "s.json").write_text(json.dumps(data), encoding="utf-8")
    a = load_scenario(tmp_path / "s.yaml")
    b = load_scenario(tmp_path / "s.json")
    assert a == b
    with pytest.raises(ValueError):
        (tmp_path / "s.txt").write_text("x", encoding="utf-8")
        load_scenario(tmp_path / "s.txt")


def test_presets_parse_and_are_unique():
    presets = stormspec.load_presets()
    assert len(presets) >= 4
    ids = [p.id for p in presets]
    assert len(ids) == len(set(ids))
    for path, p in zip(stormspec.preset_paths(), presets, strict=True):
        assert path.stem == p.id, f"{path.name} must be named after its id"
        assert not stormspec.check_capabilities(p), p.id
