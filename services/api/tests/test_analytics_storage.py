from __future__ import annotations

import hashlib

import pytest

from conftest import NETWORK_ID
from gridstorm_api.storage import ArtifactIntegrityError, LocalArtifactStore, S3ArtifactStore


def _write_real_network(path) -> None:
    import pypsa

    n = pypsa.Network()
    n.set_snapshots(range(4))
    n.add("Carrier", ["gas", "wind"])
    n.add("Bus", ["b0", "b1"], x=[0.0, 1.0], y=[0.0, 0.0], v_nom=380.0)
    n.add("Line", "l0", bus0="b0", bus1="b1", s_nom=200.0, x=10.0, r=1.0)
    n.add("Generator", "g-gas", bus="b0", carrier="gas", p_nom=80.0, marginal_cost=50.0)
    n.add("Generator", "g-wind", bus="b1", carrier="wind", p_nom=60.0, p_max_pu=0.5)
    n.add("Load", "ld", bus="b1", p_set=90.0)
    n.export_to_netcdf(str(path))


def test_analytics_endpoint_runs_gridstorm_analytics(client, workspace):
    _write_real_network(workspace / "data" / "networks" / NETWORK_ID / "network.nc")
    r = client.get(f"/api/v1/networks/{NETWORK_ID}/analytics/capacity")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["network_id"] == NETWORK_ID and body["provenance"] == "calculated"
    r = client.get(f"/api/v1/networks/{NETWORK_ID}/analytics/capacity?carriers=gas")
    assert r.status_code == 200
    r = client.get(f"/api/v1/networks/{NETWORK_ID}/analytics/capacity?carriers=unobtainium")
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_analytics_filter"
    r = client.get(f"/api/v1/networks/{NETWORK_ID}/analytics/nonsense")
    assert r.status_code == 404 and r.json()["error"]["code"] == "analytics_kind_not_found"
    assert "capacity" in r.json()["error"]["details"]["available"]
    assert client.get("/api/v1/networks/nope/analytics/capacity").status_code == 404


def test_analytics_without_network_file(client, workspace):
    (workspace / "data" / "networks" / NETWORK_ID / "network.nc").unlink()
    r = client.get(f"/api/v1/networks/{NETWORK_ID}/analytics/capacity")
    assert r.status_code == 503 and r.json()["error"]["code"] == "network_file_missing"


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
