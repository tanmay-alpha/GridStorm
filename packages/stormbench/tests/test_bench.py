import numpy as np
import pytest

from stormbench.bench import _sig, quiet, run_case
from stormbench.metrics import compare


@pytest.mark.slow
def test_case14_end_to_end():
    quiet()
    p = run_case("case14_ieee", repeats=1, memory=False, log=lambda *_: None)
    v = p["validation"]
    assert v["ptdf_max_abs_diff_vs_pandapower"] < 1e-9
    assert v["lodf_max_abs_diff_vs_pandapower"] < 1e-9
    assert v["lodf_vs_dc_resolve_max_abs_mw"] < 1e-6
    assert p["counts"]["screened"] + p["counts"]["islanding"] == p["counts"]["contingencies"]
    assert p["ac"]["not_converged"] == 0
    rows = p["contingencies"]
    assert len(rows) == p["counts"]["contingencies"]
    screened = [r for r in rows if not r["islanding"]]
    assert all(r["screening_severity_pct"] is None for r in rows if r["islanding"])
    prediction = np.array([r["screening_severity_pct"] for r in screened])
    exact = np.array([r["dc_exact_severity_pct"] for r in screened])
    assert _sig(compare(prediction, exact)) == p["screening_vs_dc"]
    converged = [r for r in screened if r["ac_status"] != "not_converged"]
    prediction = np.array([r["screening_severity_pct"] for r in converged])
    exact = np.array([r["ac_exact_severity_pct"] for r in converged])
    assert _sig(compare(prediction, exact)) == p["screening_vs_ac"]
