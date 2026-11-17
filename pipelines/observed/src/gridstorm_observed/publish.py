"""Data Observatory publication pipeline: licence-gated, deterministic bundle ``data/observatory/``.

Entries (``DatasetEntry``, ``gridstorm-observatory/1.0``; contract in
``docs/data/observatory-pipeline.md``):

* ``opsd-de-load-forecast``: German day-ahead total load forecast (ENTSO-E Art. 6.1.b, CC BY 4.0)
  from the sha256-pinned OPSD 2020-10-06 CSV, hourly UTC 2015-01-01..2020-09-30;
* ``nasa-power-de-weather`` / ``nasa-power-de-renewable-resource``: NASA POWER hourly UTC T2M,
  WS10M / WS50M, ALLSKY_SFC_SW_DWN at four German city grid cells (the 2015 stress window and
  calendar year 2017, which contains both 2017 stress windows);
* ``nasa-power-de-daily``: GridStorm's daily means of complete UTC days of the same four
  parameters and points, computed from yearly hourly UTC requests over the load-forecast
  coverage 2015-01-01..2020-09-30;
* ``opsd-de-derived-multipliers``: the observed-analogue hourly demand multipliers;
* ``observed-analogue-scenarios``: metadata for the three StormSpec scenarios and their
  precomputed results.

Every series passes :func:`licence.gate`; restricted OPSD columns (actual load, actual
generation, capacities) are never read here except to verify the source checksum. Sources that
are not in the repository (the 130 MB OPSD CSV, raw POWER responses) are read from the cache when
present; otherwise the previous bundle's series are *carried forward* and re-checked (POWER
values against the committed request record, everything against the manifest).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import yaml

from . import bundle, licence, power_daily, power_hourly, sources
from .bundle import Series, Table, check

PIPELINE_VERSION = "gridstorm-observatory-publisher/1.0.0"
BUNDLE_VERSION = "2026-11-17.2"
REPO_BLOB = "https://github.com/tanmay-alpha/GridStorm/blob/main/"
COMMAND = (
    "cd pipelines/observed && uv run --locked python scripts/publish_observatory.py "
    "--out ../../data/observatory "
    '--opsd-csv "$GRIDSTORM_DATA_CACHE/opsd/time_series_60min_singleindex.csv"'
)
VERIFY_COMMAND = (
    "cd pipelines/observed && uv run --locked python scripts/publish_observatory.py "
    "--out ../../data/observatory --verify"
)
DOC_SOURCES = {
    "label": "Sources and licensing",
    "href": REPO_BLOB + "docs/data/sources-and-licensing.md",
}
DOC_PIPELINE = {
    "label": "Observatory pipeline",
    "href": REPO_BLOB + "docs/data/observatory-pipeline.md",
}
DOC_ANALOGUES = {
    "label": "Observed-analogue scenarios",
    "href": REPO_BLOB + "docs/research/observed-analogue-scenarios.md",
}
DOC_ENTSOE = {
    "label": "ENTSO-E re-use check",
    "href": REPO_BLOB + "docs/research/entsoe-reuse-check.md",
}

OPSD_ID = "opsd-de-load-forecast"
WEATHER_ID = "nasa-power-de-weather"
RESOURCE_ID = "nasa-power-de-renewable-resource"
DERIVED_ID = "opsd-de-derived-multipliers"
ANALOGUE_ID = "observed-analogue-scenarios"
DAILY_ID = "nasa-power-de-daily"

OPSD_START = datetime(2015, 1, 1, tzinfo=UTC)
OPSD_END = datetime(2020, 9, 30, 23, tzinfo=UTC)
#: Quality checks of the OPSD entry that need the source CSV (carried forward otherwise).
OPSD_SOURCE_CHECKS = (
    "source_sha256",
    "source_utc_format",
    "source_no_duplicates",
    "source_hourly_grid",
    "dst_free_utc",
    "coverage_trim",
)
DERIVED_PATH = sources.OPSD_OUT_DIR / "derived-multipliers.json"
OPSD_MANIFEST_PATH = sources.OPSD_OUT_DIR / "manifest.json"
RESULTS_PATH = sources.OBSERVED_DIR / "analogue-results.json"
OLD_EXTRACT_PATH = sources.POWER_OUT_DIR / "t2m_ws10m_hourly.csv"
#: Studio presets that must stay byte-identical copies of data/scenarios/observed/*.yaml.
PRESET_DIR = sources.REPO_ROOT / "packages" / "stormspec" / "presets"
#: The representative observed-analogue preset offered by "use in scenario".
ANALOGUE_PRESET = "observed-dunkelflaute-2015-01-20"


@dataclass
class Inputs:
    opsd_csv: Path | None = None
    power_cache: Path | None = None
    previous: Path | None = None
    power_record: Path = power_hourly.RECORD_PATH
    power_daily_record: Path = power_daily.RECORD_PATH
    bundle_version: str = BUNDLE_VERSION


@dataclass
class Built:
    entry: dict
    series: list[Series] = field(default_factory=list)
    table: Table | None = None


@dataclass
class Result:
    files: dict[str, bytes]
    notes: list[str]


# --- helpers --------------------------------------------------------------------------------


def _rel(path: Path) -> str:
    return path.resolve().relative_to(sources.REPO_ROOT).as_posix()


def _sha_file(path: Path) -> str:
    return sources.sha256_file(path)


def _day(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=UTC)


def stress_windows() -> list[dict]:
    out = []
    for day, label in power_hourly.STRESS_DAYS:
        d = _day(day)
        pad = timedelta(days=power_hourly.WINDOW_PAD_DAYS)
        out.append(
            {
                "start_utc": bundle.fmt_utc(d - pad),
                "end_utc": bundle.fmt_utc(d + pad + timedelta(hours=23)),
                "label": f"{label} ±{power_hourly.WINDOW_PAD_DAYS} d",
            }
        )
    return out


def _entry(**kw: object) -> dict:
    entry = {k: kw.pop(k) for k in bundle.ENTRY_KEYS if k in kw}
    if kw:
        raise TypeError(f"unknown entry keys {sorted(kw)}")
    return entry


def _quality(
    table: Table | None, expected: list[datetime], checks: list[dict], warnings: list[str]
) -> dict:
    if table is None:
        q = {
            "rows": None,
            "expected_rows": None,
            "completeness_pct": None,
            "missing_values": {},
            "missing_policy": "kept-as-null",
        }
    else:
        q = bundle.table_quality(table, expected)
    q["checks"] = checks
    q["warnings"] = warnings
    return q


def _previous_table(inputs: Inputs, dataset_id: str) -> tuple[Table, dict]:
    if inputs.previous is None:
        raise FileNotFoundError(f"{dataset_id}: source not available and no previous bundle")
    prev = inputs.previous
    catalog = json.loads((prev / "catalog.json").read_text("utf-8"))
    entry = next((e for e in catalog["entries"] if e["id"] == dataset_id), None)
    if entry is None:
        raise FileNotFoundError(f"{dataset_id}: not in the previous bundle")
    manifest = json.loads((prev / "manifest.json").read_text("utf-8"))
    data = (prev / entry["artifact"]["path"]).read_bytes()
    listed = {f["path"]: f["sha256"] for f in manifest["files"]}
    if listed.get(entry["artifact"]["path"]) != bundle.sha256(data):
        raise ValueError(f"{dataset_id}: previous series file does not match its manifest")
    _, table = bundle.read_csv(data)
    return table, entry


# --- OPSD day-ahead load forecast -----------------------------------------------------------


def opsd_series(decimals: int) -> list[Series]:
    return [
        Series(
            id="de_load_forecast",
            label="Germany: day-ahead total load forecast",
            unit="MW",
            quantity="day-ahead forecast of total load (hourly mean)",
            location_id=None,
            decimals=decimals,
            source_key=f"{licence.OPSD_SOURCE}:{sources.OPSD_LOAD_FORECAST_COL}",
        )
    ]


def load_opsd(
    csv_path: Path,
    expected_sha256: str = sources.OPSD_CSV_SHA256,
    start: datetime = OPSD_START,
    end: datetime = OPSD_END,
) -> tuple[Table, list[dict]]:
    """Forecast column on the UTC calendar-day grid 2015-01-01..2020-09-30 plus source checks.

    Only ``utc_timestamp``, ``cet_cest_timestamp`` and the forecast column are read.
    """
    digest = _sha_file(csv_path)
    if digest != expected_sha256:
        raise ValueError(f"{csv_path}: sha256 {digest} != pinned {expected_sha256}")
    col = sources.OPSD_LOAD_FORECAST_COL
    df = pd.read_csv(
        csv_path,
        usecols=["utc_timestamp", "cet_cest_timestamp", col],
        dtype=str,
        keep_default_na=False,
    )
    checks = [
        check("source_sha256", "pass", f"source CSV sha256 {digest} matches the pinned value")
    ]
    utc_txt = df["utc_timestamp"].tolist()
    bad_fmt = [t for t in utc_txt if not bundle.UTC_RE.match(t)]
    checks.append(
        check(
            "source_utc_format",
            "pass" if not bad_fmt else "fail",
            f"{len(utc_txt) - len(bad_fmt)}/{len(utc_txt)} utc_timestamp values are "
            "ISO-8601 with 'Z'",
        )
    )
    if bad_fmt:
        raise ValueError(f"OPSD utc_timestamp not in Z form, e.g. {bad_fmt[0]!r}")
    utc = [bundle.parse_utc(t) for t in utc_txt]
    dupes = len(utc) - len(set(utc))
    checks.append(
        check(
            "source_no_duplicates", "pass" if not dupes else "fail", f"{dupes} duplicate UTC hours"
        )
    )
    steps = {b - a for a, b in zip(utc, utc[1:], strict=False)}
    checks.append(
        check(
            "source_hourly_grid",
            "pass" if steps == {bundle.HOUR} else "fail",
            f"{len(utc)} source rows {bundle.fmt_utc(utc[0])}..{bundle.fmt_utc(utc[-1])}, "
            f"step(s) {sorted(str(s) for s in steps)}",
        )
    )
    local = [datetime.strptime(t, "%Y-%m-%dT%H:%M:%S%z") for t in df["cet_cest_timestamp"]]
    offsets = [x.utcoffset() for x in local]
    consistent = all(x.astimezone(UTC) == u for x, u in zip(local, utc, strict=True))
    allowed = {timedelta(hours=1), timedelta(hours=2)}
    switches = sum(a != b for a, b in zip(offsets, offsets[1:], strict=False))
    dst_ok = consistent and set(offsets) <= allowed and steps == {bundle.HOUR} and not dupes
    checks.append(
        check(
            "dst_free_utc",
            "pass" if dst_ok else "fail",
            f"UTC index strictly hourly across {switches} CET/CEST offset changes; every "
            "cet_cest_timestamp converts to its utc_timestamp; no repeated or skipped UTC hour",
        )
    )
    raw = df[col].tolist()
    keep = [i for i, t in enumerate(utc) if start <= t <= end]
    kept = set(keep)
    dropped = [i for i in range(len(utc)) if i not in kept]
    dropped_desc = ", ".join(
        f"{bundle.fmt_utc(utc[i])} ({'empty' if raw[i] == '' else 'value'} in source)"
        for i in dropped
    )
    checks.append(
        check(
            "coverage_trim",
            "pass",
            f"published UTC calendar days {bundle.fmt_utc(start)}..{bundle.fmt_utc(end)}; "
            f"dropped {len(dropped)} source row(s): {dropped_desc or 'none'}",
        )
    )
    values = [None if raw[i] == "" else float(raw[i]) for i in keep]
    table = Table([utc[i] for i in keep], {"de_load_forecast": values})
    if table.timestamps != bundle.hourly_range(start, end):
        raise ValueError("OPSD source does not cover the published hourly grid")
    return table, checks


def opsd_entry(table: Table, source_checks: list[dict], opsd_manifest: dict) -> Built:
    vals = [v for v in table.values["de_load_forecast"] if v is not None]
    integral = all(float(v).is_integer() for v in vals)
    series = opsd_series(0 if integral else 4)
    expected = bundle.hourly_range(OPSD_START, OPSD_END)
    checks = list(source_checks)
    checks.append(
        check(
            "integer_valued",
            "pass" if integral else "warn",
            "every value is a whole MW in the source (written without decimals)"
            if integral
            else "non-integer source values (written with 4 decimals)",
        )
    )
    checks += bundle.grid_checks(table, expected)
    checks.append(bundle.range_check(table, series, 20000, 100000, "plausible_range_mw"))
    missing = sum(v is None for v in table.values["de_load_forecast"])
    warnings = [
        "Forecast, not measured load: the TSOs' day-ahead estimate differs from the actual load "
        "by the forecast error; actual load is not published (not openly licensed).",
    ]
    if missing:
        warnings.append(f"{missing} hourly values are missing in the source and kept empty.")
    src = opsd_manifest["source"]
    rec = licence.gate(series[0].source_key)
    entry = _entry(
        id=OPSD_ID,
        title="Germany day-ahead total load forecast (ENTSO-E via OPSD), 2015–2020",
        summary="Hourly German day-ahead total load forecast in MW, UTC, 2015-01-01 to 2020-09-30.",
        description=(
            "Day-ahead forecast of the total load per market time unit for Germany "
            "(Reg. (EU) 543/2013 Art. 6.1.b) as published on the ENTSO-E Transparency Platform and "
            f"packaged by Open Power System Data (time series {sources.OPSD_VERSION}, column "
            f"`{sources.OPSD_LOAD_FORECAST_COL}`).\n\n"
            "This is the TSOs' forecast, **not measured load**. It is the only OPSD load column on "
            "ENTSO-E's free re-use list (item #1, CC BY 4.0); actual load, actual generation and "
            "capacities are not published here. Values are unchanged; missing hours stay empty. "
            "It is the demand input of the observed-analogue scenarios."
        ),
        category="historical_demand",
        provenance="estimated",
        data_nature="TSO day-ahead total load forecast (ENTSO-E Art. 6.1.b), not measured load",
        region={"code": "DE", "name": "Germany", "kind": "country"},
        source={
            "name": f"Open Power System Data – Time series {sources.OPSD_VERSION} "
            f"({sources.OPSD_LOAD_FORECAST_COL})",
            "publisher": "Open Power System Data; primary data: ENTSO-E Transparency Platform",
            "url": sources.OPSD_CSV_URL,
            "version": sources.OPSD_VERSION,
            "doi": sources.OPSD_DOI,
            "retrieved_at": src["retrieved_at"],
            "source_sha256": src["sha256"],
            "license": {
                "id": rec.licence_id,
                "name": rec.licence_name,
                "url": rec.licence_url,
                "redistribution": rec.redistribution,
            },
            "attribution": (
                "Day-ahead forecast of the total load per market time unit, Germany (Reg. (EU) "
                "543/2013 Art. 6.1.b), ENTSO-E Transparency Platform "
                "(https://transparency.entsoe.eu/), "
                f"obtained via Open Power System Data, Time series {sources.OPSD_VERSION} "
                f"({sources.OPSD_DOI}), column {sources.OPSD_LOAD_FORECAST_COL}. Licensed under "
                f"CC BY 4.0 ({sources.CC_BY_4_URL}) per the ENTSO-E list of data available for "
                "free "
                f"re-use ({sources.ENTSOE_REUSE_LIST_VERSION}), item #1. Modified by GridStorm: "
                "column extracted; restricted to UTC calendar days 2015-01-01..2020-09-30; "
                "timestamps reformatted; whole-MW values written without decimals. No value "
                "altered, filled or interpolated."
            ),
        },
        temporal={
            "start_utc": bundle.fmt_utc(OPSD_START),
            "end_utc": bundle.fmt_utc(OPSD_END),
            "resolution": "PT1H",
            "timezone": "UTC",
            "windows": stress_windows(),
        },
        spatial={"kind": "region", "points": None},
        series=[s.public() for s in series],
        quality=_quality(table, expected, checks, warnings),
        transformations=[
            {
                "step": "verify",
                "description": "sha256 of the cached OPSD CSV equals the datapackage.json hash "
                "pinned in data/observed/opsd-de/manifest.json",
            },
            {
                "step": "select",
                "description": "read utc_timestamp, cet_cest_timestamp and "
                f"{sources.OPSD_LOAD_FORECAST_COL} only",
            },
            {
                "step": "check",
                "description": "UTC format, duplicates, hourly grid, CET/CEST consistency, range",
            },
            {
                "step": "trim",
                "description": "keep UTC calendar days 2015-01-01..2020-09-30 "
                "(hour-start timestamps)",
            },
            {"step": "write", "description": "wide CSV; empty cell = missing; whole MW"},
        ],
        transformation_version="opsd-de-load-forecast/1.0.0",
        artifact=None,
        links={
            "network_id": None,
            "scenario_ids": _scenario_ids(),
            "study_route": None,
            "docs": [DOC_SOURCES, DOC_ENTSOE, DOC_ANALOGUES],
        },
        use_in_scenario={
            "available": False,
            "network_id": None,
            "preset_id": None,
            "route": None,
            "rationale": "A national MW series has no validated mapping onto a network's buses. "
            "Its only validated use is the observed-analogue mapping onto scigrid-de; see "
            f"{ANALOGUE_ID}.",
        },
        exportable=True,
    )
    return Built(entry, series, table)


# --- NASA POWER -----------------------------------------------------------------------------

POWER_META = {
    "T2M": ("t2m", "2 m air temperature", "°C", "air temperature at 2 m (hourly mean)", 2),
    "WS10M": ("ws10m", "10 m wind speed", "m/s", "wind speed at 10 m (hourly mean)", 2),
    "WS50M": ("ws50m", "50 m wind speed", "m/s", "wind speed at 50 m (hourly mean)", 2),
    "ALLSKY_SFC_SW_DWN": (
        "ghi",
        "all-sky GHI",
        "Wh/m²",
        "all-sky surface shortwave downward irradiance, GHI (hourly; Wh/m² per hour = mean W/m²)",
        2,
    ),
}
POWER_RANGES = {
    "T2M": (-45.0, 45.0),
    "WS10M": (0.0, 60.0),
    "WS50M": (0.0, 75.0),
    "ALLSKY_SFC_SW_DWN": (0.0, 1400.0),
}


def power_series(params: tuple[str, ...]) -> list[Series]:
    out = []
    for p in sources.POWER_POINTS:
        for param in params:
            key, label, unit, quantity, dec = POWER_META[param]
            out.append(
                Series(
                    id=f"{p.id}_{key}",
                    label=f"{p.name}: {label} ({param})",
                    unit=unit,
                    quantity=quantity,
                    location_id=p.id,
                    decimals=dec,
                    source_key=f"{licence.POWER_SOURCE}:{param}",
                )
            )
    return out


def power_expected() -> list[datetime]:
    hours: list[datetime] = []
    for a, b in power_hourly.RANGES:
        start = datetime.strptime(a, "%Y%m%d").replace(tzinfo=UTC)
        end = datetime.strptime(b, "%Y%m%d").replace(tzinfo=UTC) + timedelta(hours=23)
        hours += bundle.hourly_range(start, end)
    return hours


def _param_of(series_id: str) -> str:
    key = series_id.split("_", 1)[1]
    return next(p for p, m in POWER_META.items() if m[0] == key)


def power_tables(
    by_point: dict[str, dict[str, dict]], params_by_entry: dict[str, tuple[str, ...]]
) -> dict[str, Table]:
    expected = power_expected()
    out = {}
    for eid, params in params_by_entry.items():
        cols = {}
        for s in power_series(params):
            col = by_point[s.location_id][_param_of(s.id)]
            cols[s.id] = [col.get(t) for t in expected]
        out[eid] = Table(list(expected), cols)
    return out


def tables_to_points(tables: list[Table]) -> dict[str, dict[str, dict]]:
    by_point: dict[str, dict[str, dict]] = {}
    for table in tables:
        for sid, col in table.values.items():
            point = sid.split("_", 1)[0]
            dest = by_point.setdefault(point, {})
            dest[_param_of(sid)] = dict(zip(table.timestamps, col, strict=True))
    return by_point


def check_power_record(record: dict, by_point: dict[str, dict[str, dict]]) -> None:
    """Every request's canonical-values sha256 must equal the committed record."""
    for rec in record["requests"]:
        start = datetime.strptime(rec["start"], "%Y%m%d").replace(tzinfo=UTC)
        end = datetime.strptime(rec["end"], "%Y%m%d").replace(tzinfo=UTC) + timedelta(hours=23)
        cols = {
            p: {t: v for t, v in by_point[rec["point"]][p].items() if start <= t <= end}
            for p in power_hourly.PARAMETERS
        }
        if power_hourly.values_digest(rec["point"], cols) != rec["values_sha256"]:
            raise ValueError(
                f"POWER values for {rec['point']} {rec['start']}..{rec['end']} differ from the "
                "committed request record"
            )


def _old_extract_check(table: Table) -> dict:
    """Compare T2M/WS10M with the extract committed on 2026-11-14 (same API, same points)."""
    df = pd.read_csv(OLD_EXTRACT_PATH, dtype={"point": str})
    idx = {t: i for i, t in enumerate(table.timestamps)}
    n = same = 0
    worst = 0.0
    for row in df.itertuples(index=False):
        t = datetime.strptime(row.utc, "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC)
        for param, key in (("T2M", "t2m"), ("WS10M", "ws10m")):
            new = table.values[f"{row.point}_{key}"][idx[t]]
            old = getattr(row, param)
            n += 1
            if new is not None and abs(new - old) < 1e-9:
                same += 1
            elif new is not None:
                worst = max(worst, abs(new - old))
    status = "pass" if same == n else "warn"
    detail = (
        f"{same}/{n} T2M/WS10M values identical to data/observed/nasa-power-de extract (2026-11-14)"
    )
    if same != n:
        detail += f"; max abs difference {worst:.2f}"
    return check("consistent_with_previous_extract", status, detail)


def power_points() -> list[dict]:
    return [
        {
            "id": p.id,
            "name": p.name,
            "lat": p.lat,
            "lon": p.lon,
            "grid_note": "Coordinates as requested from the POWER point API (city centre). POWER "
            "returns the source grid cell containing them: MERRA-2 0.5° × 0.625° for T2M/WS10M/"
            "WS50M; CERES SYN1deg 1° × 1° for ALLSKY_SFC_SW_DWN. Not a station.",
        }
        for p in sources.POWER_POINTS
    ]


def _power_provenance(reqs: list[dict]) -> tuple[list[str], list[str], str | None, str]:
    """API versions, header sources, last retrieval time and the access date (YYYY/MM/DD)."""
    versions = sorted({r["api"]["version"] for r in reqs})
    header_sources = sorted({s for r in reqs for s in r["header_sources"]})
    retrieved = sorted(r["retrieved_at"] for r in reqs if r["retrieved_at"])
    last = retrieved[-1] if retrieved else None
    accessed = last[:10].replace("-", "/") if last else "unknown date"
    return versions, header_sources, last, accessed


def power_entries(record: dict, tables: dict[str, Table], record_sha: str) -> list[Built]:
    reqs = record["requests"]
    versions, header_sources, last, accessed = _power_provenance(reqs)
    expected = power_expected()
    points = power_points()
    attribution = (
        "The data was obtained from National Aeronautics and Space Administration (NASA) Langley "
        "Research Center's Prediction Of Worldwide Energy Resources (POWER) project funded through "
        "the NASA Earth Science Division. The data was obtained from the POWER Project's Hourly "
        f"{', '.join(versions)} version on {accessed}. Modified by GridStorm: hourly UTC values of "
        "four city grid cells reshaped to one wide CSV; fill value -999 written as empty cells; no "
        "value altered or interpolated. No endorsement by NASA is implied."
    )
    common_warn = [
        "Modeled grid-cell values (reanalysis / satellite-derived), not station measurements.",
        "Rows cover 2015-01-17..2015-01-23 and calendar year 2017 only; hours in between were not "
        "requested (not covered, not missing).",
        "Timestamps are POWER's UTC hour labels (YYYYMMDDHH) written as hour start; POWER "
        "documents "
        "hourly average values; the alignment of the averaging interval within the hour was not "
        "verified.",
    ]
    fills = {p: sum(r["fill_values_replaced"][p] for r in reqs) for p in power_hourly.PARAMETERS}

    def build(eid: str, params: tuple[str, ...], **kw: object) -> Built:
        series = power_series(params)
        table = tables[eid]
        rec = licence.gate(series[0].source_key)
        checks = [
            check(
                "time_standard_utc",
                "pass"
                if all(
                    r["time_standard"] == "UTC" and "time-standard=UTC" in r["url"] for r in reqs
                )
                else "fail",
                f"{len(reqs)} requests with time-standard=UTC; every response header says UTC",
            ),
            check(
                "values_match_request_record",
                "pass",
                f"canonical values of all {len(reqs)} requests hash to the values_sha256 in "
                f"{_rel(power_hourly.RECORD_PATH)}",
            ),
            check(
                "api_version",
                "pass",
                f"POWER Hourly API {', '.join(versions)}; "
                f"header sources {', '.join(header_sources)}",
            ),
            check(
                "fill_values",
                "pass",
                "fill value -999 replaced by empty cells: "
                + ", ".join(f"{p} {fills[p]}" for p in params),
            ),
        ]
        checks += bundle.grid_checks(table, expected)
        for param in params:
            lo, hi = POWER_RANGES[param]
            sel = [s for s in series if _param_of(s.id) == param]
            checks.append(
                bundle.range_check(table, sel, lo, hi, f"plausible_range_{param.lower()}")
            )
        extra_checks = kw.pop("extra_checks", [])
        checks += extra_checks
        warnings = common_warn + list(kw.pop("warnings", []))
        return Built(
            _entry(
                id=eid,
                category=kw.pop("category"),
                title=kw.pop("title"),
                summary=kw.pop("summary"),
                description=kw.pop("description"),
                data_nature=kw.pop("data_nature"),
                provenance="modeled",
                region={"code": "DE", "name": "Germany (4 city grid cells)", "kind": "points"},
                source={
                    "name": "NASA POWER Hourly API (point, community RE, time-standard=UTC)",
                    "publisher": "NASA Langley Research Center, POWER Project",
                    "url": sources.POWER_HOURLY_URL,
                    "version": ", ".join(versions),
                    "doi": None,
                    "retrieved_at": last,
                    "source_sha256": record_sha,
                    "license": {
                        "id": rec.licence_id,
                        "name": rec.licence_name,
                        "url": rec.licence_url,
                        "redistribution": rec.redistribution,
                    },
                    "attribution": attribution,
                },
                temporal={
                    "start_utc": bundle.fmt_utc(expected[0]),
                    "end_utc": bundle.fmt_utc(expected[-1]),
                    "resolution": "PT1H",
                    "timezone": "UTC",
                    "windows": stress_windows(),
                },
                spatial={"kind": "points", "points": points},
                series=[s.public() for s in series],
                quality=_quality(table, expected, checks, warnings),
                transformations=[
                    {
                        "step": "request",
                        "description": f"{len(reqs)} sequential point requests (4 points × 2 date "
                        "ranges), parameters T2M, WS10M, WS50M, ALLSKY_SFC_SW_DWN, community RE, "
                        "format JSON, time-standard=UTC",
                    },
                    {
                        "step": "record",
                        "description": "URL, response sha256, API version, header sources, fill "
                        "counts and canonical-values sha256 per request in "
                        f"{_rel(power_hourly.RECORD_PATH)}",
                    },
                    {
                        "step": "parse",
                        "description": "YYYYMMDDHH (UTC) -> ISO-8601 hour start; -999 -> empty",
                    },
                    {
                        "step": "write",
                        "description": "wide CSV, one column per point and parameter",
                    },
                ],
                transformation_version=f"{eid}/1.0.0",
                artifact=None,
                links={
                    "network_id": None,
                    "scenario_ids": _scenario_ids(),
                    "study_route": None,
                    "docs": [DOC_SOURCES, DOC_ANALOGUES],
                },
                use_in_scenario={
                    "available": False,
                    "network_id": None,
                    "preset_id": None,
                    "route": None,
                    "rationale": "No validated mapping from these point weather/resource series "
                    "to a network input (GridStorm has no validated weather-to-availability "
                    "model). The only validated scenario use of observed data is the three "
                    f"observed-analogue scenarios on scigrid-de; see {ANALOGUE_ID}.",
                },
                exportable=True,
            ),
            series,
            table,
        )

    weather = build(
        WEATHER_ID,
        ("T2M", "WS10M"),
        category="weather_reanalysis",
        title="NASA POWER hourly temperature and 10 m wind, four German cities (UTC)",
        summary="Hourly MERRA-2 2 m temperature and 10 m wind speed at Berlin, Hamburg, Cologne "
        "and Munich grid cells around the observed stress days and for 2017.",
        description=(
            "Hourly `T2M` (°C) and `WS10M` (m/s) from the NASA POWER Hourly API, requested with "
            "`time-standard=UTC` (the API defaults to local solar time). Values are MERRA-2 "
            "reanalysis averages over the 0.5° × 0.625° grid cell containing each city centre — "
            "**modeled, not station data**.\n\n"
            "Coverage: the Dunkelflaute window 2015-01-17..23 and calendar year 2017 (which "
            "contains the 2017-01-24 and 2017-12-13 stress windows)."
        ),
        data_nature="MERRA-2 reanalysis via NASA POWER (grid-cell values, not station data)",
        extra_checks=[_old_extract_check(tables[WEATHER_ID])],
    )
    resource = build(
        RESOURCE_ID,
        ("WS50M", "ALLSKY_SFC_SW_DWN"),
        category="renewable_resource",
        title="NASA POWER hourly 50 m wind and solar irradiance, four German cities (UTC)",
        summary="Hourly 50 m wind speed (MERRA-2) and all-sky GHI (CERES SYN1deg) at Berlin, "
        "Hamburg, Cologne and Munich grid cells around the observed stress days and for 2017.",
        description=(
            "Hourly `WS50M` (m/s, MERRA-2, 0.5° × 0.625°) and `ALLSKY_SFC_SW_DWN` (all-sky global "
            "horizontal irradiance, Wh/m² per hour = mean W/m²; CERES SYN1deg Ed4.2, 1° × 1°) from "
            "the NASA POWER Hourly API with `time-standard=UTC`. **Modeled resource indicators, "
            "not "
            "station data and not power output**: 50 m is above the grid cell's mean elevation, "
            "not a turbine hub height.\n\n"
            "Coverage: 2015-01-17..23 and calendar year 2017."
        ),
        data_nature="MERRA-2 reanalysis wind and CERES SYN1deg satellite-derived irradiance via "
        "NASA POWER (grid-cell values, not station data)",
        warnings=[
            "Resource indicators only: no conversion to capacity factors or generation is made.",
        ],
    )
    return [weather, resource]


def load_power(inputs: Inputs) -> tuple[dict, str, dict[str, Table], str]:
    record_path = inputs.power_record
    if not record_path.exists():
        raise FileNotFoundError(f"{record_path} missing: run with --fetch-nasa first")
    record = json.loads(record_path.read_text("utf-8"))
    record_sha = _sha_file(record_path)
    params = {WEATHER_ID: ("T2M", "WS10M"), RESOURCE_ID: ("WS50M", "ALLSKY_SFC_SW_DWN")}
    cache = inputs.power_cache
    by_point = power_hourly.load_cached(record, cache) if cache and cache.exists() else None
    if by_point is not None:
        how = "re-derived from cached raw POWER responses (sha256 = request record)"
    else:
        prev = [_previous_table(inputs, eid)[0] for eid in params]
        by_point = tables_to_points(prev)
        how = "carried forward from the previous bundle (raw responses not cached)"
    check_power_record(record, by_point)
    return record, record_sha, power_tables(by_point, params), how


# --- NASA POWER daily means of UTC days -----------------------------------------------------

DAILY_META = {
    "T2M": (
        "2 m air temperature, daily mean",
        "°C",
        "air temperature at 2 m (mean of the 24 hourly values of the UTC day)",
    ),
    "WS10M": (
        "10 m wind speed, daily mean",
        "m/s",
        "wind speed at 10 m (mean of the 24 hourly values of the UTC day)",
    ),
    "WS50M": (
        "50 m wind speed, daily mean",
        "m/s",
        "wind speed at 50 m (mean of the 24 hourly values of the UTC day)",
    ),
    "ALLSKY_SFC_SW_DWN": (
        "all-sky GHI, daily mean irradiance",
        "W/m²",
        "all-sky surface shortwave downward irradiance, GHI: mean irradiance over the UTC day "
        "(mean of the 24 hourly Wh/m² values = W/m²; × 24 h = daily insolation in Wh/m²)",
    ),
}
#: Plausible ranges of German daily means (wider than any observed daily mean).
DAILY_RANGES = {
    "T2M": (-35.0, 40.0),
    "WS10M": (0.0, 40.0),
    "WS50M": (0.0, 50.0),
    "ALLSKY_SFC_SW_DWN": (0.0, 450.0),
}


def daily_series() -> list[Series]:
    out = []
    for p in sources.POWER_POINTS:
        for param in power_hourly.PARAMETERS:
            label, unit, quantity = DAILY_META[param]
            out.append(
                Series(
                    id=f"{p.id}_{POWER_META[param][0]}",
                    label=f"{p.name}: {label} ({param})",
                    unit=unit,
                    quantity=quantity,
                    location_id=p.id,
                    decimals=power_daily.DECIMALS,
                    source_key=f"{licence.POWER_SOURCE}:{param}",
                )
            )
    return out


def daily_table(by_point: dict[str, dict[str, dict]]) -> Table:
    """Daily means of complete UTC days (:mod:`power_daily` rule) on the full coverage grid,
    held at the published precision so a carried-forward table is identical."""
    grid = power_daily.days()

    def published(v: float | None) -> float | None:
        return None if v is None else float(bundle.fmt_num(v, power_daily.DECIMALS))

    cols = {}
    for s in daily_series():
        col = by_point[s.location_id][_param_of(s.id)]
        cols[s.id] = [published(v) for v in power_daily.daily_means(col, grid)]
    return Table(grid, cols)


def check_daily_record(
    record: dict, table: Table, by_point: dict[str, dict[str, dict]] | None = None
) -> None:
    """The record lists exactly the pipeline's yearly requests; each request's daily means (and,
    given the hourly values, its hourly values) hash to the record; incomplete days match."""
    if [r["url"] for r in record["requests"]] != [r.url for r in power_daily.requests()]:
        raise ValueError("daily request record does not list the pipeline's yearly requests")
    if by_point is not None:
        check_power_record(record, by_point)
    idx = {t: i for i, t in enumerate(table.timestamps)}
    for rec in record["requests"]:
        grid = power_daily.request_days(rec["start"], rec["end"])
        missing = [d for d in grid if d not in idx]
        if missing:
            raise ValueError(f"daily table lacks {len(missing)} days of {rec['start']}")
        daily = {
            p: [table.values[f"{rec['point']}_{POWER_META[p][0]}"][idx[d]] for d in grid]
            for p in power_hourly.PARAMETERS
        }
        incomplete = {
            p: [f"{d:%Y-%m-%d}" for d, v in zip(grid, daily[p], strict=True) if v is None]
            for p in power_hourly.PARAMETERS
        }
        if (
            power_daily.daily_digest(rec["point"], daily, grid) != rec["daily_values_sha256"]
            or incomplete != rec["incomplete_days"]
        ):
            raise ValueError(
                f"POWER daily means for {rec['point']} {rec['start']}..{rec['end']} differ from "
                "the committed request record"
            )


def load_power_daily(inputs: Inputs) -> tuple[dict, str, Table, str]:
    path = inputs.power_daily_record
    if not path.exists():
        raise FileNotFoundError(f"{path} missing: run with --fetch-nasa first")
    record = json.loads(path.read_text("utf-8"))
    record_sha = _sha_file(path)
    cache = inputs.power_cache
    by_point = power_hourly.load_cached(record, cache) if cache and cache.exists() else None
    if by_point is not None:
        table = daily_table(by_point)
        how = "re-derived from cached raw POWER responses (sha256 = daily request record)"
    else:
        table = _previous_table(inputs, DAILY_ID)[0]
        how = "carried forward from the previous bundle (raw responses not cached)"
    check_daily_record(record, table, by_point)
    return record, record_sha, table, how


def _daily_vs_hourly_check(table: Table, hourly: dict[str, Table]) -> dict:
    """Daily means recomputed from the published hourly entries must equal the daily entry."""
    by_point = tables_to_points([hourly[WEATHER_ID], hourly[RESOURCE_ID]])
    covered = set(hourly[WEATHER_ID].timestamps)
    days = [d for d in table.timestamps if d in covered and d + timedelta(hours=23) in covered]
    idx = {t: i for i, t in enumerate(table.timestamps)}
    n = same = 0
    worst = 0.0
    for s in daily_series():
        col = by_point[s.location_id][_param_of(s.id)]
        for d in days:
            got = table.values[s.id][idx[d]]
            want = power_daily.day_mean(col, d)
            n += 1
            if bundle.fmt_num(got, s.decimals) == bundle.fmt_num(want, s.decimals):
                same += 1
            elif got is not None and want is not None:
                worst = max(worst, abs(got - want))
    detail = (
        f"{same}/{n} daily means (on the {len(days)} UTC days also covered by {WEATHER_ID} and "
        f"{RESOURCE_ID}) equal the means recomputed from those hourly entries"
    )
    if same != n:
        detail += f"; max abs difference {worst:.2f} (different POWER responses)"
    return check("consistent_with_hourly_entries", "pass" if same == n else "warn", detail)


def daily_entry(
    record: dict, table: Table, record_sha: str, hourly: dict[str, Table], record_path: Path
) -> Built:
    reqs = record["requests"]
    versions, header_sources, last, accessed = _power_provenance(reqs)
    grid = power_daily.days()
    series = daily_series()
    rec = licence.gate(series[0].source_key)
    params = power_hourly.PARAMETERS
    years = sorted({r["start"][:4] for r in reqs})
    fills = {p: sum(r["fill_values_replaced"][p] for r in reqs) for p in params}
    incomplete = {p: sum(len(r["incomplete_days"][p]) for r in reqs) for p in params}
    short = [
        f"{r['point']} {r['start']}..{r['end']}"
        for r in reqs
        if r["hours"] != 24 * len(power_daily.request_days(r["start"], r["end"]))
    ]
    midnight = all((t.hour, t.minute, t.second) == (0, 0, 0) for t in table.timestamps)
    span = f"{grid[0]:%Y-%m-%d}..{grid[-1]:%Y-%m-%d}"
    checks = [
        check(
            "time_standard_utc",
            "pass"
            if all(r["time_standard"] == "UTC" and "time-standard=UTC" in r["url"] for r in reqs)
            else "fail",
            f"{len(reqs)} hourly requests with time-standard=UTC; every response header says UTC; "
            "NASA's daily endpoint (non-UTC days) is not used",
        ),
        check(
            "values_match_request_record",
            "pass",
            f"daily means of all {len(reqs)} requests hash to the daily_values_sha256 in "
            f"{_rel(record_path)} (and, when the raw responses are cached, their hourly values "
            "to values_sha256)",
        ),
        check(
            "api_version",
            "pass",
            f"POWER Hourly API {', '.join(versions)}; header sources {', '.join(header_sources)}",
        ),
        check(
            "requested_hours",
            "pass" if not short else "warn",
            f"every response has 24 hourly values per requested UTC day ({len(reqs)} requests: "
            f"{len(sources.POWER_POINTS)} points × calendar years {years[0]}–{years[-1]}, "
            f"{span})"
            if not short
            else f"responses with fewer hours than 24 × days: {', '.join(short)}",
        ),
        check(
            "fill_values",
            "pass",
            "fill value -999 treated as missing before aggregation: "
            + ", ".join(f"{p} {fills[p]} h" for p in params),
        ),
        check(
            "complete_day_rule",
            "pass" if not any(incomplete.values()) else "warn",
            f"{power_daily.RULE}; incomplete days left empty (of {len(grid)} days × "
            f"{len(sources.POWER_POINTS)} points): "
            + ", ".join(f"{p} {incomplete[p]}" for p in params),
        ),
        check(
            "utc_day_boundaries",
            "pass" if midnight else "fail",
            "every row is a UTC day start (00:00:00Z) and its value aggregates the POWER UTC "
            "hour labels 00..23 of that date (no local-time or solar-time day)",
        ),
        check(
            "coverage_matches_load_forecast",
            "pass"
            if (grid[0], grid[-1] + timedelta(hours=23)) == (OPSD_START, OPSD_END)
            else "fail",
            f"UTC days {span} = the UTC calendar days of {OPSD_ID}",
        ),
    ]
    checks += bundle.grid_checks(table, grid, bundle.DAY)
    for param in params:
        lo, hi = DAILY_RANGES[param]
        sel = [s for s in series if _param_of(s.id) == param]
        checks.append(bundle.range_check(table, sel, lo, hi, f"plausible_range_{param.lower()}"))
    checks.append(_daily_vs_hourly_check(table, hourly))
    warnings = [
        "Modeled grid-cell values (reanalysis / satellite-derived), not station measurements.",
        "Daily means computed by GridStorm from POWER's hourly UTC values, not NASA's daily "
        "product (whose days are not UTC days). A day with any missing hour is left empty.",
        "ALLSKY_SFC_SW_DWN is a daily mean irradiance in W/m², not an energy: multiply by 24 h "
        "for the daily insolation in Wh/m².",
        f"Same UTC days as {OPSD_ID} (whose P1D view uses the same UTC day buckets): compare "
        "seasonal and year-to-year patterns only; weather at four grid cells neither explains "
        "nor predicts national demand here (no causal claim).",
        "POWER documents hourly average values labelled YYYYMMDDHH (UTC); the alignment of the "
        "averaging interval within the hour was not verified, so a UTC day may be offset by up "
        "to one hour.",
    ]
    attribution = (
        "The data was obtained from National Aeronautics and Space Administration (NASA) Langley "
        "Research Center's Prediction Of Worldwide Energy Resources (POWER) project funded through "
        "the NASA Earth Science Division. The data was obtained from the POWER Project's Hourly "
        f"{', '.join(versions)} version on {accessed}. Modified by GridStorm: hourly UTC values of "
        "four city grid cells averaged to UTC-day means (all 24 hours required, otherwise empty); "
        f"fill value -999 treated as missing; rounded to {power_daily.DECIMALS} decimals; nothing "
        "interpolated. No endorsement by NASA is implied."
    )
    entry = _entry(
        id=DAILY_ID,
        title="NASA POWER daily weather and resource means, four German cities, 2015–2020 "
        "(UTC days)",
        summary="Daily means of UTC days, computed by GridStorm from hourly UTC values, of 2 m "
        "temperature, 10 m / 50 m wind and all-sky GHI at Berlin, Hamburg, Cologne and Munich "
        "grid cells; same coverage as the load forecast (2015-01-01 to 2020-09-30).",
        description=(
            "Daily means of `T2M` (°C), `WS10M` and `WS50M` (m/s) and `ALLSKY_SFC_SW_DWN` "
            "(all-sky GHI as mean irradiance, W/m²) **computed by GridStorm** from NASA POWER "
            "hourly values requested with `time-standard=UTC`: the value of day D is the mean of "
            "the 24 hours D 00:00–23:00 UTC and is written only when all 24 are present (fill "
            "value -999 = missing; nothing interpolated). NASA's own daily product is not used "
            "because its days are not UTC days.\n\n"
            "**Reanalysis, not station data**: temperature and wind are MERRA-2 reanalysis "
            "(0.5° × 0.625° grid cells), GHI is CERES SYN1deg satellite-derived (1° × 1°). Each "
            "series samples the grid cell containing the city centre coordinates; it is not a "
            "measurement in the city.\n\n"
            f"Coverage equals `{OPSD_ID}` (UTC days 2015-01-01..2020-09-30), so weather and "
            "the day-ahead demand forecast can be viewed side by side across seasons and years "
            "(e.g. winter cold spells against daily demand at P1D). The comparison is "
            "descriptive: no causal or predictive relationship is claimed or validated. Hourly "
            f"detail for the stress windows and 2017 is in `{WEATHER_ID}` and `{RESOURCE_ID}`."
        ),
        category="weather_reanalysis",
        provenance="modeled",
        data_nature="MERRA-2 reanalysis and CERES SYN1deg irradiance via NASA POWER, averaged "
        "to UTC days by GridStorm (grid-cell values, not station data)",
        region={"code": "DE", "name": "Germany (4 city grid cells)", "kind": "points"},
        source={
            "name": "NASA POWER Hourly API (point, community RE, time-standard=UTC); daily means "
            "by GridStorm",
            "publisher": "NASA Langley Research Center, POWER Project; aggregation: GridStorm",
            "url": sources.POWER_HOURLY_URL,
            "version": ", ".join(versions),
            "doi": None,
            "retrieved_at": last,
            "source_sha256": record_sha,
            "license": {
                "id": rec.licence_id,
                "name": rec.licence_name,
                "url": rec.licence_url,
                "redistribution": rec.redistribution,
            },
            "attribution": attribution,
        },
        temporal={
            "start_utc": bundle.fmt_utc(grid[0]),
            "end_utc": bundle.fmt_utc(grid[-1]),
            "resolution": "P1D",
            "timezone": "UTC",
            "windows": stress_windows(),
        },
        spatial={"kind": "points", "points": power_points()},
        series=[s.public() for s in series],
        quality=_quality(table, grid, checks, warnings),
        transformations=[
            {
                "step": "request",
                "description": f"{len(reqs)} sequential hourly point requests (4 points × "
                f"calendar years {years[0]}–{years[-1]}, the last ending {grid[-1]:%Y-%m-%d}), "
                "parameters T2M, WS10M, WS50M, ALLSKY_SFC_SW_DWN, community RE, format JSON, "
                "time-standard=UTC",
            },
            {
                "step": "record",
                "description": "URL, response sha256, API version, header sources, fill counts, "
                "canonical hourly-values sha256, daily-means sha256 and incomplete days per "
                f"request in {_rel(record_path)}",
            },
            {
                "step": "parse",
                "description": "YYYYMMDDHH (UTC) -> UTC hour; -999 -> missing",
            },
            {"step": "aggregate", "description": power_daily.RULE},
            {
                "step": "write",
                "description": f"wide CSV, one column per point and parameter, "
                f"{power_daily.DECIMALS} decimals; row timestamp = UTC day start (00:00:00Z)",
            },
        ],
        transformation_version=f"{DAILY_ID}/1.0.0",
        artifact=None,
        links={
            "network_id": None,
            "scenario_ids": _scenario_ids(),
            "study_route": None,
            "docs": [DOC_SOURCES, DOC_PIPELINE, DOC_ANALOGUES],
        },
        use_in_scenario={
            "available": False,
            "network_id": None,
            "preset_id": None,
            "route": None,
            "rationale": "Daily point weather means have no validated mapping to a network "
            "input (GridStorm has no validated weather-to-availability or weather-to-demand "
            "model). To run observed conditions in Studio, use the precomputed observed-analogue "
            f"presets on scigrid-de (e.g. {ANALOGUE_PRESET}); see {ANALOGUE_ID}.",
        },
        exportable=True,
    )
    return Built(entry, series, table)


# --- derived multipliers and analogue scenarios ---------------------------------------------


def _derived() -> dict:
    return json.loads(DERIVED_PATH.read_text("utf-8"))


def _scenario_ids() -> list[str]:
    return sorted(s["scenario_id"] for s in _derived()["scenarios"])


def _scenarios_by_day() -> list[dict]:
    return sorted(_derived()["scenarios"], key=lambda s: s["stress_day_utc"])


def _series_id(scenario_id: str) -> str:
    return scenario_id.removeprefix("observed-").replace("-", "_")


def derived_entry(opsd_manifest: dict) -> Built:
    derived = _derived()
    derived_sha = _sha_file(DERIVED_PATH)
    snaps = derived["network"]["snapshots_utc"]
    start = datetime.fromisoformat(snaps[0]).replace(tzinfo=UTC)
    end = datetime.fromisoformat(snaps[1]).replace(tzinfo=UTC)
    stamps = bundle.hourly_range(start, end)
    scen = _scenarios_by_day()
    series = [
        Series(
            id=_series_id(s["scenario_id"]),
            label=f"Hour-of-day demand multiplier for stress day {s['stress_day_utc']} "
            f"(reference {s['reference_day_utc']}), applied to the SciGRID-DE model day 2011-01-01",
            unit="dimensionless",
            quantity="hour-of-day demand multiplier applied to all scigrid-de loads "
            "(timestamp = model snapshot hour, not observation time)",
            location_id=None,
            decimals=4,
            source_key=f"{licence.DERIVED_SOURCE}:demand_multipliers",
        )
        for s in scen
    ]
    table = Table(
        stamps, {_series_id(s["scenario_id"]): list(s["demand"]["multipliers"]) for s in scen}
    )
    checks = [
        check(
            "derived_file_checksum",
            "pass"
            if opsd_manifest["derived_files"]["derived-multipliers.json"] == derived_sha
            else "fail",
            f"derived-multipliers.json sha256 {derived_sha} matches "
            "data/observed/opsd-de/manifest.json",
        )
    ]
    mismatches = []
    for s in scen:
        path = sources.SCENARIO_OUT_DIR / f"{s['scenario_id']}.yaml"
        doc = yaml.safe_load(path.read_text("utf-8"))
        ev = [e for e in doc["events"] if e["type"] == "demand_multiplier"]
        got = [e["value"] for e in sorted(ev, key=lambda e: e["window"]["start"])]
        if got != s["demand"]["multipliers"]:
            mismatches.append(s["scenario_id"])
    checks.append(
        check(
            "matches_scenario_events",
            "pass" if not mismatches else "fail",
            "the 24 demand_multiplier events of each scenario YAML equal these values"
            if not mismatches
            else f"differs: {mismatches}",
        )
    )
    clipped = sum(len(s["demand"]["clipped_hours"]) for s in scen)
    checks.append(
        check(
            "no_clipping",
            "pass" if not clipped else "warn",
            f"{clipped} hours clipped to StormSpec (0, 5]",
        )
    )
    checks += bundle.grid_checks(table, stamps)
    checks.append(bundle.range_check(table, series, 1e-9, 5.0, "stormspec_range"))
    rec = licence.gate(series[0].source_key)
    entry = _entry(
        id=DERIVED_ID,
        title="Observed-analogue hourly demand multipliers (scigrid-de)",
        summary="The 24 hourly demand multipliers that map each observed German stress day onto "
        "the "
        "scigrid-de network day.",
        description=(
            "For each observed stress day d with reference day r (nearest complete 1 January), "
            "`m_h = (F(d,h) / mean F(r)) / (L_net(h) / mean L_net)`, where F is the ENTSO-E "
            "day-ahead load forecast and L_net the scigrid-de network load; rounded to 4 "
            "decimals (docs/research/observed-analogue-scenarios.md §3).\n\n"
            "**Time axis**: the `utc` timestamps are the SciGRID-DE **model snapshot hours** "
            "(2011-01-01 h:00 UTC) each multiplier is applied to, **not observation times**: "
            "hour h of the stress day (UTC) maps to model snapshot h. Each column is the "
            "hour-of-day profile of one stress day (2015-01-20, 2017-01-24, 2017-12-13). The "
            "renewable daily multipliers of the same file derive from non-open actual-generation "
            "data and are not published as series here."
        ),
        category="derived_research",
        provenance="modeled",
        data_nature="GridStorm-derived scenario parameters (MODELED mapping of a CC BY 4.0 "
        "forecast "
        "onto a network day)",
        region={"code": "DE", "name": "Germany (scigrid-de network)", "kind": "country"},
        source={
            "name": "GridStorm observed-analogue derived parameters (derived-multipliers.json)",
            "publisher": "GridStorm (pipelines/observed)",
            "url": REPO_BLOB + _rel(DERIVED_PATH),
            "version": derived["schema_version"],
            "doi": None,
            "retrieved_at": None,
            "source_sha256": derived_sha,
            "license": {
                "id": rec.licence_id,
                "name": rec.licence_name,
                "url": rec.licence_url,
                "redistribution": rec.redistribution,
            },
            "attribution": sources.LOAD_FORECAST_ATTRIBUTION
            + " Network load: scigrid-de (PyPSA SciGRID example, PyPSA contributors, CC BY 4.0; "
            "SciGRID/© OpenStreetMap contributors, ODbL).",
        },
        temporal={
            "start_utc": bundle.fmt_utc(start),
            "end_utc": bundle.fmt_utc(end),
            "resolution": "PT1H",
            "timezone": "UTC",
            "windows": None,
        },
        spatial={"kind": "network", "points": None},
        series=[s.public() for s in series],
        quality=_quality(
            table,
            stamps,
            checks,
            [
                "Timestamps are SciGRID-DE model snapshot hours (2011-01-01), not observation "
                "times: column <stress day> holds that day's hour-of-day multipliers (UTC hour h "
                "-> snapshot h)."
            ],
        ),
        transformations=[
            {
                "step": "read",
                "description": f"scenarios[].demand.multipliers of {_rel(DERIVED_PATH)} "
                "(written by gridstorm_observed.build)",
            },
            {"step": "align", "description": "stress-day hour h -> scigrid-de snapshot h (UTC)"},
            {"step": "write", "description": "one column per scenario, 4 decimals"},
        ],
        transformation_version="opsd-de-derived-multipliers/1.0.0",
        artifact=None,
        links={
            "network_id": sources.NETWORK_ID,
            "scenario_ids": _scenario_ids(),
            "study_route": None,
            "docs": [DOC_ANALOGUES, DOC_ENTSOE],
        },
        use_in_scenario={
            "available": False,
            "network_id": sources.NETWORK_ID,
            "preset_id": None,
            "route": None,
            "rationale": "Already embedded as demand_multiplier events in the three scenarios "
            f"of {ANALOGUE_ID}; "
            "use those instead of applying the series by hand.",
        },
        exportable=True,
    )
    return Built(entry, series, table)


def analogue_entry(opsd_manifest: dict) -> Built:
    results = json.loads(RESULTS_PATH.read_text("utf-8"))
    scen = _scenarios_by_day()
    runs = {r["scenario_id"]: r for r in results["runs"]}
    pinned = opsd_manifest["scenario_files"]
    checks = []
    bad_sha, bad_runs = [], []
    for s in scen:
        rel = f"data/scenarios/observed/{s['scenario_id']}.yaml"
        sha = _sha_file(sources.REPO_ROOT / rel)
        if pinned.get(rel) != sha or s["scenario_sha256"] != sha:
            bad_sha.append(rel)
        run = runs.get(s["scenario_id"])
        if (
            run is None
            or run["scenario_sha256"] != sha
            or not run["validation"]["canonical_json"]["valid"]
            or run["solver"]["termination_condition"] != "optimal"
        ):
            bad_runs.append(s["scenario_id"])
    checks.append(
        check(
            "scenario_checksums",
            "pass" if not bad_sha else "fail",
            "scenario YAML sha256 = data/observed/opsd-de/manifest.json scenario_files = "
            "derived-multipliers.json" + (f"; mismatched: {bad_sha}" if bad_sha else ""),
        )
    )
    drift = [
        s["scenario_id"]
        for s in scen
        if not (PRESET_DIR / f"{s['scenario_id']}.yaml").exists()
        or (PRESET_DIR / f"{s['scenario_id']}.yaml").read_bytes()
        != (sources.SCENARIO_OUT_DIR / f"{s['scenario_id']}.yaml").read_bytes()
    ]
    if drift:
        raise ValueError(f"Studio preset copies differ from data/scenarios/observed: {drift}")
    checks.append(
        check(
            "studio_presets_identical",
            "pass",
            f"{_rel(PRESET_DIR)}/<id>.yaml is byte-identical to data/scenarios/observed/<id>.yaml "
            "for all three scenarios",
        )
    )
    checks.append(
        check(
            "precomputed_results",
            "pass" if not bad_runs else "fail",
            "each scenario has a result in analogue-results.json for the same scenario sha256, "
            "validated and solved to optimality" + (f"; failing: {bad_runs}" if bad_runs else ""),
        )
    )
    rows = []
    for s in scen:
        m = runs[s["scenario_id"]]["metrics"]
        rows.append(
            f"| `{s['scenario_id']}` | {s['stress_day_utc']} | {m['unserved_energy_mwh']:,.0f} | "
            f"{m['peak_load_shed_mw']:,.0f} | {m['load_shed_hours']:.0f} |"
        )
    base = runs.get("observed-baseline-network-day")
    if base is not None:
        bm = base["metrics"]
        rows.insert(
            0,
            "| baseline (network day, no events) | 2011-01-01 | "
            f"{bm['unserved_energy_mwh']:,.0f} | "
            f"{bm['peak_load_shed_mw']:,.0f} | {bm['load_shed_hours']:.0f} |",
        )
    days = [s["stress_day_utc"] for s in scen]
    entry = _entry(
        id=ANALOGUE_ID,
        title="Observed-analogue stress scenarios on scigrid-de (2015–2017 German stress days)",
        summary="Three StormSpec scenarios replaying observed German stress days on the scigrid-de "
        "network, with precomputed PyPSA results.",
        description=(
            "Historical-analogue scenarios: the German highest-load day, the winter Dunkelflaute "
            "day and the combined high-load / low-renewable day (detected in OPSD 2015–2020) "
            "mapped "
            "onto the 24 snapshots of scigrid-de: hourly demand from the CC BY 4.0 load forecast, "
            "one MODELED daily availability multiplier per renewable carrier. The mapping and "
            "every "
            "result are **modeled** (DC LOPF, 2011 topology), not a reconstruction of the day.\n\n"
            "Precomputed results (`data/observed/analogue-results.json`):\n\n"
            "| Scenario | Day (UTC) | Unserved energy (MWh) | Peak shed (MW) | Shed hours |\n"
            "|---|---|---:|---:|---:|\n" + "\n".join(rows)
        ),
        category="synthetic_scenario_input",
        provenance="modeled",
        data_nature="StormSpec scenario inputs constructed by GridStorm from observed stress days "
        "(analogue mapping, not a real system state)",
        region={"code": "DE", "name": "Germany (scigrid-de network)", "kind": "country"},
        source={
            "name": "GridStorm observed-analogue scenarios (data/scenarios/observed/*.yaml)",
            "publisher": "GridStorm (pipelines/observed)",
            "url": REPO_BLOB + "data/scenarios/observed",
            "version": opsd_manifest["schema_version"],
            "doi": None,
            "retrieved_at": None,
            "source_sha256": _sha_file(OPSD_MANIFEST_PATH),
            "license": {
                "id": "LicenseRef-GridStorm-observed-analogue",
                "name": "Mixed: CC BY 4.0 demand multipliers (ENTSO-E load forecast); daily "
                "renewable multipliers derived from non-open ENTSO-E actual generation "
                "(derived-only)",
                "url": DOC_ENTSOE["href"],
                "redistribution": "derived-only",
            },
            "attribution": opsd_manifest["attribution"] + " " + sources.LOAD_FORECAST_ATTRIBUTION,
        },
        temporal={
            "start_utc": bundle.fmt_utc(_day(days[0])),
            "end_utc": bundle.fmt_utc(_day(days[-1]) + timedelta(hours=23)),
            "resolution": "PT1H",
            "timezone": "UTC",
            "windows": [
                {
                    "start_utc": bundle.fmt_utc(_day(s["stress_day_utc"])),
                    "end_utc": bundle.fmt_utc(_day(s["stress_day_utc"]) + timedelta(hours=23)),
                    "label": f"{s['scenario_id']} (stress day, UTC)",
                }
                for s in scen
            ],
        },
        spatial={"kind": "network", "points": None},
        series=[],
        quality=_quality(
            None,
            [],
            checks,
            [
                "Metadata-only entry: the scenario files and results are linked, not re-published "
                "as series.",
                "Renewable shortfall is one daily multiplier per carrier on the network's own "
                "2011-01-01 profile; observed hourly renewable timing is not represented.",
            ],
        ),
        transformations=[
            {
                "step": "detect",
                "description": "stress days from OPSD actual load / generation / capacity "
                "(dates only are committed)",
            },
            {
                "step": "map",
                "description": "hourly demand multipliers from the load forecast; one daily "
                "renewable multiplier per carrier, rounded to 0.05",
            },
            {"step": "solve", "description": "PyPSA LOPF (HiGHS) per scenario + baseline"},
        ],
        transformation_version="observed-analogue-scenarios/1.0.0",
        artifact=None,
        links={
            "network_id": sources.NETWORK_ID,
            "scenario_ids": _scenario_ids(),
            "study_route": None,
            "docs": [
                DOC_ANALOGUES,
                {"label": "Precomputed results (JSON)", "href": REPO_BLOB + _rel(RESULTS_PATH)},
                DOC_ENTSOE,
            ],
        },
        use_in_scenario={
            "available": True,
            "network_id": sources.NETWORK_ID,
            "preset_id": ANALOGUE_PRESET,
            "route": f"/studio?network={sources.NETWORK_ID}&preset={ANALOGUE_PRESET}",
            "rationale": "The three StormSpec analogue scenarios are published as PRECOMPUTED "
            "Studio presets on SciGRID-DE (too large for live runs on the free API); the "
            "presets are byte-identical copies of data/scenarios/observed/*.yaml. The other two "
            "are " + " and ".join(i for i in _scenario_ids() if i != ANALOGUE_PRESET) + ".",
        },
        exportable=False,
    )
    return Built(entry)


# --- bundle ---------------------------------------------------------------------------------


def build_bundle(inputs: Inputs) -> Result:
    notes: list[str] = []
    opsd_manifest = json.loads(OPSD_MANIFEST_PATH.read_text("utf-8"))
    if opsd_manifest["source"]["sha256"] != sources.OPSD_CSV_SHA256:
        raise ValueError("data/observed/opsd-de/manifest.json sha256 differs from sources.py")

    if inputs.opsd_csv is not None and inputs.opsd_csv.exists():
        table, src_checks = load_opsd(inputs.opsd_csv)
        notes.append(f"{OPSD_ID}: re-derived from the OPSD source CSV")
    else:
        table, prev = _previous_table(inputs, OPSD_ID)
        src_checks = [c for c in prev["quality"]["checks"] if c["name"] in OPSD_SOURCE_CHECKS]
        notes.append(f"{OPSD_ID}: carried forward from the previous bundle (OPSD CSV not given)")
    built = [opsd_entry(table, src_checks, opsd_manifest)]

    record, record_sha, tables, how = load_power(inputs)
    notes.append(f"{WEATHER_ID}, {RESOURCE_ID}: {how}")
    built += power_entries(record, tables, record_sha)
    daily_record, daily_sha, table_daily, how_daily = load_power_daily(inputs)
    notes.append(f"{DAILY_ID}: {how_daily}")
    built.append(
        daily_entry(daily_record, table_daily, daily_sha, tables, inputs.power_daily_record)
    )
    built.append(derived_entry(opsd_manifest))
    built.append(analogue_entry(opsd_manifest))
    notes.append(f"{DERIVED_ID}, {ANALOGUE_ID}: re-derived from committed inputs")

    files: dict[str, bytes] = {}
    gate: dict[str, dict] = {}
    for b in built:
        if b.table is None:
            continue
        gate[b.entry["id"]] = {}
        for s in b.series:
            rec = licence.gate(s.source_key)
            gate[b.entry["id"]][s.id] = {
                "source_key": s.source_key,
                "licence_id": rec.licence_id,
                "redistribution": rec.redistribution,
            }
        data = bundle.write_csv(b.table, b.series)
        path = f"series/{b.entry['id']}.csv"
        files[path] = data
        b.entry["artifact"] = {
            "path": path,
            "sha256": bundle.sha256(data),
            "bytes": len(data),
            "rows": len(b.table.timestamps),
        }
    entries = sorted((b.entry for b in built), key=lambda e: e["id"])
    for e in entries:
        errors = bundle.validate_entry(e)
        if errors:
            raise ValueError(f"{e['id']}: {errors}")
    catalog = {
        "schema_version": bundle.SCHEMA_VERSION,
        "bundle_version": inputs.bundle_version,
        "entries": entries,
    }
    files["catalog.json"] = bundle.dump_json(catalog)
    for name, data in files.items():
        licence.assert_clean_text(name, data.decode("utf-8"))
    manifest = make_manifest(files, gate, inputs, opsd_manifest)
    files["manifest.json"] = bundle.dump_json(manifest)
    licence.assert_clean_text("manifest.json", files["manifest.json"].decode("utf-8"))
    return Result(files, notes)


def make_manifest(files: dict[str, bytes], gate: dict, inputs: Inputs, opsd_manifest: dict) -> dict:
    listed = [
        {"path": p, "sha256": bundle.sha256(d), "bytes": len(d)} for p, d in sorted(files.items())
    ]
    src = opsd_manifest["source"]
    committed = [
        DERIVED_PATH,
        OPSD_MANIFEST_PATH,
        RESULTS_PATH,
        OLD_EXTRACT_PATH,
        inputs.power_record,
        inputs.power_daily_record,
        *sorted(sources.SCENARIO_OUT_DIR.glob("*.yaml")),
        *sorted(PRESET_DIR.glob("observed-*.yaml")),
    ]
    return {
        "schema_version": bundle.MANIFEST_SCHEMA,
        "bundle_version": inputs.bundle_version,
        "pipeline": {
            "name": "pipelines/observed scripts/publish_observatory.py "
            "(gridstorm_observed.publish)",
            "version": PIPELINE_VERSION,
            "command": COMMAND,
            "verify_command": VERIFY_COMMAND,
        },
        "sources": {
            "external": [
                {
                    "id": "opsd-time-series-60min",
                    "url": src["url"],
                    "version": src["version"],
                    "doi": src["doi"],
                    "sha256": src["sha256"],
                    "bytes": src["bytes"],
                    "retrieved_at": src["retrieved_at"],
                    "columns_read": [sources.OPSD_LOAD_FORECAST_COL],
                },
                {
                    "id": "nasa-power-hourly",
                    "url": sources.POWER_HOURLY_URL,
                    "request_record": _rel(inputs.power_record),
                    "request_record_sha256": _sha_file(inputs.power_record),
                    "note": "per-request URL, response sha256, API version and retrieval time are "
                    "in the request record",
                },
                {
                    "id": "nasa-power-hourly-for-daily-means",
                    "url": sources.POWER_HOURLY_URL,
                    "request_record": _rel(inputs.power_daily_record),
                    "request_record_sha256": _sha_file(inputs.power_daily_record),
                    "note": "yearly hourly UTC requests behind nasa-power-de-daily; per-request "
                    "URL, response sha256, API version, retrieval time, daily-means sha256 and "
                    "incomplete days are in the request record",
                },
            ],
            "committed": [{"path": _rel(p), "sha256": _sha_file(p)} for p in committed],
        },
        "licence_gate": gate,
        "files": listed,
        "total_bytes": sum(f["bytes"] for f in listed),
    }


def write_bundle(out: Path, files: dict[str, bytes]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "series").mkdir(exist_ok=True)
    for stale in (out / "series").glob("*.csv"):
        if f"series/{stale.name}" not in files:
            stale.unlink()
    for rel, data in files.items():
        path = out / rel
        if not path.exists() or path.read_bytes() != data:
            path.write_bytes(data)


# --- verify ---------------------------------------------------------------------------------


def verify(out: Path, inputs: Inputs) -> tuple[list[str], list[str]]:
    """Errors and notes for the bundle in ``out`` (empty error list = verified)."""
    errors: list[str] = []
    manifest = json.loads((out / "manifest.json").read_text("utf-8"))
    listed = {f["path"]: f for f in manifest["files"]}
    on_disk = {
        p.relative_to(out).as_posix()
        for p in out.rglob("*")
        if p.is_file() and p.name != "manifest.json" and not p.name.startswith(".")
    }
    for extra in sorted(on_disk - set(listed)):
        errors.append(f"{extra}: not listed in manifest.json")
    for rel, f in sorted(listed.items()):
        path = out / rel
        if not path.exists():
            errors.append(f"{rel}: listed but missing")
            continue
        data = path.read_bytes()
        if bundle.sha256(data) != f["sha256"] or len(data) != f["bytes"]:
            errors.append(f"{rel}: sha256/bytes differ from manifest.json")
    if manifest.get("total_bytes") != sum(f["bytes"] for f in manifest["files"]):
        errors.append("manifest.json total_bytes inconsistent")
    catalog = json.loads((out / "catalog.json").read_text("utf-8"))
    if catalog.get("schema_version") != bundle.SCHEMA_VERSION:
        errors.append(f"catalog schema_version {catalog.get('schema_version')!r}")
    ids = [e.get("id") for e in catalog["entries"]]
    if len(ids) != len(set(ids)):
        errors.append("duplicate entry ids")
    gate = manifest.get("licence_gate", {})
    for e in catalog["entries"]:
        eid = e.get("id")
        errors += [f"{eid}: {m}" for m in bundle.validate_entry(e)]
        art = e.get("artifact")
        if not art:
            continue
        f = listed.get(art["path"])
        if f is None or f["sha256"] != art["sha256"] or f["bytes"] != art["bytes"]:
            errors.append(f"{eid}: artifact does not match manifest.json")
            continue
        try:
            header, table = bundle.read_csv((out / art["path"]).read_bytes())
        except (ValueError, OSError) as exc:
            errors.append(f"{eid}: {exc}")
            continue
        if header != [s["id"] for s in e["series"]]:
            errors.append(f"{eid}: CSV header differs from entry series")
        if art["rows"] != len(table.timestamps):
            errors.append(f"{eid}: artifact.rows {art['rows']} != {len(table.timestamps)}")
        if e["source"]["license"]["redistribution"] != "permitted":
            errors.append(f"{eid}: series published without redistribution permission")
        for s in e["series"]:
            g = gate.get(eid, {}).get(s["id"])
            if g is None:
                errors.append(f"{eid}/{s['id']}: no licence-gate record in manifest.json")
                continue
            try:
                rec = licence.gate(g["source_key"])
            except licence.LicenceError as exc:
                errors.append(f"{eid}/{s['id']}: {exc}")
                continue
            if rec.licence_id != g["licence_id"] or rec.licence_id != e["source"]["license"]["id"]:
                errors.append(f"{eid}/{s['id']}: licence id mismatch")
    for rel in sorted(listed) + ["manifest.json"]:
        path = out / rel
        if path.exists():
            try:
                licence.assert_clean_text(rel, path.read_text("utf-8"))
            except licence.LicenceError as exc:
                errors.append(str(exc))
    if errors:
        return errors, []
    rebuild_inputs = Inputs(
        opsd_csv=inputs.opsd_csv,
        power_cache=inputs.power_cache,
        previous=out,
        power_record=inputs.power_record,
        power_daily_record=inputs.power_daily_record,
        bundle_version=catalog["bundle_version"],
    )
    try:
        rebuilt = build_bundle(rebuild_inputs)
    except (ValueError, FileNotFoundError, KeyError, licence.LicenceError) as exc:
        return [f"re-derivation failed: {exc}"], []
    current = {rel: (out / rel).read_bytes() for rel in [*listed, "manifest.json"]}
    for rel in sorted(set(current) | set(rebuilt.files)):
        if current.get(rel) != rebuilt.files.get(rel):
            errors.append(f"{rel}: differs from the re-derived bundle")
    return errors, rebuilt.notes
