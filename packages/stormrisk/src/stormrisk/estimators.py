"""Crude Monte Carlo estimators over frequency-weighted distinct states.

Notation: ``N`` i.i.d. samples, distinct states ``s`` with counts ``c_s`` (``sum c_s = N``) and
unserved energy ``y_s`` [MWh]. With ``p_s = c_s / N``:

* EENS        = sum_s p_s y_s                       (via :func:`stormspec.eens`)
* sample var  S^2 = sum_s c_s (y_s - EENS)^2 / (N - 1)
* SE(EENS)    = S / sqrt(N);  95 % CI = EENS +/- z_{0.975} SE   (normal approximation / CLT)
* CV          = SE / EENS   (coefficient of variation of the estimator; undefined if EENS = 0)
* LOLP        = sum_s p_s 1[y_s > tol];  SE(LOLP) = sqrt(LOLP (1 - LOLP) / N)
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from stormspec import eens as stormspec_eens

Z_975 = 1.959963984540054


def mc_statistics(
    values: Sequence[float], counts: Sequence[int], *, tol: float = 1e-6
) -> dict[str, float | int | None]:
    """Point estimates and CLT uncertainty for frequency-weighted samples of unserved energy."""
    y = np.asarray(values, dtype=float)
    c = np.asarray(counts, dtype=np.int64)
    if y.shape != c.shape or y.ndim != 1 or y.size == 0:
        raise ValueError("values and counts must be equal-length non-empty 1-D sequences")
    if (c <= 0).any():
        raise ValueError("counts must be positive")
    if not np.isfinite(y).all() or (y < 0).any():
        raise ValueError("unserved energies must be finite and >= 0")
    n = int(c.sum())
    p = c / n
    eens = stormspec_eens(zip(p.tolist(), y.tolist(), strict=True))
    if n > 1:
        var = float(np.sum(c * (y - eens) ** 2) / (n - 1))
    else:
        var = float("nan")
    std = math.sqrt(var) if n > 1 else None
    se = std / math.sqrt(n) if std is not None else None
    shed = y > tol
    n_shed = int(c[shed].sum())
    lolp = n_shed / n
    expanded = np.repeat(y, c)
    return {
        "n_samples": n,
        "eens_mwh": eens,
        "std_unserved_mwh": std,
        "se_eens_mwh": se,
        "ci95_low_mwh": None if se is None else max(0.0, eens - Z_975 * se),
        "ci95_high_mwh": None if se is None else eens + Z_975 * se,
        "cv_eens": None if (se is None or eens == 0.0) else se / eens,
        "lolp": lolp,
        "se_lolp": math.sqrt(lolp * (1.0 - lolp) / n),
        "n_loss_of_load_samples": n_shed,
        "mean_unserved_given_shed_mwh": (float(np.sum(c[shed] * y[shed]) / n_shed)
                                         if n_shed else None),
        "p95_unserved_mwh": float(np.percentile(expanded, 95)),
        "max_unserved_mwh": float(y.max()),
    }


def convergence_trace(sequence: Sequence[float], *, max_points: int = 120) -> list[dict]:
    """Running EENS and 95 % CI half-width after k samples (draw order), at <= max_points k's."""
    y = np.asarray(sequence, dtype=float)
    n = y.size
    if n == 0:
        return []
    ks = np.unique(np.round(np.geomspace(1, n, num=min(max_points, n))).astype(int))
    s1 = np.cumsum(y)
    s2 = np.cumsum(y * y)
    out = []
    for k in ks:
        mean = s1[k - 1] / k
        if k > 1:
            var = max(0.0, (s2[k - 1] - k * mean * mean) / (k - 1))
            half = Z_975 * math.sqrt(var / k)
        else:
            half = None
        out.append({"n": int(k), "eens_mwh": float(mean), "ci95_half_width_mwh": half})
    return out


def importance_ranking(
    state_outages: Sequence[Sequence[tuple[str, str]]],
    values: Sequence[float],
    counts: Sequence[int],
    *,
    tol: float = 1e-6,
) -> list[dict]:
    """Descriptive ranking of components whose outage co-occurs with load shedding.

    For component k: ``share`` = (sum of unserved energy over samples where k is out) / (total
    sampled unserved energy). Because several components can be out in the same sample, shares
    can sum to > 1 and are NOT causal attributions.
    """
    y = np.asarray(values, dtype=float)
    c = np.asarray(counts, dtype=np.int64)
    n = int(c.sum())
    total = float(np.sum(c * y))
    acc: dict[tuple[str, str], list[float]] = {}
    for outs, ys, cs in zip(state_outages, y.tolist(), c.tolist(), strict=True):
        for comp in outs:
            a = acc.setdefault(tuple(comp), [0, 0, 0.0])
            a[0] += cs
            a[1] += cs if ys > tol else 0
            a[2] += cs * ys
    rows = []
    for (component, aid), (n_out, n_out_shed, e_out) in acc.items():
        if n_out_shed == 0:
            continue
        n_in = n - n_out
        rows.append({
            "component": component,
            "asset_id": aid,
            "n_samples_out": int(n_out),
            "n_samples_out_with_shed": int(n_out_shed),
            "conditional_mean_unserved_if_out_mwh": e_out / n_out,
            "conditional_mean_unserved_if_in_service_mwh": (
                (total - e_out) / n_in if n_in else None
            ),
            "share_of_sampled_unserved_energy": (e_out / total) if total > 0 else None,
        })
    rows.sort(key=lambda r: (-(r["share_of_sampled_unserved_energy"] or 0.0),
                             r["component"], r["asset_id"]))
    return rows
