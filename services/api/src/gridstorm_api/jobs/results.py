"""Persisting and loading gridstorm-result/1.0 documents for jobs."""

from __future__ import annotations

import json
import math
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import SimulationArtifact, SimulationJob, SimulationMetrics
from ..errors import Conflict, NotFound
from ..storage import ArtifactStore, StoredBlob

RESULT_SCHEMA = "gridstorm-result/1.0"

_METRIC_COLUMNS = (
    "total_load_mwh",
    "served_load_mwh",
    "unserved_energy_mwh",
    "peak_load_shed_mw",
    "total_system_cost_eur",
    "curtailment_mwh",
    "max_line_loading_pct",
    "co2_emissions_t",
    "balance_residual_max_mw",
)


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    f = float(value)
    return f if math.isfinite(f) else None


def record_artifact(
    session: Session, job: SimulationJob, kind: str, blob: StoredBlob
) -> SimulationArtifact:
    existing = session.scalar(
        select(SimulationArtifact).where(
            SimulationArtifact.job_id == job.id, SimulationArtifact.kind == kind
        )
    )
    if existing is not None:
        session.delete(existing)
        session.flush()
    row = SimulationArtifact(
        job_id=job.id,
        kind=kind,
        storage_backend=blob.backend,
        storage_key=blob.key,
        sha256=blob.sha256,
        bytes=blob.bytes,
        content_type=blob.content_type,
    )
    session.add(row)
    return row


def record_metrics(session: Session, job: SimulationJob, result: dict[str, Any]) -> None:
    metrics = result.get("metrics") or {}
    values = {c: _num(metrics.get(c)) for c in _METRIC_COLUMNS}
    congested = metrics.get("congested_line_count")
    row = session.get(SimulationMetrics, job.id) or SimulationMetrics(job_id=job.id)
    row.network_id = job.network_id
    row.scenario_hash = job.scenario_hash
    row.outcome = result.get("outcome")
    row.congested_line_count = congested if isinstance(congested, int) else None
    row.metrics = metrics
    for k, v in values.items():
        setattr(row, k, v)
    session.add(row)


def parse_result(data: bytes) -> dict[str, Any]:
    doc = json.loads(data)
    if not isinstance(doc, dict) or doc.get("schema_version") != RESULT_SCHEMA:
        raise ValueError(f"engine output is not {RESULT_SCHEMA}")
    if doc.get("outcome") not in ("feasible", "infeasible", "error"):
        raise ValueError(f"engine output has invalid outcome {doc.get('outcome')!r}")
    return doc


def solver_summary(result: dict[str, Any]) -> dict[str, Any] | None:
    solver = result.get("solver")
    if not isinstance(solver, dict):
        return None
    keys = ("name", "version", "status", "termination_condition", "objective_eur", "wall_time_s")
    return {k: solver.get(k) for k in keys}


def result_artifact(session: Session, job: SimulationJob) -> SimulationArtifact:
    if job.status != "completed" or not job.result_sha256:
        raise Conflict(
            f"job {job.id} has no result (status {job.status})",
            code="result_not_available",
            details={"job_id": str(job.id), "status": job.status},
        )
    art = session.scalar(
        select(SimulationArtifact).where(
            SimulationArtifact.job_id == job.id, SimulationArtifact.kind == "result"
        )
    )
    if art is None:
        raise NotFound("result artifact record missing", code="artifact_not_found")
    return art


def load_result_bytes(session: Session, store: ArtifactStore, job: SimulationJob) -> bytes:
    art = result_artifact(session, job)
    return store.get(art.storage_key, expected_sha256=art.sha256)


def load_result(session: Session, store: ArtifactStore, job: SimulationJob) -> dict[str, Any]:
    return json.loads(load_result_bytes(session, store, job))
