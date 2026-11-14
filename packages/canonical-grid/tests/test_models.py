from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from canonical_grid import (
    CanonicalNetwork,
    DatasetManifest,
    NetworkCatalog,
    dump_json,
    load_canonical,
    load_catalog,
    load_manifest,
)
from canonical_grid.schema_export import DEFAULT_DIR, render

REPO = Path(__file__).resolve().parents[3]
NETWORKS = REPO / "data" / "networks"

MINIMAL = {
    "schema_version": "canonical-grid/1.0",
    "network_id": "toy-two-bus",
    "name": "Toy",
    "coordinate_kind": "schematic",
    "crs": None,
    "snapshots": {"count": 1, "start": None, "end": None, "resolution_h": 1.0},
    "buses": [
        {
            "id": "b0",
            "name": None,
            "x": 0.0,
            "y": 0.0,
            "v_nom_kv": 110.0,
            "carrier": "AC",
            "country": None,
        },
        {
            "id": "b1",
            "name": None,
            "x": 1.0,
            "y": 0.0,
            "v_nom_kv": 110.0,
            "carrier": "AC",
            "country": None,
        },
    ],
    "lines": [
        {
            "id": "l0",
            "bus0": "b0",
            "bus1": "b1",
            "v_nom_kv": 110.0,
            "s_nom_mva": 100.0,
            "x_ohm": 10.0,
            "r_ohm": 1.0,
            "length_km": None,
            "num_parallel": 1.0,
            "carrier": "AC",
        }
    ],
    "transformers": [],
    "links": [],
    "generators": [
        {
            "id": "g0",
            "bus": "b0",
            "carrier": "gas",
            "p_nom_mw": 50.0,
            "marginal_cost_eur_per_mwh": 30.0,
            "p_nom_extendable": False,
            "is_variable": False,
        }
    ],
    "loads": [{"id": "d1", "bus": "b1", "p_peak_mw": 40.0, "p_mean_mw": 40.0, "energy_mwh": 40.0}],
    "storage_units": [],
    "stores": [],
    "carriers": [{"id": "gas", "color": None, "co2_emissions_t_per_mwh": 0.2, "nice_name": None}],
    "summary": {
        "counts": {"buses": 2, "lines": 1, "generators": 1, "loads": 1},
        "capacity_by_carrier_mw": {"gas": 50.0},
        "peak_load_mw": 40.0,
        "total_load_mwh": 40.0,
    },
    "field_provenance": {"buses.x": "synthetic", "generators.marginal_cost_eur_per_mwh": "modeled"},
    "assumptions": ["toy"],
}


def test_minimal_roundtrip():
    net = CanonicalNetwork.model_validate(MINIMAL)
    again = CanonicalNetwork.model_validate(json.loads(dump_json(net)))
    assert again == net


@pytest.mark.parametrize(
    ("mutate", "needle"),
    [
        (lambda d: d["lines"][0].update(bus1="nope"), "unknown bus"),
        (lambda d: d["buses"].append(dict(d["buses"][0])), "duplicate buses"),
        (lambda d: d.update(crs="EPSG:4326"), "schematic"),
        (lambda d: d.update(coordinate_kind="geographic"), "requires a crs"),
        (lambda d: d["buses"][0].update(v_nom_kv=0.0), "greater than 0"),
        (lambda d: d["lines"][0].update(s_nom_mva=-1.0), "greater than or equal"),
        (lambda d: d["field_provenance"].update({"buses.bogus": "observed"}), "field_provenance"),
        (lambda d: d["field_provenance"].update({"buses.x": "guessed"}), "field_provenance"),
        (lambda d: d["summary"]["counts"].update(lines=7), "summary.counts"),
        (lambda d: d["buses"][0].update(extra=1), "Extra inputs"),
        (lambda d: d["lines"][0].update(x_ohm=float("nan")), "finite"),
    ],
)
def test_rejects_invalid(mutate, needle):
    d = copy.deepcopy(MINIMAL)
    mutate(d)
    with pytest.raises(ValidationError) as exc:
        CanonicalNetwork.model_validate(d)
    assert needle in str(exc.value)


def test_storage_efficiency_range():
    d = copy.deepcopy(MINIMAL)
    d["storage_units"] = [
        {
            "id": "s",
            "bus": "b0",
            "carrier": None,
            "p_nom_mw": 1.0,
            "max_hours": 6.0,
            "efficiency_store": 1.2,
            "efficiency_dispatch": 0.9,
        }
    ]
    with pytest.raises(ValidationError):
        CanonicalNetwork.model_validate(d)


def test_manifest_rejects_bad_paths_and_hashes():
    base = {
        "network_id": "toy-two-bus",
        "name": "Toy",
        "description": "",
        "source": {"url": "x", "version": "1", "publication_date": None, "upstream_commit": None},
        "retrieved_at": "2026-01-01T00:00:00+00:00",
        "files": [{"path": "network.nc", "sha256": "0" * 64, "bytes": 1}],
        "license": {"spdx": "MIT", "url": "x", "attribution": "x", "redistribution": "permitted"},
        "coverage": {"geographic": "x", "temporal": "x"},
        "units": {},
        "missing_value_policy": "null",
        "quality_flags": [],
        "transformations": [],
        "engines": ["pypsa"],
        "provenance_class": "synthetic",
    }
    DatasetManifest.model_validate(base)
    for bad in (
        {"path": "../x", "sha256": "0" * 64, "bytes": 1},
        {"path": "a\\b", "sha256": "0" * 64, "bytes": 1},
        {"path": "x", "sha256": "XYZ", "bytes": 1},
    ):
        with pytest.raises(ValidationError):
            DatasetManifest.model_validate({**base, "files": [bad]})


def test_committed_schemas_are_current():
    for filename, text in render().items():
        assert (DEFAULT_DIR / filename).read_text(encoding="utf-8") == text, filename


def test_schema_accepts_minimal_example():
    schema = json.loads((DEFAULT_DIR / "canonical-grid-1.0.schema.json").read_text("utf-8"))
    jsonschema.validate(MINIMAL, schema)


@pytest.mark.skipif(not (NETWORKS / "catalog.json").exists(), reason="no committed datasets")
def test_committed_datasets_validate():
    catalog = load_catalog(NETWORKS / "catalog.json")
    assert isinstance(catalog, NetworkCatalog)
    schema = json.loads((DEFAULT_DIR / "canonical-grid-1.0.schema.json").read_text("utf-8"))
    for entry in catalog.networks:
        d = NETWORKS / entry.path
        net = load_canonical(d / "canonical.json")
        man = load_manifest(d / "manifest.json")
        assert net.network_id == man.network_id == entry.id
        jsonschema.validate(json.loads((d / "canonical.json").read_text("utf-8")), schema)
