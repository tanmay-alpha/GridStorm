import pytest

from gridstorm_grid2op.kpis import compute_kpis

DN = {"type": "do_nothing", "targets": [], "source": "agent", "illegal": False}


def _trace():
    # 3 lines, initial state + 4 steps, game over at step 4.
    return {
        "t": [0, 1, 2, 3, 4],
        "datetime": ["2019-01-01T00:00:00"] * 5,
        "rho": [
            [0.5, 0.9, 0.2],
            [0.6, 1.2, 0.3],  # one overload
            [0.0, 1.1, 1.05],  # line 0 disconnected (rho ignored), two overloads
            [0.4, 0.8, 0.7],  # line 0 reconnected
            None,  # game over row
        ],
        "line_status": [
            [True, True, True],
            [True, True, True],
            [False, True, True],
            [True, True, True],
            None,
        ],
        "action": [
            None,
            {"type": "disconnect_line", "targets": ["l0"], "source": "scenario", "illegal": False},
            {
                "type": "reconnect_line",
                "targets": ["l0"],
                "source": "agent",
                "illegal": True,
                "blocked_by_scenario": False,
            },
            {"type": "reconnect_line", "targets": ["l0"], "source": "agent", "illegal": False},
            DN,
        ],
        "reward": [None, 1.0, 0.5, 0.25, -1.0],
        "load_mw": [10.0, 10.0, 10.0, 10.0, None],
        "gen_mw": [10.2, 10.2, 10.2, 10.2, None],
        "topo_distance": [0, 0, 1, 0, None],
    }


def test_kpis_on_synthetic_trace():
    k = compute_kpis(_trace(), {"step": 4, "reasons": ["DivergingPowerflow: x"]}, max_steps=10)
    assert k["survival_steps"] == 3
    assert k["survived"] is False
    assert k["survival_ratio"] == 0.3
    assert k["overload_line_steps"] == 3
    assert k["steps_with_overload"] == 2
    assert k["disconnection_events"] == 1
    assert k["reconnection_events"] == 1
    assert k["forced_events"] == 1
    assert k["illegal_actions"] == 1
    assert k["actions_count"] == 1
    assert k["actions_by_type"] == {"reconnect_line": 1}
    assert k["cumulative_reward"] == pytest.approx(0.75)
    # connected lines over rows 1..3: 0.6,1.2,0.3 | 1.1,1.05 | 0.4,0.8,0.7
    assert k["mean_rho"] == pytest.approx(round(6.15 / 8, 4))
    assert k["max_rho"] == 1.2
    assert k["max_rho_line_index"] == 1
    assert k["max_topological_distance"] == 1
    assert k["game_over_reasons"] == ["DivergingPowerflow: x"]


def test_kpis_full_survival():
    tr = _trace()
    for key in tr:
        tr[key] = tr[key][:4]
    k = compute_kpis(tr, None, max_steps=3)
    assert k["survival_steps"] == 3
    assert k["survived"] is True


def test_kpis_reject_ragged_trace():
    tr = _trace()
    tr["reward"] = tr["reward"][:3]
    with pytest.raises(ValueError):
        compute_kpis(tr, None, max_steps=4)
