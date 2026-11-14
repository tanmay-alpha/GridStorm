"""End-to-end: the API runs the real ``python -m gridstorm_pypsa run`` on the committed
``ac-dc-meshed`` dataset with the committed presets, then compares two real results."""

from __future__ import annotations

import importlib.util
import json

import pytest

from conftest import wait_job
from gridstorm_api.config import DEFAULT_ENGINE_CMD, REPO_ROOT

pytestmark = pytest.mark.slow

NET_DIR = REPO_ROOT / "data" / "networks" / "ac-dc-meshed"
PRESETS = REPO_ROOT / "packages" / "stormspec" / "presets"
BASELINE = "ac-dc-meshed-baseline"
OUTAGE = "ac-dc-meshed-dc-link-outage"


def _missing() -> str | None:
    if importlib.util.find_spec("gridstorm_pypsa") is None:
        return "gridstorm_pypsa is not installed in this environment"
    for path in (
        NET_DIR / "network.nc",
        NET_DIR / "canonical.json",
        REPO_ROOT / "data" / "networks" / "catalog.json",
        PRESETS / f"{BASELINE}.yaml",
        PRESETS / f"{OUTAGE}.yaml",
    ):
        if not path.is_file():
            return f"missing {path.relative_to(REPO_ROOT)}"
    return None


@pytest.fixture
def real_client(client_factory):
    reason = _missing()
    if reason:
        pytest.skip(f"real-engine e2e skipped: {reason}")
    return client_factory(
        data_dir=REPO_ROOT / "data",
        presets_dir=PRESETS,
        engine_cmd=DEFAULT_ENGINE_CMD,
        job_timeout_s=300.0,
        job_memory_mb=1500,
    )


def test_real_pypsa_run_and_comparison(real_client):
    client = real_client
    ids = {s["id"] for s in client.get("/api/v1/scenarios?preset=true&limit=500").json()["items"]}
    assert {BASELINE, OUTAGE} <= ids

    jobs = {}
    for sid in (BASELINE, OUTAGE):
        r = client.post("/api/v1/simulations", json={"scenario_id": sid})
        assert r.status_code == 202, r.text
        jobs[sid] = wait_job(client, r.json()["id"], timeout=300)
    for sid, job in jobs.items():
        assert job["status"] == "completed", (sid, job)
        assert job["outcome"] == "feasible", (sid, job)
        assert job["stage_history"][-1]["stage"] == "done"
        assert job["solver"]["name"] == "highs"

    result = client.get(f"/api/v1/simulations/{jobs[OUTAGE]['id']}/result").json()
    assert result["schema_version"] == "gridstorm-result/1.0"
    assert result["scenario_hash"] == jobs[OUTAGE]["scenario_hash"]
    links = {link["id"]: link for link in result["assets"]["links"]}
    assert links["DC link"]["outaged"] is True
    assert abs(result["metrics"]["balance_residual_max_mw"]) < 1e-3

    r = client.post(
        "/api/v1/comparisons",
        json={"baseline_job_id": jobs[BASELINE]["id"], "scenario_job_id": jobs[OUTAGE]["id"]},
    )
    assert r.status_code == 201, r.text
    report = r.json()["report"]
    m = {row["metric"]: row for row in report["metrics"]}
    assert m["total_system_cost_eur"]["delta"] is not None
    link_rows = [b for b in report["branch_loading"] if b["component"] == "link"]
    assert any(b["id"] == "DC link" and b["scenario_outaged"] for b in link_rows)
    md = client.get(f"/api/v1/reports/{r.json()['id']}?format=md").text
    assert "ac-dc-meshed" in md
    json.dumps(report)  # serialisable
