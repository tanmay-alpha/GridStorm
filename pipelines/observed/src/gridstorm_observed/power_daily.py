"""Daily means of UTC days computed by GridStorm from NASA POWER hourly UTC point data.

Same API, community, parameters and four points as :mod:`power_hourly`, requested with
``time-standard=UTC`` as one request per point per calendar year over the coverage of the
``opsd-de-load-forecast`` entry (2015-01-01..2020-09-30; the 2020 request ends 2020-09-30).
NASA's daily endpoint is deliberately not used: its days are not UTC days.

Aggregation rule: the value of UTC day ``D`` is the arithmetic mean of the 24 hourly values
labelled ``D 00`` .. ``D 23`` (UTC). It is written only if all 24 values are present (fill value
-999 counts as missing); otherwise the day is left empty. Nothing is interpolated or filled.

The committed request record (``data/observed/nasa-power-de/power-daily-requests.json``) pins
every URL with its response sha256 and API version (as for the hourly record) plus, per request,
the sha256 of the canonical daily means and the incomplete days per parameter, so the published
daily series can be checked without the ~15 MB of raw responses.
"""

from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import bundle, sources
from .power_hourly import (
    PARAMETERS,
    PAUSE_S,
    Request,
    download_all,
    make_record,
    parse_response,
    record_entry,
)

RECORD_SCHEMA = "gridstorm-power-daily-requests/1.0"
RECORD_PATH = sources.POWER_OUT_DIR / "power-daily-requests.json"
#: Coverage = the published day-ahead load forecast (UTC calendar days, inclusive).
START = datetime(2015, 1, 1, tzinfo=UTC)
END = datetime(2020, 9, 30, tzinfo=UTC)
#: Decimals of the published daily means (all four parameters).
DECIMALS = 2
HOURS_PER_DAY = 24
RULE = (
    "value of UTC day D = arithmetic mean of the 24 hourly values labelled D 00..23 UTC; written "
    "only if all 24 are present (fill value -999 = missing), otherwise empty; no interpolation"
)

Column = dict[datetime, float | None]


def ranges() -> list[tuple[str, str]]:
    """One inclusive ``(YYYYMMDD, YYYYMMDD)`` range per calendar year, clipped to the coverage."""
    out = []
    for year in range(START.year, END.year + 1):
        a = max(START, datetime(year, 1, 1, tzinfo=UTC))
        b = min(END, datetime(year, 12, 31, tzinfo=UTC))
        out.append((f"{a:%Y%m%d}", f"{b:%Y%m%d}"))
    return out


def requests() -> list[Request]:
    """Year-major, then the points in :data:`sources.POWER_POINTS` order (sequential fetch)."""
    return [Request(p, a, b) for a, b in ranges() for p in sources.POWER_POINTS]


def days(start: datetime = START, end: datetime = END) -> list[datetime]:
    """Inclusive UTC day starts ``start .. end`` (both must be 00:00 UTC)."""
    for t in (start, end):
        if t.utcoffset() != timedelta(0) or (t.hour, t.minute, t.second, t.microsecond) != (
            0,
            0,
            0,
            0,
        ):
            raise ValueError(f"not a UTC day start: {t!r}")
    return bundle.step_range(start, end, bundle.DAY)


def day_mean(col: Column, day: datetime) -> float | None:
    """Mean of hours ``day 00..23`` UTC; ``None`` unless all 24 hours are present."""
    vals = [col.get(day + timedelta(hours=h)) for h in range(HOURS_PER_DAY)]
    if any(v is None for v in vals):
        return None
    return math.fsum(vals) / HOURS_PER_DAY  # type: ignore[arg-type]


def daily_means(col: Column, grid: list[datetime]) -> list[float | None]:
    return [day_mean(col, d) for d in grid]


def daily_digest(point_id: str, daily: dict[str, list[float | None]], grid: list[datetime]) -> str:
    """sha256 of ``point,param,YYYYMMDD,value`` lines with the published formatting."""
    lines = []
    for p in PARAMETERS:
        for d, v in zip(grid, daily[p], strict=True):
            lines.append(f"{point_id},{p},{d:%Y%m%d},{bundle.fmt_num(v, DECIMALS)}")
    return hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest()


def request_days(start: str, end: str) -> list[datetime]:
    a = datetime.strptime(start, "%Y%m%d").replace(tzinfo=UTC)
    b = datetime.strptime(end, "%Y%m%d").replace(tzinfo=UTC)
    return days(a, b)


def daily_summary(point_id: str, cols: dict[str, Column], grid: list[datetime]) -> dict:
    """Daily digest and incomplete days (ISO dates per parameter) of one request's hours."""
    daily = {p: daily_means(cols[p], grid) for p in PARAMETERS}
    return {
        "days": len(grid),
        "daily_values_sha256": daily_digest(point_id, daily, grid),
        "incomplete_days": {
            p: [f"{d:%Y-%m-%d}" for d, v in zip(grid, daily[p], strict=True) if v is None]
            for p in PARAMETERS
        },
    }


def daily_record_entry(req: Request, path: Path) -> dict:
    entry = record_entry(req, path)
    _, cols = parse_response(path.read_bytes())
    entry.update(daily_summary(req.point.id, cols, request_days(req.start, req.end)))
    return entry


def build_record(entries: list[dict]) -> dict:
    record = make_record(entries)
    record["schema_version"] = RECORD_SCHEMA
    record["aggregation"] = {
        "rule": RULE,
        "decimals": DECIMALS,
        "start_utc": bundle.fmt_utc(START),
        "end_utc": bundle.fmt_utc(END),
    }
    return record


def fetch(cache: Path, *, pause_s: float = PAUSE_S) -> dict:
    """Download every yearly request (sequentially, skipping cached files) -> new record."""
    reqs = requests()
    paths = download_all(reqs, cache, pause_s=pause_s)
    return build_record([daily_record_entry(r, p) for r, p in zip(reqs, paths, strict=True)])
