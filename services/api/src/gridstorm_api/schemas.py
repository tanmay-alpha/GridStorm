"""Pydantic request/response models (OpenAPI surface of contract §6)."""

from __future__ import annotations

from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

T = TypeVar("T")

Provenance = Literal["observed", "estimated", "synthetic", "modeled", "calculated"]
JobStatus = Literal["queued", "running", "completed", "failed", "cancelled", "timeout"]
JobStage = Literal[
    "queued",
    "loading_network",
    "applying_scenario",
    "building_model",
    "solving",
    "postprocessing",
    "done",
]
Outcome = Literal["feasible", "infeasible", "error"]
Visibility = Literal["public", "private"]
AssetType = Literal[
    "buses",
    "lines",
    "transformers",
    "links",
    "generators",
    "loads",
    "storage_units",
    "stores",
    "carriers",
]


class _Open(BaseModel):
    model_config = ConfigDict(extra="allow")


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


# --- health -----------------------------------------------------------------------------------
class Health(BaseModel):
    status: Literal["ok"]
    version: str
    git_sha: str | None


class ReadyCheck(_Open):
    status: Literal["ok", "error", "skipped"]
    detail: str | None = None


class ReadyChecks(BaseModel):
    database: ReadyCheck
    storage: ReadyCheck
    solver: ReadyCheck
    datasets: ReadyCheck


class Ready(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: ReadyChecks


# --- networks ---------------------------------------------------------------------------------
class License(BaseModel):
    spdx: str | None = None
    url: str | None = None
    attribution: str | None = None
    redistribution: str | None = None


class NetworkSummary(BaseModel):
    id: str
    name: str
    description: str | None = None
    coordinate_kind: Literal["geographic", "schematic"]
    crs: str | None = None
    snapshots: dict[str, Any] | None = None
    counts: dict[str, int]
    capacity_by_carrier_mw: dict[str, float | None]
    peak_load_mw: float | None = None
    total_load_mwh: float | None = None
    license: License
    provenance_class: str | None = None
    engines: list[str]
    network_sha256: str | None = None
    has_network_file: bool
    live_execution: bool
    source: dict[str, Any] | None = None


class NetworkDetail(NetworkSummary):
    manifest: dict[str, Any]
    assumptions: list[str]
    field_provenance: dict[str, str]
    carriers: list[dict[str, Any]]


class AssetPage(Page[dict[str, Any]]):
    network_id: str
    type: AssetType
    field_provenance: dict[str, str] = Field(
        description="canonical field_provenance entries for this asset type"
    )


# --- scenarios --------------------------------------------------------------------------------
class Issue(BaseModel):
    code: str
    path: str
    message: str


class ValidationReport(BaseModel):
    valid: bool
    errors: list[Issue]
    warnings: list[Issue]
    scenario_hash: str | None = None
    network_id: str | None = None


_SPEC_DOC = "A stormspec/1.0 scenario (see packages/stormspec/schema/stormspec-1.0.schema.json)."


def _unwrap(data: Any) -> Any:
    """Accept ``{"scenario": spec, ...}`` or a bare spec (top-level ``schema_version``)."""
    if isinstance(data, dict) and "scenario" not in data and "schema_version" in data:
        return {"scenario": data}
    return data


class ScenarioValidateRequest(BaseModel):
    scenario: dict[str, Any] = Field(description=_SPEC_DOC)

    @model_validator(mode="before")
    @classmethod
    def accept_bare_spec(cls, data: Any) -> Any:
        return _unwrap(data)


class ScenarioCreate(BaseModel):
    scenario: dict[str, Any] = Field(description=_SPEC_DOC)
    visibility: Visibility | None = Field(
        default=None,
        description="Default: private for signed-in users; anonymous saves are always public.",
    )

    @model_validator(mode="before")
    @classmethod
    def accept_bare_spec(cls, data: Any) -> Any:
        return _unwrap(data)


class ScenarioRecord(BaseModel):
    id: str
    hash: str
    spec: dict[str, Any]
    preset: bool
    owner_id: str | None
    created_at: str
    name: str
    network_id: str
    visibility: Visibility


# --- simulations ------------------------------------------------------------------------------
class SimulationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str | None = Field(default=None, description="Preset or saved scenario record id")
    scenario: dict[str, Any] | None = Field(default=None, description=_SPEC_DOC)
    reuse: bool = Field(
        default=True,
        description="Reuse a completed result with the identical scenario hash and dataset "
        "version (the job is flagged reused=true).",
    )
    visibility: Visibility | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> SimulationCreate:
        if (self.scenario_id is None) == (self.scenario is None):
            raise ValueError("provide exactly one of scenario_id or scenario")
        return self


class StageEvent(_Open):
    stage: JobStage
    at: str


class SolverInfo(BaseModel):
    name: str | None = None
    version: str | None = None
    status: str | None = None
    termination_condition: str | None = None
    objective_eur: float | None = None
    wall_time_s: float | None = None


class JobError(BaseModel):
    code: str
    message: str


class Job(BaseModel):
    id: str
    scenario_id: str
    scenario_record_id: str | None
    scenario_hash: str
    network_id: str
    execution_mode: Literal["live", "precomputed"]
    reused: bool
    reused_from_job_id: str | None
    status: JobStatus
    stage: JobStage
    stage_history: list[StageEvent]
    outcome: Outcome | None
    solver: SolverInfo | None
    error: JobError | None
    cancel_requested: bool
    attempts: int
    created_at: str
    started_at: str | None
    finished_at: str | None
    result_sha256: str | None
    owner_id: str | None
    visibility: Visibility


class JobMetrics(BaseModel):
    job_id: str
    network_id: str
    scenario_hash: str
    outcome: Outcome | None
    provenance: Literal["modeled"] = "modeled"
    metrics: dict[str, Any]
    solver: SolverInfo | None


class StoredArtifact(BaseModel):
    kind: Literal["result", "scenario", "log"]
    sha256: str
    bytes: int
    content_type: str
    storage_backend: str
    storage_key: str
    created_at: str


class StoredArtifactList(BaseModel):
    job_id: str
    items: list[StoredArtifact]


# --- comparisons ------------------------------------------------------------------------------
class ComparisonCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline_job_id: str
    scenario_job_id: str
    visibility: Visibility | None = None


class Comparison(BaseModel):
    id: str
    baseline_job_id: str
    scenario_job_id: str
    network_id: str
    owner_id: str | None
    visibility: Visibility
    created_at: str
    report_sha256: str
    report: dict[str, Any]


# --- precomputed artifacts --------------------------------------------------------------------
class PrecomputedArtifact(_Open):
    engine: str
    artifact_id: str
    kind: str | None
    network_id: str | None
    title: str | None
    bytes: int | None
    available: bool
