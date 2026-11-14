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


def recall_at_k(score_pred: np.ndarray, score_true: np.ndarray, k: int) -> float | None:
    """|top-k(pred) ∩ top-k(true)| / k (stable sort, ties broken by index)."""
    n = score_pred.shape[0]
    k = min(k, n)
    if k <= 0:
        return None
    top_p = set(np.argsort(-score_pred, kind="stable")[:k].tolist())
    top_t = set(np.argsort(-score_true, kind="stable")[:k].tolist())
    return len(top_p & top_t) / k


def rank_agreement(score_pred: np.ndarray, score_true: np.ndarray) -> dict:
    """Kendall tau-b and Spearman rho (None if fewer than 2 points or a constant vector)."""
    if score_pred.shape[0] < 2 or np.ptp(score_pred) == 0 or np.ptp(score_true) == 0:
        return {"kendall_tau": None, "spearman": None}
    tau = stats.kendalltau(score_pred, score_true).statistic
    rho = stats.spearmanr(score_pred, score_true).statistic
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
    return out
