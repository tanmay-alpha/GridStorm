"""Unsupported StormSpec content is rejected before any environment is created (no dataset)."""

import pytest

from gridstorm_grid2op import ScenarioRejected, run_scenario


def _scenario(**over):
    base = {
        "schema_version": "stormspec/1.0",
        "id": "g2o-test-reject",
        "name": "test",
        "dataset": {"network_id": "l2rpn-case14-sandbox"},
        "horizon": {"start": 0, "snapshots": 25},
        "events": [],
        "mitigation": {"load_shedding": {"enabled": False}},
        "execution": {
            "engine": "grid2op",
            "formulation": "sequential",
            "solver": "lightsim2grid",
            "seed": 0,
        },
    }
    base.update(over)
    return base


@pytest.mark.parametrize(
    "event",
    [
        {"type": "demand_multiplier", "value": 1.2},
        {"type": "demand_multiplier", "value": 1.2, "window": {"start": 2, "end": 10}},
        {"type": "generator_outage", "asset_id": "gen_0_4"},
        {"type": "renewable_availability_multiplier", "carrier": "wind", "value": 0.5},
        {"type": "link_outage", "asset_id": "x"},
        {"type": "storage_state", "asset_id": "x", "initial_soc_fraction": 0.5},
    ],
)
def test_unsupported_events_rejected(event):
    with pytest.raises(ScenarioRejected) as exc:
        run_scenario(_scenario(events=[event]))
    assert [i["code"] for i in exc.value.issues] == ["unsupported_operation"]
    assert exc.value.issues[0]["path"] == "events[0].type"


def test_load_shedding_rejected():
    with pytest.raises(ScenarioRejected) as exc:
        run_scenario(_scenario(mitigation={"load_shedding": {"enabled": True}}))
    assert [i["path"] for i in exc.value.issues] == ["mitigation.load_shedding.enabled"]


def test_wrong_engine_formulation_solver_rejected():
    ex = {"engine": "grid2op", "formulation": "lopf", "solver": "highs", "seed": 0}
    with pytest.raises(ScenarioRejected) as exc:
        run_scenario(_scenario(execution=ex))
    paths = {i["path"] for i in exc.value.issues}
    assert {"execution.formulation", "execution.solver"} <= paths


def test_wrong_network_rejected():
    with pytest.raises(ScenarioRejected) as exc:
        run_scenario(_scenario(dataset={"network_id": "pglib-case14-ieee"}))
    assert [i["code"] for i in exc.value.issues] == ["network_mismatch"]


def test_single_snapshot_horizon_rejected():
    with pytest.raises(ScenarioRejected) as exc:
        run_scenario(_scenario(horizon={"start": 0, "snapshots": 1}))
    assert exc.value.issues[0]["path"] == "horizon.snapshots"


def test_unknown_agent_rejected():
    with pytest.raises(ValueError):
        run_scenario(_scenario(), agent="ppo")
