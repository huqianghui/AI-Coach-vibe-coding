"""Session lifecycle API: create, message with SSE streaming, end, list."""

import asyncio
import hashlib
import json
import secrets
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from app.config import get_settings
from app.dependencies import get_current_user, get_db
from app.models.scenario import Scenario
from app.models.session import CoachingSession
from app.models.session_turn import SessionTurn
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
from app.services.agent_chat_service import AgentChatError, stream_agent_response
from app.services.foundry_conversation_service import FoundryConversationService
from app.services.report_service import generate_report
from app.services.scoring_service import resolve_rubric_dimensions
from app.services.session_turn_orchestrator import SessionTurnOrchestrator, TurnResult
from app.services.suggestion_service import generate_suggestions, parse_key_messages_status
from app.utils.exceptions import AppException
from app.utils.pagination import PaginatedResponse

settings = get_settings()

router = APIRouter(prefix="/sessions", tags=["sessions"])

_UNFINISHED_TURN_STATES = (
    "pending",
    "leased",
    "provider_pending",
    "provider_unknown",
    "reconciling",
)


async def _session_turn_orchestrator(db: AsyncSession) -> SessionTurnOrchestrator:
    """Build the exact configured provider adapter for a server-owned turn."""
    from app.services import agent_sync_service

    endpoint, api_key = await agent_sync_service.get_project_endpoint(db)
    project_client = agent_sync_service._get_project_client(endpoint, api_key)
    openai_client = project_client.get_openai_client()
    return SessionTurnOrchestrator(
        FoundryConversationService(openai_client),
        openai_client,
    )


async def _resolve_server_turn_key(
    db: AsyncSession, session_id: str, message: str
) -> tuple[str, bool]:
    """Resume only an unfinished same-input turn; otherwise allocate server authority."""
    digest = hashlib.sha256(message.encode("utf-8")).hexdigest()
    existing = await db.scalar(
        select(SessionTurn.turn_key)
        .where(
            SessionTurn.session_id == session_id,
            SessionTurn.input_digest == digest,
            SessionTurn.status.in_(_UNFINISHED_TURN_STATES),
        )
        .order_by(SessionTurn.created_at.desc())
        .limit(1)
    )
    return (existing, True) if existing else (str(uuid.uuid4()), False)


def _turn_state_event(result: TurnResult) -> dict[str, str] | None:
    codes = {
        "in_progress": "SESSION_TURN_IN_PROGRESS",
        "reconciling": "SESSION_TURN_RECONCILING",
        "failed_terminal": "SESSION_TURN_FAILED",
    }
    code = codes.get(result.status)
    if code is None:
        return None
    return {
        "event": "state",
        "data": json.dumps({"code": code, "status": result.status}),
    }


async def _successful_turn_observables(
    db: AsyncSession, session_id: str, user_message: str
) -> tuple[str, list[SuggestionResponse]]:
    """Compute compatibility observables after the orchestrator commits its winner."""
    db.expire_all()
    session = await db.scalar(
        select(CoachingSession)
        .options(selectinload(CoachingSession.scenario).selectinload(Scenario.hcp_profile))
        .where(CoachingSession.id == session_id)
    )
    if session is None:
        raise AppException(404, "SESSION_NOT_FOUND", "Session not found")

    key_messages_status = await session_service.detect_key_messages(db, session, user_message)
    rubric_dims = await resolve_rubric_dimensions(db, session.scenario)
    scoring_weights = {dimension["name"]: dimension["weight"] for dimension in rubric_dims}
    messages = await session_service.get_session_messages(db, session_id)
    suggestions = await generate_suggestions(
        messages=[{"role": message.role, "content": message.content} for message in messages],
        key_messages_status=key_messages_status,
        scoring_weights=scoring_weights,
    )
    return json.dumps(key_messages_status), suggestions


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

    if session.skill_id and session.skill_version_id:
        turn_key, resumed = await _resolve_server_turn_key(db, session_id, request.message)
        orchestrator = await _session_turn_orchestrator(db)
        await db.rollback()

        async def durable_event_generator():
            yield {
                "event": "state",
                "data": json.dumps(
                    {
                        "code": "SESSION_TURN_RESUMED" if resumed else "SESSION_TURN_ACCEPTED",
                        "status": "in_progress",
                    }
                ),
            }
            try:
                result = await orchestrator.run_turn(
                    session_id,
                    turn_key,
                    request.message,
                    f"api-{secrets.token_hex(8)}",
                )
            except AppException as exc:
                yield {
                    "event": "error",
                    "data": json.dumps(
                        {"code": exc.code, "message": exc.message, "details": exc.details}
                    ),
                }
                return
            state_event = _turn_state_event(result)
            if state_event is not None:
                yield state_event
                return
            try:
                key_messages_status, suggestions = await _successful_turn_observables(
                    db, session_id, request.message
                )
            except AppException as exc:
                yield {
                    "event": "error",
                    "data": json.dumps(
                        {"code": exc.code, "message": exc.message, "details": exc.details}
                    ),
                }
                return
            yield {"event": "text", "data": result.text}
            yield {"event": "key_messages", "data": key_messages_status}
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

        return EventSourceResponse(durable_event_generator())

    pinned_agent = await session_service.resolve_pinned_agent(session)

    # Suggestions still use the rubric after the Agent response; the rubric is never
    # supplied to Foundry as prompt or temporary instructions.
    rubric_dims = await resolve_rubric_dimensions(db, session.scenario)
    scoring_weights = {d["name"]: d["weight"] for d in rubric_dims}

    # Save MR message (transitions created -> in_progress)
    await session_service.save_message(db, session_id, "user", request.message)

    async def event_generator():
        full_response = ""
        response_id = None
        try:
            async for event in stream_agent_response(
                db,
                pinned_agent.name,
                pinned_agent.version,
                request.message,
                session.agent_response_id,
            ):
                if event.kind == "text":
                    full_response += event.text
                    yield {"event": "text", "data": event.text}
                elif event.kind == "completed":
                    response_id = event.response_id
        except AgentChatError as exc:
            yield {
                "event": "error",
                "data": json.dumps({"code": "AGENT_RESPONSE_FAILED", "message": str(exc)}),
            }
            return

        if not response_id:
            yield {
                "event": "error",
                "data": json.dumps(
                    {
                        "code": "AGENT_RESPONSE_INCOMPLETE",
                        "message": "Agent response ended without completion",
                    }
                ),
            }
            return

        # Persist successful conversation state atomically after terminal completion.
        await session_service.save_message(db, session_id, "assistant", full_response)
        session.agent_response_id = response_id
        await db.flush()

        km_status = await session_service.detect_key_messages(db, session, request.message)
        yield {"event": "key_messages", "data": json.dumps(km_status)}

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
