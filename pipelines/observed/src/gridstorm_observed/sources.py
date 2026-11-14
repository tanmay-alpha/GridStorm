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
    "for a complete list see URL). German load/generation: ENTSO-E Transparency Platform; "
    "German capacities: OPSD calculations based on BNetzA and netztransparenz.de."
)

#: German columns of the OPSD 60-min single-index CSV used here (all in MW).
OPSD_DE_COLUMNS = (
    "DE_load_actual_entsoe_transparency",
    "DE_solar_capacity",
    "DE_solar_generation_actual",
    "DE_wind_onshore_capacity",
    "DE_wind_onshore_generation_actual",
    "DE_wind_offshore_capacity",
    "DE_wind_offshore_generation_actual",
)

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
