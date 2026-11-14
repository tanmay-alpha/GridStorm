#!/usr/bin/env python3
"""Read-only checks against public production URLs; no credentials or writes."""

from __future__ import annotations

import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API = "https://gridstorm-api.onrender.com"
WEB = "https://gridstorm.vercel.app"


def fetch(url: str, *, origin: str | None = None, retries: int = 1):
    headers = {"User-Agent": "GridStorm-Public-Smoke/1", "Accept": "application/json"}
    if origin:
        headers["Origin"] = origin
    for attempt in range(retries):
        try:
            with urlopen(Request(url, headers=headers), timeout=25) as response:
                return (
                    response.status,
                    {k.lower(): v for k, v in response.headers.items()},
                    response.read(3_000_000),
                )
        except HTTPError as exc:
            # 4xx/5xx are real server responses, not cold-start network failures.
            detail = exc.read(500).decode('utf-8', errors='replace').strip()
            raise RuntimeError(
                f"GET {url}: HTTP {exc.code}; response {detail[:240]!r}"
            ) from exc
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
    assert {"pglib-case14-ieee", "scigrid-de", "pypsa-eur-be"} <= ids, ids
    print("PASS networks, CORS", len(ids))

    scenarios, _ = api_json("/api/v1/scenarios?limit=200")
    assert len(scenarios.get("items") or []) > 0
    print("PASS visible scenarios", len(scenarios["items"]))

    assets, _ = api_json("/api/v1/networks/pglib-case14-ieee/assets?type=buses&limit=2")
    assert assets.get("total", 0) >= 14
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
    if completed:
        job_id = completed[0]["id"]
        try:
            result, _ = api_json(f"/api/v1/simulations/{job_id}/result")
            assert result.get("schema_version") == "gridstorm-result/1.0"
            print("PASS completed result retrievable", job_id[:8])
        except Exception as exc:
            raise AssertionError(
                f"Completed job {job_id[:8]} has no available full result: {exc}"
            ) from exc
    else:
        print("WARN no visible completed jobs; persistence not verified")
    print("PASS public read-only smoke")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print("FAIL", exc, file=sys.stderr)
        sys.exit(1)
