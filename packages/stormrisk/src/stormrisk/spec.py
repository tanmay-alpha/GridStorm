"""Sampling specification for a StormRisk Monte Carlo stress study (``stormrisk-sampling/1.0``).

All probabilities here are **modelled assumptions** supplied by the study author. StormRisk never
estimates outage probabilities from data; it propagates the ones it is given. Each outage class
therefore carries a free-text ``source`` (citation or justification) and a ``provenance`` class.
"""

from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SAMPLING_SCHEMA_VERSION = "stormrisk-sampling/1.0"

#: Component classes and the StormSpec event used to represent a whole-horizon outage.
#: canonical-grid list key -> StormSpec event type.
COMPONENT_EVENTS: dict[str, tuple[str, str]] = {
    "line": ("lines", "line_outage"),
    "transformer": ("transformers", "line_outage"),
    "link": ("links", "link_outage"),
    "generator": ("generators", "generator_outage"),
}

Component = Literal["line", "transformer", "link", "generator"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class OutageClass(_Strict):
    """Independent whole-horizon unavailability ``q`` for every asset matched by this class.

    An asset matches if its component type equals ``component`` and (if given) its carrier is in
    ``carriers`` and (if given) its id is in ``asset_ids``. An asset may match at most one class.
    """

    name: str = Field(min_length=1, max_length=100)
    component: Component
    unavailability: float = Field(
        ge=0.0, lt=1.0, description="Probability that the asset is out for the whole horizon."
    )
    carriers: list[str] | None = Field(default=None, description="null = any carrier.")
    asset_ids: list[str] | None = Field(default=None, description="null = all matching assets.")
    provenance: Literal["modeled", "estimated", "synthetic"] = "modeled"
    source: str = Field(min_length=1, max_length=1000, description="Citation / justification.")

    @field_validator("carriers", "asset_ids")
    @classmethod
    def _non_empty_unique(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            if not v:
                raise ValueError("must be null or a non-empty list")
            if len(set(v)) != len(v):
                raise ValueError("contains duplicates")
        return v


class DiscreteDemand(_Strict):
    """Demand multiplier drawn from a finite set of values with given probabilities."""

    kind: Literal["discrete"] = "discrete"
    values: list[Annotated[float, Field(gt=0.0, le=5.0)]] = Field(min_length=1)
    probabilities: list[Annotated[float, Field(ge=0.0, le=1.0)]] = Field(min_length=1)
    source: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def _normalised(self) -> DiscreteDemand:
        if len(self.values) != len(self.probabilities):
            raise ValueError("values and probabilities must have equal length")
        if len(set(self.values)) != len(self.values):
            raise ValueError("values contains duplicates")
        total = math.fsum(self.probabilities)
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"probabilities sum to {total!r}, expected 1")
        return self


class TruncatedNormalDemand(_Strict):
    """Demand multiplier ~ Normal(mean, std) truncated to [lower, upper] (rejection sampling),
    then rounded to a multiple of ``resolution`` so identical states can be collapsed."""

    kind: Literal["truncated_normal"] = "truncated_normal"
    mean: float = Field(gt=0.0, le=5.0)
    std: float = Field(gt=0.0, le=5.0)
    lower: float = Field(gt=0.0, le=5.0)
    upper: float = Field(gt=0.0, le=5.0)
    resolution: float = Field(default=0.01, gt=0.0, le=1.0)
    source: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def _ordered(self) -> TruncatedNormalDemand:
        if not self.lower < self.upper:
            raise ValueError("lower must be < upper")
        if not self.lower <= self.mean <= self.upper:
            raise ValueError("mean must lie in [lower, upper]")
        return self


DemandDistribution = Annotated[
    DiscreteDemand | TruncatedNormalDemand, Field(discriminator="kind")
]


class SamplingSpec(_Strict):
    schema_version: Literal["stormrisk-sampling/1.0"] = SAMPLING_SCHEMA_VERSION
    n_samples: int = Field(ge=2, le=1_000_000)
    seed: int = Field(ge=0, le=2**63 - 1)
    outage_classes: list[OutageClass] = Field(default_factory=list, max_length=100)
    demand_multiplier: DemandDistribution | None = None
    shed_tolerance_mwh: float = Field(
        default=1e-6,
        ge=0.0,
        description="A sample counts as a loss-of-load sample if unserved energy > this value.",
    )
    max_outages_per_sample: int = Field(
        default=200,
        ge=1,
        le=200,
        description="StormSpec allows <= 200 events; samples exceeding this are classified "
        "'invalid' (never truncated).",
    )

    @field_validator("outage_classes")
    @classmethod
    def _unique_names(cls, v: list[OutageClass]) -> list[OutageClass]:
        names = [c.name for c in v]
        if len(set(names)) != len(names):
            raise ValueError("outage class names must be unique")
        return v
