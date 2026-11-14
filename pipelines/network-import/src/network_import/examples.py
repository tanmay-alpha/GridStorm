"""Import PyPSA's example networks ``ac-dc-meshed`` and ``scigrid-de``.

Source: the exact files PyPSA 1.4.0 downloads in ``pypsa.examples.ac_dc_meshed()`` /
``pypsa.examples.scigrid_de()``: ``https://data.pypsa.org/networks/examples/v1.4.0/<name>.nc``.
``network.nc`` is the upstream file, byte-identical (sha256 pinned in ``source/retrieval.json``);
only canonical.json and manifest.json are derived from it.

License (verified): PyPSA ``REUSE.toml`` at tag v1.4.0 (commit
6c45594596cbc5612511ee9202a9e269e5001d88) annotates ``examples/**.nc`` as
``SPDX-License-Identifier = "CC-BY-4.0"``, ``SPDX-FileCopyrightText = "PyPSA Contributors"``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pypsa
from canonical_grid import Provenance

from network_import.canonical import from_pypsa
from network_import.manifest import (
    BASE_UNITS,
    update_catalog,
    write_canonical,
    write_manifest,
)
from network_import.paths import fetch, networks_dir

PYPSA_VERSION = "1.4.0"
PYPSA_COMMIT = "6c45594596cbc5612511ee9202a9e269e5001d88"
BASE_URL = f"https://data.pypsa.org/networks/examples/v{PYPSA_VERSION}"
REUSE_URL = f"https://github.com/PyPSA/PyPSA/blob/{PYPSA_COMMIT}/REUSE.toml"

PYPSA_LICENSE_NOTE = (
    "PyPSA REUSE.toml (v1.4.0, commit 6c45594) licenses examples/**.nc as CC-BY-4.0, copyright "
    "'PyPSA Contributors'."
)


@dataclass
class ExampleSpec:
    network_id: str
    upstream_name: str
    name: str
    description: str
    expected_sha256: str
    coverage: dict[str, str]
    license: dict[str, str]
    provenance_class: str
    field_provenance: dict[str, Provenance]
    null_fields: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    quality_flags: list[str] = field(default_factory=list)


_SYN = "synthetic"

AC_DC_MESHED = ExampleSpec(
    network_id="ac-dc-meshed",
    upstream_name="ac_dc_meshed",
    name="AC-DC meshed (PyPSA example)",
    description=(
        "Small synthetic 9-bus meshed AC/DC test network (UK, Germany, Norway nodes) shipped with "
        "PyPSA: 7 AC lines, 4 DC links, 6 generators (gas/wind, extendable), 10 hourly snapshots "
        "starting 2015-01-01. Illustrative only; not a real grid."
    ),
    expected_sha256="62e4e53555e2219a2ae48b7f91e576e2ea383cadd2f61db9919f3592503c932f",
    coverage={
        "geographic": "Illustrative nodes placed at UK (London, Norwich, Manchester), Germany "
        "(Frankfurt, Bremen) and Norway; lon/lat EPSG:4326; synthetic topology.",
        "temporal": "10 hourly snapshots 2015-01-01T00:00 to 2015-01-01T09:00 (synthetic).",
    },
    license={
        "spdx": "CC-BY-4.0",
        "url": REUSE_URL,
        "attribution": "AC-DC meshed example network, (c) PyPSA Contributors, CC-BY-4.0, "
        "https://github.com/PyPSA/PyPSA (examples/networks/ac-dc-meshed).",
        "redistribution": "permitted",
    },
    provenance_class=_SYN,
    field_provenance={
        **{f"buses.{f}": _SYN for f in ("x", "y", "v_nom_kv", "carrier", "country")},
        **{f"lines.{f}": _SYN for f in ("s_nom_mva", "x_ohm", "r_ohm", "num_parallel", "carrier")},
        **{f"links.{f}": _SYN for f in ("p_nom_mw", "efficiency", "carrier")},
        **{
            f"generators.{f}": _SYN
            for f in ("carrier", "p_nom_mw", "marginal_cost_eur_per_mwh", "p_nom_extendable")
        },
        **{f"loads.{f}": "calculated" for f in ("p_peak_mw", "p_mean_mw", "energy_mwh")},
        **{f"carriers.{f}": _SYN for f in ("color", "co2_emissions_t_per_mwh", "nice_name")},
    },
    null_fields=["lines.length_km", "buses.name"],
    assumptions=[
        "Synthetic example network; all values are illustrative test data from PyPSA.",
        "lines.length_km is null: the source stores PyPSA's default length 0 for every line.",
        "AC lines '0', '1', '5', '6' have r_ohm = 0 (reactance only); lines '2', '3', '4' join "
        "the DC buses and have x_ohm = 0 (resistance only, as PyPSA's DC power flow uses r). "
        "All lines carry carrier 'AC' in the source; values are kept unchanged.",
        "Generators are p_nom_extendable with large placeholder p_nom (e.g. 50000 MW gas) in the "
        "source; the network is meant for capacity-expansion demos.",
        "The source also contains GlobalConstraint 'co2_limit' (not part of canonical-grid/1.0).",
        "The AC/DC lines form 4 PyPSA sub-networks (bus counts 3, 3, 2, 1) that are coupled "
        "only through the 4 converter links; this is by design, not a data error.",
    ],
    quality_flags=[
        "synthetic_network",
        "line_length_missing",
        "zero_line_impedances_in_source",
        "extendable_generators_with_placeholder_p_nom",
        "multiple_sub_networks_coupled_by_links",
    ],
)

_SG_OBS: Provenance = "observed"
SCIGRID_DE = ExampleSpec(
    network_id="scigrid-de",
    upstream_name="scigrid_de",
    name="SciGRID Germany (PyPSA example)",
    description=(
        "German 220/380 kV transmission grid from SciGRID v0.2 (derived from OpenStreetMap), with "
        "power plants, load and renewable availability for 24 hourly snapshots of 2011-01-01, as "
        "packaged by the PyPSA project (pypsa.examples.scigrid_de)."
    ),
    expected_sha256="284850c8e922414f9da69ffda0623431148e0c28a3380ba370e4135ac5236500",
    coverage={
        "geographic": "Germany, 220 kV and 380 kV transmission level (SciGRID v0.2, OSM-derived); "
        "lon/lat EPSG:4326.",
        "temporal": "24 hourly snapshots 2011-01-01T00:00 to 2011-01-01T23:00.",
    },
    license={
        "spdx": "CC-BY-4.0",
        "url": REUSE_URL,
        "attribution": "SciGRID Germany example network, (c) PyPSA Contributors (CC-BY-4.0, "
        "https://github.com/PyPSA/PyPSA); grid topology from SciGRID v0.2 (DLR Institute of "
        "Networked Energy Systems, formerly NEXT ENERGY, www.scigrid.de) based on OpenStreetMap "
        "data (c) OpenStreetMap contributors, ODbL-1.0.",
        "redistribution": "permitted",
    },
    provenance_class="modeled",
    field_provenance={
        "buses.x": _SG_OBS,
        "buses.y": _SG_OBS,
        "buses.v_nom_kv": _SG_OBS,
        "buses.carrier": _SG_OBS,
        "lines.length_km": _SG_OBS,
        "lines.num_parallel": _SG_OBS,
        "lines.s_nom_mva": "estimated",
        "lines.x_ohm": "calculated",
        "lines.r_ohm": "calculated",
        "transformers.s_nom_mva": "estimated",
        "transformers.x_pu": "estimated",
        "transformers.r_pu": "estimated",
        "transformers.tap_ratio": "estimated",
        "generators.carrier": _SG_OBS,
        "generators.p_nom_mw": _SG_OBS,
        "generators.marginal_cost_eur_per_mwh": "modeled",
        "generators.p_nom_extendable": "modeled",
        "loads.p_peak_mw": "modeled",
        "loads.p_mean_mw": "modeled",
        "loads.energy_mwh": "modeled",
        "storage_units.carrier": _SG_OBS,
        "storage_units.p_nom_mw": _SG_OBS,
        "storage_units.max_hours": "estimated",
        "storage_units.efficiency_store": "estimated",
        "storage_units.efficiency_dispatch": "estimated",
        "carriers.nice_name": "modeled",
    },
    null_fields=[
        "buses.name",
        "buses.country",
        "lines.carrier",
        "carriers.co2_emissions_t_per_mwh",
        "carriers.color",
    ],
    assumptions=[
        "lines.x_ohm/r_ohm are the effective impedances PyPSA derives from the standard line "
        "type ('Al/St 240/40 2-bundle 220.0' / '4-bundle 380.0') x length / num_parallel; the "
        "source stores x = r = 0 with a line type.",
        "lines.s_nom_mva follows from the standard type's thermal current x v_nom x num_parallel "
        "(PyPSA example preparation) and is an estimate, not an operator rating.",
        "Transformers use uniform placeholder parameters from the PyPSA example preparation "
        "(s_nom 2000 MVA, x = 0.1 p.u.); treat as estimates.",
        "Load (per PyPSA docs/examples/scigrid-lopf-then-pf.ipynb): ENTSO-E hourly German load "
        "scaled uniformly by 1.12, distributed to buses proportional to NUTS3 GDP and "
        "population (attached to the 220 kV substation in doubt) — modeled, not metered.",
        "Conventional plant capacities/locations from the BNetzA power plant list; wind/solar "
        "capacities from EEG Stammdaten/EnergyMap (end-2014); wind/solar availability from "
        "REatlas (Andresen et al. 2015); plants attached to the nearest HV substation. Marginal "
        "costs are illustrative per-carrier values (upstream notebook: 'not accurate'). Biomass "
        "from EEG Stammdaten is not included.",
        "carriers.co2_emissions_t_per_mwh is null: the source stores 0 for every carrier, which "
        "is a default, not an emission factor.",
        "Line and transformer ids overlap (e.g. '2' is both a line and a transformer); ids are "
        "unique only per component list. line_outage events must set component.",
        "4 loads have no p_set time series and keep the static p_set = 0 MW.",
    ],
    quality_flags=[
        "line_impedance_from_standard_types",
        "line_rating_estimated",
        "transformer_parameters_placeholder",
        "load_spatially_disaggregated_model",
        "marginal_cost_placeholder",
        "co2_factors_missing",
        "cross_component_id_collision",
    ],
)

EXAMPLES = {s.network_id: s for s in (AC_DC_MESHED, SCIGRID_DE)}


def import_example(network_id: str, *, catalog: bool = True) -> None:
    spec = EXAMPLES[network_id]
    d = networks_dir() / network_id
    url = f"{BASE_URL}/{spec.upstream_name}.nc"
    rec = fetch(
        url,
        d / "network.nc",
        record=d / "source" / "retrieval.json",
        expected_sha256=spec.expected_sha256,
    )
    n = pypsa.Network(d / "network.nc")
    canonical = from_pypsa(
        n,
        spec.network_id,
        spec.name,
        coordinate_kind="geographic",
        crs=f"EPSG:{int(n.srid)}",
        field_provenance=spec.field_provenance,
        assumptions=spec.assumptions,
        null_fields=spec.null_fields,
    )
    write_canonical(d, canonical)
    write_manifest(
        d,
        network_id=spec.network_id,
        name=spec.name,
        description=spec.description,
        source={
            "url": url,
            "version": f"PyPSA v{PYPSA_VERSION} example network ({spec.upstream_name})",
            "publication_date": rec.get("http_last_modified"),
            "upstream_commit": PYPSA_COMMIT,
        },
        retrieved_at=rec["retrieved_at"],
        license=spec.license,
        coverage=spec.coverage,
        quality_flags=spec.quality_flags,
        transformations=[
            {
                "step": "download",
                "tool": "network_import.paths.fetch",
                "version": "1.0.0",
                "description": f"Downloaded {url} (the URL pypsa.examples uses for "
                f"v{PYPSA_VERSION}); sha256 pinned in source/retrieval.json. "
                "network.nc is byte-identical upstream.",
            },
            {
                "step": "canonicalize",
                "tool": "network_import.canonical.from_pypsa",
                "version": f"pypsa {pypsa.__version__}",
                "description": "Converted to canonical-grid/1.0; derived impedances via "
                "calculate_dependent_values; defaults masquerading as data emitted as null.",
            },
        ],
        engines=["pypsa"],
        provenance_class=spec.provenance_class,
        units=BASE_UNITS,
    )
    if catalog:
        update_catalog()
