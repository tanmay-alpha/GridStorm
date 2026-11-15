"""Readiness checks: database, artifact store, solver, datasets."""

from __future__ import annotations

import json
import subprocess
import threading
import time
from typing import Any

from .context import AppContext
from .storage import ArtifactStore

_PROBE = (
    "import json, highspy, pypsa, linopy; "
    "print(json.dumps({'highspy': getattr(highspy, '__version__', None) or "
    "__import__('importlib.metadata').metadata.version('highspy'), "
    "'pypsa': pypsa.__version__, 'linopy': linopy.__version__, "
    "'gridstorm_pypsa': "
    "__import__('importlib.util').util.find_spec('gridstorm_pypsa') is not None}))"
)


class SolverProbe:
    """Imports the solver stack in a subprocess (so a broken install cannot crash the API);
    the result is cached for ``ttl_s`` seconds."""

    def __init__(self, python: str, ttl_s: float) -> None:
        self.python = python
        self.ttl_s = ttl_s
        self._lock = threading.Lock()
        self._cached: tuple[float, dict[str, Any]] | None = None

    def check(self) -> dict[str, Any]:
        with self._lock:
            if self._cached and time.monotonic() - self._cached[0] < self.ttl_s:
                return self._cached[1]
            try:
                proc = subprocess.run(
                    [self.python, "-c", _PROBE],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                if proc.returncode == 0:
                    versions = json.loads(proc.stdout.strip().splitlines()[-1])
                    ok = bool(versions.pop("gridstorm_pypsa"))
                    res = {
                        "status": "ok" if ok else "error",
                        "detail": "highs importable" if ok else "gridstorm_pypsa not installed",
                        "versions": versions,
                    }
                else:
                    res = {"status": "error", "detail": proc.stderr.strip()[-500:]}
            except (OSError, subprocess.TimeoutExpired, ValueError, IndexError) as exc:
                res = {"status": "error", "detail": f"{type(exc).__name__}: {exc}"}
            self._cached = (time.monotonic(), res)
            return res


class StorageProbe:
    """Cache a verified storage round-trip, not merely a successful upload."""

    def __init__(self, store: ArtifactStore, ttl_s: float) -> None:
        self.store = store
        self.ttl_s = ttl_s
        self._lock = threading.Lock()
        self._cached: tuple[float, dict[str, Any]] | None = None

    def check(self) -> dict[str, Any]:
        with self._lock:
            if self._cached and time.monotonic() < self._cached[0]:
                return self._cached[1]
            result: dict[str, Any] = {
                "status": "error",
                "backend": self.store.backend,
                "durable": False,
            }
            try:
                result["detail"] = self.store.check_writable()
            except Exception as exc:
                # Backend exceptions can contain URLs or credentials; never return them.
                result["detail"] = f"artifact storage probe failed ({type(exc).__name__})"
            else:
                result["status"] = "ok"
                result["durable"] = self.store.durable
            self._cached = (time.monotonic() + self.ttl_s, result)
            return result


def _safe(fn: Any) -> dict[str, Any]:
    try:
        return fn()
    except Exception as exc:  # report, never raise from /ready
        return {"status": "error", "detail": f"{type(exc).__name__}: {exc}"[:500]}


def run_checks(ctx: AppContext) -> dict[str, Any]:
    def database() -> dict[str, Any]:
        ctx.db.ping()
        if ctx.db.is_postgres:
            return {"status": "ok", "kind": "postgres", "detail": "postgres"}
        return {
            "status": "ok",
            "kind": "sqlite-ephemeral",
            "detail": "SQLite fallback (DATABASE_URL unset): not durable on hosts with ephemeral "
            "disks (e.g. Render free) — jobs and saved scenarios are lost on restart/redeploy",
        }

    def storage() -> dict[str, Any]:
        assert ctx.storage_probe is not None
        return ctx.storage_probe.check()

    def solver() -> dict[str, Any]:
        if ctx.settings.execution_mode == "precomputed":
            return {"status": "skipped", "detail": "execution_mode=precomputed (no live solves)"}
        assert ctx.solver_probe is not None
        return ctx.solver_probe.check()

    def datasets() -> dict[str, Any]:
        entries = ctx.catalog.entries()
        errors = ctx.catalog.errors
        missing_nc = [i for i, e in entries.items() if not e.network_nc.is_file()]
        ok = bool(entries) and not errors
        detail = f"{len(entries)} network(s) loaded"
        if errors:
            detail += f"; unusable: {sorted(errors)}"
        res: dict[str, Any] = {"status": "ok" if ok else "error", "detail": detail}
        if missing_nc:
            res["networks_without_network_nc"] = sorted(missing_nc)
        return res

    checks = {
        "database": _safe(database),
        "storage": _safe(storage),
        "solver": _safe(solver),
        "datasets": _safe(datasets),
    }
    ready = all(c["status"] in ("ok", "skipped") for c in checks.values())
    return {"status": "ready" if ready else "not_ready", "checks": checks}
