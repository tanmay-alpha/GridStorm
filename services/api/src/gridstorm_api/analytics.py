"""Network analytics via ``gridstorm_analytics.compute`` (PyPSA-Explorer-derived).

``pypsa.Network`` objects are loaded lazily from ``network.nc`` into a bounded LRU cache
(``GRIDSTORM_NETWORK_CACHE_SIZE``); computations run in a worker thread with a timeout
(``GRIDSTORM_ANALYTICS_TIMEOUT_S``) and bounded concurrency. Results for the unsolved input
network are deterministic, so they are memoised per (network, file sha256, kind, filters).
A timed-out computation keeps running in its thread until done (Python threads cannot be killed);
the concurrency bound prevents pile-up.
"""

from __future__ import annotations

import asyncio
import threading
from collections import OrderedDict
from typing import Any

from .catalog import NetworkEntry
from .errors import APIError, NotFound, ServiceUnavailable, Unprocessable


class AnalyticsService:
    def __init__(self, *, cache_size: int, timeout_s: float, max_concurrency: int) -> None:
        self.cache_size = cache_size
        self.timeout_s = timeout_s
        self._networks: OrderedDict[str, Any] = OrderedDict()
        self._results: OrderedDict[tuple[Any, ...], dict[str, Any]] = OrderedDict()
        self._load_lock = threading.Lock()
        self._sem = asyncio.Semaphore(max_concurrency)

    @staticmethod
    def kinds() -> tuple[str, ...]:
        import gridstorm_analytics

        return tuple(gridstorm_analytics.KINDS)

    def _network(self, entry: NetworkEntry) -> Any:
        key = f"{entry.id}:{entry.network_sha256 or entry.manifest_sha256}"
        with self._load_lock:
            if key in self._networks:
                self._networks.move_to_end(key)
                return self._networks[key]
            if not entry.network_nc.is_file():
                raise ServiceUnavailable(
                    f"network {entry.id} has no network.nc in this deployment",
                    code="network_file_missing",
                )
            import pypsa

            n = pypsa.Network(str(entry.network_nc))
            self._networks[key] = n
            while len(self._networks) > self.cache_size:
                self._networks.popitem(last=False)
            return n

    def _compute(
        self,
        entry: NetworkEntry,
        kind: str,
        carriers: list[str] | None,
        countries: list[str] | None,
    ) -> dict[str, Any]:
        import gridstorm_analytics

        key = (entry.id, entry.network_sha256, kind, tuple(carriers or ()), tuple(countries or ()))
        with self._load_lock:
            if key in self._results:
                self._results.move_to_end(key)
                return self._results[key]
        n = self._network(entry)
        try:
            result = gridstorm_analytics.compute(kind, n, carriers=carriers, countries=countries)
        except gridstorm_analytics.UnknownAnalyticsKind as exc:
            raise NotFound(
                str(exc),
                code="analytics_kind_not_found",
                details={"kind": kind, "available": list(gridstorm_analytics.KINDS)},
            ) from exc
        except ValueError as exc:
            raise Unprocessable(str(exc), code="invalid_analytics_filter") from exc
        with self._load_lock:
            self._results[key] = result
            while len(self._results) > 64:
                self._results.popitem(last=False)
        return result

    async def compute(
        self,
        entry: NetworkEntry,
        kind: str,
        carriers: list[str] | None,
        countries: list[str] | None,
    ) -> dict[str, Any]:
        if kind not in self.kinds():
            raise NotFound(
                f"unknown analytics kind {kind!r}",
                code="analytics_kind_not_found",
                details={"kind": kind, "available": list(self.kinds())},
            )
        if self._sem.locked():
            raise ServiceUnavailable(
                "analytics capacity exhausted; retry shortly",
                code="analytics_busy",
                headers={"Retry-After": "5"},
            )
        async with self._sem:
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(self._compute, entry, kind, carriers, countries),
                    timeout=self.timeout_s,
                )
            except TimeoutError as exc:
                raise APIError(
                    f"analytics computation exceeded {self.timeout_s:g} s",
                    code="analytics_timeout",
                    status_code=504,
                ) from exc
