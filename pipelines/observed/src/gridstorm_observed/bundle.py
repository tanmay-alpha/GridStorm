"""Deterministic primitives for the Data Observatory bundle (``gridstorm-observatory/1.0``).

Wide CSV: header ``utc,<series_id>,...``; ``utc`` is ``YYYY-MM-DDTHH:MM:SSZ`` and strictly
increasing; an empty cell is a missing value (never 0); numbers use a fixed number of decimals
per series with trailing zeros removed; LF line endings, UTF-8, no BOM. JSON: sorted keys,
two-space indent, UTF-8, trailing newline. Nothing here reads the clock.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

SCHEMA_VERSION = "gridstorm-observatory/1.0"
MANIFEST_SCHEMA = "gridstorm-observatory-manifest/1.0"
UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SERIES_ID_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
HOUR = timedelta(hours=1)

CATEGORIES = (
    "network_model",
    "network_assets",
    "historical_demand",
    "weather_reanalysis",
    "renewable_resource",
    "synthetic_scenario_input",
    "derived_research",
    "precomputed_experiment",
    "simulation_output",
)
PROVENANCES = ("observed", "estimated", "synthetic", "modeled", "calculated")
REDISTRIBUTION = ("permitted", "derived-only", "restricted")
CHECK_STATUS = ("pass", "warn", "fail")
REGION_KINDS = ("country", "points", "benchmark", "bidding-zone")
SPATIAL_KINDS = ("points", "region", "network", "none")


# --- time -----------------------------------------------------------------------------------


def parse_utc(text: str) -> datetime:
    """Parse the bundle's ``YYYY-MM-DDTHH:MM:SSZ`` form only (no offsets, no local times)."""
    if not UTC_RE.match(text):
        raise ValueError(f"not a bundle UTC timestamp: {text!r}")
    return datetime.strptime(text, UTC_FORMAT).replace(tzinfo=UTC)


def fmt_utc(ts: datetime) -> str:
    if ts.tzinfo is None or ts.utcoffset() != timedelta(0):
        raise ValueError(f"timestamp must be timezone-aware UTC: {ts!r}")
    return ts.strftime(UTC_FORMAT)


def hourly_range(start: datetime, end: datetime) -> list[datetime]:
    """Inclusive hourly grid ``start .. end``."""
    out, t = [], start
    while t <= end:
        out.append(t)
        t += HOUR
    return out


# --- numbers --------------------------------------------------------------------------------


def fmt_num(value: float | None, decimals: int) -> str:
    """Fixed decimals, trailing zeros stripped; ``None``/NaN -> empty cell; ``-0`` -> ``0``."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = f"{value:.{decimals}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


# --- tables ---------------------------------------------------------------------------------


@dataclass
class Series:
    id: str
    label: str
    unit: str
    quantity: str
    location_id: str | None
    decimals: int
    source_key: str

    def public(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "unit": self.unit,
            "quantity": self.quantity,
            "location_id": self.location_id,
        }


@dataclass
class Table:
    """Hourly wide table; ``values[series_id][i]`` belongs to ``timestamps[i]``."""

    timestamps: list[datetime]
    values: dict[str, list[float | None]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for sid, col in self.values.items():
            if len(col) != len(self.timestamps):
                raise ValueError(f"column {sid}: {len(col)} values for {len(self.timestamps)} rows")


def write_csv(table: Table, series: list[Series]) -> bytes:
    ids = [s.id for s in series]
    if ids != list(table.values):
        raise ValueError(f"series order {ids} != table columns {list(table.values)}")
    check_timestamps(table.timestamps)
    lines = [",".join(["utc", *ids])]
    cols = [(table.values[s.id], s.decimals) for s in series]
    for i, ts in enumerate(table.timestamps):
        lines.append(",".join([fmt_utc(ts), *(fmt_num(c[i], d) for c, d in cols)]))
    return ("\n".join(lines) + "\n").encode("utf-8")


def read_csv(data: bytes) -> tuple[list[str], Table]:
    """Strict parser for a bundle CSV; returns the series ids and the table."""
    text = data.decode("utf-8")
    if not text.endswith("\n") or "\r" in text:
        raise ValueError("CSV must use LF line endings and end with a newline")
    rows = text[:-1].split("\n")
    header = rows[0].split(",")
    if header[0] != "utc" or len(header) < 2:
        raise ValueError(f"CSV header must start with 'utc' and name >= 1 series: {header}")
    ids = header[1:]
    if len(set(ids)) != len(ids) or not all(SERIES_ID_RE.match(i) for i in ids):
        raise ValueError(f"invalid or duplicate series ids: {ids}")
    stamps: list[datetime] = []
    cols: dict[str, list[float | None]] = {i: [] for i in ids}
    for n, row in enumerate(rows[1:], start=2):
        cells = row.split(",")
        if len(cells) != len(header):
            raise ValueError(f"line {n}: {len(cells)} cells, expected {len(header)}")
        stamps.append(parse_utc(cells[0]))
        for sid, cell in zip(ids, cells[1:], strict=True):
            if cell == "":
                cols[sid].append(None)
                continue
            v = float(cell)
            if not math.isfinite(v):
                raise ValueError(f"line {n}: non-finite value {cell!r}")
            cols[sid].append(v)
    check_timestamps(stamps)
    return ids, Table(stamps, cols)


def check_timestamps(stamps: list[datetime]) -> None:
    for a, b in zip(stamps, stamps[1:], strict=False):
        if b <= a:
            raise ValueError(f"timestamps not strictly increasing at {fmt_utc(b)}")


# --- quality --------------------------------------------------------------------------------


def check(name: str, status: str, detail: str) -> dict:
    if status not in CHECK_STATUS:
        raise ValueError(status)
    return {"name": name, "status": status, "detail": detail}


def missing_runs(stamps: list[datetime], col: list[float | None]) -> list[tuple[datetime, int]]:
    """Runs of consecutive missing hours as ``(first_hour, length)``."""
    runs: list[tuple[datetime, int]] = []
    start: datetime | None = None
    n = 0
    prev: datetime | None = None
    for ts, v in zip(stamps, col, strict=True):
        if v is None and start is not None and prev is not None and ts - prev == HOUR:
            n += 1
        elif v is None:
            if start is not None:
                runs.append((start, n))
            start, n = ts, 1
        elif start is not None:
            runs.append((start, n))
            start, n = None, 0
        prev = ts
    if start is not None:
        runs.append((start, n))
    return runs


def table_quality(table: Table, expected: list[datetime]) -> dict:
    """Counts derived from the table alone: rows, missing per series, completeness.

    A value is missing when its cell is empty or its expected hour has no row. Completeness is
    ``present cells / (expected rows x series) x 100``, rounded to 3 decimals.
    """
    expected_set = set(expected)
    rows = len(table.timestamps)
    extra = [t for t in table.timestamps if t not in expected_set]
    if extra:
        raise ValueError(f"{len(extra)} rows outside the declared coverage, first {extra[0]}")
    absent = len(expected) - rows
    missing = {sid: sum(v is None for v in col) + absent for sid, col in table.values.items()}
    cells = len(expected) * len(table.values)
    present = cells - sum(missing.values())
    pct = round(100.0 * present / cells, 3) if cells else None
    return {
        "rows": rows,
        "expected_rows": len(expected),
        "completeness_pct": pct,
        "missing_values": dict(sorted(missing.items())),
        "missing_policy": "kept-as-null",
    }


def grid_checks(table: Table, expected: list[datetime]) -> list[dict]:
    """Hourly-grid, duplicate and gap checks on the published table."""
    out = []
    dupes = len(table.timestamps) - len(set(table.timestamps))
    out.append(
        check(
            "no_duplicate_timestamps",
            "pass" if dupes == 0 else "fail",
            f"{dupes} duplicate UTC timestamps",
        )
    )
    on_grid = table.timestamps == expected
    out.append(
        check(
            "hourly_utc_grid",
            "pass" if on_grid else "fail",
            f"{len(table.timestamps)} rows on the expected hourly UTC grid of "
            f"{len(expected)} hours" + ("" if on_grid else " (mismatch)"),
        )
    )
    gaps = []
    for sid, col in table.values.items():
        for first, n in missing_runs(table.timestamps, col):
            gaps.append(f"{sid}: {fmt_utc(first)} +{n} h")
    out.append(
        check(
            "gaps",
            "pass" if not gaps else "warn",
            "no missing values" if not gaps else "missing runs (kept empty): " + "; ".join(gaps),
        )
    )
    return out


def range_check(table: Table, series: list[Series], lo: float, hi: float, name: str) -> dict:
    bad = []
    lows, highs = [], []
    for s in series:
        vals = [v for v in table.values[s.id] if v is not None]
        if not vals:
            continue
        lows.append(min(vals))
        highs.append(max(vals))
        n = sum(not (lo <= v <= hi) for v in vals)
        if n:
            bad.append(f"{s.id}: {n} values outside [{lo:g}, {hi:g}]")
    detail = (
        f"all values within [{lo:g}, {hi:g}] (observed min {min(lows):g}, max {max(highs):g})"
        if not bad and lows
        else "; ".join(bad) or "no values"
    )
    return check(name, "pass" if not bad else "warn", detail)


# --- JSON, hashing, entries -----------------------------------------------------------------


def dump_json(obj: object) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


ENTRY_KEYS = (
    "id",
    "title",
    "summary",
    "description",
    "category",
    "provenance",
    "data_nature",
    "region",
    "source",
    "temporal",
    "spatial",
    "series",
    "quality",
    "transformations",
    "transformation_version",
    "artifact",
    "links",
    "use_in_scenario",
    "exportable",
)


def validate_entry(e: dict) -> list[str]:
    """Schema errors of one DatasetEntry (empty list = valid)."""
    err: list[str] = []
    missing = [k for k in ENTRY_KEYS if k not in e]
    if missing:
        return [f"missing keys {missing}"]
    extra = sorted(set(e) - set(ENTRY_KEYS))
    if extra:
        err.append(f"unexpected keys {extra}")
    eid = e["id"]
    if not isinstance(eid, str) or not ID_RE.match(eid):
        err.append(f"id {eid!r} is not kebab-case")
    for k in ("title", "summary", "description", "data_nature", "transformation_version"):
        if not isinstance(e[k], str) or not e[k].strip():
            err.append(f"{k} must be a non-empty string")
    if e["category"] not in CATEGORIES:
        err.append(f"category {e['category']!r}")
    if e["provenance"] not in PROVENANCES:
        err.append(f"provenance {e['provenance']!r}")
    if e["region"] is not None:
        r = e["region"]
        if set(r) != {"code", "name", "kind"} or r["kind"] not in REGION_KINDS:
            err.append(f"region {r!r}")
    src = e["source"]
    src_keys = {
        "name",
        "publisher",
        "url",
        "version",
        "doi",
        "retrieved_at",
        "source_sha256",
        "license",
        "attribution",
    }
    if not isinstance(src, dict) or set(src) != src_keys:
        err.append(f"source keys {sorted(src) if isinstance(src, dict) else src!r}")
    else:
        lic = src["license"]
        if set(lic) != {"id", "name", "url", "redistribution"}:
            err.append(f"source.license keys {sorted(lic)}")
        elif lic["redistribution"] not in REDISTRIBUTION:
            err.append(f"redistribution {lic['redistribution']!r}")
        elif e["exportable"] is not (lic["redistribution"] == "permitted"):
            err.append("exportable must be true iff redistribution == 'permitted'")
    t = e["temporal"]
    if t is not None:
        if set(t) != {"start_utc", "end_utc", "resolution", "timezone", "windows"}:
            err.append(f"temporal keys {sorted(t)}")
        else:
            if t["timezone"] != "UTC":
                err.append("temporal.timezone must be UTC")
            try:
                if parse_utc(t["start_utc"]) > parse_utc(t["end_utc"]):
                    err.append("temporal start after end")
                for w in t["windows"] or []:
                    if set(w) != {"start_utc", "end_utc", "label"}:
                        err.append(f"window keys {sorted(w)}")
                    elif parse_utc(w["start_utc"]) > parse_utc(w["end_utc"]):
                        err.append(f"window {w['label']} start after end")
            except ValueError as exc:
                err.append(str(exc))
    sp = e["spatial"]
    if set(sp) != {"kind", "points"} or sp["kind"] not in SPATIAL_KINDS:
        err.append(f"spatial {sp!r}")
    elif sp["points"] is not None:
        for p in sp["points"]:
            if set(p) != {"id", "name", "lat", "lon", "grid_note"}:
                err.append(f"spatial point keys {sorted(p)}")
    ids = []
    for s in e["series"]:
        if set(s) != {"id", "label", "unit", "quantity", "location_id"}:
            err.append(f"series keys {sorted(s)}")
            continue
        if not SERIES_ID_RE.match(s["id"]):
            err.append(f"series id {s['id']!r}")
        ids.append(s["id"])
    if len(ids) != len(set(ids)):
        err.append("duplicate series ids")
    q = e["quality"]
    q_keys = {
        "rows",
        "expected_rows",
        "completeness_pct",
        "missing_values",
        "missing_policy",
        "checks",
        "warnings",
    }
    if set(q) != q_keys:
        err.append(f"quality keys {sorted(q)}")
    else:
        if q["missing_policy"] != "kept-as-null":
            err.append("missing_policy must be kept-as-null")
        for c in q["checks"]:
            if set(c) != {"name", "status", "detail"} or c["status"] not in CHECK_STATUS:
                err.append(f"check {c!r}")
        if set(q["missing_values"]) != set(ids):
            err.append("quality.missing_values must have one count per series")
    for tr in e["transformations"]:
        if set(tr) != {"step", "description"}:
            err.append(f"transformation keys {sorted(tr)}")
    art = e["artifact"]
    if e["series"]:
        if not art or set(art) != {"path", "sha256", "bytes", "rows"}:
            err.append("series entries need artifact {path, sha256, bytes, rows}")
        elif art["path"] != f"series/{eid}.csv":
            err.append(f"artifact.path must be series/{eid}.csv")
    elif art is not None:
        err.append("metadata-only entries must have artifact null")
    links = e["links"]
    if set(links) != {"network_id", "scenario_ids", "study_route", "docs"}:
        err.append(f"links keys {sorted(links)}")
    else:
        for d in links["docs"]:
            if set(d) != {"label", "href"}:
                err.append(f"links.docs item {d!r}")
    use = e["use_in_scenario"]
    if set(use) != {"available", "network_id", "preset_id", "route", "rationale"}:
        err.append(f"use_in_scenario keys {sorted(use)}")
    elif not use["rationale"]:
        err.append("use_in_scenario.rationale required")
    if not isinstance(e["exportable"], bool):
        err.append("exportable must be bool")
    return err
