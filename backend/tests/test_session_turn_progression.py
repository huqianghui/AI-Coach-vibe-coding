"""Tests for typed monotonic Session SOP progression."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.session import CoachingSession
from app.models.skill import Skill, SkillVersion
from app.services.session_skill_context import build_sop_snapshot
from app.services.session_turn_progression import (
    SessionProgressionDecision,
    commit_session_progression,
    decide_next_session_step,
)


def _session(step=1, revision=2):
    skill = Skill(
        id="skill-1",
        name="SOP",
        description="",
        status="published",
        created_by="user-1",
    )
    version = SkillVersion(
        id="version-1",
        skill_id=skill.id,
        version_number=1,
        content="# SOP\n## Step 1: Open\n## Step 2: Explore\n## Step 3: Close",
        metadata_json="{}",
        is_published=True,
        created_by="user-1",
    )
    _, payload, digest = build_sop_snapshot(skill, version)
    return CoachingSession(
        id="session-1",
        agent_name="agent",
        agent_version="1",
        skill_id=skill.id,
        skill_version_id=version.id,
        sop_snapshot_json=payload,
        sop_snapshot_sha256=digest,
        focus_instruction="immutable bytes",
        sop_current_step=step,
        context_revision=revision,
    )


@pytest.mark.parametrize(
    ("detected", "result", "target"),
    [
        (0, "unchanged", 1),
        (1, "unchanged", 1),
        (2, "advanced", 2),
        (99, "completed", 3),
    ],
)
async def test_decision_is_monotonic_and_bounded(detected, result, target):
    detector = AsyncMock(return_value=detected)

    decision = await decide_next_session_step(_session(), [], "endpoint", "key", detector=detector)

    assert decision.result == result
    assert decision.from_step == 1
    assert decision.to_step == target


async def test_completed_session_does_not_call_detector():
    detector = AsyncMock()

    decision = await decide_next_session_step(
        _session(step=3), [], "endpoint", "key", detector=detector
    )

    assert decision.result == "completed"
    detector.assert_not_awaited()


async def test_missing_endpoint_and_detector_exception_fail_without_advancing():
    missing = await decide_next_session_step(_session(), [], "", "", detector=AsyncMock())
    failed = await decide_next_session_step(
        _session(), [], "endpoint", "key", detector=AsyncMock(side_effect=TimeoutError)
    )

    assert (missing.result, missing.to_step) == ("detector_failed", 1)
    assert (failed.result, failed.to_step) == ("detector_failed", 1)


async def test_invalid_detector_result_and_snapshot_are_typed_invalid():
    invalid_result = await decide_next_session_step(
        _session(), [], "endpoint", "key", detector=AsyncMock(return_value="2")
    )
    invalid_session = _session()
    invalid_session.sop_snapshot_sha256 = "broken"
    invalid_snapshot = await decide_next_session_step(
        invalid_session, [], "endpoint", "key", detector=AsyncMock(return_value=2)
    )

    assert invalid_result.result == "invalid"
    assert invalid_snapshot.result == "invalid"


async def test_commit_requires_winner_and_successful_compare_and_set():
    session = _session()
    decision = SessionProgressionDecision("advanced", 1, 2, "detector_advanced")
    db = MagicMock()
    execution = MagicMock(rowcount=1)
    db.execute = AsyncMock(return_value=execution)

    losing = await commit_session_progression(
        db, session, decision, expected_revision=2, winner_committed=False
    )
    won = await commit_session_progression(
        db, session, decision, expected_revision=2, winner_committed=True
    )

    assert losing is False
    assert won is True
    assert session.sop_current_step == 2
    assert session.context_revision == 3
    assert session.focus_instruction == "immutable bytes"
    db.execute.assert_awaited_once()


async def test_commit_rejects_noop_and_cas_loss():
    session = _session()
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(rowcount=0))

    noop = await commit_session_progression(
        db,
        session,
        SessionProgressionDecision("unchanged", 1, 1, "same"),
        expected_revision=2,
        winner_committed=True,
    )
    lost = await commit_session_progression(
        db,
        session,
        SessionProgressionDecision("advanced", 1, 2, "advance"),
        expected_revision=2,
        winner_committed=True,
    )

    assert noop is False
    assert lost is False
    assert session.sop_current_step == 1
    assert session.context_revision == 2
