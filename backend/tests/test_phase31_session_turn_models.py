"""Phase 31 durable Session turn model and public-schema boundary tests."""

import hashlib
import json
import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.models import (
    SessionTurn,
    SessionTurnAttempt,
    SessionTurnAttemptEvent,
    SessionTurnContextAudit,
)
from app.models.hcp_profile import HcpProfile
from app.models.scenario import Scenario
from app.models.session import CoachingSession
from app.models.user import User
from app.schemas.session import SendMessageRequest, SessionResponse
from app.services.auth import get_password_hash


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


async def _session(db_session) -> CoachingSession:
    user = User(
        username=f"phase31-{uuid.uuid4()}",
        email=f"phase31-{uuid.uuid4()}@example.com",
        hashed_password=get_password_hash("password"),
        full_name="Phase 31",
        role="admin",
    )
    db_session.add(user)
    await db_session.flush()
    hcp = HcpProfile(name="Dr. Phase 31", specialty="Oncology", created_by=user.id)
    db_session.add(hcp)
    await db_session.flush()
    scenario = Scenario(
        name="Phase 31",
        tags="[]",
        hcp_profile_id=hcp.id,
        rubric_id="rubric",
        skill_id="skill",
        created_by=user.id,
    )
    db_session.add(scenario)
    await db_session.flush()
    session = CoachingSession(
        user_id=user.id,
        scenario_id=scenario.id,
        agent_name="Dr-Chen-Jun",
        agent_version="5",
        sop_snapshot_json=json.dumps({"schema_version": "1", "steps": ["one"]}),
        sop_snapshot_sha256=_digest("snapshot"),
    )
    db_session.add(session)
    await db_session.flush()
    return session


def _turn(session_id: str, turn_key: str | None = None) -> SessionTurn:
    return SessionTurn(
        session_id=session_id,
        turn_key=turn_key or str(uuid.uuid4()),
        input_digest=_digest("input"),
        frozen_step=0,
        frozen_context_revision=0,
        frozen_context_digest=_digest("context"),
    )


def _attempt(turn_id: str, number: int = 1) -> SessionTurnAttempt:
    return SessionTurnAttempt(
        turn_id=turn_id,
        attempt_number=number,
        request_digest=_digest(f"request-{number}"),
        lease_token=str(uuid.uuid4()),
        correlation_id=str(uuid.uuid4()),
    )


async def test_session_authority_defaults_and_internal_schema_boundary(db_session) -> None:
    session = await _session(db_session)
    assert session.foundry_conversation_state == "unprovisioned"
    assert session.context_revision == 0
    assert session.foundry_conversation_create_retry_count == 0
    assert session.foundry_conversation_cleanup_retry_count == 0

    forbidden = {
        "sop_snapshot_json",
        "sop_snapshot_sha256",
        "context_revision",
        "foundry_conversation_id",
        "foundry_conversation_state",
        "foundry_conversation_create_lease_token",
        "foundry_conversation_delete_lease_token",
    }
    assert forbidden.isdisjoint(SessionResponse.model_fields)
    with pytest.raises(ValidationError):
        SendMessageRequest.model_validate(
            {"message": "hello", "foundry_conversation_id": "client-controlled"}
        )


async def test_turn_transition_matrix_blocks_terminal_reentry(db_session) -> None:
    session = await _session(db_session)
    turn = _turn(session.id)
    db_session.add(turn)
    await db_session.flush()

    turn.transition_to("leased")
    await db_session.flush()
    turn.transition_to("provider_pending")
    await db_session.flush()
    turn.transition_to("succeeded")
    await db_session.flush()
    assert not turn.can_transition_to("pending")
    with pytest.raises(ValueError, match="Illegal SessionTurn transition"):
        turn.transition_to("pending")

    turn.status = "pending"
    with pytest.raises(ValueError, match="succeeded -> pending"):
        await db_session.flush()
    turn.status = "succeeded"


def test_transition_matrix_covers_every_legal_and_illegal_branch() -> None:
    legal = {
        "pending": {"leased", "failed_terminal", "cancelled"},
        "leased": {"pending", "provider_pending", "failed_terminal", "cancelled"},
        "provider_pending": {"provider_unknown", "succeeded", "failed_terminal"},
        "provider_unknown": {"reconciling", "failed_terminal"},
        "reconciling": {"provider_unknown", "succeeded", "failed_terminal"},
        "succeeded": set(),
        "failed_terminal": set(),
        "cancelled": set(),
    }
    for status, targets in legal.items():
        turn = _turn("session")
        turn.status = status
        for target in legal:
            assert turn.can_transition_to(target) is (target in targets)
    unknown = _turn("session")
    unknown.status = "invalid"
    assert not unknown.can_transition_to("pending")


async def test_turn_key_and_attempt_number_are_unique(db_session) -> None:
    session = await _session(db_session)
    key = str(uuid.uuid4())
    first = _turn(session.id, key)
    db_session.add(first)
    await db_session.flush()
    db_session.add(_turn(session.id, key))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()

    session = await _session(db_session)
    turn = _turn(session.id)
    db_session.add(turn)
    await db_session.flush()
    db_session.add_all([_attempt(turn.id), _attempt(turn.id)])
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_attempt_and_events_are_append_only(db_session) -> None:
    session = await _session(db_session)
    turn = _turn(session.id)
    db_session.add(turn)
    await db_session.flush()
    attempt = _attempt(turn.id)
    db_session.add(attempt)
    await db_session.flush()
    event = SessionTurnAttemptEvent(
        attempt_id=attempt.id,
        event_sequence=1,
        event_kind="dispatched",
    )
    db_session.add(event)
    await db_session.flush()
    event_id = event.id
    await db_session.commit()

    attempt.request_digest = _digest("changed")
    with pytest.raises(ValueError, match="Attempt rows are immutable"):
        await db_session.flush()
    await db_session.rollback()

    event = await db_session.get(SessionTurnAttemptEvent, event_id)
    assert event is not None
    event.event_kind = "known_success"
    with pytest.raises(ValueError, match="AttemptEvent rows are immutable"):
        await db_session.flush()


async def test_attempt_delete_and_event_sequence_uniqueness(db_session) -> None:
    session = await _session(db_session)
    turn = _turn(session.id)
    db_session.add(turn)
    await db_session.flush()
    attempt = _attempt(turn.id)
    db_session.add(attempt)
    await db_session.flush()
    db_session.add_all(
        [
            SessionTurnAttemptEvent(attempt_id=attempt.id, event_sequence=1, event_kind="timeout"),
            SessionTurnAttemptEvent(attempt_id=attempt.id, event_sequence=1, event_kind="unknown"),
        ]
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()

    session = await _session(db_session)
    turn = _turn(session.id)
    db_session.add(turn)
    await db_session.flush()
    attempt = _attempt(turn.id)
    db_session.add(attempt)
    await db_session.flush()
    attempt_id = attempt.id
    await db_session.commit()
    attempt = await db_session.get(SessionTurnAttempt, attempt_id)
    assert attempt is not None
    await db_session.delete(attempt)
    with pytest.raises(ValueError, match="Attempt rows are immutable"):
        await db_session.flush()
    await db_session.rollback()

    attempt = await db_session.get(SessionTurnAttempt, attempt_id)
    assert attempt is not None
    event = SessionTurnAttemptEvent(attempt_id=attempt.id, event_sequence=1, event_kind="timeout")
    db_session.add(event)
    await db_session.flush()
    event_id = event.id
    attempt_id = attempt.id
    await db_session.commit()
    db_session.add(
        SessionTurnAttemptEvent(attempt_id=attempt_id, event_sequence=1, event_kind="unknown")
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()

    event = await db_session.get(SessionTurnAttemptEvent, event_id)
    assert event is not None
    await db_session.delete(event)
    with pytest.raises(ValueError, match="AttemptEvent rows are immutable"):
        await db_session.flush()


async def test_audit_is_one_per_turn_and_immutable(db_session) -> None:
    session = await _session(db_session)
    turn = _turn(session.id)
    db_session.add(turn)
    await db_session.flush()
    attempt = _attempt(turn.id)
    db_session.add(attempt)
    await db_session.flush()
    audit = SessionTurnContextAudit(
        session_id=session.id,
        turn_id=turn.id,
        turn_key=turn.turn_key,
        terminal_status="succeeded",
        agent_name="Dr-Chen-Jun",
        agent_version="5",
        skill_id=str(uuid.uuid4()),
        skill_version_id=str(uuid.uuid4()),
        sop_snapshot_digest=_digest("snapshot"),
        focus_digest=_digest("focus"),
        context_digest=_digest("context"),
        context_schema_version="1",
        applied_step=0,
        applied_context_revision=0,
        conversation_digest=_digest("conversation"),
        winning_attempt_id=attempt.id,
        provider_response_id="resp_1",
        progression_result="advanced",
        progression_from_step=0,
        progression_to_step=1,
    )
    db_session.add(audit)
    await db_session.flush()
    audit_id = audit.id
    await db_session.commit()

    duplicate = SessionTurnContextAudit(
        **{
            column.name: getattr(audit, column.name)
            for column in SessionTurnContextAudit.__table__.columns
            if column.name not in {"id", "created_at"}
        }
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()

    audit = await db_session.get(SessionTurnContextAudit, audit_id)
    assert audit is not None
    audit.progression_result = "unchanged"
    with pytest.raises(ValueError, match="ContextAudit rows are immutable"):
        await db_session.flush()
    await db_session.rollback()
    audit = await db_session.get(SessionTurnContextAudit, audit_id)
    assert audit is not None
    await db_session.delete(audit)
    with pytest.raises(ValueError, match="ContextAudit rows are immutable"):
        await db_session.flush()
