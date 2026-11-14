# Derived from PyPSA-Explorer (https://github.com/open-energy-transition/PyPSA-Explorer)
# commit c85252c98cab742b43245a18bcd310d095bab443, original paths:
#   src/pypsa_explorer/utils/helpers.py (get_carrier_nice_name, get_country_options,
#   get_country_filter), src/pypsa_explorer/utils/network_loader.py (get_unique_carriers).
# Copyright (c) 2025 OET Network Viewer contributors. MIT License; full text in
# UPSTREAM_LICENSE_PyPSA-Explorer.txt next to this file.
# Modifications Copyright (c) 2026 GridStorm contributors (MIT): Dash/HTML output removed,
# filters validated and applied to DataFrames instead of plotly `query` strings.
"""Shared helpers: provenance envelope, filter validation, JSON conversion."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from typing import Any

import pandas as pd
import pypsa

UPSTREAM = {
    "upstream": "PyPSA-Explorer",
    "url": "https://github.com/open-energy-transition/PyPSA-Explorer",
    "sha": "c85252c98cab742b43245a18bcd310d095bab443",
    "license": "MIT",
}

SCHEMA_VERSION = "gridstorm-analytics/1.0"

# Monetary values: PyPSA stores no currency; GridStorm networks use EUR cost data.
CURRENCY_ASSUMPTION = (
    "Monetary values are in the cost currency of the network data; PyPSA stores no currency "
    "unit, GridStorm assumes EUR (example-network costs are illustrative, not market data)."
)

# PyPSA's statistics module rounds to `params.statistics.round` decimals when `round` is None.
# `round=0` is falsy and disables rounding without touching the (global) option state.
NO_ROUNDING = 0


def is_solved(n: pypsa.Network) -> bool:
    """True when the network carries optimisation results (objective value set)."""
    return bool(n.is_solved)


def bus_countries(n: pypsa.Network) -> list[str]:
    """Sorted non-empty country codes of the network's buses (Explorer country options)."""
    if "country" not in n.buses.columns:
        return []
    countries = n.buses["country"].dropna().astype(str)
    return sorted({c for c in countries if c.strip()})


def network_carriers(n: pypsa.Network) -> list[str]:
    """Carriers used by any component or declared in n.carriers (Explorer get_unique_carriers)."""
    carriers: set[str] = set(map(str, n.carriers.index))
    for c in n.components.values():
        static = c.static
        if static.empty or "carrier" not in static.columns:
            continue
        values = static["carrier"].dropna().astype(str)
        carriers.update(v for v in values if v)
    return sorted(carriers)


def carrier_nice_names(n: pypsa.Network) -> dict[str, str]:
    """Carrier id -> display name; falls back to the id when nice_name is empty or missing."""
    out: dict[str, str] = {}
    nice = n.carriers["nice_name"] if "nice_name" in n.carriers.columns else None
    for carrier in network_carriers(n):
        name = None
        if nice is not None and carrier in nice.index:
            value = nice.at[carrier]
            if isinstance(value, str) and value.strip():
                name = value
        out[carrier] = name or carrier
    return out


def validate_filters(
    n: pypsa.Network,
    carriers: Sequence[str] | None,
    countries: Sequence[str] | None,
) -> tuple[list[str] | None, list[str] | None]:
    """Validate carrier/country filters against the network. Raises ValueError on unknown values.

    An empty list is rejected (the Explorer UI shows "please select" instead of an empty chart).
    """
    carriers_out: list[str] | None = None
    countries_out: list[str] | None = None
    if carriers is not None:
        carriers_out = _dedupe(carriers)
        if not carriers_out:
            raise ValueError("carriers filter must be null or a non-empty list")
        known = set(network_carriers(n))
        unknown = [c for c in carriers_out if c not in known]
        if unknown:
            raise ValueError(f"unknown carrier(s) {unknown}; network carriers: {sorted(known)}")
    if countries is not None:
        countries_out = _dedupe(countries)
        if not countries_out:
            raise ValueError("countries filter must be null or a non-empty list")
        known_countries = bus_countries(n)
        if not known_countries:
            raise ValueError("countries filter given but the network has no bus country data")
        unknown = [c for c in countries_out if c not in known_countries]
        if unknown:
            raise ValueError(
                f"unknown country code(s) {unknown}; network countries: {known_countries}"
            )
    return carriers_out, countries_out


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: list[str] = []
    for v in values:
        s = str(v)
        if s not in seen:
            seen.append(s)
    return seen


def has_country(n: pypsa.Network) -> bool:
    """True when buses carry a `country` column (not a mandatory PyPSA attribute)."""
    return "country" in n.buses.columns


def run_statistic(
    n: pypsa.Network,
    method: str,
    *,
    groupby: Sequence[str],
    countries: list[str] | None,
    **kwargs: Any,
) -> pd.Series | pd.DataFrame:
    """Call ``n.statistics.<method>`` grouped by ``groupby`` + country, unrounded, zeros kept.

    Networks without a bus `country` column get a `country` index level of None so callers see
    one index layout. Single-column DataFrames are squeezed to Series. Rows are filtered to
    ``countries`` (PyPSA-Explorer applies the same filter as a plotly `country in [...]` query).
    """
    use_country = has_country(n)
    keys = list(groupby) + (["country"] if use_country else [])
    result = getattr(n.statistics, method)(
        groupby=keys, nice_names=False, drop_zero=False, round=NO_ROUNDING, **kwargs
    )
    if isinstance(result, pd.DataFrame) and kwargs.get("groupby_time", "sum") is not False:
        if result.shape[1] != 1:
            raise RuntimeError(f"expected one statistics column, got {list(result.columns)}")
        result = result.iloc[:, 0]
    if result.empty:
        return result
    if not use_country:
        frame = result.index.to_frame(index=False)
        frame["country"] = None
        result = result.copy()
        result.index = pd.MultiIndex.from_frame(frame)
    if countries is not None:
        level = result.index.get_level_values("country")
        result = result[level.isin(countries)]
    return result


def to_float(value: Any) -> float | None:
    """JSON-safe float: NaN/inf -> None."""
    if value is None:
        return None
    f = float(value)
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def country_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    s = str(value)
    return s if s.strip() else None


def envelope(
    kind: str,
    n: pypsa.Network,
    *,
    carriers: list[str] | None,
    countries: list[str] | None,
    available: bool,
    reason: str | None,
    units: dict[str, str],
    assumptions: list[str],
    derived_from: list[str],
    pypsa_statistics: list[str],
    data: dict[str, Any],
) -> dict[str, Any]:
    """Common result envelope for every analytics kind."""
    out: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "available": available,
        "reason": reason,
        "provenance": "calculated",
        "network_solved": is_solved(n),
        "filters": {"carriers": carriers, "countries": countries},
        "units": units,
        "assumptions": assumptions,
        "source": {
            **UPSTREAM,
            "derived_from": derived_from,
            "engine": {"name": "pypsa", "version": pypsa.__version__},
            "pypsa_statistics": pypsa_statistics,
        },
    }
    out.update(data)
    return out
