"""Data Observatory bundle: licence gate, determinism, checksums, quality, UTC, verify/tamper."""

from __future__ import annotations

import csv
import json
import shutil
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gridstorm_observed import bundle, licence, opsd, power_daily, power_hourly, publish, sources

BUNDLE = sources.DATA_DIR / "observatory"
CATALOG = json.loads((BUNDLE / "catalog.json").read_text("utf-8"))
MANIFEST = json.loads((BUNDLE / "manifest.json").read_text("utf-8"))
ENTRIES = {e["id"]: e for e in CATALOG["entries"]}
OPSD_CSV = sources.cache_dir() / "opsd" / sources.OPSD_CSV_NAME
POWER_CACHE = power_hourly.default_cache()
MISSING = Path("does-not-exist")


def _carry_inputs(previous: Path = BUNDLE) -> publish.Inputs:
    """Inputs that need neither the OPSD CSV nor raw POWER responses (CI situation)."""
    return publish.Inputs(
        opsd_csv=None,
        power_cache=MISSING,
        previous=previous,
        bundle_version=CATALOG["bundle_version"],
    )


def _ts(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


# --- licence gate ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", sorted(licence.ALLOWED))
def test_allow_listed_sources_pass(key):
    rec = licence.gate(key)
    assert rec.redistribution == "permitted" and rec.licence_id and rec.basis


@pytest.mark.parametrize("column", sources.OPSD_NON_OPEN_COLUMNS)
def test_restricted_columns_never_pass_even_if_allow_listed(column):
    key = f"{licence.OPSD_SOURCE}:{column}"
    forged = {
        key: licence.LicenceRecord(key, "CC-BY-4.0", "forged", "https://x", "permitted", "none")
    }
    assert licence.is_restricted(key)
    with pytest.raises(licence.LicenceError, match="restricted"):
        licence.gate(key, allowed=forged)
    with pytest.raises(licence.LicenceError):
        licence.gate(key)


@pytest.mark.parametrize(
    "key",
    [
        "opsd:DE_load_actual_entsoe_transparency",
        "opsd:FR_wind_onshore_generation_actual",
        "opsd:DE_solar_capacity",
        "gridstorm-derived:renewable_daily_multiplier",
    ],
)
def test_restricted_patterns(key):
    assert licence.is_restricted(key)


def test_unknown_or_not_permitted_sources_rejected():
    with pytest.raises(licence.LicenceError, match="allow-list"):
        licence.gate("opsd:DE_price_day_ahead")
    key = "nasa-power:T2M"
    derived_only = {key: licence.LicenceRecord(key, "x", "x", "x", "derived-only", "x")}
    with pytest.raises(licence.LicenceError, match="redistribution"):
        licence.gate(key, allowed=derived_only)


def test_assert_clean_text():
    licence.assert_clean_text("ok", "utc,de_load_forecast\n")
    for bad in ("DE_load_actual_entsoe_transparency", "x_generation_actual", "DE_solar_capacity"):
        with pytest.raises(licence.LicenceError):
            licence.assert_clean_text("bad", f"utc,{bad}\n")


def test_build_refuses_a_restricted_series(monkeypatch):
    original = publish.opsd_series

    def forged(decimals):
        series = original(decimals)
        series[0].source_key = "opsd:DE_load_actual_entsoe_transparency"
        return series

    monkeypatch.setattr(publish, "opsd_series", forged)
    with pytest.raises(licence.LicenceError):
        publish.build_bundle(_carry_inputs())


def test_build_refuses_a_restricted_daily_series(monkeypatch):
    original = publish.daily_series

    def forged():
        series = original()
        series[-1].source_key = "opsd:DE_load_actual_entsoe_transparency"
        return series

    monkeypatch.setattr(publish, "daily_series", forged)
    with pytest.raises(licence.LicenceError):
        publish.build_bundle(_carry_inputs())


def test_daily_series_pass_the_gate_with_nasa_power_keys():
    gate = MANIFEST["licence_gate"][publish.DAILY_ID]
    assert len(gate) == 4 * len(power_hourly.PARAMETERS)
    for sid, g in gate.items():
        param = g["source_key"].removeprefix(f"{licence.POWER_SOURCE}:")
        assert param in power_hourly.PARAMETERS, sid
        assert licence.gate(g["source_key"]).redistribution == "permitted"


def test_published_bundle_is_licence_clean():
    gate = MANIFEST["licence_gate"]
    for e in CATALOG["entries"]:
        if not e["series"]:
            assert e["artifact"] is None
            continue
        assert e["source"]["license"]["redistribution"] == "permitted" and e["exportable"]
        assert set(gate[e["id"]]) == {s["id"] for s in e["series"]}
        for rec in gate[e["id"]].values():
            assert licence.gate(rec["source_key"]).licence_id == rec["licence_id"]
    for path in BUNDLE.rglob("*"):
        if path.is_file():
            licence.assert_clean_text(path.name, path.read_text("utf-8"))


def _published_forecast() -> pd.Series:
    _, table = bundle.read_csv((BUNDLE / "series" / f"{publish.OPSD_ID}.csv").read_bytes())
    idx = pd.DatetimeIndex(table.timestamps, name="utc")
    return pd.Series(table.values["de_load_forecast"], index=idx, dtype=float)


@pytest.fixture(scope="module")
def opsd_de() -> pd.DataFrame:
    if not OPSD_CSV.exists():
        pytest.skip(f"OPSD source not cached at {OPSD_CSV}")
    assert sources.sha256_file(OPSD_CSV) == sources.OPSD_CSV_SHA256
    return opsd.read_de(OPSD_CSV)


def test_published_forecast_does_not_reconstruct_actual_load(opsd_de):
    """The published forecast equals the source forecast but not the (non-open) actual load.

    Even an oracle affine fit (a * forecast + b, fitted to the secret actual values) misses the
    actual load by > 1 GW RMS and by > 500 MW in most hours, and by > 500 MW on every stress day.
    """
    pub = _published_forecast()
    src = opsd_de[opsd.LOAD_FORECAST_COL].reindex(pub.index)
    both = pub.notna() & src.notna()
    assert (pub.isna() == src.isna()).all()
    assert np.array_equal(pub[both].to_numpy(), src[both].to_numpy())  # positive control
    actual = opsd_de[opsd.LOAD_COL].reindex(pub.index)
    m = pub.notna() & actual.notna()
    f, a = pub[m].to_numpy(), actual[m].to_numpy()
    x = np.c_[f, np.ones_like(f)]
    coef, *_ = np.linalg.lstsq(x, a, rcond=None)
    err = a - x @ coef
    assert np.sqrt(np.mean(err**2)) > 1000.0
    assert np.mean(np.abs(err) > 500.0) > 0.5
    for day, _ in power_hourly.STRESS_DAYS:
        t = pd.Timestamp(day, tz="UTC")
        sel = (pub.index >= t) & (pub.index < t + pd.Timedelta(days=1))
        fd, ad = pub[sel].to_numpy(), actual[sel].to_numpy()
        xd = np.c_[fd, np.ones_like(fd)]
        cd, *_ = np.linalg.lstsq(xd, ad, rcond=None)
        assert np.max(np.abs(ad - xd @ cd)) > 500.0, day


# --- determinism and checksums --------------------------------------------------------------


def test_two_builds_are_byte_identical_and_equal_the_committed_bundle():
    first = publish.build_bundle(_carry_inputs()).files
    second = publish.build_bundle(_carry_inputs()).files
    assert first == second
    committed = {
        p.relative_to(BUNDLE).as_posix(): p.read_bytes()
        for p in BUNDLE.rglob("*")
        if p.is_file() and not p.name.startswith(".")
    }
    assert first == committed


@pytest.mark.skipif(
    not (OPSD_CSV.exists() and POWER_CACHE.exists()), reason="raw sources not cached"
)
def test_build_from_raw_sources_equals_the_committed_bundle():
    inputs = publish.Inputs(
        opsd_csv=OPSD_CSV,
        power_cache=POWER_CACHE,
        previous=None,
        bundle_version=CATALOG["bundle_version"],
    )
    rebuilt = publish.build_bundle(inputs)
    assert any("re-derived from the OPSD source" in n for n in rebuilt.notes)
    assert any("cached raw POWER responses" in n for n in rebuilt.notes)
    for rel, data in rebuilt.files.items():
        assert (BUNDLE / rel).read_bytes() == data, rel


def test_manifest_checksums_cover_every_file():
    listed = {f["path"]: f for f in MANIFEST["files"]}
    on_disk = {
        p.relative_to(BUNDLE).as_posix()
        for p in BUNDLE.rglob("*")
        if p.is_file() and p.name != "manifest.json" and not p.name.startswith(".")
    }
    assert set(listed) == on_disk
    assert "catalog.json" in listed
    for rel, f in listed.items():
        data = (BUNDLE / rel).read_bytes()
        assert bundle.sha256(data) == f["sha256"] and len(data) == f["bytes"], rel
    assert MANIFEST["total_bytes"] == sum(f["bytes"] for f in listed.values())
    total = MANIFEST["total_bytes"] + (BUNDLE / "manifest.json").stat().st_size
    assert total < 3_000_000
    for e in CATALOG["entries"]:
        if e["artifact"]:
            assert listed[e["artifact"]["path"]]["sha256"] == e["artifact"]["sha256"]


def test_entries_are_schema_valid_and_honest():
    assert CATALOG["schema_version"] == bundle.SCHEMA_VERSION
    assert set(ENTRIES) == {
        publish.OPSD_ID,
        publish.WEATHER_ID,
        publish.RESOURCE_ID,
        publish.DAILY_ID,
        publish.DERIVED_ID,
        publish.ANALOGUE_ID,
    }
    for e in CATALOG["entries"]:
        assert bundle.validate_entry(e) == [], e["id"]
        assert e["category"] not in ("network_model", "precomputed_experiment")
    for eid in (publish.WEATHER_ID, publish.RESOURCE_ID, publish.DAILY_ID):
        e = ENTRIES[eid]
        assert e["provenance"] == "modeled" and "not station" in e["data_nature"]
        assert all(p["grid_note"] for p in e["spatial"]["points"])
    assert ENTRIES[publish.OPSD_ID]["provenance"] == "estimated"
    assert "forecast" in ENTRIES[publish.OPSD_ID]["data_nature"]
    analogue = ENTRIES[publish.ANALOGUE_ID]
    assert analogue["links"]["network_id"] == "scigrid-de"
    assert analogue["links"]["scenario_ids"] == sorted(
        p.stem for p in sources.SCENARIO_OUT_DIR.glob("*.yaml")
    )
    use = analogue["use_in_scenario"]
    assert use["available"] is True and use["network_id"] == "scigrid-de"
    assert use["preset_id"] in analogue["links"]["scenario_ids"]
    assert use["route"] == f"/studio?network=scigrid-de&preset={use['preset_id']}"
    for eid in (
        publish.OPSD_ID,
        publish.WEATHER_ID,
        publish.RESOURCE_ID,
        publish.DAILY_ID,
        publish.DERIVED_ID,
    ):
        assert ENTRIES[eid]["use_in_scenario"]["available"] is False
        assert publish.ANALOGUE_ID in ENTRIES[eid]["use_in_scenario"]["rationale"]


def test_daily_entry_covers_the_load_forecast_on_utc_days():
    daily, forecast = ENTRIES[publish.DAILY_ID], ENTRIES[publish.OPSD_ID]
    assert daily["category"] == "weather_reanalysis"
    assert daily["temporal"]["resolution"] == "P1D"
    assert daily["temporal"]["start_utc"] == forecast["temporal"]["start_utc"]
    assert daily["temporal"]["end_utc"] == "2020-09-30T00:00:00Z"
    assert forecast["temporal"]["end_utc"] == "2020-09-30T23:00:00Z"
    assert daily["artifact"]["rows"] == len(power_daily.days()) == 2100
    assert daily["artifact"]["bytes"] <= 600_000
    ghi = [s for s in daily["series"] if s["id"].endswith("_ghi")]
    assert len(ghi) == 4 and all(s["unit"] == "W/m²" for s in ghi)
    text = daily["description"]
    for phrase in ("not station data", "computed by GridStorm", "UTC", publish.OPSD_ID, "causal"):
        assert phrase in text, phrase
    checks = {c["name"]: c["status"] for c in daily["quality"]["checks"]}
    for name in (
        "time_standard_utc",
        "utc_day_boundaries",
        "daily_utc_grid",
        "coverage_matches_load_forecast",
        "consistent_with_hourly_entries",
    ):
        assert checks[name] == "pass", name
    assert checks["complete_day_rule"] in ("pass", "warn")
    _, table = bundle.read_csv((BUNDLE / daily["artifact"]["path"]).read_bytes())
    assert table.timestamps == power_daily.days()


def test_studio_presets_are_byte_identical_to_the_scenarios():
    scenarios = sorted(sources.SCENARIO_OUT_DIR.glob("*.yaml"))
    assert len(scenarios) == 3
    for path in scenarios:
        assert (publish.PRESET_DIR / path.name).read_bytes() == path.read_bytes(), path.name


def test_verify_detects_preset_drift(copy, tmp_path, monkeypatch):
    presets = tmp_path / "presets"
    presets.mkdir()
    for path in sources.SCENARIO_OUT_DIR.glob("*.yaml"):
        shutil.copy(path, presets / path.name)
    target = presets / f"{publish.ANALOGUE_PRESET}.yaml"
    target.write_bytes(target.read_bytes() + b"# drift\n")
    monkeypatch.setattr(publish, "PRESET_DIR", presets)
    errors, _ = publish.verify(copy, _carry_inputs(copy))
    assert any("Studio preset copies differ" in e for e in errors), errors


def test_power_requests_are_utc_and_recorded():
    record = json.loads(power_hourly.RECORD_PATH.read_text("utf-8"))
    assert len(record["requests"]) == len(power_hourly.requests())
    for rec, req in zip(record["requests"], power_hourly.requests(), strict=True):
        assert rec["url"] == req.url and "time-standard=UTC" in rec["url"]
        assert rec["time_standard"] == "UTC" and rec["fill_value"] == -999.0
        assert len(rec["response_sha256"]) == 64 and rec["retrieved_at"]


def test_daily_requests_are_yearly_hourly_utc_and_recorded():
    record = json.loads(power_daily.RECORD_PATH.read_text("utf-8"))
    reqs = power_daily.requests()
    assert len(reqs) == 4 * 6 and len(record["requests"]) == len(reqs)
    assert power_daily.ranges()[0] == ("20150101", "20151231")
    assert power_daily.ranges()[-1] == ("20200101", "20200930")
    for rec, req in zip(record["requests"], reqs, strict=True):
        assert rec["url"] == req.url and rec["url"].startswith(sources.POWER_HOURLY_URL + "?")
        assert "time-standard=UTC" in rec["url"] and "/daily/" not in rec["url"]
        assert rec["time_standard"] == "UTC" and rec["fill_value"] == -999.0
        assert len(rec["response_sha256"]) == 64 and rec["retrieved_at"]
        assert rec["api"]["version"] and len(rec["daily_values_sha256"]) == 64
        days = power_daily.request_days(rec["start"], rec["end"])
        assert rec["days"] == len(days) and rec["start"][:4] == rec["end"][:4]
        assert set(rec["incomplete_days"]) == set(power_hourly.PARAMETERS)


# --- quality --------------------------------------------------------------------------------


def test_quality_keeps_missing_as_null_and_counts_completeness():
    grid = bundle.hourly_range(_ts(2017, 1, 1), _ts(2017, 1, 1, 5))  # 6 hours
    rows = [grid[i] for i in (0, 1, 2, 4, 5)]  # hour 3 absent
    table = bundle.Table(rows, {"a": [1.0, None, None, 0.0, 2.5], "b": [1.0, 2.0, 3.0, 4.0, 5.0]})
    q = bundle.table_quality(table, grid)
    assert q["rows"] == 5 and q["expected_rows"] == 6
    assert q["missing_values"] == {"a": 3, "b": 1}
    assert q["completeness_pct"] == round(100 * (12 - 4) / 12, 3)
    assert q["missing_policy"] == "kept-as-null"
    assert bundle.missing_runs(rows, table.values["a"]) == [(grid[1], 2)]
    series = [bundle.Series(s, s, "u", "q", None, 2, "nasa-power:T2M") for s in ("a", "b")]
    text = bundle.write_csv(table, series).decode()
    assert text.splitlines()[2] == "2017-01-01T01:00:00Z,,2"
    assert text.splitlines()[4] == "2017-01-01T04:00:00Z,0,4"  # a real zero stays 0
    checks = {c["name"]: c for c in bundle.grid_checks(table, grid)}
    assert checks["hourly_utc_grid"]["status"] == "fail"
    assert checks["gaps"]["status"] == "warn"
    with pytest.raises(ValueError):
        bundle.table_quality(bundle.Table([_ts(2018, 1, 1)], {"a": [1.0]}), grid)


def _hours(day: datetime, values: list[float | None]) -> dict[datetime, float | None]:
    return {day + timedelta(hours=h): v for h, v in enumerate(values)}


def test_daily_mean_uses_exactly_the_24_utc_hours_of_the_day():
    day = _ts(2017, 3, 26)  # CET -> CEST switch: still 24 UTC hours
    col = _hours(day, [float(h) for h in range(24)])
    col[day - timedelta(hours=1)] = 1000.0  # previous UTC day's last hour
    col[day + timedelta(hours=24)] = 1000.0  # next UTC day's first hour
    assert power_daily.day_mean(col, day) == sum(range(24)) / 24
    assert power_daily.daily_means(col, [day]) == [11.5]


@pytest.mark.parametrize("gap", [0, 13, 23])
def test_daily_mean_of_a_partial_day_is_missing(gap):
    day = _ts(2017, 1, 1)
    full = _hours(day, [1.0] * 24)
    missing = dict(full)
    missing[day + timedelta(hours=gap)] = None  # fill value -999 after parse_response
    absent = {t: v for t, v in full.items() if t != day + timedelta(hours=gap)}
    assert power_daily.day_mean(full, day) == 1.0
    assert power_daily.day_mean(missing, day) is None
    assert power_daily.day_mean(absent, day) is None


def test_daily_days_reject_non_utc_day_starts():
    assert power_daily.days()[0] == _ts(2015, 1, 1)
    assert power_daily.days()[-1] == _ts(2020, 9, 30)
    with pytest.raises(ValueError):
        power_daily.days(_ts(2017, 1, 1, 1), _ts(2017, 1, 2))
    cet = timezone(timedelta(hours=1))
    with pytest.raises(ValueError):
        power_daily.days(datetime(2017, 1, 1, tzinfo=cet), datetime(2017, 1, 2, tzinfo=cet))


def _power_doc(day: datetime, hours: int, fill_at: int | None = None) -> bytes:
    values = {}
    for h in range(hours):
        t = day + timedelta(hours=h)
        values[f"{t:%Y%m%d%H}"] = -999.0 if h == fill_at else round(0.5 + h / 10, 2)
    doc = {
        "header": {"time_standard": "UTC", "fill_value": -999.0},
        "properties": {"parameter": {p: dict(values) for p in power_hourly.PARAMETERS}},
    }
    return json.dumps(doc).encode()


def test_daily_summary_counts_incomplete_days_and_is_deterministic():
    day = _ts(2017, 1, 1)
    grid = power_daily.days(day, day + timedelta(days=1))
    _, cols = power_hourly.parse_response(_power_doc(day, 48, fill_at=30))
    first = power_daily.daily_summary("berlin", cols, grid)
    assert first == power_daily.daily_summary("berlin", cols, grid)
    assert first["days"] == 2
    assert first["incomplete_days"] == {p: ["2017-01-02"] for p in power_hourly.PARAMETERS}
    _, other = power_hourly.parse_response(_power_doc(day, 48))
    second = power_daily.daily_summary("berlin", other, grid)
    assert second["incomplete_days"] == {p: [] for p in power_hourly.PARAMETERS}
    assert second["daily_values_sha256"] != first["daily_values_sha256"]
    # day 1 is identical in both responses, so the published value is the same
    first_day = power_daily.daily_means(cols["T2M"], grid)[0]
    assert first_day == power_daily.daily_means(other["T2M"], grid)[0] is not None


def test_daily_grid_checks_use_days():
    grid = power_daily.days(_ts(2017, 1, 1), _ts(2017, 1, 4))
    table = bundle.Table(grid, {"a": [1.0, None, None, 2.0]})
    checks = {c["name"]: c for c in bundle.grid_checks(table, grid, bundle.DAY)}
    assert checks["daily_utc_grid"]["status"] == "pass"
    assert checks["gaps"]["detail"].endswith("a: 2017-01-02T00:00:00Z +2 d")
    assert bundle.missing_runs(grid, table.values["a"], bundle.DAY) == [(grid[1], 2)]


@pytest.mark.parametrize(
    ("value", "decimals", "text"),
    [
        (None, 2, ""),
        (float("nan"), 2, ""),
        (0.0, 2, "0"),
        (-0.001, 2, "0"),
        (1.50, 2, "1.5"),
        (39723.0, 0, "39723"),
        (1.03749999, 4, "1.0375"),
        (-12.5, 1, "-12.5"),
    ],
)
def test_number_formatting(value, decimals, text):
    assert bundle.fmt_num(value, decimals) == text


# --- UTC parsing ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "2017-01-01T00:00:00+01:00",
        "2017-01-01 00:00:00",
        "2017-01-01T00:00Z",
        "2017-01-01T00:00:00",
    ],
)
def test_parse_utc_rejects_non_bundle_forms(text):
    with pytest.raises(ValueError):
        bundle.parse_utc(text)


def test_read_csv_rejects_unordered_or_duplicate_hours():
    ok = b"utc,a\n2017-01-01T00:00:00Z,1\n2017-01-01T01:00:00Z,\n"
    ids, table = bundle.read_csv(ok)
    assert ids == ["a"] and table.values["a"] == [1.0, None]
    assert table.timestamps[1] - table.timestamps[0] == timedelta(hours=1)
    for bad in (
        b"utc,a\n2017-01-01T01:00:00Z,1\n2017-01-01T00:00:00Z,2\n",
        b"utc,a\n2017-01-01T00:00:00Z,1\n2017-01-01T00:00:00Z,2\n",
        b"utc,a\r\n2017-01-01T00:00:00Z,1\r\n",
        b"utc,a\n2017-01-01T00:00:00Z,1,2\n",
    ):
        with pytest.raises(ValueError):
            bundle.read_csv(bad)


def _opsd_fixture(path: Path, shift_local: bool = False) -> str:
    """Tiny OPSD-shaped CSV across the 2015-03-29 CET -> CEST switch (01:00 UTC)."""
    col = sources.OPSD_LOAD_FORECAST_COL
    with path.open("w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(
            ["utc_timestamp", "cet_cest_timestamp", "DE_load_actual_entsoe_transparency", col]
        )
        t = _ts(2015, 3, 28, 22)
        for i in range(8):
            offset = 2 if t >= _ts(2015, 3, 29, 1) else 1
            if shift_local and i == 4:
                offset += 1
            local = (t + timedelta(hours=offset)).strftime("%Y-%m-%dT%H:%M:%S") + f"+0{offset}00"
            w.writerow([bundle.fmt_utc(t), local, "1", "" if i == 3 else f"{50000 + i}.0000"])
            t += timedelta(hours=1)
    return sources.sha256_file(path)


def test_load_opsd_parses_utc_across_dst(tmp_path):
    path = tmp_path / "opsd.csv"
    digest = _opsd_fixture(path)
    table, checks = publish.load_opsd(path, digest, _ts(2015, 3, 28, 23), _ts(2015, 3, 29, 5))
    assert table.timestamps == bundle.hourly_range(_ts(2015, 3, 28, 23), _ts(2015, 3, 29, 5))
    assert table.values["de_load_forecast"][:4] == [50001.0, 50002.0, None, 50004.0]
    status = {c["name"]: c["status"] for c in checks}
    assert status["dst_free_utc"] == "pass" and status["source_hourly_grid"] == "pass"
    assert (
        "1 CET/CEST offset changes"
        in next(c for c in checks if c["name"] == "dst_free_utc")["detail"]
    )
    assert (
        "dropped 1 source row(s)"
        in next(c for c in checks if c["name"] == "coverage_trim")["detail"]
    )
    with pytest.raises(ValueError, match="sha256"):
        publish.load_opsd(path, "0" * 64)


def test_load_opsd_flags_inconsistent_local_time(tmp_path):
    path = tmp_path / "opsd.csv"
    digest = _opsd_fixture(path, shift_local=True)
    _, checks = publish.load_opsd(path, digest, _ts(2015, 3, 28, 22), _ts(2015, 3, 29, 5))
    assert {c["name"]: c["status"] for c in checks}["dst_free_utc"] == "fail"


def test_power_response_must_be_utc():
    doc = {
        "header": {"time_standard": "LST", "fill_value": -999.0},
        "properties": {"parameter": {p: {"2017010100": 1.0} for p in power_hourly.PARAMETERS}},
    }
    with pytest.raises(ValueError, match="UTC"):
        power_hourly.parse_response(json.dumps(doc).encode())
    doc["header"]["time_standard"] = "UTC"
    doc["properties"]["parameter"]["T2M"]["2017010100"] = -999.0
    _, cols = power_hourly.parse_response(json.dumps(doc).encode())
    assert cols["T2M"] == {_ts(2017, 1, 1, 0): None}
    assert cols["WS10M"] == {_ts(2017, 1, 1, 0): 1.0}


# --- verify ---------------------------------------------------------------------------------


@pytest.fixture
def copy(tmp_path) -> Path:
    out = tmp_path / "observatory"
    shutil.copytree(BUNDLE, out)
    return out


def _rehash(out: Path) -> None:
    """Re-sign a tampered bundle consistently (artifact hashes, catalog, manifest)."""
    catalog = json.loads((out / "catalog.json").read_text("utf-8"))
    for e in catalog["entries"]:
        if e["artifact"]:
            data = (out / e["artifact"]["path"]).read_bytes()
            e["artifact"]["sha256"] = bundle.sha256(data)
            e["artifact"]["bytes"] = len(data)
    (out / "catalog.json").write_bytes(bundle.dump_json(catalog))
    manifest = json.loads((out / "manifest.json").read_text("utf-8"))
    for f in manifest["files"]:
        data = (out / f["path"]).read_bytes()
        f["sha256"], f["bytes"] = bundle.sha256(data), len(data)
    manifest["total_bytes"] = sum(f["bytes"] for f in manifest["files"])
    (out / "manifest.json").write_bytes(bundle.dump_json(manifest))


def _replace(path: Path, old: str, new: str) -> None:
    text = path.read_text("utf-8")
    assert old in text
    path.write_bytes(text.replace(old, new, 1).encode("utf-8"))


def test_verify_passes_on_the_committed_bundle(copy):
    errors, notes = publish.verify(copy, _carry_inputs(copy))
    assert errors == []
    assert any("carried forward" in n for n in notes)


def test_verify_detects_unsigned_byte_change(copy):
    _replace(
        copy / "series" / f"{publish.OPSD_ID}.csv",
        "2015-01-01T00:00:00Z,39723",
        "2015-01-01T00:00:00Z,39724",
    )
    errors, _ = publish.verify(copy, _carry_inputs(copy))
    assert any("differ from manifest.json" in e for e in errors)


def test_verify_detects_resigned_power_values(copy):
    path = copy / "series" / f"{publish.WEATHER_ID}.csv"
    _replace(path, "2015-01-17T00:00:00Z,2.51,", "2015-01-17T00:00:00Z,2.52,")
    _rehash(copy)
    errors, _ = publish.verify(copy, _carry_inputs(copy))
    assert any("request record" in e for e in errors), errors


def test_verify_detects_resigned_daily_values(copy):
    path = copy / "series" / f"{publish.DAILY_ID}.csv"
    _replace(path, "2015-01-01T00:00:00Z,0.96,", "2015-01-01T00:00:00Z,0.97,")
    _rehash(copy)
    errors, _ = publish.verify(copy, _carry_inputs(copy))
    assert any("daily means" in e and "request record" in e for e in errors), errors


def test_verify_detects_resigned_derived_values(copy):
    path = copy / "series" / f"{publish.DERIVED_ID}.csv"
    _replace(path, "2011-01-01T00:00:00Z,1.0375,", "2011-01-01T00:00:00Z,1.0376,")
    _rehash(copy)
    errors, _ = publish.verify(copy, _carry_inputs(copy))
    assert any("differs from the re-derived bundle" in e for e in errors), errors


def test_verify_detects_resigned_metadata_change(copy):
    _replace(copy / "catalog.json", '"completeness_pct": 99.952', '"completeness_pct": 100.0')
    _rehash(copy)
    errors, _ = publish.verify(copy, _carry_inputs(copy))
    assert any("catalog.json: differs from the re-derived bundle" in e for e in errors), errors


def test_verify_detects_restricted_series(copy):
    _replace(
        copy / "manifest.json",
        '"source_key": "opsd:DE_load_forecast_entsoe_transparency"',
        '"source_key": "opsd:DE_wind_onshore_capacity"',
    )
    errors, _ = publish.verify(copy, _carry_inputs(copy))
    assert any("restricted" in e for e in errors), errors


def test_verify_detects_unlisted_file(copy):
    (copy / "series" / "extra.csv").write_bytes(b"utc,a\n")
    errors, _ = publish.verify(copy, _carry_inputs(copy))
    assert any("not listed" in e for e in errors)


@pytest.mark.skipif(not OPSD_CSV.exists(), reason="OPSD source not cached")
def test_verify_with_source_detects_resigned_forecast(copy):
    _replace(
        copy / "series" / f"{publish.OPSD_ID}.csv",
        "2015-01-01T00:00:00Z,39723",
        "2015-01-01T00:00:00Z,39724",
    )
    _rehash(copy)
    inputs = _carry_inputs(copy)
    inputs.opsd_csv = OPSD_CSV
    errors, _ = publish.verify(copy, inputs)
    assert any(f"series/{publish.OPSD_ID}.csv: differs" in e for e in errors), errors
