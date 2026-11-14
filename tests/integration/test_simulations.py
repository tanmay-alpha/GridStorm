"""Simulation job lifecycle, results, comparisons and reports (contract §4, §6).

Tests marked ``live`` submit real PyPSA jobs on the target server (ac-dc-meshed presets are
small). The scientific checks recompute metrics from the returned series independently.
"""

from __future__ import annotations

import copy
import math

import httpx
import pytest

from conftest import JOB_TIMEOUT_S
from gs_helpers import (
    PROVENANCE,
    TERMINAL_STATUSES,
    assert_error,
    assert_job_shape,
    assert_page,
    canonical_sha256,
    wait_for_job,
)

TOL_MWH = 1e-3


def _submit(client: httpx.Client, body: dict) -> dict:
    r = client.post("/api/v1/simulations", json=body)
    assert r.status_code == 202, r.text
    job = r.json()
    assert_job_shape(job)
    return job


@pytest.fixture(scope="module")
def completed_job(client: httpx.Client, acdc_preset: dict) -> dict:
    job = _submit(client, {"scenario_id": acdc_preset["id"]})
    job = wait_for_job(client, job["id"], JOB_TIMEOUT_S)
    assert job["status"] == "completed", job
    return job


@pytest.fixture(scope="module")
def baseline_job(client: httpx.Client, acdc_preset: dict) -> dict:
    """The preset with all events removed (an explicit inline baseline)."""
    spec = copy.deepcopy(acdc_preset["spec"])
    spec["id"] = f"{spec['id'][:50]}-itbase"
    spec["events"] = []
    job = _submit(client, {"scenario": spec})
    job = wait_for_job(client, job["id"], JOB_TIMEOUT_S)
    assert job["status"] == "completed", job
    return job


def test_jobs_page(client: httpx.Client) -> None:
    r = client.get("/api/v1/simulations", params={"limit": 5, "offset": 0})
    assert r.status_code == 200, r.text
    for job in assert_page(r.json(), limit=5, offset=0):
        assert_job_shape(job)


def test_unknown_job_404(client: httpx.Client) -> None:
    for suffix in ("", "/metrics", "/result", "/artifacts"):
        assert_error(client.get(f"/api/v1/simulations/nonexistent-job{suffix}"), 404)
    assert_error(client.post("/api/v1/simulations/nonexistent-job/cancel"), 404)


@pytest.mark.parametrize(
    "body",
    [{}, {"scenario_id": "no-such-scenario"}, {"scenario": {"id": "x"}}, {"scenario_id": 5}],
)
def test_bad_submission_rejected(client: httpx.Client, body: dict) -> None:
    r = client.post("/api/v1/simulations", json=body)
    assert_error(r, {400, 404, 422})


def test_unsupported_operation_not_queued(client: httpx.Client, acdc_preset: dict) -> None:
    """An inline scenario the engine cannot represent must be rejected before queuing."""
    lines = client.get(
        "/api/v1/networks/ac-dc-meshed/assets", params={"type": "lines", "limit": 1}
    ).json()["items"]
    spec = copy.deepcopy(acdc_preset["spec"])
    spec["id"] = "it-partial-window"
    h = spec["horizon"]
    spec["events"] = [
        {
            "type": "line_outage",
            "asset_id": lines[0]["id"],
            "window": {"start": h["start"], "end": h["start"] + 1},
        }
    ]
    before = client.get("/api/v1/simulations", params={"limit": 1}).json()["total"]
    err = assert_error(client.post("/api/v1/simulations", json={"scenario": spec}), {400, 422})
    assert "unsupported_operation" in str(err), err
    after = client.get("/api/v1/simulations", params={"limit": 1}).json()["total"]
    assert after == before, "a rejected scenario created a job"


@pytest.mark.live
def test_job_lifecycle_and_result(client: httpx.Client, completed_job: dict, acdc_preset) -> None:
    job = completed_job
    assert job["outcome"] in {"feasible", "infeasible"}
    assert job["stage"] == "done"
    stages = [h["stage"] for h in job["stage_history"]]
    if not job["reused"]:
        for s in ("loading_network", "solving", "done"):
            assert s in stages, stages
    assert job["scenario_hash"] == acdc_preset["hash"]
    assert job["network_id"] == "ac-dc-meshed"
    assert job["solver"] and job["solver"]["name"] == "highs"
    assert job["finished_at"] >= job["created_at"]

    res = client.get(f"/api/v1/simulations/{job['id']}/result")
    assert res.status_code == 200, res.text
    result = res.json()
    assert result["schema_version"] == "gridstorm-result/1.0"
    assert result["scenario_hash"] == job["scenario_hash"]
    assert result["outcome"] == job["outcome"]
    manifest = result["manifest"]
    assert manifest["scenario_hash"] == job["scenario_hash"]
    body = {k: v for k, v in result.items() if k != "manifest"}
    assert manifest["result_sha256"] == canonical_sha256(body), "result_sha256 mismatch"
    assert job["result_sha256"] == manifest["result_sha256"]

    met = client.get(f"/api/v1/simulations/{job['id']}/metrics")
    assert met.status_code == 200, met.text
    assert "unserved_energy_mwh" in met.text

    arts = client.get(f"/api/v1/simulations/{job['id']}/artifacts")
    assert arts.status_code == 200, arts.text
    assert "sha256" in arts.text


@pytest.mark.live
def test_result_physics_recomputed(
    client: httpx.Client, completed_job: dict, acdc_preset: dict
) -> None:
    """Independent recomputation of headline metrics from the result series."""
    result = client.get(f"/api/v1/simulations/{completed_job['id']}/result").json()
    if result["outcome"] != "feasible":
        assert not any(result["series"].get(k) for k in ("load_mw", "load_shed_mw")), (
            "infeasible result must not carry fabricated series"
        )
        return
    w = result["snapshot_weightings_h"]
    s = result["series"]
    m = result["metrics"]
    n = len(result["snapshots"])
    assert len(w) == n and len(s["load_mw"]) == n and len(s["load_shed_mw"]) == n
    unserved = sum(p * dt for p, dt in zip(s["load_shed_mw"], w, strict=True))
    total = sum(p * dt for p, dt in zip(s["load_mw"], w, strict=True))
    assert math.isclose(m["unserved_energy_mwh"], unserved, rel_tol=1e-6, abs_tol=TOL_MWH)
    assert math.isclose(m["total_load_mwh"], total, rel_tol=1e-6, abs_tol=TOL_MWH)
    assert math.isclose(
        m["served_load_mwh"] + m["unserved_energy_mwh"], m["total_load_mwh"], abs_tol=TOL_MWH
    )
    assert m["peak_load_shed_mw"] == pytest.approx(max(s["load_shed_mw"]), abs=1e-6)
    assert abs(m["balance_residual_max_mw"]) < 1e-3
    for g in result["assets"]["generators"]:
        for p, avail in zip(g["p_mw"], g["available_mw"], strict=True):
            assert p <= avail + 1e-4, (g["id"], p, avail)
        if g["outaged"]:
            assert max(abs(p) for p in g["p_mw"]) <= 1e-6, g["id"]
    for ln in result["assets"]["lines"]:
        if ln["outaged"]:
            assert max(abs(f) for f in ln["flow_mw"]) <= 1e-6, ln["id"]
        for f, pct in zip(ln["flow_mw"], ln["loading_pct"], strict=True):
            if ln["s_nom_mva"]:
                assert pct == pytest.approx(abs(f) / ln["s_nom_mva"] * 100, rel=1e-3, abs=1e-3)
    ls = acdc_preset["spec"].get("mitigation", {}).get("load_shedding", {})
    if ls.get("enabled", True):
        voll = ls.get("voll_eur_per_mwh", 10000.0)
        assert m["load_shedding_cost_eur"] == pytest.approx(unserved * voll, rel=1e-4, abs=1e-2)
    else:
        assert m["unserved_energy_mwh"] == 0
    assert result["assumptions"], "result has no assumptions"


@pytest.mark.live
def test_resubmit_identical_scenario(client: httpx.Client, completed_job: dict, acdc_preset):
    job = _submit(client, {"scenario_id": acdc_preset["id"]})
    job = wait_for_job(client, job["id"], JOB_TIMEOUT_S)
    assert job["status"] == "completed"
    assert job["scenario_hash"] == completed_job["scenario_hash"]
    if job["reused"]:
        assert job["result_sha256"] == completed_job["result_sha256"]


@pytest.mark.live
def test_cancel_queued_job(client: httpx.Client, acdc_preset: dict) -> None:
    """With bounded concurrency, the second of two fresh jobs is queued and must cancel cleanly."""
    jobs = []
    for seed in (101, 102):
        spec = copy.deepcopy(acdc_preset["spec"])
        spec["id"] = f"it-cancel-{seed}"
        spec["execution"]["seed"] = seed  # distinct hash => no reuse
        jobs.append(_submit(client, {"scenario": spec}))
    target = jobs[-1]
    r = client.post(f"/api/v1/simulations/{target['id']}/cancel")
    if r.status_code == 409:
        assert_error(r, 409)
        assert client.get(f"/api/v1/simulations/{target['id']}").json()["status"] in (
            TERMINAL_STATUSES
        )
    else:
        assert r.status_code in (200, 202), r.text
        final = wait_for_job(client, target["id"], JOB_TIMEOUT_S)
        assert final["status"] == "cancelled", final
        assert final["outcome"] is None
        assert final["result_sha256"] is None
        assert_error(client.get(f"/api/v1/simulations/{target['id']}/result"), {404, 409})
        # Cancelling a cancelled job is a conflict, not a silent success that resurrects it.
        again = client.post(f"/api/v1/simulations/{target['id']}/cancel")
        assert again.status_code in (200, 409), again.text
        assert client.get(f"/api/v1/simulations/{target['id']}").json()["status"] == "cancelled"
    for j in jobs[:-1]:
        client.post(f"/api/v1/simulations/{j['id']}/cancel")


@pytest.mark.live
def test_comparison_and_reports(
    client: httpx.Client, completed_job: dict, baseline_job: dict
) -> None:
    r = client.post(
        "/api/v1/comparisons",
        json={"baseline_job_id": baseline_job["id"], "scenario_job_id": completed_job["id"]},
    )
    assert r.status_code in (200, 201), r.text
    comp = r.json()
    assert "id" in comp
    got = client.get(f"/api/v1/comparisons/{comp['id']}")
    assert got.status_code == 200
    assert got.json() == comp

    base_m = client.get(f"/api/v1/simulations/{baseline_job['id']}/result").json()["metrics"]
    scen_m = client.get(f"/api/v1/simulations/{completed_job['id']}/result").json()["metrics"]
    expected = scen_m["unserved_energy_mwh"] - base_m["unserved_energy_mwh"]
    found = _find_delta(comp, "unserved_energy_mwh")
    assert found is not None, f"comparison has no unserved_energy_mwh delta: {comp}"
    assert found == pytest.approx(expected, abs=1e-6)

    rj = client.get(f"/api/v1/reports/{comp['id']}", params={"format": "json"})
    assert rj.status_code == 200, rj.text
    assert completed_job["scenario_hash"] in rj.text
    rm = client.get(f"/api/v1/reports/{comp['id']}", params={"format": "md"})
    assert rm.status_code == 200, rm.text
    assert "markdown" in rm.headers["content-type"] or "text/" in rm.headers["content-type"]
    assert completed_job["scenario_hash"] in rm.text
    assert any(p in rm.text for p in PROVENANCE), "markdown report carries no provenance labels"
    jr = client.get(f"/api/v1/reports/{completed_job['id']}", params={"format": "md"})
    assert jr.status_code == 200, jr.text
    assert_error(client.get(f"/api/v1/reports/{comp['id']}", params={"format": "exe"}), {400, 422})


def _find_delta(obj, metric: str):
    """Locate ``scenario - baseline`` for ``metric`` in a comparison of unknown nesting."""
    if isinstance(obj, dict):
        if obj.get("metric") == metric or obj.get("name") == metric or obj.get("key") == metric:
            for k in ("delta", "difference", "diff", "delta_abs"):
                if k in obj:
                    return obj[k]
        for k, v in obj.items():
            if k in (metric, f"{metric}_delta", f"delta_{metric}") and isinstance(v, dict):
                for kk in ("delta", "difference", "diff", "delta_abs"):
                    if kk in v:
                        return v[kk]
            if k == f"delta_{metric}" or k == f"{metric}_delta":
                return v
            found = _find_delta(v, metric)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _find_delta(v, metric)
            if found is not None:
                return found
    return None


def test_comparison_unknown_jobs(client: httpx.Client) -> None:
    r = client.post(
        "/api/v1/comparisons", json={"baseline_job_id": "nope-1", "scenario_job_id": "nope-2"}
    )
    assert_error(r, {404, 422})
    assert_error(client.get("/api/v1/comparisons/nope"), 404)
    assert_error(client.get("/api/v1/reports/nope", params={"format": "json"}), 404)
