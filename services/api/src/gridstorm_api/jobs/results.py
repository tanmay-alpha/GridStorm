"""Persisting and loading gridstorm-result/1.0 documents for jobs."""

from __future__ import annotations

import json
import math
import uuid
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import SimulationArtifact, SimulationJob, SimulationMetrics
from ..errors import Conflict
from ..storage import ArtifactUnavailable, StoredBlob

if TYPE_CHECKING:
    from ..context import AppContext

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
    if job.status != "completed":
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
        raise ArtifactUnavailable("result artifact record missing")
    return art


def load_result_bytes(ctx: AppContext, session: Session, job: SimulationJob) -> bytes:
    try:
        art = result_artifact(session, job)
        return ctx.store.get(art.storage_key, expected_sha256=art.sha256)
    except ArtifactUnavailable as exc:
        raise result_unavailable(ctx, job) from exc


def load_result(ctx: AppContext, session: Session, job: SimulationJob) -> dict[str, Any]:
    result = json.loads(load_result_bytes(ctx, session, job))
    if not result.get("cost_basis"):
        basis = ctx.catalog.get(job.network_id).manifest.get("cost_basis")
        if basis:
            basis = dict(basis)
            shedding = ((job.spec or {}).get("mitigation") or {}).get("load_shedding") or {}
            basis["penalties"] = (
                [
                    {
                        "term": "load_shedding",
                        "value_per_mwh": shedding.get("voll_eur_per_mwh", 10000),
                        "unit": basis["price_unit"],
                        "nature": "penalty",
                        "description": "Legacy scenario VOLL interpreted in the dataset "
                        "money unit.",
                    }
                ]
                if shedding.get("enabled", True)
                else []
            )
            result["cost_basis"] = basis
            for field in ("assumptions", "warnings"):
                if field in result:
                    result[field] = [
                        text.replace(" EUR/MWh", f" {basis['price_unit']}")
                        for text in result[field]
                    ]
    return result


def recompute_path(job: SimulationJob) -> str:
    return f"/api/v1/simulations/{job.id}/recompute"


def can_recompute(ctx: AppContext, job: SimulationJob) -> bool:
    """A lost result can be regenerated: live solve allowed here, or a committed precomputed
    result exists for the exact scenario hash."""
    if ctx.settings.live_execution(job.network_id):
        return True
    return ctx.precomputed.find_simulation(job.scenario_hash) is not None


def result_unavailable(ctx: AppContext, job: SimulationJob) -> ArtifactUnavailable:
    """HTTP 410 for a completed job whose result blob is gone (never exposes storage keys)."""
    recoverable = can_recompute(ctx, job)
    hint = (
        f"Recompute it (POST {recompute_path(job)}) or re-run the scenario."
        if recoverable
        else "Live re-computation of this network is unavailable on this deployment."
    )
    return ArtifactUnavailable(
        "The stored result of this simulation is no longer available: it was lost from artifact "
        f"storage. Its metrics and metadata are kept. {hint}",
        details={
            "job_id": str(job.id),
            "kind": "result",
            "network_id": job.network_id,
            "scenario_id": job.scenario_id,
            "scenario_hash": job.scenario_hash,
            "scenario_record_id": job.scenario_definition_id,
            "result_sha256": job.result_sha256,
            "recoverable": recoverable,
            "recompute_path": recompute_path(job) if recoverable else None,
        },
    )


def result_availability(
    ctx: AppContext, session: Session, jobs: Sequence[SimulationJob]
) -> dict[uuid.UUID, bool]:
    """``{job.id: result blob present}`` (existence only, cached; integrity is verified on read)."""
    ids = [j.id for j in jobs if j.status == "completed" and j.result_sha256]
    keys: dict[uuid.UUID, str] = {}
    if ids:
        keys = dict(
            session.execute(
                select(SimulationArtifact.job_id, SimulationArtifact.storage_key).where(
                    SimulationArtifact.job_id.in_(ids), SimulationArtifact.kind == "result"
                )
            ).all()
        )
    present = ctx.store.exists_many(keys.values()) if keys else {}
    return {j.id: bool(j.id in keys and present.get(keys[j.id])) for j in jobs}
