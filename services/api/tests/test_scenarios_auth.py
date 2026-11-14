from __future__ import annotations

import uuid

from conftest import JWT_SECRET, NETWORK_ID, auth, make_token, scenario

ALICE = uuid.UUID("11111111-1111-4111-8111-111111111111")
BOB = uuid.UUID("22222222-2222-4222-8222-222222222222")


def test_presets_synced_and_invalid_preset_rejected(client):
    page = client.get("/api/v1/scenarios?preset=true").json()
    ids = {s["id"] for s in page["items"]}
    assert ids == {"preset-base", "preset-stress"}  # preset-bad references a missing generator
    one = client.get("/api/v1/scenarios/preset-stress").json()
    assert one["preset"] is True and one["owner_id"] is None and one["network_id"] == NETWORK_ID
    assert len(one["hash"]) == 64 and one["spec"]["events"][0]["value"] == 1.3
    assert client.get("/api/v1/scenarios/preset-bad").status_code == 404


def test_validate_reports_errors_and_warnings(client):
    ok = client.post("/api/v1/scenarios/validate", json={"scenario": scenario()}).json()
    assert ok["valid"] is True and ok["errors"] == [] and len(ok["scenario_hash"]) == 64
    assert any(w["code"] == "dataset_unpinned" for w in ok["warnings"])
    # bare spec (no wrapper) is accepted too
    assert client.post("/api/v1/scenarios/validate", json=scenario()).json()["valid"] is True

    bad = scenario(events=[{"type": "line_outage", "asset_id": "g-gas"}])
    r = client.post("/api/v1/scenarios/validate", json={"scenario": bad}).json()
    assert r["valid"] is False and r["errors"][0]["code"] == "unknown_asset"

    trafo = scenario(events=[{"type": "line_outage", "asset_id": "l0", "component": "transformer"}])
    assert client.post("/api/v1/scenarios/validate", json=trafo).json()["valid"] is True

    schema = scenario(horizon={"start": 0, "snapshots": -1})
    r = client.post("/api/v1/scenarios/validate", json=schema).json()
    assert r["valid"] is False and r["errors"][0]["code"] == "schema_error"
    assert r["errors"][0]["path"].startswith("horizon")

    too_long = scenario(horizon={"start": 0, "snapshots": 10})
    r = client.post("/api/v1/scenarios/validate", json=too_long).json()
    assert [e["code"] for e in r["errors"]] == ["horizon_out_of_range"]

    other_engine = scenario(execution={"engine": "pandapower", "formulation": "ac_pf"})
    r = client.post("/api/v1/scenarios/validate", json=other_engine).json()
    assert r["valid"] is False
    assert any(e["code"] == "unsupported_operation" and e["path"] == "execution.engine"
               for e in r["errors"])

    unknown_net = scenario(dataset={"network_id": "nowhere", "sha256": None})
    r = client.post("/api/v1/scenarios/validate", json=unknown_net).json()
    assert r["errors"][0]["code"] == "unknown_network"

    pinned = scenario(dataset={"network_id": NETWORK_ID, "sha256": "f" * 64})
    r = client.post("/api/v1/scenarios/validate", json=pinned).json()
    assert any(e["code"] == "dataset_sha256_mismatch" for e in r["errors"])


def test_request_validation_errors(client):
    r = client.post("/api/v1/scenarios/validate", content=b"{not json",
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    r = client.post("/api/v1/simulations", json={})
    assert r.status_code == 422
    r = client.post("/api/v1/simulations", json={"scenario_id": "x", "scenario": scenario()})
    assert r.status_code == 422
    r = client.post("/api/v1/simulations", json={"scenario_id": "x", "bogus": 1})
    assert r.status_code == 422


def test_save_scenario_anonymous_is_public(client):
    r = client.post("/api/v1/scenarios", json={"scenario": scenario("my-case", demand=1.1)})
    assert r.status_code == 201, r.text
    rec = r.json()
    assert rec["visibility"] == "public" and rec["owner_id"] is None and rec["preset"] is False
    assert client.get(f"/api/v1/scenarios/{rec['id']}").json()["hash"] == rec["hash"]
    r = client.post("/api/v1/scenarios", json={"scenario": scenario(), "visibility": "private"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "auth_required_for_private"
    bad = scenario(events=[{"type": "generator_outage", "asset_id": "missing"}])
    r = client.post("/api/v1/scenarios", json={"scenario": bad})
    assert r.status_code == 422 and r.json()["error"]["code"] == "scenario_invalid"
    assert r.json()["error"]["details"]["errors"][0]["code"] == "unknown_asset"


def test_owner_isolation_for_private_scenarios(client):
    r = client.post("/api/v1/scenarios", json={"scenario": scenario("alice-case")},
                    headers=auth(ALICE))
    assert r.status_code == 201
    rec = r.json()
    assert rec["visibility"] == "private" and rec["owner_id"] == str(ALICE)
    sid = rec["id"]
    assert client.get(f"/api/v1/scenarios/{sid}", headers=auth(ALICE)).status_code == 200
    assert client.get(f"/api/v1/scenarios/{sid}", headers=auth(BOB)).status_code == 404
    assert client.get(f"/api/v1/scenarios/{sid}").status_code == 404

    def listed(headers=None):
        return {s["id"] for s in client.get("/api/v1/scenarios", headers=headers).json()["items"]}

    assert sid in listed(auth(ALICE))
    assert sid not in listed(auth(BOB)) and sid not in listed()
    # Bob cannot run Alice's private scenario by id
    r = client.post("/api/v1/simulations", json={"scenario_id": sid}, headers=auth(BOB))
    assert r.status_code == 404


def test_jwt_validation(client):
    r = client.get("/api/v1/scenarios", headers=auth(ALICE))
    assert r.status_code == 200
    expired = make_token(ALICE, expires_in=-10)
    r = client.get("/api/v1/scenarios", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "token_expired"
    assert r.headers["www-authenticate"] == "Bearer"
    forged = make_token(ALICE, secret="wrong-secret-" + JWT_SECRET)
    r = client.get("/api/v1/scenarios", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_token"
    wrong_aud = make_token(ALICE, aud="anon")
    r = client.get("/api/v1/scenarios", headers={"Authorization": f"Bearer {wrong_aud}"})
    assert r.status_code == 401
    not_uuid = make_token("service-account")
    r = client.get("/api/v1/scenarios", headers={"Authorization": f"Bearer {not_uuid}"})
    assert r.status_code == 401
    r = client.get("/api/v1/scenarios", headers={"Authorization": "Basic abc"})
    assert r.status_code == 401
    r = client.get("/api/v1/scenarios", headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401


def test_token_rejected_when_auth_not_configured(client_factory):
    client = client_factory(supabase_jwt_secret=None)
    r = client.get("/api/v1/scenarios", headers=auth(ALICE))
    assert r.status_code == 401 and r.json()["error"]["code"] == "auth_not_configured"
    assert client.get("/api/v1/scenarios").status_code == 200


def test_rate_limit_on_posts(client_factory):
    client = client_factory(rate_limit_post_per_min=1.0, rate_limit_post_burst=2)
    body = {"scenario": scenario()}
    codes = [client.post("/api/v1/scenarios/validate", json=body).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    r = client.post("/api/v1/scenarios/validate", json=body)
    assert r.json()["error"]["code"] == "rate_limited" and int(r.headers["retry-after"]) >= 1
    assert client.get("/api/v1/scenarios").status_code == 200  # GETs are not limited


def test_body_size_limit(client_factory):
    client = client_factory(max_body_bytes=1024)
    big = scenario(description="x" * 2000)
    r = client.post("/api/v1/scenarios/validate", json=big)
    assert r.status_code == 413 and r.json()["error"]["code"] == "payload_too_large"
