from __future__ import annotations

import hashlib
import json
import subprocess
import sys

import pytest

from conftest import NETWORK_ID
from gridstorm_api.config import REPO_ROOT
from gridstorm_api.storage import ArtifactIntegrityError, LocalArtifactStore, S3ArtifactStore

PRECOMPUTE = REPO_ROOT / "services" / "analytics" / "scripts" / "precompute_analytics.py"


def _precompute_real_network(network_dir) -> dict:
    """Replace tiny-net's placeholder network.nc by a real one and precompute its analytics."""
    import pypsa

    n = pypsa.Network()
    n.set_snapshots(range(4))
    n.add("Carrier", ["gas", "wind"])
    n.add("Bus", ["b0", "b1"], x=[0.0, 1.0], y=[0.0, 0.0], v_nom=380.0)
    n.add("Line", "l0", bus0="b0", bus1="b1", s_nom=200.0, x=10.0, r=1.0)
    n.add("Generator", "g-gas", bus="b0", carrier="gas", p_nom=80.0, marginal_cost=50.0)
    n.add("Generator", "g-wind", bus="b1", carrier="wind", p_nom=60.0, p_max_pu=0.5)
    n.add("Load", "ld", bus="b1", p_set=90.0)
    nc = network_dir / "network.nc"
    n.export_to_netcdf(str(nc))
    manifest_path = network_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for f in manifest["files"]:
        if f["path"] == "network.nc":
            f["sha256"] = hashlib.sha256(nc.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    subprocess.run(
        [sys.executable, str(PRECOMPUTE), "--data-dir", str(network_dir.parent.parent)],
        check=True,
        capture_output=True,
    )
    return json.loads((network_dir / "analytics" / "index.json").read_text(encoding="utf-8"))


def test_analytics_serves_precomputed_files(client_factory, workspace):
    index = _precompute_real_network(workspace / "data" / "networks" / NETWORK_ID)
    client = client_factory()
    base = f"/api/v1/networks/{NETWORK_ID}/analytics"
    r = client.get(f"{base}/capacity")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["network_id"] == NETWORK_ID and body["provenance"] == "calculated"
    assert body["execution_mode"] == "precomputed"
    assert body["precomputed"]["file_sha256"] == index["kinds"]["capacity"]["sha256"]
    assert body["precomputed"]["network_sha256"] == index["network_sha256"]
    assert body["precomputed"]["generator"]["pypsa"] == body["source"]["engine"]["version"]
    assert body["precomputed"]["filters_derived_from_unfiltered"] is False

    r = client.get(f"{base}/capacity?carriers=gas")
    assert r.status_code == 200, r.text
    gen = next(g for g in r.json()["groups"] if g["key"] == "generator_power")
    assert [row["carrier"] for row in gen["rows"]] == ["gas"]
    assert gen["total_installed_mw"] == 80.0 and r.json()["filters"]["carriers"] == ["gas"]
    assert r.json()["generation_capacity_by_carrier_mw"] == {"gas": 80.0}
    assert r.json()["precomputed"]["filters_derived_from_unfiltered"] is True
    r = client.get(f"{base}/costs?carriers=wind&carriers=wind")
    assert r.status_code == 200 and r.json()["filters"]["carriers"] == ["wind"]
    r = client.get(f"{base}/energy_balance?carriers=gas")  # unsolved: unavailable, filters echoed
    assert r.status_code == 200 and r.json()["available"] is False
    assert r.json()["filters"] == {"carriers": ["gas"], "countries": None}

    for query, code in (
        ("capacity?carriers=unobtainium", "invalid_analytics_filter"),
        ("capacity?countries=DE", "invalid_analytics_filter"),  # no bus country data
        ("summary?carriers=gas", "invalid_analytics_filter"),
    ):
        r = client.get(f"{base}/{query}")
        assert r.status_code == 422 and r.json()["error"]["code"] == code, (query, r.text)
    r = client.get(f"{base}/nonsense")
    assert r.status_code == 404 and r.json()["error"]["code"] == "analytics_kind_not_found"
    assert set(r.json()["error"]["details"]["available"]) == set(index["kinds"])
    assert client.get("/api/v1/networks/nope/analytics/capacity").status_code == 404


def test_analytics_not_precomputed_stale_or_tampered(client_factory, workspace):
    network_dir = workspace / "data" / "networks" / NETWORK_ID
    client = client_factory()
    r = client.get(f"/api/v1/networks/{NETWORK_ID}/analytics/capacity")
    assert r.status_code == 503 and r.json()["error"]["code"] == "analytics_not_precomputed"

    _precompute_real_network(network_dir)
    (network_dir / "analytics" / "costs.json").write_text("{}", encoding="utf-8")
    client = client_factory()
    r = client.get(f"/api/v1/networks/{NETWORK_ID}/analytics/costs")
    assert r.status_code == 500 and r.json()["error"]["code"] == "analytics_integrity_error"

    manifest_path = network_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for f in manifest["files"]:
        if f["path"] == "network.nc":
            f["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    client = client_factory()
    r = client.get(f"/api/v1/networks/{NETWORK_ID}/analytics/capacity")
    assert r.status_code == 503 and r.json()["error"]["code"] == "analytics_stale"


def test_local_store_is_content_addressed(tmp_path):
    store = LocalArtifactStore(tmp_path / "store")
    data = b'{"a":1}'
    blob = store.put(data)
    digest = hashlib.sha256(data).hexdigest()
    assert blob.key == f"sha256/{digest}.json" and blob.sha256 == digest and blob.bytes == 7
    assert store.put(data) == blob  # idempotent
    assert store.get(blob.key, expected_sha256=digest) == data
    (tmp_path / "store" / blob.key).write_bytes(b"tampered")
    with pytest.raises(ArtifactIntegrityError):
        store.get(blob.key, expected_sha256=digest)
    with pytest.raises(ValueError):
        store.get("../escape.json")
    assert store.check_writable().startswith("local:")


class _FakeS3:
    """In-memory stand-in for the boto3 S3 client surface the store uses."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.puts = 0

    def head_object(self, Bucket, Key):  # noqa: N803
        from botocore.exceptions import ClientError

        if (Bucket, Key) not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {}

    def put_object(self, Bucket, Key, Body, ContentType=None):  # noqa: N803
        self.puts += 1
        self.objects[(Bucket, Key)] = Body

    def get_object(self, Bucket, Key):  # noqa: N803
        import io

        from botocore.exceptions import ClientError

        if (Bucket, Key) not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def delete_object(self, Bucket, Key):  # noqa: N803
        self.objects.pop((Bucket, Key), None)


def test_s3_store_with_prefix():
    fake = _FakeS3()
    store = S3ArtifactStore("bucket", prefix="/gridstorm/", client=fake)
    blob = store.put(b"hello", ext="txt", content_type="text/plain")
    assert ("bucket", f"gridstorm/sha256/{blob.sha256}.txt") in fake.objects
    store.put(b"hello", ext="txt")
    assert fake.puts == 1  # immutable: existing keys are never rewritten
    assert store.get(blob.key, expected_sha256=blob.sha256) == b"hello"
    with pytest.raises(ArtifactIntegrityError):
        store.get("sha256/missing.json")
    assert store.check_writable() == "s3:bucket"
