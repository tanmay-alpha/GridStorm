"""Check the solve-evidence CLI against an independently calculable DC dispatch."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"

import pandas as pd  # noqa: E402
import pypsa  # noqa: E402
import pytest  # noqa: E402

CHECKER = Path(__file__).with_name("solve_check.py")


def network(path: Path, *, feasible: bool) -> None:
    n = pypsa.Network()
    n.set_snapshots(pd.date_range("2020-01-01", periods=2, freq="h"))
    n.snapshot_weightings = pd.DataFrame(
        {column: [2.0, 3.0] for column in n.snapshot_weightings}, index=n.snapshots
    )
    n.add("Bus", "source", v_nom=220)
    n.add("Bus", "sink", v_nom=220)
    n.add("Line", "limited", bus0="source", bus1="sink", x=10, s_nom=60)
    n.add("Generator", "cheap", bus="source", p_nom=200, marginal_cost=10)
    n.add("Generator", "expensive", bus="sink", p_nom=100 if feasible else 0, marginal_cost=50)
    n.add("Load", "demand", bus="sink", p_set=100)
    n.export_to_netcdf(path)


def test_weighted_merit_order_and_nodal_balance(tmp_path: Path) -> None:
    path = tmp_path / "physical.nc"
    network(path, feasible=True)
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--network", str(path)],
        capture_output=True,
        text=True,
        timeout=90,
        check=True,
    )
    report = json.loads(result.stdout)
    # The 60 MW line binds; 40 MW must be generated locally at 50 EUR/MWh.
    assert report["objective_eur"] == pytest.approx((60 * 10 + 40 * 50) * (2 + 3))
    assert report["snapshot_weight_sum_h"] == 5
    assert report["balance_residual_max_mw"] < 1e-6
    assert report["status"] == "ok"
    assert report["termination_condition"] == "optimal"


def test_infeasible_dispatch_is_not_successful_evidence(tmp_path: Path) -> None:
    path = tmp_path / "infeasible.nc"
    network(path, feasible=False)
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--network", str(path)],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode != 0
    assert "LOPF did not solve optimally" in result.stderr
    assert '"objective_eur"' not in result.stdout
