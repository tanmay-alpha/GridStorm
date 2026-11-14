"""NASA POWER hourly 2-m temperature and 10-m wind speed at a few German points.

POWER hourly point data are **reanalysis-derived** (MERRA-2 based, native ~0.5 x 0.625 deg
grid), not station measurements; they are labelled ``observed (reanalysis-derived)`` throughout.
Requests use ``time-standard=UTC`` so hours align with the OPSD UTC index. The POWER fill value
(``-999``) becomes NaN and is counted, never interpolated.
"""

from __future__ import annotations

import hashlib
import json
import urllib.parse
from pathlib import Path

import pandas as pd

from . import sources

PARAMETERS = ("T2M", "WS10M")
UNITS = {"T2M": "degC", "WS10M": "m/s"}


def point_url(point: sources.Point, start: str, end: str) -> str:
    """API url for one point and an inclusive ``YYYYMMDD`` date range (UTC)."""
    query = {
        "parameters": ",".join(PARAMETERS),
        "community": "RE",
        "longitude": f"{point.lon}",
        "latitude": f"{point.lat}",
        "start": start,
        "end": end,
        "format": "JSON",
        "time-standard": "UTC",
    }
    return f"{sources.POWER_HOURLY_URL}?{urllib.parse.urlencode(query)}"


def fetch_point(point: sources.Point, start: str, end: str, cache: Path | None = None) -> Path:
    """Download (once) the JSON response for ``point`` into the cache; returns its path."""
    url = point_url(point, start, end)
    key = hashlib.sha256(url.encode()).hexdigest()[:16]
    dest = (cache or sources.cache_dir() / "nasa-power") / f"{point.id}_{start}_{end}_{key}.json"
    if not dest.exists():
        sources.download(url, dest)
    return dest


def parse_point(path: Path, point: sources.Point) -> tuple[pd.DataFrame, dict]:
    """Hourly frame (UTC index) with columns ``PARAMETERS`` plus the response header."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    header = doc["header"]
    if header.get("time_standard") != "UTC":
        raise ValueError(f"{path}: expected UTC time standard, got {header.get('time_standard')}")
    fill = float(header.get("fill_value", -999.0))
    cols = {}
    for p in PARAMETERS:
        raw = doc["properties"]["parameter"][p]
        idx = pd.to_datetime(list(raw.keys()), format="%Y%m%d%H", utc=True)
        s = pd.Series([float(v) for v in raw.values()], index=idx, dtype=float)
        cols[p] = s.where(s != fill)
    df = pd.DataFrame(cols).sort_index()
    df.index.name = "utc"
    df.insert(0, "point", point.id)
    return df, header


def day_summary(df: pd.DataFrame, day: str) -> dict:
    """Per-point and all-point mean/min T2M and mean WS10M over one UTC day."""
    d = pd.Timestamp(day, tz="UTC")
    sl = df[(df.index >= d) & (df.index < d + pd.Timedelta(days=1))]
    per_point = {}
    for pid, g in sl.groupby("point"):
        per_point[pid] = {
            "t2m_mean_c": round(float(g["T2M"].mean()), 2),
            "t2m_min_c": round(float(g["T2M"].min()), 2),
            "ws10m_mean_ms": round(float(g["WS10M"].mean()), 2),
            "missing_hours": int(g[list(PARAMETERS)].isna().any(axis=1).sum()),
        }
    return {
        "date": day,
        "points": per_point,
        "t2m_mean_all_points_c": round(float(sl["T2M"].mean()), 2),
        "ws10m_mean_all_points_ms": round(float(sl["WS10M"].mean()), 2),
    }
