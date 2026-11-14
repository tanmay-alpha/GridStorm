from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Response

from ..deps import Ctx, Paging
from ..schemas import ErrorResponse, Page, PrecomputedArtifact

router = APIRouter(prefix="/api/v1/artifacts", tags=["artifacts"])


@router.get(
    "",
    response_model=Page[PrecomputedArtifact],
    summary="Precomputed engine artifact index (data/artifacts/<engine>/index.json)",
    description="Artifacts are produced offline by the pandapower/grid2op/stormbench/... "
    "environments and committed; they are always `execution_mode: precomputed`. Extra index "
    "fields (e.g. `description`, `scenario_hash`) are passed through.",
)
def list_artifacts(
    ctx: Ctx,
    page: Paging,
    engine: Annotated[str | None, Query()] = None,
    kind: Annotated[str | None, Query()] = None,
    network_id: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    items = [
        i
        for i in ctx.precomputed.index()
        if (engine is None or i["engine"] == engine)
        and (kind is None or i["kind"] == kind)
        and (network_id is None or i["network_id"] == network_id)
    ]
    return {
        "items": items[page.offset : page.offset + page.limit],
        "total": len(items),
        "limit": page.limit,
        "offset": page.offset,
    }


@router.get(
    "/{engine}/{artifact_id}",
    responses={
        200: {
            "content": {"application/json": {}},
            "description": "gridstorm-artifact/1.0 document (`artifact` header + `payload`), "
            "byte-identical to the committed file",
        },
        404: {"model": ErrorResponse},
    },
    summary="One precomputed artifact",
    description="`X-GridStorm-Payload-Verified`: `true` when the payload matches the header's "
    "`payload_sha256`, `false` on mismatch, `unknown` when the header declares none.",
)
def get_artifact(ctx: Ctx, engine: str, artifact_id: str) -> Response:
    raw, _, verified = ctx.precomputed.load(engine, artifact_id)
    flag = "unknown" if verified is None else ("true" if verified else "false")
    return Response(
        raw,
        media_type="application/json",
        headers={"X-GridStorm-Payload-Verified": flag, "Cache-Control": "public, max-age=300"},
    )
