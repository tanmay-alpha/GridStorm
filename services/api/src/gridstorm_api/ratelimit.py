"""In-process per-IP token buckets for POST endpoints, and a request body size limit.

Limits (defaults; env-configurable):
  * ``post``: 60 requests/min refill, burst 20, for every POST endpoint;
  * ``simulations``: additionally 6 requests/min, burst 3, for ``POST /api/v1/simulations``.
State is per process (a multi-instance deployment multiplies the effective limit by the number of
instances). The client IP is the socket peer, or the first ``X-Forwarded-For`` hop when
``GRIDSTORM_TRUST_PROXY=true`` (Render terminates TLS in a proxy).
"""

from __future__ import annotations

import math
import threading
import time
from collections import OrderedDict

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .errors import APIError, error_body


class RateLimited(APIError):
    status_code = 429
    code = "rate_limited"


class TokenBucketLimiter:
    def __init__(self, per_minute: float, burst: int, *, max_keys: int = 10_000) -> None:
        self.rate = per_minute / 60.0
        self.capacity = float(max(1, burst))
        self.max_keys = max_keys
        self._buckets: OrderedDict[str, tuple[float, float]] = OrderedDict()
        self._lock = threading.Lock()

    def check(self, key: str, now: float | None = None) -> None:
        if self.rate <= 0:
            return
        now = time.monotonic() if now is None else now
        with self._lock:
            tokens, last = self._buckets.pop(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - last) * self.rate)
            if tokens < 1.0:
                self._buckets[key] = (tokens, now)
                retry = math.ceil((1.0 - tokens) / self.rate)
                raise RateLimited(
                    "too many requests; slow down",
                    details={"retry_after_s": retry},
                    headers={"Retry-After": str(retry)},
                )
            self._buckets[key] = (tokens - 1.0, now)
            while len(self._buckets) > self.max_keys:
                self._buckets.popitem(last=False)


def client_ip(scope: Scope, trust_proxy: bool) -> str:
    if trust_proxy:
        for name, value in scope.get("headers") or []:
            if name == b"x-forwarded-for":
                first = value.decode("latin-1").split(",")[0].strip()
                if first:
                    return first
    client = scope.get("client")
    return client[0] if client else "unknown"


class BodySizeLimitMiddleware:
    """Reject request bodies larger than ``max_bytes`` with 413 (Content-Length or streamed)."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        for name, value in scope.get("headers") or []:
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    declared = 0
                if declared > self.max_bytes:
                    await self._reject(send)
                    return
        received = 0
        too_large = False

        async def limited_receive() -> Message:
            nonlocal received, too_large
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    too_large = True
                    raise _BodyTooLarge
            return message

        response_started = False

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLarge:
            if not response_started:
                await self._reject(send)
        except Exception:
            if too_large and not response_started:
                await self._reject(send)
                return
            raise

    async def _reject(self, send: Send) -> None:
        import json

        body = json.dumps(
            error_body(
                "payload_too_large",
                f"request body exceeds {self.max_bytes} bytes",
                {"max_bytes": self.max_bytes},
            )
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


class _BodyTooLarge(Exception):
    pass
