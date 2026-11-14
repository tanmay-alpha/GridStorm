# Derived from PyPSA-Explorer (https://github.com/open-energy-transition/PyPSA-Explorer)
# commit c85252c98cab742b43245a18bcd310d095bab443, original path:
#   src/pypsa_explorer/callbacks/visualizations.py (create_energy_balance_callback: timeseries
#   area view and aggregated bar view, one chart per bus carrier).
# Copyright (c) 2025 OET Network Viewer contributors. MIT License; full text in
# UPSTREAM_LICENSE_PyPSA-Explorer.txt next to this file.
# Modifications Copyright (c) 2026 GridStorm contributors (MIT): Plotly/Dash rendering removed;
# returns JSON totals + time series per bus carrier, refuses unsolved networks, adds a nodal
# balance residual self-check.
"""Energy balance (supply positive, withdrawal negative) per bus carrier."""

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

DERIVED_FROM = [
    "src/pypsa_explorer/callbacks/visualizations.py:create_energy_balance_callback",
]

GROUPBY = ["carrier", "bus_carrier"]


def _bus_carrier_units(n: pypsa.Network) -> dict[str, str]:
    """Power unit per bus carrier (PyPSA `Bus.unit`); 'MW' when unset."""
    buses = n.buses
    units: dict[str, str] = {}
    unit_col = buses["unit"] if "unit" in buses.columns else pd.Series("MW", index=buses.index)
    for carrier, unit in zip(buses["carrier"].astype(str), unit_col, strict=True):
        u = str(unit) if isinstance(unit, str) and unit.strip() and unit != "None" else "MW"
        prev = units.get(carrier)
        units[carrier] = u if prev in (None, u) else "mixed"
    return units


def _is_power_unit(unit: str) -> bool:
    """MW-based bus carriers. PyPSA-Eur labels energy buses 'MWh_el', 'MWh_LHV', 'MWh_th':
    their flows are MW and their balances MWh. Mass units such as 't_co2' are not energy."""
    return unit == "MW" or unit.startswith("MWh")


def _balance(
    n: pypsa.Network,
    carriers: list[str] | None,
    countries: list[str] | None,
    groupby_time: str | bool,
) -> Any:
    return run_statistic(
        n,
        "energy_balance",
        groupby=GROUPBY,
        countries=countries,
        groupby_time=groupby_time,
        carrier=carriers,
    )


def compute_energy_balance(
    n: pypsa.Network, *, carriers: list[str] | None, countries: list[str] | None
) -> dict[str, Any]:
    base_assumptions = [
        "Sign convention (PyPSA statistics.energy_balance): positive = energy supplied to a bus, "
        "negative = energy withdrawn from a bus (loads, storage charging, branch withdrawal at a "
        "port). Every branch port is counted at its own bus, so with no carrier filter the sum "
        "over all rows of a bus carrier is the nodal balance and must be ~0 per snapshot.",
        "Energy (MWh) = sum over snapshots of power (MW) x snapshot_weightings.generators (h).",
        "Only bus carriers whose buses use unit 'MW' or an energy label 'MWh*' (PyPSA-Eur: "
        "MWh_el, MWh_LHV, MWh_th; flows in MW) are reported, each with its raw `unit`; other "
        "units (e.g. t_co2) and mixed-unit carriers are listed in excluded_bus_carriers.",
    ]
    common = {
        "carriers": carriers,
        "countries": countries,
        "units": {
            "bus_carriers[].rows[].energy_mwh": "MWh",
            "bus_carriers[].by_carrier_mwh": "MWh",
            "bus_carriers[].supply_mwh": "MWh",
            "bus_carriers[].withdrawal_mwh": "MWh",
            "bus_carriers[].net_mwh": "MWh",
            "bus_carriers[].balance_residual_max_mw": "MW",
            "bus_carriers[].timeseries_mw.by_carrier": "MW",
        },
        "derived_from": DERIVED_FROM,
        "pypsa_statistics": ["energy_balance"],
    }
    if not is_solved(n):
        return envelope(
            "energy_balance",
            n,
            available=False,
            reason=(
                "network is not solved: the energy balance needs dispatch results (p time "
                "series) from an optimisation or power flow run; none are present"
            ),
            assumptions=base_assumptions,
            data={"bus_carriers": [], "excluded_bus_carriers": []},
            **common,
        )

    totals = _balance(n, carriers, countries, "sum")
    series = _balance(n, carriers, countries, False)

    snapshots = [pd.Timestamp(s).isoformat() for s in n.snapshots]
    weights_h = [to_float(w) for w in n.snapshot_weightings.generators]
    units = _bus_carrier_units(n)
    residual_meaningful = carriers is None
    out_groups: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    bus_carriers_present = (
        sorted(map(str, totals.index.get_level_values("bus_carrier").unique()))
        if not totals.empty
        else []
    )
    for bc in bus_carriers_present:
        unit = units.get(bc, "MW")
        if not _is_power_unit(unit):
            excluded.append({"bus_carrier": bc, "unit": unit})
            continue
        t_bc = totals[totals.index.get_level_values("bus_carrier") == bc]
        s_bc = series[series.index.get_level_values("bus_carrier") == bc]
        rows = [
            {
                "component": str(comp),
                "carrier": str(carrier) if str(carrier) else None,
                "country": country_or_none(country),
                "energy_mwh": to_float(value),
            }
            for (comp, carrier, _bc, country), value in t_bc.items()
        ]
        by_carrier = t_bc.groupby(level="carrier").sum()
        ts_by_carrier = s_bc.groupby(level="carrier").sum()
        residual = s_bc.sum(axis=0)
        out_groups.append(
            {
                "bus_carrier": bc,
                "unit": unit,
                "rows": rows,
                "by_carrier_mwh": {str(k): to_float(v) for k, v in by_carrier.items()},
                "supply_mwh": to_float(t_bc[t_bc > 0].sum()),
                "withdrawal_mwh": to_float(t_bc[t_bc < 0].sum()),
                "net_mwh": to_float(t_bc.sum()),
                "balance_residual_max_mw": (
                    to_float(residual.abs().max())
                    if residual_meaningful and len(residual)
                    else None
                ),
                "timeseries_mw": {
                    "by_carrier": {
                        str(k): [to_float(v) for v in row.to_numpy()]
                        for k, row in ts_by_carrier.iterrows()
                    },
                },
            }
        )

    assumptions = list(base_assumptions)
    if not residual_meaningful:
        assumptions.append(
            "Carrier filter active: rows are a subset of the balance, so net_mwh need not be 0 and "
            "balance_residual_max_mw is null."
        )
    if countries is not None:
        assumptions.append(
            f"Filtered to bus countries {countries}; cross-border branch flows appear as branch "
            "rows (each port is attributed to its own bus country)."
        )
    return envelope(
        "energy_balance",
        n,
        available=True,
        reason=None,
        assumptions=assumptions,
        data={
            "carrier_names": carrier_nice_names(n),
            "snapshots": snapshots,
            "snapshot_weightings_h": weights_h,
            "bus_carriers": out_groups,
            "excluded_bus_carriers": excluded,
        },
        **common,
    )
