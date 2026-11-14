"""Semantic validation of a scenario against a canonical-grid/1.0 network and engine capabilities.

``validate(scenario, network)`` never raises for invalid scenarios; it returns a
:class:`ValidationReport`. ``network`` is the canonical-grid/1.0 JSON as a plain ``dict`` (or any
object with ``model_dump()``, e.g. ``canonical_grid.CanonicalNetwork``).

Error codes
-----------
``schema_error``            structural (Pydantic) validation failed
``network_mismatch``        dataset.network_id differs from the network supplied
``horizon_out_of_range``    horizon exceeds the network's snapshots
``window_out_of_range``     event window outside the horizon
``unknown_asset``           asset id not present in the component list the event targets
                            (line_outage: ``component`` = line | transformer); the message names
                            the component type if the id exists elsewhere
``unknown_carrier``         carrier not present in the network
``no_variable_generators``  carrier has no variable (time-varying availability) generators
``no_loads``                demand multiplier selects buses without any load
``conflicting_events``      events contradict each other (e.g. two storage_state for one unit)
``unsupported_operation``   engine cannot represent the formulation / event / window / mitigation
``unknown_engine``          engine not declared in CAPABILITIES

Warning codes: ``duplicate_outage``, ``large_multiplier``, ``mitigation_not_modelled``,
``dataset_unpinned``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from .capabilities import CAPABILITIES
from .models import (
    DemandMultiplier,
    GeneratorOutage,
    LineOutage,
    LinkOutage,
    RenewableAvailabilityMultiplier,
    Scenario,
    StorageState,
)


class Issue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    path: str
    message: str


class ValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    errors: list[Issue]
    warnings: list[Issue]


# canonical-grid list key -> human label
_COMPONENT_KEYS = {
    "buses": "bus",
    "lines": "line",
    "transformers": "transformer",
    "links": "link",
    "generators": "generator",
    "loads": "load",
    "storage_units": "storage unit",
    "stores": "store",
}

# event type -> canonical-grid component key that is the valid target
_EVENT_TARGETS = {
    "link_outage": "links",
    "generator_outage": "generators",
    "storage_state": "storage_units",
}
# line_outage.component -> canonical-grid key
_LINE_COMPONENT = {"line": "lines", "transformer": "transformers"}


def _target_key(ev: Any) -> str:
    if isinstance(ev, LineOutage):
        return _LINE_COMPONENT[ev.component]
    return _EVENT_TARGETS[ev.type]


def _loc_to_path(loc: tuple[Any, ...]) -> str:
    out = ""
    for part in loc:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += ("." if out else "") + str(part)
    return out or "$"


def _network_dict(network: Any) -> dict:
    if isinstance(network, dict):
        return network
    dump = getattr(network, "model_dump", None)
    if callable(dump):
        return dump(mode="json")
    raise TypeError("network must be a canonical-grid/1.0 dict or a model with model_dump()")


class _Index:
    def __init__(self, net: dict) -> None:
        self.ids: dict[str, set[str]] = {
            key: {str(row["id"]) for row in (net.get(key) or [])} for key in _COMPONENT_KEYS
        }
        self.carriers = {str(c["id"]) for c in (net.get("carriers") or [])}
        self.variable_carriers = {
            str(g.get("carrier"))
            for g in (net.get("generators") or [])
            if g.get("is_variable") and g.get("carrier") is not None
        }
        self.load_buses = {str(ld.get("bus")) for ld in (net.get("loads") or [])}
        snaps = net.get("snapshots") or {}
        self.snapshot_count = snaps.get("count")

    def kind_of(self, asset_id: str) -> list[str]:
        return [key for key, ids in self.ids.items() if asset_id in ids]


def check_capabilities(scenario: Scenario) -> list[Issue]:
    """Engine-capability checks that need no network (also used by engine adapters)."""
    issues: list[Issue] = []
    ex = scenario.execution
    caps = CAPABILITIES.get(ex.engine)
    if caps is None:
        return [Issue(code="unknown_engine", path="execution.engine", message=ex.engine)]
    if ex.formulation not in caps.formulations:
        issues.append(
            Issue(
                code="unsupported_operation",
                path="execution.formulation",
                message=f"engine {ex.engine!r} supports formulations {list(caps.formulations)}, "
                f"not {ex.formulation!r}",
            )
        )
    if ex.solver not in caps.solvers:
        issues.append(
            Issue(
                code="unsupported_operation",
                path="execution.solver",
                message=f"engine {ex.engine!r} accepts solvers {list(caps.solvers)}, "
                f"not {ex.solver!r}",
            )
        )
    if caps.max_snapshots is not None and scenario.horizon.snapshots > caps.max_snapshots:
        issues.append(
            Issue(
                code="unsupported_operation",
                path="horizon.snapshots",
                message=f"engine {ex.engine!r} supports at most {caps.max_snapshots} snapshot(s)",
            )
        )
    h_start, h_end = scenario.horizon.start, scenario.horizon.end
    for i, ev in enumerate(scenario.events):
        support = caps.event_windows.get(ev.type)
        if support is None:
            issues.append(
                Issue(
                    code="unsupported_operation",
                    path=f"events[{i}].type",
                    message=f"engine {ex.engine!r} does not support event type {ev.type!r}",
                )
            )
            continue
        window = getattr(ev, "window", None)
        if window is None:
            continue
        if support == "none":
            issues.append(
                Issue(
                    code="unsupported_operation",
                    path=f"events[{i}].window",
                    message=f"engine {ex.engine!r} does not support time windows for {ev.type!r}",
                )
            )
        elif support == "full_horizon" and not window.covers(h_start, h_end):
            issues.append(
                Issue(
                    code="unsupported_operation",
                    path=f"events[{i}].window",
                    message=f"engine {ex.engine!r} represents {ev.type!r} as a topology change "
                    f"for the whole horizon [{h_start}, {h_end}); a partial window "
                    f"[{window.start}, {window.end}) cannot be represented and is rejected",
                )
            )
    mit = scenario.mitigation
    if mit.load_shedding.enabled and not caps.load_shedding:
        issues.append(
            Issue(
                code="unsupported_operation",
                path="mitigation.load_shedding.enabled",
                message=f"engine {ex.engine!r} cannot model load shedding; set enabled: false",
            )
        )
    return issues


def _mitigation_warnings(scenario: Scenario) -> list[Issue]:
    caps = CAPABILITIES.get(scenario.execution.engine)
    if caps is None:
        return []
    out = []
    mit = scenario.mitigation
    for field, supported in (
        ("storage_dispatch", caps.storage_dispatch),
        ("curtailment", caps.curtailment),
    ):
        if not supported:
            out.append(
                Issue(
                    code="mitigation_not_modelled",
                    path=f"mitigation.{field}",
                    message=f"engine {caps.engine!r} does not optimise {field}; the flag "
                    f"(currently {getattr(mit, field)}) has no effect",
                )
            )
    return out


def validate(scenario: Scenario | dict, network: Any) -> ValidationReport:
    errors: list[Issue] = []
    warnings: list[Issue] = []

    if not isinstance(scenario, Scenario):
        try:
            scenario = Scenario.model_validate(scenario)
        except ValidationError as exc:
            errors = [
                Issue(code="schema_error", path=_loc_to_path(e["loc"]), message=e["msg"])
                for e in exc.errors()
            ]
            return ValidationReport(valid=False, errors=errors, warnings=[])

    net = _network_dict(network)
    idx = _Index(net)

    if net.get("network_id") != scenario.dataset.network_id:
        errors.append(
            Issue(
                code="network_mismatch",
                path="dataset.network_id",
                message=f"scenario targets {scenario.dataset.network_id!r} but network is "
                f"{net.get('network_id')!r}",
            )
        )
    if scenario.dataset.sha256 is None:
        warnings.append(
            Issue(
                code="dataset_unpinned",
                path="dataset.sha256",
                message="dataset sha256 not pinned; results record the hash actually used",
            )
        )

    h = scenario.horizon
    if idx.snapshot_count is None:
        errors.append(
            Issue(code="horizon_out_of_range", path="horizon", message="network has no snapshots")
        )
    elif h.end > idx.snapshot_count:
        errors.append(
            Issue(
                code="horizon_out_of_range",
                path="horizon",
                message=f"horizon [{h.start}, {h.end}) exceeds the network's "
                f"{idx.snapshot_count} snapshots",
            )
        )

    storage_seen: dict[str, int] = {}
    outage_seen: dict[tuple[str, str], int] = {}
    for i, ev in enumerate(scenario.events):
        p = f"events[{i}]"
        window = getattr(ev, "window", None)
        if window is not None and not (window.start >= h.start and window.end <= h.end):
            errors.append(
                Issue(
                    code="window_out_of_range",
                    path=f"{p}.window",
                    message=f"window [{window.start}, {window.end}) is not inside horizon "
                    f"[{h.start}, {h.end})",
                )
            )

        if isinstance(ev, LineOutage | LinkOutage | GeneratorOutage | StorageState):
            target = _target_key(ev)
            if ev.asset_id not in idx.ids[target]:
                others = [k for k in idx.kind_of(ev.asset_id) if k != target]
                hint = (
                    f" (it exists as a {'/'.join(_COMPONENT_KEYS[k] for k in others)})"
                    if others
                    else ""
                )
                errors.append(
                    Issue(
                        code="unknown_asset",
                        path=f"{p}.asset_id",
                        message=f"no {_COMPONENT_KEYS[target]} with id {ev.asset_id!r} in "
                        f"network {net.get('network_id')!r}{hint}",
                    )
                )
            if isinstance(ev, StorageState):
                if ev.asset_id in storage_seen:
                    errors.append(
                        Issue(
                            code="conflicting_events",
                            path=f"{p}.asset_id",
                            message=f"storage_state for {ev.asset_id!r} already set by "
                            f"events[{storage_seen[ev.asset_id]}]",
                        )
                    )
                storage_seen.setdefault(ev.asset_id, i)
            else:
                key = (target, ev.asset_id)
                if key in outage_seen:
                    warnings.append(
                        Issue(
                            code="duplicate_outage",
                            path=f"{p}.asset_id",
                            message=f"{ev.asset_id!r} also outaged by events[{outage_seen[key]}]",
                        )
                    )
                outage_seen.setdefault(key, i)

        elif isinstance(ev, DemandMultiplier):
            if ev.buses is not None:
                for j, bus in enumerate(ev.buses):
                    if bus not in idx.ids["buses"]:
                        errors.append(
                            Issue(
                                code="unknown_asset",
                                path=f"{p}.buses[{j}]",
                                message=f"no bus with id {bus!r}",
                            )
                        )
                    elif bus not in idx.load_buses:
                        errors.append(
                            Issue(
                                code="no_loads",
                                path=f"{p}.buses[{j}]",
                                message=f"bus {bus!r} has no load to scale",
                            )
                        )
            if ev.value > 2.0 or ev.value < 0.5:
                warnings.append(
                    Issue(
                        code="large_multiplier",
                        path=f"{p}.value",
                        message=f"demand multiplier {ev.value} is far from 1; check plausibility",
                    )
                )

        elif isinstance(ev, RenewableAvailabilityMultiplier):
            if ev.carrier not in idx.carriers:
                errors.append(
                    Issue(
                        code="unknown_carrier",
                        path=f"{p}.carrier",
                        message=f"carrier {ev.carrier!r} not in network carriers "
                        f"{sorted(idx.carriers)}",
                    )
                )
            elif ev.carrier not in idx.variable_carriers:
                errors.append(
                    Issue(
                        code="no_variable_generators",
                        path=f"{p}.carrier",
                        message=f"no variable generators with carrier {ev.carrier!r}",
                    )
                )

    errors.extend(check_capabilities(scenario))
    warnings.extend(_mitigation_warnings(scenario))
    return ValidationReport(valid=not errors, errors=errors, warnings=warnings)
