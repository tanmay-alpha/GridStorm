from __future__ import annotations

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from .. import __version__
from ..deps import Ctx
from ..readiness import run_checks
from ..schemas import Health, Ready

router = APIRouter(tags=["health"])


@router.get("/health", response_model=Health, summary="Liveness")
def health(ctx: Ctx) -> Health:
    return Health(status="ok", version=__version__, git_sha=ctx.settings.git_sha)


@router.get(
    "/ready",
    response_model=Ready,
    summary="Readiness (database, artifact storage, solver, datasets)",
    responses={503: {"model": Ready, "description": "One or more checks failed"}},
)
async def ready(ctx: Ctx) -> JSONResponse:
    result = await run_in_threadpool(run_checks, ctx)
    body = Ready.model_validate(result).model_dump(mode="json")
    return JSONResponse(body, status_code=200 if result["status"] == "ready" else 503)
