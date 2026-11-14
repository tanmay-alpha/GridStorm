"""Scenario validation: StormSpec schema + ``stormspec.validate`` against the canonical network,
plus the API's own execution checks (dataset hash pinning, executable engine, network file)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import stormspec
from pydantic import ValidationError

from .catalog import NetworkCatalog, NetworkEntry
from .errors import NotFound, ServiceUnavailable

#: Engines this API can execute live. Other engines' results are served as precomputed artifacts.
LIVE_ENGINES = ("pypsa",)


@dataclass
class ValidationOutcome:
    errors: list[dict[str, str]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    scenario: Any = None  # stormspec.Scenario when structurally valid
    entry: NetworkEntry | None = None
    scenario_hash: str | None = None

    @property
    def valid(self) -> bool:
        return not self.errors

    def report(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "scenario_hash": self.scenario_hash,
            "network_id": self.entry.id if self.entry else None,
        }


def _issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _as_issue(item: Any) -> dict[str, str]:
    if isinstance(item, dict):
        get = item.get
    else:
        def get(k: str, default: Any = None) -> Any:
            return getattr(item, k, default)
    return _issue(str(get("code", "invalid")), str(get("path", "") or ""), str(get("message", "")))


def _loc(loc: tuple[Any, ...]) -> str:
    out = ""
    for part in loc:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += ("." if out else "") + str(part)
    return out


def validate_spec(
    spec: Any, catalog: NetworkCatalog, *, for_execution: bool
) -> ValidationOutcome:
    out = ValidationOutcome()
    if not isinstance(spec, dict):
        out.errors.append(_issue("schema_error", "", "scenario must be a JSON object"))
        return out
    try:
        scenario = stormspec.Scenario.model_validate(spec)
    except ValidationError as exc:
        for err in exc.errors():
            out.errors.append(_issue("schema_error", _loc(tuple(err.get("loc", ()))), err["msg"]))
        return out
    out.scenario = scenario
    out.scenario_hash = stormspec.scenario_hash(scenario)
    network_id = scenario.dataset.network_id
    try:
        entry = catalog.get(network_id)
    except (NotFound, ServiceUnavailable) as exc:
        out.errors.append(_issue("unknown_network", "dataset.network_id", exc.message))
        return out
    out.entry = entry

    report = stormspec.validate(scenario, entry.canonical)
    out.errors.extend(_as_issue(i) for i in getattr(report, "errors", []))
    out.warnings.extend(_as_issue(i) for i in getattr(report, "warnings", []))

    pinned = scenario.dataset.sha256
    if pinned and entry.network_sha256 and pinned != entry.network_sha256:
        out.errors.append(
            _issue(
                "dataset_sha256_mismatch",
                "dataset.sha256",
                f"scenario pins network.nc sha256 {pinned} but the served dataset is "
                f"{entry.network_sha256}",
            )
        )
    elif pinned and not entry.network_sha256:
        out.warnings.append(
            _issue(
                "dataset_sha256_unverifiable",
                "dataset.sha256",
                "the dataset manifest lists no network.nc sha256; the pin cannot be checked",
            )
        )

    engine = scenario.execution.engine
    if engine not in LIVE_ENGINES:
        issue = _issue(
            "unsupported_operation",
            "execution.engine",
            f"this API executes {', '.join(LIVE_ENGINES)} scenarios only; {engine} results are "
            "available as precomputed artifacts (/api/v1/artifacts)",
        )
        (out.errors if for_execution else out.warnings).append(issue)
    if for_execution and not entry.network_nc.is_file():
        out.errors.append(
            _issue(
                "network_file_missing",
                "dataset.network_id",
                f"network {entry.id} has no network.nc in this deployment; it cannot be simulated",
            )
        )
    return out
