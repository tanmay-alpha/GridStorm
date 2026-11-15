"""GridStorm analytics: PyPSA-Explorer's analytical views as pure functions on pypsa.Network.

Public API::

    available_analytics() -> list[str]
    compute(kind, n, *, carriers=None, countries=None) -> dict   # JSON-serialisable

Every result carries ``provenance: "calculated"``, ``assumptions``, ``units`` and
``source: {upstream: "PyPSA-Explorer", sha, ...}``. Kinds that need optimisation results return
``available: false`` with a ``reason`` for unsolved networks instead of zeros.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import pypsa

from ._common import UPSTREAM, validate_filters
from .capacity import compute_capacity
from .costs import compute_costs
from .energy_balance import compute_energy_balance
from .summary import compute_summary

__all__ = ["KINDS", "UPSTREAM", "UnknownAnalyticsKind", "available_analytics", "compute"]


class UnknownAnalyticsKind(ValueError):
    """Raised by :func:`compute` for a kind not in :data:`KINDS`."""


_REGISTRY: dict[str, Callable[..., dict[str, Any]]] = {
    "capacity": compute_capacity,
    "energy_balance": compute_energy_balance,
    "costs": compute_costs,
    "summary": compute_summary,
}

KINDS: tuple[str, ...] = tuple(_REGISTRY)


def available_analytics() -> list[str]:
    """Names of the supported analytics kinds."""
    return list(KINDS)


def compute(
    kind: str,
    n: pypsa.Network,
    *,
    carriers: Sequence[str] | None = None,
    countries: Sequence[str] | None = None,
    cost_basis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute analytics ``kind`` for network ``n``.

    ``carriers`` filters by component carrier (e.g. ``["wind", "gas"]``), ``countries`` by the
    country code of the bus an asset is attached to. Unknown kinds raise
    :class:`UnknownAnalyticsKind`; unknown filter values raise ``ValueError``.
    """
    try:
        func = _REGISTRY[kind]
    except KeyError:
        raise UnknownAnalyticsKind(
            f"unknown analytics kind {kind!r}; available: {list(KINDS)}"
        ) from None
    carriers_v, countries_v = validate_filters(n, carriers, countries)
    if kind == "costs":
        return func(n, carriers=carriers_v, countries=countries_v, cost_basis=cost_basis)
    return func(n, carriers=carriers_v, countries=countries_v)
