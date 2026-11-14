"""Network analytics served from precomputed JSON; pypsa is never imported in the API process.

``services/analytics/scripts/precompute_analytics.py`` runs ``gridstorm_analytics.compute`` for
every kind on each catalog network's unsolved ``network.nc`` and writes
``data/networks/<id>/analytics/<kind>.json`` plus ``index.json`` (sha256 of ``network.nc`` and of
every file, generator command and source versions). Importing pypsa costs ~300 MB RSS, which
together with a solver child overflowed the 512 MB container (docs/benchmarks/api-memory.md).

Carrier/country filters are applied to the precomputed unfiltered result only where that is exact
for unsolved networks: capacity and costs rows are already grouped by (component,) carrier and bus
country, so a filter keeps a subset of rows and per-carrier values and totals are re-summed from
the kept rows (``math.fsum``; pandas may round the last bit differently). Kinds that are not
available (energy balance of an unsolved network) only echo the filters. Any other filtered request
is a 422 ``analytics_filter_not_precomputed``; nothing is approximated.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable
from typing import Any

from .catalog import NetworkEntry
from .errors import APIError, NotFound, ServiceUnavailable, Unprocessable

INDEX_SCHEMA = "gridstorm-analytics-precomputed/1.0"
# Filter derivation per kind; "summary" never accepts filters (as gridstorm_analytics.compute).
_DERIVABLE = frozenset({"capacity", "costs"})


class AnalyticsService:
    def __init__(self) -> None:
        # (network id, network sha256) -> index; (network id, network sha256, kind) -> result
        self._indexes: dict[tuple[str, str | None], dict[str, Any]] = {}
        self._results: dict[tuple[str, str | None, str], dict[str, Any]] = {}

    def _index(self, entry: NetworkEntry) -> dict[str, Any]:
        key = (entry.id, entry.network_sha256)
        if key in self._indexes:
            return self._indexes[key]
        path = entry.directory / "analytics" / "index.json"
        if not path.is_file():
            raise ServiceUnavailable(
                f"network {entry.id} has no precomputed analytics in this deployment",
                code="analytics_not_precomputed",
            )
        index = json.loads(path.read_bytes())
        if index.get("schema_version") != INDEX_SCHEMA:
            raise _integrity_error(entry, f"unsupported schema {index.get('schema_version')!r}")
        if entry.network_sha256 and index.get("network_sha256") != entry.network_sha256:
            raise ServiceUnavailable(
                f"precomputed analytics of {entry.id} were built from another network.nc "
                f"(sha256 {index.get('network_sha256')}, manifest {entry.network_sha256})",
                code="analytics_stale",
            )
        self._indexes[key] = index
        return index

    def _result(self, entry: NetworkEntry, index: dict[str, Any], kind: str) -> dict[str, Any]:
        key = (entry.id, entry.network_sha256, kind)
        if key in self._results:
            return self._results[key]
        meta = index["kinds"][kind]
        data = (entry.directory / "analytics" / meta["path"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != meta["sha256"]:
            raise _integrity_error(entry, f"{meta['path']} does not match its recorded sha256")
        self._results[key] = result = json.loads(data)
        return result

    async def compute(
        self,
        entry: NetworkEntry,
        kind: str,
        carriers: list[str] | None,
        countries: list[str] | None,
    ) -> dict[str, Any]:
        index = self._index(entry)
        kinds = index["kinds"]
        if kind not in kinds:
            raise NotFound(
                f"unknown analytics kind {kind!r}; available: {list(kinds)}",
                code="analytics_kind_not_found",
                details={"kind": kind, "available": list(kinds)},
            )
        result = self._result(entry, index, kind)
        derived = carriers is not None or countries is not None
        if derived:
            summary = self._result(entry, index, "summary")
            exempt = frozenset(index["carrier_filter_exempt_components"])
            result = _filtered(kind, result, summary, carriers, countries, exempt)
        return {
            **result,
            "execution_mode": "precomputed",
            "precomputed": {
                "network_sha256": index["network_sha256"],
                "file": f"data/networks/{entry.id}/analytics/{kinds[kind]['path']}",
                "file_sha256": kinds[kind]["sha256"],
                "filters_derived_from_unfiltered": derived,
                "generator": index["generator"],
            },
        }


def _integrity_error(entry: NetworkEntry, message: str) -> APIError:
    return APIError(
        f"precomputed analytics of {entry.id}: {message}",
        code="analytics_integrity_error",
        status_code=500,
    )


def _dedupe(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    for v in values:
        if v not in out:
            out.append(v)
    return out


def _validate(
    carriers: list[str] | None, countries: list[str] | None, summary: dict[str, Any]
) -> tuple[list[str] | None, list[str] | None]:
    """Same checks and messages as ``gridstorm_analytics._common.validate_filters``."""
    if carriers is not None:
        carriers = _dedupe(carriers)
        if not carriers:
            raise _bad_filter("carriers filter must be null or a non-empty list")
        known = summary["carriers"]
        unknown = [c for c in carriers if c not in known]
        if unknown:
            raise _bad_filter(f"unknown carrier(s) {unknown}; network carriers: {sorted(known)}")
    if countries is not None:
        countries = _dedupe(countries)
        if not countries:
            raise _bad_filter("countries filter must be null or a non-empty list")
        known = summary["countries"]
        if not known:
            raise _bad_filter("countries filter given but the network has no bus country data")
        unknown = [c for c in countries if c not in known]
        if unknown:
            raise _bad_filter(f"unknown country code(s) {unknown}; network countries: {known}")
    return carriers, countries


def _bad_filter(message: str) -> Unprocessable:
    return Unprocessable(message, code="invalid_analytics_filter")


def _filtered(
    kind: str,
    result: dict[str, Any],
    summary: dict[str, Any],
    carriers: list[str] | None,
    countries: list[str] | None,
    carrier_exempt: frozenset[str],
) -> dict[str, Any]:
    carriers, countries = _validate(carriers, countries, summary)
    if kind == "summary":
        raise _bad_filter("the summary analytic does not accept carrier/country filters")
    filters = {"carriers": carriers, "countries": countries}
    if not result["available"]:
        return {**result, "filters": filters}
    if result["network_solved"] or kind not in _DERIVABLE:
        raise Unprocessable(
            f"filtered {kind} analytics are not precomputed for this network; request it "
            "without carriers/countries",
            code="analytics_filter_not_precomputed",
            details={"kind": kind, "filters": filters},
        )

    def keep(row: dict[str, Any], component: str) -> bool:
        # PyPSA applies a carrier filter only to components that have a carrier attribute
        carrier_ok = carriers is None or component in carrier_exempt or row["carrier"] in carriers
        return carrier_ok and (countries is None or row["country"] in countries)

    assumptions = list(result["assumptions"])
    if countries is not None:
        assumptions.append(f"Filtered to bus countries {countries}.")
    if carriers is not None:
        assumptions.append(f"Filtered to component carriers {carriers}.")
    out = {**result, "filters": filters, "assumptions": assumptions}
    if kind == "capacity":
        groups = [_capacity_group(g, keep) for g in result["groups"]]
        generation = next((g for g in groups if g["key"] == "generator_power"), None)
        out["groups"] = groups
        out["generation_capacity_by_carrier_mw"] = (
            {c: v["installed_mw"] for c, v in generation["by_carrier"].items()}
            if generation
            else {}
        )
    else:
        rows = [r for r in result["rows"] if keep(r, r["component"])]
        columns = ("capex_installed_eur", "capex_optimal_eur", "opex_eur")
        out["rows"] = rows
        out["by_carrier"] = {
            c: None if result["by_carrier"][c] is None else _sum_by_carrier(rows, c)
            for c in columns
        }
        out["totals"] = {
            c: None if result["totals"][c] is None else _sum(r[c] for r in rows) for c in columns
        }
    return out


def _capacity_group(group: dict[str, Any], keep: Any) -> dict[str, Any]:
    suffix = next(k for k in group if k.startswith("total_installed_"))[len("total_installed_") :]
    installed, optimal = f"installed_{suffix}", f"optimal_{suffix}"
    rows = [r for r in group["rows"] if keep(r, group["component"])]
    inst = _sum_by_carrier(rows, installed)
    opt = _sum_by_carrier(rows, optimal) if group[f"total_optimal_{suffix}"] is not None else None
    return {
        **group,
        "rows": rows,
        "by_carrier": {
            c: {installed: v, optimal: opt[c] if opt is not None else None} for c, v in inst.items()
        },
        f"total_installed_{suffix}": _sum(r[installed] for r in rows),
        f"total_optimal_{suffix}": (_sum(r[optimal] for r in rows) if opt is not None else None),
    }


def _sum(values: Iterable[float | None]) -> float:
    """pandas ``sum`` semantics: missing values (NaN, serialised as null) are skipped."""
    return math.fsum(v for v in values if v is not None)


def _sum_by_carrier(rows: list[dict[str, Any]], column: str) -> dict[str, float]:
    """Per-carrier sums in pandas ``groupby`` order (sorted; a null carrier is the "" group)."""
    groups: dict[str, list[float | None]] = {}
    for r in rows:
        groups.setdefault(r["carrier"] or "", []).append(r[column])
    return {c: _sum(groups[c]) for c in sorted(groups)}
