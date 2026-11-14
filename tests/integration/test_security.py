"""Black-box security checks: CORS, body limits, rate limits, JWT forgery, cross-user isolation,
injection surfaces."""

from __future__ import annotations

import base64
import copy
import json
import uuid

import httpx
import pytest

from conftest import ALLOWED_ORIGIN, JWT_SECRET, make_token
from gs_helpers import assert_error

EVIL_ORIGIN = "https://evil.example.com"


def _b64(obj: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()


def _alg_none_token(sub: str) -> str:
    return f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{_b64({'sub': sub, 'aud': 'authenticated'})}."


def test_cors_rejects_foreign_origin(client: httpx.Client) -> None:
    r = client.options(
        "/api/v1/networks",
        headers={"Origin": EVIL_ORIGIN, "Access-Control-Request-Method": "GET"},
    )
    acao = r.headers.get("access-control-allow-origin")
    assert acao not in (EVIL_ORIGIN, "*"), f"CORS allows {acao!r}"
    r = client.get("/api/v1/networks", headers={"Origin": EVIL_ORIGIN})
    assert r.headers.get("access-control-allow-origin") not in (EVIL_ORIGIN, "*")
    assert r.headers.get("access-control-allow-credentials") != "true" or (
        r.headers.get("access-control-allow-origin") is None
    )


def test_cors_allows_configured_origin(client: httpx.Client) -> None:
    r = client.options(
        "/api/v1/networks",
        headers={"Origin": ALLOWED_ORIGIN, "Access-Control-Request-Method": "GET"},
    )
    assert r.status_code in (200, 204), r.text
    assert r.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN


def test_body_limit(client: httpx.Client) -> None:
    big = {"padding": "x" * (2 * 1024 * 1024)}
    r = client.post("/api/v1/scenarios/validate", json=big)
    assert_error(r, 413)


def test_body_limit_without_content_length(client: httpx.Client) -> None:
    def gen():
        for _ in range(64):
            yield b"x" * 65536

    r = client.post(
        "/api/v1/scenarios/validate", content=gen(), headers={"content-type": "application/json"}
    )
    assert r.status_code in (400, 413, 422), r.status_code
    assert r.status_code != 500


@pytest.mark.parametrize("kind", ["wrong-secret", "alg-none", "garbage", "expired"])
def test_forged_tokens_never_grant_identity(
    client: httpx.Client, acdc_preset: dict, kind: str
) -> None:
    """A forged/invalid bearer token must be rejected (401) or at least never be trusted."""
    sub = str(uuid.uuid4())
    token = {
        "wrong-secret": lambda: make_token(sub, "not-the-real-secret-" + "x" * 32),
        "alg-none": lambda: _alg_none_token(sub),
        "garbage": lambda: "abc.def.ghi",
        "expired": lambda: make_token(
            sub, JWT_SECRET or "not-the-real-secret-" + "x" * 32, exp=1, iat=0
        ),
    }[kind]()
    spec = copy.deepcopy(acdc_preset["spec"])
    spec["id"] = f"it-forged-{uuid.uuid4().hex[:8]}"
    r = client.post("/api/v1/scenarios", json=spec, headers={"Authorization": f"Bearer {token}"})
    if r.status_code == 401:
        assert_error(r, 401)
        return
    assert r.status_code in (200, 201), r.text
    assert r.json().get("owner_id") != sub, f"{kind} token was trusted as user {sub}"


@pytest.mark.skipif(JWT_SECRET is None, reason="GRIDSTORM_TEST_JWT_SECRET not set")
def test_cross_user_isolation(client: httpx.Client, acdc_preset: dict) -> None:
    alice, bob = str(uuid.uuid4()), str(uuid.uuid4())
    ha = {"Authorization": f"Bearer {make_token(alice, JWT_SECRET)}"}
    hb = {"Authorization": f"Bearer {make_token(bob, JWT_SECRET)}"}
    spec = copy.deepcopy(acdc_preset["spec"])
    spec["id"] = f"it-alice-{uuid.uuid4().hex[:8]}"
    r = client.post("/api/v1/scenarios", json=spec, headers=ha)
    assert r.status_code in (200, 201), r.text
    rec = r.json()
    assert rec["owner_id"] == alice
    # Alice sees it; Bob and anonymous users must not.
    assert client.get(f"/api/v1/scenarios/{rec['id']}", headers=ha).status_code == 200
    assert client.get(f"/api/v1/scenarios/{rec['id']}", headers=hb).status_code in (403, 404)
    assert client.get(f"/api/v1/scenarios/{rec['id']}").status_code in (401, 403, 404)
    listed = client.get("/api/v1/scenarios", params={"limit": 500}, headers=hb).json()["items"]
    assert rec["id"] not in {s["id"] for s in listed}
    # Bob cannot run Alice's scenario by id.
    r = client.post("/api/v1/simulations", json={"scenario_id": rec["id"]}, headers=hb)
    assert r.status_code in (403, 404), r.text


@pytest.mark.parametrize(
    ("method", "path", "params"),
    [
        ("GET", "/api/v1/networks", {"limit": "1; DROP TABLE jobs"}),
        ("GET", "/api/v1/simulations", {"offset": "0 OR 1=1"}),
        ("GET", "/api/v1/artifacts", {"engine": "' OR '1'='1", "network_id": 'x" OR 1=1 --'}),
        ("GET", "/api/v1/simulations/' OR '1'='1", {}),
        ("GET", "/api/v1/scenarios/1%27%20OR%20%271%27=%271", {}),
        ("GET", "/api/v1/reports/x", {"format": "json'; --"}),
    ],
)
def test_injection_surfaces_do_not_500(
    client: httpx.Client, method: str, path: str, params: dict
) -> None:
    r = client.request(method, path, params=params)
    assert r.status_code < 500, (path, r.status_code, r.text[:300])
    if r.status_code == 200:
        body = r.json()
        assert body.get("items") in ([], None) or "artifacts" in path, body


def test_inline_scenario_injection_in_ids(client: httpx.Client, acdc_preset: dict) -> None:
    """Asset ids flow into subprocess args / file names in some engines; must be validated."""
    spec = copy.deepcopy(acdc_preset["spec"])
    spec["id"] = "it-injection"
    spec["events"] = [{"type": "generator_outage", "asset_id": "$(touch /tmp/pwned); ../../x"}]
    r = client.post("/api/v1/simulations", json={"scenario": spec})
    assert_error(r, {400, 422})


def test_error_bodies_do_not_leak_internals(client: httpx.Client) -> None:
    r = client.post(
        "/api/v1/scenarios", content=b"{bad", headers={"content-type": "application/json"}
    )
    assert r.status_code in (400, 422)
    for needle in ("Traceback", 'File "', "site-packages", "sqlalchemy", "psycopg"):
        assert needle not in r.text, needle


def test_security_headers_or_docs(client: httpx.Client) -> None:
    r = client.get("/openapi.json")
    assert r.status_code == 200, "OpenAPI schema should be served (P1-06 acceptance)"
    paths = r.json()["paths"]
    for p in (
        "/api/v1/networks",
        "/api/v1/simulations",
        "/api/v1/comparisons",
        "/api/v1/artifacts/{engine}/{artifact_id}",
    ):
        assert p in paths, p


@pytest.mark.ratelimit
def test_post_rate_limit(client: httpx.Client) -> None:
    codes = []
    for _ in range(200):
        r = client.post("/api/v1/scenarios/validate", json={})
        codes.append(r.status_code)
        if r.status_code == 429:
            assert_error(r, 429)
            assert "retry-after" in {k.lower() for k in r.headers}
            break
    assert 429 in codes, "no rate limit after 200 POSTs"
