from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, Response

from ..analytics import AnalyticsService
from ..caching import cached_json
from ..deps import Ctx, Paging
from ..errors import ServiceUnavailable
from ..geojson import build_geojson
from ..schemas import AssetPage, AssetType, ErrorResponse, NetworkDetail, NetworkSummary, Page

router = APIRouter(prefix="/api/v1/networks", tags=["networks"])

_404 = {404: {"model": ErrorResponse}}


@router.get("", response_model=Page[NetworkSummary], summary="List network datasets")
def list_networks(request: Request, ctx: Ctx, page: Paging) -> Response:
    entries = [ctx.catalog.get(i) for i in ctx.catalog.ids()]
    items = [
        {**e.summary(), "live_execution": ctx.settings.live_execution(e.id)}
        for e in entries[page.offset : page.offset + page.limit]
    ]
    content = {"items": items, "total": len(entries), "limit": page.limit, "offset": page.offset}
    return cached_json(request, content, model=Page[NetworkSummary])


@router.get(
    "/{network_id}",
    response_model=NetworkDetail,
    responses=_404,
    summary="Network summary + dataset manifest + assumptions",
)
def get_network(request: Request, ctx: Ctx, network_id: str) -> Response:
    entry = ctx.catalog.get(network_id)
    content = {
        **entry.summary(),
        "live_execution": ctx.settings.live_execution(entry.id),
        "manifest": entry.manifest,
        "assumptions": entry.canonical.get("assumptions") or [],
        "field_provenance": entry.canonical.get("field_provenance") or {},
        "carriers": entry.canonical.get("carriers") or [],
    }
    return cached_json(request, content, model=NetworkDetail)


@router.get(
    "/{network_id}/assets",
    response_model=AssetPage,
    responses=_404,
    summary="Canonical asset rows of one component type (paginated)",
)
def list_assets(
    request: Request,
    ctx: Ctx,
    network_id: str,
    type: Annotated[AssetType, Query(description="Component type")],  # noqa: A002
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Response:
    entry = ctx.catalog.get(network_id)
    rows = entry.canonical.get(type) or []
    prefix = f"{type}."
    content = {
        "network_id": network_id,
        "type": type,
        "items": rows[offset : offset + limit],
        "total": len(rows),
        "limit": limit,
        "offset": offset,
        "field_provenance": {
            k: v
            for k, v in (entry.canonical.get("field_provenance") or {}).items()
            if k.startswith(prefix)
        },
    }
    return cached_json(request, content, model=AssetPage)


@router.get(
    "/{network_id}/geojson",
    response_model=dict[str, Any],
    responses=_404,
    summary="GeoJSON FeatureCollection (buses = Point; lines/transformers/links = LineString)",
    description="Top-level and per-feature `coordinate_kind`; `schematic` coordinates are layout "
    "coordinates, not lon/lat. Features are keyed by `properties.component` + `properties.id`.",
)
def network_geojson(request: Request, ctx: Ctx, network_id: str) -> Response:
    return cached_json(request, build_geojson(ctx.catalog.get(network_id)))


@router.get(
    "/{network_id}/analytics/{kind}",
    responses={
        **_404,
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
    summary="PyPSA-Explorer-derived analytics (summary, capacity, energy_balance, costs)",
    description="Precomputed by `gridstorm_analytics.compute` on the unsolved input network "
    "(services/analytics/scripts/precompute_analytics.py) and served from "
    "data/networks/<id>/analytics; carrier/country filters are derived exactly from the "
    "unfiltered result or rejected with 422 `analytics_filter_not_precomputed`. Kinds that need "
    "a solved network return `available: false`.",
)
async def network_analytics(
    ctx: Ctx,
    network_id: str,
    kind: str,
    carriers: Annotated[list[str] | None, Query(description="Filter by carrier")] = None,
    countries: Annotated[list[str] | None, Query(description="Filter by country")] = None,
) -> dict[str, Any]:
    entry = ctx.catalog.get(network_id)
    service: AnalyticsService | None = ctx.analytics
    if service is None:
        raise ServiceUnavailable("analytics are not available", code="analytics_unavailable")
    result = await service.compute(entry, kind, carriers, countries)
    return {"network_id": network_id, **result}
