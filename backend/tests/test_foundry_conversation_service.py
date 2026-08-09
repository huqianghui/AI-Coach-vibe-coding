"""Focused durable Foundry Conversation lifecycle tests."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.session import CoachingSession
from app.services.foundry_conversation_service import (
    ConversationUnavailable,
    FoundryConversationService,
)
from tests.conftest import test_engine


@pytest.fixture
def session_factory():
    return async_sessionmaker(test_engine, expire_on_commit=False)


async def _row(db_session, state="unprovisioned", conversation_id=None):
    session = CoachingSession(
        user_id="user",
        scenario_id="scenario",
        agent_name="agent",
        agent_version="1",
        foundry_conversation_state=state,
        foundry_conversation_id=conversation_id,
    )
    db_session.add(session)
    await db_session.commit()
    return session


async def test_create_persists_then_reuses_without_second_side_effect(db_session, session_factory):
    session = await _row(db_session)
    client = MagicMock()
    client.conversations.create.return_value = SimpleNamespace(id="conv-1")
    service = FoundryConversationService(client, session_factory=session_factory)

    assert await service.ensure_conversation(session.id) == "conv-1"
    assert await service.ensure_conversation(session.id) == "conv-1"
    client.conversations.create.assert_called_once_with()

    async with session_factory() as db:
        persisted = await db.get(CoachingSession, session.id)
        assert persisted.foundry_conversation_state == "active"
        assert persisted.foundry_conversation_id == "conv-1"
        assert persisted.foundry_conversation_create_retry_count == 1


async def test_unknown_create_is_quarantined_without_blind_replacement(db_session, session_factory):
    session = await _row(db_session)
    client = MagicMock()
    client.conversations.create.side_effect = TimeoutError("secret provider text")
    service = FoundryConversationService(client, session_factory=session_factory)

    with pytest.raises(ConversationUnavailable) as first:
        await service.ensure_conversation(session.id)
    with pytest.raises(ConversationUnavailable) as second:
        await service.ensure_conversation(session.id)
    assert first.value.details == {"state": "create_unknown"}
    assert second.value.details == {"state": "create_unknown"}
    client.conversations.create.assert_called_once()

    async with session_factory() as db:
        persisted = await db.get(CoachingSession, session.id)
        assert persisted.foundry_conversation_state == "create_unknown"
        assert "secret provider text" not in persisted.foundry_conversation_last_error


async def test_reclaimed_create_uses_persisted_idempotency_key(db_session, session_factory):
    now = datetime(2026, 8, 5, 10, 0, 0)
    session = await _row(db_session, "creating")
    session.foundry_conversation_create_idempotency_id = "persisted-key"
    session.foundry_conversation_create_lease_token = "expired-worker"
    session.foundry_conversation_create_lease_expires_at = now - timedelta(seconds=1)
    await db_session.commit()
    client = MagicMock()
    client.conversations.create.return_value = SimpleNamespace(id="conv-reclaimed")
    service = FoundryConversationService(
        client,
        session_factory=session_factory,
        clock=lambda: now,
        idempotency_supported=lambda _call: True,
    )

    assert await service.ensure_conversation(session.id) == "conv-reclaimed"
    client.conversations.create.assert_called_once_with(idempotency_key="persisted-key")


async def test_active_missing_mapping_becomes_cleanup_not_replacement(db_session, session_factory):
    session = await _row(db_session, "active", "conv-missing")
    client = MagicMock()
    service = FoundryConversationService(client, session_factory=session_factory)

    await service.mark_mapping_missing(session.id)
    assert await service.cleanup(session.id) is True
    client.conversations.delete.assert_called_once_with("conv-missing")
    client.conversations.create.assert_not_called()


async def test_cleanup_absent_is_closed_and_transient_retries_with_ceiling(
    db_session, session_factory
):
    now = datetime(2026, 8, 5, 10, 0, 0)
    missing = await _row(db_session, "cleanup_pending", "conv-gone")
    transient = await _row(db_session, "cleanup_pending", "conv-retry")
    client = MagicMock()
    not_found = RuntimeError("not found")
    not_found.status_code = 404
    client.conversations.delete.side_effect = [not_found, RuntimeError("token=secret")]
    service = FoundryConversationService(
        client,
        session_factory=session_factory,
        clock=lambda: now,
        retry_base_seconds=10,
        retry_ceiling_seconds=11,
        jitter=lambda: 1,
    )

    assert await service.cleanup(missing.id) is True
    assert await service.cleanup(transient.id) is False
    async with session_factory() as db:
        closed = await db.get(CoachingSession, missing.id)
        retry = await db.get(CoachingSession, transient.id)
        assert closed.foundry_conversation_state == "closed"
        assert closed.foundry_conversation_id is None
        assert closed.foundry_conversation_create_idempotency_id is None
        assert retry.foundry_conversation_state == "cleanup_pending"
        assert retry.foundry_conversation_cleanup_retry_count == 1
        assert retry.foundry_conversation_next_cleanup_at == now + timedelta(seconds=11)
        assert "secret" not in retry.foundry_conversation_last_error


async def test_live_create_lease_and_cleanup_lease_block_competing_worker(
    db_session, session_factory
):
    now = datetime(2026, 8, 5, 10, 0, 0)
    creating = await _row(db_session, "creating")
    cleanup = await _row(db_session, "cleanup_pending", "conv")
    creating.foundry_conversation_create_lease_expires_at = now + timedelta(seconds=10)
    cleanup.foundry_conversation_delete_lease_expires_at = now + timedelta(seconds=10)
    cleanup.foundry_conversation_delete_lease_token = "other"
    await db_session.commit()
    client = MagicMock()
    service = FoundryConversationService(client, session_factory=session_factory, clock=lambda: now)

    with pytest.raises(ConversationUnavailable) as exc:
        await service.claim_create(creating.id)
    assert exc.value.details == {"state": "creating"}
    assert await service.cleanup(cleanup.id) is False
    client.conversations.delete.assert_not_called()
