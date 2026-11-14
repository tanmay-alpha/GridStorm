"""Shared fixtures: a synthetic network catalog, presets, precomputed artifacts, app factory.

The synthetic network ``tiny-net`` is a hand-written test fixture (not a real grid). Its
``network.nc`` is placeholder bytes: live jobs in these tests run ``tests/fake_engine.py``.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient

from gridstorm_api.config import Settings
from gridstorm_api.main import create_app

HERE = Path(__file__).resolve().parent
FAKE_ENGINE = (HERE / "fake_engine.py").as_posix()
JWT_SECRET = "test-only-secret-not-used-anywhere-else-0123456789"
NETWORK_ID = "tiny-net"

CANONICAL: dict[str, Any] = {
    "schema_version": "canonical-grid/1.0",
    "network_id": NETWORK_ID,
    "name": "Tiny synthetic test network",
    "coordinate_kind": "schematic",
    "crs": None,
    "snapshots": {
        "count": 4,
        "start": "2020-01-01T00:00:00",
        "end": "2020-01-01T03:00:00",
        "resolution_h": 1.0,
    },
    "buses": [
        {
            "id": "b0",
            "name": "b0",
            "x": 0.0,
            "y": 0.0,
            "v_nom_kv": 380.0,
            "carrier": "AC",
            "country": "DE",
        },
        {
            "id": "b1",
            "name": "b1",
            "x": 1.0,
            "y": 0.5,
            "v_nom_kv": 380.0,
            "carrier": "AC",
            "country": "DE",
        },
        {
            "id": "b2",
            "name": "b2",
            "x": 2.0,
            "y": 0.0,
            "v_nom_kv": 220.0,
            "carrier": "AC",
            "country": "FR",
        },
    ],
    "lines": [
        {
            "id": "l0",
            "bus0": "b0",
            "bus1": "b1",
            "v_nom_kv": 380.0,
            "s_nom_mva": 200.0,
            "x_ohm": 10.0,
            "r_ohm": 1.0,
            "length_km": 50.0,
            "num_parallel": 1,
            "carrier": "AC",
        },
    ],
    "transformers": [
        {
            "id": "l0",
            "bus0": "b1",
            "bus1": "b2",
            "s_nom_mva": 100.0,
            "x_pu": 0.1,
            "r_pu": 0.01,
            "tap_ratio": 1.0,
        },
    ],
    "links": [],
    "generators": [
        {
            "id": "g-gas",
            "bus": "b0",
            "carrier": "gas",
            "p_nom_mw": 80.0,
            "marginal_cost_eur_per_mwh": 50.0,
            "p_nom_extendable": False,
            "is_variable": False,
        },
        {
            "id": "g-wind",
            "bus": "b1",
            "carrier": "wind",
            "p_nom_mw": 60.0,
            "marginal_cost_eur_per_mwh": 0.0,
            "p_nom_extendable": False,
            "is_variable": True,
        },
    ],
    "loads": [
        {"id": "ld2", "bus": "b2", "p_peak_mw": 100.0, "p_mean_mw": 90.0, "energy_mwh": 360.0}
    ],
    "storage_units": [],
    "stores": [],
    "carriers": [
        {"id": "gas", "color": "#aa0000", "co2_emissions_t_per_mwh": 0.4, "nice_name": "Gas"},
        {"id": "wind", "color": "#00aa00", "co2_emissions_t_per_mwh": 0.0, "nice_name": "Wind"},
    ],
    "summary": {
        "counts": {"buses": 3, "lines": 1, "transformers": 1, "generators": 2, "loads": 1},
        "capacity_by_carrier_mw": {"gas": 80.0, "wind": 60.0},
        "peak_load_mw": 100.0,
        "total_load_mwh": 360.0,
    },
    "field_provenance": {"buses.x": "synthetic", "generators.p_nom_mw": "synthetic"},
    "assumptions": ["synthetic test fixture"],
}

NC_BYTES = b"placeholder network.nc for API tests\n"


def manifest() -> dict[str, Any]:
    return {
        "schema_version": "dataset-manifest/1.0",
        "network_id": NETWORK_ID,
        "name": "Tiny synthetic test network",
        "description": "Synthetic 3-bus fixture",
        "source": {
            "url": None,
            "version": "test",
            "publication_date": None,
            "upstream_commit": None,
        },
        "retrieved_at": "2026-01-01T00:00:00Z",
        "files": [
            {
                "path": "network.nc",
                "sha256": hashlib.sha256(NC_BYTES).hexdigest(),
                "bytes": len(NC_BYTES),
            }
        ],
        "license": {
            "spdx": "CC0-1.0",
            "url": None,
            "attribution": "test",
            "redistribution": "permitted",
        },
        "coverage": {"geographic": "none", "temporal": "4 h"},
        "units": {},
        "missing_value_policy": "null",
        "quality_flags": [],
        "transformations": [],
        "engines": ["pypsa"],
        "provenance_class": "synthetic",
    }


def scenario(
    sid: str = "base-case",
    *,
    demand: float | None = None,
    assumptions: list[str] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "schema_version": "stormspec/1.0",
        "id": sid,
        "name": sid.replace("-", " ").title(),
        "description": "test scenario",
        "dataset": {"network_id": NETWORK_ID, "sha256": None},
        "horizon": {"start": 0, "snapshots": 4},
        "events": [] if demand is None else [{"type": "demand_multiplier", "value": demand}],
        "execution": {
            "engine": "pypsa",
            "formulation": "lopf",
            "solver": "highs",
            "solver_options": {"time_limit_s": 60, "threads": 1},
        },
        "assumptions": assumptions or [],
    }
    spec.update(overrides)
    return spec


def canonical_sha256(obj: Any) -> str:
    data = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def write_data(root: Path) -> Path:
    data = root / "data"
    net = data / "networks" / NETWORK_ID
    net.mkdir(parents=True)
    (data / "networks" / "catalog.json").write_text(
        json.dumps(
            {
                "schema_version": "network-catalog/1.0",
                "networks": [
                    {"id": NETWORK_ID, "path": NETWORK_ID},
                    {"id": "broken-net", "path": "x"},
                ],
            }
        )
    )
    (net / "canonical.json").write_text(json.dumps(CANONICAL))
    (net / "manifest.json").write_text(json.dumps(manifest()))
    (net / "network.nc").write_bytes(NC_BYTES)

    import stormspec

    preset_hash = stormspec.scenario_hash(
        stormspec.Scenario.model_validate(scenario("preset-base"))
    )
    art = data / "artifacts"
    (art / "pypsa").mkdir(parents=True)
    (art / "pandapower").mkdir(parents=True)
    payload = _precomputed_result(preset_hash)
    _write_artifact(art / "pypsa", "preset-base-result", "simulation", "pypsa", payload)
    _write_artifact(
        art / "pandapower",
        "n1-tiny",
        "n_minus_1",
        "pandapower",
        {"contingencies": [{"line": "l0", "max_loading_pct": 87.5}]},
    )
    _write_artifact(
        art / "pandapower",
        "tampered",
        "n_minus_1",
        "pandapower",
        {"contingencies": []},
        tamper=True,
    )
    for d, ids in (
        (art / "pypsa", [("preset-base-result", "simulation")]),
        (
            art / "pandapower",
            [
                ("n1-tiny", "n_minus_1"),
                ("tampered", "n_minus_1"),
                ("listed-but-missing", "n_minus_1"),
            ],
        ),
    ):
        (d / "index.json").write_text(
            json.dumps(
                {
                    "artifacts": [
                        {
                            "artifact_id": a,
                            "kind": k,
                            "network_id": NETWORK_ID,
                            "title": a,
                            "description": f"{a} description",
                        }
                        for a, k in ids
                    ]
                }
            )
        )

    presets = root / "presets"
    presets.mkdir()
    (presets / "preset-base.json").write_text(json.dumps(scenario("preset-base")))
    (presets / "preset-stress.json").write_text(json.dumps(scenario("preset-stress", demand=1.3)))
    bad = scenario("preset-bad", events=[{"type": "generator_outage", "asset_id": "nope"}])
    (presets / "preset-bad.json").write_text(json.dumps(bad))
    return data


def _precomputed_result(scenario_hash: str) -> dict[str, Any]:
    return {
        "schema_version": "gridstorm-result/1.0",
        "scenario_id": "preset-base",
        "scenario_hash": scenario_hash,
        "network_id": NETWORK_ID,
        "engine": {"name": "pypsa", "version": "1.4.0", "formulation": "lopf"},
        "solver": {
            "name": "highs",
            "version": "1.16.0",
            "status": "ok",
            "termination_condition": "optimal",
            "objective_eur": 1.0,
            "wall_time_s": 0.1,
        },
        "outcome": "feasible",
        "snapshots": [],
        "snapshot_weightings_h": [],
        "metrics": {"total_load_mwh": 400.0, "unserved_energy_mwh": 0.0},
        "series": {},
        "assets": {},
        "assumptions": ["precomputed"],
        "warnings": [],
        "manifest": {},
    }


def _write_artifact(
    d: Path,
    artifact_id: str,
    kind: str,
    engine: str,
    payload: dict[str, Any],
    *,
    tamper: bool = False,
) -> None:
    header = {
        "schema_version": "gridstorm-artifact/1.0",
        "artifact_id": artifact_id,
        "kind": kind,
        "engine": engine,
        "engine_version": "test",
        "network_id": NETWORK_ID,
        "created_at": "2026-01-01T00:00:00Z",
        "command": "test",
        "inputs": [],
        "platform": "test",
        "execution_mode": "precomputed",
        "payload_sha256": canonical_sha256(payload) if not tamper else "0" * 64,
    }
    (d / f"{artifact_id}.json").write_text(json.dumps({"artifact": header, "payload": payload}))


def make_token(
    sub: uuid.UUID | str,
    *,
    secret: str = JWT_SECRET,
    expires_in: float = 3600,
    aud: str = "authenticated",
) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": str(sub),
        "aud": aud,
        "role": "authenticated",
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    return jwt.encode(claims, secret, algorithm="HS256")


def auth(user: uuid.UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(user)}"}


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    write_data(tmp_path)
    return tmp_path


@pytest.fixture
def settings_factory(workspace: Path) -> Callable[..., Settings]:
    def make(**overrides: Any) -> Settings:
        values: dict[str, Any] = {
            "data_dir": workspace / "data",
            "state_dir": workspace / "state",
            "presets_dir": workspace / "presets",
            "cors_origins": ["http://localhost:5173"],
            "live_networks": {NETWORK_ID, "ac-dc-meshed"},
            "engine_cmd": f'{{python}} "{FAKE_ENGINE}" run --scenario {{scenario}} '
            "--network-dir {network_dir} --out {out}",
            "python_executable": sys.executable,
            "rate_limit_post_per_min": 100_000.0,
            "rate_limit_post_burst": 100_000,
            "rate_limit_sim_per_min": 100_000.0,
            "rate_limit_sim_burst": 100_000,
            "job_timeout_s": 60.0,
            "job_poll_s": 0.05,
            "job_heartbeat_s": 0.5,
            "supabase_jwt_secret": JWT_SECRET,
        }
        values.update(overrides)
        return Settings(**values)

    return make


@pytest.fixture
def client_factory(
    settings_factory: Callable[..., Settings],
) -> Iterator[Callable[..., TestClient]]:
    clients: list[TestClient] = []

    def make(**overrides: Any) -> TestClient:
        client = TestClient(create_app(settings_factory(**overrides)))
        client.__enter__()
        clients.append(client)
        return client

    yield make
    for c in reversed(clients):
        c.__exit__(None, None, None)


@pytest.fixture
def client(client_factory: Callable[..., TestClient]) -> TestClient:
    return client_factory()


TERMINAL = {"completed", "failed", "cancelled", "timeout"}


def wait_job(
    client: TestClient,
    job_id: str,
    *,
    timeout: float = 60.0,
    until: Callable[[dict[str, Any]], bool] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    until = until or (lambda j: j["status"] in TERMINAL)
    deadline = time.monotonic() + timeout
    while True:
        job = client.get(f"/api/v1/simulations/{job_id}", headers=headers).json()
        if until(job):
            return job
        if time.monotonic() > deadline:
            raise AssertionError(f"job {job_id} did not reach the expected state: {job}")
        time.sleep(0.1)


def run_job(client: TestClient, spec: dict[str, Any], **kw: Any) -> dict[str, Any]:
    headers = kw.pop("headers", None)
    r = client.post("/api/v1/simulations", json={"scenario": spec, **kw}, headers=headers)
    assert r.status_code == 202, r.text
    return wait_job(client, r.json()["id"], headers=headers)
