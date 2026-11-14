"""Scientific and contract tests for the PyPSA adapter (real HiGHS solves on data/networks)."""

from __future__ import annotations

import json
import subprocess
import sys
import warnings

import numpy as np
import pytest
import stormspec
from conftest import RESULT_SCHEMA, network_dir, run_cached, scenario

from gridstorm_pypsa import STAGES, ScenarioRejected, run_scenario

AC = "ac-dc-meshed"
SG = "scigrid-de"
P14 = "pglib-case14-ieee"
AC_GAS = ["Manchester Gas", "Norway Gas", "Frankfurt Gas"]
TOL_MW = 1e-3


def _ac_base() -> dict:
    return run_cached("ac-base", scenario(AC, 10, sid="ac-base"), AC)


def _by_id(rows: list[dict]) -> dict[str, dict]:
    return {r["id"]: r for r in rows}


def _arr(x) -> np.ndarray:
    return np.asarray(x, dtype=float)


# --------------------------------------------------------------------------- contract shape


def test_result_validates_against_schema_and_stages_in_order():
    jsonschema = pytest.importorskip("jsonschema")
    stages: list[str] = []
    res = run_scenario(scenario(AC, 3, sid="ac-stages"), network_dir(AC), progress=stages.append)
    assert tuple(stages) == STAGES
    schema = json.loads(RESULT_SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validate(res, schema)
    jsonschema.validate(_ac_base(), schema)
    assert res["outcome"] == "feasible"
    assert res["engine"] == {
        "name": "pypsa",
        "version": res["engine"]["version"],
        "formulation": "lopf",
    }
    assert any("DC linearised" in a for a in res["assumptions"])
    # the ac-dc-meshed CO2 cap belongs to the planning study and is removed, visibly
    assert any("global constraints removed" in a for a in res["assumptions"])
    m = res["manifest"]
    assert m["dataset_sha256"] == stormspec.file_sha256(network_dir(AC) / "network.nc")
    assert m["result_sha256"] == stormspec.result_sha256(res)
    assert {"pypsa", "linopy", "highspy"} <= set(m["package_versions"])


# --------------------------------------------------------------------------- physics


def test_power_balance_residual_is_zero():
    assert _ac_base()["metrics"]["balance_residual_max_mw"] < TOL_MW


def test_generation_within_available_capacity():
    for g in _ac_base()["assets"]["generators"]:
        p, avail = _arr(g["p_mw"]), _arr(g["available_mw"])
        assert (p <= avail + TOL_MW).all(), g["id"]
        assert (p >= -TOL_MW).all(), g["id"]


def test_demand_multiplier_scales_total_load_exactly():
    k = 1.37
    res = run_scenario(
        scenario(AC, 10, [{"type": "demand_multiplier", "value": k}], sid="ac-demand"),
        network_dir(AC),
    )
    base = _ac_base()["metrics"]["total_load_mwh"]
    assert res["metrics"]["total_load_mwh"] == pytest.approx(k * base, rel=1e-9, abs=1e-5)
    assert _arr(res["series"]["load_mw"]) == pytest.approx(
        k * _arr(_ac_base()["series"]["load_mw"]), abs=1e-3
    )
    assert res["metrics"]["balance_residual_max_mw"] < TOL_MW


def test_line_outage_zeroes_flow_and_redistributes():
    base_lines = _by_id(_ac_base()["assets"]["lines"])
    target = max(base_lines, key=lambda i: np.abs(_arr(base_lines[i]["flow_mw"])).max())
    res = run_scenario(
        scenario(AC, 10, [{"type": "line_outage", "asset_id": target}], sid="ac-line-out"),
        network_dir(AC),
    )
    lines = _by_id(res["assets"]["lines"])
    assert lines[target]["outaged"] is True
    assert np.abs(_arr(lines[target]["flow_mw"])).max() == 0.0
    others = [i for i in lines if i != target]
    changed = [
        i
        for i in others
        if np.abs(_arr(lines[i]["flow_mw"]) - _arr(base_lines[i]["flow_mw"])).max() > 1e-3
    ]
    assert changed, "no other line flow changed after the outage"
    assert res["metrics"]["balance_residual_max_mw"] < TOL_MW


def test_link_outage_zeroes_link_flow():
    res = run_scenario(
        scenario(AC, 4, [{"type": "link_outage", "asset_id": "DC link"}], sid="ac-link-out"),
        network_dir(AC),
    )
    link = _by_id(res["assets"]["links"])["DC link"]
    assert link["outaged"] is True and np.abs(_arr(link["flow_mw"])).max() == 0.0


def test_partial_window_branch_outage_is_rejected():
    spec = scenario(
        AC,
        10,
        [{"type": "line_outage", "asset_id": "0", "window": {"start": 2, "end": 5}}],
        sid="ac-partial",
    )
    with pytest.raises(ScenarioRejected) as ei:
        run_scenario(spec, network_dir(AC))
    assert ei.value.code == "unsupported_operation"


def test_unknown_asset_is_rejected():
    spec = scenario(AC, 2, [{"type": "generator_outage", "asset_id": "nope"}], sid="ac-bad-id")
    with pytest.raises(ScenarioRejected) as ei:
        run_scenario(spec, network_dir(AC))
    assert ei.value.code == "unknown_asset"


def _all_gas_out(load_shedding: bool, sid: str) -> dict:
    events = [
        {"type": "generator_outage", "asset_id": g, "window": {"start": 2, "end": 8}}
        for g in AC_GAS
    ]
    spec = scenario(
        AC,
        10,
        events,
        sid=sid,
        mitigation={"load_shedding": {"enabled": load_shedding, "voll_eur_per_mwh": 10000}},
    )
    return run_cached(sid, spec, AC)


def test_unserved_energy_formula_and_generator_outage_window():
    res = _all_gas_out(True, "ac-gas-out")
    m, s = res["metrics"], res["series"]
    w = _arr(res["snapshot_weightings_h"])
    shed = _arr(s["load_shed_mw"])
    assert m["unserved_energy_mwh"] > 0
    assert m["unserved_energy_mwh"] == pytest.approx(float((shed * w).sum()), abs=1e-3)
    assert m["served_load_mwh"] == pytest.approx(m["total_load_mwh"] - m["unserved_energy_mwh"])
    assert m["peak_load_shed_mw"] == pytest.approx(shed.max(), abs=1e-3)
    assert m["load_shed_hours"] == pytest.approx(float(w[shed > 1e-3].sum()))
    # only the outage window sheds load; outaged units produce nothing there
    assert (shed[:2] < TOL_MW).all() and (shed[8:] < TOL_MW).all()
    gens = _by_id(res["assets"]["generators"])
    for g in AC_GAS:
        assert gens[g]["outaged"] is True
        assert np.abs(_arr(gens[g]["p_mw"])[2:8]).max() == 0.0
    # bus-level shedding adds up to the system series
    bus_shed = sum(_arr(b["load_shed_mw"]) for b in res["assets"]["buses"])
    assert bus_shed == pytest.approx(shed, abs=1e-3)
    assert m["load_shedding_cost_eur"] == pytest.approx(10000 * m["unserved_energy_mwh"], rel=1e-6)
    assert m["balance_residual_max_mw"] < TOL_MW


def test_infeasible_without_load_shedding_reports_no_numbers():
    res = _all_gas_out(False, "ac-gas-out-noshed")
    assert res["outcome"] == "infeasible"
    assert res["solver"]["termination_condition"] in {"infeasible", "infeasible_or_unbounded"}
    assert res["solver"]["objective_eur"] is None
    assert res["metrics"] is None and res["series"] is None and res["assets"] is None
    assert any("infeasible" in w for w in res["warnings"])


def test_curtailment_counts_only_variable_generators():
    """Regression: events densify p_max_pu; dispatchable units must not count as curtailable."""
    res = run_scenario(
        scenario(
            AC,
            10,
            [
                {"type": "renewable_availability_multiplier", "carrier": "wind", "value": 0.5},
                {"type": "generator_outage", "asset_id": "Norway Gas"},
            ],
            sid="ac-curtail",
        ),
        network_dir(AC),
    )
    m = res["metrics"]
    assert set(m["curtailment_by_carrier_mwh"]) <= {"wind"}
    w = _arr(res["snapshot_weightings_h"])
    wind = [g for g in res["assets"]["generators"] if g["carrier"] == "wind"]
    wind_avail = sum(_arr(g["available_mw"]) for g in wind)
    wind_p = sum(_arr(g["p_mw"]) for g in wind)
    assert (_arr(res["series"]["curtailment_mw"]) <= wind_avail + TOL_MW).all()
    assert m["curtailment_mwh"] == pytest.approx(float(((wind_avail - wind_p) * w).sum()), abs=1e-2)
    # availability multiplier applied exactly
    base_wind = sum(
        _arr(g["available_mw"])
        for g in _ac_base()["assets"]["generators"]
        if g["carrier"] == "wind"
    )
    assert wind_avail == pytest.approx(0.5 * base_wind, abs=1e-3)


def test_reproducible_objective_and_result_hash():
    spec = scenario(AC, 6, [{"type": "demand_multiplier", "value": 1.1}], sid="ac-repro")
    a = run_scenario(spec, network_dir(AC))
    b = run_scenario(spec, network_dir(AC))
    assert a["solver"]["objective_eur"] == b["solver"]["objective_eur"]
    assert a["manifest"]["result_sha256"] == b["manifest"]["result_sha256"]
    assert a["scenario_hash"] == b["scenario_hash"] == stormspec.scenario_hash(spec)


def test_pglib_setpoints_released_and_generator_outage_sheds_expected_energy():
    base = run_scenario(scenario(P14, 1, sid="p14-base"), network_dir(P14))
    assert base["snapshots"] == ["now"]  # non-temporal label kept verbatim
    assert base["metrics"]["unserved_energy_mwh"] == 0.0
    assert any("set-points (p_set) released" in a for a in base["assumptions"])
    out = run_scenario(
        scenario(P14, 1, [{"type": "generator_outage", "asset_id": "gen-1"}], sid="p14-gen1"),
        network_dir(P14),
    )
    gens = _by_id(out["assets"]["generators"])
    remaining = sum(g["available_mw"][0] for gid, g in gens.items() if gid != "gen-1")
    expected = out["metrics"]["total_load_mwh"] - remaining
    assert out["metrics"]["unserved_energy_mwh"] == pytest.approx(expected, abs=1e-3)


# --------------------------------------------------------------------------- storage (scigrid-de)


@pytest.fixture(scope="module")
def scigrid_storage_run():
    import pypsa

    spec = scenario(
        SG,
        6,
        [
            {"type": "line_outage", "asset_id": "2", "component": "transformer"},
            {"type": "demand_multiplier", "value": 1.1},
        ],
        sid="sg-storage",
    )
    res = run_scenario(spec, network_dir(SG))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        n = pypsa.Network(str(network_dir(SG) / "network.nc"))
    return res, n


def test_transformer_outage_resolves_in_transformer_list(scigrid_storage_run):
    res, n = scigrid_storage_run
    assert res["outcome"] == "feasible"
    assert "2" in n.lines.index and "2" in n.transformers.index  # ids collide across lists
    tr = _by_id(res["assets"]["transformers"])["2"]
    line = _by_id(res["assets"]["lines"])["2"]
    assert tr["outaged"] is True and np.abs(_arr(tr["flow_mw"])).max() == 0.0
    assert line["outaged"] is False
    assert res["metrics"]["balance_residual_max_mw"] < TOL_MW


def test_storage_soc_bounds_and_recursion(scigrid_storage_run):
    res, n = scigrid_storage_run
    su = n.storage_units
    snaps = n.snapshots[:6]
    w = n.snapshot_weightings.stores.reindex(snaps).to_numpy(dtype=float)
    inflow = n.get_switchable_as_dense("StorageUnit", "inflow").reindex(snaps)
    rows = _by_id(res["assets"]["storage_units"])
    assert len(rows) == len(su) > 0
    for sid, r in rows.items():
        e_nom = float(su.at[sid, "p_nom"] * su.at[sid, "max_hours"])
        soc = _arr(r["soc_mwh"])
        disp, store, spill = _arr(r["p_dispatch_mw"]), _arr(r["p_store_mw"]), _arr(r["spill_mw"])
        assert (soc >= -TOL_MW).all() and (soc <= e_nom + TOL_MW).all(), sid
        assert _arr(r["p_mw"]) == pytest.approx(disp - store, abs=1e-3)
        eff_s = float(su.at[sid, "efficiency_store"])
        eff_d = float(su.at[sid, "efficiency_dispatch"])
        loss = float(su.at[sid, "standing_loss"])
        prev = (
            soc[-1]
            if bool(su.at[sid, "cyclic_state_of_charge"])
            else float(su.at[sid, "state_of_charge_initial"])
        )
        for t in range(len(soc)):
            expected = (1 - loss) ** w[t] * prev + w[t] * (
                eff_s * store[t] - disp[t] / eff_d + float(inflow[sid].iloc[t]) - spill[t]
            )
            assert soc[t] == pytest.approx(expected, abs=5e-3), (sid, t)
            prev = soc[t]


# --------------------------------------------------------------------------- CLI


def _cli(tmp_path, spec: dict, network_id: str):
    sp = tmp_path / "s.json"
    sp.write_text(json.dumps(spec), encoding="utf-8")
    out = tmp_path / "r.json"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "gridstorm_pypsa",
            "run",
            "--scenario",
            str(sp),
            "--network-dir",
            str(network_dir(network_id)),
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc, out


def test_cli_writes_result_and_prints_stages(tmp_path):
    proc, out = _cli(tmp_path, scenario(AC, 2, sid="ac-cli"), AC)
    assert proc.returncode == 0, proc.stderr
    stages = [ln.split(" ", 1)[1] for ln in proc.stdout.splitlines() if ln.startswith("STAGE ")]
    assert tuple(stages) == STAGES
    assert json.loads(out.read_text(encoding="utf-8"))["outcome"] == "feasible"


def test_cli_infeasible_exit_zero_and_rejection_exit_two(tmp_path):
    events = [{"type": "generator_outage", "asset_id": g} for g in AC_GAS]
    spec = scenario(
        AC, 2, events, sid="ac-cli-inf", mitigation={"load_shedding": {"enabled": False}}
    )
    proc, out = _cli(tmp_path, spec, AC)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(out.read_text(encoding="utf-8"))["outcome"] == "infeasible"

    bad = scenario(
        AC,
        2,
        [{"type": "line_outage", "asset_id": "0", "window": {"start": 0, "end": 1}}],
        sid="ac-cli-bad",
    )
    (tmp_path / "b").mkdir()
    proc, out2 = _cli(tmp_path / "b", bad, AC)
    assert proc.returncode == 2
    err = json.loads(proc.stderr.strip().splitlines()[-1])
    assert err["error"]["code"] == "unsupported_operation"
    assert not out2.exists()
