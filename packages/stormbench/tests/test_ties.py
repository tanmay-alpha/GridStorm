"""Tie-aware ranking: statistics must not depend on round-off order of (near-)tied severities."""

import json
from pathlib import Path

import numpy as np
import pytest

from stormbench import metrics
from stormbench.bench import _sig

ARTIFACTS = Path(__file__).resolve().parents[3] / "data" / "artifacts" / "stormbench"
RANKED = ("kendall_tau", "spearman", "recall_at_k", "recall_at_10", "k", "tp", "fp", "fn", "tn")


def test_tie_groups_single_linkage_and_order_invariant():
    v = np.array([3.0, 1.0, 1.0 + 4e-7, 2.0, 1.0 + 8e-7, 2.0 + 2e-6])
    # 1, 1+4e-7, 1+8e-7 chain into one group; 2 and 2+2e-6 are separated by more than 1e-6.
    np.testing.assert_array_equal(metrics.tie_groups(v), [3, 0, 0, 1, 0, 2])
    perm = np.random.default_rng(0).permutation(v.size)
    np.testing.assert_array_equal(metrics.tie_groups(v[perm]), metrics.tie_groups(v)[perm])
    s = metrics.tie_summary(v)
    assert (s["tie_groups"], s["tied_pairs"]) == (1, 3)
    assert s["max_group_span_pct"] == pytest.approx(8e-7)
    assert s["tolerance_margin_pct"] == pytest.approx(6e-7)  # gaps 4e-7 -> |4e-7 - 1e-6|
    with pytest.raises(ValueError):
        metrics.tie_groups(np.array([1.0, np.nan]))


def test_hand_case_tau_b_and_average_rank_rho():
    pred = np.array([1.0, 1.0 + 1e-12, 2.0, 3.0])
    true = np.array([1.0 + 5e-13, 1.0, 3.0, 2.0])
    # groups: pred [0, 0, 1, 2], true [0, 0, 2, 1]; C = 4, D = 1, one tie in each vector:
    # tau_b = (4 - 1) / sqrt((6 - 1) * (6 - 1)) = 0.6; average ranks give rho = 3.5 / 4.5.
    r = metrics.rank_agreement(pred, true)
    assert r["kendall_tau"] == pytest.approx(0.6, abs=1e-15)
    assert r["spearman"] == pytest.approx(7 / 9, abs=1e-15)
    # Without tie grouping the 1e-12 round-off decides the order: tau = (4 - 2) / 6.
    raw = metrics.rank_agreement(pred, true, tol=0.0)
    assert raw["kendall_tau"] == pytest.approx(1 / 3, abs=1e-15)


def test_hand_case_recall_at_k_tie_break_by_index():
    pred = np.array([5.0, 5.0 + 1e-9, 3.0, 1.0])
    true = np.array([5.0 + 1e-9, 5.0, 1.0, 3.0])
    assert metrics.recall_at_k(pred, true, 1) == 1.0  # both tops are the tie group {0, 1} -> 0
    assert metrics.recall_at_k(pred, true, 1, tol=0.0) == 0.0
    assert metrics.recall_at_k(pred, true, 3) == pytest.approx(2 / 3)
    np.testing.assert_array_equal(metrics.top_k_order(pred), [0, 1, 2, 3])
    assert metrics.rank_agreement(np.ones(3), np.array([1.0, 2.0, 3.0]))["kendall_tau"] is None
    near_constant = np.array([1.0, 1.0 + 1e-9])
    assert metrics.rank_agreement(near_constant, np.array([1.0, 2.0]))["spearman"] is None


def _clustered(rng: np.random.Generator, n: int) -> tuple[np.ndarray, np.ndarray]:
    """Severities with many exact/near ties (levels >= 0.01 pp apart) and imperfect order."""
    levels = 50.0 + 0.01 * rng.choice(20000, size=40, replace=False)
    idx = rng.integers(0, levels.size, size=n)
    pred = levels[idx]
    swap = rng.permutation(levels.size)[: levels.size // 4]  # reorder a quarter of the levels
    true_levels = levels.copy()
    true_levels[swap] = levels[np.roll(swap, 1)]
    return pred, true_levels[idx] + 0.5  # shift keeps the threshold classification non-trivial


def _ranked(out: dict) -> dict:
    return {k: out[k] for k in RANKED}


def test_invariant_to_round_off_noise_and_near_tie_permutation():
    rng = np.random.default_rng(20261117)
    pred, true = _clustered(rng, 300)
    ref = metrics.compare(pred, true)
    assert ref["ties"]["screening"]["tie_groups"] > 0 and ref["ties"]["reference"]["tied_pairs"] > 0
    raw_taus = set()
    for _ in range(25):
        p = pred + rng.uniform(-1e-12, 1e-12, pred.size)
        t = true + rng.uniform(-1e-12, 1e-12, true.size)
        out = metrics.compare(p, t)
        assert _ranked(out) == _ranked(ref)
        for side in ("screening", "reference"):
            for key in ("tie_groups", "tied_pairs"):
                assert out["ties"][side][key] == ref["ties"][side][key]
        raw_taus.add(metrics.rank_agreement(p, t, tol=0.0)["kendall_tau"])
        # permute the (perturbed) values inside every tie group: equal up to round-off
        for v in (p, t):
            groups = metrics.tie_groups(v)
            for g in np.unique(groups):
                members = np.flatnonzero(groups == g)
                v[members] = v[rng.permutation(members)]
        assert _ranked(metrics.compare(p, t)) == _ranked(ref)
    assert len(raw_taus) > 1  # the untreated statistic really is round-off dependent here


def _rows(case: str) -> list[dict]:
    doc = json.loads((ARTIFACTS / f"stormbench-{case}.json").read_text("utf-8"))
    return doc["payload"]


@pytest.mark.parametrize("case", ["case14-ieee", "case30-ieee"])
def test_committed_screening_vs_dc_rank_agreement_is_exact(case):
    payload = _rows(case)
    rows = [r for r in payload["contingencies"] if not r["islanding"]]
    s = np.array([r["screening_severity_pct"] for r in rows])
    d = np.array([r["dc_exact_severity_pct"] for r in rows])
    r = metrics.rank_agreement(s, d)
    assert r["kendall_tau"] == pytest.approx(1.0, abs=1e-12)
    assert r["spearman"] == pytest.approx(1.0, abs=1e-12)
    assert payload["screening_vs_dc"]["kendall_tau"] == 1.0
    assert payload["screening_vs_dc"]["spearman"] == 1.0
    rng = np.random.default_rng(14 if case == "case14-ieee" else 30)
    for _ in range(10):
        noisy = metrics.rank_agreement(
            s + rng.uniform(-1e-12, 1e-12, s.size), d + rng.uniform(-1e-12, 1e-12, d.size)
        )
        assert noisy == r


@pytest.mark.parametrize(
    "path", sorted(ARTIFACTS.glob("stormbench-case*.json")), ids=lambda p: p.stem
)
def test_committed_aggregates_recompute_from_rows(path):
    payload = json.loads(path.read_text("utf-8"))["payload"]
    rows = [r for r in payload["contingencies"] if not r["islanding"]]
    s = np.array([r["screening_severity_pct"] for r in rows])
    d = np.array([r["dc_exact_severity_pct"] for r in rows])
    assert _sig(metrics.compare(s, d)) == payload["screening_vs_dc"]
    conv = [r for r in rows if r["ac_status"] != "not_converged"]
    s = np.array([r["screening_severity_pct"] for r in conv])
    a = np.array([r["ac_exact_severity_pct"] for r in conv])
    assert _sig(metrics.compare(s, a)) == payload["screening_vs_ac"]
