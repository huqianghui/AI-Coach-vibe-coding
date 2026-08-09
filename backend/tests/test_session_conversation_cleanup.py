"""Focused startup and periodic Conversation cleanup tests."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.session import CoachingSession
from app.services.session_conversation_cleanup import SessionConversationCleanup
from tests.conftest import test_engine


@pytest.fixture
def session_factory():
    return async_sessionmaker(test_engine, expire_on_commit=False)


async def test_sweep_is_bounded_and_only_selects_due_cleanup(db_session, session_factory):
    now = datetime(2026, 8, 5, 10, 0, 0)
    due = []
    for index in range(3):
        session = CoachingSession(
            user_id=f"u{index}",
            scenario_id=f"s{index}",
            foundry_conversation_state="cleanup_pending",
            foundry_conversation_next_cleanup_at=now,
        )
        db_session.add(session)
        due.append(session)
    db_session.add(
        CoachingSession(
            user_id="active",
            scenario_id="active",
            foundry_conversation_state="active",
        )
    )
    await db_session.commit()
    service = AsyncMock()
    service.cleanup.return_value = True
    worker = SessionConversationCleanup(
        service,
        session_factory=session_factory,
        clock=lambda: now,
        batch_size=2,
    )

    assert await worker.sweep_once() == 2
    assert service.cleanup.await_count == 2
    assert service.mark_cleanup_pending.await_count == 2


async def test_periodic_worker_uses_injected_wait_and_stops_without_sleep(session_factory):
    service = AsyncMock()
    worker = None

    async def wait(_seconds):
        await worker.stop()

    worker = SessionConversationCleanup(service, session_factory=session_factory, wait=wait)
    worker.sweep_once = AsyncMock(return_value=0)
    await worker.run()
    worker.sweep_once.assert_awaited_once()


async def test_cancellation_is_propagated(session_factory):
    entered = asyncio.Event()

    async def wait(_seconds):
        entered.set()
        await asyncio.Future()

    worker = SessionConversationCleanup(AsyncMock(), session_factory=session_factory, wait=wait)
    task = asyncio.create_task(worker.run())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
