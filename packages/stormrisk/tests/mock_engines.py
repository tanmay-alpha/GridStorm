"""Module-level (picklable) mock engines returning minimal gridstorm-result/1.0 documents.

Unserved energy of the toy model (MWh): 10 per outaged line, +5 if generator G1 is out, all
multiplied by the demand multiplier (if any). Both lines out => "infeasible"; generator G3 out
=> the engine raises (classified "error").
"""

from __future__ import annotations


def _outages(scenario):
    return {ev.asset_id for ev in scenario.events if ev.type.endswith("_outage")}


def _demand(scenario):
    d = 1.0
    for ev in scenario.events:
        if ev.type == "demand_multiplier":
            d *= ev.value
    return d


def _result(outcome, unserved=None):
    metrics = (
        {}
        if unserved is None
        else {"unserved_energy_mwh": unserved, "peak_load_shed_mw": unserved / 4}
    )
    return {
        "schema_version": "gridstorm-result/1.0",
        "outcome": outcome,
        "engine": {"name": "mock", "version": "0", "formulation": "lopf"},
        "solver": {
            "name": "mock",
            "version": "0",
            "status": "ok",
            "termination_condition": "optimal" if outcome == "feasible" else outcome,
        },
        "metrics": metrics,
        "warnings": [],
    }


def toy_engine(scenario):
    out = _outages(scenario)
    if {"L1", "L2"} <= out:
        return _result("infeasible")
    if "G3" in out:
        raise RuntimeError("mock solver crash")
    e = 10.0 * len(out & {"L1", "L2"}) + (5.0 if "G1" in out else 0.0)
    return _result("feasible", e * _demand(scenario))


def lines_only_engine(scenario):
    """Feasible everywhere: 10 MWh per outaged line, x demand multiplier."""
    out = _outages(scenario)
    return _result("feasible", 10.0 * len(out) * _demand(scenario))
