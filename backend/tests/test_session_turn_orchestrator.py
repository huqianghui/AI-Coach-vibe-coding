"""Focused durable Session turn orchestrator tests."""

import asyncio
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.message import SessionMessage
from app.models.session import CoachingSession
from app.models.session_turn import SessionTurn
from app.models.session_turn_attempt import SessionTurnAttempt
from app.models.session_turn_attempt_event import SessionTurnAttemptEvent
from app.models.session_turn_context_audit import SessionTurnContextAudit
from app.services.agent_chat_service import AgentChatError, SessionAgentResponse
from app.services.session_turn_orchestrator import SessionTurnOrchestrator, TurnResult
from app.services.session_turn_progression import SessionProgressionDecision
from tests.conftest import test_engine


def _sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


@pytest.fixture
def session_factory():
    return async_sessionmaker(test_engine, expire_on_commit=False)


async def _session(db_session):
    payload = {
        "knowledge_references": [],
        "schema_version": "1",
        "skill_id": "skill",
        "skill_version_id": "version",
        "sop_steps": ["Ask only about CURRENT STEP"],
        "source_sha256": _sha("source"),
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    session = CoachingSession(
        user_id="user",
        scenario_id="scenario",
        agent_name="Dr-Pinned",
        agent_version="5",
        skill_id="skill",
        skill_version_id="version",
        focus_instruction="STALE: discuss a different step",
        sop_snapshot_json=raw,
        sop_snapshot_sha256=_sha(raw),
        sop_current_step=0,
        context_revision=0,
        foundry_conversation_state="active",
        foundry_conversation_id="conv-1",
    )
    db_session.add(session)
    await db_session.commit()
    return session


def _orchestrator(session_factory, response=None):
    conversations = AsyncMock()
    conversations.ensure_conversation.return_value = "conv-1"
    client = MagicMock()
    client.conversations.items.create.return_value = SimpleNamespace(id="item")
    orchestrator = SessionTurnOrchestrator(
        conversations,
        client,
        session_factory=session_factory,
    )
    response = response or SessionAgentResponse(
        "follow current step", "resp-1", ({"call_id": "iq-1", "name": "knowledge_base_retrieve"},)
    )
    return orchestrator, client, conversations, response


async def test_success_freezes_context_orders_items_and_commits_one_winner(
    db_session, session_factory
):
    session = await _session(db_session)
    orchestrator, client, conversations, response = _orchestrator(session_factory)
    progression = SessionProgressionDecision("completed", 0, 1, "detected")
    with patch(
        "app.services.session_turn_orchestrator.respond_in_session_conversation",
        new=AsyncMock(return_value=response),
    ) as provider:
        result = await orchestrator.run_turn(
            session.id, "turn-1", "hello", "worker-a", progression=progression
        )

    assert result == TurnResult("succeeded", "turn-1", "follow current step", "resp-1")
    conversations.ensure_conversation.assert_awaited_once_with(session.id)
    items = client.conversations.items.create.call_args.kwargs["items"]
    assert [item["role"] for item in items] == ["developer", "user"]
    directive = items[0]["content"]
    assert directive.index("STALE") < directive.index("FINAL HIGHEST-PRECEDENCE")
    assert directive.endswith("=== END FINAL HIGHEST-PRECEDENCE CURRENT-STEP DIRECTIVE ===")
    kwargs = provider.await_args.kwargs
    assert kwargs["agent_name"] == "Dr-Pinned"
    assert kwargs["agent_version"] == "5"
    assert kwargs["conversation_id"] == "conv-1"

    async with session_factory() as db:
        turn = await db.scalar(select(SessionTurn).where(SessionTurn.turn_key == "turn-1"))
        attempts = await db.scalar(select(func.count(SessionTurnAttempt.id)))
        events = list((await db.scalars(select(SessionTurnAttemptEvent))).all())
        messages = list(
            (await db.scalars(select(SessionMessage).order_by(SessionMessage.message_index))).all()
        )
        audit = await db.scalar(select(SessionTurnContextAudit))
        persisted = await db.get(CoachingSession, session.id)
        assert turn.status == "succeeded" and turn.winning_attempt_id
        assert attempts == 1
        assert [event.event_kind for event in events] == [
            "dispatched",
            "known_success",
            "winner_selected",
        ]
        assert [(message.role, message.content) for message in messages] == [
            ("user", "hello"),
            ("assistant", "follow current step"),
        ]
        assert json.loads(audit.iq_correlation_json) == [
            {"call_id": "iq-1", "name": "knowledge_base_retrieve"}
        ]
        assert persisted.sop_current_step == 1
        assert persisted.context_revision == 1


async def test_duplicate_call_replays_committed_winner_without_provider(
    db_session, session_factory
):
    session = await _session(db_session)
    orchestrator, _client, conversations, response = _orchestrator(session_factory)
    provider = AsyncMock(return_value=response)
    with patch(
        "app.services.session_turn_orchestrator.respond_in_session_conversation", new=provider
    ):
        first = await orchestrator.run_turn(session.id, "same", "hello", "worker-a")
        second = await orchestrator.run_turn(session.id, "same", "hello", "worker-b")
    assert first == second
    assert provider.await_count == 1
    assert conversations.ensure_conversation.await_count == 1


async def test_live_worker_conflict_returns_in_progress(db_session, session_factory):
    session = await _session(db_session)
    orchestrator, _client, _conversations, _response = _orchestrator(session_factory)
    claimed = await orchestrator.claim(session.id, "conflict", "hello", "worker-a")
    assert not isinstance(claimed, TurnResult)
    conflict = await orchestrator.claim(session.id, "conflict", "hello", "worker-b")
    assert conflict == TurnResult("in_progress", "conflict")


async def test_unknown_provider_outcome_is_append_only_and_never_blindly_retried(
    db_session, session_factory
):
    session = await _session(db_session)
    orchestrator, _client, conversations, _response = _orchestrator(session_factory)
    provider = AsyncMock(side_effect=AgentChatError("unknown after dispatch"))
    with patch(
        "app.services.session_turn_orchestrator.respond_in_session_conversation", new=provider
    ):
        first = await orchestrator.run_turn(session.id, "unknown", "hello", "worker-a")
        second = await orchestrator.run_turn(session.id, "unknown", "hello", "worker-b")
    assert first == TurnResult("reconciling", "unknown")
    assert second == TurnResult("reconciling", "unknown")
    assert provider.await_count == 1
    assert conversations.ensure_conversation.await_count == 1
    async with session_factory() as db:
        turn = await db.scalar(select(SessionTurn).where(SessionTurn.turn_key == "unknown"))
        events = list((await db.scalars(select(SessionTurnAttemptEvent))).all())
        assert turn.status == "provider_unknown"
        assert [event.event_kind for event in events] == ["dispatched", "timeout", "unknown"]
        assert await db.scalar(select(func.count(SessionMessage.id))) == 0
        assert await db.scalar(select(func.count(SessionTurnContextAudit.id))) == 0


async def test_cancellation_after_dispatch_is_quarantined_and_propagated(
    db_session, session_factory
):
    session = await _session(db_session)
    orchestrator, _client, conversations, _response = _orchestrator(session_factory)
    provider = AsyncMock(side_effect=asyncio.CancelledError)
    with (
        patch(
            "app.services.session_turn_orchestrator.respond_in_session_conversation",
            new=provider,
        ),
        pytest.raises(asyncio.CancelledError),
    ):
        await orchestrator.run_turn(session.id, "cancelled", "hello", "worker-a")

    replay = await orchestrator.run_turn(session.id, "cancelled", "hello", "worker-b")
    assert replay == TurnResult("reconciling", "cancelled")
    assert provider.await_count == 1
    assert conversations.ensure_conversation.await_count == 1
    async with session_factory() as db:
        turn = await db.scalar(select(SessionTurn).where(SessionTurn.turn_key == "cancelled"))
        events = list((await db.scalars(select(SessionTurnAttemptEvent))).all())
        assert turn.status == "provider_unknown"
        assert turn.lease_owner is None
        assert [event.event_kind for event in events] == ["dispatched", "timeout", "unknown"]


async def test_cancellation_before_dispatch_is_terminal_without_provider_call(
    db_session, session_factory
):
    session = await _session(db_session)
    orchestrator, _client, _conversations, _response = _orchestrator(session_factory)
    orchestrator._append_event = AsyncMock(side_effect=[asyncio.CancelledError, None])

    with pytest.raises(asyncio.CancelledError):
        await orchestrator.run_turn(session.id, "pre-dispatch-cancel", "hello", "worker")

    async with session_factory() as db:
        turn = await db.scalar(
            select(SessionTurn).where(SessionTurn.turn_key == "pre-dispatch-cancel")
        )
        assert turn.status == "failed_terminal"


async def test_provider_conversation_not_found_marks_mapping_missing(db_session, session_factory):
    session = await _session(db_session)
    orchestrator, client, conversations, _response = _orchestrator(session_factory)
    missing = RuntimeError("conversation not found")
    missing.status_code = 404
    client.conversations.items.create.side_effect = missing

    result = await orchestrator.run_turn(session.id, "missing", "hello", "worker")

    assert result == TurnResult("failed_terminal", "missing")
    conversations.mark_mapping_missing.assert_awaited_once_with(session.id)


async def test_known_failure_is_terminal_without_assistant_or_audit(db_session, session_factory):
    session = await _session(db_session)
    orchestrator, client, _conversations, _response = _orchestrator(session_factory)
    client.conversations.items.create.side_effect = ValueError("known bad request")
    result = await orchestrator.run_turn(session.id, "failed", "hello", "worker")
    assert result == TurnResult("failed_terminal", "failed")
    async with session_factory() as db:
        turn = await db.scalar(select(SessionTurn).where(SessionTurn.turn_key == "failed"))
        events = list((await db.scalars(select(SessionTurnAttemptEvent))).all())
        assert turn.status == "failed_terminal"
        assert [event.event_kind for event in events] == ["dispatched", "known_failure"]
        assert await db.scalar(select(func.count(SessionMessage.id))) == 0
