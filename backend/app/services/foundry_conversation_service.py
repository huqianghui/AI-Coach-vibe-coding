"""Durable server-owned Foundry Conversation lifecycle for Skill Sessions."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import AsyncSessionLocal
from app.models.session import CoachingSession
from app.utils.datetime import utc_now_naive
from app.utils.exceptions import AppException

logger = logging.getLogger(__name__)

ConversationState = Literal[
    "unprovisioned", "creating", "active", "create_unknown", "cleanup_pending", "closed"
]


@dataclass(frozen=True, slots=True)
class ConversationLease:
    """Result of atomically inspecting or claiming a Conversation mapping."""

    state: ConversationState
    conversation_id: str | None
    lease_token: str | None = None
    idempotency_supported: bool = False
    idempotency_key: str | None = None


class ConversationUnavailable(AppException):
    """A Session Conversation cannot safely accept a new turn."""

    def __init__(self, state: str) -> None:
        super().__init__(
            status_code=409,
            code="SESSION_CONVERSATION_UNAVAILABLE",
            message="Session Conversation is not available for a new turn",
            details={"state": state},
        )


def _sanitized_error(exc: BaseException) -> str:
    """Persist only an exception class and stable digest, never provider payloads."""
    digest = hashlib.sha256(str(exc).encode("utf-8")).hexdigest()[:16]
    return f"{type(exc).__name__}:{digest}"


def is_conversation_not_found(exc: BaseException) -> bool:
    """Return whether a provider error proves the persisted mapping is absent."""
    status = getattr(exc, "status_code", None)
    return status == 404 or "not found" in str(exc).casefold()


class FoundryConversationService:
    """Own create/reuse/delete state using short DB transactions and bounded SDK calls."""

    def __init__(
        self,
        openai_client: object,
        *,
        session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
        clock: Callable[[], datetime] = utc_now_naive,
        call_timeout: float = 20.0,
        lease_seconds: float = 30.0,
        retry_base_seconds: float = 30.0,
        retry_ceiling_seconds: float = 3600.0,
        jitter: Callable[[], float] = lambda: secrets.randbelow(1000) / 1000,
        idempotency_supported: Callable[[object], bool] | None = None,
    ) -> None:
        self._client = openai_client
        self._sessions = session_factory
        self._clock = clock
        self._call_timeout = call_timeout
        self._lease_seconds = lease_seconds
        self._retry_base_seconds = retry_base_seconds
        self._retry_ceiling_seconds = retry_ceiling_seconds
        self._jitter = jitter
        self._idempotency_supported = idempotency_supported

    async def _session(self, db: AsyncSession, session_id: str) -> CoachingSession:
        row = await db.scalar(
            select(CoachingSession).where(CoachingSession.id == session_id).with_for_update()
        )
        if row is None:
            raise AppException(404, "SESSION_NOT_FOUND", "Session not found")
        return row

    def _create_supports_idempotency(self) -> bool:
        """Use metadata only when the installed SDK explicitly advertises a parameter."""
        if self._idempotency_supported is not None:
            return self._idempotency_supported(self._client.conversations.create)
        try:
            signature = inspect.signature(self._client.conversations.create)
        except (TypeError, ValueError, AttributeError):
            return False
        return "idempotency_key" in signature.parameters

    async def claim_create(self, session_id: str) -> ConversationLease:
        """Reuse active state or claim an expired/unprovisioned create lease."""
        now = self._clock()
        async with self._sessions() as db, db.begin():
            session = await self._session(db, session_id)
            state = session.foundry_conversation_state
            if state == "active" and session.foundry_conversation_id:
                return ConversationLease("active", session.foundry_conversation_id)
            if state in {"create_unknown", "cleanup_pending", "closed"}:
                raise ConversationUnavailable(state)
            if (
                state == "creating"
                and session.foundry_conversation_create_lease_expires_at
                and session.foundry_conversation_create_lease_expires_at > now
            ):
                raise ConversationUnavailable("creating")
            token = secrets.token_hex(16)
            supports = self._create_supports_idempotency()
            session.foundry_conversation_state = "creating"
            session.foundry_conversation_create_lease_token = token
            session.foundry_conversation_create_lease_expires_at = now + timedelta(
                seconds=self._lease_seconds
            )
            session.foundry_conversation_create_retry_count += 1
            session.foundry_conversation_create_idempotency_id = (
                session.foundry_conversation_create_idempotency_id or token if supports else None
            )
            return ConversationLease(
                "creating",
                None,
                token,
                supports,
                session.foundry_conversation_create_idempotency_id,
            )

    async def ensure_conversation(self, session_id: str) -> str:
        """Return the one mapping, creating it once and quarantining unknown outcomes."""
        lease = await self.claim_create(session_id)
        if lease.state == "active":
            assert lease.conversation_id
            return lease.conversation_id
        kwargs: dict[str, Any] = {}
        if lease.idempotency_supported:
            kwargs["idempotency_key"] = lease.idempotency_key
        try:
            conversation = await asyncio.wait_for(
                asyncio.to_thread(self._client.conversations.create, **kwargs),
                timeout=self._call_timeout,
            )
            conversation_id = str(getattr(conversation, "id", "") or "")
            if not conversation_id:
                raise RuntimeError("Conversation create returned no ID")
        except asyncio.CancelledError:
            await self._record_create_unknown(
                session_id, lease.lease_token or "", RuntimeError("create cancelled")
            )
            raise
        except BaseException as exc:
            await self._record_create_unknown(session_id, lease.lease_token or "", exc)
            raise ConversationUnavailable("create_unknown") from exc
        async with self._sessions() as db, db.begin():
            session = await self._session(db, session_id)
            if (
                session.foundry_conversation_state != "creating"
                or session.foundry_conversation_create_lease_token != lease.lease_token
            ):
                # A durable mapping must never be overwritten by a stale creator.
                raise ConversationUnavailable(session.foundry_conversation_state)
            session.foundry_conversation_id = conversation_id
            session.foundry_conversation_state = "active"
            session.foundry_conversation_created_at = self._clock()
            session.foundry_conversation_create_lease_token = None
            session.foundry_conversation_create_lease_expires_at = None
            session.foundry_conversation_last_error = None
        return conversation_id

    async def _record_create_unknown(self, session_id: str, token: str, exc: BaseException) -> None:
        async with self._sessions() as db, db.begin():
            session = await self._session(db, session_id)
            if session.foundry_conversation_create_lease_token != token:
                return
            session.foundry_conversation_state = "create_unknown"
            session.foundry_conversation_last_error = _sanitized_error(exc)
            session.foundry_conversation_create_lease_token = None
            session.foundry_conversation_create_lease_expires_at = None

    async def mark_cleanup_pending(self, session_id: str) -> None:
        """Atomically block new turns before any provider deletion attempt."""
        async with self._sessions() as db, db.begin():
            session = await self._session(db, session_id)
            if session.foundry_conversation_state == "closed":
                return
            session.foundry_conversation_state = "cleanup_pending"
            session.foundry_conversation_cleanup_started_at = (
                session.foundry_conversation_cleanup_started_at or self._clock()
            )
            session.foundry_conversation_next_cleanup_at = self._clock()

    async def cleanup(self, session_id: str) -> bool:
        """Lease and execute one deletion; absent is success, unknown schedules retry."""
        now = self._clock()
        token = secrets.token_hex(16)
        async with self._sessions() as db, db.begin():
            session = await self._session(db, session_id)
            if session.foundry_conversation_state == "closed":
                return True
            if session.foundry_conversation_state != "cleanup_pending":
                return False
            if (
                session.foundry_conversation_next_cleanup_at
                and session.foundry_conversation_next_cleanup_at > now
            ):
                return False
            if (
                session.foundry_conversation_delete_lease_expires_at
                and session.foundry_conversation_delete_lease_expires_at > now
            ):
                return False
            conversation_id = session.foundry_conversation_id
            session.foundry_conversation_delete_lease_token = token
            session.foundry_conversation_delete_lease_expires_at = now + timedelta(
                seconds=self._lease_seconds
            )
        try:
            if conversation_id:
                await asyncio.wait_for(
                    asyncio.to_thread(self._client.conversations.delete, conversation_id),
                    timeout=self._call_timeout,
                )
        except asyncio.CancelledError:
            await self._schedule_cleanup_retry(session_id, token, RuntimeError("cleanup cancelled"))
            raise
        except BaseException as exc:
            if not is_conversation_not_found(exc):
                await self._schedule_cleanup_retry(session_id, token, exc)
                return False
        async with self._sessions() as db, db.begin():
            session = await self._session(db, session_id)
            if session.foundry_conversation_delete_lease_token != token:
                return False
            session.foundry_conversation_state = "closed"
            session.foundry_conversation_id = None
            session.foundry_conversation_closed_at = self._clock()
            session.foundry_conversation_next_cleanup_at = None
            session.foundry_conversation_create_operation_id = None
            session.foundry_conversation_create_idempotency_id = None
            session.foundry_conversation_create_lease_token = None
            session.foundry_conversation_create_lease_expires_at = None
            session.foundry_conversation_delete_lease_token = None
            session.foundry_conversation_delete_lease_expires_at = None
            session.foundry_conversation_last_error = None
        return True

    async def _schedule_cleanup_retry(
        self, session_id: str, token: str, exc: BaseException
    ) -> None:
        async with self._sessions() as db, db.begin():
            session = await self._session(db, session_id)
            if session.foundry_conversation_delete_lease_token != token:
                return
            session.foundry_conversation_cleanup_retry_count += 1
            delay = min(
                self._retry_ceiling_seconds,
                self._retry_base_seconds
                * (2 ** max(0, session.foundry_conversation_cleanup_retry_count - 1)),
            )
            delay = min(self._retry_ceiling_seconds, delay * (1 + self._jitter() * 0.25))
            session.foundry_conversation_next_cleanup_at = self._clock() + timedelta(seconds=delay)
            session.foundry_conversation_last_error = _sanitized_error(exc)
            session.foundry_conversation_delete_lease_token = None
            session.foundry_conversation_delete_lease_expires_at = None

    async def mark_mapping_missing(self, session_id: str) -> None:
        """Treat provider 404 for a persisted mapping as terminal cleanup evidence."""
        await self.mark_cleanup_pending(session_id)
