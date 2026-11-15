# Derived from PyPSA-Explorer (https://github.com/open-energy-transition/PyPSA-Explorer)
# commit c85252c98cab742b43245a18bcd310d095bab443, original path:
#   src/pypsa_explorer/callbacks/visualizations.py (update_capex_charts, update_opex_charts).
# Copyright (c) 2025 OET Network Viewer contributors. MIT License; full text in
# UPSTREAM_LICENSE_PyPSA-Explorer.txt next to this file.
# Modifications Copyright (c) 2026 GridStorm contributors (MIT): Plotly/Dash rendering removed;
# CAPEX and OPEX merged into one JSON table; installed CAPEX added for unsolved networks; OPEX
# withheld (null) instead of plotted as zero when the network is not solved.
"""CAPEX (installed and optimal) and OPEX by component, carrier and country."""

from __future__ import annotations

from typing import Any

import pandas as pd
import pypsa

from ._common import (
    CURRENCY_ASSUMPTION,
    carrier_nice_names,
    country_or_none,
    envelope,
    is_solved,
    run_statistic,
    to_float,
)

DERIVED_FROM = [
    "src/pypsa_explorer/callbacks/visualizations.py:update_capex_charts",
    "src/pypsa_explorer/callbacks/visualizations.py:update_opex_charts",
]

COST_COMPONENTS = ("Generator", "StorageUnit", "Store", "Line", "Transformer", "Link")


def _stat(
    n: pypsa.Network, method: str, carriers: list[str] | None, countries: list[str] | None
) -> pd.Series:
    return run_statistic(
        n,
        method,
        groupby=["carrier"],
        countries=countries,
        components=list(COST_COMPONENTS),
        carrier=carriers,
    )


def _by_carrier(series: pd.Series | None) -> dict[str, float | None] | None:
    if series is None:
        return None
    if series.empty:
        return {}
    return {str(k): to_float(v) for k, v in series.groupby(level="carrier").sum().items()}


def _total(series: pd.Series | None) -> float | None:
    if series is None:
        return None
    return to_float(series.sum()) if not series.empty else 0.0


def compute_costs(
    n: pypsa.Network,
    *,
    carriers: list[str] | None,
    countries: list[str] | None,
    cost_basis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    solved = is_solved(n)
    installed = _stat(n, "installed_capex", carriers, countries)
    optimal = _stat(n, "capex", carriers, countries) if solved else None
    opex = _stat(n, "opex", carriers, countries) if solved else None

    columns = {"capex_installed_eur": installed}
    if optimal is not None:
        columns["capex_optimal_eur"] = optimal
    if opex is not None:
        columns["opex_eur"] = opex
    table = (
        pd.concat({k: v for k, v in columns.items() if not v.empty}, axis=1, sort=True).fillna(0.0)
        if any(not v.empty for v in columns.values())
        else pd.DataFrame()
    )
    rows = []
    for (comp, carrier, country), values in table.iterrows():
        rows.append(
            {
                "component": str(comp),
                "carrier": str(carrier) if str(carrier) else None,
                "country": country_or_none(country),
                "capex_installed_eur": to_float(values.get("capex_installed_eur", 0.0)),
                "capex_optimal_eur": (
                    to_float(values.get("capex_optimal_eur", 0.0)) if optimal is not None else None
                ),
                "opex_eur": to_float(values.get("opex_eur", 0.0)) if opex is not None else None,
            }
        )
    snapshot_hours = float(n.snapshot_weightings.objective.sum())
    money_unit = (cost_basis or {}).get("money_unit") or "cost units (basis unknown)"
    assumptions = [
        CURRENCY_ASSUMPTION,
        f"Declared money unit: {money_unit}.",
        "capex_installed_eur = nominal capacity (p_nom/s_nom/e_nom) x capital_cost "
        "(PyPSA statistics.installed_capex); available without optimisation.",
        "capex_optimal_eur = optimal capacity (*_opt) x capital_cost (PyPSA statistics.capex, "
        "the quantity PyPSA-Explorer plots); null when the network is not solved.",
        "opex_eur = dispatch x marginal cost (plus storage/spill/unit-commitment cost terms when "
        "present) weighted by snapshot_weightings.objective (PyPSA statistics.opex); null when "
        "the network is not solved.",
        "capital_cost is the model's per-period (typically annualised) cost per unit capacity and "
        f"is charged once for the modelled horizon ({snapshot_hours:g} h of objective-weighted "
        "snapshots); CAPEX and OPEX are only on the same time basis if that horizon is one year.",
        "Branch components (Line, Transformer, Link) are attributed to the country of bus0.",
    ]
    if countries is not None:
        assumptions.append(f"Filtered to bus countries {countries}.")
    if carriers is not None:
        assumptions.append(f"Filtered to component carriers {carriers}.")
    return envelope(
        "costs",
        n,
        carriers=carriers,
        countries=countries,
        available=True,
        reason=None,
        units={
            "rows[].capex_installed_eur": money_unit,
            "rows[].capex_optimal_eur": money_unit,
            "rows[].opex_eur": money_unit,
            "by_carrier.*": money_unit,
            "totals.*": money_unit,
            "objective_weighted_hours_h": "h",
        },
        assumptions=assumptions,
        derived_from=DERIVED_FROM,
        pypsa_statistics=["installed_capex", "capex", "opex"],
        data={
            "carrier_names": carrier_nice_names(n),
            "opex_available": solved,
            "opex_reason": None if solved else "network is not solved: no dispatch results",
            "objective_weighted_hours_h": snapshot_hours,
            "rows": rows,
            "by_carrier": {
                "capex_installed_eur": _by_carrier(installed),
                "capex_optimal_eur": _by_carrier(optimal),
                "opex_eur": _by_carrier(opex),
            },
            "totals": {
                "capex_installed_eur": _total(installed),
                "capex_optimal_eur": _total(optimal),
                "opex_eur": _total(opex),
            },
        },
    )
