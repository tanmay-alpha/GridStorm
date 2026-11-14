import json
import shutil

import numpy as np
import pandas as pd
import pypsa
import pytest
from canonical_grid import load_canonical, load_catalog, load_manifest

from network_import.canonical import from_pypsa
from network_import.manifest import export_netcdf
from network_import.paths import networks_dir
from network_import.validate import validate_all, validate_dataset

REQUIRED = ["ac-dc-meshed", "scigrid-de", "pglib-case14-ieee", "pglib-case118-ieee"]


def _toy() -> pypsa.Network:
    n = pypsa.Network()
    n.set_snapshots(pd.date_range("2020-01-01", periods=3, freq="h"))
    n.add("Bus", ["a", "b"], v_nom=110.0, x=[0.0, 1.0], y=[0.0, 1.0])
    n.add("Line", "1", bus0="a", bus1="b", x=10.0, r=1.0, s_nom=100.0)
    n.add("Transformer", "1", bus0="a", bus1="b", x=0.1, s_nom=50.0)
    n.add(
        "Generator",
        "g",
        bus="a",
        p_nom=80.0,
        p_max_pu=pd.Series([1.0, 0.5, 0.2], index=n.snapshots),
    )
    # n.add replaces NaN attributes with defaults; inject missing source data explicitly.
    n.c.generators.static.loc["g", "marginal_cost"] = np.nan
    n.add("Load", "l", bus="b", p_set=pd.Series([10.0, 30.0, 20.0], index=n.snapshots))
    return n


def test_from_pypsa_values_nulls_and_provenance():
    cn = from_pypsa(
        _toy(),
        "toy-net",
        "Toy",
        null_fields=["lines.length_km"],
        field_provenance={"buses.x": "observed"},
    )
    assert cn.crs == "EPSG:4326" and cn.snapshots.count == 3 and cn.snapshots.resolution_h == 1.0
    assert [r.id for r in cn.lines] == ["1"] and [r.id for r in cn.transformers] == ["1"]
    assert cn.lines[0].length_km is None and cn.lines[0].x_ohm == 10.0
    g = cn.generators[0]
    assert g.marginal_cost_eur_per_mwh is None  # NaN -> null, never invented
    assert g.is_variable is True
    ld = cn.loads[0]
    assert (ld.p_peak_mw, ld.p_mean_mw, ld.energy_mwh) == (30.0, 20.0, 60.0)
    assert cn.summary.peak_load_mw == 30.0 and cn.summary.total_load_mwh == 60.0
    assert cn.field_provenance["buses.x"] == "observed"
    assert cn.field_provenance["loads.p_peak_mw"] == "calculated"
    assert "lines.length_km" not in cn.field_provenance


def test_from_pypsa_schematic_requires_null_crs():
    with pytest.raises(ValueError):
        from_pypsa(_toy(), "toy-net", "Toy", coordinate_kind="schematic", crs="EPSG:4326")
    cn = from_pypsa(_toy(), "toy-net", "Toy", coordinate_kind="schematic")
    assert cn.crs is None


def test_from_pypsa_does_not_mutate_input():
    n = _toy()
    before = n.c.lines.static.copy()
    from_pypsa(n, "toy-net", "Toy")
    pd.testing.assert_frame_equal(n.c.lines.static, before)


def test_catalog_lists_required_networks():
    cat = load_catalog(networks_dir() / "catalog.json")
    ids = [e.id for e in cat.networks]
    for nid in REQUIRED:
        assert nid in ids


@pytest.mark.parametrize("nid", REQUIRED)
def test_dataset_files_validate(nid):
    d = networks_dir() / nid
    cn = load_canonical(d / "canonical.json")
    mf = load_manifest(d / "manifest.json")
    assert cn.network_id == mf.network_id == nid
    assert mf.license.spdx == "CC-BY-4.0" and mf.license.redistribution == "permitted"
    assert {f.path for f in mf.files} >= {"network.nc", "canonical.json"}
    # committed JSON is the deterministic dump
    assert (d / "canonical.json").read_text("utf-8").endswith("\n")
    json.loads((d / "manifest.json").read_text("utf-8"))


def test_scigrid_cross_list_id_collision_is_flagged():
    cn = load_canonical(networks_dir() / "scigrid-de/canonical.json")
    overlap = {r.id for r in cn.lines} & {r.id for r in cn.transformers}
    assert len(overlap) == 96
    assert (
        "cross_component_id_collision"
        in load_manifest(networks_dir() / "scigrid-de/manifest.json").quality_flags
    )


def test_pglib_ids_follow_contract():
    cn = load_canonical(networks_dir() / "pglib-case14-ieee/canonical.json")
    assert cn.coordinate_kind == "schematic" and cn.crs is None
    assert {r.id for r in cn.transformers} == {"branch-8", "branch-9", "branch-10"}
    assert all(r.id.startswith("load-") for r in cn.loads)
    assert [r.id for r in cn.generators] == [f"gen-{i}" for i in range(1, 6)]


def test_validate_all_reports_no_errors():
    reports = validate_all(REQUIRED, powerflow=True)
    for rep in reports:
        assert rep["errors"] == [], (rep["network_id"], rep["errors"])
    by_id = {r["network_id"]: r for r in reports}
    pf = by_id["pglib-case14-ieee"]["info"]["pglib"]["dc_powerflow"]
    assert abs(pf["imbalance_mw"]) < 1e-6 and pf["total_load_mw"] == 259.0
    assert by_id["ac-dc-meshed"]["info"]["connectivity"]["sub_networks"] == 4


def test_export_netcdf_is_idempotent(tmp_path):
    n = _toy()
    path = tmp_path / "network.nc"
    assert export_netcdf(n, path)
    before = path.read_bytes()
    assert not export_netcdf(n, path)
    assert path.read_bytes() == before


def test_validation_detects_checksum_tampering(tmp_path):
    source = networks_dir() / "pglib-case14-ieee"
    dataset = tmp_path / source.name
    shutil.copytree(source, dataset)
    canonical = dataset / "canonical.json"
    canonical.write_text(canonical.read_text("utf-8") + "\n", encoding="utf-8")
    report = validate_dataset(dataset, powerflow=False)
    assert "checksum/size mismatch for canonical.json" in report["errors"]
