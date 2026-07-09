"""Scenario group service: weighted multi-scenario training orchestration."""

import json
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.hcp_profile import HcpProfile
from app.models.scenario import Scenario
from app.models.scenario_group import (
    ScenarioGroup,
    ScenarioGroupItem,
    ScenarioGroupRun,
    ScenarioGroupRunItem,
)
from app.models.session import CoachingSession
from app.schemas.scenario_group import ScenarioGroupCreate, ScenarioGroupUpdate
from app.services import session_service
from app.utils.datetime import utc_now_naive
from app.utils.exceptions import AppException, bad_request, not_found

VALID_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"active"},
    "active": {"archived"},
}


def _group_options():
    return (
        selectinload(ScenarioGroup.items)
        .selectinload(ScenarioGroupItem.scenario)
        .selectinload(Scenario.hcp_profile)
        .selectinload(HcpProfile.voice_live_instance)
    )


def _run_options():
    return (
        selectinload(ScenarioGroupRun.group),
        selectinload(ScenarioGroupRun.items)
        .selectinload(ScenarioGroupRunItem.scenario)
        .selectinload(Scenario.hcp_profile)
        .selectinload(HcpProfile.voice_live_instance),
    )


async def _reload_group(db: AsyncSession, group_id: str) -> ScenarioGroup:
    result = await db.execute(
        select(ScenarioGroup)
        .options(_group_options())
        .where(ScenarioGroup.id == group_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


async def _reload_run(db: AsyncSession, run_id: str) -> ScenarioGroupRun:
    result = await db.execute(
        select(ScenarioGroupRun)
        .options(*_run_options())
        .where(ScenarioGroupRun.id == run_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


async def _sync_run_items_from_sessions(db: AsyncSession, run: ScenarioGroupRun) -> None:
    """Mirror child CoachingSession status and scores into group run items."""
    total_weight = 0
    weighted_score = 0.0
    all_scored = bool(run.items)
    has_progress = False

    for item in run.items:
        session = None
        if item.session_id:
            result = await db.execute(
                select(CoachingSession).where(CoachingSession.id == item.session_id)
            )
            session = result.scalar_one_or_none()

        if session is None or session.status != "in_progress":
            best_scored_result = await db.execute(
                select(CoachingSession)
                .where(
                    CoachingSession.user_id == run.user_id,
                    CoachingSession.scenario_id == item.scenario_id,
                    CoachingSession.status == "scored",
                    CoachingSession.overall_score.is_not(None),
                )
                .order_by(CoachingSession.overall_score.desc(), CoachingSession.created_at.desc())
                .limit(1)
            )
            best_scored_session = best_scored_result.scalar_one_or_none()
            if best_scored_session is not None:
                session = best_scored_session
                item.session_id = best_scored_session.id
            elif session is None:
                latest_completed_result = await db.execute(
                    select(CoachingSession)
                    .where(
                        CoachingSession.user_id == run.user_id,
                        CoachingSession.scenario_id == item.scenario_id,
                        CoachingSession.status == "completed",
                    )
                    .order_by(CoachingSession.created_at.desc())
                    .limit(1)
                )
                session = latest_completed_result.scalar_one_or_none()
                if session is not None:
                    item.session_id = session.id

        if session is None:
            all_scored = False
            continue

        has_progress = True
        if session.status == "scored" and session.overall_score is not None:
            item.status = "scored"
            item.score = session.overall_score
            item.passed = session.passed
            total_weight += item.weight
            weighted_score += session.overall_score * item.weight
        elif session.status == "completed":
            item.status = "completed"
            item.score = None
            item.passed = None
            all_scored = False
        else:
            item.status = "in_progress"
            item.score = None
            item.passed = None
            all_scored = False

    if all_scored and total_weight > 0:
        overall = round(weighted_score / total_weight, 1)
        run.status = "scored"
        run.completed_at = run.completed_at or utc_now_naive()
        run.overall_score = overall
        run.passed = overall >= run.group.pass_threshold
    elif has_progress:
        run.status = "in_progress"
        run.completed_at = None
        run.overall_score = None
        run.passed = None


async def _load_scenarios(db: AsyncSession, scenario_ids: Sequence[str]) -> dict[str, Scenario]:
    result = await db.execute(select(Scenario).where(Scenario.id.in_(list(scenario_ids))))
    scenarios = {scenario.id: scenario for scenario in result.scalars().all()}
    missing = [scenario_id for scenario_id in scenario_ids if scenario_id not in scenarios]
    if missing:
        not_found(f"Scenario not found: {missing[0]}")
    return scenarios


def _validate_group_items(items) -> None:
    if not items:
        bad_request("Scenario group must contain at least one scenario")
    ids = [item.scenario_id for item in items]
    if len(ids) != len(set(ids)):
        bad_request("Scenario group cannot contain duplicate scenarios")


async def _replace_items(db: AsyncSession, group: ScenarioGroup, items) -> None:
    _validate_group_items(items)
    scenarios = await _load_scenarios(db, [item.scenario_id for item in items])
    for scenario in scenarios.values():
        if scenario.status != "active":
            bad_request("Scenario group can only include active scenarios")

    existing_result = await db.execute(
        select(ScenarioGroupItem).where(ScenarioGroupItem.group_id == group.id)
    )
    for existing in existing_result.scalars().all():
        await db.delete(existing)
    await db.flush()

    for index, item in enumerate(items):
        db.add(
            ScenarioGroupItem(
                group_id=group.id,
                scenario_id=item.scenario_id,
                weight=item.weight,
                sort_order=item.sort_order if item.sort_order is not None else index,
            )
        )


async def create_group(db: AsyncSession, data: ScenarioGroupCreate, user_id: str) -> ScenarioGroup:
    """Create a draft scenario group with weighted active scenarios."""
    _validate_group_items(data.items)
    group = ScenarioGroup(
        name=data.name,
        description=data.description,
        tags=json.dumps(data.tags),
        pass_threshold=data.pass_threshold,
        created_by=user_id,
    )
    db.add(group)
    await db.flush()
    await _replace_items(db, group, data.items)
    await db.flush()
    return await _reload_group(db, group.id)


async def list_groups(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    search: str | None = None,
) -> tuple[list[ScenarioGroup], int]:
    """List scenario groups with optional filters."""
    filters = []
    if status:
        filters.append(ScenarioGroup.status == status)
    if search:
        filters.append(ScenarioGroup.name.ilike(f"%{search}%"))

    count_result = await db.execute(select(func.count()).select_from(ScenarioGroup).where(*filters))
    total = count_result.scalar() or 0

    result = await db.execute(
        select(ScenarioGroup)
        .options(_group_options())
        .where(*filters)
        .order_by(ScenarioGroup.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), total


async def get_group(db: AsyncSession, group_id: str) -> ScenarioGroup:
    """Get a scenario group by id."""
    result = await db.execute(
        select(ScenarioGroup).options(_group_options()).where(ScenarioGroup.id == group_id)
    )
    group = result.scalar_one_or_none()
    if group is None:
        not_found("Scenario group not found")
    return group


async def update_group(db: AsyncSession, group_id: str, data: ScenarioGroupUpdate) -> ScenarioGroup:
    """Update an editable scenario group."""
    group = await get_group(db, group_id)
    if group.status == "archived":
        bad_request("Cannot edit an archived scenario group")

    update_data = data.model_dump(exclude_unset=True, exclude={"items"})
    if "tags" in update_data and update_data["tags"] is not None:
        update_data["tags"] = json.dumps(update_data["tags"])
    for field, value in update_data.items():
        setattr(group, field, value)

    if data.items is not None:
        await _replace_items(db, group, data.items)

    await db.flush()
    return await _reload_group(db, group.id)


async def transition_group_status(
    db: AsyncSession, group_id: str, new_status: str
) -> ScenarioGroup:
    """Transition scenario group status."""
    group = await get_group(db, group_id)
    allowed = VALID_TRANSITIONS.get(group.status, set())
    if new_status not in allowed:
        bad_request(f"Cannot transition from '{group.status}' to '{new_status}'")
    if new_status == "active" and not group.items:
        bad_request("Cannot activate a scenario group without scenarios")
    group.status = new_status
    await db.flush()
    return await _reload_group(db, group.id)


async def delete_group(db: AsyncSession, group_id: str) -> None:
    """Delete a scenario group."""
    group = await get_group(db, group_id)
    if group.status == "active":
        bad_request("Cannot delete an active scenario group. Archive it first.")
    await db.delete(group)
    await db.flush()


async def create_run(db: AsyncSession, group_id: str, user_id: str) -> ScenarioGroupRun:
    """Start a scenario group run for the current user."""
    group = await get_group(db, group_id)
    if group.status != "active":
        raise AppException(409, "GROUP_NOT_ACTIVE", "Scenario group is not active")
    if not group.items:
        bad_request("Scenario group has no scenarios")

    run = ScenarioGroupRun(
        user_id=user_id,
        group_id=group_id,
        status="in_progress",
        started_at=utc_now_naive(),
    )
    db.add(run)
    await db.flush()

    for item in group.items:
        db.add(
            ScenarioGroupRunItem(
                run_id=run.id,
                group_item_id=item.id,
                scenario_id=item.scenario_id,
                weight=item.weight,
                sort_order=item.sort_order,
            )
        )
    await db.flush()
    return await _reload_run(db, run.id)


async def get_run(db: AsyncSession, run_id: str, user_id: str) -> ScenarioGroupRun:
    """Get a group run owned by the current user."""
    result = await db.execute(
        select(ScenarioGroupRun).options(*_run_options()).where(ScenarioGroupRun.id == run_id)
    )
    run = result.scalar_one_or_none()
    if run is None:
        not_found("Scenario group run not found")
    if run.user_id != user_id:
        raise AppException(403, "FORBIDDEN", "Scenario group run does not belong to this user")
    await _sync_run_items_from_sessions(db, run)
    await db.flush()
    return await _reload_run(db, run_id)


async def create_child_session(
    db: AsyncSession,
    run_id: str,
    run_item_id: str,
    user_id: str,
    mode: str,
    retrain: bool = False,
) -> tuple[ScenarioGroupRun, CoachingSession]:
    """Create or return the child session for one run item."""
    run = await get_run(db, run_id, user_id)
    if run.status not in ("created", "in_progress") and not retrain:
        raise AppException(409, "GROUP_RUN_CLOSED", "Scenario group run is no longer active")

    run_item = next((item for item in run.items if item.id == run_item_id), None)
    if run_item is None:
        not_found("Scenario group run item not found")
    if run_item.session_id and not retrain:
        result = await db.execute(
            select(CoachingSession).where(CoachingSession.id == run_item.session_id)
        )
        session = result.scalar_one_or_none()
        if session is None:
            not_found("Child session not found")
        return run, session

    scenario = run_item.scenario
    if scenario is None:
        scenario_result = await db.execute(
            select(Scenario).where(Scenario.id == run_item.scenario_id)
        )
        scenario = scenario_result.scalar_one_or_none()
    if scenario is not None and scenario.mode == "conference":
        from app.services import conference_service

        session = await conference_service.create_conference_session(
            db, run_item.scenario_id, user_id, mode
        )
    else:
        session = await session_service.create_session(db, run_item.scenario_id, user_id, mode)
    run_item.session_id = session.id
    run_item.status = "in_progress"
    run_item.score = None
    run_item.passed = None
    run.status = "in_progress"
    run.completed_at = None
    run.overall_score = None
    run.passed = None
    await db.flush()
    return await _reload_run(db, run_id), session


async def refresh_run_score(db: AsyncSession, run_id: str, user_id: str) -> ScenarioGroupRun:
    """Refresh child item scores and aggregate the group run if all are scored."""
    run = await get_run(db, run_id, user_id)
    await _sync_run_items_from_sessions(db, run)
    await db.flush()
    return await _reload_run(db, run_id)
