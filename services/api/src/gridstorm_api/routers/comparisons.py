from __future__ import annotations

import hashlib
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from ..access import audit, can_read, ensure_profile, resolve_visibility
from ..comparisons import (
    build_comparison_report,
    build_job_report,
    comparison_markdown,
    job_markdown,
)
from ..db.models import ComparisonReport, SimulationJob
from ..deps import Ctx, CurrentPrincipal, DBSession, parse_uuid, rate_limit_post
from ..errors import Conflict, NotFound, Unprocessable
from ..jobs.results import load_result
from ..jobs.service import canonical_bytes, iso
from ..schemas import Comparison, ComparisonCreate, ErrorResponse
from .simulations import get_visible_job

router = APIRouter(tags=["comparisons"])

_404 = {404: {"model": ErrorResponse}}


def comparison_to_dict(row: ComparisonReport) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "baseline_job_id": str(row.baseline_job_id),
        "scenario_job_id": str(row.scenario_job_id),
        "network_id": row.network_id,
        "owner_id": str(row.owner_id) if row.owner_id else None,
        "visibility": row.visibility,
        "created_at": iso(row.created_at),
        "report_sha256": row.report_sha256,
        "report": row.report,
    }


def _completed(job: SimulationJob, label: str) -> None:
    if job.status != "completed" or not job.result_sha256:
        raise Conflict(
            f"{label} job {job.id} is {job.status}; comparisons need two completed jobs",
            code="job_not_completed",
            details={"job_id": str(job.id), "status": job.status, "role": label},
        )


@router.post(
    "/api/v1/comparisons",
    response_model=Comparison,
    status_code=201,
    dependencies=[Depends(rate_limit_post)],
    responses={**_404, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    summary="Compare two completed jobs on the same network",
    description="Metric deltas, per-carrier deltas and per-branch max-loading deltas "
    "(scenario − baseline) with a reproducibility manifest. A comparison that involves a private "
    "job is private.",
)
def create_comparison(
    ctx: Ctx, session: DBSession, principal: CurrentPrincipal, body: ComparisonCreate
) -> dict[str, Any]:
    baseline_job = get_visible_job(session, principal, body.baseline_job_id)
    scenario_job = get_visible_job(session, principal, body.scenario_job_id)
    _completed(baseline_job, "baseline")
    _completed(scenario_job, "scenario")
    if baseline_job.network_id != scenario_job.network_id:
        raise Unprocessable(
            "jobs ran on different networks and cannot be compared",
            code="network_mismatch",
            details={"baseline": baseline_job.network_id, "scenario": scenario_job.network_id},
        )
    visibility = resolve_visibility(body.visibility, principal)
    if "private" in (baseline_job.visibility, scenario_job.visibility):
        if body.visibility == "public":
            raise Unprocessable(
                "a comparison that includes a private job cannot be public",
                code="visibility_conflict",
            )
        visibility = "private"
    baseline = load_result(session, ctx.store, baseline_job)
    scenario = load_result(session, ctx.store, scenario_job)
    report = build_comparison_report(
        session, baseline_job, scenario_job, baseline, scenario, ctx.settings.git_sha
    )
    ensure_profile(session, principal)
    row = ComparisonReport(
        baseline_job_id=baseline_job.id,
        scenario_job_id=scenario_job.id,
        network_id=baseline_job.network_id,
        report=report,
        report_sha256=hashlib.sha256(canonical_bytes(report)).hexdigest(),
        owner_id=principal.user_id,
        visibility=visibility,
    )
    session.add(row)
    session.flush()
    audit(
        session,
        principal,
        "comparison.create",
        "comparison_report",
        row.id,
        {"baseline_job_id": str(baseline_job.id), "scenario_job_id": str(scenario_job.id)},
    )
    session.commit()
    return comparison_to_dict(row)


def _visible_comparison(session: Any, principal: Any, comparison_id: str) -> ComparisonReport:
    row = session.get(ComparisonReport, parse_uuid(comparison_id, "comparison"))
    if row is None or not can_read(row, principal):
        raise NotFound(f"comparison {comparison_id!r} not found", code="comparison_not_found")
    return row


@router.get(
    "/api/v1/comparisons/{comparison_id}",
    response_model=Comparison,
    responses=_404,
    summary="One comparison",
)
def get_comparison(
    session: DBSession, principal: CurrentPrincipal, comparison_id: str
) -> dict[str, Any]:
    return comparison_to_dict(_visible_comparison(session, principal, comparison_id))


@router.get(
    "/api/v1/reports/{report_id}",
    responses={
        200: {
            "content": {"application/json": {}, "text/markdown": {}},
            "description": "gridstorm-comparison/1.0 or gridstorm-run-report/1.0",
        },
        **_404,
        409: {"model": ErrorResponse},
    },
    tags=["reports"],
    summary="Reproducible report for a comparison id or a job id (JSON or Markdown)",
)
def get_report(
    ctx: Ctx,
    session: DBSession,
    principal: CurrentPrincipal,
    report_id: str,
    format: Annotated[Literal["json", "md"], Query()] = "json",  # noqa: A002
) -> Response:
    uid = parse_uuid(report_id, "report")
    comparison = session.get(ComparisonReport, uid)
    if comparison is not None and can_read(comparison, principal):
        report, sha = comparison.report, comparison.report_sha256
        if format == "md":
            return PlainTextResponse(
                comparison_markdown(report, str(comparison.id)),
                media_type="text/markdown; charset=utf-8",
                headers={"X-GridStorm-Report-SHA256": sha},
            )
        return JSONResponse(report, headers={"X-GridStorm-Report-SHA256": sha})
    job = session.get(SimulationJob, uid)
    if job is None or not can_read(job, principal):
        raise NotFound(f"report {report_id!r} not found", code="report_not_found")
    _completed(job, "report")
    report = build_job_report(
        session, job, load_result(session, ctx.store, job), ctx.settings.git_sha
    )
    if format == "md":
        return PlainTextResponse(job_markdown(report), media_type="text/markdown; charset=utf-8")
    return JSONResponse(report)
