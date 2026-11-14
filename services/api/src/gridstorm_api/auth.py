"""Optional Supabase JWT authentication.

* No ``Authorization`` header → anonymous principal (may read public data and run demo jobs).
* ``Bearer <jwt>`` → verified with ``SUPABASE_JWT_SECRET`` (HS256, legacy Supabase secret) or the
  project's JWKS at ``SUPABASE_URL/auth/v1/.well-known/jwks.json`` (RS256/ES256 signing keys).
  Audience must equal ``SUPABASE_JWT_AUDIENCE`` (default ``authenticated``); ``exp`` is required.
* A token that is present but invalid/expired is rejected with 401 — never silently downgraded.
Tokens are never logged.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Request

from .errors import Unauthorized

log = logging.getLogger("gridstorm_api.auth")

_ASYMMETRIC = ("RS256", "ES256", "EdDSA")


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID | None = None
    role: str = "anon"

    @property
    def is_authenticated(self) -> bool:
        return self.user_id is not None


ANONYMOUS = Principal()


class JWTVerifier:
    def __init__(self, *, secret: str | None, supabase_url: str | None, audience: str) -> None:
        self.secret = secret
        self.audience = audience
        self.jwks_url = (
            f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json" if supabase_url else None
        )
        self._jwks: Any = None
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return bool(self.secret or self.jwks_url)

    def _jwks_client(self) -> Any:
        with self._lock:
            if self._jwks is None:
                self._jwks = jwt.PyJWKClient(self.jwks_url, cache_keys=True, lifespan=600)
            return self._jwks

    def verify(self, token: str) -> Principal:
        if not self.enabled:
            raise Unauthorized(
                "authentication is not configured on this server; omit the Authorization header",
                code="auth_not_configured",
            )
        try:
            header = jwt.get_unverified_header(token)
            alg = header.get("alg")
            options = {"require": ["exp", "sub"]}
            if alg == "HS256" and self.secret:
                claims = jwt.decode(
                    token, self.secret, algorithms=["HS256"], audience=self.audience,
                    options=options,
                )
            elif alg in _ASYMMETRIC and self.jwks_url:
                key = self._jwks_client().get_signing_key_from_jwt(token)
                claims = jwt.decode(
                    token, key.key, algorithms=[alg], audience=self.audience, options=options
                )
            else:
                raise Unauthorized(
                    f"unsupported token algorithm {alg!r}", code="invalid_token"
                )
        except jwt.ExpiredSignatureError as exc:
            raise Unauthorized("token expired", code="token_expired") from exc
        except jwt.PyJWKClientError as exc:
            log.warning("JWKS lookup failed: %s", type(exc).__name__)
            raise Unauthorized("token signing key could not be resolved", code="invalid_token") from exc
        except jwt.InvalidTokenError as exc:
            raise Unauthorized(f"invalid token ({type(exc).__name__})", code="invalid_token") from exc
        try:
            user_id = uuid.UUID(str(claims["sub"]))
        except ValueError as exc:
            raise Unauthorized("token subject is not a user id", code="invalid_token") from exc
        return Principal(user_id=user_id, role=str(claims.get("role") or "authenticated"))


def principal_from_request(request: Request) -> Principal:
    header = request.headers.get("authorization")
    if not header:
        return ANONYMOUS
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise Unauthorized("Authorization header must be 'Bearer <token>'", code="invalid_token")
    verifier: JWTVerifier = request.app.state.ctx.jwt
    return verifier.verify(token.strip())
