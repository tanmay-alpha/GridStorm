"""Manifest regeneration preserves the audited basis instead of guessing EUR."""

import json

import pytest

from network_import.cost_basis import dataset_cost_basis
from network_import.manifest import write_manifest
from network_import.paths import networks_dir

DATASETS = ["ac-dc-meshed", "scigrid-de", "pglib-case14-ieee", "pglib-case118-ieee", "pypsa-eur-be"]


@pytest.mark.parametrize("network_id", DATASETS)
def test_generator_basis_matches_committed_manifest(network_id):
    manifest = json.loads(
        (networks_dir() / network_id / "manifest.json").read_text(encoding="utf-8")
    )
    assert dataset_cost_basis(network_id) == manifest["cost_basis"]


def test_manifest_writer_overrides_legacy_eur_unit(tmp_path):
    (tmp_path / "network.nc").write_bytes(b"test fixture")
    result = write_manifest(
        tmp_path,
        network_id="pglib-case14-ieee",
        name="Fixture",
        description="Fixture",
        source={
            "url": "fixture",
            "version": "test",
            "publication_date": None,
            "upstream_commit": None,
        },
        retrieved_at="2026-11-15T00:00:00+00:00",
        license={
            "spdx": "CC0-1.0",
            "url": "fixture",
            "attribution": "test",
            "redistribution": "permitted",
        },
        coverage={"geographic": "fixture", "temporal": "one snapshot"},
        quality_flags=[],
        transformations=[],
        engines=["pypsa"],
        provenance_class="synthetic",
        units={"generators.marginal_cost_eur_per_mwh": "EUR/MWh"},
    )
    assert result.cost_basis.money_unit == "PGLib cost units"
    assert result.units["generators.marginal_cost_eur_per_mwh"] == "PGLib cost units/MWh"


def test_custom_netcdf_import_does_not_invent_a_currency():
    assert dataset_cost_basis("custom-network")["money_unit"] == "cost units (basis unknown)"
