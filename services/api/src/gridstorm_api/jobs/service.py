"""Job creation, result reuse, recompute, precomputed demo mode, serialisation and cancellation."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..access import audit, ensure_profile, visible
from ..auth import Principal
from ..context import AppContext
from ..db.models import (
    AuditEvent,
    SimulationArtifact,
    SimulationJob,
    SimulationMetrics,
    utcnow,
)
from ..errors import APIError, Conflict, ServiceUnavailable, Unprocessable
from ..validation import ValidationOutcome, validate_spec
from .results import (
    parse_result,
    record_artifact,
    record_metrics,
    result_availability,
    solver_summary,
)

log = logging.getLogger("gridstorm_api.jobs")

TERMINAL = ("completed", "failed", "cancelled", "timeout")
REUSABLE_OUTCOMES = ("feasible", "infeasible")
# Most recent identical completed jobs inspected for reuse (reused jobs share one blob).
REUSE_CANDIDATES = 5
ACTIVE = ("queued", "running")
_JOB_CREATE_ACTIONS = ("simulation.create", "simulation.recompute")


def client_fingerprint(client_key: str) -> str:
    """Pseudonymous anonymous-client id kept in the server-only audit trail (never the raw IP)."""
    return hashlib.sha256(f"gridstorm-client:{client_key}".encode()).hexdigest()[:32]


def active_jobs_of(session: Session, principal: Principal, fingerprint: str | None) -> int:
    """Queued+running jobs of a signed-in owner, or of an anonymous client fingerprint."""
    if principal.user_id is not None:
        return (
            session.scalar(
                select(func.count())
                .select_from(SimulationJob)
                .where(
                    SimulationJob.owner_id == principal.user_id, SimulationJob.status.in_(ACTIVE)
                )
            )
            or 0
        )
    if fingerprint is None:
        return 0
    # Ownerless active jobs are bounded by GRIDSTORM_MAX_QUEUED_JOBS, so this stays small.
    ids = session.scalars(
        select(SimulationJob.id).where(
            SimulationJob.owner_id.is_(None), SimulationJob.status.in_(ACTIVE)
        )
    ).all()
    if not ids:
        return 0
    details = session.scalars(
        select(AuditEvent.details).where(
            AuditEvent.target_type == "simulation_job",
            AuditEvent.action.in_(_JOB_CREATE_ACTIONS),
            AuditEvent.target_id.in_([str(i) for i in ids]),
        )
    ).all()
    return sum(1 for d in details if (d or {}).get("client") == fingerprint)


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat().replace("+00:00", "Z") if dt else None


def stage_event(stage: str, at: datetime | None = None, **extra: Any) -> dict[str, Any]:
    return {"stage": stage, "at": iso(at or utcnow()), **extra}


def recomputed_from(job: SimulationJob) -> str | None:
    """Provenance of a recompute job, recorded on its first (``queued``) stage event."""
    history = job.stage_history or []
    return history[0].get("recomputed_from") if history else None


def job_to_dict(job: SimulationJob, *, result_available: bool) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "scenario_id": job.scenario_id,
        "scenario_record_id": job.scenario_definition_id,
        "scenario_hash": job.scenario_hash,
        "network_id": job.network_id,
        "execution_mode": job.execution_mode,
        "reused": job.reused,
        "reused_from_job_id": str(job.reused_from_job_id) if job.reused_from_job_id else None,
        "recomputed_from_job_id": recomputed_from(job),
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
        "result_available": result_available,
        "owner_id": str(job.owner_id) if job.owner_id else None,
        "visibility": job.visibility,
    }


def jobs_to_dicts(
    ctx: AppContext, session: Session, jobs: Sequence[SimulationJob]
) -> list[dict[str, Any]]:
    available = result_availability(ctx, session, jobs)
    return [job_to_dict(j, result_available=available[j.id]) for j in jobs]


def job_json(ctx: AppContext, session: Session, job: SimulationJob) -> dict[str, Any]:
    return jobs_to_dicts(ctx, session, [job])[0]


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
    queued_extra: dict[str, Any] | None = None,
) -> SimulationJob:
    sc = outcome.scenario
    assert sc is not None and outcome.entry is not None and outcome.scenario_hash is not None
    # Explicit, not the column default (evaluated at flush): reused/precomputed completions set
    # started_at/finished_at before the INSERT and must not precede created_at (VER-009).
    now = utcnow()
    return SimulationJob(
        id=uuid.uuid4(),
        created_at=now,
        updated_at=now,
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
        stage_history=[stage_event("queued", now, **(queued_extra or {}))],
    )


def _store_scenario(ctx: AppContext, session: Session, job: SimulationJob) -> None:
    blob = ctx.store.put(canonical_bytes(job.spec), ext="json")
    record_artifact(session, job, "scenario", blob)


def find_reusable(
    ctx: AppContext, session: Session, principal: Principal, job: SimulationJob
) -> tuple[SimulationJob, SimulationArtifact] | None:
    """Latest identical completed job the principal may read whose result blob is still stored
    and verifies against its sha256; ``None`` means run fresh.

    Only visible jobs qualify, so reuse never reveals (or links to) another user's private job.
    """
    q = (
        select(SimulationJob)
        .where(
            SimulationJob.scenario_hash == job.scenario_hash,
            SimulationJob.network_id == job.network_id,
            SimulationJob.status == "completed",
            SimulationJob.execution_mode == job.execution_mode,
            SimulationJob.outcome.in_(REUSABLE_OUTCOMES),
            SimulationJob.result_sha256.is_not(None),
            visible(SimulationJob, principal),
        )
        .order_by(SimulationJob.finished_at.desc())
        .limit(REUSE_CANDIDATES)
    )
    if job.network_version_id is None:
        q = q.where(SimulationJob.network_version_id.is_(None))
    else:
        q = q.where(SimulationJob.network_version_id == job.network_version_id)
    rejected: set[str] = set()
    for source in session.scalars(q).all():
        art = session.scalar(
            select(SimulationArtifact).where(
                SimulationArtifact.job_id == source.id, SimulationArtifact.kind == "result"
            )
        )
        if art is None or art.sha256 != source.result_sha256 or art.storage_key in rejected:
            continue
        try:
            ctx.store.get(art.storage_key, expected_sha256=art.sha256)
        except APIError as exc:  # unavailable, corrupt or store outage: not reusable
            log.warning("job %s not reusable: %s", source.id, exc.code)
            rejected.add(art.storage_key)
            continue
        return source, art
    return None


def _complete_from(
    ctx: AppContext,
    session: Session,
    job: SimulationJob,
    source: SimulationJob,
    result_art: SimulationArtifact,
) -> None:
    now = utcnow()
    job.status, job.stage = "completed", "done"
    job.reused, job.reused_from_job_id = True, source.id
    job.outcome, job.solver, job.error = source.outcome, source.solver, source.error
    job.result_sha256 = source.result_sha256
    job.started_at = job.finished_at = now
    job.stage_history = [*job.stage_history, stage_event("done", now, reused_from=str(source.id))]
    session.add(job)
    session.flush()
    # The result was just verified in the current store: record that backend, not the source's.
    session.add(
        SimulationArtifact(
            job_id=job.id,
            kind="result",
            storage_backend=ctx.store.backend,
            storage_key=result_art.storage_key,
            sha256=result_art.sha256,
            bytes=result_art.bytes,
            content_type=result_art.content_type,
        )
    )
    log_art = session.scalar(
        select(SimulationArtifact).where(
            SimulationArtifact.job_id == source.id, SimulationArtifact.kind == "log"
        )
    )
    if log_art is not None:
        session.add(
            SimulationArtifact(
                job_id=job.id,
                kind="log",
                storage_backend=log_art.storage_backend,
                storage_key=log_art.storage_key,
                sha256=log_art.sha256,
                bytes=log_art.bytes,
                content_type=log_art.content_type,
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
    recompute_of: SimulationJob | None = None,
    claim_for: str | None = None,
    client_key: str | None = None,
) -> SimulationJob:
    """Create a job: precomputed completion, verified reuse, or a queued live run.

    ``recompute_of`` records recompute provenance and disables reuse. ``claim_for`` (recovery CLI)
    inserts a live job already claimed by that worker id, so no API worker can take it.
    ``client_key`` (the rate-limit identity of an HTTP caller) enforces
    ``GRIDSTORM_MAX_ACTIVE_JOBS_PER_CLIENT`` for anonymous callers; signed-in callers are counted
    by owner. Only jobs that actually enqueue are capped (reuse/precomputed never are).
    """
    ensure_profile(session, principal)
    fingerprint = (
        client_fingerprint(client_key) if client_key and principal.user_id is None else None
    )
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
    provenance: dict[str, Any] = {}
    if recompute_of is not None:
        reuse = False
        provenance = {
            "recomputed_from": str(recompute_of.id),
            "lost_result_sha256": recompute_of.result_sha256,
        }
    job = _new_job(
        ctx,
        outcome,
        principal,
        scenario_record_id=scenario_record_id,
        visibility=visibility,
        execution_mode=mode,
        queued_extra=provenance,
    )
    if mode == "precomputed":
        _complete_precomputed(ctx, session, job)
    else:
        found = find_reusable(ctx, session, principal, job) if reuse else None
        if found is not None:
            _complete_from(ctx, session, job, *found)
        else:
            queued = session.scalar(
                select(func.count())
                .select_from(SimulationJob)
                .where(SimulationJob.status.in_(ACTIVE))
            )
            cap = ctx.settings.max_active_jobs_per_client
            if claim_for is None and cap > 0 and (principal.user_id or fingerprint):
                active = active_jobs_of(session, principal, fingerprint)
                if active >= cap:
                    raise APIError(
                        f"you already have {active} simulation(s) queued or running; at most "
                        f"{cap} per user or client may be active at a time. Wait for one to "
                        "finish or cancel it, then submit again.",
                        code="too_many_active_jobs",
                        status_code=429,
                        details={"active_jobs": active, "limit": cap},
                    )
            if (queued or 0) >= ctx.settings.max_queued_jobs:
                raise ServiceUnavailable(
                    "the simulation queue is full; try again later",
                    code="queue_full",
                    details={"max_queued_jobs": ctx.settings.max_queued_jobs},
                    headers={"Retry-After": "60"},
                )
            if claim_for is not None:
                now = utcnow()
                job.status, job.worker_id, job.attempts = "running", claim_for, 1
                job.started_at = job.heartbeat_at = now
            elif ctx.pool is None or not ctx.pool.active:
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
        "simulation.recompute" if recompute_of is not None else "simulation.create",
        "simulation_job",
        job.id,
        {
            "scenario_hash": job.scenario_hash,
            "reused": job.reused,
            "mode": job.execution_mode,
            **provenance,
            **({"client": fingerprint} if fingerprint else {}),
        },
    )
    session.commit()
    if job.status == "queued" and ctx.pool is not None:
        ctx.pool.notify()
    return job


def recompute_job(
    ctx: AppContext,
    session: Session,
    principal: Principal,
    source: SimulationJob,
    *,
    force: bool = False,
    claim_for: str | None = None,
    client_key: str | None = None,
) -> SimulationJob:
    """Re-run a completed job's stored scenario spec as a NEW job (``recomputed_from`` = source).

    The source job is never modified: its recorded ``result_sha256`` stays as the provenance of
    the lost bytes, the new job records its own. Identical bytes share the content address, so
    a byte-identical recompute (e.g. precomputed) also makes the source's result available again.
    """
    if source.status != "completed":
        raise Conflict(
            f"job {source.id} is {source.status}; only completed jobs can be recomputed",
            code="job_not_recomputable",
            details={"job_id": str(source.id), "status": source.status},
        )
    art = session.scalar(
        select(SimulationArtifact).where(
            SimulationArtifact.job_id == source.id, SimulationArtifact.kind == "result"
        )
    )
    if not force and art is not None and ctx.store.exists(art.storage_key, fresh=True):
        raise Conflict(
            "the result of this job is still available; recompute is only for lost results",
            code="result_still_available",
            details={"job_id": str(source.id)},
        )
    outcome = validate_spec(source.spec, ctx.catalog, for_execution=True)
    if not outcome.valid:
        raise Unprocessable(
            "the stored scenario no longer validates",
            code="scenario_invalid",
            details=outcome.report(),
        )
    if outcome.scenario_hash != source.scenario_hash:
        raise Conflict(
            "the stored scenario now hashes differently; a recompute would not reproduce it",
            code="recompute_hash_mismatch",
            details={"recorded": source.scenario_hash, "current": outcome.scenario_hash},
        )
    return create_job(
        ctx,
        session,
        principal,
        outcome,
        scenario_record_id=source.scenario_definition_id,
        visibility=source.visibility,
        reuse=False,
        recompute_of=source,
        claim_for=claim_for,
        client_key=client_key,
    )


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
