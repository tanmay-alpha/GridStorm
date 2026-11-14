"""Mapping math: demand and renewable multipliers, clipping and capacity weighting."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from gridstorm_observed import build, mapping

H = np.arange(24)
NET_LOAD = 50_000 + 8_000 * np.sin((H - 11) / 24 * 2 * np.pi)


def test_demand_multipliers_reproduce_observed_shape_and_relative_level():
    ref = 40_000 + 5_000 * np.cos(H / 24 * 2 * np.pi)
    obs = 1.4 * ref.mean() * (1 + 0.2 * np.sin(H / 3))
    dm = mapping.demand_multipliers(obs, ref, NET_LOAD)
    scaled = np.asarray(dm.raw) * NET_LOAD
    # Scaled network load / network mean == observed day / observed reference-day mean.
    np.testing.assert_allclose(scaled / NET_LOAD.mean(), obs / ref.mean(), rtol=1e-12)
    np.testing.assert_allclose(dm.target_load_mw, scaled, rtol=1e-12)
    assert dm.clipped_hours == []
    np.testing.assert_allclose(dm.multipliers, np.round(dm.raw, 4), atol=0)


def test_demand_identity_when_observed_day_equals_network_shape():
    ref = NET_LOAD * 0.9
    dm = mapping.demand_multipliers(ref, ref, NET_LOAD)
    np.testing.assert_allclose(dm.multipliers, np.ones(24), atol=1e-4)


def test_demand_clipped_to_stormspec_range():
    ref = np.full(24, 1000.0)
    obs = np.full(24, 1000.0)
    obs[3] = 7000.0  # raw multiplier ~ 7 * mean(net)/net[3] > 5
    dm = mapping.demand_multipliers(obs, ref, NET_LOAD)
    assert dm.clipped_hours == [3]
    assert dm.multipliers[3] == 5.0
    assert dm.raw[3] > 5.0


def test_demand_rejects_missing_values():
    obs = NET_LOAD.copy()
    obs[5] = np.nan
    with pytest.raises(ValueError, match="no interpolation"):
        mapping.demand_multipliers(obs, NET_LOAD, NET_LOAD)
    with pytest.raises(ValueError):
        mapping.demand_multipliers(NET_LOAD[:23], NET_LOAD[:23], NET_LOAD[:23])


def test_renewable_multipliers_ratio_clip_and_undefined():
    net = np.full(24, 0.5)
    net[:6] = 0.0  # e.g. solar at night
    obs = np.full(24, 0.1)
    obs[10] = 0.8  # observed above network -> clipped to 1
    rm = mapping.renewable_multipliers("Solar", obs, net)
    assert rm.undefined_hours == [0, 1, 2, 3, 4, 5]
    assert rm.multipliers[:6] == [None] * 6
    assert rm.clipped_hours == [10]
    assert rm.multipliers[10] == 1.0
    assert rm.raw[10] == pytest.approx(1.6)
    assert rm.multipliers[12] == pytest.approx(0.2)
    eff = mapping.effective_cf(rm)
    # Unclipped, defined hours reproduce the observed CF exactly (up to 4-decimal rounding).
    for h in range(6, 24):
        if h != 10:
            assert eff[h] == pytest.approx(obs[h], abs=0.5e-4)
    assert eff[10] == pytest.approx(0.5)


def test_capacity_weighted_cf():
    pmax = np.array([[1.0, 0.0], [0.5, 0.5]])
    cf = mapping.capacity_weighted_cf(pmax, np.array([3.0, 1.0]))
    np.testing.assert_allclose(cf, [0.75, 0.5])
    with pytest.raises(ValueError):
        mapping.capacity_weighted_cf(pmax, np.array([1.0]))


def test_reference_day_is_nearest_complete_first_of_january():
    idx = pd.date_range("2015-12-25", "2017-01-10", freq="h", tz="UTC")
    load = pd.Series(1.0, index=idx, name="load")
    assert build.reference_day(load, "2016-12-20") == "2017-01-01"
    assert build.reference_day(load, "2016-02-20") == "2016-01-01"
    load.loc["2017-01-01 05:00"] = np.nan  # incomplete -> fall back to the next nearest
    assert build.reference_day(load, "2016-12-20") == "2016-01-01"
