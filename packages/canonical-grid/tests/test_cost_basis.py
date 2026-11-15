"""Optional manifest cost basis is validated without changing manifest/1.0."""

import json
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from canonical_grid import CostBasis, load_catalog, load_manifest

NETWORKS = Path(__file__).resolve().parents[3] / "data/networks"
SCHEMA = Path(__file__).resolve().parents[1] / "schema/dataset-manifest-1.0.schema.json"


def test_all_five_manifests_validate_against_model_and_schema():
    catalog = load_catalog(NETWORKS / "catalog.json")
    assert len(catalog.networks) == 5
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    for entry in catalog.networks:
        path = NETWORKS / entry.path / "manifest.json"
        manifest = load_manifest(path)
        assert manifest.cost_basis is not None
        jsonschema.validate(json.loads(path.read_text(encoding="utf-8")), schema)


def test_unverified_basis_cannot_claim_currency_or_incoherent_price_unit():
    basis = load_manifest(NETWORKS / "pglib-case14-ieee/manifest.json").cost_basis.model_dump()
    for change in ({"currency": "EUR"}, {"price_unit": "EUR/MWh"}):
        with pytest.raises(ValidationError):
            CostBasis.model_validate({**basis, **change})
