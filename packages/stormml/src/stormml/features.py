"""Per-contingency screening features computed from the *pre-contingency* (base AC) state only.

One row per outaged ``mpc.branch`` row ``l``. All features are dimensionless or in percent so that
they transfer between networks of different size; no network-size feature is used.

The primary DC-LODF baseline is the maximum estimated loading of any remaining branch.
``dc_attributable_score`` is a secondary feature: existing overloads must worsen by 5 percentage
points to count, whereas new overloads use the ordinary 100 % limit.
Islanding outages (bridges, LODF undefined) use base loading (no redistribution information);
their separate bridge feature exposes this limitation.
"""

from __future__ import annotations

import numpy as np

from .cases import BASE_KV, BR_X, RATE_A, TAP, VMAX, VMIN, MatpowerCase
from .dc import Sensitivities, Topology, dc_post_contingency_loading

AGGRAVATION_PP = 5.0

FEATURE_NAMES: tuple[str, ...] = (
    "dc_score",
    "dc_attributable_score",
    "dc_n_over",
    "dc_excess_sum",
    "lodf_absmax",
    "pre_load",
    "pre_p_frac",
    "pre_q_frac",
    "nbr_load_max",
    "nbr_load_mean",
    "sys_load_max",
    "sys_frac_over",
    "load_factor",
    "is_bridge",
    "is_transformer",
    "betweenness",
    "deg_min",
    "deg_max",
    "vm_end_min",
    "vm_margin_end",
    "sys_vm_margin_min",
    "rel_rate",
    "rel_x",
)


def attributable_dc_loading(est: np.ndarray, base_dc: np.ndarray) -> np.ndarray:
    """Secondary aggravation score; ``est`` is (m, m) [k, l], ``base_dc`` is (m,)."""
    b = base_dc[:, None]
    return np.where(b <= 100.0, est, 100.0 - AGGRAVATION_PP + (est - b))


def compute_features(
    case: MatpowerCase,
    sens: Sensitivities,
    topo: Topology,
    *,
    p_from_mw: np.ndarray,
    q_from_mvar: np.ndarray,
    s_max_mva: np.ndarray,
    vm_pu: np.ndarray,
    load_factor: float,
) -> np.ndarray:
    """Return an ``(m, len(FEATURE_NAMES))`` float array (no NaNs)."""
    m = case.branch.shape[0]
    rate = case.branch[:, RATE_A]
    rated = rate > 0
    safe_rate = np.where(rated, rate, 1.0)
    pre_load = np.where(rated, s_max_mva / safe_rate * 100.0, 0.0)
    base_dc = np.where(rated, np.abs(p_from_mw) / safe_rate * 100.0, np.nan)

    est = dc_post_contingency_loading(p_from_mw, rate, sens.lodf)  # NaN: unrated / islanding
    isl = sens.islanding
    if isl.any():
        est[:, isl] = base_dc[:, None]
    g = attributable_dc_loading(est, base_dc)
    diag = np.arange(m)
    g[diag, diag] = np.nan
    est[diag, diag] = np.nan
    with np.errstate(invalid="ignore"):
        over = np.nan_to_num(g - 100.0, nan=0.0)
    dc_attributable = np.nan_to_num(np.nanmax(g, axis=0), nan=0.0)
    dc_score = np.nan_to_num(np.nanmax(est, axis=0), nan=0.0)
    dc_n_over = (over > 0).sum(axis=0).astype(float)
    dc_excess = np.clip(over, 0.0, None).sum(axis=0)
    lodf_abs = np.abs(np.nan_to_num(sens.lodf, nan=0.0))
    lodf_abs[diag, diag] = 0.0
    lodf_absmax = lodf_abs.max(axis=0)

    nbr_max = np.array([pre_load[n].max() if n.size else 0.0 for n in topo.neighbours])
    nbr_mean = np.array([pre_load[n].mean() if n.size else 0.0 for n in topo.neighbours])

    vmax, vmin = case.bus[:, VMAX], case.bus[:, VMIN]
    margin = np.minimum(vm_pu - vmin, vmax - vm_pu)
    vm_end_min = np.minimum(vm_pu[topo.f], vm_pu[topo.t])
    vm_margin_end = np.minimum(margin[topo.f], margin[topo.t])

    kv = case.bus[:, BASE_KV]
    is_tr = (case.branch[:, TAP] != 0) | (kv[topo.f] != kv[topo.t])
    x = np.abs(case.branch[:, BR_X])

    cols = {
        "dc_score": dc_score,
        "dc_attributable_score": dc_attributable,
        "dc_n_over": dc_n_over,
        "dc_excess_sum": dc_excess,
        "lodf_absmax": lodf_absmax,
        "pre_load": pre_load,
        "pre_p_frac": np.where(rated, np.abs(p_from_mw) / safe_rate, 0.0),
        "pre_q_frac": np.where(rated, np.abs(q_from_mvar) / safe_rate, 0.0),
        "nbr_load_max": nbr_max,
        "nbr_load_mean": nbr_mean,
        "sys_load_max": np.full(m, pre_load.max()),
        "sys_frac_over": np.full(m, float((pre_load > 100.0).mean())),
        "load_factor": np.full(m, load_factor),
        "is_bridge": topo.is_bridge.astype(float),
        "is_transformer": is_tr.astype(float),
        "betweenness": topo.edge_betweenness,
        "deg_min": np.minimum(topo.bus_degree[topo.f], topo.bus_degree[topo.t]),
        "deg_max": np.maximum(topo.bus_degree[topo.f], topo.bus_degree[topo.t]),
        "vm_end_min": vm_end_min,
        "vm_margin_end": vm_margin_end,
        "sys_vm_margin_min": np.full(m, margin.min()),
        "rel_rate": np.where(rated, rate / np.median(rate[rated]) if rated.any() else 1.0, 0.0),
        "rel_x": x / np.median(x),
    }
    out = np.column_stack([cols[n] for n in FEATURE_NAMES]).astype(float)
    if not np.isfinite(out).all():
        bad = [n for i, n in enumerate(FEATURE_NAMES) if not np.isfinite(out[:, i]).all()]
        raise ValueError(f"non-finite features: {bad}")
    return out
