"""HCP Profile CRUD API router: admin-only management of Healthcare Professional profiles."""

import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_role
from app.models.user import User
from app.schemas.hcp_profile import HcpProfileCreate, HcpProfileUpdate
from app.services import agent_chat_service, hcp_profile_service
from app.utils.pagination import PaginatedResponse

router = APIRouter(prefix="/hcp-profiles", tags=["hcp-profiles"])


class HcpProfileOut(BaseModel):
    """HCP profile response with JSON list fields parsed to Python lists."""

    id: str
    name: str
    specialty: str
    hospital: str
    title: str
    avatar_url: str
    personality_type: str
    emotional_state: int
    communication_style: int
    expertise_areas: list[str]
    prescribing_habits: str
    concerns: str
    objections: list[str]
    probe_topics: list[str]
    difficulty: str
    is_active: bool
    agent_id: str
    agent_version: str
    agent_sync_status: str
    agent_sync_error: str

    # Voice Live Instance reference
    voice_live_instance_id: str | None = None

    agent_instructions_override: str = ""

    # Knowledge Base config count (Phase 17)
    knowledge_config_count: int = 0

    created_by: str
    created_at: str
    updated_at: str

    model_config = ConfigDict(from_attributes=True)

    @field_validator("expertise_areas", "objections", "probe_topics", mode="before")
    @classmethod
    def parse_json_list(cls, v: str | list[str]) -> list[str]:
        """Parse JSON string fields into Python lists."""
        if isinstance(v, str):
            return json.loads(v)
        return v

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def datetime_to_str(cls, v: object) -> str:
        """Convert datetime to ISO string."""
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v)


@router.post("", response_model=HcpProfileOut, status_code=201)
async def create_profile(
    data: HcpProfileCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """Create a new HCP profile. Admin only."""
    profile = await hcp_profile_service.create_hcp_profile(db, data, user.id)
    return profile


@router.get("", response_model=PaginatedResponse[HcpProfileOut])
async def list_profiles(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    is_active: bool | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """List HCP profiles with optional search and filter. Admin only."""
    items, total = await hcp_profile_service.get_hcp_profiles(
        db, page=page, page_size=page_size, search=search, is_active=is_active
    )
    return PaginatedResponse.create(
        items=[HcpProfileOut.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{profile_id}", response_model=HcpProfileOut)
async def get_profile(
    profile_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """Get a single HCP profile by ID. Admin only."""
    profile = await hcp_profile_service.get_hcp_profile(db, profile_id)
    return profile


@router.put("/{profile_id}", response_model=HcpProfileOut)
async def update_profile(
    profile_id: str,
    data: HcpProfileUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """Update an HCP profile. Admin only."""
    profile = await hcp_profile_service.update_hcp_profile(db, profile_id, data)
    return profile


@router.post("/{profile_id}/retry-sync", response_model=HcpProfileOut)
async def retry_sync(
    profile_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """Retry AI Foundry agent sync for a profile with failed status. Admin only. (D-11)"""
    profile = await hcp_profile_service.retry_agent_sync(db, profile_id)
    return profile


@router.post("/batch-sync")
async def batch_sync_agents(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """Batch sync agents for all profiles with missing/failed agent_id. Admin only."""
    result = await hcp_profile_service.batch_sync_agents(db)
    return result


class InstructionsPreviewRequest(BaseModel):
    """Profile data for instructions generation preview."""

    name: str = ""
    specialty: str = ""
    hospital: str = ""
    title: str = ""
    personality_type: str = "friendly"
    emotional_state: int = 50
    communication_style: int = 50
    expertise_areas: list[str] = []
    prescribing_habits: str = ""
    concerns: str = ""
    objections: list[str] = []
    probe_topics: list[str] = []
    difficulty: str = "medium"
    agent_instructions_override: str = ""


class InstructionsPreviewResponse(BaseModel):
    """Generated instructions text with precedence flag."""

    instructions: str
    is_override: bool


@router.post("/preview-instructions", response_model=InstructionsPreviewResponse)
async def preview_instructions(
    body: InstructionsPreviewRequest,
    user: User = Depends(require_role("admin")),
):
    """Preview auto-generated agent instructions from profile data. Admin only.

    Instruction precedence: override (non-empty) > auto-generated from template.
    """
    from app.services.agent_sync_service import build_agent_instructions

    profile_data = body.model_dump()
    instructions = build_agent_instructions(profile_data)
    override_text = body.agent_instructions_override
    is_override = bool(override_text and override_text.strip())
    return InstructionsPreviewResponse(instructions=instructions, is_override=is_override)


class TestChatRequest(BaseModel):
    """Request body for test chat with agent."""

    message: str
    previous_response_id: str | None = None


class TestChatResponse(BaseModel):
    """Response from test chat with agent."""

    response_text: str
    response_id: str
    agent_name: str
    agent_version: str


class AgentPortalUrlResponse(BaseModel):
    """Azure Portal URL for viewing agent in playground."""

    url: str
    agent_name: str
    agent_version: str


@router.post("/{profile_id}/test-chat", response_model=TestChatResponse)
async def test_chat(
    profile_id: str,
    body: TestChatRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """Send a test message to the HCP's AI Foundry Agent. Admin only.

    The chat session will appear in Azure Portal's agent playground.
    Pass previous_response_id for multi-turn conversation.
    """
    profile = await hcp_profile_service.get_hcp_profile(db, profile_id)
    if not profile.agent_id:
        from app.utils.exceptions import bad_request

        bad_request("No agent synced for this profile. Sync the agent first.")

    result = await agent_chat_service.chat_with_agent(
        db,
        agent_name=profile.agent_id,
        agent_version=profile.agent_version or "1",
        message=body.message,
        previous_response_id=body.previous_response_id,
    )
    return result


@router.get("/{profile_id}/portal-url", response_model=AgentPortalUrlResponse)
async def get_agent_portal_url(
    profile_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """Get the Azure Portal URL for viewing this agent in the playground. Admin only.

    Auto-discovers subscription, resource group, resource name from the
    connections API — no extra env vars needed beyond endpoint + key.
    """
    from app.services import agent_sync_service

    profile = await hcp_profile_service.get_hcp_profile(db, profile_id)
    if not profile.agent_id:
        from app.utils.exceptions import bad_request

        bad_request("No agent synced for this profile.")

    # Auto-discover portal URL components from connections API
    components = await agent_sync_service.get_portal_url_components(db)
    sub_hash = components.get("subscription_hash", "")
    rg = components.get("resource_group", "")
    resource_name = components.get("resource_name", "")
    project_name = components.get("project_name", "")

    # Always fetch latest version from Azure (version increments on each update)
    version = await agent_sync_service.get_agent_latest_version(db, profile.agent_id)
    if sub_hash and rg and resource_name and project_name:
        url = (
            f"https://ai.azure.com/nextgen/r/"
            f"{sub_hash},{rg},,{resource_name},{project_name}"
            f"/build/agents/{profile.agent_id}/build?version={version}"
        )
    else:
        # Fallback: generic Azure AI Studio URL
        url = "https://ai.azure.com"

    return AgentPortalUrlResponse(
        url=url,
        agent_name=profile.agent_id,
        agent_version=version,
    )


@router.delete("/{profile_id}", status_code=204)
async def delete_profile(
    profile_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """Delete an HCP profile. Admin only."""
    await hcp_profile_service.delete_hcp_profile(db, profile_id)
    return Response(status_code=204)
