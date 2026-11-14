import numpy as np
import pytest

from stormbench import metrics


def test_loading_pct_unmonitored_zero():
    ld = metrics.loading_pct(np.array([50.0, -30.0, 10.0]), np.array([100.0, 20.0, 0.0]))
    np.testing.assert_allclose(ld, [50.0, 150.0, 0.0])


def test_severity_excludes_outaged_and_base_overloads():
    post = np.array([[0.0, 120.0], [130.0, 0.0], [150.0, 160.0]])
    base = np.array([50.0, 60.0, 101.0])  # branch 2 already overloaded
    sev = metrics.contingency_severity(post, base, np.array([0, 1]))
    np.testing.assert_allclose(sev, [130.0, 120.0])


def test_confusion_and_ratios():
    c = metrics.confusion(np.array([1, 1, 0, 0], bool), np.array([1, 0, 1, 0], bool))
    assert (c["tp"], c["fp"], c["fn"], c["tn"]) == (1, 1, 1, 1)
    assert c["precision"] == 0.5 and c["recall"] == 0.5
    empty = metrics.confusion(np.zeros(3, bool), np.zeros(3, bool))
    assert empty["precision"] is None and empty["recall"] is None


def test_recall_at_k():
    pred = np.array([0.9, 0.8, 0.1, 0.5])
    true = np.array([0.95, 0.1, 0.9, 0.2])
    assert metrics.recall_at_k(pred, true, 2) == 0.5
    assert metrics.recall_at_k(pred, true, 4) == 1.0


def test_rank_agreement():
    a = np.array([1.0, 2.0, 3.0, 4.0])
    r = metrics.rank_agreement(a, a)
    assert r["kendall_tau"] == pytest.approx(1.0) and r["spearman"] == pytest.approx(1.0)
    r = metrics.rank_agreement(a, -a)
    assert r["kendall_tau"] == pytest.approx(-1.0)
    assert metrics.rank_agreement(a, np.ones(4))["kendall_tau"] is None


def test_compare_threshold_tolerance():
    out = metrics.compare(np.array([100.0 + 1e-9, 101.0]), np.array([99.0, 102.0]))
    assert out["tp"] == 1 and out["fp"] == 0 and out["recall"] == 1.0
