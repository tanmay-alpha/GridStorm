"""Defence-in-depth response headers (VER-011).

``Strict-Transport-Security`` is only sent for HTTPS requests: the ASGI scheme is ``https``, or
``GRIDSTORM_TRUST_PROXY=true`` and the first ``X-Forwarded-Proto`` hop is ``https`` (Render
terminates TLS in its proxy). Headers already set by a route are left untouched.
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

HSTS = "max-age=31536000; includeSubDomains"
STATIC_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


def is_https(scope: Scope, trust_proxy: bool) -> bool:
    if scope.get("scheme") == "https":
        return True
    if trust_proxy:
        for name, value in scope.get("headers") or []:
            if name == b"x-forwarded-proto":
                return value.decode("latin-1").split(",")[0].strip().lower() == "https"
    return False


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, trust_proxy: bool) -> None:
        self.app = app
        self.trust_proxy = trust_proxy

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        https = is_https(scope, self.trust_proxy)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in STATIC_HEADERS.items():
                    headers.setdefault(name, value)
                if https:
                    headers.setdefault("Strict-Transport-Security", HSTS)
            await send(message)

        await self.app(scope, receive, send_with_headers)
