"""Objective stress-period detection on hourly observed series.

All functions take hourly ``pandas.Series`` indexed by a tz-aware UTC ``DatetimeIndex`` (start of
the hour). Days are **UTC calendar days** (00:00-23:00 UTC), because the scigrid-de snapshots are
aligned to UTC hours (see ``alignment_evidence`` in the builder). Missing values are never
interpolated: a day or window containing any missing hour, or a gap in the hourly index, is
excluded from every criterion.

Criteria
--------
(a) ``highest_load_day``: the UTC day containing the maximum hourly load.
(b) ``lowest_cf_day``: among complete days in the given months (default winter, Dec-Feb), the day
    with the lowest daily-mean wind+solar capacity factor. ``min_mean_window`` additionally
    reports the unconstrained 24-h rolling minimum (any start hour) for comparison.
(c) ``combined_day``: among complete days whose daily-mean load is at or above the
    ``load_quantile`` (default 0.9) of all complete days' daily-mean load, the day with the
    lowest daily-mean wind+solar capacity factor.
Ties are broken by the earliest timestamp.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

HOURS_PER_DAY = 24
WINTER_MONTHS = (12, 1, 2)


@dataclass(frozen=True)
class WindowResult:
    start: pd.Timestamp  # first hour (inclusive, UTC)
    end: pd.Timestamp  # hour after the last one (exclusive, UTC)
    mean: float
    hours: int

    def as_dict(self) -> dict:
        d = asdict(self)
        d["start"] = self.start.isoformat()
        d["end"] = self.end.isoformat()
        return d


def _check_hourly_utc(s: pd.Series) -> None:
    idx = s.index
    if not isinstance(idx, pd.DatetimeIndex) or idx.tz is None:
        raise ValueError("series must have a tz-aware DatetimeIndex")
    if str(idx.tz) != "UTC":
        raise ValueError(f"series index must be UTC, got {idx.tz}")
    if not idx.is_monotonic_increasing or idx.has_duplicates:
        raise ValueError("series index must be strictly increasing")


def _regular(s: pd.Series) -> pd.Series:
    """Reindex onto a gap-free hourly grid; hours absent from the input become NaN (flagged)."""
    _check_hourly_utc(s)
    if s.empty:
        return s.astype(float)
    full = pd.date_range(s.index[0], s.index[-1], freq="h", tz="UTC")
    return s.astype(float).reindex(full)


def min_mean_window(
    s: pd.Series, length: int = HOURS_PER_DAY, *, start_hours: Iterable[int] | None = None,
    months: Iterable[int] | None = None,
) -> WindowResult:
    """Window of ``length`` consecutive hours with the lowest mean.

    Windows with any missing hour are skipped. ``start_hours`` restricts allowed start hours of
    day (UTC), e.g. ``[0]`` for calendar days. ``months`` restricts the start timestamp's month.
    """
    if length < 1:
        raise ValueError("length must be >= 1")
    r = _regular(s)
    means = r.rolling(length, min_periods=length).mean().shift(-(length - 1))
    ok = means.notna()
    if start_hours is not None:
        ok &= means.index.hour.isin(list(start_hours))
    if months is not None:
        ok &= means.index.month.isin(list(months))
    cand = means[ok]
    if cand.empty:
        raise ValueError("no complete window satisfies the constraints")
    start = cand.idxmin()  # first occurrence => earliest on ties
    return WindowResult(
        start=start,
        end=start + pd.Timedelta(hours=length),
        mean=float(cand.loc[start]),
        hours=length,
    )


def daily_table(s: pd.Series) -> pd.DataFrame:
    """Per UTC day: count of valid hours, complete flag, mean, max, argmax hour."""
    r = _regular(s)
    day = r.index.floor("D")
    g = r.groupby(day)
    out = pd.DataFrame(
        {
            "valid_hours": g.count(),
            "slots": g.size(),
            "mean": g.mean(),
            "max": g.max(),
        }
    )
    out["complete"] = (out["valid_hours"] == HOURS_PER_DAY) & (out["slots"] == HOURS_PER_DAY)
    return out


@dataclass(frozen=True)
class DayResult:
    date: str  # YYYY-MM-DD (UTC day)
    value: float  # criterion value
    detail: dict

    def as_dict(self) -> dict:
        return asdict(self)


def _day_slice(s: pd.Series, day: pd.Timestamp) -> pd.Series:
    return s.loc[day : day + pd.Timedelta(hours=HOURS_PER_DAY - 1)]


def highest_load_day(load: pd.Series) -> DayResult:
    """(a) UTC day containing the maximum hourly load; the day must be complete."""
    t = daily_table(load)
    complete = t[t["complete"]]
    if complete.empty:
        raise ValueError("no complete day")
    day = complete["max"].idxmax()
    hours = _day_slice(load, day)
    peak_ts = hours.idxmax()
    energy_day = complete["mean"].idxmax()
    return DayResult(
        date=day.strftime("%Y-%m-%d"),
        value=float(complete.loc[day, "max"]),
        detail={
            "criterion": "maximum hourly load over all complete UTC days",
            "peak_load_mw": float(complete.loc[day, "max"]),
            "peak_hour_utc": peak_ts.isoformat(),
            "daily_mean_load_mw": float(complete.loc[day, "mean"]),
            "max_daily_mean_load_day": energy_day.strftime("%Y-%m-%d"),
            "max_daily_mean_load_mw": float(complete.loc[energy_day, "mean"]),
            "complete_days_considered": int(len(complete)),
        },
    )


def lowest_cf_day(cf: pd.Series, *, months: Iterable[int] = WINTER_MONTHS) -> DayResult:
    """(b) Complete UTC day (in ``months``) with the lowest daily-mean capacity factor."""
    months = tuple(months)
    day_win = min_mean_window(cf, HOURS_PER_DAY, start_hours=[0], months=months)
    any_win = min_mean_window(cf, HOURS_PER_DAY, months=months)
    t = daily_table(cf)
    n = int((t["complete"] & t.index.month.isin(months)).sum())
    return DayResult(
        date=day_win.start.strftime("%Y-%m-%d"),
        value=day_win.mean,
        detail={
            "criterion": "lowest daily-mean wind+solar capacity factor over complete UTC days "
            f"in months {list(months)}",
            "daily_mean_cf": day_win.mean,
            "rolling_24h_minimum_any_start": any_win.as_dict(),
            "complete_days_considered": n,
        },
    )


def combined_day(load: pd.Series, cf: pd.Series, *, load_quantile: float = 0.9) -> DayResult:
    """(c) Lowest daily-mean CF among complete days with daily-mean load >= the quantile."""
    if not 0.0 <= load_quantile < 1.0:
        raise ValueError("load_quantile must be in [0, 1)")
    tl = daily_table(load)
    tc = daily_table(cf)
    both = tl.add_suffix("_load").join(tc.add_suffix("_cf"), how="inner")
    both = both[both["complete_load"] & both["complete_cf"]]
    if both.empty:
        raise ValueError("no day with complete load and capacity-factor data")
    threshold = float(np.quantile(both["mean_load"].to_numpy(), load_quantile))
    high = both[both["mean_load"] >= threshold]
    day = high["mean_cf"].idxmin()
    return DayResult(
        date=day.strftime("%Y-%m-%d"),
        value=float(high.loc[day, "mean_cf"]),
        detail={
            "criterion": f"lowest daily-mean wind+solar CF among complete UTC days whose "
            f"daily-mean load >= the {load_quantile:.2f} quantile of daily-mean load",
            "load_quantile": load_quantile,
            "daily_mean_load_threshold_mw": threshold,
            "daily_mean_load_mw": float(high.loc[day, "mean_load"]),
            "daily_peak_load_mw": float(high.loc[day, "max_load"]),
            "daily_mean_cf": float(high.loc[day, "mean_cf"]),
            "high_load_days": int(len(high)),
            "complete_days_considered": int(len(both)),
        },
    )
