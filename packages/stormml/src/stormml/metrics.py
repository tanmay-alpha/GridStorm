"""Screening metrics and operating-point (cluster) bootstrap confidence intervals."""

from __future__ import annotations

import numpy as np
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score


def pr_auc(y: np.ndarray, s: np.ndarray) -> float:
    return float(average_precision_score(y, s)) if 0 < y.sum() < y.size else float("nan")


def roc_auc(y: np.ndarray, s: np.ndarray) -> float:
    return float(roc_auc_score(y, s)) if 0 < y.sum() < y.size else float("nan")


def recall_at_precision(y: np.ndarray, s: np.ndarray, min_precision: float) -> float:
    """Largest recall over thresholds whose precision is >= ``min_precision`` (0 if none)."""
    if y.sum() == 0:
        return float("nan")
    prec, rec, _ = precision_recall_curve(y, s)
    ok = prec >= min_precision
    return float(rec[ok].max()) if ok.any() else 0.0


def ranks_within_groups(s: np.ndarray, groups: np.ndarray) -> np.ndarray:
    """0-based rank of each row inside its group, by descending score (ties: lower row first)."""
    order = np.lexsort((np.arange(s.size), -s, groups))
    g_sorted = groups[order]
    starts = np.r_[0, np.flatnonzero(g_sorted[1:] != g_sorted[:-1]) + 1]
    pos = np.arange(s.size) - np.repeat(starts, np.diff(np.r_[starts, s.size]))
    ranks = np.empty(s.size, dtype=np.int64)
    ranks[order] = pos
    return ranks


def recall_at_k(y: np.ndarray, s: np.ndarray, groups: np.ndarray, k: int) -> float:
    """Share of all positives that fall in the top-``k`` contingencies of their operating point."""
    if y.sum() == 0:
        return float("nan")
    r = ranks_within_groups(s, groups)
    return float(y[r < k].sum() / y.sum())


def precision_recall_at(y: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    tp = float((pred & (y == 1)).sum())
    fp = float((pred & (y == 0)).sum())
    fn = float((~pred & (y == 1)).sum())
    p = tp / (tp + fp) if tp + fp else float("nan")
    r = tp / (tp + fn) if tp + fn else float("nan")
    f1 = 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else float("nan")
    return {"precision": p, "recall": r, "f1": f1, "flagged_share": float(pred.mean())}


def best_f1_threshold(y: np.ndarray, s: np.ndarray) -> float:
    """Threshold ``t`` maximising F1 of ``s >= t`` (ties: the highest threshold)."""
    prec, rec, thr = precision_recall_curve(y, s)
    with np.errstate(invalid="ignore", divide="ignore"):
        f1 = np.where(prec + rec > 0, 2 * prec * rec / (prec + rec), 0.0)[:-1]
    best = np.flatnonzero(f1 == f1.max())
    return float(thr[best[-1]])


def brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def calibration_bins(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> dict:
    """Equal-width reliability bins and the expected calibration error (ECE)."""
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, n_bins - 1)
    bins = []
    ece = 0.0
    for b in range(n_bins):
        sel = idx == b
        n = int(sel.sum())
        if n == 0:
            bins.append({"lo": edges[b], "hi": edges[b + 1], "n": 0})
            continue
        mp, fy = float(p[sel].mean()), float(y[sel].mean())
        ece += n / y.size * abs(mp - fy)
        bins.append({"lo": edges[b], "hi": edges[b + 1], "n": n, "mean_pred": mp, "frac_pos": fy})
    return {"ece": float(ece), "bins": bins}


def cluster_bootstrap_indices(groups: np.ndarray, n_boot: int, seed: int) -> list[np.ndarray]:
    """Row-index resamples drawing whole groups (operating points) with replacement.

    Resampling operating points, not rows, respects the within-operating-point correlation of
    contingency labels. The same resamples are reused for every model (paired comparison).
    """
    uniq, inv = np.unique(groups, return_inverse=True)
    order = np.argsort(inv, kind="stable")
    bounds = np.r_[0, np.cumsum(np.bincount(inv, minlength=uniq.size))]
    members = [order[bounds[i] : bounds[i + 1]] for i in range(uniq.size)]
    rng = np.random.default_rng(seed)
    return [
        np.concatenate([members[i] for i in rng.integers(0, uniq.size, uniq.size)])
        for _ in range(n_boot)
    ]


def percentile_ci(values, alpha: float = 0.05) -> tuple[float, float]:
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return float("nan"), float("nan")
    lo, hi = np.quantile(v, [alpha / 2, 1 - alpha / 2])
    return float(lo), float(hi)
