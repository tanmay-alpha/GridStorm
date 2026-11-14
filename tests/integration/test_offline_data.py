"""Offline checks of committed datasets, presets and precomputed artifacts (contracts §2, §3, §5).

Independent of every GridStorm package: only stdlib + PyYAML. Run from tests/integration:
``uv run pytest -q test_offline_data.py``.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pytest
import yaml

from conftest import REPO_ROOT
from gs_helpers import PROVENANCE, canonical_sha256

NETWORKS = REPO_ROOT / "data" / "networks"
ARTIFACTS = REPO_ROOT / "data" / "artifacts"
PRESETS = REPO_ROOT / "packages" / "stormspec" / "presets"
UNIT_SUFFIXES = (
    "_mw",
    "_mwh",
    "_mva",
    "_kv",
    "_pct",
    "_eur",
    "_eur_per_mwh",
    "_h",
    "_s",
    "_t",
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _catalog() -> list[dict]:
    path = NETWORKS / "catalog.json"
    if not path.exists():
        return []
    cat = json.loads(path.read_text(encoding="utf-8"))
    assert cat["schema_version"] == "network-catalog/1.0"
    return cat["networks"]


def _canonical(network_id: str) -> dict:
    for n in _catalog():
        if n["id"] == network_id:
            return json.loads((NETWORKS / n["path"] / "canonical.json").read_text("utf-8"))
    raise KeyError(network_id)


def _artifact_files() -> list[Path]:
    if not ARTIFACTS.exists():
        return []
    return sorted(p for p in ARTIFACTS.glob("*/*.json") if p.name != "index.json")


def _no_nonfinite(obj, where: str) -> None:
    if isinstance(obj, float):
        assert math.isfinite(obj), where
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _no_nonfinite(v, f"{where}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _no_nonfinite(v, f"{where}[{i}]")


# ----------------------------------------------------------------------------------- networks


@pytest.mark.parametrize("entry", _catalog(), ids=lambda e: e["id"])
def test_dataset_files_match_manifest(entry: dict) -> None:
    d = NETWORKS / entry["path"]
    manifest = json.loads((d / "manifest.json").read_text("utf-8"))
    assert manifest["schema_version"] == "dataset-manifest/1.0"
    assert manifest["network_id"] == entry["id"]
    assert manifest["provenance_class"] in PROVENANCE
    assert manifest["license"]["spdx"] and manifest["license"]["url"]
    assert manifest["source"]["url"].startswith("http")
    for f in manifest["files"]:
        p = d / f["path"]
        assert p.exists(), p
        assert _sha256(p) == f["sha256"], f"{p}: sha256 mismatch with manifest"
        assert p.stat().st_size == f["bytes"], p
    nc = d / "network.nc"
    if nc.exists():
        assert nc.stat().st_size <= 10 * 1024 * 1024, "network.nc > 10 MB committed"


@pytest.mark.parametrize("entry", _catalog(), ids=lambda e: e["id"])
def test_canonical_consistency(entry: dict) -> None:
    net = _canonical(entry["id"])
    assert net["schema_version"] == "canonical-grid/1.0"
    assert net["network_id"] == entry["id"]
    _no_nonfinite(net, entry["id"])
    buses = {b["id"] for b in net["buses"]}
    for comp in ("lines", "transformers", "links"):
        for row in net[comp]:
            assert row["bus0"] in buses and row["bus1"] in buses, (comp, row["id"])
    for comp in ("generators", "loads", "storage_units", "stores"):
        for row in net[comp]:
            assert row["bus"] in buses, (comp, row["id"])
    for comp, n in net["summary"]["counts"].items():
        assert len(net[comp]) == n, comp
    if net["coordinate_kind"] == "geographic":
        assert net["crs"] == "EPSG:4326"
        for b in net["buses"]:
            if b["x"] is not None:
                assert -180 <= b["x"] <= 180 and -90 <= b["y"] <= 90, b
    else:
        assert net["crs"] is None
    # Capacity by carrier recomputed from generator rows.
    cap: dict[str, float] = {}
    for g in net["generators"]:
        if g["p_nom_mw"] is not None:
            cap[g["carrier"]] = cap.get(g["carrier"], 0.0) + g["p_nom_mw"]
    for carrier, mw in net["summary"]["capacity_by_carrier_mw"].items():
        assert mw == pytest.approx(cap.get(carrier, 0.0), rel=1e-6, abs=1e-6), carrier
    for key, prov in net["field_provenance"].items():
        assert prov in PROVENANCE, key
    assert net["assumptions"], "canonical network lists no assumptions"


# ------------------------------------------------------------------------------------ presets


def _presets() -> list[Path]:
    if not PRESETS.exists():
        return []
    return sorted([*PRESETS.glob("*.yaml"), *PRESETS.glob("*.yml"), *PRESETS.glob("*.json")])


@pytest.mark.parametrize("path", _presets(), ids=lambda p: p.name)
def test_presets_reference_real_assets(path: Path) -> None:
    spec = yaml.safe_load(path.read_text("utf-8"))
    net = _canonical(spec["dataset"]["network_id"])
    kinds = {
        "line_outage": ("lines", "transformers"),
        "link_outage": ("links",),
        "generator_outage": ("generators",),
        "storage_state": ("storage_units",),
    }
    for ev in spec.get("events", []):
        if ev["type"] in kinds:
            ids = {r["id"] for c in kinds[ev["type"]] for r in net[c]}
            assert ev["asset_id"] in ids, (path.name, ev)
        if ev["type"] == "renewable_availability_multiplier":
            assert ev["carrier"] in {g["carrier"] for g in net["generators"]}, ev
        if ev["type"] == "demand_multiplier" and ev.get("buses"):
            assert set(ev["buses"]) <= {ld["bus"] for ld in net["loads"]}, ev
    h = spec["horizon"]
    assert h.get("start", 0) + h["snapshots"] <= net["snapshots"]["count"]
    if spec["dataset"].get("sha256"):
        manifest = json.loads(
            (NETWORKS / spec["dataset"]["network_id"] / "manifest.json").read_text("utf-8")
        )
        shas = {f["sha256"] for f in manifest["files"] if f["path"].endswith(".nc")}
        assert spec["dataset"]["sha256"] in shas, "preset pins a sha256 that is not the dataset"


# ---------------------------------------------------------------------------------- artifacts


def test_artifact_indexes_match_files() -> None:
    for idx_path in sorted(ARTIFACTS.glob("*/index.json")) if ARTIFACTS.exists() else []:
        idx = json.loads(idx_path.read_text("utf-8"))
        entries = idx["artifacts"] if isinstance(idx, dict) else idx
        listed = {e["artifact_id"] for e in entries}
        on_disk = {p.stem for p in idx_path.parent.glob("*.json") if p.name != "index.json"}
        assert listed == on_disk, (idx_path, sorted(listed ^ on_disk))
        for e in entries:
            assert {"artifact_id", "kind", "network_id", "title"} <= set(e), e


@pytest.mark.parametrize("path", _artifact_files(), ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_artifact_header_and_payload_hash(path: Path) -> None:
    assert path.stat().st_size < 5 * 1024 * 1024, "artifact > 5 MB"
    art = json.loads(path.read_text("utf-8"))
    hdr = art["artifact"]
    assert hdr["schema_version"] == "gridstorm-artifact/1.0"
    assert hdr["artifact_id"] == path.stem
    assert hdr["engine"] == path.parent.name or path.parent.name in hdr["engine"]
    assert hdr["execution_mode"] == "precomputed"
    assert hdr["command"], "artifact does not record the command that produced it"
    assert canonical_sha256(art["payload"]) == hdr["payload_sha256"], "payload_sha256 mismatch"
    for inp in hdr["inputs"]:
        p = REPO_ROOT / inp["path"]
        if p.exists() and p.is_file():
            assert _sha256(p) == inp["sha256"], f"input {inp['path']} changed since the run"
    _no_nonfinite(art["payload"], path.stem)


def _simulation_results() -> list[tuple[str, dict]]:
    out = []
    for p in _artifact_files():
        art = json.loads(p.read_text("utf-8"))
        payload = art["payload"]
        if isinstance(payload, dict) and payload.get("schema_version") == "gridstorm-result/1.0":
            out.append((p.stem, payload))
        elif isinstance(payload, dict) and isinstance(payload.get("result"), dict):
            if payload["result"].get("schema_version") == "gridstorm-result/1.0":
                out.append((p.stem, payload["result"]))
    return out


@pytest.mark.parametrize("name_result", _simulation_results(), ids=lambda t: t[0])
def test_precomputed_pypsa_result_physics(name_result: tuple[str, dict]) -> None:
    """Recompute E_unserved = Σ shed·Δt, energy totals, generator limits, balance residual."""
    _, r = name_result
    manifest = r["manifest"]
    body = {k: v for k, v in r.items() if k != "manifest"}
    assert manifest["result_sha256"] == canonical_sha256(body), "result_sha256 mismatch"
    assert manifest["scenario_hash"] == r["scenario_hash"]
    if r["outcome"] != "feasible":
        assert not r["series"].get("load_mw"), "non-feasible result carries series"
        return
    w = r["snapshot_weightings_h"]
    s, m = r["series"], r["metrics"]
    unserved = sum(p * dt for p, dt in zip(s["load_shed_mw"], w, strict=True))
    total = sum(p * dt for p, dt in zip(s["load_mw"], w, strict=True))
    # Artifacts may round floats to ~4 significant digits (contract §5).
    assert m["unserved_energy_mwh"] == pytest.approx(unserved, rel=2e-3, abs=1e-2)
    assert m["total_load_mwh"] == pytest.approx(total, rel=2e-3, abs=1e-2)
    assert m["served_load_mwh"] + m["unserved_energy_mwh"] == pytest.approx(
        m["total_load_mwh"], rel=2e-3, abs=1e-2
    )
    assert abs(m["balance_residual_max_mw"]) < 1e-3
    for g in r["assets"]["generators"]:
        for p, a in zip(g["p_mw"], g["available_mw"], strict=True):
            assert p <= a * (1 + 2e-3) + 1e-3, (g["id"], p, a)
            assert p >= -1e-3, (g["id"], p)
        if g["outaged"]:
            assert max(abs(x) for x in g["p_mw"]) <= 1e-3, g["id"]
    for ln in r["assets"]["lines"]:
        if ln["outaged"]:
            assert max(abs(x) for x in ln["flow_mw"]) <= 1e-3, ln["id"]
    assert all(c >= -1e-3 for c in s.get("curtailment_mw", [])), "negative curtailment"
    net = _canonical(r["network_id"])
    su = {u["id"]: u for u in net["storage_units"]}
    for st in r["assets"]["storage_units"]:
        u = su[st["id"]]
        e_max = (u["p_nom_mw"] or 0.0) * (u["max_hours"] or 0.0)
        for soc in st["soc_mwh"]:
            assert -1e-3 <= soc <= e_max * (1 + 2e-3) + 1e-3, (st["id"], soc, e_max)
        for p in st["p_mw"]:
            assert abs(p) <= (u["p_nom_mw"] or 0.0) * (1 + 2e-3) + 1e-3, (st["id"], p)
    for k, v in m.items():
        if isinstance(v, (int, float)) and k not in ("congested_line_count",):
            assert k.endswith(UNIT_SUFFIXES) or k.endswith("_hours") or k.endswith("_count"), (
                f"metric {k!r} has no unit suffix"
            )
