import numpy as np
import pytest

from stormml import metrics as m
from stormml.splits import (
    LeakageError,
    Split,
    check_no_leakage,
    leave_network_out_split,
    operating_point_split,
)


def test_hand_computed_ranking_metrics():
    y = np.array([1, 0, 1, 0])
    s = np.array([.9, .8, .7, .1])
    assert m.pr_auc(y, s) == pytest.approx(5 / 6)
    assert m.roc_auc(y, s) == pytest.approx(.75)
    assert m.recall_at_precision(y, s, .9) == pytest.approx(.5)
    assert m.recall_at_precision(y, s, .6) == pytest.approx(1)
    assert m.best_f1_threshold(y, s) == pytest.approx(.7)
    assert m.recall_at_k(y, s, np.array(["a", "a", "b", "b"]), 1) == 1
    stats = m.precision_recall_at(y, s >= .7)
    assert stats["precision"] == pytest.approx(2 / 3)
    assert stats["recall"] == 1
    assert stats["f1"] == pytest.approx(.8)
    assert np.isnan(m.roc_auc(np.ones(4), s))
    assert np.isnan(m.pr_auc(np.zeros(4), s))


def test_tie_order_and_calibration():
    np.testing.assert_array_equal(
        m.ranks_within_groups(np.array([1., 1., 2., 2.]), np.array(["b", "b", "a", "a"])),
        [0, 1, 0, 1],
    )
    y, p = np.array([0, 1]), np.array([.2, .8])
    assert m.brier(y, p) == pytest.approx(.04)
    bins = m.calibration_bins(y, p, n_bins=2)
    assert bins["ece"] == pytest.approx(.2)
    assert [b["n"] for b in bins["bins"]] == [1, 1]
    assert bins["bins"][0]["frac_pos"] == 0
    assert bins["bins"][1]["frac_pos"] == 1


def test_cluster_bootstrap_keeps_operating_points_together():
    groups = np.array(["a", "a", "b", "b", "b", "c"])
    a = m.cluster_bootstrap_indices(groups, 20, 17)
    b = m.cluster_bootstrap_indices(groups, 20, 17)
    for first, second in zip(a, b, strict=True):
        np.testing.assert_array_equal(first, second)
        counts = np.bincount(first, minlength=len(groups))
        for group in np.unique(groups):
            # Every row of a drawn operating point appears the same number of times.
            assert np.unique(counts[groups == group]).size == 1
    assert m.percentile_ci([0, 1, 2, 3, 4], alpha=.5) == (1, 3)
    assert all(np.isnan(v) for v in m.percentile_ci([np.nan]))


def test_operating_point_and_network_splits_are_disjoint():
    networks = np.repeat(["a", "a", "b", "b"], 2)
    seeds = np.repeat([1_000_000, 2_000_000, 1_000_000, 2_000_000], 2)
    ops = np.array([f"{net}/{seed}" for net, seed in zip(networks, seeds, strict=True)])
    split = operating_point_split(seeds, ops)
    np.testing.assert_array_equal(split.train, [0, 1, 4, 5])
    np.testing.assert_array_equal(split.test, [2, 3, 6, 7])
    held = leave_network_out_split(networks, ops, "b")
    assert set(networks[held.train]) == {"a"}
    assert set(networks[held.test]) == {"b"}
    with pytest.raises(LeakageError, match="operating points"):
        check_no_leakage(Split("bad", np.array([0]), np.array([1])), ops)
    with pytest.raises(LeakageError, match="rows shared"):
        check_no_leakage(Split("bad", np.array([0]), np.array([0])), ops)
    with pytest.raises(ValueError, match="no rows"):
        leave_network_out_split(networks, ops, "missing")
