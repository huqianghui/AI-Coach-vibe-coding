"""Scenario CRUD API router: admin management of training scenarios."""

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_role
from app.models.user import User
from app.schemas.scenario import ScenarioCreate, ScenarioUpdate
from app.schemas.voice_live_instance import VoiceLiveInstanceSummary
from app.services import scenario_service
from app.services.conference_prompt_config import normalize_conference_prompt_config
from app.utils.pagination import PaginatedResponse

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


class HcpProfileBrief(BaseModel):
    """Minimal HCP profile data for scenario list display.

    Avatar/voice config lives exclusively on the linked VoiceLiveInstance
    (D-09/D-10, Phase 29) -- no inline avatar/voice columns on HcpProfile.
    """

    id: str
    name: str
    specialty: str = ""
    avatar_url: str = ""
    personality_type: str = "friendly"
    voice_live_instance_id: str | None = None
    voice_live_instance: VoiceLiveInstanceSummary | None = None

    model_config = ConfigDict(from_attributes=True)


class ScenarioOut(BaseModel):
    """Scenario response with JSON list fields parsed to Python lists."""

    id: str
    name: str
    description: str
    tags: list[str]
    mode: str
    difficulty: str
    status: str
    hcp_profile_id: str
    hcp_profile: HcpProfileBrief | None = None
    key_messages: list[str]
    conference_prompt_config: dict[str, Any]
    conference_prompt_version: int = 1
    skill_id: str
    skill_version_id: str | None = None
    rubric_id: str
    pass_threshold: int
    created_by: str
    created_at: str
    updated_at: str

    model_config = ConfigDict(from_attributes=True)

    @field_validator("tags", "key_messages", mode="before")
    @classmethod
    def parse_json_list(cls, v: str | list[str]) -> list[str]:
        """Parse JSON string field into Python list."""
        if isinstance(v, str):
            return json.loads(v)
        return v

    @field_validator("conference_prompt_config", mode="before")
    @classmethod
    def parse_conference_prompt_config(cls, v: str | dict[str, Any] | None) -> dict[str, Any]:
        """Parse and default the conference prompt config."""
        return normalize_conference_prompt_config(v)

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def datetime_to_str(cls, v: Any) -> str:
        """Convert datetime to ISO string."""
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)


@router.post("", response_model=ScenarioOut, status_code=201)
async def create_scenario(
    data: ScenarioCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """Create a new scenario. Admin only."""
    scenario = await scenario_service.create_scenario(db, data, user.id)
    return scenario


@router.get("", response_model=PaginatedResponse[ScenarioOut])
async def list_scenarios(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    mode: str | None = Query(None),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """List scenarios with optional filters. Admin only."""
    items, total = await scenario_service.get_scenarios(
        db, page=page, page_size=page_size, status=status, mode=mode, search=search
    )
    return PaginatedResponse.create(
        items=[ScenarioOut.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


# IMPORTANT: Static route /active BEFORE parameterized /{scenario_id} (Gotcha #3)
@router.get("/active", response_model=list[ScenarioOut])
async def list_active_scenarios(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List active scenarios for user selection. Accessible by authenticated users."""
    items, _ = await scenario_service.get_scenarios(db, status="active", page_size=100)
    return [ScenarioOut.model_validate(item) for item in items]


class TransitionRequest(BaseModel):
    """Request body for status transition."""

    status: str


@router.post("/{scenario_id}/transition", response_model=ScenarioOut)
async def transition_scenario_status(
    scenario_id: str,
    body: TransitionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """Transition scenario status. Admin only. Validates allowed transitions."""
    scenario = await scenario_service.transition_scenario_status(db, scenario_id, body.status)
    return scenario


@router.get("/{scenario_id}", response_model=ScenarioOut)
async def get_scenario(
    scenario_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get a single scenario with HCP profile. Accessible by any authenticated user."""
    scenario = await scenario_service.get_scenario(db, scenario_id)
    return scenario


@router.put("/{scenario_id}", response_model=ScenarioOut)
async def update_scenario(
    scenario_id: str,
    data: ScenarioUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """Update a scenario. Admin only."""
    scenario = await scenario_service.update_scenario(db, scenario_id, data)
    return scenario


@router.delete("/{scenario_id}", status_code=204)
async def delete_scenario(
    scenario_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """Delete a scenario. Admin only."""
    await scenario_service.delete_scenario(db, scenario_id)
    return Response(status_code=204)


@router.get("/{scenario_id}/skill")
async def get_scenario_skill(
    scenario_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get the Skill associated with a scenario. Returns skill summary or null."""
    from sqlalchemy import select

    from app.models.skill import Skill, SkillVersion

    scenario = await scenario_service.get_scenario(db, scenario_id)
    if not scenario.skill_id:
        return None

    result = await db.execute(select(Skill).where(Skill.id == scenario.skill_id))
    skill = result.scalar_one_or_none()
    if skill is None:
        return None

    # Get pinned version info
    version_number = None
    if scenario.skill_version_id:
        ver_result = await db.execute(
            select(SkillVersion).where(SkillVersion.id == scenario.skill_version_id)
        )
        version = ver_result.scalar_one_or_none()
        if version:
            version_number = version.version_number

    return {
        "id": skill.id,
        "name": skill.name,
        "status": skill.status,
        "quality_score": skill.quality_score,
        "version_number": version_number,
        "skill_version_id": scenario.skill_version_id,
    }


@router.post("/{scenario_id}/clone", response_model=ScenarioOut, status_code=201)
async def clone_scenario(
    scenario_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """Clone an existing scenario. Admin only."""
    scenario = await scenario_service.clone_scenario(db, scenario_id, user.id)
    return scenario
