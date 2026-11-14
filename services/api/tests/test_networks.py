from __future__ import annotations

from conftest import NETWORK_ID


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["version"]
    assert "git_sha" in body


def test_ready_reports_each_check_and_database_kind(client_factory):
    # precomputed mode skips the solver probe (no live solves); the live probe runs in the
    # e2e/docker checks.
    client = client_factory(execution_mode="precomputed")
    r = client.get("/ready")
    body = r.json()
    assert set(body["checks"]) == {"database", "storage", "solver", "datasets"}
    assert body["checks"]["database"]["status"] == "ok"
    assert body["checks"]["database"]["kind"] == "sqlite-ephemeral"
    assert body["checks"]["storage"]["status"] == "ok"
    assert body["checks"]["solver"]["status"] == "skipped"
    # the fixture catalog lists one broken network → datasets check fails honestly
    assert body["checks"]["datasets"]["status"] == "error"
    assert "broken-net" in body["checks"]["datasets"]["detail"]
    assert r.status_code == 503 and body["status"] == "not_ready"


def test_list_networks_and_pagination(client):
    r = client.get("/api/v1/networks")
    assert r.status_code == 200
    page = r.json()
    assert page["total"] == 1 and page["limit"] == 50 and page["offset"] == 0
    net = page["items"][0]
    assert net["id"] == NETWORK_ID
    assert net["coordinate_kind"] == "schematic"
    assert net["has_network_file"] is True
    assert net["license"]["spdx"] == "CC0-1.0"
    assert client.get("/api/v1/networks?offset=1").json()["items"] == []
    bad = client.get("/api/v1/networks?limit=0")
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "validation_error"


def test_network_detail_and_errors(client):
    r = client.get(f"/api/v1/networks/{NETWORK_ID}")
    assert r.status_code == 200
    body = r.json()
    assert body["manifest"]["schema_version"] == "dataset-manifest/1.0"
    assert body["assumptions"] == ["synthetic test fixture"]
    assert body["field_provenance"]["buses.x"] == "synthetic"
    r = client.get("/api/v1/networks/nope")
    assert r.status_code == 404
    assert r.json() == {
        "error": {
            "code": "network_not_found",
            "message": "unknown network 'nope'",
            "details": {"network_id": "nope"},
        }
    }
    r = client.get("/api/v1/networks/broken-net")
    assert r.status_code == 503 and r.json()["error"]["code"] == "network_unavailable"


def test_assets_paginated(client):
    r = client.get(f"/api/v1/networks/{NETWORK_ID}/assets?type=buses&limit=2&offset=1")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3 and [b["id"] for b in body["items"]] == ["b1", "b2"]
    assert body["field_provenance"] == {"buses.x": "synthetic"}
    assert client.get(f"/api/v1/networks/{NETWORK_ID}/assets?type=nonsense").status_code == 422
    assert client.get(f"/api/v1/networks/{NETWORK_ID}/assets").status_code == 422


def test_geojson_keys_by_component(client):
    r = client.get(f"/api/v1/networks/{NETWORK_ID}/geojson")
    assert r.status_code == 200
    fc = r.json()
    assert fc["type"] == "FeatureCollection"
    assert fc["coordinate_kind"] == "schematic"
    keys = [(f["properties"]["component"], f["properties"]["id"]) for f in fc["features"]]
    assert len(keys) == len(set(keys))
    # a line and a transformer share id "l0" and must both be present, distinguished by component
    assert ("line", "l0") in keys and ("transformer", "l0") in keys
    bus = next(f for f in fc["features"] if f["properties"]["id"] == "b1")
    assert bus["geometry"] == {"type": "Point", "coordinates": [1.0, 0.5]}
    line = next(f for f in fc["features"] if f["properties"]["component"] == "line")
    assert line["geometry"]["type"] == "LineString"
    assert all(f["properties"]["coordinate_kind"] == "schematic" for f in fc["features"])


def test_cors_allows_configured_origin_only(client):
    ok = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    other = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in other.headers


def test_openapi_matches_contract_paths(client):
    spec = client.get("/openapi.json").json()
    expected = {
        ("get", "/health"),
        ("get", "/ready"),
        ("get", "/api/v1/networks"),
        ("get", "/api/v1/networks/{network_id}"),
        ("get", "/api/v1/networks/{network_id}/assets"),
        ("get", "/api/v1/networks/{network_id}/geojson"),
        ("get", "/api/v1/networks/{network_id}/analytics/{kind}"),
        ("get", "/api/v1/scenarios"),
        ("post", "/api/v1/scenarios/validate"),
        ("post", "/api/v1/scenarios"),
        ("get", "/api/v1/scenarios/{scenario_id}"),
        ("post", "/api/v1/simulations"),
        ("get", "/api/v1/simulations"),
        ("get", "/api/v1/simulations/{job_id}"),
        ("post", "/api/v1/simulations/{job_id}/cancel"),
        ("get", "/api/v1/simulations/{job_id}/metrics"),
        ("get", "/api/v1/simulations/{job_id}/result"),
        ("get", "/api/v1/simulations/{job_id}/artifacts"),
        ("post", "/api/v1/comparisons"),
        ("get", "/api/v1/comparisons/{comparison_id}"),
        ("get", "/api/v1/reports/{report_id}"),
        ("get", "/api/v1/artifacts"),
        ("get", "/api/v1/artifacts/{engine}/{artifact_id}"),
    }
    actual = {(m, p) for p, ops in spec["paths"].items() for m in ops}
    assert actual == expected
    assert client.get("/docs").status_code == 200
