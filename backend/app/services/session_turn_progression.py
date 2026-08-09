"""Typed monotonic Session SOP progression and compare-and-set persistence."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import CoachingSession
from app.services.session_skill_context import load_sop_snapshot

ProgressionResult = Literal["unchanged", "advanced", "completed", "invalid", "detector_failed"]
Detector = Callable[[list[dict], list[str], str, str], Awaitable[int]]


@dataclass(frozen=True, slots=True)
class SessionProgressionDecision:
    """Validated pure decision for the next committed Session step."""

    result: ProgressionResult
    from_step: int
    to_step: int
    reason: str


async def decide_next_session_step(
    session: CoachingSession,
    messages: list[dict],
    endpoint: str,
    api_key: str,
    *,
    detector: Detector | None = None,
) -> SessionProgressionDecision:
    """Detect and clamp a monotonic next step without mutating Session state."""
    try:
        snapshot = load_sop_snapshot(session)
    except Exception as exc:
        return SessionProgressionDecision(
            result="invalid",
            from_step=session.sop_current_step if isinstance(session.sop_current_step, int) else 0,
            to_step=session.sop_current_step if isinstance(session.sop_current_step, int) else 0,
            reason=str(getattr(exc, "code", "invalid_snapshot")),
        )
    current = session.sop_current_step
    if not isinstance(current, int) or current < 0 or current > len(snapshot.sop_steps):
        return SessionProgressionDecision("invalid", 0, 0, "current_step_out_of_range")
    if current == len(snapshot.sop_steps):
        return SessionProgressionDecision("completed", current, current, "already_completed")
    if not endpoint:
        return SessionProgressionDecision("detector_failed", current, current, "endpoint_missing")
    if detector is None:
        from app.services.skill_focus_service import detect_sop_step

        detector = detect_sop_step
    try:
        detected = await detector(messages, list(snapshot.sop_steps), endpoint, api_key)
    except Exception as exc:
        return SessionProgressionDecision("detector_failed", current, current, type(exc).__name__)
    if isinstance(detected, bool) or not isinstance(detected, int):
        return SessionProgressionDecision(
            "invalid", current, current, "detector_result_not_integer"
        )
    bounded = min(max(detected, 0), len(snapshot.sop_steps))
    target = max(current, bounded)
    if target == current:
        return SessionProgressionDecision("unchanged", current, current, "no_monotonic_advance")
    result: ProgressionResult = "completed" if target == len(snapshot.sop_steps) else "advanced"
    return SessionProgressionDecision(result, current, target, "detector_advanced")


async def commit_session_progression(
    db: AsyncSession,
    session: CoachingSession,
    decision: SessionProgressionDecision,
    *,
    expected_revision: int,
    winner_committed: bool,
) -> bool:
    """CAS-commit advancement only after the caller's winner transaction is ready."""
    if not winner_committed or decision.result not in {"advanced", "completed"}:
        return False
    statement = (
        update(CoachingSession)
        .where(
            CoachingSession.id == session.id,
            CoachingSession.sop_current_step == decision.from_step,
            CoachingSession.context_revision == expected_revision,
        )
        .values(
            sop_current_step=decision.to_step,
            context_revision=expected_revision + 1,
        )
    )
    result = await db.execute(statement)
    if result.rowcount != 1:
        return False
    session.sop_current_step = decision.to_step
    session.context_revision = expected_revision + 1
    return True
