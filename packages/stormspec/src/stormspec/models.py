"""StormSpec 1.0 scenario models (Pydantic v2).

A StormSpec scenario is an engine-agnostic, typed description of a crisis event applied to a
network dataset. Structural rules (types, ranges, slugs) are enforced here; rules that need the
network or engine capabilities (asset ids, horizon bounds, windows inside the horizon, engine
support) are enforced by :func:`stormspec.validate`.

Conventions
-----------
* ``horizon.start`` / ``horizon.snapshots`` index the network's snapshot axis (0-based).
* ``window`` values are **absolute** network snapshot indices forming the half-open interval
  ``[start, end)``; they must lie inside the horizon. ``window: null`` means the whole horizon.
* Multipliers are dimensionless.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "stormspec/1.0"
SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]{2,63}$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"

#: Upper bound on the horizon length (one leap year of hourly snapshots).
MAX_HORIZON_SNAPSHOTS = 8784


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class Window(_Strict):
    """Half-open interval ``[start, end)`` of absolute network snapshot indices."""

    start: int = Field(ge=0, description="First affected snapshot index (inclusive).")
    end: int = Field(gt=0, description="Snapshot index after the last affected one (exclusive).")

    @model_validator(mode="after")
    def _ordered(self) -> Window:
        if self.end <= self.start:
            raise ValueError(f"window.end ({self.end}) must be greater than start ({self.start})")
        return self

    def covers(self, start: int, end: int) -> bool:
        """True if this window covers the whole interval ``[start, end)``."""
        return self.start <= start and self.end >= end


class Dataset(_Strict):
    network_id: str = Field(pattern=SLUG_PATTERN, description="Network id in data/networks.")
    sha256: str | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
        description="sha256 of the network.nc the scenario was authored against; null = unpinned.",
    )


class Horizon(_Strict):
    start: int = Field(default=0, ge=0, description="First snapshot index (0-based).")
    snapshots: int = Field(
        ge=1, le=MAX_HORIZON_SNAPSHOTS, description="Number of consecutive snapshots."
    )

    @property
    def end(self) -> int:
        """Exclusive end index."""
        return self.start + self.snapshots


AssetId = Annotated[str, Field(min_length=1, max_length=200)]


class DemandMultiplier(_Strict):
    """Scale electrical demand (all loads, or loads at ``buses``) by ``value`` within ``window``."""

    type: Literal["demand_multiplier"] = "demand_multiplier"
    value: float = Field(gt=0.0, le=5.0, description="Dimensionless demand multiplier.")
    buses: list[AssetId] | None = Field(
        default=None, description="Bus ids whose loads are scaled; null = all loads."
    )
    window: Window | None = None

    @field_validator("buses")
    @classmethod
    def _non_empty_unique(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            if not v:
                raise ValueError("buses must be null (all) or a non-empty list")
            if len(set(v)) != len(v):
                raise ValueError("buses contains duplicates")
        return v


class RenewableAvailabilityMultiplier(_Strict):
    """Scale the per-unit availability of variable generators of ``carrier`` (e.g. wind)."""

    type: Literal["renewable_availability_multiplier"] = "renewable_availability_multiplier"
    carrier: str = Field(min_length=1, max_length=100)
    value: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Multiplier on availability (p_max_pu); <=1 so availability stays within [0,1]."
        ),
    )
    window: Window | None = None


class LineOutage(_Strict):
    """Take an AC line or a transformer out of service.

    ``component`` selects which list ``asset_id`` is resolved in: some datasets (e.g. SciGRID)
    reuse the same name for a line and a transformer.
    """

    type: Literal["line_outage"] = "line_outage"
    asset_id: AssetId
    component: Literal["line", "transformer"] = Field(
        default="line", description="Component list in which asset_id is resolved."
    )
    window: Window | None = Field(
        default=None,
        description="null = whole horizon. Engines declare whether partial windows are supported.",
    )


class LinkOutage(_Strict):
    """Take a controllable link (e.g. HVDC) out of service."""

    type: Literal["link_outage"] = "link_outage"
    asset_id: AssetId
    window: Window | None = None


class GeneratorOutage(_Strict):
    """Force a generator's available capacity to zero within ``window``."""

    type: Literal["generator_outage"] = "generator_outage"
    asset_id: AssetId
    window: Window | None = None


class StorageState(_Strict):
    """Set the initial state of charge of a storage unit as a fraction of its energy capacity."""

    type: Literal["storage_state"] = "storage_state"
    asset_id: AssetId
    initial_soc_fraction: float = Field(ge=0.0, le=1.0)


Event = Annotated[
    DemandMultiplier
    | RenewableAvailabilityMultiplier
    | LineOutage
    | LinkOutage
    | GeneratorOutage
    | StorageState,
    Field(discriminator="type"),
]

EVENT_TYPES: tuple[str, ...] = (
    "demand_multiplier",
    "renewable_availability_multiplier",
    "line_outage",
    "link_outage",
    "generator_outage",
    "storage_state",
)


class LoadShedding(_Strict):
    enabled: bool = True
    voll_eur_per_mwh: float = Field(
        default=10000.0,
        gt=0.0,
        le=1.0e6,
        description="Value of lost load used as marginal cost of the load-shedding generators.",
    )


class Mitigation(_Strict):
    storage_dispatch: bool = Field(
        default=True, description="false => storage units are held at zero dispatch."
    )
    curtailment: bool = Field(
        default=True, description="false => variable renewables must produce all available power."
    )
    load_shedding: LoadShedding = Field(default_factory=LoadShedding)


class SolverOptions(_Strict):
    time_limit_s: float = Field(default=120.0, gt=0.0, le=3600.0)
    threads: int = Field(default=1, ge=1, le=64)


Engine = Literal["pypsa", "pandapower", "grid2op"]
Formulation = Literal["lopf", "ac_pf", "n_minus_1", "sequential"]


class Execution(_Strict):
    engine: Engine
    formulation: Formulation
    solver: str | None = Field(default="highs", max_length=50)
    solver_options: SolverOptions = Field(default_factory=SolverOptions)
    deterministic: bool = True
    seed: int = Field(default=0, ge=0, le=2**31 - 1)


class Scenario(_Strict):
    """Root StormSpec 1.0 model."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        title="StormSpec scenario",
        json_schema_extra={"description": "GridStorm crisis-scenario specification, version 1.0."},
    )

    schema_version: Literal["stormspec/1.0"] = SCHEMA_VERSION
    id: str = Field(pattern=SLUG_PATTERN)
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    dataset: Dataset
    horizon: Horizon
    events: list[Event] = Field(default_factory=list, max_length=200)
    mitigation: Mitigation = Field(default_factory=Mitigation)
    execution: Execution
    assumptions: list[Annotated[str, Field(max_length=1000)]] = Field(
        default_factory=list, max_length=100
    )
