"""Pure violation / energy bookkeeping on per-step arrays (no pandapower dependency).

All functions take numpy arrays shaped ``(n_steps, n_elements)`` (or ``(n_steps,)``) and treat NaN
(non-converged step) as "no information": a NaN never counts as a violation.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class RunStats:
    steps: int  # number of flagged steps
    longest_run_steps: int  # longest consecutive run of flagged steps
    events: int  # number of separate runs (rising edges)


def run_stats(flags: np.ndarray) -> RunStats:
    """Count flagged steps, the longest consecutive run and the number of separate runs."""
    f = np.asarray(flags, dtype=bool).ravel()
    if f.size == 0:
        return RunStats(0, 0, 0)
    padded = np.concatenate(([False], f, [False])).astype(np.int8)
    edges = np.diff(padded)
    starts = np.flatnonzero(edges == 1)
    ends = np.flatnonzero(edges == -1)
    lengths = ends - starts
    return RunStats(int(f.sum()), int(lengths.max(initial=0)), int(starts.size))


def voltage_flags(
    vm_pu: np.ndarray, vmin: np.ndarray | float, vmax: np.ndarray | float
) -> tuple[np.ndarray, np.ndarray]:
    """Return boolean ``(under, over)`` arrays; limits broadcast over the element axis."""
    vm = np.asarray(vm_pu, dtype=float)
    with np.errstate(invalid="ignore"):
        under = np.nan_to_num(vm < np.asarray(vmin, dtype=float), nan=False)
        over = np.nan_to_num(vm > np.asarray(vmax, dtype=float), nan=False)
    return under.astype(bool), over.astype(bool)


def loading_flags(loading_pct: np.ndarray, limit_pct: np.ndarray | float) -> np.ndarray:
    """Boolean overload array: ``loading > limit`` (strict)."""
    ld = np.asarray(loading_pct, dtype=float)
    with np.errstate(invalid="ignore"):
        return np.nan_to_num(ld > np.asarray(limit_pct, dtype=float), nan=False).astype(bool)


def summarize_flags(flags: np.ndarray, dt_h: float) -> dict[str, float | int]:
    """Aggregate an element-wise flag matrix to system-level counts and durations.

    ``steps_with_violation`` counts steps where at least one element is flagged;
    ``element_steps`` is the total of element x step violations.
    """
    f = np.asarray(flags, dtype=bool)
    any_step = f.any(axis=1) if f.ndim == 2 else f
    rs = run_stats(any_step)
    return {
        "steps_with_violation": rs.steps,
        "hours_with_violation": rs.steps * dt_h,
        "longest_violation_h": rs.longest_run_steps * dt_h,
        "violation_events": rs.events,
        "element_steps": int(f.sum()),
        "elements_affected": int(f.any(axis=0).sum()) if f.ndim == 2 else int(bool(f.any())),
    }


def top_elements(
    flags: np.ndarray,
    values: np.ndarray,
    names: list[str],
    *,
    worst: str,
    k: int = 5,
    dt_h: float,
) -> list[dict[str, float | int | str]]:
    """Up to ``k`` elements with the most violating steps (ties: worst extreme value).

    ``worst`` is ``"max"`` or ``"min"`` and selects the reported extreme of ``values``.
    """
    f = np.asarray(flags, dtype=bool)
    v = np.asarray(values, dtype=float)
    counts = f.sum(axis=0)
    if worst == "max":
        extreme = np.nanmax(np.where(np.isnan(v), -np.inf, v), axis=0)
        order_key = -extreme
    elif worst == "min":
        extreme = np.nanmin(np.where(np.isnan(v), np.inf, v), axis=0)
        order_key = extreme
    else:
        raise ValueError(f"worst must be 'max' or 'min', got {worst!r}")
    idx = [i for i in np.lexsort((order_key, -counts)) if counts[i] > 0][:k]
    out = []
    for i in idx:
        rs = run_stats(f[:, i])
        out.append(
            {
                "name": names[i],
                "violation_steps": int(counts[i]),
                "violation_h": rs.steps * dt_h,
                "longest_violation_h": rs.longest_run_steps * dt_h,
                worst: float(extreme[i]),
            }
        )
    return out


def energy_mwh(power_mw: np.ndarray, dt_h: float) -> float:
    """Rectangle-rule energy of a per-step power series (NaN steps excluded)."""
    return float(np.nansum(np.asarray(power_mw, dtype=float)) * dt_h)
