"""Defence-in-depth response headers (VER-011).

``Strict-Transport-Security`` is only sent for HTTPS requests, i.e. when the ASGI scheme is
``https``. Behind a trusted proxy (``GRIDSTORM_TRUST_PROXY=true``) ``TrustedProxyMiddleware`` has
already set the scheme from ``X-Forwarded-Proto`` (Render terminates TLS in its proxy). Headers
already set by a route are left untouched.
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


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        https = scope.get("scheme") == "https"

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in STATIC_HEADERS.items():
                    headers.setdefault(name, value)
                if https:
                    headers.setdefault("Strict-Transport-Security", HSTS)
            await send(message)

        await self.app(scope, receive, send_with_headers)
