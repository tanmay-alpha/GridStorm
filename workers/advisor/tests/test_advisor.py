"""Advisor correctness on a constructed 3-bus network with a known fix.

Topology (110 kV, three identical 10 km lines in a triangle):

    bus-0 (slack, cheap) --line-0 (rated 120 MVA)-- bus-2 (load 150 MW)
       \\                                            /
        line-1 (200 MVA) -- bus-1 (gen-0, 20 MW, expensive) -- line-2 (80 MVA)

Crisis: outage of line-1. The network becomes radial bus-0 - bus-2 - bus-1, so line-0 must carry
load - gen-0 output + losses ~= 132 MW > 120 MVA. Known fix: raise gen-0 by ~15 MW (the slack
backs down). Raising gen-0 by 70 MW also clears line-0 but overloads line-2 (90 MW > 80 MVA).
Opening line-2 would island gen-0, opening line-0 would island the load: no switching candidate.
"""

from __future__ import annotations

import copy
import json
import math

import pandapower as pp
import pytest

from gridstorm_advisor import actions as act
from gridstorm_advisor.advisor import advise, evaluate_actions
from gridstorm_advisor.crisis import Crisis, UnsupportedCrisis, apply_crisis
from gridstorm_advisor.network import from_pandapower
from gridstorm_advisor.state import evaluate_state

RATINGS = {"line-0": 120.0, "line-1": 200.0, "line-2": 80.0}
CRISIS = Crisis("lose-line-1", title="Loss of line-1", line_outages=["line-1"])


def _three_bus():
    net = pp.create_empty_network(sn_mva=100.0)
    for i in range(3):
        pp.create_bus(net, vn_kv=110.0, min_vm_pu=0.9, max_vm_pu=1.1, name=f"b{i}", index=i)
    for i, (f, t) in enumerate([(0, 2), (0, 1), (1, 2)]):
        pp.create_line_from_parameters(
            net,
            f,
            t,
            length_km=10.0,
            r_ohm_per_km=0.06,
            x_ohm_per_km=0.4,
            c_nf_per_km=10.0,
            max_i_ka=1.5,
            index=i,
        )
    pp.create_ext_grid(
        net, 0, vm_pu=1.0, min_p_mw=-500.0, max_p_mw=500.0, min_q_mvar=-300.0, max_q_mvar=300.0
    )
    pp.create_gen(
        net,
        1,
        p_mw=20.0,
        vm_pu=1.0,
        min_p_mw=0.0,
        max_p_mw=100.0,
        min_q_mvar=-100.0,
        max_q_mvar=100.0,
    )
    pp.create_load(net, 2, p_mw=150.0, q_mvar=30.0)
    pp.create_poly_cost(net, 0, "ext_grid", cp1_eur_per_mw=20.0)
    pp.create_poly_cost(net, 0, "gen", cp1_eur_per_mw=40.0)
    return from_pandapower(net, "test-3bus", branch_rating_mva=dict(RATINGS))


@pytest.fixture(scope="module")
def adv():
    return _three_bus()


@pytest.fixture(scope="module")
def payload(adv):
    return advise(adv, CRISIS)


def _independent_loading(adv, crisis, actions) -> dict[str, float]:
    """Re-solve with plain pandapower (no advisor code in the loop) and compute |S|/rating."""
    net = copy.deepcopy(adv.net)
    for bid in crisis.line_outages:
        net.line.at[int(bid.split("-")[1]), "in_service"] = False
    for a in actions:
        if a["type"] == "redispatch":
            assert a["gen_up"] == "gen-0" and a["gen_down"] == "ext_grid-0"
            net.gen.at[0, "p_mw"] += a["delta_mw"]
        elif a["type"] == "load_shed":
            for e in a["loads"]:
                frac = 1.0 - e["shed_mw"] / 150.0
                net.load.at[0, "p_mw"] *= frac
                net.load.at[0, "q_mvar"] *= frac
    pp.runpp(net, calculate_voltage_angles=True, enforce_q_lims=True, tolerance_mva=1e-8)
    out = {}
    for i in net.line.index[net.line.in_service]:
        r = net.res_line.loc[i]
        s = max(math.hypot(r.p_from_mw, r.q_from_mvar), math.hypot(r.p_to_mw, r.q_to_mvar))
        out[f"line-{i}"] = 100.0 * s / RATINGS[f"line-{i}"]
    return out


def test_base_case_is_secure_and_crisis_overloads_line_0(adv):
    base = evaluate_state(adv, adv.copy_net())
    assert base["converged"] and base["violations"] == []
    net, _ = apply_crisis(adv, CRISIS)
    crisis = evaluate_state(adv, net)
    assert crisis["converged"]
    assert [(v["kind"], v["asset_id"]) for v in crisis["violations"]] == [("thermal", "line-0")]
    assert 105.0 < crisis["branch_loading_pct"]["line-0"] < 115.0
    assert adv.net.line.at[1, "in_service"] is not False  # input network never mutated
    assert bool(adv.net.line.at[1, "in_service"])


def test_known_redispatch_fix_is_accepted_and_independently_verified(adv):
    fix = [{"type": "redispatch", "gen_up": "gen-0", "gen_down": "ext_grid-0", "delta_mw": 20.0}]
    row = evaluate_actions(adv, CRISIS, fix)
    assert row["status"] == "accepted", row["rejection_reasons"]
    assert row["violations"]["cleared"] == [["thermal", "line-0"]]
    assert row["violations"]["new"] == []
    loading = _independent_loading(adv, CRISIS, fix)
    assert max(loading.values()) < 100.0
    assert loading["line-0"] == pytest.approx(row["after"]["max_branch_loading_pct"], abs=0.01)


def test_candidate_creating_new_violation_is_rejected(adv):
    over = [{"type": "redispatch", "gen_up": "gen-0", "gen_down": "ext_grid-0", "delta_mw": 70.0}]
    row = evaluate_actions(adv, CRISIS, over)
    assert row["status"] == "rejected"
    assert row["violations"]["cleared"] == [["thermal", "line-0"]]  # original overload cleared...
    assert row["violations"]["new"] == [["thermal", "line-2"]]  # ...but line-2 now overloaded
    assert any(r.startswith("new violation: line-2") for r in row["rejection_reasons"])
    assert _independent_loading(adv, CRISIS, over)["line-2"] > 100.0


def test_insufficient_candidate_is_rejected_with_remaining_violation(adv):
    small = [{"type": "redispatch", "gen_up": "gen-0", "gen_down": "ext_grid-0", "delta_mw": 2.0}]
    row = evaluate_actions(adv, CRISIS, small)
    assert row["status"] == "rejected"
    assert row["violations"]["remaining"] == [["thermal", "line-0"]]


def test_advisor_recommends_minimal_redispatch(adv, payload):
    assert payload["outcome"] == "recommended"
    rec = payload["recommendation"]
    assert [a["type"] for a in rec["actions"]] == ["redispatch"]
    a = rec["actions"][0]
    assert (a["gen_up"], a["gen_down"]) == ("gen-0", "ext_grid-0")
    # AC-sized: just enough to bring line-0 under its rating
    assert 8.0 < a["delta_mw"] < 25.0
    loading = _independent_loading(adv, CRISIS, rec["actions"])
    assert max(loading.values()) <= 100.0 + 1e-6
    assert loading["line-0"] > 97.0  # minimal amount -> close to the limit
    # cheaper than any accepted shedding option (VOLL 10 000 EUR/MWh vs 20 EUR/MWh cost delta)
    accepted = [c for c in payload["candidates"] if c["status"] == "accepted"]
    shed = [c for c in accepted if act.shed_mw(c["actions"]) > 0]
    assert shed, "load shedding at bus-2 should also be an accepted (but costlier) option"
    assert all(c["objective"]["objective_eur"] > rec["objective"]["objective_eur"] for c in shed)


def test_no_islanding_switching_candidates(payload):
    assert not any(a["type"] == "open_branch" for c in payload["candidates"] for a in c["actions"])


def test_every_candidate_has_explanation_and_consistent_status(payload):
    for c in payload["candidates"]:
        assert c["explanation"]
        if c["status"] == "accepted":
            assert c["rejection_reasons"] == [] and c["after"]["n_violations"] == 0
            assert c["rank"] is not None
        else:
            assert c["rejection_reasons"] and c["rank"] is None
    ranks = [c["rank"] for c in payload["candidates"] if c["rank"] is not None]
    assert ranks == list(range(1, len(ranks) + 1))


def test_baselines_and_security_statement(payload):
    assert payload["baselines"]["do_nothing"]["status"] == "rejected"
    prop = payload["baselines"]["proportional_load_shed"]
    assert prop["status"] == "accepted" and prop["objective"]["load_shed_mw"] > 0
    assert "N-1" in payload["security_statement"]
    assert payload["recommendation"]["n_minus_1"]["n_contingencies"] == 2


def test_determinism(adv, payload):
    again = advise(adv, CRISIS)
    assert json.dumps(again, sort_keys=True) == json.dumps(payload, sort_keys=True)


def test_payload_is_json_finite(payload):
    json.dumps(payload, allow_nan=False)


def test_no_violation_crisis_returns_no_action(adv):
    out = advise(adv, Crisis("calm", demand_multiplier=0.5))
    assert out["outcome"] == "no_violation" and out["recommendation"] is None


def test_unknown_assets_and_unsupported_events_are_rejected(adv):
    with pytest.raises(ValueError, match="unknown asset ids"):
        apply_crisis(adv, Crisis("x", line_outages=["line-99"]))
    with pytest.raises(UnsupportedCrisis):
        Crisis.from_stormspec(
            {
                "id": "s",
                "events": [
                    {"type": "line_outage", "asset_id": "line-1", "window": {"start": 0, "end": 2}}
                ],
            }
        )
    with pytest.raises(UnsupportedCrisis):
        Crisis.from_stormspec(
            {
                "id": "s",
                "events": [
                    {"type": "renewable_availability_multiplier", "carrier": "wind", "value": 0.5}
                ],
            }
        )


def test_sensitivity_failure_is_explicit(adv, monkeypatch):
    from gridstorm_advisor import sensitivity

    monkeypatch.setattr(sensitivity, "compute", lambda *_: None)
    result = advise(adv, CRISIS)
    assert result["outcome"] == "no_accepted_candidate"
    assert result["candidate_generation"]["status"] == "unavailable"
    assert "not establish" in result["candidate_generation"]["warnings"][0]
    assert result["baselines"]["proportional_load_shed"]["after"]["converged"]


def test_stormspec_outage_component_defaults_to_line_and_is_checked(adv):
    event = {"type": "line_outage", "asset_id": "line-1"}
    crisis = Crisis.from_stormspec({"id": "typed", "events": [event]})
    assert crisis.outage_components == {"line-1": "line"}
    assert not apply_crisis(adv, crisis)[0].line.at[1, "in_service"]
    wrong = Crisis.from_stormspec(
        {
            "id": "wrong",
            "events": [{**event, "component": "transformer"}],
        }
    )
    with pytest.raises(ValueError, match="is a line, not a transformer"):
        apply_crisis(adv, wrong)
    assert Crisis.from_dict(crisis.to_dict()) == crisis


def test_islanded_load_is_an_explicit_violation(adv):
    net = adv.copy_net()
    net.line.loc[[0, 2], "in_service"] = False
    state = evaluate_state(adv, net)
    assert state["islanded_load_mw"] > 0
    assert any(v["kind"] == "islanded_load" for v in state["violations"])
