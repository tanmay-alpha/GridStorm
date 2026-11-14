import numpy as np
import pytest

from gridstorm_distribution.metrics import (
    energy_mwh,
    loading_flags,
    run_stats,
    summarize_flags,
    top_elements,
    voltage_flags,
)


def test_run_stats_constructed_series():
    f = np.array([0, 1, 1, 0, 0, 1, 1, 1, 0, 1], dtype=bool)
    rs = run_stats(f)
    assert (rs.steps, rs.longest_run_steps, rs.events) == (6, 3, 3)
    assert run_stats(np.zeros(5, bool)) == run_stats(np.array([], bool))
    assert run_stats(np.ones(4, bool)).longest_run_steps == 4


def test_voltage_flags_limits_and_nan():
    vm = np.array(
        [
            [1.00, 1.11, 0.89],
            [np.nan, 1.10, 0.90],  # exactly at the limits -> no violation (strict)
            [1.20, 1.05, 0.80],
        ]
    )
    under, over = voltage_flags(vm, 0.9, np.array([1.1, 1.1, 1.1]))
    assert over.tolist() == [[False, True, False], [False, False, False], [True, False, False]]
    assert under.tolist() == [[False, False, True], [False, False, False], [False, False, True]]


def test_summarize_and_top_elements():
    vm = np.array([[1.12, 1.0], [1.13, 1.0], [1.0, 1.0], [1.11, 1.15]])
    _, over = voltage_flags(vm, 0.9, 1.1)
    s = summarize_flags(over, dt_h=0.25)
    assert s == {
        "steps_with_violation": 3,
        "hours_with_violation": 0.75,
        "longest_violation_h": 0.5,
        "violation_events": 2,
        "element_steps": 4,
        "elements_affected": 2,
    }
    top = top_elements(over, vm, ["a", "b"], worst="max", dt_h=0.25)
    assert [t["name"] for t in top] == ["a", "b"]
    assert top[0]["violation_steps"] == 3 and top[0]["max"] == pytest.approx(1.13)
    assert top[1]["violation_h"] == 0.25 and top[1]["max"] == pytest.approx(1.15)


def test_loading_flags_and_energy():
    ld = np.array([[99.9, 100.0], [100.1, np.nan]])
    assert loading_flags(ld, 100.0).tolist() == [[False, False], [True, False]]
    assert energy_mwh(np.array([1.0, np.nan, 3.0]), 0.25) == pytest.approx(1.0)
    assert energy_mwh(np.array([np.nan, np.nan]), 0.25) is None
    assert energy_mwh(np.array([]), 0.25) is None
