"""Physical integration oracle: fixed supply deficit and snapshot-hour weighting."""

from __future__ import annotations

import pandas as pd
import pypsa
import pytest
from gridstorm_pypsa import network_index, run_scenario
from stormspec import Scenario

from stormrisk import SamplingSpec, run_study


def test_real_engine_weighted_energy_and_outage_probability(tmp_path):
    network_dir = tmp_path / "weighted-system"
    network_dir.mkdir()
    n = pypsa.Network()
    n.set_snapshots(pd.date_range("2020-01-01", periods=2, freq="h"))
    n.snapshot_weightings.loc[n.snapshots[1], :] = 3.0
    n.add("Carrier", "gas")
    n.add("Bus", "bus", carrier="AC")
    n.add("Generator", "supply", bus="bus", carrier="gas", p_nom=60, marginal_cost=10)
    n.add("Load", "demand", bus="bus", p_set=100)
    n.export_to_netcdf(network_dir / "network.nc")
    base = Scenario.model_validate({
        "id": "weighted-deficit",
        "name": "Known supply deficit",
        "dataset": {"network_id": network_dir.name},
        "horizon": {"start": 0, "snapshots": 2},
        "events": [],
        "mitigation": {"load_shedding": {"enabled": True, "voll_eur_per_mwh": 10000}},
        "execution": {"engine": "pypsa", "formulation": "lopf", "solver": "highs",
                      "solver_options": {"threads": 1}, "deterministic": True},
    })
    spec = SamplingSpec.model_validate({
        "n_samples": 200, "seed": 321,
        "outage_classes": [{"name": "supply", "component": "generator",
                            "unavailability": 0.25, "source": "synthetic integration fixture"}],
    })
    results = []

    def engine(scenario):
        result = run_scenario(scenario, network_dir)
        results.append(result)
        return result

    study = run_study(base, spec, network_index(n, network_dir.name), engine)
    assert study["runtime"]["solves"] == 2
    assert study["sample_accounting"]["n_feasible_samples"] == 200
    n_out = 0
    for state in study["states"]:
        # Without outage: (100 - 60) MW * (1 + 3) h = 160 MWh.
        # With outage: 100 MW * (1 + 3) h = 400 MWh.
        expected = 400.0 if state["outages"] else 160.0
        assert state["unserved_energy_mwh"] == pytest.approx(expected, abs=1e-6)
        if state["outages"]:
            n_out += state["count"]
    assert study["estimates"]["eens_mwh"] == pytest.approx(160 + 240 * n_out / 200)
    assert study["estimates"]["lolp"] == 1.0
    # Independent analytical ensemble target: .75*160 + .25*400 = 220 MWh.
    assert abs(study["estimates"]["eens_mwh"] - 220) < 4 * study["estimates"]["se_eens_mwh"]
    for result in results:
        assert result["metrics"]["balance_residual_max_mw"] < 1e-6
        assert result["metrics"]["served_load_mwh"] + result["metrics"]["unserved_energy_mwh"] == pytest.approx(400)
