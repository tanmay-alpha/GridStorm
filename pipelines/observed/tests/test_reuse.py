"""Licence guard: the committed files must not let anyone rebuild non-open ENTSO-E series.

Actual load (Reg. 543/2013 Art. 6.1.a) and actual generation (Art. 16.1) are not on the ENTSO-E
free re-use list (docs/research/entsoe-reuse-check.md). The previous committed files returned the
observed hourly load to within 2.4 MW and observed hourly CFs to within 5e-5. These tests

* check that no non-open column name and no observed absolute/statistic is committed, and
* attempt the reconstruction from the committed files against the real OPSD data (cached,
  sha256-verified download; skipped when the cache is absent) and require it to FAIL by more
  than the stated tolerances, even with an oracle scale fitted to the observed values.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest
import stormspec

from gridstorm_observed import opsd, sources

#: The reconstructed actual hourly load must miss somewhere by more than this (MW): ~200x the
#: 2.4 MW the previous files allowed, ~0.7 % of a 70 GW winter peak.
LOAD_TOL_MW = 500.0
#: The reconstructed hourly CF must miss somewhere by more than this fraction of the day's
#: observed peak CF, per carrier and stress day.
CF_TOL_OF_PEAK = 0.10

DERIVED_PATH = sources.OPSD_OUT_DIR / "derived-multipliers.json"
MANIFEST_PATH = sources.OPSD_OUT_DIR / "manifest.json"
RESULTS_PATH = sources.OBSERVED_DIR / "analogue-results.json"
SCENARIOS = sorted(sources.SCENARIO_OUT_DIR.glob("*.yaml"))
DATA_FILES = [DERIVED_PATH, RESULTS_PATH, *SCENARIOS]
DERIVED = json.loads(DERIVED_PATH.read_text("utf-8"))

#: Keys that held observed absolutes/statistics or hourly observed ratios in earlier versions.
FORBIDDEN_KEYS = {
    "reference_day_mean_load_mw",
    "stress_day_mean_over_reference_mean",
    "peak_load_mw",
    "peak_hour_utc",
    "daily_mean_load_mw",
    "max_daily_mean_load_mw",
    "max_daily_mean_load_day",
    "daily_mean_load_threshold_mw",
    "daily_peak_load_mw",
    "daily_mean_cf",
    "observed_daily_mean_cf",
    "observed_cf",
    "target_load_mw",
    "max_raw_ratio_in_clipped_hours",
    "value",
}


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


@pytest.mark.parametrize("path", DATA_FILES, ids=lambda p: p.name)
def test_no_non_open_column_name_in_committed_data(path):
    text = path.read_text("utf-8")
    for col in sources.OPSD_NON_OPEN_COLUMNS:
        assert col not in text, f"{path.name} names non-open column {col}"
    assert "load_actual" not in text and "generation_actual" not in text


def test_no_observed_absolutes_or_hourly_renewable_ratios_committed():
    manifest = json.loads(MANIFEST_PATH.read_text("utf-8"))
    for doc in (DERIVED, manifest):
        found = FORBIDDEN_KEYS & set(_keys(doc))
        assert not found, found
    for rec in DERIVED["scenarios"]:
        assert rec["demand"]["source_column"] == sources.OPSD_LOAD_FORECAST_COL
        det = rec["detection"]
        numbers = {k: v for k, v in det.items() if isinstance(v, float)}
        assert set(numbers) <= {"load_quantile"}, numbers
        for r in rec["renewables"].values():
            w = r["daily_multiplier"]
            assert isinstance(w, float) and 0.0 <= w <= 1.0
            assert round(w / 0.05) * 0.05 == pytest.approx(w, abs=1e-12)
    for path in SCENARIOS:
        scen = stormspec.load_scenario(path)
        ren = [e for e in scen.events if e.type == "renewable_availability_multiplier"]
        assert len({e.carrier for e in ren}) == len(ren)  # at most one (daily) event per carrier
        assert all((e.window.start, e.window.end) == (0, 24) for e in ren)


# --- reconstruction attempt against the real data --------------------------------------------


@pytest.fixture(scope="module")
def opsd_de() -> pd.DataFrame:
    csv = sources.cache_dir() / "opsd" / sources.OPSD_CSV_NAME
    if not csv.exists():
        pytest.skip(f"OPSD source not cached at {csv} (run gridstorm_observed.build once)")
    assert sources.sha256_file(csv) == sources.OPSD_CSV_SHA256
    return opsd.read_de(csv)


def _day(s: pd.Series, day: str) -> np.ndarray:
    t = pd.Timestamp(day, tz="UTC")
    v = s.loc[t : t + pd.Timedelta(hours=23)].to_numpy(dtype=float)
    assert v.shape == (24,) and np.all(np.isfinite(v))
    return v


def _oracle(shape: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Best least-squares scaling of ``shape`` onto ``target`` (uses the secret values)."""
    return shape * float(shape @ target / (shape @ shape))


@pytest.mark.parametrize("rec", DERIVED["scenarios"], ids=lambda r: r["scenario_id"])
def test_actual_load_not_reconstructable(rec, opsd_de):
    net = np.asarray(DERIVED["network"]["load_mw"])
    m = np.asarray(rec["demand"]["multipliers"])
    shape = m * net / net.mean()  # = F(d,h) / mean F(ref) up to rounding
    day, ref = rec["stress_day_utc"], rec["reference_day_utc"]
    # Positive control: the committed multipliers do carry the (CC BY 4.0) forecast ...
    fc = _day(opsd_de[opsd.LOAD_FORECAST_COL], day)
    fc_rebuilt = shape * _day(opsd_de[opsd.LOAD_FORECAST_COL], ref).mean()
    assert np.max(np.abs(fc_rebuilt - fc)) < 10.0
    # ... but not the actual load (Art. 6.1.a), even with the best possible level.
    actual = _day(opsd_de[opsd.LOAD_COL], day)
    err = np.max(np.abs(_oracle(shape, actual) - actual))
    assert err > LOAD_TOL_MW, f"actual load reconstructable to {err:.1f} MW"


@pytest.mark.parametrize("rec", DERIVED["scenarios"], ids=lambda r: r["scenario_id"])
def test_observed_hourly_cf_not_reconstructable(rec, opsd_de):
    cf = opsd.capacity_factors(opsd_de)
    carrier_to_tech = {c: t for t, c in opsd.TECHS.items()}
    for carrier, r in rec["renewables"].items():
        net = np.asarray(DERIVED["network"]["capacity_factor"][carrier])
        obs = _day(cf[carrier_to_tech[carrier]], rec["stress_day_utc"])
        for label, rebuilt in (
            ("committed w", r["daily_multiplier"] * net),
            ("oracle scale", _oracle(net, obs)),
        ):
            rel = np.max(np.abs(rebuilt - obs)) / obs.max()
            assert rel > CF_TOL_OF_PEAK, f"{carrier} ({label}): hourly CF within {rel:.3f}"
