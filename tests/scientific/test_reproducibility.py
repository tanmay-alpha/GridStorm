"""Two real HiGHS reruns; opt in with ``-m slow`` (no network access)."""

import json

import pytest
import stormspec
from gridstorm_pypsa import run_scenario

from harness import evaluate_result, load
from paths import ARTIFACTS, NETWORKS, PRESETS


@pytest.mark.slow
@pytest.mark.parametrize("preset", ["ac-dc-meshed-baseline", "pglib-case14-ieee-baseline"])
def test_reproduce_small_preset(preset):
    scenario = stormspec.load_scenario(PRESETS / f"{preset}.yaml")
    committed = load(ARTIFACTS / f"{preset}.json")["payload"]
    fresh = run_scenario(scenario, NETWORKS / scenario.dataset.network_id)
    report = evaluate_result(fresh, scenario, preset)
    assert not report.failures(), report.failures()
    assert fresh["outcome"] == committed["outcome"] == "feasible"
    objective = fresh["solver"]["objective_eur"]
    reference = committed["solver"]["objective_eur"]
    assert objective == pytest.approx(reference, rel=1e-7, abs=1e-5)
    for key, expected in committed["metrics"].items():
        actual = fresh["metrics"][key]
        if expected is None:
            assert actual is None, key
        else:
            assert actual == pytest.approx(expected, rel=1e-7, abs=1e-5), key
    assert fresh["scenario_hash"] == committed["scenario_hash"]
    assert fresh["manifest"]["dataset_sha256"] == committed["manifest"]["dataset_sha256"]
    print(
        json.dumps(
            {
                "preset": preset,
                "objective_eur": objective,
                "reference_eur": reference,
                "absolute_difference_eur": abs(objective - reference),
                "metrics_compared": len(committed["metrics"]),
                "invariants": "pass",
            }
        )
    )
