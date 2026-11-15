"""Audit public completed results; opt in with ``-m network -s``.

HTTP 410/500 result bodies are unavailable evidence, never scientific passes. Every such
job is printed with its status, and a wholly unavailable inventory makes this test skip.
"""

import json
import os
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import urlopen

import pytest
import stormspec

from harness import evaluate_result
from paths import NETWORKS


def get_json(base, path):
    try:
        with urlopen(base + path, timeout=120) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        if exc.code not in {410, 500}:
            raise
        return exc.code, json.loads(exc.read())


@pytest.mark.network
def test_public_completed_results():
    base = os.environ.get("GRIDSTORM_API_URL", "https://gridstorm-api.onrender.com").rstrip("/")
    status, inventory = get_json(base, "/api/v1/simulations?limit=100")
    assert status == 200, inventory
    completed = [job for job in inventory["items"] if job["status"] == "completed"]
    checked = []
    unavailable = []
    failures = {}
    print(
        json.dumps(
            {
                "api": base,
                "listed": len(inventory["items"]),
                "total": inventory["total"],
                "completed": len(completed),
            }
        )
    )
    for job in completed:
        jid = quote(job["id"], safe="")
        status, result = get_json(base, f"/api/v1/simulations/{jid}/result")
        if status in {410, 500}:
            row = {
                "job_id": job["id"],
                "http_status": status,
                "error_code": result.get("error", {}).get("code"),
            }
            unavailable.append(row)
            print(json.dumps(row))
            continue
        assert status == 200, (job["id"], status)
        sid = quote(job.get("scenario_record_id") or job["scenario_id"], safe="")
        status, detail = get_json(base, f"/api/v1/scenarios/{sid}")
        assert status == 200, (job["id"], status, detail)
        scenario = stormspec.Scenario.model_validate(detail["spec"])
        report = evaluate_result(result, scenario, job["id"])
        expected_hash = stormspec.scenario_hash(scenario)
        report.require(
            "provenance",
            all(
                value == expected_hash
                for value in (
                    detail["hash"],
                    job["scenario_hash"],
                    result["scenario_hash"],
                    result["manifest"]["scenario_hash"],
                )
            ),
            "scenario hash differs between normalized spec/job/result/manifest",
        )
        report.require(
            "provenance",
            result["network_id"] == scenario.dataset.network_id,
            "result network id differs from scenario",
        )
        report.require(
            "provenance",
            result["manifest"]["dataset_sha256"]
            == stormspec.file_sha256(NETWORKS / scenario.dataset.network_id / "network.nc"),
            "result dataset SHA differs from the committed network.nc",
        )
        report.require(
            "provenance",
            result["manifest"]["result_sha256"] == stormspec.result_sha256(result),
            "result content SHA does not recompute",
        )
        checked.append(job["id"])
        if report.failures():
            failures[job["id"]] = report.failures()
        print(
            json.dumps(
                {
                    "job_id": job["id"],
                    "http_status": 200,
                    "failures": report.failures(),
                    "facts": report.facts,
                }
            )
        )
    assert not failures, failures
    if not checked:
        pytest.skip(
            "No retrievable completed results; "
            f"completed={len(completed)}, unavailable={unavailable}"
        )
