# Derived from PyPSA-Explorer (https://github.com/open-energy-transition/PyPSA-Explorer)
# commit c85252c98cab742b43245a18bcd310d095bab443, original paths:
#   src/pypsa_explorer/layouts/components.py (create_header KPI counts),
#   src/pypsa_explorer/utils/helpers.py (summarize_network, get_bus_carrier_options,
#   get_country_options).
# Copyright (c) 2025 OET Network Viewer contributors. MIT License; full text in
# UPSTREAM_LICENSE_PyPSA-Explorer.txt next to this file.
# Modifications Copyright (c) 2026 GridStorm contributors (MIT): Dash components removed;
# returns component counts and filter options as JSON.
"""Network summary: component counts, carriers, countries, snapshots, solve state."""

from __future__ import annotations

from typing import Any

import pandas as pd
import pypsa

from ._common import (
    bus_countries,
    carrier_nice_names,
    envelope,
    is_solved,
    network_carriers,
    to_float,
)

DERIVED_FROM = [
    "src/pypsa_explorer/layouts/components.py:create_header",
    "src/pypsa_explorer/utils/helpers.py:summarize_network",
    "src/pypsa_explorer/utils/helpers.py:get_bus_carrier_options",
    "src/pypsa_explorer/utils/helpers.py:get_country_options",
]

COUNTED = (
    "buses",
    "generators",
    "loads",
    "lines",
    "transformers",
    "links",
    "storage_units",
    "stores",
)


def compute_summary(
    n: pypsa.Network, *, carriers: list[str] | None, countries: list[str] | None
) -> dict[str, Any]:
    if carriers is not None or countries is not None:
        raise ValueError("the summary analytic does not accept carrier/country filters")
    counts = {name: int(len(getattr(n, name))) for name in COUNTED}
    bus_carriers = sorted({str(c) for c in n.buses["carrier"].astype(str) if c and c != "none"})
    snaps = n.snapshots
    solved = is_solved(n)
    # PyPSA's default single snapshot is the label "now", not a time: pd.Timestamp("now") would
    # report the wall-clock time of the computation.
    timestamped = isinstance(snaps, pd.DatetimeIndex) and len(snaps) > 0
    assumptions = ["Counts are numbers of static component rows (inactive assets included)."]
    if len(snaps) and not timestamped:
        assumptions.append(
            "Snapshots are labels, not timestamps (e.g. PyPSA's default single snapshot 'now'); "
            "snapshot_start and snapshot_end are null."
        )
    return envelope(
        "summary",
        n,
        carriers=None,
        countries=None,
        available=True,
        reason=None,
        units={"snapshot_hours_h": "h", "objective_eur": "EUR"},
        assumptions=assumptions,
        derived_from=DERIVED_FROM,
        pypsa_statistics=[],
        data={
            "counts": counts,
            "bus_carriers": bus_carriers,
            "carriers": network_carriers(n),
            "carrier_names": carrier_nice_names(n),
            "countries": bus_countries(n),
            "snapshot_count": int(len(snaps)),
            "snapshot_start": snaps[0].isoformat() if timestamped else None,
            "snapshot_end": snaps[-1].isoformat() if timestamped else None,
            "snapshot_hours_h": to_float(n.snapshot_weightings.generators.sum()),
            "objective_eur": to_float(n.objective) if solved else None,
        },
    )
