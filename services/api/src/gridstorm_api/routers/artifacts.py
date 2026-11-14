from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, Response

from ..caching import cached_bytes, cached_json
from ..deps import Ctx, Paging
from ..errors import Unprocessable
from ..schemas import ArtifactKind, ErrorResponse, Page, PrecomputedArtifact

router = APIRouter(prefix="/api/v1/artifacts", tags=["artifacts"])

# Payload keys of a ``simulation`` artifact (gridstorm-result) kept by ``view=summary``; the
# bulky per-asset/per-snapshot fields (assets, series, snapshots, ...) are dropped.
SUMMARY_KEYS = (
    "schema_version",
    "scenario_id",
    "scenario_hash",
    "network_id",
    "provenance",
    "engine",
    "solver",
    "outcome",
    "metrics",
    "warnings",
)


@router.get(
    "",
    response_model=Page[PrecomputedArtifact],
    summary="Precomputed engine artifact index (data/artifacts/<engine>/index.json)",
    description="Artifacts are produced offline by the pandapower/grid2op/stormbench/... "
    "environments and committed; they are always `execution_mode: precomputed`. Extra index "
    "fields (e.g. `description`, `scenario_hash`) are passed through.",
)
def list_artifacts(
    request: Request,
    ctx: Ctx,
    page: Paging,
    engine: Annotated[str | None, Query()] = None,
    kind: Annotated[ArtifactKind | None, Query()] = None,
    network_id: Annotated[str | None, Query()] = None,
) -> Response:
    items = [
        i
        for i in ctx.precomputed.index()
        if (engine is None or i["engine"] == engine)
        and (kind is None or i["kind"] == kind)
        and (network_id is None or i["network_id"] == network_id)
    ]
    content = {
        "items": items[page.offset : page.offset + page.limit],
        "total": len(items),
        "limit": page.limit,
        "offset": page.offset,
    }
    return cached_json(request, content, model=Page[PrecomputedArtifact])


@router.get(
    "/{engine}/{artifact_id}",
    responses={
        200: {
            "content": {"application/json": {}},
            "description": "`view=full`: gridstorm-artifact/1.0 document (`artifact` header + "
            "`payload`), byte-identical to the committed file. `view=summary`: "
            '`{"artifact": <header>, "summary": {...}}`',
        },
        304: {"description": "`If-None-Match` matched the current `ETag`"},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
    summary="One precomputed artifact",
    description="`X-GridStorm-Payload-Verified`: `true` when the payload matches the header's "
    "`payload_sha256`, `false` on mismatch, `unknown` when the header declares none (always "
    "computed over the full payload, whichever view is requested).\n\n"
    "`view=summary` (only for `kind: simulation`) returns the unchanged `artifact` header plus "
    "`summary`, the payload restricted to `schema_version`, `scenario_id`, `scenario_hash`, "
    "`network_id`, `provenance`, `engine`, `solver`, `outcome`, `metrics` and `warnings` "
    "(no `assets`, `series`, `snapshots`, `snapshot_weightings_h`, `assumptions`, `manifest`). "
    "Other kinds answer 422 `summary_view_unsupported`.\n\n"
    "Responses carry `Cache-Control: public, max-age=3600` and an `ETag` (sha256 of the body); "
    "a matching `If-None-Match` yields `304 Not Modified`.",
)
def get_artifact(
    request: Request,
    ctx: Ctx,
    engine: str,
    artifact_id: str,
    view: Annotated[
        Literal["full", "summary"],
        Query(description="`full` document or header + payload `summary` (simulation only)"),
    ] = "full",
) -> Response:
    raw, doc, verified = ctx.precomputed.load(engine, artifact_id)
    flag = "unknown" if verified is None else ("true" if verified else "false")
    headers = {"X-GridStorm-Payload-Verified": flag}
    if view == "full":
        return cached_bytes(request, raw, headers=headers)
    header = doc.get("artifact") or {}
    kind = header.get("kind")
    if kind != "simulation":
        raise Unprocessable(
            f"artifact {engine}/{artifact_id} of kind {kind!r} has no summary view",
            code="summary_view_unsupported",
            details={"engine": engine, "artifact_id": artifact_id, "kind": kind},
        )
    payload = doc.get("payload") or {}
    summary = {k: payload[k] for k in SUMMARY_KEYS if k in payload}
    return cached_json(request, {"artifact": header, "summary": summary}, headers=headers)
