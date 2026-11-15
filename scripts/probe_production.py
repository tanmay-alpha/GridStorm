#!/usr/bin/env python3
"""Read-only checks against public production URLs; no credentials or writes."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API = "https://gridstorm-api.onrender.com"
WEB = "https://gridstorm.vercel.app"


def fetch(
    url: str, *, origin: str | None = None, retries: int = 1, accepted_errors: tuple[int, ...] = ()
):
    headers = {"User-Agent": "GridStorm-Public-Smoke/1", "Accept": "application/json"}
    if origin:
        headers["Origin"] = origin
    for attempt in range(retries):
        try:
            with urlopen(Request(url, headers=headers), timeout=25) as response:
                return (
                    response.status,
                    {k.lower(): v for k, v in response.headers.items()},
                    response.read(),
                )
        except HTTPError as exc:
            if exc.code in accepted_errors:
                return exc.code, {k.lower(): v for k, v in exc.headers.items()}, exc.read()
            # 4xx/5xx are real server responses, not cold-start network failures.
            detail = exc.read(500).decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"GET {url}: HTTP {exc.code}; response {detail[:240]!r}") from exc
        except (URLError, TimeoutError) as exc:
            if attempt + 1 >= retries:
                raise RuntimeError(f"GET {url}: {type(exc).__name__}") from exc
            time.sleep(min(10 * (attempt + 1), 20))
    raise AssertionError("unreachable")


def api_json(path: str, *, origin: str | None = None):
    code, headers, raw = fetch(API + path, origin=origin, retries=8 if path == "/health" else 2)
    assert code == 200, (path, code)
    return json.loads(raw), headers


API_SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
}
WEB_HARDENING_HEADERS = ("x-content-type-options", "x-frame-options", "content-security-policy")
FOREIGN_ORIGIN = "https://evil.example"
JWT_RE = re.compile(rb"eyJ[A-Za-z0-9_-]{8,}\.(eyJ[A-Za-z0-9_-]{8,})\.[A-Za-z0-9_-]{8,}")
SECRET_RES = {
    "service_role": re.compile(rb"service_role"),
    "SUPABASE_SERVICE": re.compile(rb"SUPABASE_SERVICE"),
    "SUPABASE_JWT_SECRET": re.compile(rb"SUPABASE_JWT_SECRET"),
    "postgres URL": re.compile(rb"postgres(?:ql)?://[^\s\"']+@"),
    "sk_ key": re.compile(rb"\bsk_(?:live|test)_[A-Za-z0-9]{8,}"),
}


def preflight(origin: str):
    """CORS preflight for POST /api/v1/simulations; returns (status, headers)."""
    req = Request(
        API + "/api/v1/simulations",
        method="OPTIONS",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
            "User-Agent": "GridStorm-Public-Smoke/1",
        },
    )
    try:
        with urlopen(req, timeout=25) as response:
            return response.status, {k.lower(): v for k, v in response.headers.items()}
    except HTTPError as exc:
        return exc.code, {k.lower(): v for k, v in exc.headers.items()}


def scan_web_bundle() -> int:
    """Fetch index.html and every reachable /assets/*.js; fail on server-side secrets."""
    _, _, html = fetch(WEB + "/")
    todo = set(re.findall(rb"/assets/[A-Za-z0-9_.-]+\.js", html))
    seen: set[bytes] = set()
    while todo:
        path = todo.pop()
        seen.add(path)
        _, _, js = fetch(WEB + path.decode())
        for name, pattern in SECRET_RES.items():
            assert not pattern.search(js), f"{name} pattern found in {path.decode()}"
        for match in JWT_RE.finditer(js):
            payload = match.group(1) + b"=" * (-len(match.group(1)) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload))
            assert claims.get("role") != "service_role", f"service_role JWT in {path.decode()}"
            print("INFO JWT in bundle", path.decode(), "role", claims.get("role"))
        for ref in re.findall(rb"(?:/assets/|\./)([A-Za-z0-9_.-]+\.js)", js):
            nxt = b"/assets/" + ref
            if nxt not in seen:
                todo.add(nxt)
    assert seen, "no JS assets found in index.html"
    return len(seen)


def run():
    health, _ = api_json("/health")
    assert health.get("status") == "ok"
    print("PASS API /health", health.get("version"))

    ready, _ = api_json("/ready")
    assert ready.get("status") == "ready", ready.get("status")
    checks = ready.get("checks") or {}
    assert (checks.get("database") or {}).get("kind") == "postgres", "database not Postgres"
    print("PASS API /ready", {k: v.get("status") for k, v in checks.items()})
    storage = checks.get("storage") or {}
    assert storage.get("backend") == "supabase" and storage.get("durable") is True, storage
    print("PASS durable artifact storage", storage.get("detail"))

    _, headers, _ = fetch(API + "/health")
    for name, value in API_SECURITY_HEADERS.items():
        assert headers.get(name) == value, (name, headers.get(name))
    assert "max-age=" in headers.get("strict-transport-security", ""), "API HSTS missing"
    print("PASS API security headers")

    code, headers = preflight(WEB)
    assert code == 200 and headers.get("access-control-allow-origin") == WEB, (code, headers)
    assert "access-control-allow-credentials" not in headers
    code, headers = preflight(FOREIGN_ORIGIN)
    assert code >= 400 and "access-control-allow-origin" not in headers, (code, headers)
    print("PASS CORS preflight: production origin allowed, foreign origin refused")

    networks, headers = api_json("/api/v1/networks?limit=200", origin=WEB)
    assert headers.get("access-control-allow-origin") == WEB, "production CORS origin missing"
    ids = {n.get("id") for n in networks.get("items") or []}
    assert {
        "ac-dc-meshed",
        "pglib-case118-ieee",
        "pglib-case14-ieee",
        "scigrid-de",
        "pypsa-eur-be",
    } <= ids, ids
    print("PASS networks, CORS", len(ids))

    scenarios, _ = api_json("/api/v1/scenarios?limit=200")
    assert len(scenarios.get("items") or []) > 0
    print("PASS visible scenarios", len(scenarios["items"]))

    assets, _ = api_json("/api/v1/networks/pglib-case14-ieee/assets?type=buses&limit=2")
    assert assets.get("total") == 14
    print("PASS IEEE-14 asset endpoint")

    artifacts, _ = api_json("/api/v1/artifacts?limit=100")
    assert artifacts.get("total", 0) > 0
    print("PASS precomputed index", artifacts["total"])

    for route in ("/", "/studio", "/compare", "/library"):
        code, _, html = fetch(WEB + route)
        assert code == 200 and b"<html" in html.lower(), f"unexpected HTML for {route}"
        print("PASS frontend transport", route)

    _, headers, _ = fetch(WEB + "/")
    assert "max-age=" in headers.get("strict-transport-security", ""), "web HSTS missing"
    missing = [h for h in WEB_HARDENING_HEADERS if h not in headers]
    # apps/web/vercel.json sets these; they appear once that config is deployed
    print("PASS web HSTS;", f"WARN web headers missing {missing}" if missing else "hardening ok")
    print("PASS web bundle has no server secrets; JS files scanned:", scan_web_bundle())

    history, _ = api_json("/api/v1/simulations?limit=20")
    completed = [j for j in history.get("items") or [] if j.get("status") == "completed"]
    assert completed, "No visible completed jobs; result persistence cannot be verified"
    durable_id = os.environ.get("GRIDSTORM_DURABLE_JOB_ID")
    job_ids = dict.fromkeys(j["id"] for j in completed)
    if durable_id:
        job_ids[durable_id] = None
    verified = 0
    for job_id in job_ids:
        job, _ = api_json(f"/api/v1/simulations/{job_id}")
        assert job["status"] == "completed", f"Job {job_id} is not completed"
        assert isinstance(job.get("result_available"), bool), (
            "Missing artifact availability metadata"
        )
        if job_id == durable_id:
            assert job["result_available"], "Post-deploy acceptance job did not survive restart"
        if job.get("recomputed_from_job_id"):
            assert job["stage_history"][0]["recomputed_from"] == job["recomputed_from_job_id"]
        if not job["result_available"]:
            code, _, raw = fetch(
                API + f"/api/v1/simulations/{job_id}/result", accepted_errors=(410,)
            )
            assert code == 410, "Missing result must be explicitly HTTP 410"
            error = json.loads(raw)["error"]
            assert error["code"] == "artifact_unavailable"
            assert error["details"]["job_id"] == job_id
            print("PASS lost artifact explicitly disclosed", job_id[:8])
            continue
        try:
            code, headers, raw = fetch(API + f"/api/v1/simulations/{job_id}/result")
            assert code == 200
            digest = hashlib.sha256(raw).hexdigest()
            assert digest == job["result_sha256"], "result bytes differ from recorded sha256"
            assert headers.get("x-gridstorm-result-sha256") == digest, (
                "result sha256 header differs"
            )
            result = json.loads(raw)
            assert result.get("schema_version") == "gridstorm-result/1.0"
            print("PASS completed result retrievable and sha256 verified", job_id[:8])
            verified += 1
        except Exception as exc:
            raise AssertionError(
                f"Completed job {job_id[:8]} has no available full result: {exc}"
            ) from exc
    assert verified > 0, "No actual full result was retrievable"
    print("PASS public read-only smoke")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print("FAIL", exc, file=sys.stderr)
        sys.exit(1)
