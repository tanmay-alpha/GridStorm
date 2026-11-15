#!/usr/bin/env python3
"""Read-only checks against public production URLs; no credentials or writes."""

from __future__ import annotations

import json
import hashlib
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API = "https://gridstorm-api.onrender.com"
WEB = "https://gridstorm.vercel.app"


def fetch(url: str, *, origin: str | None = None, retries: int = 1, accepted_errors: tuple[int, ...] = ()):
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


def run():
    health, _ = api_json("/health")
    assert health.get("status") == "ok"
    print("PASS API /health", health.get("version"))

    ready, _ = api_json("/ready")
    assert ready.get("status") == "ready", ready.get("status")
    checks = ready.get("checks") or {}
    assert (checks.get("database") or {}).get("kind") == "postgres", "database not Postgres"
    print("PASS API /ready", {k: v.get("status") for k, v in checks.items()})

    networks, headers = api_json("/api/v1/networks?limit=200", origin=WEB)
    assert headers.get("access-control-allow-origin") == WEB, "production CORS origin missing"
    ids = {n.get("id") for n in networks.get("items") or []}
    assert {"ac-dc-meshed", "pglib-case118-ieee", "pglib-case14-ieee", "scigrid-de", "pypsa-eur-be"} <= ids, ids
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

    history, _ = api_json("/api/v1/simulations?limit=100")
    completed = [j for j in history.get("items") or [] if j.get("status") == "completed"]
    assert completed, "No visible completed jobs; result persistence cannot be verified"
    durable_id = os.environ.get("GRIDSTORM_DURABLE_JOB_ID")
    job_ids = dict.fromkeys([j["id"] for j in completed[:3]])
    job_ids["2d47898b-8546-420e-a382-acc29f14d3d4"] = None
    if durable_id:
        job_ids[durable_id] = None
    verified = 0
    for job_id in job_ids:
        job, _ = api_json(f"/api/v1/simulations/{job_id}")
        assert job["status"] == "completed", f"Job {job_id} is not completed"
        assert isinstance(job.get("result_available"), bool), "Missing artifact availability metadata"
        if job_id == durable_id:
            assert job["result_available"], "Post-deploy acceptance job did not survive restart"
        if job.get("recomputed_from_job_id"):
            assert job["stage_history"][0]["recomputed_from"] == job["recomputed_from_job_id"]
        if not job["result_available"]:
            code, _, raw = fetch(API + f"/api/v1/simulations/{job_id}/result", accepted_errors=(410,))
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
            assert headers.get("x-gridstorm-result-sha256") == digest, "result sha256 header differs"
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
