from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import false, func, or_, select

from ..access import audit, can_read, ensure_profile, resolve_visibility
from ..db.models import ScenarioDefinition
from ..deps import Ctx, CurrentPrincipal, DBSession, Paging, rate_limit_post
from ..errors import NotFound, Unprocessable
from ..jobs.service import iso
from ..schemas import (
    ErrorResponse,
    Page,
    ScenarioCreate,
    ScenarioRecord,
    ScenarioValidateRequest,
    ValidationReport,
)
from ..validation import validate_spec

router = APIRouter(prefix="/api/v1/scenarios", tags=["scenarios"])


def scenario_to_dict(row: ScenarioDefinition) -> dict[str, Any]:
    return {
        "id": row.id,
        "hash": row.scenario_hash,
        "spec": row.spec,
        "preset": row.is_preset,
        "owner_id": str(row.owner_id) if row.owner_id else None,
        "created_at": iso(row.created_at),
        "name": row.name,
        "network_id": row.network_id,
        "visibility": row.visibility,
        "listed": is_listed(row),
    }


def is_listed(row: ScenarioDefinition) -> bool:
    """Presets are listed to everyone, owned saves to their owner only. Anonymous saves
    (``owner_id`` null) are unlisted: never in ``GET /scenarios``, retrievable by id (VER-013)."""
    return row.is_preset or row.owner_id is not None


def get_visible_scenario(session: Any, principal: Any, scenario_id: str) -> ScenarioDefinition:
    row = session.get(ScenarioDefinition, scenario_id)
    if row is None or not can_read(row, principal):
        raise NotFound(
            f"scenario {scenario_id!r} not found",
            code="scenario_not_found",
            details={"scenario_id": scenario_id},
        )
    return row


@router.get(
    "",
    response_model=Page[ScenarioRecord],
    summary="Preset scenarios and the caller's own saved scenarios",
    description="Saves by other users and anonymous saves are not listed; public ones remain "
    "readable via `GET /api/v1/scenarios/{id}`.",
)
def list_scenarios(
    session: DBSession,
    principal: CurrentPrincipal,
    page: Paging,
    network_id: Annotated[str | None, Query()] = None,
    preset: Annotated[bool | None, Query(description="Only presets (true) / saved (false)")] = None,
) -> dict[str, Any]:
    own = (
        ScenarioDefinition.owner_id == principal.user_id
        if principal.user_id is not None
        else false()
    )
    cond = [or_(ScenarioDefinition.is_preset.is_(True), own)]
    if network_id is not None:
        cond.append(ScenarioDefinition.network_id == network_id)
    if preset is not None:
        cond.append(ScenarioDefinition.is_preset.is_(preset))
    total = session.scalar(select(func.count()).select_from(ScenarioDefinition).where(*cond))
    rows = session.scalars(
        select(ScenarioDefinition)
        .where(*cond)
        .order_by(
            ScenarioDefinition.is_preset.desc(),
            ScenarioDefinition.created_at.desc(),
            ScenarioDefinition.id,
        )
        .limit(page.limit)
        .offset(page.offset)
    ).all()
    return {
        "items": [scenario_to_dict(r) for r in rows],
        "total": total or 0,
        "limit": page.limit,
        "offset": page.offset,
    }


@router.post(
    "/validate",
    response_model=ValidationReport,
    dependencies=[Depends(rate_limit_post)],
    summary="Validate a StormSpec scenario against its network and engine capabilities",
    description="Always 200 with a ValidationReport (valid=false lists errors). Execution checks "
    "(live engine, network.nc present) are included so `valid=true` means runnable here.",
)
def validate_scenario(ctx: Ctx, body: ScenarioValidateRequest) -> dict[str, Any]:
    return validate_spec(body.scenario, ctx.catalog, for_execution=True).report()


@router.post(
    "",
    response_model=ScenarioRecord,
    status_code=201,
    dependencies=[Depends(rate_limit_post)],
    responses={422: {"model": ErrorResponse}},
    summary="Save a scenario (validated first)",
)
def create_scenario(
    ctx: Ctx, session: DBSession, principal: CurrentPrincipal, body: ScenarioCreate
) -> dict[str, Any]:
    outcome = validate_spec(body.scenario, ctx.catalog, for_execution=False)
    if not outcome.valid or outcome.scenario is None:
        raise Unprocessable(
            "scenario is invalid", code="scenario_invalid", details=outcome.report()
        )
    visibility = resolve_visibility(body.visibility, principal)
    ensure_profile(session, principal)
    sc = outcome.scenario
    row = ScenarioDefinition(
        id=str(uuid.uuid4()),
        spec_id=sc.id,
        name=sc.name,
        network_id=sc.dataset.network_id,
        scenario_hash=outcome.scenario_hash,
        spec=sc.model_dump(mode="json"),
        is_preset=False,
        visibility=visibility,
        owner_id=principal.user_id,
    )
    session.add(row)
    session.flush()
    audit(
        session,
        principal,
        "scenario.create",
        "scenario_definition",
        row.id,
        {"scenario_hash": row.scenario_hash, "visibility": visibility},
    )
    session.commit()
    return scenario_to_dict(row)


@router.get(
    "/{scenario_id}",
    response_model=ScenarioRecord,
    responses={404: {"model": ErrorResponse}},
    summary="One preset or saved scenario",
)
def get_scenario(
    session: DBSession, principal: CurrentPrincipal, scenario_id: str
) -> dict[str, Any]:
    return scenario_to_dict(get_visible_scenario(session, principal, scenario_id))
