from __future__ import annotations

import hashlib
import json

import pytest

from conftest import NETWORK_ID, _precomputed_result, _write_artifact

SIM = "/api/v1/artifacts/pypsa/preset-base-result"
CACHED = [
    "/api/v1/networks",
    f"/api/v1/networks/{NETWORK_ID}",
    f"/api/v1/networks/{NETWORK_ID}/assets?type=buses",
    f"/api/v1/networks/{NETWORK_ID}/geojson",
    "/api/v1/artifacts",
    "/api/v1/artifacts/pandapower/n1-tiny",
    SIM,
    f"{SIM}?view=summary",
]
SUMMARY_KEYS = {
    "schema_version",
    "scenario_id",
    "scenario_hash",
    "network_id",
    "provenance",
    "engine",
    "solver",
    "outcome",
    "metrics",
    "warnings",
}


@pytest.mark.parametrize("url", CACHED)
def test_cacheable_get_sends_cache_control_and_body_etag(client, url):
    r = client.get(url)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=3600"
    assert r.headers["etag"] == f'"{hashlib.sha256(r.content).hexdigest()}"'
    assert client.get(url).headers["etag"] == r.headers["etag"]


@pytest.mark.parametrize("url", CACHED)
def test_if_none_match_revalidates_with_304(client, url):
    etag = client.get(url).headers["etag"]
    for tag in (etag, f"W/{etag}", f'"other", W/{etag}', "*"):
        r = client.get(url, headers={"If-None-Match": tag})
        assert r.status_code == 304, tag
        assert r.content == b""
        assert r.headers["etag"] == etag
        assert r.headers["cache-control"] == "public, max-age=3600"
    stale = client.get(url, headers={"If-None-Match": f'"{"0" * 64}", W/"nope"'})
    assert stale.status_code == 200 and stale.content
    assert stale.headers["etag"] == etag


def test_json_routes_keep_response_model_serialization(client):
    # cached JSON routes still validate through their response_model (same keys as before)
    page = client.get("/api/v1/networks").json()
    assert set(page) == {"items", "total", "limit", "offset"}
    assets = client.get(f"/api/v1/networks/{NETWORK_ID}/assets?type=buses&limit=1").json()
    assert assets["limit"] == 1 and assets["type"] == "buses" and len(assets["items"]) == 1
    arts = client.get("/api/v1/artifacts?engine=pandapower").json()
    ids = {a["artifact_id"] for a in arts["items"]}
    assert ids == {"n1-tiny", "tampered", "listed-but-missing"}


def test_full_artifact_view_is_byte_identical(client, workspace):
    path = workspace / "data" / "artifacts" / "pypsa" / "preset-base-result.json"
    for url in (SIM, f"{SIM}?view=full"):
        r = client.get(url)
        assert r.status_code == 200 and r.content == path.read_bytes()
        assert r.headers["x-gridstorm-payload-verified"] == "true"


def test_summary_view_drops_bulky_simulation_fields(client_factory, workspace):
    pypsa = workspace / "data" / "artifacts" / "pypsa"
    index = json.loads((pypsa / "index.json").read_text())
    index["artifacts"].append(
        {"artifact_id": "bulky", "kind": "simulation", "network_id": NETWORK_ID, "title": "b"}
    )
    (pypsa / "index.json").write_text(json.dumps(index))
    payload = _precomputed_result("h" * 64)
    snapshots = [f"2026-01-01T{h:02d}:00:00Z" for h in range(24)]
    payload.update(
        provenance={"source": "test"},
        snapshots=snapshots,
        snapshot_weightings_h=[1.0] * 24,
        series={"buses.p": {f"b{i}": [float(i)] * 24 for i in range(200)}},
        assets={"lines": [{"id": f"l{i}", "loading_pct": 50.0} for i in range(500)]},
    )
    _write_artifact(pypsa, "bulky", "simulation", "pypsa", payload)
    client = client_factory()

    url = "/api/v1/artifacts/pypsa/bulky"
    full = client.get(url)
    r = client.get(f"{url}?view=summary")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/json"
    assert r.headers["x-gridstorm-payload-verified"] == "true"
    body = r.json()
    assert set(body) == {"artifact", "summary"}
    assert body["artifact"] == full.json()["artifact"]
    assert body["artifact"]["payload_sha256"] == full.json()["artifact"]["payload_sha256"]
    assert set(body["summary"]) == SUMMARY_KEYS
    assert body["summary"] == {k: payload[k] for k in SUMMARY_KEYS}
    assert len(r.content) * 20 < len(full.content)
    assert r.headers["etag"] != full.headers["etag"]


def test_summary_view_of_fixture_simulation_keeps_only_present_keys(client):
    body = client.get(f"{SIM}?view=summary").json()
    assert body["artifact"]["kind"] == "simulation"
    # the fixture payload has no `provenance`; absent keys are omitted, not null-filled
    assert set(body["summary"]) == SUMMARY_KEYS - {"provenance"}
    assert body["summary"]["metrics"] == {"total_load_mwh": 400.0, "unserved_energy_mwh": 0.0}


def test_summary_view_rejects_non_simulation_kinds(client):
    r = client.get("/api/v1/artifacts/pandapower/n1-tiny?view=summary")
    assert r.status_code == 422
    assert r.json()["error"] == {
        "code": "summary_view_unsupported",
        "message": "artifact pandapower/n1-tiny of kind 'n_minus_1' has no summary view",
        "details": {"engine": "pandapower", "artifact_id": "n1-tiny", "kind": "n_minus_1"},
    }
    assert "cache-control" not in r.headers and "etag" not in r.headers
    bad = client.get(f"{SIM}?view=everything")
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize(
    "url",
    [
        "/api/v1/artifacts/pypsa/nope",
        "/api/v1/artifacts/pypsa/nope?view=summary",
        "/api/v1/artifacts/pandapower/listed-but-missing",
        "/api/v1/networks/nope",
        "/api/v1/networks/nope/assets?type=buses",
        "/api/v1/networks/nope/geojson",
    ],
)
def test_errors_carry_no_cache_headers(client, url):
    r = client.get(url, headers={"If-None-Match": "*"})
    assert r.status_code == 404
    assert "cache-control" not in r.headers and "etag" not in r.headers


def test_openapi_documents_summary_view_and_keeps_response_models(client):
    spec = client.get("/openapi.json").json()
    op = spec["paths"]["/api/v1/artifacts/{engine}/{artifact_id}"]["get"]
    view = next(p for p in op["parameters"] if p["name"] == "view")
    assert view["in"] == "query" and view["schema"]["enum"] == ["full", "summary"]
    assert view["schema"]["default"] == "full"
    assert "summary_view_unsupported" in op["description"]
    ok = "200"
    paths = spec["paths"]
    for path, ref in (
        ("/api/v1/networks/{network_id}", "#/components/schemas/NetworkDetail"),
        ("/api/v1/networks/{network_id}/assets", "#/components/schemas/AssetPage"),
    ):
        schema = paths[path]["get"]["responses"][ok]["content"]["application/json"]["schema"]
        assert schema == {"$ref": ref}
    geo = paths["/api/v1/networks/{network_id}/geojson"]["get"]["responses"][ok]
    assert geo["content"]["application/json"]["schema"]["type"] == "object"
