import copy

import numpy as np

from stormml.cases import PD, QD, RATE_A, branch_flows, build_pp_net, parse_matpower
from stormml.datagen import (
    LABEL_NAMES,
    Dataset,
    PreparedNetwork,
    _runpp,
    label_operating_point,
    sample_operating_point,
)
from stormml.dc import sensitivities, topology


def prepared(case):
    return PreparedNetwork(
        case.name, case.name, case, "synthetic test circuit", [], sensitivities(case), topology(case)
    )


def test_sampler_deterministic_and_constant_power_factor(triangle):
    a, fa = sample_operating_point(triangle, 42, "triangle")
    b, fb = sample_operating_point(triangle, 42, "triangle")
    c, _ = sample_operating_point(triangle, 43, "triangle")
    np.testing.assert_array_equal(a.bus, b.bus)
    np.testing.assert_array_equal(a.gen, b.gen)
    assert fa == fb
    assert .8 <= fa <= 1.2
    assert not np.array_equal(a.bus[:, PD], c.bus[:, PD])
    np.testing.assert_allclose(a.bus[1:, QD] / a.bus[1:, PD], [.2, 1 / 6])
    np.testing.assert_array_equal(triangle.bus[:, PD], [0, 50, 30])


def test_ac_labels_repeat_and_respect_line_limits(triangle):
    prep = prepared(triangle)
    a = label_operating_point(prep, 42)
    b = label_operating_point(prep, 42)
    assert a.ok and b.ok
    np.testing.assert_array_equal(a.labels, b.labels)
    np.testing.assert_allclose(a.features, b.features, rtol=0, atol=1e-12)
    assert not a.labels[:, LABEL_NAMES.index("label")].any()
    assert a.base_thermal_violations == 0
    # Actual AC branch powers include losses; physical balance is checked, not just labels.
    net, bmap = build_pp_net(triangle)
    assert _runpp(net)
    _, smva = branch_flows(net, bmap)
    assert np.all(smva < triangle.branch[:, RATE_A])
    generation = net.res_ext_grid.p_mw.sum()
    demand = net.res_load.p_mw.sum()
    losses = net.res_line.pl_mw.sum()
    assert generation > demand
    np.testing.assert_allclose(generation - demand, losses, atol=1e-6)


def test_absolute_label_retains_existing_violation(triangle):
    case = copy.deepcopy(triangle)
    case.name = "triangle-with-overloaded-tail"
    case.branch[:, 5:8] = 200
    case.bus = np.vstack([case.bus, [4, 1, 5, 0, 0, 0, 1, 1, 0, 110, 1, 1.2, .8]])
    case.branch = np.vstack([
        case.branch, [3, 4, .005, .05, 0, 1, 1, 1, 0, 0, 1, -360, 360]
    ])
    result = label_operating_point(prepared(case), 42)
    assert result.ok
    assert result.base_thermal_violations == 1
    # Ring outages leave the pre-existing 1 MVA tail overloaded without aggravating it by 5 pp.
    assert result.labels[0, LABEL_NAMES.index("thermal")] == 1
    assert result.labels[0, LABEL_NAMES.index("label")] == 1
    assert result.labels[0, LABEL_NAMES.index("aggravated")] == 0
    # Outaging the tail disconnects real demand; preserve MW rather than inventing non-convergence.
    assert result.labels[3, LABEL_NAMES.index("islanding")] == 1
    assert result.lost_load_mw[3] > 0
    assert result.labels[3, LABEL_NAMES.index("nonconv")] == 0


def test_matpower_numeric_reader(tmp_path):
    source = tmp_path / "tiny.m"
    source.write_text("""function mpc = tiny
mpc.baseMVA = 100;
mpc.bus = [1 3 0 0 0 0 1 1 0 110 1 1.1 0.9; % reference
2 1 20 5 0 0 1 1 0 110 1 1.1 0.9];
mpc.gen = [1 20 0 100 -100 1 100 1 100 0];
mpc.branch = [1 2 0.01 0.1 0 100 100 100 0 0 1 -360 360];
""")
    case = parse_matpower(source)
    assert case.base_mva == 100
    np.testing.assert_array_equal(case.bus[:, PD], [0, 20])
    assert len(case.source_sha256) == 64
    net, mapping = build_pp_net(case)
    assert _runpp(net)
    assert len(branch_flows(net, mapping)[0]) == 1


def test_dataset_roundtrip(tmp_path):
    ds = Dataset(
        np.array([[1., 2.], [3., 4.]]), np.zeros((2, len(LABEL_NAMES)), dtype=np.uint8),
        np.array(["triangle"] * 2), np.array(["triangle/42"] * 2), np.array([42, 42]),
        np.array([0, 1]), np.array([0., 5.]), ("a", "b"),
    )
    path = tmp_path / "dataset.npz"
    ds.save(path)
    actual = Dataset.load(path)
    np.testing.assert_array_equal(actual.X, ds.X)
    np.testing.assert_array_equal(actual.lost_load_mw, ds.lost_load_mw)
    assert actual.feature_names == ds.feature_names
