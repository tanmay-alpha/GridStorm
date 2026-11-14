"""Stress-period detection on synthetic hourly series with known answers."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from gridstorm_observed import detect


def _series(values, start="2021-01-01") -> pd.Series:
    idx = pd.date_range(start, periods=len(values), freq="h", tz="UTC")
    return pd.Series(np.asarray(values, dtype=float), index=idx)


def test_min_mean_window_finds_planted_window():
    v = np.full(24 * 10, 0.5)
    v[24 * 3 + 5 : 24 * 4 + 5] = 0.1  # 24 h starting day 3, 05:00 UTC
    r = detect.min_mean_window(_series(v))
    assert r.start == pd.Timestamp("2021-01-04 05:00", tz="UTC")
    assert r.end == pd.Timestamp("2021-01-05 05:00", tz="UTC")
    assert r.mean == pytest.approx(0.1)
    # Restricted to calendar days, the best day is one of the two days the window overlaps.
    day = detect.min_mean_window(_series(v), start_hours=[0])
    assert day.start == pd.Timestamp("2021-01-04 00:00", tz="UTC")
    assert day.mean == pytest.approx((5 * 0.5 + 19 * 0.1) / 24)


def test_windows_with_missing_hours_are_skipped():
    v = np.full(24 * 6, 0.5)
    v[24 * 1 : 24 * 2] = 0.0  # lowest day ...
    v[24 * 1 + 7] = np.nan  # ... but incomplete -> excluded
    v[24 * 4 : 24 * 5] = 0.2
    r = detect.lowest_cf_day(_series(v), months=(1,))
    assert r.date == "2021-01-05"
    assert r.value == pytest.approx(0.2)


def test_gap_in_index_is_flagged_not_bridged():
    s = _series(np.full(24 * 4, 0.5))
    s.iloc[24 * 2 : 24 * 3] = 0.05
    s = s.drop(s.index[24 * 2 + 10])  # remove one hour from the low day
    with pytest.raises(ValueError):
        detect.min_mean_window(s.iloc[24 * 2 : 24 * 3 - 1], start_hours=[0])
    r = detect.lowest_cf_day(s, months=(1,))
    assert r.date != "2021-01-03"


def test_months_filter():
    s = _series(np.full(24 * 62, 0.5), start="2021-01-01")
    s.loc["2021-02-10"] = 0.05
    s.loc["2021-01-20"] = 0.1
    assert detect.lowest_cf_day(s, months=(1,)).date == "2021-01-20"
    assert detect.lowest_cf_day(s, months=(1, 2)).date == "2021-02-10"


def test_highest_load_day_and_tie_break():
    v = np.full(24 * 5, 100.0)
    v[24 * 2 + 17] = 300.0
    v[24 * 4 + 3] = 300.0  # tie -> earliest day wins
    r = detect.highest_load_day(_series(v))
    assert r.date == "2021-01-03"
    assert r.detail["peak_hour_utc"] == "2021-01-03T17:00:00+00:00"


def test_combined_day_restricts_to_high_load_days():
    days = 10
    load = np.repeat(np.arange(days, dtype=float) * 10 + 100, 24)  # day 9 highest
    cf = np.full(24 * days, 0.4)
    cf[0:24] = 0.01  # lowest CF, but lowest load -> not eligible at q=0.8
    cf[24 * 8 : 24 * 9] = 0.2  # day 8 is in the top 20 % of load
    r = detect.combined_day(_series(load), _series(cf), load_quantile=0.8)
    assert r.date == "2021-01-09"
    assert r.value == pytest.approx(0.2)
    assert r.detail["high_load_days"] == 2


def test_rejects_naive_or_non_utc_index():
    s = pd.Series([1.0, 2.0], index=pd.date_range("2021-01-01", periods=2, freq="h"))
    with pytest.raises(ValueError):
        detect.min_mean_window(s, 1)
    with pytest.raises(ValueError):
        detect.min_mean_window(s.tz_localize("Europe/Berlin"), 1)
