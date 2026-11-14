"""Pinned external sources, paths and download helpers for the observed-data pipelines.

Every remote file is pinned by version and (where the publisher states one) by sha256. Raw
downloads go to a cache OUTSIDE the repository (``$GRIDSTORM_DATA_CACHE`` or
``<repo>/../upstream/_data_cache``); only derived, small files are written into ``data/``.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = REPO_ROOT / "data"
OBSERVED_DIR = DATA_DIR / "observed"
OPSD_OUT_DIR = OBSERVED_DIR / "opsd-de"
POWER_OUT_DIR = OBSERVED_DIR / "nasa-power-de"
SCENARIO_OUT_DIR = DATA_DIR / "scenarios" / "observed"
NETWORK_ID = "scigrid-de"
NETWORK_DIR = DATA_DIR / "networks" / NETWORK_ID


def cache_dir() -> Path:
    """Raw-data cache outside the repo (never committed)."""
    env = os.environ.get("GRIDSTORM_DATA_CACHE")
    path = Path(env) if env else REPO_ROOT.parent / "upstream" / "_data_cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


# --- Open Power System Data: Time series, version 2020-10-06 (latest published version) -------

OPSD_VERSION = "2020-10-06"
OPSD_BASE_URL = f"https://data.open-power-system-data.org/time_series/{OPSD_VERSION}"
OPSD_DATAPACKAGE_URL = f"{OPSD_BASE_URL}/datapackage.json"
OPSD_CSV_NAME = "time_series_60min_singleindex.csv"
OPSD_CSV_URL = f"{OPSD_BASE_URL}/{OPSD_CSV_NAME}"
#: sha256 and size published for the 60-min single-index CSV in the version's datapackage.json
#: (``resources[name=opsd_time_series_60min].hash`` / ``.bytes``).
OPSD_CSV_SHA256 = "6a7f2bc571314cbf9c321cc03437691cd4be95c3a6f075e60ff99e8035c704c8"
OPSD_CSV_BYTES = 130339665
OPSD_DOI = f"https://doi.org/10.25832/time_series/{OPSD_VERSION}"
OPSD_ATTRIBUTION = (
    "Open Power System Data. 2020. Data Package Time series. Version 2020-10-06. "
    "https://doi.org/10.25832/time_series/2020-10-06. (Primary data from various sources, "
    "for a complete list see URL). German load forecast and load/generation: ENTSO-E "
    "Transparency Platform; German capacities: OPSD calculations based on BNetzA and "
    "netztransparenz.de."
)

ENTSOE_TERMS_URL = "https://transparencyplatform.zendesk.com/hc/en-us/articles/40921911218961-Legal-Terms-and-Conditions"
ENTSOE_REUSE_LIST_URL = (
    "https://transparencyplatform.zendesk.com/hc/en-us/article_attachments/40921869379729"
)
ENTSOE_REUSE_LIST_SHA256 = "b21717e8a5a41b9b8544db730d11c2a717abc9b07f89704437a89332b708ff9a"
ENTSOE_REUSE_LIST_VERSION = "2023-10-18"
CC_BY_4_URL = "https://creativecommons.org/licenses/by/4.0/"

#: The only OPSD column whose (derived) hourly values are committed: the ENTSO-E day-ahead total
#: load forecast, Reg. (EU) 543/2013 Art. 6.1.b = item #1 of the ENTSO-E free re-use list.
OPSD_LOAD_FORECAST_COL = "DE_load_forecast_entsoe_transparency"
#: CC BY 4.0 attribution (title, source, licence, changes) for the committed demand multipliers.
LOAD_FORECAST_ATTRIBUTION = (
    "Day-ahead forecast of the total load per market time unit, Germany (Reg. (EU) 543/2013 "
    "Art. 6.1.b), ENTSO-E Transparency Platform (https://transparency.entsoe.eu/), obtained via "
    f"Open Power System Data, Time series {OPSD_VERSION} ({OPSD_DOI}), column "
    f"{OPSD_LOAD_FORECAST_COL}. Licensed under CC BY 4.0 ({CC_BY_4_URL}) per the ENTSO-E list of "
    f"data available for free re-use ({ENTSOE_REUSE_LIST_VERSION}), item #1. Changes made by "
    "GridStorm: the stress day's 24 hourly values are divided by the mean of the nearest "
    "1 January (UTC), then by the scigrid-de network's normalized hourly load, and rounded to "
    "4 decimals; only these ratios are published."
)

_NOT_LISTED = (
    f"NOT on the ENTSO-E free re-use list ({ENTSOE_REUSE_LIST_VERSION}); Terms of Use cl. 3.1/5.1"
    " apply (Primary Owner's rights; no permission obtained)"
)
_ENTSOE_ACTUAL_GEN = "ENTSO-E Transparency, Reg. (EU) 543/2013 Art. 16.1.b/c (actual generation)"
_CAPACITY_ORIGIN = "OPSD calculation based on BNetzA and netztransparenz.de (not ENTSO-E)"
_CAPACITY_TERMS = "no data licence declared by OPSD; BNetzA/netztransparenz.de terms not checked"
_GEN_USE = (
    "detection of the Dunkelflaute/combined days; one daily availability ratio per carrier "
    "(rounded to 0.05, clipped to <= 1)"
)
_GEN_COMMITTED = (
    "one MODELED daily multiplier per carrier and stress day (ratio of daily-mean CFs, rounded "
    "to 0.05, clipped to <= 1); no hourly value, no daily-mean CF, no MW value"
)


def _reuse(origin: str, status: str, raw: str, used_for: str, committed: str) -> dict[str, str]:
    return {
        "origin": origin,
        "free_reuse_status": status,
        "raw_redistribution": raw,
        "used_for": used_for,
        "committed_derivative": committed,
    }


#: Per-column redistribution assessment (docs/research/entsoe-reuse-check.md); written into the
#: manifest. Key order = the order the columns are read.
OPSD_COLUMN_REUSE: dict[str, dict[str, str]] = {
    OPSD_LOAD_FORECAST_COL: _reuse(
        "ENTSO-E Transparency, Reg. (EU) 543/2013 Art. 6.1.b (day-ahead total load forecast)",
        f"ON the free re-use list ({ENTSOE_REUSE_LIST_VERSION}), item #1: CC BY 4.0",
        "permitted with attribution and indication of changes",
        "hourly demand multipliers (shape and level relative to the nearest 1 January)",
        "24 hourly ratios per stress day (4 decimals); CC BY 4.0, attribution in "
        "license.load_forecast_attribution",
    ),
    "DE_load_actual_entsoe_transparency": _reuse(
        "ENTSO-E Transparency, Reg. (EU) 543/2013 Art. 6.1.a (actual total load)",
        _NOT_LISTED,
        "not permitted",
        "stress-day detection only (highest-load and combined criteria)",
        "the selected dates only; no value or statistic",
    ),
    "DE_solar_capacity": _reuse(
        _CAPACITY_ORIGIN, _CAPACITY_TERMS, "unclear", _GEN_USE, _GEN_COMMITTED
    ),
    "DE_solar_generation_actual": _reuse(
        _ENTSOE_ACTUAL_GEN, _NOT_LISTED, "not permitted", _GEN_USE, _GEN_COMMITTED
    ),
    "DE_wind_onshore_capacity": _reuse(
        _CAPACITY_ORIGIN, _CAPACITY_TERMS, "unclear", _GEN_USE, _GEN_COMMITTED
    ),
    "DE_wind_onshore_generation_actual": _reuse(
        _ENTSOE_ACTUAL_GEN, _NOT_LISTED, "not permitted", _GEN_USE, _GEN_COMMITTED
    ),
    "DE_wind_offshore_capacity": _reuse(
        _CAPACITY_ORIGIN, _CAPACITY_TERMS, "unclear", _GEN_USE, _GEN_COMMITTED
    ),
    "DE_wind_offshore_generation_actual": _reuse(
        _ENTSOE_ACTUAL_GEN, _NOT_LISTED, "not permitted", _GEN_USE, _GEN_COMMITTED
    ),
}
#: German columns of the OPSD 60-min single-index CSV used here (all in MW).
OPSD_DE_COLUMNS = tuple(OPSD_COLUMN_REUSE)
#: Columns that are not openly licensed: no value derived from them may be committed hourly.
OPSD_NON_OPEN_COLUMNS = tuple(c for c in OPSD_DE_COLUMNS if c != OPSD_LOAD_FORECAST_COL)

# --- NASA POWER hourly API (no key) ------------------------------------------------------------

POWER_HOURLY_URL = "https://power.larc.nasa.gov/api/temporal/hourly/point"
POWER_REFERENCING_URL = "https://power.larc.nasa.gov/docs/referencing/"
POWER_DATA_USE_URL = (
    "https://www.earthdata.nasa.gov/engage/open-data-services-software-policies/data-use-guidance"
)


@dataclass(frozen=True)
class Point:
    id: str
    name: str
    lat: float
    lon: float


#: A few large German load centres spread north/south/east/west (city-centre coordinates).
POWER_POINTS: tuple[Point, ...] = (
    Point("berlin", "Berlin", 52.52, 13.405),
    Point("hamburg", "Hamburg", 53.551, 9.994),
    Point("cologne", "Cologne", 50.938, 6.960),
    Point("munich", "Munich", 48.137, 11.575),
)


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def download(
    url: str, dest: Path, *, expected_sha256: str | None = None, timeout: float = 120.0
) -> Path:
    """Stream ``url`` to ``dest`` (atomic rename) and verify ``expected_sha256`` if given.

    An existing ``dest`` whose sha256 matches is reused without network access.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and expected_sha256 and sha256_file(dest) == expected_sha256:
        return dest
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "GridStorm-observed-pipeline/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp, tmp.open("wb") as fh:
        shutil.copyfileobj(resp, fh, length=1 << 20)
    if expected_sha256:
        got = sha256_file(tmp)
        if got != expected_sha256:
            tmp.unlink(missing_ok=True)
            raise ValueError(f"sha256 mismatch for {url}: expected {expected_sha256}, got {got}")
    tmp.replace(dest)
    return dest
