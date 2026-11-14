"""Job creation, result reuse, precomputed demo mode, serialisation and cancellation."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..access import audit, ensure_profile
from ..auth import Principal
from ..context import AppContext
from ..db.models import SimulationArtifact, SimulationJob, SimulationMetrics, utcnow
from ..errors import Conflict, ServiceUnavailable, Unprocessable
from ..validation import ValidationOutcome
from .results import parse_result, record_artifact, record_metrics, solver_summary

TERMINAL = ("completed", "failed", "cancelled", "timeout")
REUSABLE_OUTCOMES = ("feasible", "infeasible")


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat().replace("+00:00", "Z") if dt else None


def stage_event(stage: str, at: datetime | None = None, **extra: Any) -> dict[str, Any]:
    return {"stage": stage, "at": iso(at or utcnow()), **extra}


def job_to_dict(job: SimulationJob) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "scenario_id": job.scenario_id,
        "scenario_record_id": job.scenario_definition_id,
        "scenario_hash": job.scenario_hash,
        "network_id": job.network_id,
        "execution_mode": job.execution_mode,
        "reused": job.reused,
        "reused_from_job_id": str(job.reused_from_job_id) if job.reused_from_job_id else None,
        "status": job.status,
        "stage": job.stage,
        "stage_history": list(job.stage_history or []),
        "outcome": job.outcome,
        "solver": job.solver,
        "error": job.error,
        "cancel_requested": job.cancel_requested,
        "attempts": job.attempts,
        "created_at": iso(job.created_at),
        "started_at": iso(job.started_at),
        "finished_at": iso(job.finished_at),
        "result_sha256": job.result_sha256,
        "owner_id": str(job.owner_id) if job.owner_id else None,
        "visibility": job.visibility,
    }


def canonical_bytes(obj: Any) -> bytes:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _new_job(
    ctx: AppContext,
    outcome: ValidationOutcome,
    principal: Principal,
    *,
    scenario_record_id: str | None,
    visibility: str,
    execution_mode: str,
) -> SimulationJob:
    sc = outcome.scenario
    assert sc is not None and outcome.entry is not None and outcome.scenario_hash is not None
    return SimulationJob(
        id=uuid.uuid4(),
        scenario_id=sc.id,
        scenario_definition_id=scenario_record_id,
        scenario_hash=outcome.scenario_hash,
        spec=sc.model_dump(mode="json"),
        network_id=outcome.entry.id,
        network_version_id=ctx.network_versions.get(outcome.entry.id),
        execution_mode=execution_mode,
        owner_id=principal.user_id,
        visibility=visibility,
        status="queued",
        stage="queued",
        stage_history=[stage_event("queued")],
    )


def _store_scenario(ctx: AppContext, session: Session, job: SimulationJob) -> None:
    blob = ctx.store.put(canonical_bytes(job.spec), ext="json")
    record_artifact(session, job, "scenario", blob)


def find_reusable(session: Session, job: SimulationJob) -> SimulationJob | None:
    q = (
        select(SimulationJob)
        .where(
            SimulationJob.scenario_hash == job.scenario_hash,
            SimulationJob.network_id == job.network_id,
            SimulationJob.status == "completed",
            SimulationJob.execution_mode == job.execution_mode,
            SimulationJob.outcome.in_(REUSABLE_OUTCOMES),
            SimulationJob.result_sha256.is_not(None),
        )
        .order_by(SimulationJob.finished_at.desc())
        .limit(1)
    )
    if job.network_version_id is None:
        q = q.where(SimulationJob.network_version_id.is_(None))
    else:
        q = q.where(SimulationJob.network_version_id == job.network_version_id)
    return session.scalar(q)


def _complete_from(session: Session, job: SimulationJob, source: SimulationJob) -> None:
    now = utcnow()
    job.status, job.stage = "completed", "done"
    job.reused, job.reused_from_job_id = True, source.id
    job.outcome, job.solver, job.error = source.outcome, source.solver, source.error
    job.result_sha256 = source.result_sha256
    job.started_at = job.finished_at = now
    job.stage_history = [*job.stage_history, stage_event("done", now, reused_from=str(source.id))]
    session.add(job)
    session.flush()
    for art in session.scalars(
        select(SimulationArtifact).where(
            SimulationArtifact.job_id == source.id, SimulationArtifact.kind.in_(("result", "log"))
        )
    ).all():
        session.add(
            SimulationArtifact(
                job_id=job.id,
                kind=art.kind,
                storage_backend=art.storage_backend,
                storage_key=art.storage_key,
                sha256=art.sha256,
                bytes=art.bytes,
                content_type=art.content_type,
            )
        )
    m = session.get(SimulationMetrics, source.id)
    if m is not None:
        cols = {c.key: getattr(m, c.key) for c in SimulationMetrics.__table__.columns}
        cols.pop("created_at"), cols.pop("updated_at")
        cols["job_id"] = job.id
        session.add(SimulationMetrics(**cols))


def _complete_precomputed(ctx: AppContext, session: Session, job: SimulationJob) -> None:
    found = ctx.precomputed.find_simulation(job.scenario_hash)
    if found is None:
        raise Conflict(
            "this deployment runs in precomputed (demo) mode and has no precomputed result for "
            "this exact scenario; only preset scenarios with committed results can be shown",
            code="precomputed_result_unavailable",
            details={"scenario_hash": job.scenario_hash},
        )
    engine, artifact_id = found
    _, doc, verified = ctx.precomputed.load(engine, artifact_id)
    if verified is False:
        raise ServiceUnavailable(
            "precomputed artifact failed its payload_sha256 integrity check",
            code="artifact_integrity_error",
            details={"engine": engine, "artifact_id": artifact_id},
        )
    data = canonical_bytes(doc["payload"])
    result = parse_result(data)
    blob = ctx.store.put(data, ext="json")
    now = utcnow()
    job.status, job.stage = "completed", "done"
    job.outcome, job.solver = result["outcome"], solver_summary(result)
    job.result_sha256 = blob.sha256
    job.started_at = job.finished_at = now
    job.stage_history = [
        *job.stage_history,
        stage_event("done", now, precomputed_artifact=f"{engine}/{artifact_id}"),
    ]
    session.add(job)
    session.flush()
    record_artifact(session, job, "result", blob)
    record_metrics(session, job, result)


def create_job(
    ctx: AppContext,
    session: Session,
    principal: Principal,
    outcome: ValidationOutcome,
    *,
    scenario_record_id: str | None,
    visibility: str,
    reuse: bool,
) -> SimulationJob:
    ensure_profile(session, principal)
    mode = ctx.settings.execution_mode
    assert outcome.entry is not None and outcome.scenario_hash is not None
    if mode == "live" and not ctx.settings.live_execution(outcome.entry.id):
        if ctx.precomputed.find_simulation(outcome.scenario_hash) is None:
            raise Unprocessable(
                f"Live execution is unavailable for network {outcome.entry.id!r} on this "
                "deployment due to its memory budget, and no precomputed result matches this "
                "exact scenario. Select a supported network or a precomputed preset.",
                code="live_execution_unavailable",
                details={
                    "network_id": outcome.entry.id,
                    "live_networks": sorted(ctx.settings.live_networks),
                },
            )
        mode = "precomputed"
    job = _new_job(
        ctx,
        outcome,
        principal,
        scenario_record_id=scenario_record_id,
        visibility=visibility,
        execution_mode=mode,
    )
    if mode == "precomputed":
        _complete_precomputed(ctx, session, job)
    else:
        source = find_reusable(session, job) if reuse else None
        if source is not None:
            _complete_from(session, job, source)
        else:
            queued = session.scalar(
                select(func.count())
                .select_from(SimulationJob)
                .where(SimulationJob.status.in_(("queued", "running")))
            )
            if (queued or 0) >= ctx.settings.max_queued_jobs:
                raise ServiceUnavailable(
                    "the simulation queue is full; try again later",
                    code="queue_full",
                    details={"max_queued_jobs": ctx.settings.max_queued_jobs},
                    headers={"Retry-After": "60"},
                )
            if ctx.pool is None or not ctx.pool.active:
                raise ServiceUnavailable(
                    "no simulation workers are running on this server",
                    code="workers_unavailable",
                )
            session.add(job)
            session.flush()
    _store_scenario(ctx, session, job)
    audit(
        session,
        principal,
        "simulation.create",
        "simulation_job",
        job.id,
        {"scenario_hash": job.scenario_hash, "reused": job.reused, "mode": job.execution_mode},
    )
    session.commit()
    if job.status == "queued" and ctx.pool is not None:
        ctx.pool.notify()
    return job


def cancel_job(
    ctx: AppContext, session: Session, principal: Principal, job: SimulationJob
) -> SimulationJob:
    if job.status in TERMINAL:
        raise Conflict(
            f"job is already {job.status}",
            code="job_not_cancellable",
            details={"status": job.status},
        )
    now = utcnow()
    if job.status == "queued":
        res = session.execute(
            update(SimulationJob)
            .where(SimulationJob.id == job.id, SimulationJob.status == "queued")
            .values(
                status="cancelled",
                cancel_requested=True,
                finished_at=now,
                updated_at=now,
                error={"code": "cancelled", "message": "cancelled before execution started"},
            )
        )
        if res.rowcount == 0:  # claimed by a worker in the meantime
            session.rollback()
            return cancel_job(ctx, session, principal, session.get(SimulationJob, job.id))
    else:
        session.execute(
            update(SimulationJob)
            .where(SimulationJob.id == job.id)
            .values(cancel_requested=True, updated_at=now)
        )
    audit(session, principal, "simulation.cancel", "simulation_job", job.id, {})
    session.commit()
    if ctx.pool is not None:
        ctx.pool.request_cancel(job.id)
    session.refresh(job)
    return job
