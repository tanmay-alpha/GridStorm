"""`view=summary` for the research kinds (benchmark, risk, episode, timeseries)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import NETWORK_ID, _write_artifact
from gridstorm_api.routers.artifacts import SUMMARY_DROP, summarize

REPO_ARTIFACTS = Path(__file__).resolve().parents[3] / "data" / "artifacts"

STORMBENCH_SUMMARY = {
    "schema_version": "stormbench-summary/1.0",
    "threshold_pct": 100.0,
    "platform": {"cpu": "x"},
    "cases": [
        {
            "case": "case14_ieee",
            "counts": {"buses": 14},
            "contingencies": [{"branch": f"b{i}", "post_loading_pct": 50.0} for i in range(400)],
        },
        {"case": "case30_ieee", "counts": {"buses": 30}, "contingencies": []},
    ],
}
RISK = {
    "schema_version": "stormrisk-study/1.0",
    "estimates": {"eens_mwh": 1.5},
    "importance": [{"asset_id": "l0", "share_of_sampled_unserved_energy": 1.0}],
    "states": [{"outaged": [f"l{i}"], "unserved_mwh": 0.1} for i in range(400)],
    "sample_state_index": list(range(400)),
}
EPISODE = {"kpis": {"survival_steps": 10}, "steps": {"rho": [[0.5] * 20] * 400}}
TIMESERIES = {"summary": {"max_vm_pu": 1.04}, "series": {"vm_pu": [[1.0] * 20] * 400}}

CASES = [
    ("stormbench", "bench-summary", "benchmark", STORMBENCH_SUMMARY),
    ("stormrisk", "risk-study", "risk", RISK),
    ("grid2op", "episode-0", "episode", EPISODE),
    ("distribution", "lv-week", "timeseries", TIMESERIES),
]


@pytest.fixture
def research_client(client_factory, workspace):
    art = workspace / "data" / "artifacts"
    for engine, artifact_id, kind, payload in CASES:
        d = art / engine
        d.mkdir(parents=True, exist_ok=True)
        _write_artifact(d, artifact_id, kind, engine, payload)
        (d / "index.json").write_text(
            json.dumps(
                {
                    "artifacts": [
                        {"artifact_id": artifact_id, "kind": kind, "network_id": NETWORK_ID}
                    ]
                }
            )
        )
    return client_factory()


@pytest.mark.parametrize(("engine", "artifact_id", "kind", "payload"), CASES)
def test_summary_view_drops_only_declared_bulky_keys(
    research_client, engine, artifact_id, kind, payload
):
    url = f"/api/v1/artifacts/{engine}/{artifact_id}"
    full = research_client.get(url)
    r = research_client.get(f"{url}?view=summary")
    assert r.status_code == 200
    assert r.headers["x-gridstorm-payload-verified"] == "true"
    assert r.headers["cache-control"] == full.headers["cache-control"]
    body = r.json()
    assert set(body) == {"artifact", "summary"}
    assert body["artifact"] == full.json()["artifact"]
    drop = SUMMARY_DROP[kind]
    summary = body["summary"]
    assert not set(drop) & set(summary)
    for k, v in payload.items():
        if k in drop:
            continue
        if k == "cases":
            assert summary["cases"] == [
                {ck: cv for ck, cv in c.items() if ck not in drop} for c in payload["cases"]
            ]
        else:
            assert summary[k] == v
    assert len(r.content) * 5 < len(full.content)
    etag = r.headers["etag"]
    assert etag != full.headers["etag"]
    again = research_client.get(f"{url}?view=summary", headers={"If-None-Match": etag})
    assert again.status_code == 304


def test_summary_view_still_rejects_n_minus_1(research_client):
    r = research_client.get("/api/v1/artifacts/pandapower/n1-tiny?view=summary")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "summary_view_unsupported"


def test_openapi_lists_summary_kinds(research_client):
    op = research_client.get("/openapi.json").json()["paths"][
        "/api/v1/artifacts/{engine}/{artifact_id}"
    ]["get"]
    for kind in ("simulation", *SUMMARY_DROP):
        assert f"`{kind}`" in op["description"]


def _committed(kind: str) -> list[Path]:
    out = []
    for index in sorted(REPO_ARTIFACTS.glob("*/index.json")):
        raw = json.loads(index.read_text(encoding="utf-8"))
        for e in raw.get("artifacts", []) if isinstance(raw, dict) else raw:
            path = index.parent / f"{e['artifact_id']}.json"
            if e.get("kind") == kind and path.is_file():
                out.append(path)
    return out


@pytest.mark.parametrize("kind", sorted(SUMMARY_DROP))
def test_committed_artifacts_summaries_are_verbatim_subsets(kind):
    paths = _committed(kind)
    assert paths, f"no committed {kind} artifacts"
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))["payload"]
        summary = summarize(kind, payload)
        for k, v in summary.items():
            if k == "cases":
                for got, src in zip(v, payload["cases"], strict=True):
                    assert all(src[ck] == cv for ck, cv in got.items())
            else:
                assert payload[k] == v
        assert len(json.dumps(summary)) <= len(json.dumps(payload))


def test_index_include_header_returns_file_headers(client):
    plain = client.get("/api/v1/artifacts?engine=pandapower").json()
    assert all("header" not in i for i in plain["items"])
    page = client.get("/api/v1/artifacts?engine=pandapower&include=header").json()
    by_id = {i["artifact_id"]: i for i in page["items"]}
    full = client.get("/api/v1/artifacts/pandapower/n1-tiny").json()
    assert by_id["n1-tiny"]["header"] == full["artifact"]
    assert by_id["listed-but-missing"]["header"] is None
    # the header is reported as written even when the payload does not match it
    assert by_id["tampered"]["header"]["payload_sha256"] == "0" * 64
    paged = client.get("/api/v1/artifacts?include=header&limit=1&offset=1").json()
    assert paged["total"] == client.get("/api/v1/artifacts").json()["total"]
    assert len(paged["items"]) == 1
    assert "header" in paged["items"][0]
    assert client.get("/api/v1/artifacts?include=payload").status_code == 422


def test_header_falls_back_to_full_parse_when_payload_comes_first(client_factory, workspace):
    d = workspace / "data" / "artifacts" / "pandapower"
    header = {"artifact_id": "n1-tiny", "kind": "n_minus_1", "engine": "pandapower"}
    (d / "n1-tiny.json").write_text(json.dumps({"payload": {"x": 1}, "artifact": header}))
    page = client_factory().get("/api/v1/artifacts?engine=pandapower&include=header").json()
    assert next(i for i in page["items"] if i["artifact_id"] == "n1-tiny")["header"] == header


def test_committed_headers_match_full_documents():
    from gridstorm_api.precomputed import PrecomputedArtifacts

    store = PrecomputedArtifacts(REPO_ARTIFACTS)
    items = [i for i in store.index() if i["available"]]
    assert len(items) > 40
    for i in items:
        path = REPO_ARTIFACTS / i["engine"] / f"{i['artifact_id']}.json"
        expected = json.loads(path.read_text(encoding="utf-8"))["artifact"]
        assert store.header(i["engine"], i["artifact_id"]) == expected


def test_committed_pypsa_index_rows_match_their_payloads():
    """The web reads preset KPIs from index rows; they must equal the documents they index."""
    index = json.loads((REPO_ARTIFACTS / "pypsa" / "index.json").read_text(encoding="utf-8"))
    for row in index["artifacts"]:
        doc = json.loads(
            (REPO_ARTIFACTS / "pypsa" / f"{row['artifact_id']}.json").read_text(encoding="utf-8")
        )
        payload = doc["payload"]
        assert row["outcome"] == payload["outcome"]
        assert row["objective_eur"] == payload["solver"]["objective_eur"]
        assert row["unserved_energy_mwh"] == payload["metrics"]["unserved_energy_mwh"]
        assert row["payload_sha256"] == doc["artifact"]["payload_sha256"]
        assert row["measurements"] == doc["artifact"]["measurements"]
