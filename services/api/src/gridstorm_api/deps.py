"""FastAPI dependencies."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query, Request
from sqlalchemy.orm import Session

from .auth import Principal, principal_from_request
from .context import AppContext
from .errors import NotFound
from .ratelimit import client_key


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def get_session(ctx: Annotated[AppContext, Depends(get_ctx)]) -> Iterator[Session]:
    with ctx.db.session() as s:
        yield s


def get_principal(request: Request) -> Principal:
    return principal_from_request(request)


def rate_limit_post(request: Request) -> None:
    ctx: AppContext = request.app.state.ctx
    ctx.post_limiter.check(client_key(request.scope))


def rate_limit_simulations(request: Request) -> None:
    ctx: AppContext = request.app.state.ctx
    ctx.sim_limiter.check(client_key(request.scope))


def get_client_key(request: Request) -> str:
    """Rate-limit identity of the caller (resolved client IP; see ratelimit.py)."""
    return client_key(request.scope)


@dataclass
class Pagination:
    limit: int
    offset: int


def pagination(
    limit: Annotated[int, Query(ge=1, le=500, description="Page size (max 500)")] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Pagination:
    return Pagination(limit, offset)


def parse_uuid(value: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise NotFound(f"{what} {value!r} not found", code=f"{what}_not_found") from exc


Ctx = Annotated[AppContext, Depends(get_ctx)]
DBSession = Annotated[Session, Depends(get_session)]
CurrentPrincipal = Annotated[Principal, Depends(get_principal)]
Paging = Annotated[Pagination, Depends(pagination)]
ClientKey = Annotated[str, Depends(get_client_key)]
