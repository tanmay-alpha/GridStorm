"""Client identity behind a trusted proxy, in-process token buckets for POST endpoints, and a
request body size limit.

Limits (defaults; env-configurable):
  * ``post``: 60 requests/min refill, burst 20, for every POST endpoint;
  * ``simulations``: additionally 6 requests/min, burst 3, for ``POST /api/v1/simulations``.
State is per process (a multi-instance deployment multiplies the effective limit by the number of
instances). Buckets are keyed by the client address (IPv6 clients by their /64, which one
subscriber typically controls in full).

The client address is the socket peer unless ``GRIDSTORM_TRUST_PROXY=true``, in which case
``TrustedProxyMiddleware`` replaces ``scope["client"]`` (and ``scope["scheme"]``) once, for the
rate limiter, HSTS, redirects and uvicorn's access log alike:

1. ``GRIDSTORM_CLIENT_IP_HEADER`` (e.g. ``cf-connecting-ip``): a single-IP header that the edge
   proxy *overwrites* on every request. Used when present exactly once and a valid IP.
2. Otherwise the ``GRIDSTORM_TRUSTED_PROXY_HOPS``-th ``X-Forwarded-For`` entry from the right.
   Proxies append, so a client can only add entries on the left; entries left of the chosen one
   are never used. With fewer entries than hops the socket peer is kept.

Render (docs/audit/security-3.0.md): Cloudflare fronts every service and sets
``CF-Connecting-IP``; Render's proxies append further ``X-Forwarded-For`` entries. Uvicorn must run
with ``--no-proxy-headers``: its ``--forwarded-allow-ips='*'`` mode takes the *leftmost*,
client-controlled entry.
"""

from __future__ import annotations

import ipaddress
import math
import threading
import time
from collections import OrderedDict
from collections.abc import Iterable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .errors import APIError, error_body

Headers = Iterable[tuple[bytes, bytes]]


def parse_ip(value: str) -> str | None:
    """Normalised IP of a forwarded value (bare, ``v4:port`` or ``[v6]:port``), else None."""
    value = value.strip()
    if value.startswith("["):
        end = value.find("]")
        value = value[1:end] if end > 0 else value
    elif value.count(":") == 1:
        value = value.split(":", 1)[0]
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def forwarded_client_ip(
    headers: Headers, *, client_ip_header: str | None, proxy_hops: int
) -> str | None:
    """Client address asserted by the trusted proxy chain, or None to keep the socket peer."""
    headers = list(headers)
    if client_ip_header:
        name = client_ip_header.lower().encode("latin-1")
        values = [v for n, v in headers if n == name]
        if len(values) == 1:
            ip = parse_ip(values[0].decode("latin-1"))
            if ip is not None:
                return ip
    hops = [
        hop.strip()
        for n, v in headers
        if n == b"x-forwarded-for"
        for hop in v.decode("latin-1").split(",")
        if hop.strip()
    ]
    if proxy_hops < 1 or len(hops) < proxy_hops:
        return None
    return parse_ip(hops[-proxy_hops])


def forwarded_proto(headers: Headers) -> str | None:
    for name, value in headers:
        if name == b"x-forwarded-proto":
            proto = value.decode("latin-1").split(",")[0].strip().lower()
            return proto if proto in ("http", "https") else None
    return None


class TrustedProxyMiddleware:
    """Rewrite ``scope["client"]``/``scope["scheme"]`` from trusted proxy headers (see module doc).

    The scope dict is mutated in place, so uvicorn's access log reports the resolved client too.
    """

    def __init__(self, app: ASGIApp, *, client_ip_header: str | None, proxy_hops: int) -> None:
        self.app = app
        self.client_ip_header = client_ip_header
        self.proxy_hops = proxy_hops

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = scope.get("headers") or []
            ip = forwarded_client_ip(
                headers, client_ip_header=self.client_ip_header, proxy_hops=self.proxy_hops
            )
            if ip is not None:
                scope["client"] = (ip, 0)
            proto = forwarded_proto(headers)
            if proto is not None:
                scope["scheme"] = proto
        await self.app(scope, receive, send)


def client_key(scope: Scope) -> str:
    """Rate-limit bucket key: the client IP, IPv6 aggregated to its /64."""
    client = scope.get("client")
    host = client[0] if client else "unknown"
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return host
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return str(ip.ipv4_mapped)
        return str(ipaddress.IPv6Network((ip, 64), strict=False))
    return str(ip)


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
