"""Health, readiness, network catalog, assets, GeoJSON and analytics endpoints (contract §6)."""

from __future__ import annotations

import httpx
import pytest

from gs_helpers import PROVENANCE, assert_error, assert_page, iter_pages

ASSET_TYPES = [
    "buses",
    "lines",
    "transformers",
    "links",
    "generators",
    "loads",
    "storage_units",
    "stores",
    "carriers",
]


@pytest.fixture(scope="module")
def networks(client: httpx.Client) -> list[dict]:
    items = iter_pages(client, "/api/v1/networks", limit=10)
    assert items, "network catalog is empty"
    return items


def test_health(client: httpx.Client) -> None:
    r = client.get("/health")
    assert r.status_code == 200, r.text
    body = r.json()
    assert {"status", "version", "git_sha"} <= set(body), body
    assert body["status"] == "ok"


def test_ready_reports_every_check(client: httpx.Client) -> None:
    r = client.get("/ready")
    assert r.status_code in (200, 503), r.text
    body = r.json()
    assert {"status", "checks"} <= set(body), body
    assert {"database", "storage", "solver", "datasets"} <= set(body["checks"]), body["checks"]
    if r.status_code == 200:
        assert body["status"] in {"ok", "ready"}, body


def test_unknown_route_uses_error_shape(client: httpx.Client) -> None:
    assert_error(client.get("/api/v1/does-not-exist"), 404)


def test_network_list_and_ids(networks: list[dict]) -> None:
    ids = [n["id"] for n in networks]
    assert len(ids) == len(set(ids)), ids
    assert "ac-dc-meshed" in ids, ids


@pytest.mark.parametrize(("limit", "offset"), [(1, 0), (1, 1), (2, 0)])
def test_network_pagination(client: httpx.Client, networks, limit: int, offset: int) -> None:
    r = client.get("/api/v1/networks", params={"limit": limit, "offset": offset})
    assert r.status_code == 200, r.text
    items = assert_page(r.json(), limit=limit, offset=offset)
    assert [n["id"] for n in items] == [n["id"] for n in networks][offset : offset + limit]


@pytest.mark.parametrize("params", [{"limit": -1}, {"limit": 0}, {"offset": -5}, {"limit": "x"}])
def test_bad_pagination_rejected(client: httpx.Client, params: dict) -> None:
    assert_error(client.get("/api/v1/networks", params=params), {400, 422})


def test_huge_limit_is_capped_or_rejected(client: httpx.Client) -> None:
    r = client.get("/api/v1/networks", params={"limit": 10**9})
    if r.status_code == 200:
        assert r.json()["limit"] < 10**9, "limit must be capped server-side"
    else:
        assert_error(r, {400, 422})


def test_network_detail(client: httpx.Client, networks: list[dict]) -> None:
    for n in networks:
        r = client.get(f"/api/v1/networks/{n['id']}")
        assert r.status_code == 200, r.text
        body = r.json()
        text = r.text
        assert "manifest" in text and "assumptions" in text, sorted(body)
        manifest = body.get("manifest")
        assert manifest and manifest.get("schema_version") == "dataset-manifest/1.0", manifest
        assert manifest["license"]["spdx"], manifest["license"]
        assert manifest["provenance_class"] in PROVENANCE, manifest["provenance_class"]
        for f in manifest["files"]:
            assert len(f["sha256"]) == 64, f


@pytest.mark.parametrize("bad", ["nope", "..", "..%2F..%2Fetc", "x' OR '1'='1"])
def test_unknown_network_404(client: httpx.Client, bad: str) -> None:
    r = client.get(f"/api/v1/networks/{bad}")
    assert_error(r, {404, 422})


def test_assets_pages_are_consistent(client: httpx.Client) -> None:
    nid = "ac-dc-meshed"
    for t in ASSET_TYPES:
        r = client.get(f"/api/v1/networks/{nid}/assets", params={"type": t, "limit": 1000})
        assert r.status_code == 200, f"{t}: {r.text[:300]}"
        items = assert_page(r.json())
        ids = [row["id"] for row in items]
        assert len(ids) == len(set(ids)), f"duplicate {t} ids"
    lines = client.get(f"/api/v1/networks/{nid}/assets", params={"type": "lines"}).json()
    assert lines["total"] > 0


@pytest.mark.parametrize("bad", ["", "users", "buses;DROP TABLE jobs", "../manifest"])
def test_assets_bad_type_rejected(client: httpx.Client, bad: str) -> None:
    r = client.get("/api/v1/networks/ac-dc-meshed/assets", params={"type": bad})
    assert_error(r, {400, 404, 422})


def test_geojson(client: httpx.Client, networks: list[dict]) -> None:
    for n in networks:
        nid = n["id"]
        r = client.get(f"/api/v1/networks/{nid}/geojson")
        assert r.status_code == 200, r.text
        fc = r.json()
        assert fc["type"] == "FeatureCollection"
        assert fc["features"], nid
        buses = {
            row["id"]
            for row in iter_pages(client, f"/api/v1/networks/{nid}/assets", limit=500, type="buses")
        }
        kinds = set()
        for f in fc["features"]:
            g = f["geometry"]
            kinds.add(g["type"])
            assert "id" in f["properties"], f["properties"]
            if g["type"] == "Point":
                assert f["properties"]["id"] in buses, f["properties"]["id"]
                coords = [g["coordinates"]]
            else:
                assert g["type"] == "LineString", g["type"]
                coords = g["coordinates"]
            for x, y in coords:
                assert x == x and y == y, "NaN coordinate"  # noqa: PLR0124
        assert "Point" in kinds, nid
        detail = client.get(f"/api/v1/networks/{nid}").json()
        if "geographic" in str(detail) and "schematic" not in str(detail):
            for f in fc["features"]:
                pts = (
                    [f["geometry"]["coordinates"]]
                    if f["geometry"]["type"] == "Point"
                    else f["geometry"]["coordinates"]
                )
                for lon, lat in pts:
                    assert -180 <= lon <= 180 and -90 <= lat <= 90, (nid, lon, lat)


@pytest.mark.parametrize("kind", ["capacity", "energy_balance", "costs"])
def test_analytics(client: httpx.Client, kind: str) -> None:
    r = client.get(f"/api/v1/networks/ac-dc-meshed/analytics/{kind}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "provenance" in r.text, f"analytics/{kind} carries no provenance label"
    assert body


def test_analytics_unknown_kind(client: httpx.Client) -> None:
    assert_error(client.get("/api/v1/networks/ac-dc-meshed/analytics/../../x"), {400, 404, 422})
    assert_error(client.get("/api/v1/networks/ac-dc-meshed/analytics/emissions_magic"), {404, 422})
