"""Crisis definition (line/transformer outages, generator outages, demand multiplier) and its
application to a copy of an AdvisorNetwork's pandapower net."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandapower as pp

from gridstorm_advisor.network import AdvisorNetwork


class UnsupportedCrisis(ValueError):
    """Raised for crisis inputs the advisor cannot represent faithfully (never approximated)."""

    code = "unsupported_operation"


@dataclass
class Crisis:
    crisis_id: str
    title: str = ""
    line_outages: list[str] = field(default_factory=list)  # branch ids (lines or transformers)
    generator_outages: list[str] = field(default_factory=list)
    demand_multiplier: float = 1.0
    demand_buses: list[str] | None = None  # None = every load
    # Native crisis ids are branch ids; StormSpec additionally declares a component namespace.
    outage_components: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> Crisis:
        return cls(
            crisis_id=d["id"],
            title=d.get("title", ""),
            line_outages=list(d.get("line_outages", [])),
            generator_outages=list(d.get("generator_outages", [])),
            demand_multiplier=float(d.get("demand_multiplier", 1.0)),
            demand_buses=d.get("demand_buses"),
            outage_components=dict(d.get("outage_components", {})),
        )

    @classmethod
    def from_stormspec(cls, scenario: dict) -> Crisis:
        """Map a stormspec/1.0 scenario dict (single-snapshot semantics). Events that the advisor
        cannot represent (time windows, renewable/storage/link events) are rejected."""
        crisis = cls(crisis_id=scenario["id"], title=scenario.get("name", ""))
        multiplier_seen = False
        for i, ev in enumerate(scenario.get("events", [])):
            kind = ev.get("type")
            if ev.get("window") not in (None, {}):
                raise UnsupportedCrisis(
                    f"events[{i}]: time windows are not supported by the advisor"
                )
            if kind == "line_outage":
                crisis.line_outages.append(ev["asset_id"])
                component = ev.get("component", "line")
                if component not in ("line", "transformer"):
                    raise UnsupportedCrisis(f"events[{i}]: invalid outage component {component!r}")
                crisis.outage_components[ev["asset_id"]] = component
            elif kind == "generator_outage":
                crisis.generator_outages.append(ev["asset_id"])
            elif kind == "demand_multiplier":
                if multiplier_seen:
                    raise UnsupportedCrisis(f"events[{i}]: only one demand_multiplier is supported")
                multiplier_seen = True
                crisis.demand_multiplier = float(ev["value"])
                crisis.demand_buses = ev.get("buses")
            else:
                raise UnsupportedCrisis(f"events[{i}]: event type {kind!r} is not supported")
        return crisis

    def to_dict(self) -> dict:
        return {
            "id": self.crisis_id,
            "title": self.title,
            "line_outages": list(self.line_outages),
            "generator_outages": list(self.generator_outages),
            "demand_multiplier": self.demand_multiplier,
            "demand_buses": self.demand_buses,
            "outage_components": dict(self.outage_components),
        }


def validate(adv: AdvisorNetwork, crisis: Crisis) -> None:
    unknown = [b for b in crisis.line_outages if b not in adv.branches]
    unknown += [g for g in crisis.generator_outages if g not in adv.generators]
    unknown += [b for b in (crisis.demand_buses or []) if b not in adv.buses]
    if unknown:
        raise ValueError(f"unknown asset ids in crisis {crisis.crisis_id!r}: {unknown}")
    for bid, component in crisis.outage_components.items():
        ref = adv.branches[bid]
        # Equal-voltage MATPOWER transformers may be converted to pandapower impedances.
        actual = "transformer" if ref.table in ("trafo", "impedance") else "line"
        if component != actual:
            raise ValueError(f"asset {bid!r} is a {actual}, not a {component}")
    if not 0.0 < crisis.demand_multiplier <= 3.0:
        raise ValueError("demand_multiplier must be in (0, 3]")


def apply_crisis(adv: AdvisorNetwork, crisis: Crisis) -> tuple[pp.pandapowerNet, list[str]]:
    """Return (crisis net, notes). The input network is not mutated.

    If the outaged generator set contains every in-service slack (ext_grid), the in-service
    ``gen`` with the largest ``max_p_mw`` (ties: lowest index) becomes the slack; this is
    recorded in the notes. Single-slack balancing: the slack absorbs every imbalance.
    """
    validate(adv, crisis)
    net = adv.copy_net()
    notes: list[str] = []
    for bid in crisis.line_outages:
        ref = adv.branches[bid]
        net[ref.table].loc[ref.index, "in_service"] = False
    for gid in crisis.generator_outages:
        ref = adv.generators[gid]
        net[ref.table].loc[ref.index, "in_service"] = False
    slack_alive = bool(net.ext_grid.in_service.any()) or bool(
        (net.gen.in_service & net.gen.slack).any()
    )
    if not slack_alive:
        live = net.gen[net.gen.in_service]
        if live.empty:
            raise UnsupportedCrisis("no in-service generator left to act as slack")
        new_slack = int(live.sort_values("max_p_mw", ascending=False, kind="mergesort").index[0])
        net.gen.loc[new_slack, "slack"] = True
        notes.append(
            f"All slack generators outaged; {adv.gen_id_of('gen', new_slack)} (largest Pmax) "
            "takes over as the voltage-angle reference and balancing generator."
        )
    if crisis.demand_multiplier != 1.0:
        if crisis.demand_buses is None:
            mask = net.load.index
        else:
            pp_buses = {adv.buses[b] for b in crisis.demand_buses}
            mask = net.load.index[net.load.bus.isin(pp_buses)]
        net.load.loc[mask, "p_mw"] *= crisis.demand_multiplier
        net.load.loc[mask, "q_mvar"] *= crisis.demand_multiplier
        notes.append(
            f"Active and reactive demand scaled by {crisis.demand_multiplier} "
            "(constant power factor)."
        )
    return net, notes
