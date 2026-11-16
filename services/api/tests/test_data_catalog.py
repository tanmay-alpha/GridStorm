"""Data Observatory catalog API (/api/v1/data/catalog…).

Runs against the hand-built fixture bundle in ``tests/fixtures/observatory`` (synthetic values,
built to the observatory contract) and, when present, the real committed ``data/observatory``.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from gridstorm_api.config import REPO_ROOT

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "observatory"
REAL_BUNDLE = REPO_ROOT / "data" / "observatory"
BASE = "/api/v1/data/catalog"


@pytest.fixture
def bundle_dir(workspace: Path) -> Path:
    dest = workspace / "data" / "observatory"
    shutil.copytree(FIXTURE, dest)
    return dest


@pytest.fixture
def obs(bundle_dir: Path, client_factory: Callable[..., TestClient]) -> TestClient:
    return client_factory()


def series(client: TestClient, ds: str, **params: Any) -> Any:
    return client.get(f"{BASE}/{ds}/series", params=params)


# --- list / filters / facets / paging ----------------------------------------------------------
def test_list_merges_bundle_networks_and_studies(obs: TestClient) -> None:
    r = obs.get(BASE, params={"limit": 500})
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [i["id"] for i in body["items"]]
    assert ids[:3] == ["fixture-load-hourly", "fixture-wind-sparse", "fixture-metadata-only"]
    assert "network-tiny-net" in ids
    assert "network-broken-net" not in ids  # unusable network files are not listed
    assert {"study-pypsa-presets", "study-pandapower-n1"} <= set(ids)
    assert body["total"] == len(ids)
    assert body["bundle"]["status"] == "ok"
    assert body["bundle"]["bundle_version"] == "2026-11-17.0"
    for item in body["items"]:
        assert "description" not in item and "transformations" not in item
        assert "checks" not in item["quality"]
    f = body["facets"]
    assert f["category"]["network_model"] == 1
    assert f["category"]["precomputed_experiment"] == 2
    assert f["region"]["DE"] == 2
    assert f["provenance"]["synthetic"] == 2  # fixture-load-hourly + tiny-net
    assert f["source"]["GridStorm test fixture"] == 2


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"category": "historical_demand"}, ["fixture-load-hourly"]),
        ({"provenance": "modeled", "region": "DE"}, ["fixture-wind-sparse"]),
        ({"source": "Restricted test source"}, ["fixture-wind-sparse"]),
        ({"q": "SPARSE wind"}, ["fixture-wind-sparse"]),
        ({"q": "tiny"}, ["network-tiny-net"]),
        ({"category": "network_model"}, ["network-tiny-net"]),
    ],
)
def test_filters(obs: TestClient, params: dict[str, str], expected: list[str]) -> None:
    body = obs.get(BASE, params=params).json()
    assert [i["id"] for i in body["items"]] == expected
    assert body["total"] == len(expected)
    # facets describe the whole catalog, independent of the filter
    assert body["facets"]["category"]["historical_demand"] == 1


def test_paging_and_validation(obs: TestClient) -> None:
    full = obs.get(BASE).json()
    page = obs.get(BASE, params={"limit": 2, "offset": 1}).json()
    assert [i["id"] for i in page["items"]] == [i["id"] for i in full["items"][1:3]]
    assert (page["total"], page["limit"], page["offset"]) == (full["total"], 2, 1)
    r = obs.get(BASE, params={"category": "nope"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    assert obs.get(BASE, params={"limit": 501}).status_code == 422


# --- detail / 404 ------------------------------------------------------------------------------
def test_detail_bundle_entry(obs: TestClient) -> None:
    r = obs.get(f"{BASE}/fixture-load-hourly")
    assert r.status_code == 200
    e = r.json()
    assert e["description"].startswith("Synthetic test fixture")
    assert e["transformations"][0]["step"] == "fixture"
    checks = {c["name"]: c for c in e["quality"]["checks"]}
    assert checks["checksum"]["status"] == "pass"
    assert e["exportable"] is True


def test_detail_network_entry(obs: TestClient) -> None:
    e = obs.get(f"{BASE}/network-tiny-net").json()
    assert e["category"] == "network_model"
    assert e["provenance"] == "synthetic"
    assert e["spatial"] == {"kind": "network", "points": None}  # never invented coordinates
    assert e["region"] is None  # buses in DE and FR: no single region
    assert e["links"]["network_id"] == "tiny-net"
    assert e["links"]["scenario_ids"] == ["preset-base", "preset-stress"]  # preset-bad invalid
    use = e["use_in_scenario"]
    assert use["available"] is True and use["route"] == "/studio?network=tiny-net"
    assert e["source"]["license"]["id"] == "CC0-1.0"
    assert e["temporal"]["start_utc"] == "2020-01-01T00:00:00Z"
    assert e["temporal"]["resolution"] == "PT1H"
    assert e["exportable"] is False and e["series"] == []


def test_detail_experiment_entry(obs: TestClient) -> None:
    e = obs.get(f"{BASE}/study-pandapower-n1").json()
    assert e["category"] == "precomputed_experiment"
    assert e["links"]["study_route"] == "/contingency#n1"
    check = e["quality"]["checks"][0]
    assert check["status"] == "warn" and check["detail"].startswith("2 of 3")
    assert e["use_in_scenario"]["available"] is False
    p = obs.get(f"{BASE}/study-pypsa-presets").json()
    assert p["links"]["scenario_ids"] == ["preset-base-result"]
    assert p["links"]["network_id"] == "tiny-net"


def test_unknown_dataset_404(obs: TestClient) -> None:
    for path in ("nope", "nope/series", "nope/export"):
        r = obs.get(f"{BASE}/{path}")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "not_found"


# --- series ------------------------------------------------------------------------------------
def test_default_window_is_first_documented_window(obs: TestClient) -> None:
    r = series(obs, "fixture-load-hourly")
    assert r.status_code == 200, r.text
    s = r.json()
    assert (s["start_utc"], s["end_utc"]) == ("2015-01-20T00:00:00Z", "2015-01-21T00:00:00Z")
    assert s["resolution"] == "raw" and s["aggregation"] is None
    assert s["points"] == 24 == len(s["timestamps"])
    assert s["timestamps"][0] == "2015-01-20T00:00:00Z"
    assert [x["id"] for x in s["series"]] == ["load_mw", "temp_c"]
    assert s["series"][0]["values"][1] == 50000 + 100 + (19 * 24 + 1) % 7
    assert s["sha256"] and s["bundle_version"] == "2026-11-17.0"
    assert s["missing"] == {"load_mw": 0, "temp_c": 0}


def test_default_window_last_31_days_with_sparse_coverage(obs: TestClient) -> None:
    s = series(obs, "fixture-wind-sparse").json()
    assert (s["start_utc"], s["end_utc"]) == ("2016-12-08T00:00:00Z", "2017-01-08T00:00:00Z")
    assert s["resolution"] == "raw" and s["points"] == 31 * 24
    values = s["series"][0]["values"]
    assert values[: 24 * 24] == [None] * (24 * 24)  # not covered: null, never 0
    assert all(v is not None for v in values[24 * 24 :])
    assert s["missing"] == {"ws10m": 24 * 24}


def test_raw_gaps_and_empty_cells_stay_null(obs: TestClient) -> None:
    s = series(
        obs,
        "fixture-load-hourly",
        start="2015-01-10T00:00:00Z",
        end="2015-01-11T00:00:00Z",
        series="load_mw",
    ).json()
    v = s["series"][0]["values"]
    assert v[5:10] == [None] * 5 and v[4] is not None and v[10] is not None
    assert s["missing"] == {"load_mw": 5}
    s2 = series(obs, "fixture-load-hourly", start="2015-01-02", end="2015-01-03").json()
    load = s2["series"][0]["values"]
    assert load[3] is None and s2["missing"]["load_mw"] == 1


def test_auto_resolution_respects_max_points(obs: TestClient) -> None:
    window = {"start": "2015-01-01T00:00:00Z", "end": "2015-03-01T00:00:00Z"}
    raw = series(obs, "fixture-load-hourly", **window).json()
    assert raw["resolution"] == "raw" and raw["points"] == 59 * 24
    three = series(obs, "fixture-load-hourly", max_points=500, **window).json()
    assert three["resolution"] == "PT3H" and three["points"] == 59 * 8 <= 500
    assert three["aggregation"] == "mean"
    day = series(obs, "fixture-load-hourly", max_points=100, **window).json()
    assert day["resolution"] == "P1D" and day["points"] == 59
    week = series(obs, "fixture-load-hourly", max_points=20, **window).json()
    assert week["resolution"] == "P7D" and week["points"] <= 20
    for s in (raw, three, day, week):
        assert len(s["timestamps"]) == s["points"] == len(s["series"][0]["values"])


def test_raw_or_bucket_over_limit_is_range_too_large(obs: TestClient) -> None:
    window = {"start": "2015-01-01T00:00:00Z", "end": "2015-03-01T00:00:00Z"}
    r = series(obs, "fixture-load-hourly", resolution="raw", max_points=100, **window)
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "range_too_large" and err["details"]["points"] == 59 * 24
    r = series(obs, "fixture-load-hourly", resolution="PT3H", max_points=100, **window)
    assert r.status_code == 422 and r.json()["error"]["code"] == "range_too_large"
    assert series(obs, "fixture-load-hourly", max_points=2001).status_code == 422


def test_range_over_three_years_rejected(obs: TestClient) -> None:
    r = series(obs, "fixture-load-hourly", start="2015-01-01", end="2018-01-02")
    assert r.status_code == 422 and r.json()["error"]["code"] == "range_too_large"
    r = obs.get(
        f"{BASE}/fixture-load-hourly/export", params={"start": "2010-01-01", "end": "2015-01-01"}
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "range_too_large"
    r = series(obs, "fixture-load-hourly", start="2015-01-02", end="2015-01-01")
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_range"
    r = series(obs, "fixture-load-hourly", start="yesterday")
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_datetime"


def test_empty_buckets_are_null_not_zero(obs: TestClient) -> None:
    s = series(
        obs, "fixture-wind-sparse", start="2015-01-01", end="2017-01-08", resolution="P1D"
    ).json()
    values = s["series"][0]["values"]
    filled = [v for v in values if v is not None]
    assert len(filled) == 14  # 7 covered days in 2015 + 7 in 2017
    assert 0 not in values and 0.0 not in filled
    assert s["timestamps"][16] == "2015-01-17T00:00:00Z" and values[16] is not None
    assert values[15] is None and values[23] is None


def test_buckets_are_utc_aligned(obs: TestClient) -> None:
    # a +01:00 start is converted to UTC; PT3H buckets start at 00/03/06… UTC
    s = series(
        obs,
        "fixture-load-hourly",
        start="2015-01-20T02:30:00+01:00",
        end="2015-01-21T00:00:00Z",
        resolution="PT3H",
    ).json()
    assert s["start_utc"] == "2015-01-20T01:30:00Z"
    assert s["timestamps"][:2] == ["2015-01-20T00:00:00Z", "2015-01-20T03:00:00Z"]
    # first bucket only holds the in-window hours 02:00 (01:30 rounds to the 02:00 row)
    assert s["series"][0]["values"][0] == 50000 + 200 + (19 * 24 + 2) % 7
    w = series(
        obs, "fixture-load-hourly", start="2015-01-21", end="2015-02-05", resolution="P7D"
    ).json()
    assert w["timestamps"] == [
        "2015-01-19T00:00:00Z",
        "2015-01-26T00:00:00Z",
        "2015-02-02T00:00:00Z",
    ]  # Mondays 00:00 UTC
    d = series(
        obs,
        "fixture-load-hourly",
        start="2015-01-20",
        end="2015-01-22",
        resolution="P1D",
        agg="max",
        series="load_mw",
    ).json()
    assert d["timestamps"] == ["2015-01-20T00:00:00Z", "2015-01-21T00:00:00Z"]
    hourly = series(
        obs, "fixture-load-hourly", start="2015-01-20", end="2015-01-21", series="load_mw"
    ).json()["series"][0]["values"]
    assert d["series"][0]["values"][0] == max(hourly)
    mean = series(
        obs,
        "fixture-load-hourly",
        start="2015-01-20",
        end="2015-01-21",
        resolution="P1D",
        series="load_mw",
    ).json()["series"][0]["values"][0]
    assert mean == pytest.approx(sum(hourly) / 24)


def test_unknown_series_and_non_series_datasets(obs: TestClient) -> None:
    r = series(obs, "fixture-load-hourly", series="load_mw,nope")
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "unknown_series" and err["details"]["unknown"] == ["nope"]
    for ds in ("fixture-metadata-only", "network-tiny-net", "study-pypsa-presets"):
        r = series(obs, ds)
        assert r.status_code == 409 and r.json()["error"]["code"] == "not_a_series_dataset"
    r = series(obs, "fixture-wind-sparse", resolution="PT3H", start="2015-01-17", end="2015-01-18")
    assert r.status_code == 200  # bucket coarser than raw PT1H


# --- export ------------------------------------------------------------------------------------
def test_export_csv_headers_and_rows(obs: TestClient) -> None:
    r = obs.get(
        f"{BASE}/fixture-load-hourly/export",
        params={"start": "2015-01-10", "end": "2015-01-11", "series": "load_mw"},
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert r.headers["content-disposition"] == (
        'attachment; filename="fixture-load-hourly_2015-01-10_2015-01-11.csv"'
    )
    assert r.headers["cache-control"] == "public, max-age=300"
    lines = r.text.splitlines()
    comments = [x for x in lines if x.startswith("#")]
    entry = obs.get(f"{BASE}/fixture-load-hourly").json()
    assert any(entry["artifact"]["sha256"] in c for c in comments)
    assert any(c.startswith("# license: CC0-1.0") for c in comments)
    assert any(c.startswith("# attribution: GridStorm test fixture") for c in comments)
    data = lines[len(comments) :]
    assert data[0] == "utc,load_mw"
    assert len(data) == 1 + 24 - 5  # 5 absent rows are not filled in
    assert data[1] == f"2015-01-10T00:00:00Z,{float(50000 + (9 * 24) % 7)!r}"


def test_export_forbidden_when_not_permitted(obs: TestClient) -> None:
    for ds in ("fixture-wind-sparse", "network-tiny-net"):
        r = obs.get(f"{BASE}/{ds}/export")
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "export_not_permitted"


# --- integrity ---------------------------------------------------------------------------------
def test_checksum_tamper_returns_503(
    bundle_dir: Path,
    client_factory: Callable[..., TestClient],
) -> None:
    path = bundle_dir / "series" / "fixture-load-hourly.csv"
    path.write_bytes(path.read_bytes().replace(b"50000.0", b"50001.0", 1))
    client = client_factory()
    for suffix in ("series", "export"):
        r = client.get(f"{BASE}/fixture-load-hourly/{suffix}")
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "dataset_unverified"
    e = client.get(f"{BASE}/fixture-load-hourly").json()
    check = next(c for c in e["quality"]["checks"] if c["name"] == "checksum")
    assert check["status"] == "fail" and "sha256" in check["detail"]
    body = client.get(BASE).json()
    assert body["bundle"]["status"] == "degraded"
    assert body["bundle"]["failed_datasets"] == ["fixture-load-hourly"]
    assert series(client, "fixture-wind-sparse").status_code == 200  # other files still served


def _rewrite_catalog(bundle_dir: Path, mutate: Callable[[dict[str, Any]], None]) -> None:
    """Edit catalog.json and re-sign it in manifest.json (a legitimate bundle update)."""
    import hashlib

    cat_path, man_path = bundle_dir / "catalog.json", bundle_dir / "manifest.json"
    catalog = json.loads(cat_path.read_text(encoding="utf-8"))
    mutate(catalog)
    data = json.dumps(catalog).encode("utf-8")
    cat_path.write_bytes(data)
    manifest = json.loads(man_path.read_text(encoding="utf-8"))
    for f in manifest["files"]:
        if f["path"] == "catalog.json":
            f["sha256"], f["bytes"] = hashlib.sha256(data).hexdigest(), len(data)
    man_path.write_text(json.dumps(manifest), encoding="utf-8")


@pytest.mark.parametrize(
    ("network", "preset", "available"),
    [
        ("tiny-net", "preset-base", True),
        ("tiny-net", None, True),
        ("tiny-net", "preset-bad", False),  # invalid preset is not published
        ("tiny-net", "nope", False),
        ("scigrid-de", "preset-base", False),  # network not in this catalog
    ],
)
def test_declared_use_in_scenario_is_validated(
    bundle_dir: Path,
    client_factory: Callable[..., TestClient],
    network: str,
    preset: str | None,
    available: bool,
) -> None:
    route = f"/studio?network={network}" + (f"&preset={preset}" if preset else "")

    def mutate(catalog: dict[str, Any]) -> None:
        entry = next(e for e in catalog["entries"] if e["id"] == "fixture-metadata-only")
        entry["use_in_scenario"] = {
            "available": True,
            "network_id": network,
            "preset_id": preset,
            "route": route,
            "rationale": "declared by the bundle",
        }

    _rewrite_catalog(bundle_dir, mutate)
    client = client_factory()
    e = client.get(f"{BASE}/fixture-metadata-only").json()
    use = e["use_in_scenario"]
    assert use["available"] is available
    warned = [w for w in e["quality"]["warnings"] if w.startswith("use_in_scenario")]
    if available:
        assert use["route"] == route and not warned
    else:
        assert use["route"] is None and len(warned) == 1
    listed = next(i for i in client.get(BASE).json()["items"] if i["id"] == e["id"])
    assert listed["use_in_scenario"] == use


def test_tampered_catalog_drops_bundle_only(
    bundle_dir: Path, client_factory: Callable[..., TestClient]
) -> None:
    cat = bundle_dir / "catalog.json"
    cat.write_text(
        cat.read_text(encoding="utf-8").replace("Fixture hourly", "Forged hourly"), encoding="utf-8"
    )
    client = client_factory()
    body = client.get(BASE).json()
    assert body["bundle"]["status"] == "error"
    assert "catalog.json not verified" in body["bundle"]["detail"]
    ids = [i["id"] for i in body["items"]]
    assert "fixture-load-hourly" not in ids and "network-tiny-net" in ids
    assert client.get(f"{BASE}/fixture-load-hourly").status_code == 404


def test_missing_bundle_keeps_catalog_and_ready(client: TestClient) -> None:
    body = client.get(BASE).json()
    assert body["bundle"]["status"] == "absent"
    ids = {i["id"] for i in body["items"]}
    assert "network-tiny-net" in ids and "study-pypsa-presets" in ids
    ready = client.get("/ready").json()
    # the observatory is not a readiness dependency: same four checks, none mentions it
    assert set(ready["checks"]) == {"database", "storage", "solver", "datasets"}
    assert "observatory" not in json.dumps(ready)


# --- caching -----------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "path",
    [
        BASE,
        f"{BASE}/fixture-load-hourly",
        f"{BASE}/fixture-load-hourly/series",
        f"{BASE}/fixture-load-hourly/export",
    ],
)
def test_etag_and_304(obs: TestClient, path: str) -> None:
    r = obs.get(path)
    assert r.status_code == 200
    etag = r.headers["etag"]
    assert etag.startswith('"') and r.headers["cache-control"] == "public, max-age=300"
    again = obs.get(path, headers={"If-None-Match": etag})
    assert again.status_code == 304 and again.content == b""
    assert obs.get(path, headers={"If-None-Match": f"W/{etag}"}).status_code == 304
    if path.endswith(("series", "export")) or path == BASE:  # the query changes the tag
        other = obs.get(path, params={"limit": 3} if path == BASE else {"series": "load_mw"})
        assert other.status_code == 200 and other.headers["etag"] != etag


# --- real committed data -----------------------------------------------------------------------
@pytest.fixture
def real(client_factory: Callable[..., TestClient]) -> TestClient:
    return client_factory(
        data_dir=REPO_ROOT / "data",
        presets_dir=REPO_ROOT / "packages" / "stormspec" / "presets",
        live_networks={"ac-dc-meshed", "pglib-case14-ieee", "pglib-case118-ieee", "pypsa-eur-be"},
    )


@pytest.mark.skipif(not (REAL_BUNDLE / "catalog.json").is_file(), reason="no data/observatory")
def test_real_bundle_verifies_and_serves(real: TestClient) -> None:
    body = real.get(BASE, params={"limit": 500}).json()
    assert body["bundle"]["status"] == "ok", body["bundle"]
    declared = {
        e["id"]: e for e in json.loads((REAL_BUNDLE / "catalog.json").read_text("utf-8"))["entries"]
    }
    for ds, raw in declared.items():
        e = real.get(f"{BASE}/{ds}").json()
        # every declared Studio mapping is valid in this repository (presets + networks)
        assert e["use_in_scenario"] == raw["use_in_scenario"], ds
        if not e["series"]:
            assert series(real, ds).status_code == 409
            continue
        s = series(real, ds)
        assert s.status_code == 200, (ds, s.text)
        assert s.json()["points"] <= 1500
        exp = real.get(f"{BASE}/{ds}/export")
        assert exp.status_code == (200 if e["exportable"] else 403), (ds, exp.text)
        assert e["exportable"] == (e["source"]["license"]["redistribution"] == "permitted")


def test_real_catalog_networks_and_studies(real: TestClient) -> None:
    body = real.get(BASE, params={"limit": 500}).json()
    by_id = {i["id"]: i for i in body["items"]}
    for net in (
        "ac-dc-meshed",
        "pglib-case14-ieee",
        "pglib-case118-ieee",
        "pypsa-eur-be",
        "scigrid-de",
    ):
        e = by_id[f"network-{net}"]
        assert e["spatial"]["points"] is None
        assert e["use_in_scenario"]["route"] == f"/studio?network={net}"
    assert by_id["network-pglib-case14-ieee"]["region"]["kind"] == "benchmark"
    assert by_id["network-scigrid-de"]["region"]["code"] == "DE"
    assert by_id["study-stormbench"]["links"]["study_route"] == "/benchmarks#stormbench"
    assert by_id["study-grid2op-agents"]["links"]["study_route"] == "/operations"


ANALOGUES = sorted(p.stem for p in (REPO_ROOT / "data" / "scenarios" / "observed").glob("*.yaml"))


@pytest.mark.skipif(not ANALOGUES, reason="no observed-analogue scenarios")
def test_observed_analogue_presets_match_the_study(real: TestClient) -> None:
    """Published presets are byte-identical copies of the generated analogue scenarios, and their
    committed PyPSA artifacts reproduce data/observed/analogue-results.json."""
    import stormspec

    results = json.loads((REPO_ROOT / "data/observed/analogue-results.json").read_text("utf-8"))
    runs = {r["scenario_id"]: r for r in results["runs"]}
    for sid in ANALOGUES:
        src = REPO_ROOT / "data" / "scenarios" / "observed" / f"{sid}.yaml"
        preset = REPO_ROOT / "packages" / "stormspec" / "presets" / f"{sid}.yaml"
        assert preset.read_bytes() == src.read_bytes(), f"{preset} drifted from {src}"
        doc = json.loads((REPO_ROOT / "data/artifacts/pypsa" / f"{sid}.json").read_text("utf-8"))
        payload = doc["payload"]
        h = stormspec.scenario_hash(stormspec.load_scenario(preset))
        assert payload["scenario_hash"] == h == runs[sid]["scenario_hash"]
        for k in ("unserved_energy_mwh", "total_load_mwh", "total_system_cost_eur"):
            assert payload["metrics"][k] == pytest.approx(runs[sid]["metrics"][k], rel=1e-6)
    e = real.get(f"{BASE}/study-observed-analogues").json()
    use = e["use_in_scenario"]
    assert use["available"] is True and use["network_id"] == "scigrid-de"
    assert use["route"] == f"/studio?network=scigrid-de&preset={use['preset_id']}"
    assert sorted(e["links"]["scenario_ids"]) == ANALOGUES
    assert (
        "observed-dunkelflaute-2015-01-20"
        not in real.get(f"{BASE}/study-pypsa-presets").json()["links"]["scenario_ids"]
    )
