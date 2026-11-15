from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select

from ..access import can_modify, can_read, resolve_visibility, visible
from ..db.models import SimulationArtifact, SimulationJob, SimulationMetrics
from ..deps import (
    ClientKey,
    Ctx,
    CurrentPrincipal,
    DBSession,
    Paging,
    parse_uuid,
    rate_limit_post,
    rate_limit_simulations,
)
from ..errors import Conflict, Forbidden, NotFound, Unprocessable
from ..jobs.results import load_result_bytes
from ..jobs.service import cancel_job, create_job, iso, job_json, jobs_to_dicts, recompute_job
from ..schemas import (
    ErrorResponse,
    Job,
    JobMetrics,
    JobStatus,
    Page,
    SimulationCreate,
    StoredArtifactList,
)
from ..validation import validate_spec
from .scenarios import get_visible_scenario

router = APIRouter(prefix="/api/v1/simulations", tags=["simulations"])

_404 = {404: {"model": ErrorResponse}}


def get_visible_job(session: Any, principal: Any, job_id: str) -> SimulationJob:
    job = session.get(SimulationJob, parse_uuid(job_id, "job"))
    if job is None or not can_read(job, principal):
        raise NotFound(
            f"job {job_id!r} not found", code="job_not_found", details={"job_id": job_id}
        )
    return job


@router.post(
    "",
    response_model=Job,
    status_code=202,
    dependencies=[Depends(rate_limit_post), Depends(rate_limit_simulations)],
    responses={
        422: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
    },
    summary="Validate and enqueue a simulation (or reuse an identical completed result)",
    description="Body: `{scenario_id}` (preset or saved record id) or `{scenario: spec}`. "
    "In `GRIDSTORM_EXECUTION_MODE=precomputed` only scenarios with a committed precomputed "
    "result can be served (execution_mode=precomputed); otherwise 409. A caller that already "
    "has `GRIDSTORM_MAX_ACTIVE_JOBS_PER_CLIENT` (default 2) queued or running jobs gets 429 "
    "`too_many_active_jobs` (signed-in users counted per account, anonymous callers per client "
    "IP); reused and precomputed results never count.",
)
def create_simulation(
    ctx: Ctx,
    session: DBSession,
    principal: CurrentPrincipal,
    client: ClientKey,
    body: SimulationCreate,
) -> dict[str, Any]:
    record_id: str | None = None
    requested = body.visibility
    if body.scenario_id is not None:
        row = get_visible_scenario(session, principal, body.scenario_id)
        spec, record_id = row.spec, row.id
        if requested is None and row.visibility == "private":
            requested = "private"
    else:
        spec = body.scenario
    outcome = validate_spec(spec, ctx.catalog, for_execution=True)
    if not outcome.valid:
        raise Unprocessable(
            "scenario is invalid", code="scenario_invalid", details=outcome.report()
        )
    visibility = resolve_visibility(requested, principal)
    job = create_job(
        ctx,
        session,
        principal,
        outcome,
        scenario_record_id=record_id,
        visibility=visibility,
        reuse=body.reuse,
        client_key=client,
    )
    return job_json(ctx, session, job)


@router.get("", response_model=Page[Job], summary="Simulation jobs (newest first)")
def list_simulations(
    ctx: Ctx,
    session: DBSession,
    principal: CurrentPrincipal,
    page: Paging,
    status: Annotated[JobStatus | None, Query()] = None,
    network_id: Annotated[str | None, Query()] = None,
    scenario_hash: Annotated[str | None, Query()] = None,
    mine: Annotated[bool, Query(description="Only jobs owned by the caller")] = False,
) -> dict[str, Any]:
    cond = [visible(SimulationJob, principal)]
    if status is not None:
        cond.append(SimulationJob.status == status)
    if network_id is not None:
        cond.append(SimulationJob.network_id == network_id)
    if scenario_hash is not None:
        cond.append(SimulationJob.scenario_hash == scenario_hash)
    if mine:
        cond.append(
            SimulationJob.owner_id == principal.user_id
            if principal.user_id
            else SimulationJob.owner_id.is_(None)
        )
    total = session.scalar(select(func.count()).select_from(SimulationJob).where(*cond))
    rows = session.scalars(
        select(SimulationJob)
        .where(*cond)
        .order_by(SimulationJob.created_at.desc(), SimulationJob.id)
        .limit(page.limit)
        .offset(page.offset)
    ).all()
    return {
        "items": jobs_to_dicts(ctx, session, rows),
        "total": total or 0,
        "limit": page.limit,
        "offset": page.offset,
    }


@router.get("/{job_id}", response_model=Job, responses=_404, summary="One simulation job")
def get_simulation(
    ctx: Ctx, session: DBSession, principal: CurrentPrincipal, job_id: str
) -> dict[str, Any]:
    return job_json(ctx, session, get_visible_job(session, principal, job_id))


@router.post(
    "/{job_id}/cancel",
    response_model=Job,
    dependencies=[Depends(rate_limit_post)],
    responses={**_404, 403: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    summary="Cancel a queued or running job (kills the engine subprocess)",
)
def cancel_simulation(
    ctx: Ctx, session: DBSession, principal: CurrentPrincipal, job_id: str
) -> dict[str, Any]:
    job = get_visible_job(session, principal, job_id)
    if not can_modify(job, principal):
        raise Forbidden("only the owner can cancel this job", code="not_owner")
    return job_json(ctx, session, cancel_job(ctx, session, principal, job))


@router.post(
    "/{job_id}/recompute",
    response_model=Job,
    status_code=202,
    dependencies=[Depends(rate_limit_post), Depends(rate_limit_simulations)],
    responses={
        **_404,
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
    summary="Recompute a lost result as a new job with recorded provenance",
)
def recompute_simulation(
    ctx: Ctx, session: DBSession, principal: CurrentPrincipal, client: ClientKey, job_id: str
) -> dict[str, Any]:
    source = get_visible_job(session, principal, job_id)
    return job_json(ctx, session, recompute_job(ctx, session, principal, source, client_key=client))


@router.get(
    "/{job_id}/metrics",
    response_model=JobMetrics,
    responses={**_404, 409: {"model": ErrorResponse}},
    summary="Result metrics + solver summary of a completed job",
)
def simulation_metrics(
    session: DBSession, principal: CurrentPrincipal, job_id: str
) -> dict[str, Any]:
    job = get_visible_job(session, principal, job_id)
    row = session.get(SimulationMetrics, job.id)
    if job.status != "completed" or row is None:
        raise Conflict(
            f"job {job.id} has no metrics (status {job.status})",
            code="result_not_available",
            details={"job_id": str(job.id), "status": job.status},
        )
    return {
        "job_id": str(job.id),
        "network_id": job.network_id,
        "scenario_hash": job.scenario_hash,
        "outcome": job.outcome,
        "metrics": row.metrics,
        "solver": job.solver,
    }


@router.get(
    "/{job_id}/result",
    responses={
        200: {
            "content": {"application/json": {}},
            "description": "gridstorm-result/1.0 document, byte-identical to the stored artifact",
        },
        **_404,
        409: {"model": ErrorResponse},
        410: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    summary="Full gridstorm-result/1.0 document (sha256-verified)",
)
def simulation_result(
    ctx: Ctx, session: DBSession, principal: CurrentPrincipal, job_id: str
) -> Response:
    job = get_visible_job(session, principal, job_id)
    data = load_result_bytes(ctx, session, job)
    return Response(
        data,
        media_type="application/json",
        headers={
            "X-GridStorm-Result-SHA256": job.result_sha256 or "",
            "Cache-Control": "public, max-age=31536000, immutable"
            if job.visibility == "public"
            else "private, max-age=3600",
        },
    )


@router.get(
    "/{job_id}/artifacts",
    response_model=StoredArtifactList,
    responses={**_404, 410: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Stored artifacts of a job (content-addressed, with sha256)",
)
def simulation_artifacts(
    ctx: Ctx, session: DBSession, principal: CurrentPrincipal, job_id: str
) -> dict[str, Any]:
    job = get_visible_job(session, principal, job_id)
    if job.status == "completed":
        load_result_bytes(ctx, session, job)
    rows = session.scalars(
        select(SimulationArtifact)
        .where(SimulationArtifact.job_id == job.id)
        .order_by(SimulationArtifact.kind)
    ).all()
    return {
        "job_id": str(job.id),
        "items": [
            {
                "kind": a.kind,
                "sha256": a.sha256,
                "bytes": a.bytes,
                "content_type": a.content_type,
                "storage_backend": a.storage_backend,
                "storage_key": a.storage_key,
                "created_at": iso(a.created_at),
            }
            for a in rows
        ],
    }
