"""Scenario listing, validation and persistence (contract §3, §6)."""

from __future__ import annotations

import copy

import httpx
import pytest

from gs_helpers import assert_error, canonical_sha256

HASH_EXCLUDE = {"name", "description"}


def _spec(rec: dict, new_id: str) -> dict:
    spec = copy.deepcopy(rec["spec"])
    spec["id"] = new_id
    return spec


def test_presets_listed_with_hash(scenarios: list[dict]) -> None:
    presets = [s for s in scenarios if s.get("preset")]
    assert len(presets) >= 1, "no presets exposed"
    for rec in presets:
        assert {"id", "hash", "spec", "preset", "created_at"} <= set(rec), sorted(rec)
        assert len(rec["hash"]) == 64
        assert rec["spec"]["schema_version"] == "stormspec/1.0"


def test_preset_hash_is_canonical(scenarios: list[dict]) -> None:
    """Server hash == sha256(canonical JSON of the fully defaulted spec minus name/description).

    Only meaningful when the server returns the fully-defaulted spec; this re-derives the hash
    independently of the stormspec package.
    """
    for rec in (s for s in scenarios if s.get("preset")):
        spec = {k: v for k, v in rec["spec"].items() if k not in HASH_EXCLUDE}
        assert canonical_sha256(spec) == rec["hash"], rec["id"]


def test_get_scenario_by_id(client: httpx.Client, acdc_preset: dict) -> None:
    r = client.get(f"/api/v1/scenarios/{acdc_preset['id']}")
    assert r.status_code == 200, r.text
    assert r.json()["hash"] == acdc_preset["hash"]


def test_get_unknown_scenario(client: httpx.Client) -> None:
    assert_error(client.get("/api/v1/scenarios/does-not-exist-000"), 404)


def test_validate_preset_valid(client: httpx.Client, acdc_preset: dict) -> None:
    r = client.post("/api/v1/scenarios/validate", json=acdc_preset["spec"])
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["valid"] is True, rep
    assert rep["errors"] == []


def test_validate_unknown_asset(client: httpx.Client, acdc_preset: dict, unique_id: str) -> None:
    spec = _spec(acdc_preset, unique_id)
    spec["events"] = [{"type": "line_outage", "asset_id": "no-such-line-xyz"}]
    r = client.post("/api/v1/scenarios/validate", json=spec)
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["valid"] is False
    assert any(e["code"] == "unknown_asset" for e in rep["errors"]), rep


def test_validate_rejects_partial_window_line_outage(
    client: httpx.Client, acdc_preset: dict, unique_id: str
) -> None:
    """PyPSA cannot represent a partial-horizon line outage: must be rejected, not approximated."""
    lines = client.get(
        "/api/v1/networks/ac-dc-meshed/assets", params={"type": "lines", "limit": 1}
    ).json()["items"]
    spec = _spec(acdc_preset, unique_id)
    h = spec["horizon"]
    assert h["snapshots"] >= 2, "preset horizon too short for a partial window"
    spec["events"] = [
        {
            "type": "line_outage",
            "asset_id": lines[0]["id"],
            "window": {"start": h["start"], "end": h["start"] + 1},
        }
    ]
    rep = client.post("/api/v1/scenarios/validate", json=spec).json()
    assert rep["valid"] is False
    assert any(e["code"] == "unsupported_operation" for e in rep["errors"]), rep


def test_validate_horizon_out_of_range(
    client: httpx.Client, acdc_preset: dict, unique_id: str
) -> None:
    spec = _spec(acdc_preset, unique_id)
    spec["horizon"] = {"start": 0, "snapshots": 8784}
    rep = client.post("/api/v1/scenarios/validate", json=spec).json()
    assert rep["valid"] is False
    assert any(e["code"] == "horizon_out_of_range" for e in rep["errors"]), rep


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s.update(schema_version="stormspec/9.9"),
        lambda s: s.update(id="BAD ID"),
        lambda s: s.update(unexpected_field=1),
        lambda s: s["events"].append({"type": "meteor_strike"}),
        lambda s: s["events"].append({"type": "demand_multiplier", "value": -1}),
        lambda s: s["execution"].update(engine="matlab"),
    ],
)
def test_validate_schema_errors_are_reported(
    client: httpx.Client, acdc_preset: dict, unique_id: str, mutate
) -> None:
    spec = _spec(acdc_preset, unique_id)
    mutate(spec)
    r = client.post("/api/v1/scenarios/validate", json=spec)
    if r.status_code == 200:
        rep = r.json()
        assert rep["valid"] is False and rep["errors"], rep
    else:
        assert_error(r, 422)


@pytest.mark.parametrize(
    "body", [b"not json", b"[]", b'"string"', b"{" * 5000], ids=["text", "list", "str", "deep"]
)
def test_validate_garbage_body(client: httpx.Client, body: bytes) -> None:
    r = client.post(
        "/api/v1/scenarios/validate", content=body, headers={"content-type": "application/json"}
    )
    assert r.status_code < 500, r.text
    if r.status_code != 200:
        assert_error(r, {400, 413, 422})
    else:
        assert r.json()["valid"] is False


def test_save_scenario_roundtrip(client: httpx.Client, acdc_preset: dict, unique_id: str) -> None:
    spec = _spec(acdc_preset, unique_id)
    spec["name"] = "Integration test copy"
    r = client.post("/api/v1/scenarios", json=spec)
    assert r.status_code in (200, 201), r.text
    rec = r.json()
    assert {"id", "hash", "spec", "preset", "owner_id", "created_at"} <= set(rec), sorted(rec)
    assert rec["preset"] is False
    got = client.get(f"/api/v1/scenarios/{rec['id']}")
    assert got.status_code == 200, got.text
    assert got.json()["hash"] == rec["hash"]
    # Name is excluded from the hash; id is part of it.
    spec2 = dict(spec, name="Different wording")
    rep = client.post("/api/v1/scenarios/validate", json=spec2)
    assert rep.status_code == 200


def test_save_invalid_scenario_rejected(
    client: httpx.Client, acdc_preset: dict, unique_id: str
) -> None:
    spec = _spec(acdc_preset, unique_id)
    spec["events"] = [{"type": "generator_outage", "asset_id": "no-such-generator"}]
    err = assert_error(client.post("/api/v1/scenarios", json=spec), {400, 422})
    assert "unknown_asset" in str(err), err
    assert client.get(f"/api/v1/scenarios/{unique_id}").status_code == 404
