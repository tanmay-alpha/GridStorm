"""Offline checks of every committed PyPSA result, including harness fault injection."""

from copy import deepcopy

import numpy as np
import pytest
import stormspec

import netmodel
from harness import evaluate_artifact, evaluate_result, load
from invariants import CHECKS, Report
from paths import ARTIFACTS, PRESETS, artifact_paths

PATHS = artifact_paths()


def test_artifact_inventory():
    assert len(PATHS) == 15
    index = load(ARTIFACTS / "index.json")
    assert {p.stem for p in PATHS} == {row["artifact_id"] for row in index["artifacts"]}


@pytest.mark.parametrize("path", PATHS, ids=lambda p: p.stem)
@pytest.mark.parametrize("check", ("provenance", *CHECKS))
def test_committed_invariant(path, check):
    report = evaluate_artifact(path)
    result = report.checks[check]
    assert result.status in {"pass", "n/a"}, "\n".join(result.messages)


@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
def test_nonfinite_value_cannot_pass_bound(value):
    report = Report("corrupt bound")
    report.bound("bound", "p<=capacity", [value], 100, 1e-5)
    assert report.failures(), "nonfinite physics must not silently satisfy a limit"


@pytest.mark.parametrize("value", [np.inf, -np.inf])
def test_nonfinite_equality_cannot_pass(value):
    report = Report("corrupt equality")
    report.compare("equal", "energy", [value], [value], 1e-5)
    assert report.failures(), "infinite energy is not valid, even when both sides match"


@pytest.mark.parametrize(
    ("preset", "field", "check"),
    [
        ("ac-dc-meshed-baseline", "balance", "power_balance"),
        ("ac-dc-meshed-baseline", "energy", "energy_accounting"),
        ("ac-dc-meshed-baseline", "load", "demand_multipliers"),
        ("ac-dc-meshed-baseline", "generator", "generator_limits"),
        ("ac-dc-meshed-baseline", "branch", "branch_limits"),
        ("ac-dc-meshed-baseline", "objective", "objective"),
        ("pglib-case14-ieee-baseline", "co2", "co2"),
        ("pglib-case14-ieee-baseline", "outcome", "outcome_mapping"),
        ("pglib-case14-ieee-gen-1-outage", "outage", "outage_events"),
        ("scigrid-de-baseline", "storage", "storage"),
    ],
)
def test_corruption_is_detected(preset, field, check):
    scenario = stormspec.load_scenario(PRESETS / f"{preset}.yaml")
    result = deepcopy(load(ARTIFACTS / f"{preset}.json")["payload"])
    if field == "balance":
        result["assets"]["buses"][0]["load_shed_mw"][0] += 1
    elif field == "energy":
        result["metrics"]["unserved_energy_mwh"] += 1
    elif field == "load":
        result["series"]["load_mw"][0] += 1
    elif field == "generator":
        result["assets"]["generators"][0]["p_mw"][0] += 10000
    elif field == "branch":
        result["assets"]["lines"][0]["flow_mw"][0] += 10000
    elif field == "objective":
        result["solver"]["objective_eur"] += 1
    elif field == "co2":
        result["metrics"]["co2_emissions_t"] = 0
    elif field == "outcome":
        result["solver"]["termination_condition"] = "infeasible"
    elif field == "outage":
        next(g for g in result["assets"]["generators"] if g["outaged"])["p_mw"][0] = 1
    elif field == "storage":
        result["assets"]["storage_units"][0]["soc_mwh"][0] += 10000
    report = evaluate_result(result, scenario, field)
    assert check in report.failures(), report.facts


def test_nonunit_snapshot_weightings_are_exercised():
    scenario = stormspec.load_scenario(PRESETS / "pypsa-eur-be-baseline.yaml")
    assert np.all(netmodel.build(scenario).w_gen == 24)
    assert (
        evaluate_artifact(ARTIFACTS / "pypsa-eur-be-baseline.json")
        .checks["energy_accounting"]
        .status
        == "pass"
    )
