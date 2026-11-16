"""Data Observatory catalog: ``/api/v1/data/catalog`` (list, detail, bounded series, CSV export).

File-backed, immutable per deployment (ADR 0003): see ``gridstorm_api.observatory``.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, Response

from ..caching import DATA_CACHE_CONTROL, cached_bytes, cached_json
from ..deps import Ctx, Paging
from ..observatory import (
    DEFAULT_MAX_POINTS,
    MAX_POINTS,
    compute_series,
    ensure_exportable,
    export_csv,
    matches,
    summarize,
)
from ..schemas import DataCatalogPage, DataCategory, DataSeriesResponse, DatasetEntry, ErrorResponse
from ..schemas import Provenance as ProvenanceLabel

router = APIRouter(prefix="/api/v1/data", tags=["data"])

_ERR = {"model": ErrorResponse}
_CACHING = (
    "Responses carry `Cache-Control: public, max-age=300` and a strong `ETag` (sha256 of the "
    "body, which embeds the bundle version and file sha256); a matching `If-None-Match` yields "
    "`304 Not Modified`."
)
_BOUNDS = (
    "`start`/`end` are ISO-8601 (UTC when no offset is given), `end` exclusive. Without both, the "
    "dataset's first documented window is used, else the last 31 days of coverage; with only "
    "one, a 31-day window. Ranges over 3 years answer 422 `range_too_large`."
)


@router.get(
    "/catalog",
    response_model=DataCatalogPage,
    summary="Data Observatory catalog (bundle datasets + network models + precomputed studies)",
    description="Filters are exact matches (`region` = `region.code`, `source` = `source.name`); "
    "`q` is a case-insensitive substring of id, title, summary, data nature, source name or "
    "publisher. `facets` count the full, unfiltered catalog. `bundle` reports the curated "
    "bundle's load/verification status (`absent` when `data/observatory/` is not deployed; network "
    "and study entries are still listed). Items omit `description`, `transformations` and "
    f"`quality.checks` (see the detail route).\n\n{_CACHING}",
)
def list_catalog(
    request: Request,
    ctx: Ctx,
    page: Paging,
    category: Annotated[DataCategory | None, Query()] = None,
    provenance: Annotated[ProvenanceLabel | None, Query()] = None,
    region: Annotated[str | None, Query(max_length=64)] = None,
    source: Annotated[str | None, Query(max_length=200)] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> Response:
    merged = ctx.observatory.merged()
    items = [
        e
        for e in merged.entries
        if matches(e, category=category, provenance=provenance, region=region, source=source, q=q)
    ]
    content = {
        "items": [summarize(e) for e in items[page.offset : page.offset + page.limit]],
        "total": len(items),
        "limit": page.limit,
        "offset": page.offset,
        "facets": merged.facets,
        "bundle": ctx.observatory.bundle().describe(),
    }
    return cached_json(request, content, model=DataCatalogPage, cache_control=DATA_CACHE_CONTROL)


@router.get(
    "/catalog/{dataset_id}",
    response_model=DatasetEntry,
    responses={404: _ERR},
    summary="One dataset entry (full metadata, quality checks, transformations)",
    description=_CACHING,
)
def get_dataset(request: Request, ctx: Ctx, dataset_id: str) -> Response:
    entry = ctx.observatory.get(dataset_id)
    return cached_json(request, entry, model=DatasetEntry, cache_control=DATA_CACHE_CONTROL)


@router.get(
    "/catalog/{dataset_id}/series",
    response_model=DataSeriesResponse,
    responses={404: _ERR, 409: _ERR, 422: _ERR, 503: _ERR},
    summary="Bounded, optionally downsampled time series of one dataset",
    description=f"{_BOUNDS}\n\n`resolution=auto` picks the finest of raw/PT3H/P1D/P7D (coarser "
    "than the raw step) with at most `max_points` timestamps; `raw` or a fixed bucket over the "
    "limit answers 422 `range_too_large`. Buckets are UTC-aligned (PT3H at 00/03/…/21 UTC, P1D "
    "at 00:00 UTC, P7D = weeks from Monday 00:00 UTC) and labelled by their start; a bucket or "
    "raw slot without an observed value is `null`, never 0, and nothing is interpolated. "
    "`missing` counts raw-grid slots in the window without a value (absent rows + empty cells). "
    "409 `not_a_series_dataset` for metadata-only entries; 503 `dataset_unverified` when the "
    f"file failed checksum verification; 422 `unknown_series`.\n\n{_CACHING}",
)
def get_series(
    request: Request,
    ctx: Ctx,
    dataset_id: str,
    series: Annotated[str | None, Query(description="Comma-separated series ids")] = None,
    start: Annotated[str | None, Query(max_length=40)] = None,
    end: Annotated[str | None, Query(max_length=40)] = None,
    resolution: Literal["auto", "raw", "PT3H", "P1D", "P7D"] = "auto",
    agg: Literal["mean", "min", "max"] = "mean",
    max_points: Annotated[int, Query(ge=1, le=MAX_POINTS)] = DEFAULT_MAX_POINTS,
) -> Response:
    entry, table = ctx.observatory.series_dataset(dataset_id)
    content = compute_series(
        entry,
        table,
        bundle_version=ctx.observatory.bundle().bundle_version,
        series=series,
        start=start,
        end=end,
        resolution=resolution,
        agg=agg,
        max_points=max_points,
    )
    return cached_json(request, content, model=DataSeriesResponse, cache_control=DATA_CACHE_CONTROL)


@router.get(
    "/catalog/{dataset_id}/export",
    responses={
        200: {"content": {"text/csv": {}}, "description": "CSV attachment"},
        403: _ERR,
        404: _ERR,
        409: _ERR,
        422: _ERR,
        503: _ERR,
    },
    summary="CSV export of the raw rows in a bounded window",
    description=f"{_BOUNDS}\n\nRaw resolution only (rows as published; absent timestamps are not "
    "filled). `#` comment lines carry dataset, provenance, source, licence, attribution and the "
    "file sha256. 403 `export_not_permitted` when the licence does not permit redistribution "
    f"(`exportable: false`).\n\n{_CACHING}",
)
def export_dataset(
    request: Request,
    ctx: Ctx,
    dataset_id: str,
    series: Annotated[str | None, Query(description="Comma-separated series ids")] = None,
    start: Annotated[str | None, Query(max_length=40)] = None,
    end: Annotated[str | None, Query(max_length=40)] = None,
) -> Response:
    entry = ctx.observatory.get(dataset_id)
    ensure_exportable(entry)
    entry, table = ctx.observatory.series_dataset(dataset_id)
    body, filename = export_csv(
        entry,
        table,
        bundle_version=ctx.observatory.bundle().bundle_version,
        series=series,
        start=start,
        end=end,
    )
    return cached_bytes(
        request,
        body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        cache_control=DATA_CACHE_CONTROL,
    )
