"""Session lifecycle management: create, message, end, key message detection."""

import json
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.message import SessionMessage
from app.models.scenario import Scenario
from app.models.session import CoachingSession
from app.services.prompt_builder import build_key_message_detection_prompt
from app.utils.exceptions import AppException, NotFoundException


async def create_session(
    db: AsyncSession, scenario_id: str, user_id: str, mode: str = "text"
) -> CoachingSession:
    """Create a new coaching session for a scenario.

    Verifies the scenario exists and is active, initializes key_messages_status
    tracking from the scenario's key messages.
    """
    result = await db.execute(select(Scenario).where(Scenario.id == scenario_id))
    scenario = result.scalar_one_or_none()
    if scenario is None:
        raise NotFoundException("Scenario not found")
    if scenario.status != "active":
        raise AppException(
            status_code=409,
            code="SCENARIO_NOT_ACTIVE",
            message="Scenario is not active",
        )

    # Initialize key messages tracking
    key_messages = json.loads(scenario.key_messages)
    key_messages_status = [
        {"message": msg, "delivered": False, "detected_at": None} for msg in key_messages
    ]

    # Phase 24: Generate and snapshot Skill Focus instruction (D-03)
    focus_instruction = None
    if scenario.skill_id:
        from app.services.skill_focus_service import compose_focus_instruction, extract_sop_steps
        from app.services.skill_manager import load_skill_for_scenario

        skill_content = await load_skill_for_scenario(db, scenario_id)
        if skill_content:
            sop_steps = extract_sop_steps(skill_content.content)
            focus_instruction = compose_focus_instruction(skill_content, 0, sop_steps)

    session = CoachingSession(
        user_id=user_id,
        scenario_id=scenario_id,
        status="created",
        mode=mode,
        key_messages_status=json.dumps(key_messages_status),
        # Skill audit trail: snapshot from scenario at session creation time
        skill_id=scenario.skill_id,
        skill_version_id=scenario.skill_version_id,
        # Phase 24: Focus instruction snapshot (D-03)
        focus_instruction=focus_instruction,
        sop_current_step=0,
    )
    db.add(session)
    await db.flush()
    return session


async def update_sop_progress(
    db: AsyncSession, session: CoachingSession, messages: list[dict]
) -> str | None:
    """Update SOP progress after user message. Returns updated focus_instruction.

    Per D-06: Uses LLM to detect current SOP step.
    Per D-05: Returns updated focus_instruction with new progress hint.
    """
    if not session.focus_instruction or not session.skill_id:
        return None

    from app.services import config_service
    from app.services.skill_focus_service import (
        compose_focus_instruction,
        detect_sop_step,
        extract_sop_steps,
    )
    from app.services.skill_manager import load_skill_for_scenario

    skill_content = await load_skill_for_scenario(db, session.scenario_id)
    if not skill_content:
        return session.focus_instruction

    sop_steps = extract_sop_steps(skill_content.content)
    if not sop_steps:
        return session.focus_instruction

    # Get LLM endpoint for progress detection
    endpoint = await config_service.get_effective_endpoint(db, "azure_openai")
    api_key = await config_service.get_effective_key(db, "azure_openai")

    if endpoint and api_key:
        new_step = await detect_sop_step(messages, sop_steps, endpoint, api_key)
        session.sop_current_step = new_step
    else:
        # No LLM configured — increment step heuristically (1 step per 3 messages)
        new_step = min(len(messages) // 3, len(sop_steps))
        session.sop_current_step = new_step

    # Recompose focus instruction with updated progress
    updated_instruction = compose_focus_instruction(skill_content, new_step, sop_steps)
    session.focus_instruction = updated_instruction
    await db.flush()
    return updated_instruction


async def get_session(db: AsyncSession, session_id: str, user_id: str) -> CoachingSession:
    """Fetch a session with eager-loaded scenario and HCP profile.

    Verifies the session belongs to the requesting user.
    """
    result = await db.execute(
        select(CoachingSession)
        .options(
            selectinload(CoachingSession.scenario).selectinload(Scenario.hcp_profile),
            selectinload(CoachingSession.messages),
        )
        .where(CoachingSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise NotFoundException("Session not found")
    if session.user_id != user_id:
        raise AppException(
            status_code=403,
            code="FORBIDDEN",
            message="Session does not belong to this user",
        )
    return session


async def get_user_sessions(
    db: AsyncSession, user_id: str, page: int = 1, page_size: int = 20
) -> tuple[list[CoachingSession], int]:
    """List a user's sessions with pagination, ordered by created_at desc."""
    # Count total
    count_result = await db.execute(
        select(func.count()).select_from(CoachingSession).where(CoachingSession.user_id == user_id)
    )
    total = count_result.scalar_one()

    # Fetch page with eagerly loaded scenario + messages for derived properties
    offset = (page - 1) * page_size
    result = await db.execute(
        select(CoachingSession)
        .options(selectinload(CoachingSession.scenario), selectinload(CoachingSession.messages))
        .where(CoachingSession.user_id == user_id)
        .order_by(CoachingSession.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    sessions = list(result.scalars().all())
    return sessions, total


async def get_active_session(db: AsyncSession, user_id: str) -> CoachingSession | None:
    """Get the user's currently active (in_progress) session, if any."""
    result = await db.execute(
        select(CoachingSession)
        .options(
            selectinload(CoachingSession.scenario).selectinload(Scenario.hcp_profile),
            selectinload(CoachingSession.messages),
        )
        .where(
            CoachingSession.user_id == user_id,
            CoachingSession.status == "in_progress",
        )
        .order_by(CoachingSession.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def save_message(
    db: AsyncSession, session_id: str, role: str, content: str
) -> SessionMessage:
    """Save a message to a coaching session.

    If this is the first user message and session is 'created',
    transitions the session to 'in_progress' and sets started_at.
    """
    # Count existing messages to determine message_index
    count_result = await db.execute(
        select(func.count())
        .select_from(SessionMessage)
        .where(SessionMessage.session_id == session_id)
    )
    message_index = count_result.scalar_one()

    message = SessionMessage(
        session_id=session_id,
        role=role,
        content=content,
        message_index=message_index,
    )
    db.add(message)

    # Transition created -> in_progress on first user message
    if role == "user" and message_index == 0:
        result = await db.execute(select(CoachingSession).where(CoachingSession.id == session_id))
        session = result.scalar_one_or_none()
        if session and session.status == "created":
            session.status = "in_progress"
            session.started_at = datetime.now(UTC)

    await db.flush()
    return message


async def end_session(db: AsyncSession, session_id: str, user_id: str) -> CoachingSession:
    """End a coaching session, transitioning from in_progress to completed.

    Calculates duration_seconds from started_at to now.
    """
    result = await db.execute(select(CoachingSession).where(CoachingSession.id == session_id))
    session = result.scalar_one_or_none()
    if session is None:
        raise NotFoundException("Session not found")
    if session.user_id != user_id:
        raise AppException(
            status_code=403,
            code="FORBIDDEN",
            message="Session does not belong to this user",
        )
    if session.status not in ("created", "in_progress"):
        raise AppException(
            status_code=409,
            code="INVALID_STATUS",
            message=f"Cannot end session with status '{session.status}'. "
            "Only created or in_progress sessions can be ended.",
        )

    now = datetime.now(UTC)
    session.status = "completed"
    session.completed_at = now
    if not session.started_at:
        # Session was ended directly from "created" (no messages sent)
        session.started_at = now
        session.duration_seconds = 0
    else:
        started = session.started_at
        # Handle timezone-naive datetimes from SQLite
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        session.duration_seconds = int((now - started).total_seconds())

    await db.flush()
    # Full refresh to reload scalar columns (updated_at, etc.) + relationships
    await db.refresh(session)
    await db.refresh(session, attribute_names=["scenario", "messages"])
    return session


async def get_session_messages(db: AsyncSession, session_id: str) -> list[SessionMessage]:
    """Return all messages for a session ordered by message_index."""
    result = await db.execute(
        select(SessionMessage)
        .where(SessionMessage.session_id == session_id)
        .order_by(SessionMessage.message_index)
    )
    return list(result.scalars().all())


async def detect_key_messages(
    db: AsyncSession, session: CoachingSession, mr_message: str
) -> list[dict]:
    """Detect which key messages the MR delivered in their latest message.

    Uses simple keyword matching for mock adapter. Updates session's
    key_messages_status with detected changes.
    """
    current_status = json.loads(session.key_messages_status)
    key_messages = [item["message"] for item in current_status]

    if not key_messages:
        return current_status

    # Get conversation history for context
    messages = await get_session_messages(db, session.id)
    conversation_history = [{"role": msg.role, "content": msg.content} for msg in messages]

    # Simple keyword matching for mock/fallback detection
    detected = _mock_key_message_detection(key_messages, mr_message, conversation_history)

    # Update status for detected messages
    now_str = datetime.now(UTC).isoformat()
    for item in current_status:
        if not item["delivered"] and item["message"] in detected:
            item["delivered"] = True
            item["detected_at"] = now_str

    session.key_messages_status = json.dumps(current_status)
    await db.flush()
    return current_status


def _mock_key_message_detection(
    key_messages: list[str], mr_message: str, conversation_history: list[dict]
) -> list[str]:
    """Simple keyword-based detection for mock/fallback key message matching.

    Checks if significant keywords from each key message appear in the MR's
    message or recent conversation.
    """
    # Build detection prompt for reference (used when real LLM is available)
    _prompt = build_key_message_detection_prompt(key_messages, mr_message, conversation_history)

    detected = []
    mr_lower = mr_message.lower()

    for key_msg in key_messages:
        # Split into significant words (>3 chars) and check keyword overlap
        words = [w.lower() for w in key_msg.split() if len(w) > 3]
        if not words:
            continue
        # Require at least 40% of significant words to match
        matched = sum(1 for w in words if w in mr_lower)
        threshold = max(1, len(words) * 0.4)
        if matched >= threshold:
            detected.append(key_msg)

    return detected
