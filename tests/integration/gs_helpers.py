"""Shared helpers for the black-box API tests (no imports from GridStorm code on purpose)."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

import httpx

TERMINAL_STATUSES = {"completed", "failed", "cancelled", "timeout"}
JOB_STATUSES = {"queued", "running"} | TERMINAL_STATUSES
STAGES = [
    "queued",
    "loading_network",
    "applying_scenario",
    "building_model",
    "solving",
    "postprocessing",
    "done",
]
OUTCOMES = {"feasible", "infeasible", "error", None}
PROVENANCE = {"observed", "estimated", "synthetic", "modeled", "calculated"}
JOB_KEYS = {
    "id",
    "scenario_id",
    "scenario_hash",
    "network_id",
    "execution_mode",
    "reused",
    "status",
    "stage",
    "stage_history",
    "outcome",
    "solver",
    "error",
    "created_at",
    "started_at",
    "finished_at",
    "result_sha256",
    "owner_id",
}


def canonical_sha256(obj: Any) -> str:
    """sha256 of canonical JSON (sorted keys, compact separators) — contract §5."""
    data = json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def assert_error(resp: httpx.Response, status: int | set[int], code: str | None = None) -> dict:
    """Assert the contract error shape ``{"error": {"code", "message", "details"}}``."""
    wanted = {status} if isinstance(status, int) else status
    assert resp.status_code in wanted, (
        f"{resp.request.method} {resp.request.url}: expected {sorted(wanted)}, "
        f"got {resp.status_code}: {resp.text[:500]}"
    )
    body = resp.json()
    assert set(body) == {"error"}, body
    err = body["error"]
    assert isinstance(err.get("code"), str) and err["code"], err
    assert isinstance(err.get("message"), str), err
    assert isinstance(err.get("details"), dict), err
    if code is not None:
        assert err["code"] == code, err
    return err


def assert_page(body: Any, limit: int | None = None, offset: int | None = None) -> list:
    assert isinstance(body, dict), body
    assert {"items", "total", "limit", "offset"} <= set(body), sorted(body)
    assert isinstance(body["items"], list)
    assert isinstance(body["total"], int) and body["total"] >= len(body["items"])
    if limit is not None:
        assert body["limit"] == limit
        assert len(body["items"]) <= limit
    if offset is not None:
        assert body["offset"] == offset
    return body["items"]


def assert_job_shape(job: dict) -> None:
    missing = JOB_KEYS - set(job)
    assert not missing, f"job missing keys {sorted(missing)}: {job}"
    assert job["status"] in JOB_STATUSES, job["status"]
    assert job["stage"] in STAGES, job["stage"]
    assert job["outcome"] in OUTCOMES, job["outcome"]
    assert job["execution_mode"] in {"live", "precomputed"}
    assert isinstance(job["reused"], bool)
    # Contract §6: no percentage progress anywhere in the job.
    for key in job:
        assert "progress" not in key and "percent" not in key, key
    hist = [h["stage"] for h in job["stage_history"]]
    order = [STAGES.index(s) for s in hist]
    assert order == sorted(order), f"stage_history out of order: {hist}"


def wait_for_job(client: httpx.Client, job_id: str, timeout_s: float, poll_s: float = 2.0) -> dict:
    deadline = time.monotonic() + timeout_s
    seen_stages: list[str] = []
    while True:
        r = client.get(f"/api/v1/simulations/{job_id}")
        assert r.status_code == 200, r.text
        job = r.json()
        assert_job_shape(job)
        if not seen_stages or seen_stages[-1] != job["stage"]:
            seen_stages.append(job["stage"])
        if job["status"] in TERMINAL_STATUSES:
            return job
        if time.monotonic() > deadline:
            raise AssertionError(
                f"job {job_id} not terminal after {timeout_s}s; stages seen {seen_stages}"
            )
        time.sleep(poll_s)


def iter_pages(client: httpx.Client, path: str, limit: int = 50, **params: Any) -> list:
    """Walk a paginated collection; checks totals stay consistent across pages."""
    items: list = []
    offset = 0
    while True:
        r = client.get(path, params={**params, "limit": limit, "offset": offset})
        assert r.status_code == 200, r.text
        body = r.json()
        page = assert_page(body, limit=limit, offset=offset)
        items.extend(page)
        offset += limit
        if offset >= body["total"] or not page:
            assert len(items) == body["total"], (len(items), body["total"])
            return items
