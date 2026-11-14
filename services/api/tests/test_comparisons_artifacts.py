from __future__ import annotations

import hashlib
import json
import uuid

import pytest
from conftest import NETWORK_ID, auth, run_job, scenario

from gridstorm_api.comparisons import branch_max_loading, compare_results, delta_row

ALICE = uuid.UUID("11111111-1111-4111-8111-111111111111")
BOB = uuid.UUID("22222222-2222-4222-8222-222222222222")


def test_delta_math():
    assert delta_row(100.0, 120.0) == {"baseline": 100.0, "scenario": 120.0, "delta": 20.0,
                                       "delta_pct": 20.0}
    assert delta_row(-50.0, -25.0)["delta_pct"] == pytest.approx(50.0)
    assert delta_row(0.0, 5.0) == {"baseline": 0.0, "scenario": 5.0, "delta": 5.0,
                                   "delta_pct": None}
    assert delta_row(None, 5.0)["delta"] is None  # missing is never treated as 0
    assert delta_row(True, 1.0)["baseline"] is None
    assert delta_row(float("nan"), 1.0)["delta"] is None


def test_compare_results_carriers_and_branches():
    base = {
        "outcome": "feasible",
        "metrics": {"total_load_mwh": 400.0, "generation_by_carrier_mwh": {"gas": 240.0,
                                                                          "wind": 160.0}},
        "assets": {
            "lines": [{"id": "a", "loading_pct": [10.0, -60.0], "outaged": False}],
            "transformers": [{"id": "a", "loading_pct": [30.0], "outaged": False}],
            "links": [{"id": "k", "p_nom_mw": 50.0, "flow_mw": [-25.0, 10.0], "outaged": False}],
        },
    }
    scen = {
        "outcome": "feasible",
        "metrics": {"total_load_mwh": 480.0, "generation_by_carrier_mwh": {"gas": 300.0,
                                                                          "solar": 10.0}},
        "assets": {
            "lines": [{"id": "a", "loading_pct": [0.0, 0.0], "outaged": True}],
            "transformers": [{"id": "a", "loading_pct": [90.0], "outaged": False}],
            "links": [{"id": "k", "p_nom_mw": 50.0, "flow_mw": [50.0], "outaged": False}],
        },
    }
    assert branch_max_loading(base)[("link", "k")]["max_loading_pct"] == 50.0
    out = compare_results(base, scen)
    m = {r["metric"]: r for r in out["metrics"]}
    assert m["total_load_mwh"]["delta"] == 80.0 and m["total_load_mwh"]["unit"] == "MWh"
    assert m["total_load_mwh"]["delta_pct"] == pytest.approx(20.0)
    carriers = {r["carrier"]: r for r in out["carriers"]["generation_by_carrier_mwh"]}
    assert carriers["gas"]["delta"] == 60.0
    assert carriers["wind"]["scenario"] is None and carriers["wind"]["delta"] is None
    assert carriers["solar"]["baseline"] is None
    branches = {(b["component"], b["id"]): b for b in out["branch_loading"]}
    assert branches[("line", "a")]["delta_pct_points"] == -60.0
    assert branches[("line", "a")]["scenario_outaged"] is True
    assert branches[("transformer", "a")]["delta_pct_points"] == 60.0
    assert branches[("link", "k")]["delta_pct_points"] == 50.0
    # ordered by |delta| desc
    assert [abs(b["delta_pct_points"]) for b in out["branch_loading"]] == [60.0, 60.0, 50.0]
    assert out["warnings"] == []
    assert compare_results({**base, "outcome": "infeasible"}, scen)["warnings"]


def test_comparison_endpoint_and_reports(client):
    base = run_job(client, scenario("cmp-base"))
    stress = run_job(client, scenario("cmp-stress", demand=1.5))
    r = client.post("/api/v1/comparisons",
                    json={"baseline_job_id": base["id"], "scenario_job_id": stress["id"]})
    assert r.status_code == 201, r.text
    comp = r.json()
    rep = comp["report"]
    assert rep["schema_version"] == "gridstorm-comparison/1.0"
    assert rep["provenance"] == "calculated" and rep["network_id"] == NETWORK_ID
    m = {row["metric"]: row for row in rep["metrics"]}
    assert m["total_load_mwh"]["baseline"] == 400.0 and m["total_load_mwh"]["scenario"] == 600.0
    assert m["total_load_mwh"]["delta"] == 200.0 and m["total_load_mwh"]["delta_pct"] == 50.0
    assert m["unserved_energy_mwh"]["delta"] == pytest.approx(160.0)
    line = next(b for b in rep["branch_loading"] if b["component"] == "line")
    assert line["delta_pct_points"] == pytest.approx(20.0)
    assert {b["component"] for b in rep["branch_loading"]} == {"line", "transformer"}
    repro = rep["reproducibility"]
    assert repro["baseline"]["scenario_hash"] == base["scenario_hash"]
    assert repro["scenario"]["result_sha256"] == stress["result_sha256"]
    assert repro["scenario"]["scenario_spec"]["events"][0]["value"] == 1.5
    assert repro["baseline"]["dataset"]["network_sha256"] is not None
    assert repro["baseline"]["dataset"]["license"]["spdx"] == "CC0-1.0"
    canon = json.dumps(rep, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert hashlib.sha256(canon.encode()).hexdigest() == comp["report_sha256"]

    assert client.get(f"/api/v1/comparisons/{comp['id']}").json()["report_sha256"] == comp[
        "report_sha256"]
    js = client.get(f"/api/v1/reports/{comp['id']}?format=json")
    assert js.status_code == 200 and js.json()["schema_version"] == "gridstorm-comparison/1.0"
    md = client.get(f"/api/v1/reports/{comp['id']}?format=md")
    assert md.status_code == 200 and md.headers["content-type"].startswith("text/markdown")
    assert "# GridStorm comparison" in md.text and base["scenario_hash"] in md.text
    assert "## Reproducibility" in md.text

    run_md = client.get(f"/api/v1/reports/{base['id']}?format=md")
    assert run_md.status_code == 200 and "# GridStorm run" in run_md.text
    run_js = client.get(f"/api/v1/reports/{base['id']}").json()
    assert run_js["schema_version"] == "gridstorm-run-report/1.0"
    assert client.get(f"/api/v1/reports/{base['id']}?format=pdf").status_code == 422
    assert client.get(f"/api/v1/reports/{uuid.uuid4()}").status_code == 404
    assert client.get(f"/api/v1/comparisons/{uuid.uuid4()}").status_code == 404


def test_comparison_requires_completed_jobs(client):
    done = run_job(client, scenario("cmp-ok"))
    failed = run_job(client, scenario("cmp-fail", assumptions=["fake:fail"]))
    r = client.post("/api/v1/comparisons",
                    json={"baseline_job_id": done["id"], "scenario_job_id": failed["id"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "job_not_completed"
    r = client.post("/api/v1/comparisons",
                    json={"baseline_job_id": done["id"], "scenario_job_id": str(uuid.uuid4())})
    assert r.status_code == 404


def test_comparison_with_private_job_is_private(client):
    pub = run_job(client, scenario("cmp-public"))
    priv = run_job(client, scenario("cmp-private", demand=1.2), headers=auth(ALICE))
    body = {"baseline_job_id": pub["id"], "scenario_job_id": priv["id"]}
    assert client.post("/api/v1/comparisons", json=body, headers=auth(BOB)).status_code == 404
    r = client.post("/api/v1/comparisons", json={**body, "visibility": "public"},
                    headers=auth(ALICE))
    assert r.status_code == 422 and r.json()["error"]["code"] == "visibility_conflict"
    r = client.post("/api/v1/comparisons", json=body, headers=auth(ALICE))
    assert r.status_code == 201 and r.json()["visibility"] == "private"
    cid = r.json()["id"]
    assert client.get(f"/api/v1/comparisons/{cid}", headers=auth(BOB)).status_code == 404
    assert client.get(f"/api/v1/reports/{cid}").status_code == 404
    assert client.get(f"/api/v1/reports/{cid}", headers=auth(ALICE)).status_code == 200


def test_precomputed_artifact_index_and_documents(client):
    page = client.get("/api/v1/artifacts").json()
    assert page["total"] == 4
    ids = {(a["engine"], a["artifact_id"]): a for a in page["items"]}
    assert ids[("pandapower", "listed-but-missing")]["available"] is False
    assert ids[("pandapower", "n1-tiny")]["description"] == "n1-tiny description"
    only = client.get("/api/v1/artifacts?engine=pypsa&kind=simulation").json()
    assert [a["artifact_id"] for a in only["items"]] == ["preset-base-result"]
    assert client.get(f"/api/v1/artifacts?network_id={NETWORK_ID}&limit=1").json()["total"] == 4
    assert client.get("/api/v1/artifacts?network_id=other").json()["total"] == 0

    r = client.get("/api/v1/artifacts/pandapower/n1-tiny")
    assert r.status_code == 200 and r.headers["x-gridstorm-payload-verified"] == "true"
    doc = r.json()
    assert doc["artifact"]["execution_mode"] == "precomputed"
    assert client.get("/api/v1/artifacts/pandapower/tampered").headers[
        "x-gridstorm-payload-verified"] == "false"
    assert client.get("/api/v1/artifacts/pandapower/listed-but-missing").status_code == 404
    assert client.get("/api/v1/artifacts/pandapower/..%2Fsecrets").status_code == 404
    assert client.get("/api/v1/artifacts/nope/n1-tiny").status_code == 404
