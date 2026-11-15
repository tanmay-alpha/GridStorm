"""Owner isolation through the HTTP API.

The API talks to Postgres with a privileged role (RLS bypassed), so these checks are the only
thing standing between users: every job/comparison sub-resource must 404 for non-owners, list
filters must not widen visibility, JWT role claims must not escalate, and result reuse must not
leak private runs.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt

from conftest import JWT_SECRET, NETWORK_ID, auth, run_job, scenario

ALICE = uuid.UUID("11111111-1111-4111-8111-111111111111")
BOB = uuid.UUID("22222222-2222-4222-8222-222222222222")


def _token(claims: dict, *, alg: str = "HS256", key: str = JWT_SECRET) -> dict[str, str]:
    now = datetime.now(UTC)
    base = {"aud": "authenticated", "iat": now, "exp": now + timedelta(hours=1)}
    return {"Authorization": f"Bearer {jwt.encode(base | claims, key, algorithm=alg)}"}


def _job_paths(job_id: str) -> list[str]:
    return [
        f"/api/v1/simulations/{job_id}",
        f"/api/v1/simulations/{job_id}/metrics",
        f"/api/v1/simulations/{job_id}/result",
        f"/api/v1/simulations/{job_id}/artifacts",
        f"/api/v1/reports/{job_id}",
        f"/api/v1/reports/{job_id}?format=md",
    ]


def test_private_job_subresources_are_hidden_from_non_owners(client):
    job = run_job(client, scenario("authz-private", demand=1.1), headers=auth(ALICE))
    assert job["status"] == "completed" and job["visibility"] == "private"
    for path in _job_paths(job["id"]):
        assert client.get(path, headers=auth(ALICE)).status_code == 200, path
        for headers in (auth(BOB), None):
            r = client.get(path, headers=headers)
            assert r.status_code == 404, (path, headers, r.status_code)
            assert r.json()["error"]["code"] in {"job_not_found", "report_not_found"}
    # Non-owners cannot even learn that the job exists via cancel (404, not 403).
    for headers in (auth(BOB), None):
        r = client.post(f"/api/v1/simulations/{job['id']}/cancel", headers=headers)
        assert r.status_code == 404 and r.json()["error"]["code"] == "job_not_found"


def test_job_list_filters_never_widen_visibility(client):
    job = run_job(client, scenario("authz-list", demand=1.2), headers=auth(ALICE))
    filters = [
        {},
        {"status": "completed"},
        {"network_id": NETWORK_ID},
        {"scenario_hash": job["scenario_hash"]},
        {"mine": "true"},
    ]
    for params in filters:
        for headers in (auth(BOB), None):
            page = client.get("/api/v1/simulations", params=params, headers=headers).json()
            assert job["id"] not in {j["id"] for j in page["items"]}, (params, headers)
            assert page["total"] == 0, (params, headers)
        own = client.get("/api/v1/simulations", params=params, headers=auth(ALICE)).json()
        assert job["id"] in {j["id"] for j in own["items"]}, params


def test_private_jobs_cannot_be_compared_by_others(client):
    private = run_job(client, scenario("authz-cmp-a", demand=1.3), headers=auth(ALICE))
    bobs = run_job(client, scenario("authz-cmp-b", demand=1.4), headers=auth(BOB))
    for body in (
        {"baseline_job_id": private["id"], "scenario_job_id": bobs["id"]},
        {"baseline_job_id": bobs["id"], "scenario_job_id": private["id"]},
    ):
        r = client.post("/api/v1/comparisons", json=body, headers=auth(BOB))
        assert r.status_code == 404 and r.json()["error"]["code"] == "job_not_found"
    alice_pub = run_job(
        client, scenario("authz-cmp-c", demand=1.5), headers=auth(ALICE), visibility="public"
    )
    r = client.post(
        "/api/v1/comparisons",
        json={"baseline_job_id": alice_pub["id"], "scenario_job_id": private["id"]},
        headers=auth(ALICE),
    )
    assert r.status_code == 201 and r.json()["visibility"] == "private"
    cid = r.json()["id"]
    for path in (
        f"/api/v1/comparisons/{cid}",
        f"/api/v1/reports/{cid}",
        f"/api/v1/reports/{cid}?format=md",
    ):
        assert client.get(path, headers=auth(ALICE)).status_code == 200, path
        assert client.get(path, headers=auth(BOB)).status_code == 404, path
        assert client.get(path).status_code == 404, path


def test_role_claims_do_not_escalate(client):
    job = run_job(client, scenario("authz-role", demand=1.6), headers=auth(ALICE))
    for role in ("service_role", "supabase_admin", "postgres"):
        r = client.get(
            f"/api/v1/simulations/{job['id']}", headers=_token({"sub": str(BOB), "role": role})
        )
        assert r.status_code == 404, role
    # A Supabase anon/service key is a JWT without `sub`: it must not authenticate as anyone.
    r = client.get("/api/v1/simulations", headers=_token({"role": "service_role"}))
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_token"
    # alg=none / algorithm confusion is refused.
    unsigned = jwt.encode(
        {"sub": str(ALICE), "aud": "authenticated", "exp": datetime.now(UTC) + timedelta(hours=1)},
        None,
        algorithm="none",
    )
    r = client.get(
        f"/api/v1/simulations/{job['id']}", headers={"Authorization": f"Bearer {unsigned}"}
    )
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_token"


def test_result_reuse_does_not_leak_private_runs(client):
    spec = scenario("authz-reuse", demand=1.7)
    private = run_job(client, spec, headers=auth(ALICE))
    assert private["status"] == "completed" and private["visibility"] == "private"
    own_copy = run_job(client, spec, headers=auth(ALICE))
    assert own_copy["reused"] is True
    assert own_copy["reused_from_job_id"] == private["id"]
    assert own_copy["owner_id"] == str(ALICE) and own_copy["visibility"] == "private"
    for who, headers in (("bob", auth(BOB)), ("anonymous", None)):
        job = run_job(client, spec, headers=headers)
        assert job["status"] == "completed"
        assert job["reused_from_job_id"] != private["id"], f"{who} reused a private job"
        if job["reused_from_job_id"] is not None:
            source = f"/api/v1/simulations/{job['reused_from_job_id']}"
            assert client.get(source, headers=headers).status_code == 200, who
    # The owner still reuses a result she can read (her own or a public one).
    again = run_job(client, spec, headers=auth(ALICE))
    assert again["reused"] is True
    source = f"/api/v1/simulations/{again['reused_from_job_id']}"
    assert client.get(source, headers=auth(ALICE)).status_code == 200


def test_public_reuse_preserves_new_owner_and_private_default(client):
    spec = scenario("authz-public-reuse", demand=1.8)
    public = run_job(client, spec, headers=auth(ALICE), visibility="public")
    assert public["status"] == "completed" and public["owner_id"] == str(ALICE)
    bobs = run_job(client, spec, headers=auth(BOB))
    assert bobs["reused"] is True and bobs["reused_from_job_id"] == public["id"]
    assert bobs["owner_id"] == str(BOB) and bobs["visibility"] == "private"
    for headers in (auth(ALICE), None):
        assert client.get(f"/api/v1/simulations/{bobs['id']}", headers=headers).status_code == 404
    # Public visibility grants read access, not the right to cancel someone else's job.
    for headers in (auth(BOB), None):
        r = client.post(f"/api/v1/simulations/{public['id']}/cancel", headers=headers)
        assert r.status_code == 403 and r.json()["error"]["code"] == "not_owner"
