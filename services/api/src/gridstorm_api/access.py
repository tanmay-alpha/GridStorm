"""Ownership/visibility rules (mirrored by the RLS policies in database/migrations/0002)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from .auth import Principal
from .db.models import AuditEvent, Profile
from .errors import Unprocessable


def visible(model: Any, principal: Principal) -> Any:
    """SQL clause: row is public or owned by the principal."""
    if principal.user_id is None:
        return model.visibility == "public"
    return or_(model.visibility == "public", model.owner_id == principal.user_id)


def can_read(row: Any, principal: Principal) -> bool:
    return row.visibility == "public" or (
        principal.user_id is not None and row.owner_id == principal.user_id
    )


def can_modify(row: Any, principal: Principal) -> bool:
    """Owned rows: owner only. Anonymous (owner_id null) rows: anyone (documented demo rule)."""
    if row.owner_id is None:
        return True
    return principal.user_id is not None and row.owner_id == principal.user_id


def resolve_visibility(requested: str | None, principal: Principal) -> str:
    if principal.user_id is None:
        if requested == "private":
            raise Unprocessable(
                "anonymous users can only create public records; sign in to keep records private",
                code="auth_required_for_private",
            )
        return "public"
    return requested or "private"


def ensure_profile(session: Session, principal: Principal) -> None:
    if principal.user_id is not None and session.get(Profile, principal.user_id) is None:
        session.add(Profile(id=principal.user_id))
        session.flush()


def audit(
    session: Session,
    principal: Principal | None,
    action: str,
    target_type: str,
    target_id: Any,
    details: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditEvent(
            actor_id=principal.user_id if principal else None,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            details=details or {},
        )
    )
