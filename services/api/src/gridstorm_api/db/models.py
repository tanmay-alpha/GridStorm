"""SQLAlchemy 2.x ORM models.

These mirror ``database/migrations/*.sql`` (the authoritative Postgres/Supabase schema) column by
column; ``tests/test_postgres_migrations.py`` reflects the migrated schema and checks that both
agree. On SQLite (local dev/tests) the schema is created from this metadata instead.

``network_assets`` from the original brief is intentionally NOT created: asset rows are served
straight from the committed ``canonical.json`` files, so a table would only duplicate them.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Text,
    TypeDecorator,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """``timestamptz`` on Postgres; on SQLite naive values are stored/returned as UTC."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


JSONType = JSON().with_variant(JSONB(), "postgresql")
BigIntPK = BigInteger().with_variant(Integer(), "sqlite")

NAMING = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

JOB_STATUSES = ("queued", "running", "completed", "failed", "cancelled", "timeout")
JOB_STAGES = (
    "queued",
    "loading_network",
    "applying_scenario",
    "building_model",
    "solving",
    "postprocessing",
    "done",
)
OUTCOMES = ("feasible", "infeasible", "error")
VISIBILITIES = ("public", "private")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} in ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, onupdate=utcnow, nullable=False
    )


class Profile(Timestamped, Base):
    """One row per Supabase auth user that has interacted with the API (id = ``auth.users.id``)."""

    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(Text)


class NetworkDataset(Timestamped, Base):
    __tablename__ = "network_datasets"
    __table_args__ = (
        CheckConstraint(_in("coordinate_kind", ("geographic", "schematic")), name="coordinate_kind"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    coordinate_kind: Mapped[str] = mapped_column(Text, nullable=False)
    provenance_class: Mapped[str | None] = mapped_column(Text)
    license_spdx: Mapped[str | None] = mapped_column(Text)
    redistribution: Mapped[str | None] = mapped_column(Text)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class NetworkVersion(Timestamped, Base):
    __tablename__ = "network_versions"
    __table_args__ = (UniqueConstraint("network_id", "canonical_sha256", "manifest_sha256"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    network_id: Mapped[str] = mapped_column(
        Text, ForeignKey("network_datasets.id", ondelete="CASCADE"), nullable=False
    )
    network_sha256: Mapped[str | None] = mapped_column(Text)
    canonical_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    retrieved_at: Mapped[str | None] = mapped_column(Text)


class DatasetSource(Timestamped, Base):
    __tablename__ = "dataset_sources"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    network_id: Mapped[str] = mapped_column(
        Text, ForeignKey("network_datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    network_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("network_versions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    url: Mapped[str | None] = mapped_column(Text)
    version: Mapped[str | None] = mapped_column(Text)
    publication_date: Mapped[str | None] = mapped_column(Text)
    upstream_commit: Mapped[str | None] = mapped_column(Text)
    license_spdx: Mapped[str | None] = mapped_column(Text)
    license_url: Mapped[str | None] = mapped_column(Text)
    attribution: Mapped[str | None] = mapped_column(Text)
    redistribution: Mapped[str | None] = mapped_column(Text)


class IngestionRun(Timestamped, Base):
    __tablename__ = "ingestion_runs"
    __table_args__ = (CheckConstraint(_in("status", ("succeeded", "failed")), name="status"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    network_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("network_datasets.id", ondelete="CASCADE"), index=True
    )
    network_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("network_versions.id", ondelete="SET NULL")
    )
    tool: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)


class ScenarioDefinition(Timestamped, Base):
    __tablename__ = "scenario_definitions"
    __table_args__ = (
        CheckConstraint(_in("visibility", VISIBILITIES), name="visibility"),
        CheckConstraint("not is_preset or owner_id is null", name="preset_unowned"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    spec_id: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    network_id: Mapped[str] = mapped_column(
        Text, ForeignKey("network_datasets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    scenario_hash: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    spec: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    is_preset: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    visibility: Mapped[str] = mapped_column(Text, nullable=False, default="public")
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )


class SimulationJob(Timestamped, Base):
    __tablename__ = "simulation_jobs"
    __table_args__ = (
        CheckConstraint(_in("status", JOB_STATUSES), name="status"),
        CheckConstraint(_in("stage", JOB_STAGES), name="stage"),
        CheckConstraint(f"outcome is null or {_in('outcome', OUTCOMES)}", name="outcome"),
        CheckConstraint(_in("execution_mode", ("live", "precomputed")), name="execution_mode"),
        CheckConstraint(_in("visibility", VISIBILITIES), name="visibility"),
        Index("ix_simulation_jobs_status_created_at", "status", "created_at"),
        Index("ix_simulation_jobs_scenario_hash_status", "scenario_hash", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    scenario_id: Mapped[str] = mapped_column(Text, nullable=False)
    scenario_definition_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("scenario_definitions.id", ondelete="SET NULL")
    )
    scenario_hash: Mapped[str] = mapped_column(Text, nullable=False)
    spec: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    network_id: Mapped[str] = mapped_column(
        Text, ForeignKey("network_datasets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    network_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("network_versions.id", ondelete="SET NULL")
    )
    execution_mode: Mapped[str] = mapped_column(Text, nullable=False, default="live")
    reused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reused_from_job_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("simulation_jobs.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="queued")
    stage: Mapped[str] = mapped_column(Text, nullable=False, default="queued")
    stage_history: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONType, nullable=False, default=list
    )
    outcome: Mapped[str | None] = mapped_column(Text)
    solver: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    worker_id: Mapped[str | None] = mapped_column(Text)
    heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("profiles.id", ondelete="SET NULL"), index=True
    )
    visibility: Mapped[str] = mapped_column(Text, nullable=False, default="public")
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    result_sha256: Mapped[str | None] = mapped_column(Text)


class SimulationMetrics(Timestamped, Base):
    __tablename__ = "simulation_metrics"

    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("simulation_jobs.id", ondelete="CASCADE"), primary_key=True
    )
    network_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    scenario_hash: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    outcome: Mapped[str | None] = mapped_column(Text)
    total_load_mwh: Mapped[float | None] = mapped_column(Double)
    served_load_mwh: Mapped[float | None] = mapped_column(Double)
    unserved_energy_mwh: Mapped[float | None] = mapped_column(Double)
    peak_load_shed_mw: Mapped[float | None] = mapped_column(Double)
    total_system_cost_eur: Mapped[float | None] = mapped_column(Double)
    curtailment_mwh: Mapped[float | None] = mapped_column(Double)
    max_line_loading_pct: Mapped[float | None] = mapped_column(Double)
    congested_line_count: Mapped[int | None] = mapped_column(Integer)
    co2_emissions_t: Mapped[float | None] = mapped_column(Double)
    balance_residual_max_mw: Mapped[float | None] = mapped_column(Double)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)


class SimulationArtifact(Timestamped, Base):
    __tablename__ = "simulation_artifacts"
    __table_args__ = (
        UniqueConstraint("job_id", "kind"),
        CheckConstraint(_in("kind", ("result", "scenario", "log")), name="kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("simulation_jobs.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    storage_backend: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)


class ComparisonReport(Timestamped, Base):
    __tablename__ = "comparison_reports"
    __table_args__ = (CheckConstraint(_in("visibility", VISIBILITIES), name="visibility"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    baseline_job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("simulation_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scenario_job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("simulation_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    network_id: Mapped[str] = mapped_column(
        Text, ForeignKey("network_datasets.id", ondelete="RESTRICT"), nullable=False
    )
    report: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    report_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    visibility: Mapped[str] = mapped_column(Text, nullable=False, default="public")


class AuditEvent(Base):
    """Append-only audit trail (no ``updated_at``: rows are never modified)."""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_target", "target_type", "target_id"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, nullable=False, index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid())
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
