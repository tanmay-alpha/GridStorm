import numpy as np
import pytest

from stormml.cases import BR_X, F_BUS, RATE_A, T_BUS
from stormml.dc import dc_post_contingency_loading, sensitivities, topology
from stormml.features import FEATURE_NAMES, compute_features


def direct_dc(case, injections, removed=None):
    """Independent reduced Laplacian solution, without PTDF/LODF code."""
    n = len(case.bus)
    rows = np.array([i for i in range(len(case.branch)) if i != removed])
    incidence = np.zeros((len(rows), n))
    for k, row in enumerate(rows):
        incidence[k, int(case.branch[row, F_BUS]) - 1] = 1
        incidence[k, int(case.branch[row, T_BUS]) - 1] = -1
    b = 1 / case.branch[rows, BR_X]
    laplacian = incidence.T @ np.diag(b) @ incidence
    angles = np.r_[0, np.linalg.solve(laplacian[1:, 1:], injections[1:] / case.base_mva)]
    flow = np.zeros(len(case.branch))
    flow[rows] = b * (incidence @ angles) * case.base_mva
    return flow


def test_lodf_matches_independent_outage_solutions(triangle):
    injections = np.array([80.0, -50.0, -30.0])
    sens = sensitivities(triangle)
    base = direct_dc(triangle, injections)
    np.testing.assert_allclose(base, [130 / 3, -20 / 3, -110 / 3])
    np.testing.assert_allclose(sens.ptdf @ injections, base)
    assert not sens.islanding.any()
    for out in range(3):
        predicted = base + sens.lodf[:, out] * base[out]
        np.testing.assert_allclose(predicted, direct_dc(triangle, injections, out), atol=1e-12)
        # Sum injections is zero and the outaged branch carries no active flow.
        assert predicted[out] == pytest.approx(0)
    loading = dc_post_contingency_loading(base, triangle.branch[:, RATE_A], sens.lodf)
    np.testing.assert_allclose(loading[:, 0], [0, 50, 80])


def test_features_have_physical_values(triangle):
    base = direct_dc(triangle, np.array([80.0, -50.0, -30.0]))
    x = compute_features(
        triangle,
        sensitivities(triangle),
        topology(triangle),
        p_from_mw=base,
        q_from_mvar=np.zeros(3),
        s_max_mva=np.abs(base),
        vm_pu=np.ones(3),
        load_factor=1,
    )
    col = {name: x[:, i] for i, name in enumerate(FEATURE_NAMES)}
    np.testing.assert_allclose(col["dc_score"][0], 80)
    np.testing.assert_allclose(col["pre_load"], np.abs(base))
    assert col["nbr_load_mean"][0] == pytest.approx(65 / 3)
    np.testing.assert_allclose(col["deg_min"], 2)
    np.testing.assert_allclose(col["vm_margin_end"], 0.2)
    assert not col["is_bridge"].any()
    assert np.isfinite(x).all()


def test_parallel_branches_not_falsely_marked_bridges(triangle):
    triangle.branch = triangle.branch[[0, 0, 1]].copy()
    topo = topology(triangle)
    sens = sensitivities(triangle)
    np.testing.assert_array_equal(topo.is_bridge, [False, False, True])
    np.testing.assert_array_equal(sens.islanding, [False, False, True])
    assert np.isnan(sens.lodf[:, 2]).all()
    np.testing.assert_allclose(sens.lodf[1, 0], 1)
