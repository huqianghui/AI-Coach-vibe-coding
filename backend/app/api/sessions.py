"""Session lifecycle API: create, message with SSE streaming, end, list."""

import asyncio
import json

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.config import get_settings
from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.report import SessionReport
from app.schemas.session import (
    MessageResponse,
    SendMessageRequest,
    SessionCreate,
    SessionResponse,
    TranscriptMessageRequest,
)
from app.schemas.suggestion import SuggestionResponse
from app.services import session_service
from app.services.agents.base import CoachEventType, CoachRequest
from app.services.agents.registry import registry
from app.services.prompt_builder import build_hcp_system_prompt
from app.services.report_service import generate_report
from app.services.scoring_service import resolve_rubric_dimensions
from app.services.suggestion_service import generate_suggestions, parse_key_messages_status
from app.utils.exceptions import AppException
from app.utils.pagination import PaginatedResponse

settings = get_settings()

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse, status_code=201)
async def create_session(
    request: SessionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a new coaching session for a scenario."""
    # Enforce feature flag server-side: reject non-text modes when voice_live is disabled
    if request.mode != "text" and not settings.feature_voice_live_enabled:
        raise AppException(
            status_code=409,
            code="VOICE_MODE_DISABLED",
            message="Voice and avatar modes are not available. "
            "Voice Live is not enabled by the administrator.",
        )
    session = await session_service.create_session(db, request.scenario_id, user.id, request.mode)
    # Eagerly load relationships needed by SessionResponse (scenario_name, message_count)
    await db.refresh(session, attribute_names=["scenario", "messages"])
    return session


@router.get("", response_model=PaginatedResponse[SessionResponse])
async def list_sessions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List the current user's coaching sessions."""
    sessions, total = await session_service.get_user_sessions(db, user.id, page, page_size)
    return PaginatedResponse.create(sessions, total, page, page_size)


# Static route BEFORE parameterized /{session_id} per Gotcha #3
@router.get("/active", response_model=SessionResponse | None)
async def get_active_session(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get the user's currently active (in_progress) session."""
    session = await session_service.get_active_session(db, user.id)
    if session is None:
        raise AppException(
            status_code=404,
            code="NO_ACTIVE_SESSION",
            message="No active session found",
        )
    return session


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get a specific coaching session with details."""
    session = await session_service.get_session(db, session_id, user.id)
    return session


@router.post("/{session_id}/message")
async def send_message(
    session_id: str,
    request: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Send MR message and stream HCP response via SSE."""
    session = await session_service.get_session(db, session_id, user.id)
    # Reject if session is not active (COACH-09 immutability)
    if session.status not in ("created", "in_progress"):
        raise AppException(
            status_code=409,
            code="SESSION_CLOSED",
            message="Session is no longer active",
        )

    # Save MR message (transitions created -> in_progress)
    await session_service.save_message(db, session_id, "user", request.message)

    async def event_generator():
        # Get LLM adapter
        adapter = registry.get("llm", settings.default_llm_provider)
        if adapter is None:
            yield {
                "event": "error",
                "data": "No LLM adapter available",
            }
            return

        # Build HCP system prompt
        key_messages = json.loads(session.scenario.key_messages)

        hcp_prompt = await build_hcp_system_prompt(
            session.scenario.hcp_profile,
            session.scenario,
            key_messages,
            db=db,
        )

        # Fetch conversation history for multi-turn dialogue
        history_messages = await session_service.get_session_messages(db, session_id)
        conversation_history = [{"role": m.role, "content": m.content} for m in history_messages]

        # Phase 24: Update SOP progress and get focus instruction for this run (D-01, D-05, D-06)
        msg_dicts_for_sop = [{"role": m.role, "content": m.content} for m in history_messages]
        focus_instruction = await session_service.update_sop_progress(
            db, session, msg_dicts_for_sop
        )

        # Phase 24: Prepend focus_instruction to scenario context for text-mode SSE (D-01)
        scenario_context = hcp_prompt
        if focus_instruction:
            scenario_context = focus_instruction + "\n\n" + scenario_context
        # Note: For agent-mode sessions (Azure Foundry SDK), focus_instruction should be
        # passed as the `additional_instructions` parameter on the agent run.

        # Build coach request
        hcp_dict = None
        if session.scenario.hcp_profile:
            hcp_dict = session.scenario.hcp_profile.to_prompt_dict()

        # Build scoring weights from rubric dimensions (D-05)
        rubric_dims = await resolve_rubric_dimensions(db, session.scenario)
        scoring_weights = {d["name"]: d["weight"] for d in rubric_dims}

        coach_request = CoachRequest(
            session_id=session_id,
            message=request.message,
            scenario_context=scenario_context,
            hcp_profile=hcp_dict,
            scoring_criteria=scoring_weights,
            conversation_history=conversation_history,
        )

        full_response = ""
        async for event in adapter.execute(coach_request):
            if event.type == CoachEventType.TEXT:
                full_response += event.content
                yield {
                    "event": "text",
                    "data": event.content,
                }
            elif event.type == CoachEventType.SUGGESTION:
                yield {
                    "event": "hint",
                    "data": json.dumps(
                        {
                            "content": event.content,
                            "metadata": event.metadata,
                        }
                    ),
                }
            elif event.type == CoachEventType.DONE:
                # Save complete HCP response
                await session_service.save_message(db, session_id, "assistant", full_response)
                # Key message detection (D-03)
                km_status = await session_service.detect_key_messages(db, session, request.message)
                yield {
                    "event": "key_messages",
                    "data": json.dumps(km_status),
                }
                # Generate real-time coaching suggestions (COACH-08)
                km_status_list = parse_key_messages_status(session.key_messages_status)
                messages_for_hints = await session_service.get_session_messages(db, session_id)
                msg_dicts = [{"role": m.role, "content": m.content} for m in messages_for_hints]
                suggestions = await generate_suggestions(
                    messages=msg_dicts,
                    key_messages_status=km_status_list,
                    scoring_weights=scoring_weights,
                )
                for suggestion in suggestions:
                    yield {
                        "event": "hint",
                        "data": json.dumps(
                            {
                                "content": suggestion.message,
                                "metadata": {
                                    "type": suggestion.type.value,
                                    "trigger": suggestion.trigger,
                                    "relevance": suggestion.relevance_score,
                                },
                            }
                        ),
                    }
                yield {"event": "done", "data": ""}

    return EventSourceResponse(event_generator())


@router.post("/{session_id}/end", response_model=SessionResponse)
async def end_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """End a coaching session (manual end)."""
    session = await session_service.end_session(db, session_id, user.id)
    return session


@router.post("/{session_id}/transcript", response_model=MessageResponse, status_code=201)
async def persist_transcript(
    session_id: str,
    request: TranscriptMessageRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Persist a voice transcript message without triggering LLM response.

    Used by voice sessions to save transcribed speech to the database.
    Handles session status transition (created -> in_progress) on first user message.
    """
    session = await session_service.get_session(db, session_id, user.id)
    if session.status not in ("created", "in_progress"):
        raise AppException(
            status_code=409,
            code="SESSION_CLOSED",
            message="Session is no longer active",
        )
    message = await session_service.save_message(db, session_id, request.role, request.message)
    return message


@router.get(
    "/{session_id}/messages",
    response_model=list[MessageResponse],
)
async def get_session_messages(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get all messages for a coaching session."""
    # Verify access
    await session_service.get_session(db, session_id, user.id)
    messages = await session_service.get_session_messages(db, session_id)
    return messages


@router.get("/{session_id}/report", response_model=SessionReport)
async def get_session_report(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get a detailed post-session report for a scored session."""
    # Verify session belongs to user
    await session_service.get_session(db, session_id, user.id)
    report = await generate_report(db, session_id)
    return report


@router.get("/{session_id}/suggestions", response_model=list[SuggestionResponse])
async def get_session_suggestions(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get coaching suggestions for a session (regenerated on demand)."""
    session = await session_service.get_session(db, session_id, user.id)
    messages = await session_service.get_session_messages(db, session_id)
    msg_dicts = [{"role": m.role, "content": m.content} for m in messages]
    km_status_list = parse_key_messages_status(session.key_messages_status)
    # Build scoring weights from rubric dimensions (D-05)
    rubric_dims = await resolve_rubric_dimensions(db, session.scenario)
    scoring_weights = {d["name"]: d["weight"] for d in rubric_dims}
    suggestions = await generate_suggestions(
        messages=msg_dicts,
        key_messages_status=km_status_list,
        scoring_weights=scoring_weights,
    )
    return suggestions


@router.post("/{session_id}/audio", status_code=201)
async def upload_session_audio_endpoint(
    session_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Upload recorded audio for a session. Triggers async voice scoring."""
    from app.services.audio_storage_service import upload_session_audio
    from app.services.voice_scoring_service import trigger_voice_scoring

    # Validate session ownership
    session = await session_service.get_session(db, session_id, user.id)
    if session.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your session")

    # Validate file size (50MB max)
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio file too large (max 50MB)")

    # Upload to storage
    audio_url = await upload_session_audio(session_id, content, file.filename or "recording.webm")
    session.audio_url = audio_url
    session.voice_score_status = "pending"
    await db.commit()

    # Trigger async voice scoring after commit so background task can see the data
    asyncio.create_task(trigger_voice_scoring(session_id))

    return {"audio_url": audio_url, "voice_score_status": "pending"}


@router.get("/{session_id}/audio")
async def download_session_audio_endpoint(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Stream the recorded session audio through the backend after ownership check."""
    from app.services.storage import get_storage

    session = await session_service.get_session(db, session_id, user.id)
    if session.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your session")
    if not session.audio_url:
        raise HTTPException(status_code=404, detail="No session audio available")

    audio_content = await get_storage().read(session.audio_url)
    media_type = "audio/wav" if session.audio_url.lower().endswith(".wav") else "audio/webm"
    return Response(
        content=audio_content,
        media_type=media_type,
        headers={"Content-Disposition": 'inline; filename="session-recording.webm"'},
    )


@router.get("/{session_id}/voice-score")
async def get_voice_score_status(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Poll voice scoring status for a session."""
    session = await session_service.get_session(db, session_id, user.id)
    if session.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your session")

    return {
        "session_id": session_id,
        "voice_score_status": session.voice_score_status,
        "audio_url": session.audio_url,
    }


@router.post("/{session_id}/voice-score/retry", status_code=202)
async def retry_voice_scoring(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Retry voice scoring for a session stuck in pending/failed status."""
    from app.services.voice_scoring_service import trigger_voice_scoring

    session = await session_service.get_session(db, session_id, user.id)
    if session.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your session")

    if session.voice_score_status not in ("pending", "failed"):
        raise HTTPException(
            status_code=400, detail=f"Cannot retry: status is '{session.voice_score_status}'"
        )

    if not session.audio_url:
        raise HTTPException(status_code=400, detail="No audio file to score")

    session.voice_score_status = "pending"
    await db.commit()

    asyncio.create_task(trigger_voice_scoring(session_id))

    return {"session_id": session_id, "voice_score_status": "pending"}
