"""Bounded startup and periodic cleanup for server-owned Conversations."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import AsyncSessionLocal
from app.models.session import CoachingSession
from app.services.foundry_conversation_service import FoundryConversationService
from app.utils.datetime import utc_now_naive

logger = logging.getLogger(__name__)


class SessionConversationCleanup:
    """Run bounded sweeps; row-level delete leases make workers conflict-safe."""

    def __init__(
        self,
        service: FoundryConversationService,
        *,
        session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
        clock: Callable[[], datetime] = utc_now_naive,
        wait: Callable[[float], Awaitable[None]] = asyncio.sleep,
        interval_seconds: float = 300.0,
        batch_size: int = 50,
    ) -> None:
        self._service = service
        self._sessions = session_factory
        self._clock = clock
        self._wait = wait
        self._interval = interval_seconds
        self._batch_size = batch_size
        self._stopping = asyncio.Event()

    async def sweep_once(self) -> int:
        """Snapshot due IDs, then let each cleanup use its own short transactions."""
        now = self._clock()
        async with self._sessions() as db:
            result = await db.scalars(
                select(CoachingSession.id)
                .where(
                    or_(
                        CoachingSession.foundry_conversation_state == "cleanup_pending",
                        and_(
                            CoachingSession.status.in_(("completed", "scored")),
                            CoachingSession.foundry_conversation_state.in_(
                                ("active", "create_unknown")
                            ),
                        ),
                    ),
                    or_(
                        CoachingSession.foundry_conversation_next_cleanup_at.is_(None),
                        CoachingSession.foundry_conversation_next_cleanup_at <= now,
                    ),
                )
                .limit(self._batch_size)
            )
            session_ids = list(result)
        completed = 0
        for session_id in session_ids:
            try:
                await self._service.mark_cleanup_pending(session_id)
                completed += int(await self._service.cleanup(session_id))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Conversation cleanup failed for session %s", session_id)
        return completed

    async def run(self, *, initial_sweep: bool = True) -> None:
        """Run one startup sweep and periodic sweeps until cancellation/shutdown."""
        try:
            if not initial_sweep:
                await self._wait(self._interval)
            while not self._stopping.is_set():
                await self.sweep_once()
                if self._stopping.is_set():
                    break
                await self._wait(self._interval)
        except asyncio.CancelledError:
            raise

    async def run_startup(self, timeout: float = 30.0) -> int:
        """Run one bounded startup sweep without ever preventing application startup."""
        try:
            return await asyncio.wait_for(self.sweep_once(), timeout=timeout)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Bounded startup Conversation cleanup failed")
            return 0

    async def stop(self) -> None:
        """Request cooperative shutdown; lifespan also cancels the task as a backstop."""
        self._stopping.set()
