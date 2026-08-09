"""HCP Profile service: CRUD operations for Healthcare Professional profiles.

Includes automatic agent sync hooks: creating/updating/deleting HCP profiles
triggers corresponding AI Foundry Agent operations via agent_sync_service.
"""

import json
import logging

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.conference import ConferenceAudienceHcp
from app.models.hcp_profile import HcpProfile
from app.models.message import SessionMessage
from app.models.scenario import Scenario
from app.models.score import ScoreDetail, SessionScore
from app.models.session import CoachingSession
from app.schemas.hcp_profile import HcpProfileCreate, HcpProfileUpdate
from app.services import agent_sync_service
from app.utils.exceptions import bad_request, not_found

logger = logging.getLogger(__name__)

# JSON list fields that need serialization/deserialization
_JSON_LIST_FIELDS = ("expertise_areas", "objections", "probe_topics")


async def create_hcp_profile(db: AsyncSession, data: HcpProfileCreate, user_id: str) -> HcpProfile:
    """Create a new HCP profile."""
    # Pre-fetch config BEFORE any writes to avoid SQLite locking
    try:
        endpoint, api_key, model = await agent_sync_service.prefetch_sync_config(db)
    except Exception:
        logger.warning("Failed to prefetch agent sync config for create", exc_info=True)
        endpoint, api_key, model = None, None, None

    profile_data = data.model_dump()
    profile_data["created_by"] = user_id

    # Serialize list fields to JSON strings
    for field in _JSON_LIST_FIELDS:
        if field in profile_data and isinstance(profile_data[field], list):
            profile_data[field] = json.dumps(profile_data[field])

    profile = HcpProfile(**profile_data)
    db.add(profile)
    await db.flush()
    await db.refresh(profile)

    # Auto-sync agent to AI Foundry (D-01, D-02)
    profile.agent_sync_status = "pending"
    await db.flush()
    try:
        result = await agent_sync_service.sync_agent_for_profile(
            db,
            profile,
            prefetched_endpoint=endpoint,
            prefetched_key=api_key,
            prefetched_model=model,
        )
        profile.agent_id = result.get("id", "")
        profile.agent_version = str(result.get("version", ""))
        profile.agent_sync_status = "synced"
        profile.agent_sync_error = ""
    except Exception as e:
        profile.agent_sync_status = "failed"
        profile.agent_sync_error = str(e)[:500]
    await db.flush()
    await db.refresh(profile)
    return profile


async def get_hcp_profiles(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    is_active: bool | None = None,
) -> tuple[list[HcpProfile], int]:
    """List HCP profiles with optional search and active filters."""
    query = select(HcpProfile)

    if search:
        search_filter = f"%{search}%"
        query = query.where(
            or_(
                HcpProfile.name.ilike(search_filter),
                HcpProfile.specialty.ilike(search_filter),
            )
        )

    if is_active is not None:
        query = query.where(HcpProfile.is_active == is_active)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate with eager-loaded voice_live_instance for FK display + KB configs for count
    query = query.options(
        selectinload(HcpProfile.voice_live_instance),
        selectinload(HcpProfile.knowledge_configs),
    )
    query = query.order_by(HcpProfile.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return items, total


async def get_hcp_profile(db: AsyncSession, profile_id: str) -> HcpProfile:
    """Get a single HCP profile by ID. Raises 404 if not found."""
    result = await db.execute(
        select(HcpProfile)
        .options(
            selectinload(HcpProfile.voice_live_instance),
            selectinload(HcpProfile.knowledge_configs),
        )
        .where(HcpProfile.id == profile_id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        not_found("HCP profile not found")
    return profile


async def update_hcp_profile(
    db: AsyncSession, profile_id: str, data: HcpProfileUpdate
) -> HcpProfile:
    """Update an existing HCP profile with partial data."""
    # Pre-fetch config BEFORE any writes to avoid SQLite locking
    try:
        endpoint, api_key, model = await agent_sync_service.prefetch_sync_config(db)
    except Exception:
        logger.warning("Failed to prefetch agent sync config for update", exc_info=True)
        endpoint, api_key, model = None, None, None

    profile = await get_hcp_profile(db, profile_id)
    update_data = data.model_dump(exclude_unset=True)

    # D-13: voice_live_instance_id is required -- if the caller explicitly sends it,
    # it cannot be cleared (None or empty string). Omitting the key entirely is fine
    # (partial update leaves the existing value untouched).
    if "voice_live_instance_id" in update_data and not update_data["voice_live_instance_id"]:
        bad_request("voice_live_instance_id is required and cannot be cleared")

    # Serialize list fields to JSON strings
    for field in _JSON_LIST_FIELDS:
        if field in update_data and isinstance(update_data[field], list):
            update_data[field] = json.dumps(update_data[field])

    for field, value in update_data.items():
        setattr(profile, field, value)

    await db.flush()
    # Re-query with selectinload so voice_live_instance is available for
    # build_voice_live_metadata() in async context (plain refresh loses relationships).
    reload_result = await db.execute(
        select(HcpProfile)
        .options(selectinload(HcpProfile.voice_live_instance))
        .where(HcpProfile.id == profile_id)
    )
    profile = reload_result.scalar_one_or_none() or profile

    # Re-sync agent instructions on profile update (D-01)
    profile.agent_sync_status = "pending"
    await db.flush()
    try:
        result = await agent_sync_service.sync_agent_for_profile(
            db,
            profile,
            prefetched_endpoint=endpoint,
            prefetched_key=api_key,
            prefetched_model=model,
        )
        if not profile.agent_id and result.get("id"):
            profile.agent_id = result["id"]
        profile.agent_version = str(result.get("version", ""))
        profile.agent_sync_status = "synced"
        profile.agent_sync_error = ""
    except Exception as e:
        profile.agent_sync_status = "failed"
        profile.agent_sync_error = str(e)[:500]
    await db.flush()
    await db.refresh(profile)
    return profile


async def delete_hcp_profile(db: AsyncSession, profile_id: str) -> None:
    """Delete an HCP profile by ID, cleaning up all dependent records."""
    profile = await get_hcp_profile(db, profile_id)

    # Delete corresponding AI Foundry Agent (D-01)
    if profile.agent_id:
        try:
            await agent_sync_service.delete_agent(db, profile.agent_id)
        except Exception:
            logger.warning(
                "Agent deletion failed for %s, proceeding with profile deletion",
                profile.agent_id,
                exc_info=True,
            )

    # Clean up dependent records to avoid FK constraint violations.
    # Dependency chain: hcp_profile ← scenario ← coaching_session ← messages/scores
    #                   hcp_profile ← conference_audience_hcps
    #                   scenario    ← conference_audience_hcps

    # 1. Get scenario IDs for this profile
    scenario_rows = await db.execute(
        select(Scenario.id).where(Scenario.hcp_profile_id == profile_id)
    )
    scenario_ids = [row[0] for row in scenario_rows.all()]

    if scenario_ids:
        # 2. Get coaching session IDs for those scenarios
        session_rows = await db.execute(
            select(CoachingSession.id).where(CoachingSession.scenario_id.in_(scenario_ids))
        )
        session_ids = [row[0] for row in session_rows.all()]

        if session_ids:
            # 3a. Delete score_details → session_scores → session_messages
            score_rows = await db.execute(
                select(SessionScore.id).where(SessionScore.session_id.in_(session_ids))
            )
            score_ids = [row[0] for row in score_rows.all()]
            if score_ids:
                await db.execute(delete(ScoreDetail).where(ScoreDetail.score_id.in_(score_ids)))
            await db.execute(delete(SessionScore).where(SessionScore.session_id.in_(session_ids)))
            await db.execute(
                delete(SessionMessage).where(SessionMessage.session_id.in_(session_ids))
            )
            # 3b. Delete coaching sessions
            await db.execute(delete(CoachingSession).where(CoachingSession.id.in_(session_ids)))

        # 4. Delete conference_audience_hcps referencing these scenarios
        await db.execute(
            delete(ConferenceAudienceHcp).where(ConferenceAudienceHcp.scenario_id.in_(scenario_ids))
        )

        # 5. Delete scenarios
        await db.execute(delete(Scenario).where(Scenario.hcp_profile_id == profile_id))

    # 6. Delete conference_audience_hcps directly referencing this HCP profile
    await db.execute(
        delete(ConferenceAudienceHcp).where(ConferenceAudienceHcp.hcp_profile_id == profile_id)
    )

    await db.delete(profile)
    await db.flush()


async def retry_agent_sync(db: AsyncSession, profile_id: str) -> HcpProfile:
    """Retry agent sync for a profile with failed sync status (D-11)."""
    # Pre-fetch config BEFORE any writes to avoid SQLite locking
    try:
        endpoint, api_key, model = await agent_sync_service.prefetch_sync_config(db)
    except Exception:
        logger.warning("Failed to prefetch agent sync config for retry", exc_info=True)
        endpoint, api_key, model = None, None, None

    profile = await get_hcp_profile(db, profile_id)
    profile.agent_sync_status = "pending"
    profile.agent_sync_error = ""
    await db.flush()
    try:
        result = await agent_sync_service.sync_agent_for_profile(
            db,
            profile,
            prefetched_endpoint=endpoint,
            prefetched_key=api_key,
            prefetched_model=model,
        )
        if result.get("id"):
            profile.agent_id = result["id"]
        profile.agent_version = str(result.get("version", ""))
        profile.agent_sync_status = "synced"
        profile.agent_sync_error = ""
    except Exception as e:
        profile.agent_sync_status = "failed"
        profile.agent_sync_error = str(e)[:500]
    await db.flush()
    await db.refresh(profile)
    return profile


async def batch_sync_agents(db: AsyncSession) -> dict:
    """Batch sync agents for all profiles with missing or failed agent_id.

    Returns summary dict with counts of synced/failed/skipped profiles.
    """
    # Pre-fetch config once for all syncs
    try:
        endpoint, api_key, model = await agent_sync_service.prefetch_sync_config(db)
    except Exception as e:
        return {"synced": 0, "failed": 0, "skipped": 0, "error": str(e)[:500]}

    # Find profiles needing sync
    result = await db.execute(
        select(HcpProfile)
        .options(selectinload(HcpProfile.voice_live_instance))
        .where(
            (HcpProfile.agent_id == "")
            | (HcpProfile.agent_id.is_(None))
            | (HcpProfile.agent_sync_status == "failed")
        )
    )
    profiles = list(result.scalars().all())

    synced = 0
    failed = 0
    for profile in profiles:
        profile.agent_sync_status = "pending"
        profile.agent_sync_error = ""
        await db.flush()
        try:
            sync_result = await agent_sync_service.sync_agent_for_profile(
                db,
                profile,
                prefetched_endpoint=endpoint,
                prefetched_key=api_key,
                prefetched_model=model,
            )
            if sync_result.get("id"):
                profile.agent_id = sync_result["id"]
            profile.agent_version = str(sync_result.get("version", ""))
            profile.agent_sync_status = "synced"
            profile.agent_sync_error = ""
            synced += 1
        except Exception as e:
            profile.agent_sync_status = "failed"
            profile.agent_sync_error = str(e)[:500]
            failed += 1
        await db.flush()

    return {"synced": synced, "failed": failed, "total": len(profiles)}
