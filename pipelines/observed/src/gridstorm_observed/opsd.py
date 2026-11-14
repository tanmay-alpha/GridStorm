"""Open Power System Data (OPSD) time series 2020-10-06: German load, wind and solar.

The 60-min single-index CSV (~130 MB) is downloaded once to the cache outside the repo and
verified against the sha256 published in the version's ``datapackage.json``. Only the German
columns listed in :data:`sources.OPSD_DE_COLUMNS` are read. The actual load (``LOAD_COL``) and the
generation/capacity columns are used for stress-day detection and coarse daily ratios only; the
hourly demand mapping uses the openly licensed day-ahead load forecast (``LOAD_FORECAST_COL``).

Capacity factors are computed from generation and capacity (``generation_actual / capacity``)
per technology and for the wind+solar aggregate::

    CF_ws(t) = (G_on + G_off + G_pv)(t) / (C_on + C_off + C_pv)(t)

An hour where any input is missing is NaN (never interpolated) and excluded by the detectors.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import sources

TECHS = {
    # OPSD technology key -> scigrid-de carrier name
    "wind_onshore": "Wind Onshore",
    "wind_offshore": "Wind Offshore",
    "solar": "Solar",
}
LOAD_COL = "DE_load_actual_entsoe_transparency"
LOAD_FORECAST_COL = sources.OPSD_LOAD_FORECAST_COL


def fetch_csv(dest_dir: Path | None = None) -> Path:
    dest = (dest_dir or sources.cache_dir() / "opsd") / sources.OPSD_CSV_NAME
    return sources.download(sources.OPSD_CSV_URL, dest, expected_sha256=sources.OPSD_CSV_SHA256)


def fetch_datapackage(dest_dir: Path | None = None) -> Path:
    dest = (dest_dir or sources.cache_dir() / "opsd") / "datapackage.json"
    if not dest.exists():
        sources.download(sources.OPSD_DATAPACKAGE_URL, dest)
    return dest


def read_de(csv_path: Path) -> pd.DataFrame:
    """German columns indexed by UTC hour start (tz-aware), on a gap-free hourly grid."""
    df = pd.read_csv(csv_path, usecols=["utc_timestamp", *sources.OPSD_DE_COLUMNS])
    idx = pd.DatetimeIndex(pd.to_datetime(df.pop("utc_timestamp"), utc=True), name="utc")
    df.index = idx
    if idx.has_duplicates or not idx.is_monotonic_increasing:
        raise ValueError("OPSD index not strictly increasing")
    full = pd.date_range(idx[0], idx[-1], freq="h", tz="UTC", name="utc")
    return df.astype(float).reindex(full)


def capacity_factors(de: pd.DataFrame) -> pd.DataFrame:
    """Per-technology CF (generation/capacity) and the wind+solar aggregate ``wind_solar``."""
    out = pd.DataFrame(index=de.index)
    gen_sum = 0.0
    cap_sum = 0.0
    for key in TECHS:
        gen = de[f"DE_{key}_generation_actual"]
        cap = de[f"DE_{key}_capacity"]
        out[key] = gen / cap
        gen_sum = gen_sum + gen
        cap_sum = cap_sum + cap
    out["wind_solar"] = gen_sum / cap_sum  # NaN if any component missing (NaN propagates)
    return out


def coverage_report(de: pd.DataFrame) -> dict:
    """Missing-hour counts per column (gaps are flagged, never filled)."""
    return {
        "first_hour_utc": de.index[0].isoformat(),
        "last_hour_utc": de.index[-1].isoformat(),
        "hours": int(len(de)),
        "missing_hours": {c: int(de[c].isna().sum()) for c in de.columns},
    }
