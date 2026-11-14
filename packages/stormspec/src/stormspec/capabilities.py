"""Engine capability declarations.

Each engine adapter declares exactly what it can represent. :func:`stormspec.validate` rejects
anything outside the declaration with error code ``unsupported_operation`` — scenarios are never
silently approximated.

Window support per event type:

* ``"any"`` — the event may carry an arbitrary ``window`` inside the horizon.
* ``"full_horizon"`` — ``window`` must be null or cover the whole horizon (e.g. a PyPSA line outage
  is a topology change; making a line unavailable for part of a horizon cannot be represented by
  ``s_max_pu = 0`` because the line's KVL constraint would still couple the bus angles).
* ``"none"`` — ``window`` must be null (single-snapshot engines).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

WindowSupport = Literal["any", "full_horizon", "none"]


class EngineCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    engine: str
    formulations: tuple[str, ...]
    event_windows: dict[str, WindowSupport] = Field(
        description="Supported event types mapped to their window support."
    )
    max_snapshots: int | None = Field(
        default=None, description="Maximum horizon length; null = unbounded."
    )
    load_shedding: bool = Field(description="Engine can model load shedding at VOLL.")
    storage_dispatch: bool = Field(description="Engine optimises storage dispatch.")
    curtailment: bool = Field(description="Engine optimises renewable curtailment.")
    solvers: tuple[str | None, ...] = Field(description="Accepted execution.solver values.")
    notes: tuple[str, ...] = ()

    @property
    def event_types(self) -> frozenset[str]:
        return frozenset(self.event_windows)

    def accepts_window(self, event_type: str) -> bool:
        return self.event_windows.get(event_type, "none") != "none"


CAPABILITIES: dict[str, EngineCapabilities] = {
    "pypsa": EngineCapabilities(
        engine="pypsa",
        formulations=("lopf",),
        event_windows={
            "demand_multiplier": "any",
            "renewable_availability_multiplier": "any",
            "generator_outage": "any",
            "line_outage": "full_horizon",
            "link_outage": "full_horizon",
            "storage_state": "none",
        },
        max_snapshots=None,
        load_shedding=True,
        storage_dispatch=True,
        curtailment=True,
        solvers=("highs",),
        notes=(
            "Linear optimal power flow (DC-linearised network, KVL via cycle constraints).",
            "Line/transformer/link outages are topology changes for the whole horizon only.",
        ),
    ),
    "pandapower": EngineCapabilities(
        engine="pandapower",
        formulations=("ac_pf", "n_minus_1"),
        event_windows={
            "line_outage": "none",
            "generator_outage": "none",
            "demand_multiplier": "none",
        },
        max_snapshots=1,
        load_shedding=False,
        storage_dispatch=False,
        curtailment=False,
        solvers=(None, "newton_raphson", "nr"),
        notes=(
            "Single-snapshot AC power flow (Newton-Raphson); no dispatch optimisation.",
            "Load shedding cannot be modelled: mitigation.load_shedding.enabled must be false.",
        ),
    ),
    "grid2op": EngineCapabilities(
        engine="grid2op",
        formulations=("sequential",),
        event_windows={
            "line_outage": "any",
        },
        max_snapshots=None,
        load_shedding=False,
        storage_dispatch=False,
        curtailment=False,
        solvers=(None, "lightsim2grid", "pandapower"),
        notes=(
            "Sequential operation over Grid2Op chronics (5-minute steps from chronics start): "
            "forced line disconnection at window.start, reconnection blocked until window.end.",
            "Grid2Op environments (e.g. l2rpn-case14-sandbox) use their own asset ids "
            "(env.name_line); demand scaling is rejected because chronics are not re-dispatched.",
            "Load shedding cannot be modelled: mitigation.load_shedding.enabled must be false.",
        ),
    ),
}
