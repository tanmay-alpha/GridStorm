"""Small pandapower/SimBench runs (8 midday steps) - convergence, mitigation effect, determinism."""

import json

import pytest

from gridstorm_distribution.artifact import build_artifact
from gridstorm_distribution.study import StudyConfig, run_study, tiny_net_check

GRID = "1-LV-rural1--2-sw"
START = "2016-05-27 11:00"  # sunny midday hours in the SimBench 2016 profiles


def _cfg(**kw):
    return StudyConfig(GRID, START, 8, ext_grid_vm_pu=1.055, **kw)


def test_tiny_case_converges():
    r = tiny_net_check()
    assert r["converged"]
    assert 0.9 < r["vm_min_pu"] <= r["vm_max_pu"] < 1.1


def test_short_timeseries_converges_and_is_consistent():
    p = run_study(_cfg(pv_factor=1.5))
    c = p["convergence"]
    assert c["converged_steps"] == c["steps"] == 8 and c["failed_steps"] == 0
    s = p["series"]
    assert len(s["time"]) == 8 and s["time"][0] == "2016-05-27T11:00"
    # energy balance per step (storages idle): import + PV = load + losses (MW)
    for imp, pv, load, loss in zip(
        s["grid_import_mw"], s["pv_mw"], s["load_mw"], s["losses_mw"], strict=True
    ):
        assert imp + pv == pytest.approx(load + loss, abs=1e-6)
    assert p["grid"]["storages_idled"] == p["grid"]["storages"] == 5
    assert p["summary"]["max_reverse_flow_mw"] > 0  # midday PV export


def test_mitigations_reduce_peak_voltage():
    base = run_study(_cfg(pv_factor=1.5))["summary"]
    cap = run_study(_cfg(pv_factor=1.5, pv_feed_in_cap_pu=0.5))
    qu = run_study(_cfg(pv_factor=1.5, q_u_control=True))
    assert cap["summary"]["energy_mwh"]["pv_curtailed"] > 0
    assert cap["summary"]["vm_max_pu"] < base["vm_max_pu"]
    assert base["over_voltage"]["hours_with_violation"] > 0
    assert (
        cap["summary"]["over_voltage"]["hours_with_violation"]
        < base["over_voltage"]["hours_with_violation"]
    )
    assert qu["convergence"]["failed_steps"] == 0
    assert "DERController" in qu["solver"]["controllers"]
    assert min(qu["series"]["pv_q_mvar"]) < 0  # PV absorbs reactive power at high voltage
    assert qu["summary"]["vm_max_pu"] < base["vm_max_pu"]
    # Reactive absorption can fix voltage while making thermal loading worse.
    assert qu["summary"]["max_trafo_loading_pct"] > base["max_trafo_loading_pct"]


def test_deterministic_payload():
    a = run_study(_cfg(load_factor=1.3))
    b = run_study(_cfg(load_factor=1.3))
    a.pop("runtime_s"), b.pop("runtime_s")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    ha = build_artifact(
        a, artifact_id="t", network_id="n", engine_version="x", command="c", inputs=[]
    )["artifact"]["payload_sha256"]
    hb = build_artifact(
        b, artifact_id="t", network_id="n", engine_version="x", command="c", inputs=[]
    )["artifact"]["payload_sha256"]
    assert ha == hb


def test_rejects_window_outside_profiles():
    with pytest.raises(ValueError):
        run_study(StudyConfig(GRID, "2016-12-31 23:00", 8))
    with pytest.raises(ValueError):
        run_study(StudyConfig(GRID, "2016-07-27 11:07", 8))


def test_nonconverged_power_flow_reports_unknown_results(monkeypatch):
    from gridstorm_distribution import study

    # A zero-iteration Newton solve cannot solve these nonzero injections.
    monkeypatch.setattr(study, "PF_MAX_ITERATION", 0)
    payload = run_study(StudyConfig(GRID, START, 2))
    assert payload["convergence"]["failed_steps"] == 2
    assert payload["convergence"]["converged_steps"] == 0
    assert payload["convergence"]["valid_hours"] == 0
    assert payload["series"]["converged"] == [False, False]
    for key in ("vm_min_pu", "vm_max_pu", "losses_mw", "load_mw", "pv_mw", "pv_curtailed_mw"):
        assert payload["series"][key] == [None, None]
    assert all(value is None for value in payload["summary"]["energy_mwh"].values())
    json.dumps(payload, allow_nan=False)
