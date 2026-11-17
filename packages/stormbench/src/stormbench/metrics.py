"""Screening-quality metrics: overload classification, confusion counts, ranking agreement.

Definitions (used identically for the DC screening estimate, the exact DC re-solve and the exact AC
re-solve):

* loading of branch k  = 100 * |flow_k| / RATE_A_k   (MW for DC, max end |S| in MVA for AC);
  branches with RATE_A = 0 are unmonitored (MATPOWER convention: 0 = unlimited).
* a contingency l is *overloading* if some monitored branch k != l that is NOT already overloaded in
  the base case of the same model has post-contingency loading > ``threshold`` (default 100 %).
  Base-case overloads are excluded so that a pre-existing violation does not flag every outage.
* severity of l = max post-contingency loading over those same branches (NaN-safe).
* all comparisons against the threshold use a tolerance of ``TOL_PCT`` percentage points: the
  DC-OPF operating point binds limits at exactly 100 %, which round-off would otherwise flag.
* ranking (Kendall tau-b, Spearman rho, recall@k, top-contingency lists) uses the same tolerance:
  severities are grouped into tie groups by single linkage on the sorted values (consecutive sorted
  values within ``TOL_PCT`` share a group), and each value is replaced by its group's dense rank.
  The grouping depends only on the multiset of values, never on input order, so outages whose
  severities are equal in exact arithmetic but differ by round-off (1e-14…1e-11 pp, platform- and
  BLAS-kernel-dependent) cannot change a rank statistic. Within a tie group, top-k selection breaks
  ties by contingency index (source branch order).
"""

from __future__ import annotations

import numpy as np
from scipy import stats

TOL_PCT = 1e-6


def loading_pct(flow: np.ndarray, rate: np.ndarray) -> np.ndarray:
    """Element-wise 100*|flow|/rate; unmonitored (rate <= 0) rows -> 0. Works on 1-D or (m, c)."""
    rate = np.asarray(rate, dtype=float)
    safe = np.where(rate > 0, rate, 1.0)
    scale = np.where(rate > 0, 100.0 / safe, 0.0)
    if np.ndim(flow) == 2:
        return np.abs(flow) * scale[:, None]
    return np.abs(flow) * scale


def contingency_severity(
    post_loading: np.ndarray,
    base_loading: np.ndarray,
    outaged: np.ndarray,
    threshold: float = 100.0,
) -> np.ndarray:
    """Severity per column: max loading over k != outaged[j] with base loading <= threshold.

    ``post_loading`` is (m, c); column j corresponds to the outage of branch ``outaged[j]``.
    """
    mask = (base_loading <= threshold + TOL_PCT)[:, None] & np.ones(post_loading.shape, dtype=bool)
    mask[outaged, np.arange(outaged.shape[0])] = False
    vals = np.where(mask, np.nan_to_num(post_loading, nan=0.0), 0.0)
    return vals.max(axis=0) if vals.shape[0] else np.zeros(post_loading.shape[1])


def confusion(pred: np.ndarray, truth: np.ndarray) -> dict:
    """tp/fp/fn/tn with precision and recall (None when the ratio is 0/0)."""
    pred = np.asarray(pred, dtype=bool)
    truth = np.asarray(truth, dtype=bool)
    tp = int(np.sum(pred & truth))
    fp = int(np.sum(pred & ~truth))
    fn = int(np.sum(~pred & truth))
    tn = int(np.sum(~pred & ~truth))
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
    }


def tie_groups(values: np.ndarray, tol: float = TOL_PCT) -> np.ndarray:
    """Dense tie-group rank per element (0 = smallest group) by single linkage on sorted values.

    Consecutive sorted values whose gap is <= ``tol`` belong to the same group, so the result is
    invariant to the order of the input and to perturbations smaller than half the distance
    between any consecutive gap and ``tol`` (``tie_summary``'s ``tolerance_margin_pct``).
    Values must be finite.
    """
    v = np.asarray(values, dtype=float)
    if not np.all(np.isfinite(v)):
        raise ValueError("tie_groups requires finite values")
    order = np.argsort(v, kind="stable")
    new_group = np.diff(v[order]) > tol
    ranks = np.empty(v.shape[0], dtype=np.int64)
    ranks[order] = np.concatenate(([0], np.cumsum(new_group))) if v.shape[0] else []
    return ranks


def tie_summary(values: np.ndarray, tol: float = TOL_PCT) -> dict:
    """Tie groups (size >= 2), tied pairs, widest group span (chaining) and tolerance margin.

    ``tolerance_margin_pct`` is the smallest |gap - tol| over consecutive sorted values: the
    grouping cannot change unless round-off moves some value by at least half of it.
    """
    v = np.sort(np.asarray(values, dtype=float))
    groups = tie_groups(v, tol)
    sizes = np.bincount(groups) if v.shape[0] else np.zeros(0, dtype=np.int64)
    first = np.concatenate(([0], np.cumsum(sizes)[:-1])) if sizes.shape[0] else sizes
    last = first + sizes - 1
    gaps = np.diff(v)
    return {
        "tie_groups": int(np.sum(sizes > 1)),
        "tied_pairs": int(np.sum(sizes * (sizes - 1) // 2)),
        "max_group_span_pct": float(np.max(v[last] - v[first])) if sizes.shape[0] else None,
        "tolerance_margin_pct": float(np.min(np.abs(gaps - tol))) if gaps.shape[0] else None,
    }


def top_k_order(score: np.ndarray, tol: float = TOL_PCT) -> np.ndarray:
    """Indices by descending tie group of ``score``; ties (within ``tol``) broken by index."""
    groups = tie_groups(score, tol)
    return np.lexsort((np.arange(groups.shape[0]), -groups))


def recall_at_k(
    score_pred: np.ndarray, score_true: np.ndarray, k: int, tol: float = TOL_PCT
) -> float | None:
    """|top-k(pred) ∩ top-k(true)| / k on tie groups (ties within ``tol`` broken by index)."""
    n = score_pred.shape[0]
    k = min(k, n)
    if k <= 0:
        return None
    top_p = set(top_k_order(score_pred, tol)[:k].tolist())
    top_t = set(top_k_order(score_true, tol)[:k].tolist())
    return len(top_p & top_t) / k


def rank_agreement(score_pred: np.ndarray, score_true: np.ndarray, tol: float = TOL_PCT) -> dict:
    """Kendall tau-b and Spearman rho (average ranks) on tie groups within ``tol``.

    None if fewer than 2 points or either vector forms a single tie group (constant).
    """
    if score_pred.shape[0] < 2:
        return {"kendall_tau": None, "spearman": None}
    gp, gt = tie_groups(score_pred, tol), tie_groups(score_true, tol)
    if gp.max() == 0 or gt.max() == 0:
        return {"kendall_tau": None, "spearman": None}
    tau = stats.kendalltau(gp, gt, variant="b").statistic
    rho = stats.spearmanr(gp, gt).statistic
    return {"kendall_tau": float(tau), "spearman": float(rho)}


def compare(sev_pred: np.ndarray, sev_true: np.ndarray, threshold: float = 100.0) -> dict:
    """Full screening-vs-reference comparison on aligned severity vectors."""
    pred = sev_pred > threshold + TOL_PCT
    truth = sev_true > threshold + TOL_PCT
    out = confusion(pred, truth)
    k = max(1, int(truth.sum()))
    out["k"] = k
    out["recall_at_k"] = recall_at_k(sev_pred, sev_true, k)
    out["recall_at_10"] = recall_at_k(sev_pred, sev_true, 10)
    out.update(rank_agreement(sev_pred, sev_true))
    out["n"] = int(sev_pred.shape[0])
    out["ties"] = {
        "tolerance_pct": TOL_PCT,
        "screening": tie_summary(sev_pred),
        "reference": tie_summary(sev_true),
    }
    return out
