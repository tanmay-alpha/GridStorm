import pytest

from stormbench.bench import quiet, run_case


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
