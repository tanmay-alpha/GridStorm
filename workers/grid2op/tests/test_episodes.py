"""Integration tests on the real l2rpn_case14_sandbox environment (downloaded by grid2op.make)."""

import pytest

from gridstorm_grid2op import (
    ForcedLineOutage,
    ScenarioRejected,
    make_env,
    run_episode,
    run_scenario,
)

# Every test here needs the real dataset; grid2op.make downloads it on first use.
pytestmark = [pytest.mark.network, pytest.mark.slow]

STEPS = 48


@pytest.fixture(scope="module")
def env():
    e = make_env("lightsim2grid")
    yield e
    e.close()


def _scenario(**over):
    base = {
        "schema_version": "stormspec/1.0",
        "id": "g2o-test-outage",
        "name": "test",
        "dataset": {"network_id": "l2rpn-case14-sandbox"},
        "horizon": {"start": 0, "snapshots": 25},
        "events": [{"type": "line_outage", "asset_id": "1_3_3", "window": {"start": 3, "end": 15}}],
        "mitigation": {"load_shedding": {"enabled": False}},
        "execution": {
            "engine": "grid2op",
            "formulation": "sequential",
            "solver": "lightsim2grid",
            "seed": 7,
        },
    }
    base.update(over)
    return base


@pytest.mark.parametrize("agent", ["reco_powerline", "greedy_simulate"])
def test_same_seed_same_trace_hash(env, agent):
    outage = (ForcedLineOutage(line="1_3_3", start_row=5, end_row=20),)
    a = run_episode(
        env, agent, chronics_id=1, env_seed=3, agent_seed=3, max_steps=STEPS, outages=outage
    )
    # Fresh environment: determinism must not depend on in-process state.
    env2 = make_env("lightsim2grid")
    try:
        b = run_episode(
            env2, agent, chronics_id=1, env_seed=3, agent_seed=3, max_steps=STEPS, outages=outage
        )
    finally:
        env2.close()
    assert a["trace_sha256"] == b["trace_sha256"]
    assert a["kpis"] == b["kpis"]


def test_forced_outage_applied_and_blocked(env):
    p = run_episode(
        env,
        "reco_powerline",
        chronics_id=0,
        env_seed=0,
        agent_seed=0,
        max_steps=30,
        outages=(ForcedLineOutage("1_3_3", 5, 20),),
    )
    lid = [ln for ln in env.name_line].index("1_3_3")
    steps = p["steps"]
    assert steps["line_status"][4][lid] is True
    assert steps["action"][5]["source"] == "scenario"
    assert steps["action"][5]["type"] == "disconnect_line"
    assert steps["line_status"][5][lid] is False
    # Inside the window the line stays out (agent reconnections are blocked).
    for row in range(5, 20):
        if steps["line_status"][row] is not None:
            assert steps["line_status"][row][lid] is False
    assert p["kpis"]["forced_events"] == 1
    assert p["kpis"]["blocked_actions"] >= 1  # RecoPowerline tries to reconnect after cooldown
    # After the window the agent reconnects it.
    assert any(steps["line_status"][r][lid] for r in range(20, 31) if steps["line_status"][r])


def test_outage_at_horizon_start_uses_init_state(env):
    p = run_episode(
        env,
        "do_nothing",
        chronics_id=0,
        env_seed=0,
        agent_seed=0,
        max_steps=5,
        outages=(ForcedLineOutage("1_3_3", 0, None),),
    )
    lid = [str(n) for n in env.name_line].index("1_3_3")
    assert p["steps"]["line_status"][0][lid] is False


def test_unknown_line_rejected():
    with pytest.raises(ScenarioRejected) as exc:
        run_scenario(_scenario(events=[{"type": "line_outage", "asset_id": "branch-1"}]))
    assert exc.value.issues[0]["code"] == "unknown_asset"


def test_run_scenario_line_outage():
    stages = []
    res = run_scenario(_scenario(), agent="reco_powerline", chronics_id=0, progress=stages.append)
    assert stages == [
        "loading_network",
        "applying_scenario",
        "building_model",
        "solving",
        "postprocessing",
        "done",
    ]
    assert res["schema_version"] == "gridstorm-result/1.0"
    assert res["engine"]["formulation"] == "sequential"
    trace = res["episode"]["trace"]
    assert trace["episode"]["max_steps"] == 24
    assert trace["crisis"] == [
        {"type": "forced_line_outage", "line": "1_3_3", "start_row": 3, "end_row": 15}
    ]
    line = next(ln for ln in res["assets"]["lines"] if ln["id"] == "1_3_3")
    assert line["outaged"] is True
    assert res["metrics"]["unserved_energy_mwh"] is None  # not modelled => null, never invented
    assert res["manifest"]["engine_name"] == "grid2op"
    again = run_scenario(_scenario(), agent="reco_powerline", chronics_id=0)
    assert again["episode"]["trace"]["trace_sha256"] == trace["trace_sha256"]
