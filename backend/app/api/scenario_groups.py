"""Scenario group API: admin management and user group training runs."""

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_role
from app.models.user import User
from app.schemas.scenario_group import (
    ScenarioGroupCreate,
    ScenarioGroupResponse,
    ScenarioGroupRunResponse,
    ScenarioGroupRunSessionCreate,
    ScenarioGroupTransitionRequest,
    ScenarioGroupUpdate,
)
from app.schemas.session import SessionResponse
from app.services import scenario_group_service
from app.utils.pagination import PaginatedResponse

router = APIRouter(prefix="/scenario-groups", tags=["scenario-groups"])


@router.post("", response_model=ScenarioGroupResponse, status_code=201)
async def create_scenario_group(
    data: ScenarioGroupCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """Create a new scenario group. Admin only."""
    return await scenario_group_service.create_group(db, data, user.id)


@router.get("", response_model=PaginatedResponse[ScenarioGroupResponse])
async def list_scenario_groups(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
):
    """List scenario groups for admin management."""
    groups, total = await scenario_group_service.list_groups(
        db, page=page, page_size=page_size, status=status, search=search
    )
    return PaginatedResponse.create(groups, total, page, page_size)


@router.get("/active", response_model=list[ScenarioGroupResponse])
async def list_active_scenario_groups(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """List active scenario groups for user training selection."""
    groups, _ = await scenario_group_service.list_groups(db, status="active", page_size=100)
    return groups


@router.post("/runs", response_model=ScenarioGroupRunResponse, status_code=201)
async def create_scenario_group_run(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Start a new run for an active scenario group."""
    return await scenario_group_service.create_run(db, group_id, user.id)


@router.get("/runs/{run_id}", response_model=ScenarioGroupRunResponse)
async def get_scenario_group_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get current progress for a scenario group run."""
    return await scenario_group_service.get_run(db, run_id, user.id)


@router.post(
    "/runs/{run_id}/items/{run_item_id}/session",
    response_model=SessionResponse,
    status_code=201,
)
async def create_scenario_group_run_item_session(
    run_id: str,
    run_item_id: str,
    request: ScenarioGroupRunSessionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create or return the single-scenario session for a group run item."""
    _run, session = await scenario_group_service.create_child_session(
        db, run_id, run_item_id, user.id, request.mode, retrain=request.retrain
    )
    await db.refresh(session, attribute_names=["scenario", "messages"])
    return session


@router.post("/runs/{run_id}/refresh-score", response_model=ScenarioGroupRunResponse)
async def refresh_scenario_group_run_score(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Refresh child scores and aggregate final group score when all children are scored."""
    return await scenario_group_service.refresh_run_score(db, run_id, user.id)


@router.get("/{group_id}", response_model=ScenarioGroupResponse)
async def get_scenario_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Get a scenario group by id."""
    return await scenario_group_service.get_group(db, group_id)


@router.put("/{group_id}", response_model=ScenarioGroupResponse)
async def update_scenario_group(
    group_id: str,
    data: ScenarioGroupUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
):
    """Update a scenario group. Admin only."""
    return await scenario_group_service.update_group(db, group_id, data)


@router.post("/{group_id}/transition", response_model=ScenarioGroupResponse)
async def transition_scenario_group_status(
    group_id: str,
    request: ScenarioGroupTransitionRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
):
    """Transition a scenario group between draft, active, and archived."""
    return await scenario_group_service.transition_group_status(db, group_id, request.status)


@router.delete("/{group_id}", status_code=204)
async def delete_scenario_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
):
    """Delete a non-active scenario group."""
    await scenario_group_service.delete_group(db, group_id)
    return Response(status_code=204)
