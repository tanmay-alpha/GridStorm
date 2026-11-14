from __future__ import annotations

import pydantic
import pytest
from mock_engines import lines_only_engine, toy_engine
from stormspec import Scenario

from stormrisk import (
    SamplingSpec,
    StudyInputError,
    draw_samples,
    prepare_study,
    resolve_population,
    run_study,
)
from stormrisk.artifact import build_artifact, round_floats

SRC = "test value"


def _spec(**kw) -> SamplingSpec:
    doc = {
        "n_samples": 400,
        "seed": 11,
        "outage_classes": [
            {"name": "lines", "component": "line", "unavailability": 0.2, "source": SRC},
            {"name": "thermal", "component": "generator", "carriers": ["gas", "oil"],
             "unavailability": 0.1, "source": SRC},
        ],
    }
    doc.update(kw)
    return SamplingSpec.model_validate(doc)


# --- sampling -----------------------------------------------------------------------------


def test_population_resolution(toy_network, base_scenario):
    pop = resolve_population(base_scenario, _spec(), toy_network)
    assert [(a.component, a.asset_id) for a in pop.assets] == [
        ("generator", "G1"), ("generator", "G3"), ("line", "L1"), ("line", "L2")]
    assert pop.class_counts == {"lines": 2, "thermal": 2}


def test_determinism_same_seed_identical_samples(toy_network, base_scenario):
    spec = _spec(demand_multiplier={"kind": "truncated_normal", "mean": 1.0, "std": 0.1,
                                    "lower": 0.8, "upper": 1.2, "resolution": 0.05,
                                    "source": SRC})
    pop = resolve_population(base_scenario, spec, toy_network)
    a, b = draw_samples(pop, spec), draw_samples(pop, spec)
    assert a == b
    c = draw_samples(pop, spec.model_copy(update={"seed": 12}))
    assert c.sample_state_index != a.sample_state_index or c.states != a.states
    r1 = run_study(base_scenario, spec, toy_network, toy_engine)
    r2 = run_study(base_scenario, spec, toy_network, toy_engine)
    for key in ("estimates", "convergence", "importance", "sample_state_index",
                "sample_accounting"):
        assert r1[key] == r2[key]
    assert [s["state_hash"] for s in r1["states"]] == [s["state_hash"] for s in r2["states"]]


def test_demand_quantised_and_within_bounds(toy_network, base_scenario):
    spec = _spec(demand_multiplier={"kind": "truncated_normal", "mean": 1.0, "std": 0.3,
                                    "lower": 0.9, "upper": 1.1, "resolution": 0.05,
                                    "source": SRC})
    pop = resolve_population(base_scenario, spec, toy_network)
    s = draw_samples(pop, spec)
    vals = {st.demand_multiplier for st in s.states}
    assert vals <= {0.9, 0.95, 1.0, 1.05, 1.1}


def test_collapse_identical_states_and_frequency_weights(toy_network, base_scenario):
    calls = []

    def counting(scen):
        calls.append(scen)
        return lines_only_engine(scen)

    spec = _spec(n_samples=1000)
    r = run_study(base_scenario, spec, toy_network, counting)
    acc = r["sample_accounting"]
    assert acc["n_distinct_states"] == len(calls) == r["runtime"]["solves"] <= 16
    assert sum(s["count"] for s in r["states"]) == acc["n_samples"] == 1000
    assert len(r["sample_state_index"]) == 1000
    assert len({s["state_hash"] for s in r["states"]}) == acc["n_distinct_states"]
    assert len({c.id for c in calls}) == len(calls)


def test_empirical_outage_frequencies_match_unavailability(toy_network, base_scenario):
    spec = _spec(n_samples=20000)
    pop, samples = prepare_study(base_scenario, spec, toy_network)
    for i, asset in enumerate(pop.assets):
        k = sum(c for st, c in zip(samples.states, samples.counts, strict=True)
                if i in st.outage_idx)
        q = asset.unavailability
        sd = (q * (1 - q) / spec.n_samples) ** 0.5
        assert abs(k / spec.n_samples - q) < 5 * sd


def test_probability_normalisation_rejected():
    with pytest.raises(pydantic.ValidationError):
        _spec(demand_multiplier={"kind": "discrete", "values": [1.0, 1.2],
                                 "probabilities": [0.5, 0.6], "source": SRC})
    with pytest.raises(pydantic.ValidationError):
        _spec(outage_classes=[{"name": "x", "component": "line", "unavailability": 1.0,
                               "source": SRC}])


def test_mc_eens_agrees_with_exact_enumeration(toy_network, base_scenario):
    # Independent lines q1 = 0.2, q2 = 0.3; engine: 10 MWh per outaged line, x demand.
    # Exact EENS = 10 (0.2 + 0.3) * E[d] = 5 * (0.5 * 1.0 + 0.5 * 1.2) = 5.5 MWh.
    spec = SamplingSpec.model_validate({
        "n_samples": 4000, "seed": 7,
        "outage_classes": [
            {"name": "l1", "component": "line", "asset_ids": ["L1"], "unavailability": 0.2,
             "source": SRC},
            {"name": "l2", "component": "line", "asset_ids": ["L2"], "unavailability": 0.3,
             "source": SRC}],
        "demand_multiplier": {"kind": "discrete", "values": [1.0, 1.2],
                              "probabilities": [0.5, 0.5], "source": SRC},
    })
    r = run_study(base_scenario, spec, toy_network, lines_only_engine)
    e = r["estimates"]
    assert e["basis"] == "all_samples"
    assert r["sample_accounting"]["n_distinct_states"] == 8
    assert abs(e["eens_mwh"] - 5.5) < 4 * e["se_eens_mwh"]
    exact_lolp = 1 - 0.8 * 0.7
    assert abs(e["lolp"] - exact_lolp) < 4 * e["se_lolp"]
    assert r["convergence"][-1]["eens_mwh"] == pytest.approx(e["eens_mwh"])
    assert r["convergence"][-1]["n"] == 4000


# --- infeasible / error accounting -------------------------------------------------------


def test_infeasible_and_error_samples_counted_not_dropped(toy_network, base_scenario):
    spec = _spec(n_samples=2000, seed=5)
    r = run_study(base_scenario, spec, toy_network, toy_engine)
    acc = r["sample_accounting"]
    assert acc["n_infeasible_samples"] > 0  # both lines out (p = 0.04)
    assert acc["n_error_samples"] > 0  # G3 out (p = 0.1) -> engine raises
    assert (acc["n_feasible_samples"] + acc["n_infeasible_samples"] + acc["n_error_samples"]
            + acc["n_invalid_samples"]) == 2000
    e = r["estimates"]
    assert e["basis"] == "feasible_samples_only"
    assert e["n_samples"] == acc["n_feasible_samples"]
    assert e["eens_lower_bound_all_samples_mwh"] == pytest.approx(
        e["eens_mwh"] * acc["n_feasible_samples"] / 2000)
    assert any("no unserved-energy value" in w for w in r["warnings"])
    errs = [s for s in r["states"] if s["outcome"] == "error"]
    assert errs and all("mock solver crash" in s["error"] for s in errs)
    assert all(s["unserved_energy_mwh"] is None for s in r["states"]
               if s["outcome"] != "feasible")


@pytest.mark.parametrize("result", [None, [], {"outcome": "feasible", "metrics": []},
                                   {"outcome": "feasible", "metrics": {"unserved_energy_mwh": 3},
                                    "solver": "broken"}])
def test_malformed_result_is_accounted_as_error(toy_network, base_scenario, result):
    r = run_study(base_scenario, _spec(n_samples=20), toy_network, lambda _: result)
    assert r["sample_accounting"]["n_error_samples"] == 20
    assert all(s["unserved_energy_mwh"] is None for s in r["states"])
    assert "eens_mwh" not in r["estimates"]

def test_invalid_states_classified(toy_network, base_scenario):
    spec = _spec(n_samples=300, seed=2, max_outages_per_sample=1)
    r = run_study(base_scenario, spec, toy_network, lines_only_engine)
    acc = r["sample_accounting"]
    assert acc["n_invalid_samples"] > 0
    assert all(s["outcome"] == "invalid" for s in r["states"] if len(s["outages"]) > 1)


def test_engine_rejection_classified_invalid(toy_network, base_scenario):
    from stormrisk import EngineRejected

    def rejecting(scen):
        if any(ev.type == "generator_outage" for ev in scen.events):
            raise EngineRejected("unsupported_operation: committable generator")
        return lines_only_engine(scen)

    r = run_study(base_scenario, _spec(n_samples=300, seed=4), toy_network, rejecting)
    acc = r["sample_accounting"]
    assert acc["n_invalid_samples"] > 0 and acc["n_error_samples"] == 0
    assert all(s["outcome"] == "invalid" for s in r["states"]
               if any(o[0] == "generator" for o in s["outages"]))


def test_parallel_matches_serial(toy_network, base_scenario):
    spec = _spec(n_samples=300, seed=3)
    serial = run_study(base_scenario, spec, toy_network, toy_engine)
    parallel = run_study(base_scenario, spec, toy_network, toy_engine, workers=2)
    for key in ("estimates", "sample_accounting", "sample_state_index", "importance"):
        assert serial[key] == parallel[key]


# --- input errors ---------------------------------------------------------------------------


def test_input_errors(toy_network, base_scenario):
    overlap = _spec(outage_classes=[
        {"name": "a", "component": "line", "unavailability": 0.1, "source": SRC},
        {"name": "b", "component": "line", "asset_ids": ["L1"], "unavailability": 0.1,
         "source": SRC}])
    with pytest.raises(StudyInputError, match="matches outage classes"):
        prepare_study(base_scenario, overlap, toy_network)
    nomatch = _spec(outage_classes=[{"name": "c", "component": "generator",
                                     "carriers": ["nuclear"], "unavailability": 0.1,
                                     "source": SRC}])
    with pytest.raises(StudyInputError, match="matches no asset"):
        prepare_study(base_scenario, nomatch, toy_network)
    unknown = _spec(outage_classes=[{"name": "c", "component": "line", "asset_ids": ["L9"],
                                     "unavailability": 0.1, "source": SRC}])
    with pytest.raises(StudyInputError, match="unknown"):
        prepare_study(base_scenario, unknown, toy_network)
    no_shed = Scenario.model_validate(
        base_scenario.model_dump() | {"mitigation": {"load_shedding": {"enabled": False}}})
    with pytest.raises(StudyInputError, match="load shedding"):
        prepare_study(no_shed, _spec(), toy_network)
    with_dm = Scenario.model_validate(
        base_scenario.model_dump() | {"events": [{"type": "demand_multiplier", "value": 1.1}]})
    with pytest.raises(StudyInputError, match="ambiguous"):
        prepare_study(with_dm, _spec(demand_multiplier={
            "kind": "discrete", "values": [1.0], "probabilities": [1.0], "source": SRC}),
            toy_network)
    wrong_net = Scenario.model_validate(
        base_scenario.model_dump() | {"dataset": {"network_id": "other-net"}})
    with pytest.raises(StudyInputError, match="network_mismatch"):
        prepare_study(wrong_net, _spec(), toy_network)


@pytest.mark.parametrize("workers", [0, -1, True, 1.5])
def test_invalid_worker_count_rejected(toy_network, base_scenario, workers):
    with pytest.raises(StudyInputError, match="workers must be a positive integer"):
        run_study(base_scenario, _spec(n_samples=20), toy_network, toy_engine, workers=workers)


def test_base_outaged_assets_excluded(toy_network, base_scenario):
    base = Scenario.model_validate(
        base_scenario.model_dump() | {"events": [{"type": "line_outage", "asset_id": "L1"}]})
    pop = resolve_population(base, _spec(), toy_network)
    assert pop.excluded_base_outaged == (("line", "L1"),)
    assert "L1" not in {a.asset_id for a in pop.assets}


def test_ids_colliding_across_components(toy_network, base_scenario):
    """Ids are unique only per component type (contract §3, e.g. SciGRID line/transformer "5")."""
    net = dict(toy_network)
    net["lines"] = toy_network["lines"] + [{"id": "5", "bus0": "b1", "bus1": "b2",
                                            "carrier": "AC"}]
    net["transformers"] = [{"id": "5", "bus0": "b1", "bus1": "b2"}]
    spec = _spec(outage_classes=[
        {"name": "lines", "component": "line", "unavailability": 0.3, "source": SRC},
        {"name": "trafos", "component": "transformer", "unavailability": 0.5, "source": SRC},
    ])
    # A base transformer outage "5" excludes only the transformer, not line "5".
    base = Scenario.model_validate(base_scenario.model_dump() | {"events": [
        {"type": "line_outage", "asset_id": "5", "component": "transformer"}]})
    pop = resolve_population(base, spec, net)
    assert pop.excluded_base_outaged == (("transformer", "5"),)
    assert ("line", "5") in {(a.component, a.asset_id) for a in pop.assets}
    # Sampled transformer outages are emitted with component "transformer".
    pop = resolve_population(base_scenario, spec, net)
    trafo = next(i for i, a in enumerate(pop.assets) if a.component == "transformer")
    line5 = next(i for i, a in enumerate(pop.assets)
                 if a.component == "line" and a.asset_id == "5")
    from stormrisk.sampling import SampledState, state_scenario

    for idx in ((trafo,), (line5,), tuple(sorted((trafo, line5)))):
        state = SampledState(idx, None)
        scen = state_scenario(base_scenario, state, pop, state.key(pop))
        got = {(ev.component, ev.asset_id) for ev in scen.events if ev.type == "line_outage"}
        assert got == {(pop.assets[i].component, "5") for i in idx}
    assert SampledState((trafo,), None).key(pop) != SampledState((line5,), None).key(pop)


# --- artifact -------------------------------------------------------------------------------


def test_artifact_envelope(toy_network, base_scenario, tmp_path):
    from stormspec import payload_sha256

    from stormrisk.artifact import write_artifact

    r = run_study(base_scenario, _spec(n_samples=50), toy_network, lines_only_engine)
    art = build_artifact(r, artifact_id="toy-study", network_id="toy-net",
                         engine_version="0", command="pytest", inputs=[])
    assert art["artifact"]["payload_sha256"] == payload_sha256(art["payload"])
    assert art["artifact"]["kind"] == "risk"
    path = write_artifact(art, tmp_path, title="toy")
    assert path.exists() and (tmp_path / "index.json").exists()
    assert round_floats(1.23456789, 4) == 1.235
    est = art["payload"]["estimates"]
    assert est["metric"] == "EENS" and est["probability_model"]["provenance"] == "modeled"
    # per-state results are single deterministic runs: never labelled EENS
    assert all("eens_mwh" not in s and "metric" not in s for s in art["payload"]["states"])
