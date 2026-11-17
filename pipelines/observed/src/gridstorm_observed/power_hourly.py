"""NASA POWER hourly point data (community RE, ``time-standard=UTC``) for the observatory.

Parameters: ``T2M``, ``WS10M``, ``WS50M`` (MERRA-2, native 0.5 deg x 0.625 deg grid) and
``ALLSKY_SFC_SW_DWN`` (all-sky GHI from CERES SYN1deg Ed4.2 on a 1 deg x 1 deg grid for
2001 to about 3-4 months before real time). POWER returns the value of the source grid cell that
contains the requested coordinate: a *modeled* reanalysis / satellite-derived value, not a
station measurement. The hourly API defaults to Local Solar Time, so every request sets
``time-standard=UTC`` and every response is checked to say ``UTC``. The fill value (``-999``)
becomes ``None``; nothing is interpolated.

Raw responses are cached outside the repository (``<cache>/nasa-power/``). The committed request
record (``data/observed/nasa-power-de/power-hourly-requests.json``) pins every URL with its
response sha256, API version, source list, fill counts and the sha256 of the canonical values,
so the published bundle can be checked against the responses without the raw files.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from . import sources

PARAMETERS = ("T2M", "WS10M", "WS50M", "ALLSKY_SFC_SW_DWN")
COMMUNITY = "RE"
RECORD_SCHEMA = "gridstorm-power-requests/1.0"
RECORD_PATH = sources.POWER_OUT_DIR / "power-hourly-requests.json"
#: Pause between sequential requests (politeness; POWER answers HTTP 429 when rate limited).
PAUSE_S = 1.5
#: Stress days of the observed-analogue scenarios (docs/research/observed-analogue-scenarios.md)
#: and the window convention of the existing extract: the stress day +- 3 whole UTC days.
STRESS_DAYS = (
    ("2015-01-20", "Dunkelflaute 2015-01-20"),
    ("2017-01-24", "High load / low renewables 2017-01-24"),
    ("2017-12-13", "Peak load 2017-12-13"),
)
WINDOW_PAD_DAYS = 3
#: Requested date ranges (inclusive, UTC days): the 2015 window and calendar year 2017, which
#: contains both 2017 windows.
RANGES = (("20150117", "20150123"), ("20170101", "20171231"))


@dataclass(frozen=True)
class Request:
    point: sources.Point
    start: str
    end: str

    @property
    def url(self) -> str:
        query = {
            "parameters": ",".join(PARAMETERS),
            "community": COMMUNITY,
            "longitude": f"{self.point.lon}",
            "latitude": f"{self.point.lat}",
            "start": self.start,
            "end": self.end,
            "format": "JSON",
            "time-standard": "UTC",
        }
        return f"{sources.POWER_HOURLY_URL}?{urllib.parse.urlencode(query)}"

    def cache_path(self, cache: Path) -> Path:
        key = hashlib.sha256(self.url.encode()).hexdigest()[:16]
        return cache / f"{self.point.id}_{self.start}_{self.end}_{key}.json"


def requests() -> list[Request]:
    return [Request(p, a, b) for a, b in RANGES for p in sources.POWER_POINTS]


def default_cache() -> Path:
    return sources.cache_dir() / "nasa-power"


def parse_response(data: bytes) -> tuple[dict, dict[str, dict[datetime, float | None]]]:
    """Header plus ``{param: {utc_hour: value|None}}``; rejects non-UTC responses."""
    doc = json.loads(data)
    header = doc["header"]
    if header.get("time_standard") != "UTC":
        raise ValueError(f"expected UTC time standard, got {header.get('time_standard')!r}")
    fill = float(header["fill_value"])
    out: dict[str, dict[datetime, float | None]] = {}
    for p in PARAMETERS:
        raw = doc["properties"]["parameter"][p]
        col: dict[datetime, float | None] = {}
        for k, v in raw.items():
            ts = datetime.strptime(k, "%Y%m%d%H").replace(tzinfo=UTC)
            col[ts] = None if float(v) == fill else float(v)
        out[p] = col
    return doc, out


def values_digest(point_id: str, cols: dict[str, dict[datetime, float | None]]) -> str:
    """sha256 of the canonical values (``point,param,YYYYMMDDHH,value`` lines, 2 decimals)."""
    lines = []
    for p in PARAMETERS:
        for ts in sorted(cols[p]):
            v = cols[p][ts]
            lines.append(f"{point_id},{p},{ts:%Y%m%d%H},{'' if v is None else f'{v:.2f}'}")
    return hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest()


def download_all(reqs: list[Request], cache: Path, *, pause_s: float = PAUSE_S) -> list[Path]:
    """Download the uncached responses of ``reqs`` sequentially, pausing between downloads.

    Each new file gets a ``.retrieved_at`` sidecar (the only clock read of the pipeline). Any
    HTTP error (e.g. 429 rate limiting) propagates: no request record is written then.
    """
    cache.mkdir(parents=True, exist_ok=True)
    paths = []
    downloaded = 0
    for req in reqs:
        dest = req.cache_path(cache)
        if not dest.exists():
            if downloaded:
                time.sleep(pause_s)
            sources.download(req.url, dest)
            downloaded += 1
            fetched = datetime.now(UTC).replace(microsecond=0).isoformat()
            meta_path = dest.with_suffix(".retrieved_at")
            meta_path.write_text(fetched + "\n", encoding="utf-8")
        paths.append(dest)
    return paths


def fetch(cache: Path, *, pause_s: float = PAUSE_S) -> dict:
    """Download every request (sequentially, skipping cached files) and return a new record."""
    reqs = requests()
    paths = download_all(reqs, cache, pause_s=pause_s)
    return make_record([record_entry(r, p) for r, p in zip(reqs, paths, strict=True)])


def record_entry(req: Request, path: Path) -> dict:
    data = path.read_bytes()
    doc, cols = parse_response(data)
    header = doc["header"]
    meta = path.with_suffix(".retrieved_at")
    hours = {len(c) for c in cols.values()}
    if len(hours) != 1:
        raise ValueError(f"{path.name}: parameters have different hour counts {hours}")
    return {
        "point": req.point.id,
        "start": req.start,
        "end": req.end,
        "url": req.url,
        "retrieved_at": meta.read_text(encoding="utf-8").strip() if meta.exists() else None,
        "response_sha256": hashlib.sha256(data).hexdigest(),
        "response_bytes": len(data),
        "api": header["api"],
        "header_sources": header["sources"],
        "time_standard": header["time_standard"],
        "fill_value": header["fill_value"],
        "fill_values_replaced": {p: sum(v is None for v in cols[p].values()) for p in PARAMETERS},
        "hours": hours.pop(),
        "units": {p: doc["parameters"][p]["units"] for p in PARAMETERS},
        "longnames": {p: doc["parameters"][p]["longname"] for p in PARAMETERS},
        "values_sha256": values_digest(req.point.id, cols),
    }


def make_record(entries: list[dict]) -> dict:
    return {
        "schema_version": RECORD_SCHEMA,
        "api_url": sources.POWER_HOURLY_URL,
        "community": COMMUNITY,
        "parameters": list(PARAMETERS),
        "time_standard": "UTC",
        "points": [
            {"id": p.id, "name": p.name, "lat": p.lat, "lon": p.lon} for p in sources.POWER_POINTS
        ],
        "requests": entries,
    }


def load_cached(record: dict, cache: Path) -> dict[str, dict[str, dict]] | None:
    """Columns per point from the cached raw responses, or ``None`` if any is missing.

    Every cached file must hash to the recorded ``response_sha256``.
    """
    by_point: dict[str, dict[str, dict]] = {}
    points = {p.id: p for p in sources.POWER_POINTS}
    for rec in record["requests"]:
        req = Request(points[rec["point"]], rec["start"], rec["end"])
        if req.url != rec["url"]:
            raise ValueError(f"record URL differs from the pipeline's request: {rec['url']}")
        path = req.cache_path(cache)
        if not path.exists():
            return None
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != rec["response_sha256"]:
            raise ValueError(f"{path.name}: sha256 differs from the request record")
        _, cols = parse_response(data)
        dest = by_point.setdefault(rec["point"], {p: {} for p in PARAMETERS})
        for p in PARAMETERS:
            dest[p].update(cols[p])
    return by_point
