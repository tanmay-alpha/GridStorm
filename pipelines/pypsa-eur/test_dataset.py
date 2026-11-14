"""Validate the imported ``data/networks/pypsa-eur-be`` dataset (skipped until it exists)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"

import pypsa  # noqa: E402
import pytest  # noqa: E402

DATASET = Path(__file__).resolve().parents[2] / "data" / "networks" / "pypsa-eur-be"
NETWORK = DATASET / "network.nc"

pytestmark = pytest.mark.skipif(not NETWORK.exists(), reason="pypsa-eur-be not built")


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads((DATASET / "manifest.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def net() -> pypsa.Network:
    return pypsa.Network(NETWORK)


def test_files_match_manifest_and_size_limit(manifest: dict) -> None:
    entries = {e["path"]: e for e in manifest["files"]}
    assert set(entries) == {"canonical.json", "network.nc"}
    for path, entry in entries.items():
        data = (DATASET / path).read_bytes()
        assert entry["bytes"] == len(data)
        assert entry["sha256"] == hashlib.sha256(data).hexdigest()
    assert entries["network.nc"]["bytes"] <= 10 * 1024 * 1024
    assert manifest["source"]["upstream_commit"] == "c8209014468dbb3bf43257f45d34abc6e3c8c898"
    assert manifest["license"]["spdx"] == "ODbL-1.0"
    assert manifest["license"]["redistribution"] == "permitted"
    assert "OpenStreetMap contributors" in manifest["license"]["attribution"]
    assert "10.5281/zenodo.10820928" in manifest["license"]["attribution"]
    assert "synthetic demand, not observed 2013 load" in manifest["quality_flags"]
    steps = [t["step"] for t in manifest["transformations"]]
    assert steps == ["build", "replace_load", "import"]


def test_load_is_synthetic_replacement(net: pypsa.Network) -> None:
    import xarray as xr

    with xr.open_dataset(NETWORK) as ds:
        attrs = dict(ds.attrs)
    assert attrs["license"] == "ODbL-1.0"
    replacement = json.loads(attrs["gridstorm_load_replacement"])
    source = replacement["source"]
    assert source["sha256"] == "1c96ff5a041abbb85d6d24f880455e13a931c5cbaf0e54e3f7fc0f7644b12bc0"
    assert (source["license"], source["column"]) == ("CC-BY-4.0", "BE")
    # National daily means of the synthetic BE series (replace_load.py report, 2026-11-15).
    expected_mw = [11178.892, 10000.780, 9920.443, 10791.649, 10158.634, 9941.437, 10045.990]
    total_mw = net.get_switchable_as_dense("Load", "p_set").sum(axis=1)
    assert total_mw.to_numpy() == pytest.approx(expected_mw, abs=1e-3)
    assert float((total_mw * net.snapshot_weightings.objective).sum()) == pytest.approx(
        1_728_907.786, abs=1e-3
    )
    canonical = json.loads((DATASET / "canonical.json").read_text(encoding="utf-8"))
    for field in ("p_peak_mw", "p_mean_mw", "energy_mwh"):
        assert canonical["field_provenance"][f"loads.{field}"] == "modeled"


def test_network_is_belgian_tutorial_scope(net: pypsa.Network) -> None:
    ac = net.buses[net.buses.carrier == "AC"]
    assert len(ac) == 5
    assert set(ac.country) == {"BE"}
    # Belgium lies within roughly 2.5-6.5 E, 49.4-51.6 N (offshore zone extends north-west).
    assert ac.x.between(2.0, 6.5).all() and ac.y.between(49.4, 51.8).all()
    # 24 h averaging: every snapshot represents 24 h in the objective.
    assert (net.snapshot_weightings.objective == 24).all()


def test_load_and_renewable_profiles_are_physical(net: pypsa.Network) -> None:
    load = net.get_switchable_as_dense("Load", "p_set")
    assert (load.values > 0).all()
    total_mw = load.sum(axis=1)
    # Synthetic BE daily means span 9,920-11,179 MW over the week.
    assert total_mw.between(9_900, 11_200).all()
    p_max_pu = net.get_switchable_as_dense("Generator", "p_max_pu")
    assert ((p_max_pu.values >= 0) & (p_max_pu.values <= 1 + 1e-9)).all()


def test_canonical_counts_match_network(net: pypsa.Network) -> None:
    canonical = json.loads((DATASET / "canonical.json").read_text(encoding="utf-8"))
    assert len(canonical["buses"]) == len(net.buses)
    assert len(canonical["generators"]) == len(net.generators)
    assert canonical["snapshots"]["count"] == len(net.snapshots)


def test_lopf_solves_optimally_with_nodal_balance() -> None:
    checker = Path(__file__).with_name("solve_check.py")
    result = subprocess.run(
        [sys.executable, str(checker), "--network", str(NETWORK)],
        capture_output=True,
        text=True,
        timeout=300,
        check=True,
    )
    report = json.loads(result.stdout)
    assert (report["status"], report["termination_condition"]) == ("ok", "optimal")
    assert report["snapshots"] == 7 and report["snapshot_weight_sum_h"] == 168
    assert report["balance_residual_max_mw"] < 1e-4
    # Measured 2026-11-15 in the core env (HiGHS 1.16.0, threads=1): 49,392,841.28 EUR.
    assert report["objective_eur"] == pytest.approx(49_392_841.28, rel=1e-6)
