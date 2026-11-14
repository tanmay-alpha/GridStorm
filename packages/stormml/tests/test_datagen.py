import copy

import numpy as np

from stormml.cases import PD, PG, QD, RATE_A, VG, VMAX, branch_flows, build_pp_net, parse_matpower
from stormml.datagen import (
    DISPATCH_LIMIT_RANGE,
    LABEL_NAMES,
    STATUS_OK,
    STATUS_OPF_FAILED,
    TOL_PCT,
    Dataset,
    PreparedNetwork,
    _runpp,
    dispatch_ac_opf,
    dispatch_settings,
    label_case,
    label_operating_point,
    sample_operating_point,
)
from stormml.dc import sensitivities, topology


def prepared(case):
    return PreparedNetwork(case.name, case.name, case, [], sensitivities(case), topology(case))


def test_sampler_deterministic_constant_power_factor_and_cost_scaling(triangle):
    a, fa, alpha_a = sample_operating_point(triangle, 42, "triangle")
    b, fb, alpha_b = sample_operating_point(triangle, 42, "triangle")
    c, _, _ = sample_operating_point(triangle, 43, "triangle")
    np.testing.assert_array_equal(a.bus, b.bus)
    np.testing.assert_array_equal(a.gencost, b.gencost)
    assert (fa, alpha_a) == (fb, alpha_b)
    assert 0.8 <= fa <= 1.2
    assert DISPATCH_LIMIT_RANGE[0] <= alpha_a <= DISPATCH_LIMIT_RANGE[1]
    assert not np.array_equal(a.bus[:, PD], c.bus[:, PD])
    np.testing.assert_allclose(a.bus[1:, QD] / a.bus[1:, PD], [0.2, 1 / 6])
    # Cost perturbation is a positive per-generator factor; the reference case is untouched.
    factor = a.gencost[0, 5] / triangle.gencost[0, 5]
    assert factor > 0
    np.testing.assert_allclose(a.gencost[0, 4:], triangle.gencost[0, 4:] * factor)
    np.testing.assert_array_equal(triangle.bus[:, PD], [0, 50, 30])
    np.testing.assert_array_equal(triangle.gencost[0], [2, 0, 0, 3, 0, 10, 0])


def test_dispatch_settings_start_with_sampled_margin():
    assert dispatch_settings(0.85) == [
        (0.85, 0.01),
        (0.85, 0.0),
        (0.9, 0.0),
        (0.95, 0.0),
        (1.0, 0.0),
    ]
    assert dispatch_settings(0.97) == [(0.97, 0.01), (0.97, 0.0), (1.0, 0.0)]


def test_opf_enforces_apparent_power_limit_with_margin(congested_triangle):
    case = congested_triangle
    alpha, margin = 0.9, 0.01
    result = dispatch_ac_opf(case, alpha, margin)
    assert result is not None
    dispatched, q_outside = result
    assert q_outside == 0
    # The expensive unit is only dispatched because the cheap one is branch-limited.
    assert dispatched.gen[1, PG] > 1.0
    net, bmap = build_pp_net(dispatched)
    assert _runpp(net)
    _, smva = branch_flows(net, bmap)
    loading = smva / case.branch[:, RATE_A] * 100
    # MVA (not current) limit: a current limit would admit up to VMAX = 1.1 times the rating.
    assert loading.max() <= alpha * 100 + TOL_PCT
    assert loading.max() >= alpha * 100 - 0.5
    vm = net.res_bus.vm_pu.to_numpy()
    assert vm.max() <= case.bus[0, VMAX] - margin + 1e-4
    np.testing.assert_allclose(dispatched.gen[:, VG], vm[[0, 2]], atol=1e-6)
    # AC balance: generation = demand + series losses (no shunts in this case).
    gen_mw = net.res_ext_grid.p_mw.sum() + net.res_gen.p_mw.sum()
    np.testing.assert_allclose(
        gen_mw - net.res_load.p_mw.sum(), net.res_line.pl_mw.sum(), atol=1e-6
    )


def test_ac_labels_repeat_and_respect_line_limits(triangle):
    prep = prepared(triangle)
    a = label_operating_point(prep, 42)
    b = label_operating_point(prep, 42)
    assert a.ok and b.ok and a.status == STATUS_OK
    np.testing.assert_array_equal(a.labels, b.labels)
    np.testing.assert_allclose(a.features, b.features, rtol=0, atol=1e-12)
    assert a.base_thermal_violations == 0 and a.base_voltage_violations == 0
    assert a.base_max_loading_pct < 100
    # 50 MW + 30 MW over one remaining 100 MVA branch per outage: no absolute violation.
    assert not a.labels[:, LABEL_NAMES.index("label")].any()


def test_absolute_label_retains_existing_violation_and_insecure_base_is_rejected(triangle):
    case = copy.deepcopy(triangle)
    case.name = "triangle-with-overloaded-tail"
    case.branch[:, 5:8] = 200
    case.bus = np.vstack([case.bus, [4, 1, 5, 0, 0, 0, 1, 1, 0, 110, 1, 1.2, 0.8]])
    case.branch = np.vstack([case.branch, [3, 4, 0.005, 0.05, 0, 1, 1, 1, 0, 0, 1, -360, 360]])
    prep = prepared(case)
    # The 5 MW tail cannot be served through a 1 MVA branch: no N-0 secure dispatch exists.
    assert label_operating_point(prep, 42).status == STATUS_OPF_FAILED
    result = label_case(prep, case, 1.0, require_secure_base=False)
    assert result.ok
    assert result.base_thermal_violations == 1
    # Ring outages leave the pre-existing 1 MVA tail overloaded without aggravating it by 5 pp:
    # the primary absolute label is positive, the secondary incremental label is not.
    assert result.labels[0, LABEL_NAMES.index("thermal")] == 1
    assert result.labels[0, LABEL_NAMES.index("label")] == 1
    assert result.labels[0, LABEL_NAMES.index("aggravated")] == 0
    # Outaging the tail disconnects real demand; preserve MW rather than inventing non-convergence.
    assert result.labels[3, LABEL_NAMES.index("islanding")] == 1
    np.testing.assert_allclose(result.lost_load_mw[3], 5.0)
    assert result.labels[3, LABEL_NAMES.index("nonconv")] == 0
    rejected = label_case(prep, case, 1.0, require_secure_base=True)
    assert not rejected.ok and rejected.labels is None


def test_matpower_numeric_reader(tmp_path):
    source = tmp_path / "tiny.m"
    source.write_text("""function mpc = tiny
mpc.baseMVA = 100;
mpc.bus = [1 3 0 0 0 0 1 1 0 110 1 1.1 0.9; % reference
2 1 20 5 0 0 1 1 0 110 1 1.1 0.9];
mpc.gen = [1 20 0 100 -100 1 100 1 100 0];
mpc.branch = [1 2 0.01 0.1 0 100 100 100 0 0 1 -360 360];
mpc.gencost = [2 0 0 3 0.01 20 0];
""")
    case = parse_matpower(source)
    assert case.base_mva == 100
    np.testing.assert_array_equal(case.bus[:, PD], [0, 20])
    np.testing.assert_array_equal(case.gencost, [[2, 0, 0, 3, 0.01, 20, 0]])
    assert len(case.source_sha256) == 64
    net, mapping = build_pp_net(case)
    assert _runpp(net)
    assert len(branch_flows(net, mapping)[0]) == 1


def test_dataset_roundtrip(tmp_path):
    ds = Dataset(
        np.array([[1.0, 2.0], [3.0, 4.0]]),
        np.zeros((2, len(LABEL_NAMES)), dtype=np.uint8),
        np.array(["triangle"] * 2),
        np.array(["triangle/42"] * 2),
        np.array([42, 42]),
        np.array([0, 1]),
        np.array([0.0, 5.0]),
        ("a", "b"),
    )
    path = tmp_path / "dataset.npz"
    ds.save(path)
    actual = Dataset.load(path)
    np.testing.assert_array_equal(actual.X, ds.X)
    np.testing.assert_array_equal(actual.lost_load_mw, ds.lost_load_mw)
    assert actual.feature_names == ds.feature_names
