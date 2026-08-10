"""Durable orchestration for exact-Agent Skill Session text turns."""

from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import AsyncSessionLocal
from app.models.message import SessionMessage
from app.models.session import CoachingSession
from app.models.session_turn import SessionTurn
from app.models.session_turn_attempt import SessionTurnAttempt
from app.models.session_turn_attempt_event import SessionTurnAttemptEvent
from app.models.session_turn_context_audit import SessionTurnContextAudit
from app.services.agent_chat_service import (
    AgentChatError,
    SessionAgentResponse,
    respond_in_session_conversation,
)
from app.services.foundry_conversation_service import (
    FoundryConversationService,
    is_conversation_not_found,
)
from app.services.session_service import resolve_pinned_agent
from app.services.session_skill_context import SessionTurnContext, render_turn_context
from app.services.session_turn_progression import (
    SessionProgressionDecision,
    commit_session_progression,
)
from app.utils.datetime import utc_now_naive
from app.utils.exceptions import AppException

TurnOutcome = Literal["in_progress", "reconciling", "succeeded", "failed_terminal"]


@dataclass(frozen=True, slots=True)
class TurnResult:
    """Stable public result for claim/resume callers."""

    status: TurnOutcome
    turn_key: str
    text: str = ""
    response_id: str | None = None


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class SessionTurnOrchestrator:
    """Coordinate short durable boundaries around external Conversation calls."""

    def __init__(
        self,
        conversation_service: FoundryConversationService,
        openai_client: object,
        *,
        session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
        clock=utc_now_naive,
        lease_seconds: float = 60.0,
        response_timeout: float = 60.0,
        max_attempts: int = 2,
    ) -> None:
        self._conversations = conversation_service
        self._client = openai_client
        self._sessions = session_factory
        self._clock = clock
        self._lease_seconds = lease_seconds
        self._response_timeout = response_timeout
        self._max_attempts = max_attempts

    async def claim(
        self, session_id: str, turn_key: str, user_text: str, worker: str
    ) -> tuple[SessionTurn, SessionTurnContext] | TurnResult:
        """Create/reuse one outbox row and acquire its expiring worker lease."""
        now = self._clock()
        async with self._sessions() as db, db.begin():
            session = await db.scalar(
                select(CoachingSession).where(CoachingSession.id == session_id).with_for_update()
            )
            if session is None:
                raise AppException(404, "SESSION_NOT_FOUND", "Session not found")
            if session.foundry_conversation_state in {
                "create_unknown",
                "cleanup_pending",
                "closed",
            }:
                raise AppException(
                    409,
                    "SESSION_CONVERSATION_UNAVAILABLE",
                    "Session Conversation cannot accept turns",
                    {"state": session.foundry_conversation_state},
                )
            context = render_turn_context(session)
            digest = _sha(user_text)
            turn = await db.scalar(
                select(SessionTurn)
                .where(SessionTurn.session_id == session_id, SessionTurn.turn_key == turn_key)
                .with_for_update()
            )
            if turn is not None:
                if turn.input_digest != digest:
                    raise AppException(409, "TURN_KEY_CONFLICT", "Turn key input does not match")
                if turn.status == "succeeded":
                    return await self._replay(db, turn)
                if turn.status == "failed_terminal":
                    return TurnResult("failed_terminal", turn_key)
                if turn.status in {"provider_pending", "provider_unknown", "reconciling"}:
                    return TurnResult("reconciling", turn_key)
                if turn.lease_expires_at and turn.lease_expires_at > now:
                    return TurnResult("in_progress", turn_key)
                turn.status = "pending"
            else:
                turn = SessionTurn(
                    session_id=session_id,
                    turn_key=turn_key,
                    input_digest=digest,
                    frozen_step=context.applied_step,
                    frozen_context_revision=context.context_revision,
                    frozen_context_digest=context.digest,
                )
                db.add(turn)
                await db.flush()
            turn.transition_to("leased")
            turn.lease_owner = worker
            turn.lease_expires_at = now + timedelta(seconds=self._lease_seconds)
            return turn, context

    async def _replay(self, db: AsyncSession, turn: SessionTurn) -> TurnResult:
        audit = await db.scalar(
            select(SessionTurnContextAudit).where(SessionTurnContextAudit.turn_id == turn.id)
        )
        message = await db.get(SessionMessage, audit.assistant_message_id) if audit else None
        return TurnResult(
            "succeeded",
            turn.turn_key,
            message.content if message else "",
            turn.provider_response_id,
        )

    async def run_turn(
        self,
        session_id: str,
        turn_key: str,
        user_text: str,
        worker: str,
        *,
        progression: SessionProgressionDecision | None = None,
    ) -> TurnResult:
        """Claim, append immutable facts, dispatch, and commit at most one winner."""
        claimed = await self.claim(session_id, turn_key, user_text, worker)
        if isinstance(claimed, TurnResult):
            return claimed
        turn, context = claimed
        conversation_id = await self._conversations.ensure_conversation(session_id)
        attempt = await self._start_attempt(turn.id, worker, context, user_text)
        dispatched = False
        try:
            await self._append_event(attempt.id, "dispatched")
            dispatched = True
            await self._append_items(conversation_id, context.rendered, user_text)
            async with self._sessions() as db:
                session = await db.get(CoachingSession, session_id)
                assert session is not None
                pin = await resolve_pinned_agent(session)
                response = await respond_in_session_conversation(
                    db,
                    agent_name=pin.name,
                    agent_version=pin.version,
                    conversation_id=conversation_id,
                    timeout=self._response_timeout,
                )
        except asyncio.CancelledError:
            cancellation = RuntimeError("dispatch cancelled")
            if dispatched:
                await self._mark_unknown(turn.id, attempt.id, cancellation)
            else:
                await self._mark_known_failure(turn.id, attempt.id, cancellation)
            raise
        except TimeoutError as exc:
            await self._mark_unknown(turn.id, attempt.id, exc)
            return TurnResult("reconciling", turn_key)
        except AgentChatError as exc:
            if is_conversation_not_found(exc):
                await self._conversations.mark_mapping_missing(session_id)
            if "unknown" in str(exc).casefold():
                await self._mark_unknown(turn.id, attempt.id, exc)
                return TurnResult("reconciling", turn_key)
            await self._mark_known_failure(turn.id, attempt.id, exc)
            return TurnResult("failed_terminal", turn_key)
        except Exception as exc:
            if is_conversation_not_found(exc):
                await self._conversations.mark_mapping_missing(session_id)
            await self._mark_known_failure(turn.id, attempt.id, exc)
            return TurnResult("failed_terminal", turn_key)
        return await self._commit_winner(
            session_id, turn.id, attempt.id, user_text, context, response, progression
        )

    async def _append_items(self, conversation_id: str, directive: str, user_text: str) -> None:
        """Append exactly one final developer item immediately before one user item."""
        items = [
            {"type": "message", "role": "developer", "content": directive},
            {"type": "message", "role": "user", "content": user_text},
        ]
        await asyncio.wait_for(
            asyncio.to_thread(
                self._client.conversations.items.create,
                conversation_id,
                items=items,
            ),
            timeout=self._response_timeout,
        )

    async def _start_attempt(
        self, turn_id: str, worker: str, context: SessionTurnContext, user_text: str
    ) -> SessionTurnAttempt:
        async with self._sessions() as db, db.begin():
            turn = await db.get(SessionTurn, turn_id, with_for_update=True)
            assert turn is not None
            if turn.lease_owner != worker or turn.status != "leased":
                raise AppException(409, "TURN_LEASE_LOST", "Turn lease is no longer owned")
            if turn.attempt_count >= self._max_attempts:
                turn.transition_to("failed_terminal")
                raise AppException(409, "TURN_RETRY_EXHAUSTED", "Turn retry budget exhausted")
            turn.attempt_count += 1
            turn.transition_to("provider_pending")
            attempt = SessionTurnAttempt(
                turn_id=turn.id,
                attempt_number=turn.attempt_count,
                request_digest=_sha(context.rendered + "\n" + user_text),
                lease_token=secrets.token_hex(16),
                correlation_id=secrets.token_hex(12),
            )
            db.add(attempt)
            await db.flush()
            return attempt

    async def _append_event(
        self,
        attempt_id: str,
        kind: str,
        *,
        response_id: str | None = None,
        metadata: dict | None = None,
        error: BaseException | None = None,
    ) -> SessionTurnAttemptEvent:
        async with self._sessions() as db, db.begin():
            event = await self._new_event(
                db,
                attempt_id,
                kind,
                response_id=response_id,
                metadata=metadata,
                error=error,
            )
            db.add(event)
            return event

    async def _new_event(
        self,
        db: AsyncSession,
        attempt_id: str,
        kind: str,
        *,
        response_id: str | None = None,
        metadata: dict | None = None,
        error: BaseException | None = None,
    ) -> SessionTurnAttemptEvent:
        attempt = await db.scalar(
            select(SessionTurnAttempt).where(SessionTurnAttempt.id == attempt_id).with_for_update()
        )
        if attempt is None:
            raise AppException(404, "TURN_ATTEMPT_NOT_FOUND", "Turn attempt not found")
        sequence = await db.scalar(
            select(func.max(SessionTurnAttemptEvent.event_sequence)).where(
                SessionTurnAttemptEvent.attempt_id == attempt_id
            )
        )
        return SessionTurnAttemptEvent(
            attempt_id=attempt_id,
            event_sequence=int(sequence or 0) + 1,
            event_kind=kind,
            provider_response_id=response_id,
            sanitized_error_digest=_sha(str(error)) if error else None,
            event_metadata_json=json.dumps(metadata or {}, sort_keys=True),
        )

    async def _mark_unknown(self, turn_id: str, attempt_id: str, exc: BaseException) -> None:
        await self._append_event(attempt_id, "timeout", error=exc)
        await self._append_event(attempt_id, "unknown", error=exc)
        async with self._sessions() as db, db.begin():
            turn = await db.get(SessionTurn, turn_id, with_for_update=True)
            assert turn is not None
            if turn.status == "provider_pending":
                turn.transition_to("provider_unknown")
                turn.last_error = type(exc).__name__
                turn.lease_owner = None
                turn.lease_expires_at = None

    async def _mark_known_failure(self, turn_id: str, attempt_id: str, exc: BaseException) -> None:
        await self._append_event(attempt_id, "known_failure", error=exc)
        async with self._sessions() as db, db.begin():
            turn = await db.get(SessionTurn, turn_id, with_for_update=True)
            assert turn is not None
            if turn.status == "provider_pending":
                turn.transition_to("failed_terminal")
                turn.last_error = type(exc).__name__

    async def _commit_winner(
        self,
        session_id: str,
        turn_id: str,
        attempt_id: str,
        user_text: str,
        context: SessionTurnContext,
        response: SessionAgentResponse,
        progression: SessionProgressionDecision | None,
    ) -> TurnResult:
        try:
            async with self._sessions() as db, db.begin():
                turn = await db.get(SessionTurn, turn_id, with_for_update=True)
                session = await db.get(CoachingSession, session_id, with_for_update=True)
                assert turn is not None and session is not None
                if turn.winning_attempt_id or turn.status == "succeeded":
                    raise IntegrityError("winner exists", {}, None)
                pin = await resolve_pinned_agent(session)
                index = int(
                    await db.scalar(
                        select(func.count(SessionMessage.id)).where(
                            SessionMessage.session_id == session_id
                        )
                    )
                    or 0
                )
                user = SessionMessage(
                    session_id=session_id, role="user", content=user_text, message_index=index
                )
                assistant = SessionMessage(
                    session_id=session_id,
                    role="assistant",
                    content=response.text,
                    message_index=index + 1,
                )
                db.add_all([user, assistant])
                await db.flush()
                decision = progression or SessionProgressionDecision(
                    "unchanged", context.applied_step, context.applied_step, "not_requested"
                )
                turn.winning_attempt_id = attempt_id
                turn.provider_response_id = response.response_id
                turn.transition_to("succeeded")
                turn.lease_owner = None
                turn.lease_expires_at = None
                known_success = await self._new_event(
                    db, attempt_id, "known_success", response_id=response.response_id
                )
                db.add(known_success)
                await db.flush()
                winner_selected = await self._new_event(
                    db, attempt_id, "winner_selected", response_id=response.response_id
                )
                db.add_all([winner_selected])
                await db.flush()
                progressed = await commit_session_progression(
                    db,
                    session,
                    decision,
                    expected_revision=context.context_revision,
                    winner_committed=True,
                )
                db.add(
                    SessionTurnContextAudit(
                        session_id=session_id,
                        turn_id=turn_id,
                        turn_key=turn.turn_key,
                        terminal_status="succeeded",
                        agent_name=pin.name,
                        agent_version=pin.version,
                        skill_id=context.snapshot.skill_id,
                        skill_version_id=context.snapshot.skill_version_id,
                        sop_snapshot_digest=session.sop_snapshot_sha256 or "",
                        focus_digest=_sha(session.focus_instruction or ""),
                        context_digest=context.digest,
                        context_schema_version=context.snapshot.schema_version,
                        applied_step=context.applied_step,
                        applied_context_revision=context.context_revision,
                        user_message_id=user.id,
                        assistant_message_id=assistant.id,
                        conversation_digest=_sha(user_text + "\n" + response.text),
                        winning_attempt_id=attempt_id,
                        provider_response_id=response.response_id,
                        iq_correlation_json=json.dumps(response.iq_correlations, sort_keys=True),
                        progression_result=decision.result if progressed else "unchanged",
                        progression_from_step=decision.from_step,
                        progression_to_step=decision.to_step if progressed else decision.from_step,
                    )
                )
                await db.flush()
            return TurnResult("succeeded", turn.turn_key, response.text, response.response_id)
        except IntegrityError:
            await self._append_event(attempt_id, "late_duplicate", response_id=response.response_id)
            async with self._sessions() as db:
                turn = await db.get(SessionTurn, turn_id)
                assert turn is not None
                return await self._replay(db, turn)
