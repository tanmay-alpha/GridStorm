from __future__ import annotations

import hashlib
import json
import uuid
from datetime import timedelta

from conftest import NETWORK_ID, auth, run_job, scenario, wait_job
from fastapi.testclient import TestClient

from gridstorm_api.db.models import SimulationJob, utcnow
from gridstorm_api.main import create_app

ALICE = uuid.UUID("11111111-1111-4111-8111-111111111111")
BOB = uuid.UUID("22222222-2222-4222-8222-222222222222")
RUN_STAGES = ["queued", "loading_network", "applying_scenario", "building_model", "solving",
              "postprocessing", "done"]


def test_successful_job_lifecycle_and_artifact_integrity(client):
    job = run_job(client, scenario("happy", demand=1.2))
    assert job["status"] == "completed", job
    assert job["outcome"] == "feasible" and job["stage"] == "done"
    assert [e["stage"] for e in job["stage_history"]] == RUN_STAGES
    assert job["execution_mode"] == "live" and job["reused"] is False
    assert job["attempts"] == 1 and job["error"] is None
    assert job["solver"]["termination_condition"] == "optimal"
    assert job["started_at"] and job["finished_at"] and job["network_id"] == NETWORK_ID

    r = client.get(f"/api/v1/simulations/{job['id']}/result")
    assert r.status_code == 200
    assert hashlib.sha256(r.content).hexdigest() == job["result_sha256"]
    assert r.headers["x-gridstorm-result-sha256"] == job["result_sha256"]
    result = r.json()
    assert result["schema_version"] == "gridstorm-result/1.0"

    m = client.get(f"/api/v1/simulations/{job['id']}/metrics").json()
    assert m["metrics"]["total_load_mwh"] == result["metrics"]["total_load_mwh"]
    assert m["provenance"] == "modeled" and m["solver"]["name"] == "highs"

    arts = client.get(f"/api/v1/simulations/{job['id']}/artifacts").json()["items"]
    by_kind = {a["kind"]: a for a in arts}
    assert set(by_kind) == {"result", "scenario", "log"}
    assert by_kind["result"]["sha256"] == job["result_sha256"]
    assert by_kind["result"]["storage_key"] == f"sha256/{job['result_sha256']}.json"
    assert by_kind["result"]["bytes"] == len(r.content)

    page = client.get("/api/v1/simulations?status=completed").json()
    assert page["total"] == 1 and page["items"][0]["id"] == job["id"]


def test_tampered_artifact_is_detected(client, workspace):
    job = run_job(client, scenario("tamper"))
    blob = workspace / "state" / "artifacts" / "sha256" / f"{job['result_sha256']}.json"
    blob.write_bytes(blob.read_bytes() + b" ")
    r = client.get(f"/api/v1/simulations/{job['id']}/result")
    assert r.status_code == 500 and r.json()["error"]["code"] == "artifact_integrity_error"


def test_identical_scenario_reuses_result(client):
    first = run_job(client, scenario("reuse-me", demand=1.1))
    r = client.post("/api/v1/simulations", json={"scenario": scenario("reuse-me", demand=1.1)})
    assert r.status_code == 202
    second = r.json()
    assert second["status"] == "completed" and second["reused"] is True
    assert second["reused_from_job_id"] == first["id"]
    assert second["result_sha256"] == first["result_sha256"]
    assert client.get(f"/api/v1/simulations/{second['id']}/metrics").status_code == 200
    # name/description are not part of the hash; reuse still applies
    renamed = scenario("reuse-me", demand=1.1, name="Other name")
    assert client.post("/api/v1/simulations", json={"scenario": renamed}).json()["reused"] is True
    # opting out forces a fresh run
    fresh = run_job(client, scenario("reuse-me", demand=1.1), reuse=False)
    assert fresh["reused"] is False and fresh["status"] == "completed"


def test_run_by_scenario_id(client):
    r = client.post("/api/v1/simulations", json={"scenario_id": "preset-stress"})
    assert r.status_code == 202
    job = wait_job(client, r.json()["id"])
    assert job["status"] == "completed" and job["scenario_record_id"] == "preset-stress"
    assert client.post("/api/v1/simulations", json={"scenario_id": "nope"}).status_code == 404


def test_engine_failure(client):
    job = run_job(client, scenario("fails", assumptions=["fake:fail"]))
    assert job["status"] == "failed" and job["outcome"] is None
    assert job["error"]["code"] == "engine_failed"
    assert "synthetic engine failure" in job["error"]["message"]
    r = client.get(f"/api/v1/simulations/{job['id']}/result")
    assert r.status_code == 409 and r.json()["error"]["code"] == "result_not_available"
    assert client.get(f"/api/v1/simulations/{job['id']}/metrics").status_code == 409
    kinds = {a["kind"] for a in client.get(f"/api/v1/simulations/{job['id']}/artifacts").json()["items"]}
    assert kinds == {"scenario", "log"}


def test_invalid_engine_output_and_hash_mismatch(client):
    garbage = run_job(client, scenario("garbage", assumptions=["fake:garbage"]))
    assert garbage["status"] == "failed" and garbage["error"]["code"] == "invalid_result"
    wrong = run_job(client, scenario("wrong-hash", assumptions=["fake:wrong-hash"]))
    assert wrong["status"] == "failed" and wrong["error"]["code"] == "result_mismatch"


def test_infeasible_is_completed_with_scientific_outcome(client):
    job = run_job(client, scenario("infeasible", assumptions=["fake:infeasible"]))
    assert job["status"] == "completed" and job["outcome"] == "infeasible"
    assert job["error"] is None


def test_timeout(client_factory):
    client = client_factory(job_timeout_s=1.5)
    job = run_job(client, scenario("slow", assumptions=["fake:sleep=30"]))
    assert job["status"] == "timeout" and job["error"]["code"] == "timeout"
    assert job["stage"] == "solving"


def test_memory_watchdog_kills_engine(client_factory):
    client = client_factory(job_memory_mb=120)
    job = run_job(client, scenario("hog", assumptions=["fake:memory"]))
    assert job["status"] == "failed", job
    assert job["error"]["code"] == "memory_limit"
    assert "120 MB" in job["error"]["message"]


def test_cancel_running_and_queued(client):
    r = client.post("/api/v1/simulations",
                    json={"scenario": scenario("long", assumptions=["fake:sleep=30"])})
    running_id = r.json()["id"]
    wait_job(client, running_id, until=lambda j: j["stage"] == "solving")
    r = client.post("/api/v1/simulations",
                    json={"scenario": scenario("waiting", assumptions=["fake:sleep=30"])})
    queued = r.json()
    assert queued["status"] == "queued"  # one worker, busy

    c = client.post(f"/api/v1/simulations/{queued['id']}/cancel")
    assert c.status_code == 200 and c.json()["status"] == "cancelled"
    assert c.json()["error"]["code"] == "cancelled"

    c = client.post(f"/api/v1/simulations/{running_id}/cancel")
    assert c.status_code == 200 and c.json()["cancel_requested"] is True
    job = wait_job(client, running_id, timeout=15)
    assert job["status"] == "cancelled"
    r = client.post(f"/api/v1/simulations/{running_id}/cancel")
    assert r.status_code == 409 and r.json()["error"]["code"] == "job_not_cancellable"
    assert client.post(f"/api/v1/simulations/{uuid.uuid4()}/cancel").status_code == 404
    assert client.get("/api/v1/simulations/not-a-uuid").status_code == 404


def test_private_jobs_are_isolated(client):
    r = client.post("/api/v1/simulations", json={"scenario": scenario("alice-run")},
                    headers=auth(ALICE))
    job = r.json()
    assert job["visibility"] == "private" and job["owner_id"] == str(ALICE)
    wait_job(client, job["id"], headers=auth(ALICE))
    assert client.get(f"/api/v1/simulations/{job['id']}", headers=auth(BOB)).status_code == 404
    assert client.get(f"/api/v1/simulations/{job['id']}").status_code == 404
    assert client.get(f"/api/v1/simulations/{job['id']}/result").status_code == 404
    assert client.get(f"/api/v1/reports/{job['id']}").status_code == 404
    mine = client.get("/api/v1/simulations?mine=true", headers=auth(ALICE)).json()
    assert [j["id"] for j in mine["items"]] == [job["id"]]
    assert client.get("/api/v1/simulations", headers=auth(BOB)).json()["total"] == 0


def test_cancel_requires_owner(client):
    r = client.post("/api/v1/simulations",
                    json={"scenario": scenario("alice-pub", assumptions=["fake:sleep=30"]),
                          "visibility": "public"},
                    headers=auth(ALICE))
    job = r.json()
    assert job["visibility"] == "public"
    r = client.post(f"/api/v1/simulations/{job['id']}/cancel", headers=auth(BOB))
    assert r.status_code == 403 and r.json()["error"]["code"] == "not_owner"
    assert client.post(f"/api/v1/simulations/{job['id']}/cancel").status_code == 403
    assert client.post(f"/api/v1/simulations/{job['id']}/cancel",
                       headers=auth(ALICE)).status_code == 200
    assert wait_job(client, job["id"])["status"] == "cancelled"


def test_restart_recovery(settings_factory):
    settings = settings_factory(run_workers=False, job_max_attempts=2)
    with TestClient(create_app(settings)) as c:
        ids = []
        for sid in ("retry-me", "give-up"):
            r = c.post("/api/v1/scenarios/validate", json=scenario(sid))
            assert r.json()["valid"]
        ctx = c.app.state.ctx
        with ctx.db.session() as s:
            for sid, attempts in (("retry-me", 1), ("give-up", 2)):
                spec = scenario(sid)
                import stormspec

                sc = stormspec.Scenario.model_validate(spec)
                job = SimulationJob(
                    id=uuid.uuid4(), scenario_id=sid, scenario_hash=stormspec.scenario_hash(sc),
                    spec=sc.model_dump(mode="json"), network_id=NETWORK_ID,
                    execution_mode="live", status="running", stage="solving",
                    stage_history=[{"stage": "queued", "at": "2026-01-01T00:00:00Z"}],
                    attempts=attempts, worker_id="dead-host:1:abc",
                    heartbeat_at=utcnow() - timedelta(minutes=10), started_at=utcnow(),
                    visibility="public",
                )
                s.add(job)
                ids.append(str(job.id))
            s.commit()

    with TestClient(create_app(settings_factory(job_max_attempts=2))) as c:
        retried = wait_job(c, ids[0])
        assert retried["status"] == "completed" and retried["attempts"] == 2
        assert any(e.get("reason") == "worker_restart" for e in retried["stage_history"])
        failed = c.get(f"/api/v1/simulations/{ids[1]}").json()
        assert failed["status"] == "failed" and failed["error"]["code"] == "worker_restart"


def test_precomputed_mode(client_factory):
    client = client_factory(execution_mode="precomputed")
    r = client.post("/api/v1/simulations", json={"scenario_id": "preset-base"})
    assert r.status_code == 202, r.text
    job = r.json()
    assert job["status"] == "completed" and job["execution_mode"] == "precomputed"
    assert any(e.get("precomputed_artifact") == "pypsa/preset-base-result"
               for e in job["stage_history"])
    result = client.get(f"/api/v1/simulations/{job['id']}/result").json()
    assert result["metrics"]["total_load_mwh"] == 400.0
    r = client.post("/api/v1/simulations", json={"scenario": scenario("not-precomputed")})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "precomputed_result_unavailable"


def test_workers_disabled_returns_503(client_factory):
    client = client_factory(run_workers=False)
    r = client.post("/api/v1/simulations", json={"scenario": scenario("no-workers")})
    assert r.status_code == 503 and r.json()["error"]["code"] == "workers_unavailable"


def test_simulation_rate_limit(client_factory):
    client = client_factory(rate_limit_sim_per_min=1.0, rate_limit_sim_burst=1)
    assert client.post("/api/v1/simulations", json={"scenario": scenario("rl-1")}).status_code == 202
    r = client.post("/api/v1/simulations", json={"scenario": scenario("rl-2")})
    assert r.status_code == 429


def test_result_is_valid_json_document(client):
    job = run_job(client, scenario("doc"))
    body = client.get(f"/api/v1/simulations/{job['id']}/result").content
    assert json.loads(body)["scenario_hash"] == job["scenario_hash"]
