"""Import PGLib-OPF MATPOWER cases (``pglib-case14-ieee``, ``pglib-case118-ieee``).

Source: https://github.com/power-grid-lib/pglib-opf at tag v23.07, commit
dc6be4b2f85ca0e776952ec22cbd4c22396ea5a3. Raw ``.m`` files and the LICENSE are downloaded from
raw.githubusercontent.com at that pinned commit into ``source/`` (sha256 pinned in
``source/retrieval-*.json``). LICENSE (verified): "Data License: Creative Commons Attribution 4.0
International license"; each case header repeats the CC-BY-4.0 grant.
"""

from __future__ import annotations

from dataclasses import dataclass

import pypsa

from network_import.canonical import from_pypsa
from network_import.manifest import (
    BASE_UNITS,
    export_netcdf,
    update_catalog,
    write_canonical,
    write_manifest,
)
from network_import.matpower import parse_matpower
from network_import.paths import fetch, networks_dir
from network_import.pglib import UNLIMITED_RATING_MVA, build_network, schematic_layout

PGLIB_TAG = "v23.07"
PGLIB_COMMIT = "dc6be4b2f85ca0e776952ec22cbd4c22396ea5a3"
PGLIB_RAW = f"https://raw.githubusercontent.com/power-grid-lib/pglib-opf/{PGLIB_COMMIT}"
PGLIB_LICENSE_URL = f"https://github.com/power-grid-lib/pglib-opf/blob/{PGLIB_COMMIT}/LICENSE"


@dataclass(frozen=True)
class PglibCase:
    network_id: str
    file: str
    name: str
    description: str
    attribution: str


PGLIB_CASES = {
    c.network_id: c
    for c in (
        PglibCase(
            "pglib-case14-ieee", "pglib_opf_case14_ieee.m", "IEEE 14-bus (PGLib-OPF v23.07)",
            "IEEE 14-bus test case (1962 AEP system) as curated in PGLib-OPF v23.07 'typical "
            "operations' benchmark: 14 buses, 20 branches, 5 generators, single operating point.",
            "PGLib-OPF v23.07 (c) IEEE PES Task Force on Benchmarks for Validation of Emerging "
            "Power System Algorithms, CC-BY-4.0, https://github.com/power-grid-lib/pglib-opf; "
            "IEEE 14-bus data (c) 1999 Richard D. Christie, University of Washington (CC-BY-4.0).",
        ),
        PglibCase(
            "pglib-case118-ieee", "pglib_opf_case118_ieee.m", "IEEE 118-bus (PGLib-OPF v23.07)",
            "IEEE 118-bus test case (AEP system, 1962) as curated in PGLib-OPF v23.07 'typical "
            "operations' benchmark: 118 buses, 186 branches, 54 generators, single operating "
            "point.",
            "PGLib-OPF v23.07 (c) IEEE PES Task Force on Benchmarks for Validation of Emerging "
            "Power System Algorithms, CC-BY-4.0, https://github.com/power-grid-lib/pglib-opf; "
            "IEEE 118-bus data (c) 1999 Richard D. Christie, University of Washington (CC-BY-4.0).",
        ),
    )
}

PGLIB_UNITS = {
    **BASE_UNITS,
    "generators.marginal_cost_eur_per_mwh": "currency units/MWh as in MATPOWER gencost "
    "($/h polynomial; PGLib uses a nominal $); not converted to EUR",
    "buses.x": "schematic layout units (dimensionless)",
    "buses.y": "schematic layout units (dimensionless)",
}


def _flags(rep, case) -> list[str]:
    flags = ["schematic_coordinates", "single_snapshot", "cost_currency_not_eur",
             "marginal_cost_linearized_secant"]
    if rep.unlimited_branches:
        flags.append(f"rate_a_zero_unlimited:{','.join(rep.unlimited_branches)}")
    if rep.out_of_service_branches:
        flags.append(f"branches_out_of_service:{','.join(rep.out_of_service_branches)}")
    if rep.out_of_service_gens:
        flags.append(f"generators_out_of_service:{','.join(rep.out_of_service_gens)}")
    if rep.isolated_buses:
        flags.append(f"isolated_buses:{','.join(rep.isolated_buses)}")
    if rep.nonzero_gs_buses:
        flags.append(f"bus_shunt_conductance:{','.join(rep.nonzero_gs_buses)}")
    if case.extra_fields:
        flags.append(f"unparsed_matpower_fields:{','.join(case.extra_fields)}")
    return flags


def import_pglib(network_id: str, *, catalog: bool = True) -> None:
    spec = PGLIB_CASES[network_id]
    d = networks_dir() / network_id
    src = d / "source"
    url = f"{PGLIB_RAW}/{spec.file}"
    rec = fetch(url, src / spec.file, record=src / f"retrieval-{spec.file}.json")
    fetch(f"{PGLIB_RAW}/LICENSE", src / "LICENSE-pglib-opf",
          record=src / "retrieval-LICENSE.json")

    case = parse_matpower(src / spec.file)
    n, rep = build_network(case, spec.name)
    layout = schematic_layout(n)
    n.c.buses.static["x"] = layout["x"]
    n.c.buses.static["y"] = layout["y"]
    export_netcdf(n, d / "network.nc")

    n_trafo, n_line = rep.n_transformers, rep.n_lines
    assumptions = [
        f"Imported from {spec.file} (PGLib-OPF {PGLIB_TAG}, commit {PGLIB_COMMIT[:7]}); "
        f"{len(case.bus)} buses, {len(case.branch)} branches ({n_line} lines, {n_trafo} "
        f"transformers), {len(case.gen)} generators.",
        "Ids: bus-<BUS_I>, branch-<row of mpc.branch>, gen-<row of mpc.gen>, load-<BUS_I>. A "
        "branch is a transformer if TAP not in {0,1}, SHIFT != 0 or baseKV differs at its ends; "
        "it keeps the id branch-<row> in the transformers list.",
        "Line impedances: x_ohm = x_pu * baseKV^2 / baseMVA (r likewise); line shunt b in S = "
        "b_pu * baseMVA / baseKV^2. Transformer x_pu/r_pu are re-based from baseMVA to s_nom: "
        "x_pu(s_nom) = x_pu(baseMVA) * s_nom / baseMVA; tap on bus0 (MATPOWER from-bus), "
        "phase_shift = SHIFT degrees, pi model.",
        f"RATE_A = 0 means unlimited in MATPOWER: canonical s_nom_mva = null; network.nc uses "
        f"s_nom = {UNLIMITED_RATING_MVA:g} MVA so PyPSA has a finite (non-binding) value. "
        f"Affected: {', '.join(rep.unlimited_branches) or 'none'}.",
        "Quadratic costs c2*P^2 + c1*P + c0 ($/h) are linearised to the secant slope over "
        "[0, Pmax]: marginal_cost = c1 + c2*Pmax (exact when c2 = 0; c0 dropped). Labelled "
        "modeled. Currency is MATPOWER's nominal $ and not converted to EUR.",
        "Generators: p_nom = Pmax, p_min_pu = Pmin/Pmax, p_set = Pg, q_set = Qg; generator "
        "carrier = PGLib fuel comment (NG, COW, PEL, NUC, SYNC ...).",
        f"PGLib Pg values are an initial point, not a balanced dispatch: sum(Pg of in-service "
        f"generators) = {sum(g['pg'] for g in case.gen if int(g['status'])):g} MW vs sum(Pd) = "
        f"{sum(b['pd'] for b in case.bus):g} MW; in a power flow the Slack generator absorbs the "
        "difference (run an OPF for an economic dispatch).",
        "Loads: p_set = Pd, q_set = Qd; only buses with non-zero Pd or Qd get a load. Bus shunts "
        "Gs/Bs become ShuntImpedance shunt-<BUS_I> in network.nc (not in canonical-grid/1.0).",
        "Single operating point: one PyPSA snapshot 'now' with weighting 1 h, so "
        "loads.energy_mwh equals load MW x 1 h.",
        "Bus x/y are a deterministic Kamada-Kawai layout of the branch graph (coordinate_kind "
        "schematic, crs null); they are NOT geographic.",
        "Voltage limits Vmin/Vmax and setpoint Vm are stored as v_mag_pu_min/max/set in "
        "network.nc. RATE_B/RATE_C and branch angle limits are not represented.",
    ]
    canonical = from_pypsa(
        n, network_id, spec.name, coordinate_kind="schematic", crs=None,
        field_provenance={
            "buses.x": "calculated", "buses.y": "calculated", "buses.v_nom_kv": "synthetic",
            "buses.carrier": "synthetic", "buses.name": "synthetic",
            "lines.s_nom_mva": "synthetic", "lines.x_ohm": "calculated",
            "lines.r_ohm": "calculated", "lines.num_parallel": "synthetic",
            "lines.carrier": "synthetic",
            "transformers.s_nom_mva": "synthetic", "transformers.x_pu": "calculated",
            "transformers.r_pu": "calculated", "transformers.tap_ratio": "synthetic",
            "generators.carrier": "synthetic", "generators.p_nom_mw": "synthetic",
            "generators.marginal_cost_eur_per_mwh": "modeled",
            "loads.p_peak_mw": "synthetic", "loads.p_mean_mw": "synthetic",
            "loads.energy_mwh": "calculated", "carriers.nice_name": "synthetic",
        },
        assumptions=assumptions,
        null_fields=["lines.length_km", "buses.country", "generators.p_nom_extendable",
                     "carriers.color", "carriers.co2_emissions_t_per_mwh",
                     *([] if case.bus_name else ["buses.name"])],
        bus_name_column="location" if case.bus_name else None,
    )
    # RATE_A = 0: no limit in the source -> null in canonical.json (never the placeholder).
    unlimited = set(rep.unlimited_branches)
    if unlimited:
        for comp in (canonical.lines, canonical.transformers):
            for row in comp:
                if row.id in unlimited:
                    row.s_nom_mva = None
        canonical = type(canonical).model_validate(canonical.model_dump())
    write_canonical(d, canonical)

    write_manifest(
        d,
        network_id=network_id,
        name=spec.name,
        description=spec.description,
        source={"url": url, "version": f"PGLib-OPF {PGLIB_TAG}", "publication_date": "2023-07-23",
                "upstream_commit": PGLIB_COMMIT},
        retrieved_at=rec["retrieved_at"],
        license={"spdx": "CC-BY-4.0", "url": PGLIB_LICENSE_URL, "attribution": spec.attribution,
                 "redistribution": "permitted"},
        coverage={"geographic": "Synthetic/benchmark test system (historic AEP-derived IEEE "
                  "case); no geography, schematic layout only.",
                  "temporal": "Single operating point (one snapshot), no date."},
        quality_flags=_flags(rep, case),
        transformations=[
            {"step": "download", "tool": "network_import.paths.fetch", "version": "1.0.0",
             "description": f"Downloaded {spec.file} and LICENSE from pglib-opf at commit "
             f"{PGLIB_COMMIT} into source/ (sha256 pinned in source/retrieval-*.json)."},
            {"step": "parse", "tool": "network_import.matpower.parse_matpower",
             "version": "1.0.0",
             "description": "Strict MATPOWER v2 parser (bus, gen, branch, gencost, bus_name)."},
            {"step": "build", "tool": "network_import.pglib.build_network",
             "version": f"pypsa {pypsa.__version__}",
             "description": "Per-unit -> PyPSA units, transformer detection, RATE_A=0 handling, "
             "secant cost linearisation, Kamada-Kawai schematic layout; exported network.nc."},
            {"step": "canonicalize", "tool": "network_import.canonical.from_pypsa",
             "version": f"pypsa {pypsa.__version__}",
             "description": "Converted to canonical-grid/1.0; unlimited ratings emitted as null."},
        ],
        engines=["pypsa", "pandapower"],
        provenance_class="synthetic",
        units=PGLIB_UNITS,
    )
    if catalog:
        update_catalog()
