from __future__ import annotations

import json
import os

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"

import numpy as np
import pandapower as pp
import pytest
from pypower.api import ext2int, makeYbus
from stormspec import Scenario, payload_sha256

from gridstorm_pandapower import ScenarioRejected, run_scenario
from gridstorm_pandapower.contingency import (
    contingency_study,
    energised_buses,
    run_outage,
    total_load_mw,
)
from gridstorm_pandapower.model import (
    REFERENCE_DATA,
    BranchRef,
    GenRef,
    GridModel,
    load_matpower,
    resolve_case_file,
)
from gridstorm_pandapower.powerflow import power_balance, run_pf
from gridstorm_pandapower.reference import CASES, reference_payload
from gridstorm_pandapower.studies import REPO_ROOT


@pytest.fixture(scope="module")
def reference():
    return reference_payload()


def test_reference_voltage_angles_flows_and_balance(reference):
    assert reference["summary"]["all_pass"], reference
    assert reference["matpower_testsuite"]["pass"]
    assert len(reference["matpower_cases"]) == 6
    assert len(reference["pandapower_builtin"]) == 6
    assert reference["summary"]["max_abs_balance_residual_mw"] < 1e-6


@pytest.mark.parametrize("case", ["case118", "case300"])
def test_converted_admittance_matrix_equals_matpower(case):
    # case300 has transformers whose tap (F_BUS) is on the lower-voltage side; the converted
    # pandapower model must reproduce MATPOWER's bus admittance matrix exactly.
    model = load_matpower(REFERENCE_DATA / "matpower" / f"{case}.m", case)
    assert run_pf(model.net, init="flat").converged
    internal = ext2int({k: model.ppc[k] for k in ("baseMVA", "bus", "gen", "branch")})
    y_ref = makeYbus(internal["baseMVA"], internal["bus"], internal["branch"])[0].toarray()
    lookup = model.net._pd2ppc_lookups["bus"]
    order = np.array([lookup[b] for b in model.ppc["bus"][:, 0].astype(int)])
    y_pp = model.net._ppc["internal"]["Ybus"].toarray()[np.ix_(order, order)]
    assert np.max(np.abs(y_ref - y_pp)) < 1e-9


@pytest.mark.parametrize("case", CASES)
def test_id_map_round_trip(case):
    model = load_matpower(REFERENCE_DATA / "matpower" / f"{case}.m", case)
    for branch in model.branches:
        assert model.branch(branch.id, branch.component) is branch
        assert model.branch_for_element(branch.table, branch.index) is branch
    for gen in model.gens:
        assert model.gen(gen.id) is gen
        assert model.gen_for_element(gen.table, gen.index) is gen
    for bus in model.buses:
        assert model.bus_id(model.bus_index(bus)) == bus
    for load, index in model.loads.items():
        assert model.load_id_for_index(index) == load
    assert len(model.branches) == len(model.ppc["branch"])
    assert len(model.gens) == len(model.ppc["gen"])
    transformer = next((b for b in model.branches if b.component == "transformer"), None)
    if transformer is not None:
        with pytest.raises(KeyError):
            model.branch(transformer.id)  # default line lookup never crosses component types


@pytest.fixture
def tiny():
    net = pp.create_empty_network(sn_mva=100)
    for index in (1, 2, 3):
        pp.create_bus(net, vn_kv=110, index=index)
    eg = pp.create_ext_grid(net, bus=1)
    loads = {
        "load-2": pp.create_load(net, 2, p_mw=10, q_mvar=1),
        "load-3": pp.create_load(net, 3, p_mw=2, q_mvar=0.2),
    }
    branches = []
    for k, (start, end, rate) in enumerate(((1, 2, 8), (1, 2, 8), (2, 3, 100)), 1):
        index = pp.create_line_from_parameters(
            net,
            start,
            end,
            length_km=1,
            r_ohm_per_km=0.05,
            x_ohm_per_km=0.1,
            c_nf_per_km=0,
            max_i_ka=1,
        )
        branches.append(
            BranchRef(f"branch-{k}", "line", "line", index, f"bus-{start}", f"bus-{end}", rate)
        )
    model = GridModel(
        "tiny-test",
        net,
        {},
        None,
        ["bus-1", "bus-2", "bus-3"],
        branches,
        [GenRef("gen-1", "ext_grid", eg, "bus-1")],
        loads,
        {f"bus-{i}": (0.94, 1.06) for i in (1, 2, 3)},
        "test limits",
    )
    assert run_pf(net).converged
    return model


def test_known_islanding_and_overload_and_copy_isolation(tiny):
    study = contingency_study(tiny, n2_top_k=3)
    rows = {row["outage"][0]["id"]: row for row in study["contingencies"]}
    assert rows["branch-3"]["class"] == "islanding"
    assert rows["branch-3"]["islanded_buses"] == ["bus-3"]
    assert rows["branch-3"]["islanded_load_mw"] == pytest.approx(2)
    assert rows["branch-1"]["class"] == "thermal_overload"
    assert rows["branch-1"]["overloads"][0]["id"] == "branch-2"
    assert rows["branch-1"]["overloads"][0]["loading_pct"] > 150
    assert study["n_minus_2"]["pair_count"] == 3
    assert sum(study["summary"]["class_counts"].values()) == 3
    assert tiny.net.line.in_service.all()
    assert abs(power_balance(tiny.net)["residual_mw"]) < 1e-6


def test_isolated_slack_moves_reference_to_main_island():
    # bus-1 (slack, no load) --branch-1-- bus-2 (PV gen, 60 MW max 200) --branch-2-- bus-3 (load)
    net = pp.create_empty_network(sn_mva=100)
    for index in (1, 2, 3):
        pp.create_bus(net, vn_kv=110, index=index)
    eg = pp.create_ext_grid(net, bus=1)
    gen = pp.create_gen(net, 2, p_mw=60, vm_pu=1.0, max_p_mw=200)
    load = pp.create_load(net, 3, p_mw=100, q_mvar=10)
    branches = []
    for k, (start, end) in enumerate(((1, 2), (2, 3)), 1):
        index = pp.create_line_from_parameters(
            net,
            start,
            end,
            length_km=1,
            r_ohm_per_km=0.05,
            x_ohm_per_km=0.1,
            c_nf_per_km=0,
            max_i_ka=1,
        )
        branches.append(
            BranchRef(f"branch-{k}", "line", "line", index, f"bus-{start}", f"bus-{end}", 500)
        )
    gens = [GenRef("gen-1", "ext_grid", eg, "bus-1"), GenRef("gen-2", "gen", gen, "bus-2")]
    model = GridModel(
        "slack-test",
        net,
        {},
        None,
        ["bus-1", "bus-2", "bus-3"],
        branches,
        gens,
        {"load-3": load},
        {f"bus-{i}": (0.9, 1.1) for i in (1, 2, 3)},
        "test",
    )
    assert run_pf(net).converged
    slack_p = float(net.res_ext_grid.p_mw.iloc[0])
    assert slack_p > 39  # 100 MW load + losses - 60 MW from gen-2
    row = run_outage(
        model, (branches[0],), total_load=total_load_mw(net), base_energised=energised_buses(net)
    )
    assert row["class"] == "islanding"
    assert row["islanded_buses"] == ["bus-1"]
    assert row["islanded_load_mw"] == 0
    assert row["islanded_generation_mw"] == pytest.approx(slack_p, abs=1e-3)
    info = row["slack_reassignment"]
    assert info["new_slack"] == "gen-2" and info["stranded_slack"] == ["gen-1"]
    # the new slack now serves the whole 100 MW load plus branch-2 losses
    assert 100 < info["new_slack_p_mw"] < 101
    assert info["new_slack_exceeds_pmax"] is False
    assert net.ext_grid.in_service.all() and not net.gen.slack.any()  # base net untouched
    assert row["slack_excess_mw"] == 0
    assert row["severity"] == 0  # no load lost, no overload, new slack within Pmax
    # A new slack limited to 80 MW cannot serve 100 MW: the shortfall enters the severity.
    net.gen.max_p_mw = 80.0
    short = run_outage(
        model, (branches[0],), total_load=total_load_mw(net), base_energised=energised_buses(net)
    )
    assert short["slack_reassignment"]["new_slack_exceeds_pmax"] is True
    excess = short["slack_reassignment"]["new_slack_p_mw"] - 80.0
    assert short["slack_excess_mw"] == pytest.approx(excess, abs=1e-3)
    assert short["severity"] == pytest.approx(100.0 * excess / 100.0, rel=1e-4)


def test_secure_and_voltage_violation_classes(tiny):
    tiny.net.load[["p_mw", "q_mvar"]] *= 0.1
    assert run_pf(tiny.net).converged
    kwargs = {"total_load": total_load_mw(tiny.net), "base_energised": energised_buses(tiny.net)}
    secure = run_outage(tiny, (tiny.branches[0],), **kwargs)
    assert secure["class"] == "secure"
    assert secure["severity"] == 0
    tiny.net.ext_grid.vm_pu = 1.08
    assert run_pf(tiny.net).converged
    violation = run_outage(tiny, (tiny.branches[0],), **kwargs)
    assert violation["class"] == "voltage_violation"
    assert violation["voltage_violations"]


def test_solver_errors_classified(tiny, monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError("deliberate solver-interface error")

    monkeypatch.setattr(pp, "runpp", fail)
    row = run_outage(
        tiny,
        (tiny.branches[0],),
        total_load=total_load_mw(tiny.net),
        base_energised=energised_buses(tiny.net),
    )
    assert row["class"] == "error"
    assert "deliberate solver-interface error" in row["message"]
    assert row["severity"] is None


def test_real_non_convergence_classification(tiny):
    # Deliberately infeasible load increase on a previously solved network; no solver mock.
    base_energised = energised_buses(tiny.net)
    tiny.net.load.p_mw *= 1e6
    row = run_outage(
        tiny, (tiny.branches[0],), total_load=total_load_mw(tiny.net), base_energised=base_energised
    )
    assert row["class"] == "non_convergent", row
    assert not row["converged"]
    assert row["severity"] is None


def scenario(events=None, formulation="ac_pf"):
    return {
        "id": "ac-test",
        "name": "AC adapter regression",
        "dataset": {"network_id": "pglib-case14-ieee"},
        "horizon": {"snapshots": 1},
        "events": events or [],
        "mitigation": {
            "storage_dispatch": False,
            "curtailment": False,
            "load_shedding": {"enabled": False},
        },
        "execution": {"engine": "pandapower", "formulation": formulation, "solver": "nr"},
    }


@pytest.mark.parametrize(
    "event",
    [
        {"type": "link_outage", "asset_id": "branch-1"},
        {"type": "storage_state", "asset_id": "battery", "initial_soc_fraction": 0.5},
        {"type": "renewable_availability_multiplier", "carrier": "wind", "value": 0.5},
        {"type": "demand_multiplier", "value": 1.1, "window": {"start": 0, "end": 1}},
    ],
)
def test_unsupported_events_rejected_before_loading(event, tmp_path):
    with pytest.raises(ScenarioRejected) as exc:
        run_scenario(scenario([event]), tmp_path)
    assert exc.value.code == "unsupported_operation"


def test_unsupported_formulation_and_mitigation(tmp_path):
    for spec in (scenario(formulation="lopf"), scenario()):
        if spec["execution"]["formulation"] == "ac_pf":
            spec["mitigation"]["load_shedding"]["enabled"] = True
        with pytest.raises(ScenarioRejected) as exc:
            run_scenario(spec, tmp_path)
        assert exc.value.code == "unsupported_operation"


def test_adapter_events_and_ac_metrics():
    network_dir = REPO_ROOT / "data/networks/pglib-case14-ieee"
    model = load_matpower(resolve_case_file("pglib-case14-ieee", network_dir), "pglib-case14-ieee")
    transformer = next(b for b in model.branches if b.component == "transformer")
    spec = scenario(
        [
            {"type": "line_outage", "asset_id": transformer.id, "component": "transformer"},
            {"type": "generator_outage", "asset_id": "gen-2"},
            {"type": "demand_multiplier", "buses": ["bus-2"], "value": 1.01},
        ]
    )
    stages = []
    result = run_scenario(Scenario.model_validate(spec), network_dir, progress=stages.append)
    assert result["outcome"] == "feasible", result
    assert result["ac"]["converged"]
    assert result["metrics"]["balance_residual_max_mw"] < 1e-6
    assert len(result["assets"]["buses"]) == 14
    assert all("vm_pu" in bus and "va_deg" in bus for bus in result["assets"]["buses"])
    assert next(g for g in result["assets"]["generators"] if g["id"] == "gen-2")["outaged"]
    assert next(t for t in result["assets"]["transformers"] if t["id"] == transformer.id)["outaged"]
    assert stages == [
        "loading_network",
        "applying_scenario",
        "building_model",
        "solving",
        "postprocessing",
        "done",
    ]
    json.dumps(result, allow_nan=False)


def test_n1_adapter():
    result = run_scenario(
        scenario(formulation="n_minus_1"), REPO_ROOT / "data/networks/pglib-case14-ieee"
    )
    assert result["outcome"] == "feasible"
    assert result["contingency"]["summary"]["contingency_count"] == 20


def test_committed_artifact_integrity():
    root = REPO_ROOT / "data/artifacts/pandapower"
    entries = json.loads((root / "index.json").read_text(encoding="utf-8"))["artifacts"]
    assert {e["network_id"] for e in entries} >= {"pglib-case14-ieee", "pglib-case118-ieee"}
    for entry in entries:
        path = root / f"{entry['artifact_id']}.json"
        assert path.stat().st_size < 5_000_000
        artifact = json.loads(path.read_text(encoding="utf-8"))
        assert artifact["artifact"]["payload_sha256"] == payload_sha256(artifact["payload"])
        if entry["kind"] == "n_minus_1":
            summary = artifact["payload"]["summary"]
            assert sum(summary["class_counts"].values()) == summary["contingency_count"]
            assert summary["class_counts"]["error"] == 0
