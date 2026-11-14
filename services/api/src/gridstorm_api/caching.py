"""HTTP caching for immutable-per-deployment GETs: ``Cache-Control``, body-hash ``ETag``, 304.

The catalog and precomputed artifacts only change with a deployment, so every response body is
hashed (sha256 of the exact bytes) into a strong ``ETag``; ``If-None-Match`` is compared weakly
(RFC 9110 §13.1.2) so tags a proxy weakened after compression still revalidate. Error responses
never pass through here and therefore carry no caching headers.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import Any

from fastapi import Request, Response
from pydantic import TypeAdapter

CACHE_CONTROL = "public, max-age=3600"


@lru_cache(maxsize=32)
def _adapter(model: Any) -> TypeAdapter[Any]:
    return TypeAdapter(model)


def _strip_weak(tag: str) -> str:
    tag = tag.strip()
    return tag[2:] if tag.startswith("W/") else tag


def _not_modified(if_none_match: str | None, etag: str) -> bool:
    if not if_none_match:
        return False
    target = _strip_weak(etag)
    return any(t == "*" or _strip_weak(t) == target for t in if_none_match.split(","))


def cached_bytes(
    request: Request,
    body: bytes,
    *,
    media_type: str = "application/json",
    headers: dict[str, str] | None = None,
) -> Response:
    """200 with ``body`` + caching headers, or an empty 304 when ``If-None-Match`` matches."""
    etag = f'"{hashlib.sha256(body).hexdigest()}"'
    out = {**(headers or {}), "ETag": etag, "Cache-Control": CACHE_CONTROL}
    if _not_modified(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=out)
    return Response(body, media_type=media_type, headers=out)


def cached_json(
    request: Request,
    content: Any,
    *,
    model: Any = dict[str, Any],
    headers: dict[str, str] | None = None,
) -> Response:
    """Serialize ``content`` as FastAPI's response-model fast path would, then cache it.

    ``model`` is the route's declared ``response_model`` (FastAPI infers ``dict[str, Any]`` from
    a ``-> dict[str, Any]`` annotation): content is validated and dumped by pydantic with
    ``by_alias=True``, giving the same bytes the route produced without caching.
    """
    adapter = _adapter(model)
    body = adapter.dump_json(adapter.validate_python(content), by_alias=True)
    return cached_bytes(request, body, headers=headers)
