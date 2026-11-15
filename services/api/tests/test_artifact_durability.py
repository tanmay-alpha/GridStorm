from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from types import SimpleNamespace
from urllib.parse import unquote

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from conftest import NETWORK_ID, run_job, scenario, wait_job
from gridstorm_api import context, readiness, storage
from gridstorm_api.db.models import SimulationArtifact, SimulationJob
from gridstorm_api.main import create_app
from gridstorm_api.storage import (
    ArtifactIntegrityError,
    ArtifactStoreUnavailable,
    ArtifactUnavailable,
    SupabaseArtifactStore,
    content_key,
)

BUCKET = "gridstorm-artifacts"
PREFIX = "test/storage/unit"


class SupabaseServer:
    """In-memory Storage REST server, including real missing/duplicate error envelopes."""

    def __init__(self):
        self.blobs: dict[str, bytes] = {}
        self.requests: list[httpx.Request] = []
        self.failures: deque[int] = deque()
        self.duplicate_next: bytes | None = None
        self.deny_writes = False
        self.fail_result_uploads = False
        self._lock = threading.Lock()

    def key(self, key: str) -> str:
        return f"{PREFIX}/{key}"

    @staticmethod
    def missing() -> httpx.Response:
        # Supabase can return HTTP 400 with a logical 404 in its JSON body.
        return httpx.Response(400, json={"statusCode": "404", "code": "NoSuchKey"})

    def __call__(self, request: httpx.Request) -> httpx.Response:
        with self._lock:
            self.requests.append(request)
            assert request.headers["authorization"] == "Bearer test-service-role"
            assert request.headers["apikey"] == "test-service-role"
            if self.failures:
                return httpx.Response(self.failures.popleft(), json={"error": "unavailable"})
            path = unquote(request.url.path)
            root = "/storage/v1/object/"
            assert path.startswith(root), path
            path = path.removeprefix(root)
            info = path.startswith("info/")
            if info:
                path = path.removeprefix("info/")
            bucket, key = path.split("/", 1)
            assert bucket == BUCKET
            if request.method == "POST":
                assert not info
                assert request.headers["x-upsert"] == "false"
                assert "content-type" in request.headers
                if self.deny_writes:
                    return httpx.Response(403, json={"code": "AccessDenied"})
                if self.fail_result_uploads:
                    try:
                        is_result = json.loads(request.content).get("schema_version") == (
                            "gridstorm-result/1.0"
                        )
                    except (ValueError, AttributeError):
                        is_result = False
                    if is_result:
                        return httpx.Response(503, json={"error": "unavailable"})
                if self.duplicate_next is not None:
                    self.blobs[key] = self.duplicate_next
                    self.duplicate_next = None
                if key in self.blobs:
                    return httpx.Response(400, json={"statusCode": "409", "code": "Duplicate"})
                self.blobs[key] = request.content
                return httpx.Response(200, json={"Key": f"{bucket}/{key}"})
            if request.method == "GET" or request.method == "HEAD":
                if key not in self.blobs:
                    return self.missing()
                data = self.blobs[key]
                if info:
                    return httpx.Response(200, json={"name": key, "metadata": {"size": len(data)}})
                return httpx.Response(
                    200,
                    content=b"" if request.method == "HEAD" else data,
                    headers={"Content-Length": str(len(data))},
                )
            if request.method == "DELETE":
                if key not in self.blobs:
                    return self.missing()
                del self.blobs[key]
                return httpx.Response(200, json={})
            raise AssertionError(f"Unexpected Storage method: {request.method}")


@pytest.fixture
def supabase_server():
    return SupabaseServer()


@pytest.fixture
def supabase_store_factory(monkeypatch, supabase_server):
    stores = []

    def make(_settings=None, **overrides):
        options = {
            "prefix": PREFIX,
            "transport": httpx.MockTransport(supabase_server),
            "backoff_s": 0,
            "max_attempts": 3,
        }
        options.update(overrides)
        store = SupabaseArtifactStore(
            "https://storage.example.test", "test-service-role", BUCKET, **options
        )
        stores.append(store)
        return store

    # Exercise the actual app/context/worker wiring, replacing only the HTTP transport.
    monkeypatch.setattr(context, "make_store", make)
    yield make
    for store in stores:
        store.close()


def _result_key(job):
    return content_key(job["result_sha256"], "json")


def _assert_gone(client, job):
    paths = [
        f"/api/v1/simulations/{job['id']}/result",
        f"/api/v1/reports/{job['id']}",
        f"/api/v1/simulations/{job['id']}/artifacts",
    ]
    for path in paths:
        response = client.get(path)
        assert response.status_code == 410, response.text
        error = response.json()["error"]
        assert error["code"] == "artifact_unavailable"
        assert error["details"]["job_id"] == job["id"]
        assert error["details"]["result_sha256"] == job["result_sha256"]
        assert error["details"]["recoverable"] is True
        assert error["details"]["recompute_path"] == (f"/api/v1/simulations/{job['id']}/recompute")
    current = client.get(f"/api/v1/simulations/{job['id']}").json()
    assert current["status"] == "completed"
    assert current["result_available"] is False
    assert current["result_sha256"] == job["result_sha256"]
    listed = client.get("/api/v1/simulations?status=completed").json()["items"]
    assert next(row for row in listed if row["id"] == job["id"])["result_available"] is False
    assert client.get(f"/api/v1/simulations/{job['id']}/metrics").status_code == 200


def test_supabase_put_get_checksums_and_idempotent_immutable_duplicate(
    supabase_store_factory, supabase_server
):
    store = supabase_store_factory()
    payload = b'{"durable":true}'
    blob = store.put(payload)
    assert blob.backend == "supabase" and store.durable is True
    assert blob.sha256 == hashlib.sha256(payload).hexdigest()
    assert blob.key == content_key(blob.sha256, "json")
    assert blob.bytes == len(payload) and blob.content_type == "application/json"
    assert supabase_server.blobs == {supabase_server.key(blob.key): payload}
    assert store.get(blob.key, expected_sha256=blob.sha256) == payload
    uploads = sum(r.method == "POST" for r in supabase_server.requests)
    assert store.put(payload) == blob
    assert sum(r.method == "POST" for r in supabase_server.requests) == uploads == 1
    supabase_server.blobs[supabase_server.key(blob.key)] = b"tampered"
    with pytest.raises(ArtifactIntegrityError):
        store.get(blob.key, expected_sha256=blob.sha256)
    with pytest.raises(ArtifactIntegrityError):
        store.put(payload)
    assert supabase_server.blobs[supabase_server.key(blob.key)] == b"tampered"
    assert sum(r.method == "POST" for r in supabase_server.requests) == uploads
    assert all(r.method != "PUT" for r in supabase_server.requests)


@pytest.mark.parametrize("corrupt", [False, True])
def test_supabase_duplicate_upload_race_verifies_existing_without_overwriting(
    supabase_store_factory, supabase_server, corrupt
):
    store = supabase_store_factory()
    payload = b"concurrent identical upload"
    key = content_key(hashlib.sha256(payload).hexdigest(), "json")
    existing = b"corrupt concurrent upload" if corrupt else payload
    supabase_server.duplicate_next = existing
    if corrupt:
        with pytest.raises(ArtifactIntegrityError):
            store.put(payload)
    else:
        assert store.put(payload).key == key
    assert supabase_server.blobs[supabase_server.key(key)] == existing
    assert [r.method for r in supabase_server.requests].count("POST") == 1
    assert all(r.method != "PUT" for r in supabase_server.requests)


def test_supabase_missing_info_head_delete_and_readiness_round_trip(
    supabase_store_factory, supabase_server
):
    store = supabase_store_factory()
    assert store.exists("missing.json", fresh=True) is False
    with pytest.raises(ArtifactUnavailable):
        store.get("missing.json")
    blob = store.put(b"head and delete")
    head = store._client.head(f"{store._base}/{BUCKET}/{PREFIX}/{blob.key}")
    assert head.status_code == 200 and head.content == b""
    assert int(head.headers["content-length"]) == blob.bytes
    store.delete(blob.key)
    store.delete(blob.key)  # Deletion is idempotent, including Supabase's logical 404 body.
    assert store.exists(blob.key, fresh=True) is False
    assert supabase_server.blobs == {}
    before = len(supabase_server.requests)
    assert store.check_writable().startswith(f"supabase:{BUCKET}")
    assert [r.method for r in supabase_server.requests[before:]] == ["POST", "GET", "DELETE"]
    assert supabase_server.blobs == {}


@pytest.mark.parametrize("status", [500, 502, 503, 504])
@pytest.mark.parametrize("exhausted", [False, True])
def test_supabase_transient_5xx_retries_are_bounded(
    monkeypatch, supabase_store_factory, supabase_server, status, exhausted
):
    sleeps = []
    monkeypatch.setattr(
        storage, "time", SimpleNamespace(monotonic=time.monotonic, sleep=sleeps.append)
    )
    store = supabase_store_factory(max_attempts=3, backoff_s=0.25)
    payload = b"retry-safe download"
    digest = hashlib.sha256(payload).hexdigest()
    key = content_key(digest, "json")
    supabase_server.blobs[supabase_server.key(key)] = payload
    supabase_server.failures.extend([status] * (5 if exhausted else 2))
    if exhausted:
        with pytest.raises(ArtifactStoreUnavailable) as caught:
            store.get(key, expected_sha256=digest)
        assert "3 attempts" in caught.value.message
        assert len(supabase_server.failures) == 2
    else:
        assert store.get(key, expected_sha256=digest) == payload
    assert len(supabase_server.requests) == 3
    assert sleeps == [0.25, 0.5]


def test_readiness_distinguishes_local_writability_from_durability(client_factory):
    client = client_factory(execution_mode="precomputed", run_workers=False)
    check = client.get("/ready").json()["checks"]["storage"]
    assert check["status"] == "ok"
    assert check["backend"] == "local" and check["durable"] is False


def test_supabase_readiness_round_trip_is_ttl_cached_including_failures(
    monkeypatch, client_factory, supabase_store_factory, supabase_server
):
    now = [1000.0]
    monkeypatch.setattr(readiness, "time", SimpleNamespace(monotonic=lambda: now[0]))
    client = client_factory(
        artifact_store="supabase",
        execution_mode="precomputed",
        run_workers=False,
        storage_check_ttl_s=30.0,
    )

    def check():
        return client.get("/ready").json()["checks"]["storage"]

    first = check()
    assert first["status"] == "ok"
    assert first["backend"] == "supabase" and first["durable"] is True
    assert supabase_server.blobs == {}
    count = len(supabase_server.requests)
    assert count == 3
    now[0] += 29
    assert check() == first
    assert len(supabase_server.requests) == count
    now[0] += 2
    assert check()["durable"] is True
    assert len(supabase_server.requests) == count + 3
    supabase_server.deny_writes = True
    now[0] += 31
    failed = check()
    assert failed["status"] == "error"
    assert failed["backend"] == "supabase" and failed["durable"] is False
    count = len(supabase_server.requests)
    assert check() == failed
    assert len(supabase_server.requests) == count
    supabase_server.deny_writes = False
    now[0] += 31
    assert check()["durable"] is True
    assert len(supabase_server.requests) == count + 3
    assert supabase_server.blobs == {}


def test_completed_supabase_result_survives_new_app_and_local_artifact_wipe(
    settings_factory, supabase_store_factory, supabase_server
):
    settings = settings_factory(artifact_store="supabase")
    with TestClient(create_app(settings)) as client:
        job = run_job(client, scenario("durable-restart"))
        assert job["status"] == "completed" and job["result_available"] is True
        original = client.get(f"/api/v1/simulations/{job['id']}/result")
        assert original.status_code == 200
        original_ctx = client.app.state.ctx
        assert supabase_server.blobs[supabase_server.key(_result_key(job))] == original.content
    settings.resolved_artifact_dir.mkdir(parents=True, exist_ok=True)
    (settings.resolved_artifact_dir / "ephemeral-sentinel").write_bytes(b"lost on restart")
    shutil.rmtree(settings.resolved_artifact_dir)
    with TestClient(create_app(settings)) as restarted:
        assert restarted.app.state.ctx is not original_ctx
        assert restarted.app.state.ctx.store is not original_ctx.store
        response = restarted.get(f"/api/v1/simulations/{job['id']}/result")
        assert response.status_code == 200 and response.content == original.content
        assert hashlib.sha256(response.content).hexdigest() == job["result_sha256"]
        assert response.headers["x-gridstorm-result-sha256"] == job["result_sha256"]
        assert restarted.get(f"/api/v1/simulations/{job['id']}").json()["result_available"]
        assert restarted.get(f"/api/v1/reports/{job['id']}").status_code == 200
        assert restarted.get(f"/api/v1/simulations/{job['id']}/artifacts").status_code == 200


def test_missing_completed_result_is_gone_everywhere_with_metadata_retained(
    client_factory, supabase_store_factory
):
    client = client_factory(artifact_store="supabase")
    job = run_job(client, scenario("lost-result"))
    assert job["status"] == "completed"
    client.app.state.ctx.store.delete(_result_key(job))
    _assert_gone(client, job)


@pytest.mark.parametrize("resource", ["result", "report", "artifacts"])
def test_tampered_completed_result_is_integrity_error_not_gone(
    client_factory, supabase_store_factory, supabase_server, resource
):
    client = client_factory(artifact_store="supabase")
    job = run_job(client, scenario(f"tampered-{resource}"))
    assert job["status"] == "completed"
    supabase_server.blobs[supabase_server.key(_result_key(job))] += b" "
    path = (
        f"/api/v1/reports/{job['id']}"
        if resource == "report"
        else f"/api/v1/simulations/{job['id']}/{resource}"
    )
    response = client.get(path)
    assert response.status_code == 500, response.text
    assert response.json()["error"]["code"] == "artifact_integrity_error"


def test_reuse_requires_present_verified_result(client_factory, supabase_store_factory):
    client = client_factory(artifact_store="supabase")
    spec = scenario("durable-reuse", demand=1.1)
    first = run_job(client, spec)
    assert first["status"] == "completed"
    second = run_job(client, spec)
    assert second["status"] == "completed" and second["reused"] is True
    assert second["reused_from_job_id"] == first["id"]
    assert second["result_sha256"] == first["result_sha256"]
    client.app.state.ctx.store.delete(_result_key(first))
    third = run_job(client, spec)
    assert third["status"] == "completed" and third["reused"] is False
    assert third["reused_from_job_id"] is None
    assert third["attempts"] == 1 and third["result_available"] is True
    response = client.get(f"/api/v1/simulations/{third['id']}/result")
    assert response.status_code == 200
    assert hashlib.sha256(response.content).hexdigest() == third["result_sha256"]


def test_legacy_completed_job_without_artifact_record_is_gone(
    client_factory, supabase_store_factory
):
    client = client_factory(artifact_store="supabase")
    job = run_job(client, scenario("legacy-lost-record"))
    assert job["status"] == "completed"
    ctx = client.app.state.ctx
    with ctx.db.session() as session:
        session.execute(
            delete(SimulationArtifact).where(
                SimulationArtifact.job_id == uuid.UUID(job["id"]),
                SimulationArtifact.kind == "result",
            )
        )
        session.commit()
    _assert_gone(client, job)


def test_worker_result_upload_failure_cannot_publish_completed_job(
    client_factory, supabase_store_factory, supabase_server
):
    client = client_factory(artifact_store="supabase")
    supabase_server.fail_result_uploads = True
    job = run_job(client, scenario("result-persistence-fails"))
    assert job["status"] == "failed", job
    assert job["error"]["code"] == "artifact_persist_failed"
    assert job["result_sha256"] is None and job["result_available"] is False
    assert job["outcome"] is None and job["finished_at"] is not None
    assert client.get(f"/api/v1/simulations/{job['id']}/result").status_code == 409
    with client.app.state.ctx.db.session() as session:
        persisted = session.get(SimulationJob, uuid.UUID(job["id"]))
        assert persisted.status == "failed" and persisted.result_sha256 is None
        result_artifact = session.scalar(
            select(SimulationArtifact).where(
                SimulationArtifact.job_id == persisted.id,
                SimulationArtifact.kind == "result",
            )
        )
        assert result_artifact is None
    artifacts = client.get(f"/api/v1/simulations/{job['id']}/artifacts").json()["items"]
    assert {row["kind"] for row in artifacts} == {"scenario", "log"}


def test_recompute_creates_new_job_with_provenance_and_verified_checksums(
    client_factory, supabase_store_factory
):
    client = client_factory(artifact_store="supabase")
    original = run_job(client, scenario("recompute-lost", demand=1.2))
    assert original["status"] == "completed"
    original_bytes = client.get(f"/api/v1/simulations/{original['id']}/result").content
    path = f"/api/v1/simulations/{original['id']}/recompute"
    present = client.post(path)
    assert present.status_code == 409
    assert present.json()["error"]["code"] == "result_still_available"
    client.app.state.ctx.store.delete(_result_key(original))
    response = client.post(path)
    assert response.status_code == 202, response.text
    created = response.json()
    assert created["id"] != original["id"]
    assert created["recomputed_from_job_id"] == original["id"]
    assert created["reused"] is False and created["reused_from_job_id"] is None
    event = created["stage_history"][0]
    assert event["stage"] == "queued"
    assert event["recomputed_from"] == original["id"]
    assert event["lost_result_sha256"] == original["result_sha256"]
    completed = wait_job(client, created["id"])
    assert completed["status"] == "completed" and completed["result_available"] is True
    assert completed["scenario_hash"] == original["scenario_hash"]
    assert completed["recomputed_from_job_id"] == original["id"]
    assert completed["attempts"] == 1 and completed["reused"] is False
    result = client.get(f"/api/v1/simulations/{completed['id']}/result")
    assert result.status_code == 200
    assert hashlib.sha256(result.content).hexdigest() == completed["result_sha256"]
    assert result.headers["x-gridstorm-result-sha256"] == completed["result_sha256"]
    assert hashlib.sha256(original_bytes).hexdigest() == original["result_sha256"]
    artifacts = client.get(f"/api/v1/simulations/{completed['id']}/artifacts").json()["items"]
    result_artifact = next(row for row in artifacts if row["kind"] == "result")
    assert result_artifact["sha256"] == completed["result_sha256"]
    assert result_artifact["storage_key"] == _result_key(completed)
    assert result_artifact["bytes"] == len(result.content)
    previous = client.get(f"/api/v1/simulations/{original['id']}").json()
    assert previous["id"] == original["id"] and previous["status"] == "completed"
    assert previous["result_sha256"] == original["result_sha256"]
    assert previous["recomputed_from_job_id"] is None


@pytest.mark.parametrize("force", [False, True])
def test_recovery_cli_module_recomputes_from_sqlite_with_fake_engine(settings_factory, force):
    settings = settings_factory(artifact_store="local")
    with TestClient(create_app(settings)) as client:
        original = run_job(client, scenario("cli-recovery", demand=1.3))
        assert original["status"] == "completed"
        if not force:
            (settings.resolved_artifact_dir / _result_key(original)).unlink()
            response = client.get(f"/api/v1/simulations/{original['id']}/result")
            assert response.status_code == 410

    # The subprocess must use only this fixture's SQLite DB, catalog and fake engine,
    # never deployment credentials or storage settings inherited from the developer shell.
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("GRIDSTORM_", "SUPABASE_")) and name != "DATABASE_URL"
    }
    environment.update(
        {
            "DATABASE_URL": settings.resolved_database_url,
            "GRIDSTORM_DATA_DIR": str(settings.data_dir),
            "GRIDSTORM_STATE_DIR": str(settings.state_dir),
            "GRIDSTORM_PRESETS_DIR": str(settings.resolved_presets_dir),
            "GRIDSTORM_ARTIFACT_DIR": str(settings.resolved_artifact_dir),
            "GRIDSTORM_ARTIFACT_STORE": "local",
            "GRIDSTORM_EXECUTION_MODE": "live",
            "GRIDSTORM_LIVE_NETWORKS": NETWORK_ID,
            "GRIDSTORM_RUN_WORKERS": "false",
            "GRIDSTORM_ENGINE_CMD": settings.engine_cmd,
            "GRIDSTORM_JOB_TIMEOUT_S": "30",
        }
    )
    command = [sys.executable, "-m", "gridstorm_api.jobs.recover", original["id"]]
    if force:
        command.append("--force")
    completed = subprocess.run(
        command, env=environment, capture_output=True, text=True, timeout=60, check=False
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    recovered = json.loads(completed.stdout)
    assert recovered["status"] == "completed" and recovered["result_available"] is True
    assert recovered["id"] != original["id"]
    assert recovered["recomputed_from_job_id"] == original["id"]
    assert recovered["scenario_hash"] == original["scenario_hash"]
    assert recovered["reused"] is False and recovered["attempts"] == 1
    event = recovered["stage_history"][0]
    assert event["recomputed_from"] == original["id"]
    assert event["lost_result_sha256"] == original["result_sha256"]

    with TestClient(create_app(settings_factory(run_workers=False))) as restarted:
        response = restarted.get(f"/api/v1/simulations/{recovered['id']}/result")
        assert response.status_code == 200
        assert hashlib.sha256(response.content).hexdigest() == recovered["result_sha256"]
        assert response.headers["x-gridstorm-result-sha256"] == recovered["result_sha256"]
        previous = restarted.get(f"/api/v1/simulations/{original['id']}").json()
        assert previous["status"] == "completed"
        assert previous["result_sha256"] == original["result_sha256"]
        assert previous["recomputed_from_job_id"] is None


@pytest.mark.network
@pytest.mark.skipif(
    os.getenv("GRIDSTORM_STORAGE_NETWORK_TEST") != "1",
    reason="Set GRIDSTORM_STORAGE_NETWORK_TEST=1 to exercise real Supabase Storage",
)
def test_real_supabase_storage_durability_round_trip():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        pytest.skip("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
    bucket = os.getenv("GRIDSTORM_SUPABASE_BUCKET", BUCKET)
    prefix = f"test/storage/{uuid.uuid4().hex}"
    payload = json.dumps({"test": "artifact-durability", "nonce": uuid.uuid4().hex}).encode()
    digest = hashlib.sha256(payload).hexdigest()
    blob_key = content_key(digest, "json")
    store = SupabaseArtifactStore(url, key, bucket, prefix=prefix)
    try:
        blob = store.put(payload)
        assert blob.sha256 == digest and blob.key == blob_key
        assert blob.backend == "supabase" and store.durable is True
        assert store.put(payload) == blob
        # A new client has no positive existence cache or process-local blob state.
        restarted = SupabaseArtifactStore(url, key, bucket, prefix=prefix)
        try:
            assert restarted.exists(blob.key, fresh=True)
            assert restarted.get(blob.key, expected_sha256=digest) == payload
        finally:
            restarted.close()
    finally:
        try:
            # The address is known before put, so failed upload verification still cleans up.
            store.delete(blob_key)
        finally:
            store.close()
