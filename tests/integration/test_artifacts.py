"""Precomputed engine artifacts (contract §5) served by /api/v1/artifacts."""

from __future__ import annotations

import httpx
import pytest

from gs_helpers import assert_error, assert_page, canonical_sha256, iter_pages

HEADER_KEYS = {
    "schema_version",
    "artifact_id",
    "kind",
    "engine",
    "engine_version",
    "network_id",
    "created_at",
    "command",
    "inputs",
    "platform",
    "execution_mode",
    "payload_sha256",
}
KINDS = {"n_minus_1", "advisor", "episode", "benchmark", "simulation", "timeseries", "risk"}


@pytest.fixture(scope="module")
def index(client: httpx.Client) -> list[dict]:
    return iter_pages(client, "/api/v1/artifacts", limit=100)


def test_index_entries(index: list[dict]) -> None:
    assert index, "no precomputed artifacts exposed"
    for e in index:
        assert {"engine", "artifact_id", "kind", "network_id"} <= set(e), e
        assert e["kind"] in KINDS, e


def test_index_filters(client: httpx.Client, index: list[dict]) -> None:
    engines = {e["engine"] for e in index}
    for eng in engines:
        r = client.get("/api/v1/artifacts", params={"engine": eng, "limit": 100})
        assert r.status_code == 200
        items = assert_page(r.json())
        assert items and all(i["engine"] == eng for i in items)
    r = client.get("/api/v1/artifacts", params={"kind": "no-such-kind"})
    if r.status_code == 200:
        assert r.json()["items"] == []
    else:
        assert_error(r, {400, 422})


def test_every_artifact_header_and_hash(client: httpx.Client, index: list[dict]) -> None:
    """Every artifact's payload_sha256 must match an independent recomputation."""
    for e in index:
        r = client.get(f"/api/v1/artifacts/{e['engine']}/{e['artifact_id']}")
        assert r.status_code == 200, (e, r.text[:300])
        art = r.json()
        hdr = art["artifact"]
        missing = HEADER_KEYS - set(hdr)
        assert not missing, (e["artifact_id"], sorted(missing))
        assert hdr["schema_version"] == "gridstorm-artifact/1.0"
        assert hdr["execution_mode"] == "precomputed"
        assert hdr["artifact_id"] == e["artifact_id"]
        assert hdr["engine"] == e["engine"]
        assert canonical_sha256(art["payload"]) == hdr["payload_sha256"], e["artifact_id"]
        assert len(r.content) < 5 * 1024 * 1024, (e["artifact_id"], len(r.content))


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/artifacts/pypsa/..%2F..%2Fnetworks%2Fcatalog",
        "/api/v1/artifacts/..%2Fnetworks/catalog",
        "/api/v1/artifacts/pypsa/%2e%2e%2f%2e%2e%2fnetworks%2fac-dc-meshed%2fmanifest",
        "/api/v1/artifacts/pypsa/..%5C..%5Cnetworks%5Ccatalog",
        "/api/v1/artifacts/pypsa/C:%5CWindows%5Cwin",
        "/api/v1/artifacts/%2Fetc/passwd",
        "/api/v1/artifacts/pypsa/%00",
    ],
)
def test_artifact_path_traversal(client: httpx.Client, path: str) -> None:
    r = client.get(path)
    assert r.status_code in (400, 404, 422), (path, r.status_code, r.text[:300])
    assert "network-catalog" not in r.text and "dataset-manifest" not in r.text
    assert "root:" not in r.text


def test_unknown_artifact_404(client: httpx.Client) -> None:
    assert_error(client.get("/api/v1/artifacts/pypsa/does-not-exist"), 404)
    assert_error(client.get("/api/v1/artifacts/notanengine/x"), {404, 422})
