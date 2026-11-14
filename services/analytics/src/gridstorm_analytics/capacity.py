# Derived from PyPSA-Explorer (https://github.com/open-energy-transition/PyPSA-Explorer)
# commit c85252c98cab742b43245a18bcd310d095bab443, original path:
#   src/pypsa_explorer/callbacks/visualizations.py (update_capacity_charts).
# Copyright (c) 2025 OET Network Viewer contributors. MIT License; full text in
# UPSTREAM_LICENSE_PyPSA-Explorer.txt next to this file.
# Modifications Copyright (c) 2026 GridStorm contributors (MIT): Plotly/Dash rendering removed;
# returns JSON tables; reports installed capacity (p_nom/s_nom/e_nom, valid for unsolved networks)
# alongside optimal capacity (*_opt, solved networks only) and splits components by unit.
"""Installed / optimal capacity by component, carrier and country."""

from __future__ import annotations

from typing import Any

import pandas as pd
import pypsa

from ._common import (
    carrier_nice_names,
    country_or_none,
    envelope,
    is_solved,
    run_statistic,
    to_float,
)

# (component, nominal attribute, unit suffix, unit label, group key)
GROUPS: tuple[tuple[str, str, str, str, str], ...] = (
    ("Generator", "p_nom", "mw", "MW", "generator_power"),
    ("StorageUnit", "p_nom", "mw", "MW", "storage_unit_power"),
    ("StorageUnit", "p_nom*max_hours", "mwh", "MWh", "storage_unit_energy"),
    ("Store", "e_nom", "mwh", "MWh", "store_energy"),
    ("Line", "s_nom", "mva", "MVA", "line_rating"),
    ("Transformer", "s_nom", "mva", "MVA", "transformer_rating"),
    ("Link", "p_nom", "mw", "MW", "link_power"),
)

DERIVED_FROM = ["src/pypsa_explorer/callbacks/visualizations.py:update_capacity_charts"]


def _stat(
    n: pypsa.Network,
    method: str,
    component: str,
    carriers: list[str] | None,
    countries: list[str] | None,
    storage: bool,
) -> pd.Series:
    series = run_statistic(
        n,
        method,
        groupby=["carrier"],
        countries=countries,
        components=[component],
        carrier=carriers,
        storage=storage,
    )
    if series.empty:
        return series
    # storage=True makes PyPSA include both Store and StorageUnit; keep the requested one.
    series = series[series.index.get_level_values("component") == component]
    return series.droplevel("component")


def compute_capacity(
    n: pypsa.Network, *, carriers: list[str] | None, countries: list[str] | None
) -> dict[str, Any]:
    solved = is_solved(n)
    groups: list[dict[str, Any]] = []
    units: dict[str, str] = {}
    for component, attr, suffix, unit, key in GROUPS:
        if n.components[component].static.empty:
            continue
        storage = attr == "p_nom*max_hours"
        installed = _stat(n, "installed_capacity", component, carriers, countries, storage)
        optimal = (
            _stat(n, "optimal_capacity", component, carriers, countries, storage)
            if solved
            else None
        )
        installed_key = f"installed_{suffix}"
        optimal_key = f"optimal_{suffix}"
        units[f"{key}.{installed_key}"] = unit
        units[f"{key}.{optimal_key}"] = unit
        if optimal is not None:
            optimal = optimal.reindex(installed.index, fill_value=0.0)
        rows = [
            {
                "carrier": str(carrier) if str(carrier) else None,
                "country": country_or_none(country),
                installed_key: to_float(installed.iloc[i]),
                optimal_key: to_float(optimal.iloc[i]) if optimal is not None else None,
            }
            for i, (carrier, country) in enumerate(installed.index)
        ]
        by_carrier: dict[str, dict[str, float | None]] = {}
        if not installed.empty:
            inst_by_carrier = installed.groupby(level="carrier").sum()
            opt_by_carrier = optimal.groupby(level="carrier").sum() if optimal is not None else None
            for carrier, value in inst_by_carrier.items():
                by_carrier[str(carrier)] = {
                    installed_key: to_float(value),
                    optimal_key: (
                        to_float(opt_by_carrier[carrier]) if opt_by_carrier is not None else None
                    ),
                }
        groups.append(
            {
                "key": key,
                "component": component,
                "nominal_attribute": attr,
                "unit": unit,
                "rows": rows,
                "by_carrier": by_carrier,
                f"total_installed_{suffix}": to_float(installed.sum()),
                f"total_optimal_{suffix}": (
                    to_float(optimal.sum()) if optimal is not None else None
                ),
            }
        )

    generation = next((g for g in groups if g["key"] == "generator_power"), None)
    generation_by_carrier_mw = (
        {c: v["installed_mw"] for c, v in generation["by_carrier"].items()} if generation else {}
    )
    assumptions = [
        "Installed capacity = nominal attribute (p_nom, s_nom, e_nom; p_nom*max_hours for "
        "StorageUnit energy) as stored in the network input; valid without optimisation.",
        "Optimal capacity = *_opt attribute written by the PyPSA optimisation; null when the "
        "network is not solved (PyPSA-Explorer plots optimal capacity only, which is 0 for "
        "unsolved networks).",
        "Units differ per component group (MW, MVA, MWh) and are never summed across groups.",
        "Branch components (Line, Transformer, Link) are attributed to the country of bus0.",
        "Assets on buses without a country code have country = null.",
    ]
    if countries is not None:
        assumptions.append(f"Filtered to bus countries {countries}.")
    if carriers is not None:
        assumptions.append(f"Filtered to component carriers {carriers}.")
    return envelope(
        "capacity",
        n,
        carriers=carriers,
        countries=countries,
        available=True,
        reason=None,
        units=units,
        assumptions=assumptions,
        derived_from=DERIVED_FROM,
        pypsa_statistics=["installed_capacity", "optimal_capacity"],
        data={
            "carrier_names": carrier_nice_names(n),
            "generation_capacity_by_carrier_mw": generation_by_carrier_mw,
            "groups": groups,
        },
    )
