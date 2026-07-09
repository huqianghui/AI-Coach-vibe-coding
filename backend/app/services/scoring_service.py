"""Post-session scoring service: multi-dimensional analysis and feedback.

Orchestrates LLM content scoring (primary) + CU voice scoring (if audio exists).
No mock fallback — failures raise ScoringUnavailableException (HTTP 503).
"""

import json
import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.message import SessionMessage
from app.models.scenario import Scenario
from app.models.score import ScoreDetail, SessionScore
from app.models.session import CoachingSession
from app.models.voice_score import VoiceScore
from app.services.rubric_service import get_rubric
from app.services.scoring_engine import score_with_llm
from app.utils.exceptions import AppException, NotFoundException

logger = logging.getLogger(__name__)


async def resolve_rubric_dimensions(db: AsyncSession, scenario: Scenario) -> list[dict]:
    """Resolve rubric dimensions for scoring.

    Per D-05: rubric_id is NOT NULL, so direct lookup always succeeds.
    No fallback chain needed -- every scenario has an explicit rubric.
    """
    rubric = await get_rubric(db, scenario.rubric_id)
    dims = rubric.dimensions
    return json.loads(dims) if isinstance(dims, str) else dims


async def score_session(db: AsyncSession, session_id: str) -> SessionScore:
    """Score a completed coaching session with multi-dimensional analysis.

    Verifies session is 'completed' (not created, in_progress, or already scored),
    generates scoring via mock adapter, saves results, and updates session status.
    """
    # Load session with scenario and HCP profile
    result = await db.execute(
        select(CoachingSession)
        .options(
            selectinload(CoachingSession.scenario).selectinload(Scenario.hcp_profile),
            selectinload(CoachingSession.scenario).selectinload(Scenario.skill),
        )
        .where(CoachingSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise NotFoundException("Session not found")

    if session.status == "scored":
        raise AppException(
            status_code=409,
            code="ALREADY_SCORED",
            message="Session has already been scored",
        )

    existing_score = await get_session_score(db, session_id)
    if existing_score is not None and session.status == "completed":
        session.status = "scored"
        session.overall_score = existing_score.overall_score
        session.passed = existing_score.passed
        await db.flush()
        return existing_score

    if session.status != "completed":
        raise AppException(
            status_code=409,
            code="INVALID_STATUS",
            message=f"Cannot score session with status '{session.status}'. "
            "Session must be completed first.",
        )

    # Load messages
    msg_result = await db.execute(
        select(SessionMessage)
        .where(SessionMessage.session_id == session_id)
        .order_by(SessionMessage.message_index)
    )
    messages = list(msg_result.scalars().all())

    # Guard: cannot score a session with no conversation messages
    if not messages:
        raise AppException(
            status_code=409,
            code="NO_MESSAGES",
            message="Cannot score a session with no conversation messages. "
            "The session must have at least one message exchange.",
        )

    # Get scenario and key messages status
    scenario = session.scenario
    key_messages_status = json.loads(session.key_messages_status)

    # Resolve rubric config -- rubric_id is NOT NULL per D-05
    rubric = await get_rubric(db, scenario.rubric_id)
    dims = rubric.dimensions
    rubric_dimensions = json.loads(dims) if isinstance(dims, str) else dims
    hcp_profile_data = {}
    if scenario.hcp_profile:
        hcp_profile_data = {
            "name": scenario.hcp_profile.name,
            "specialty": scenario.hcp_profile.specialty,
            "personality_type": scenario.hcp_profile.personality_type,
            "communication_style": scenario.hcp_profile.communication_style,
        }
    scenario_data = {
        "product": scenario.product,
        "therapeutic_area": scenario.therapeutic_area,
        "difficulty": scenario.difficulty,
        "key_messages": scenario.key_messages,
        "hcp_profile": hcp_profile_data,
    }
    message_dicts = [{"role": m.role, "content": m.content} for m in messages]

    # LLM content scoring (primary, raises ScoringUnavailableException on failure)
    scores = await score_with_llm(
        db,
        scenario_data,
        message_dicts,
        key_messages_status,
        rubric_dimensions,
        scenario.pass_threshold,
        prompt_template=rubric.prompt_template,
    )

    overall_score = scores["overall_score"]
    passed = scores.get("passed", overall_score >= scenario.pass_threshold)

    # Create SessionScore
    session_score = SessionScore(
        session_id=session_id,
        overall_score=overall_score,
        passed=passed,
        feedback_summary=scores["feedback_summary"],
    )
    db.add(session_score)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        existing_score = await get_session_score(db, session_id)
        if existing_score is None:
            raise
        session_result = await db.execute(
            select(CoachingSession).where(CoachingSession.id == session_id)
        )
        existing_session = session_result.scalar_one_or_none()
        if existing_session is not None:
            existing_session.status = "scored"
            existing_session.overall_score = existing_score.overall_score
            existing_session.passed = existing_score.passed
            await db.flush()
        return existing_score

    # Create ScoreDetail records
    for dim_data in scores["dimensions"]:
        dimension_name = dim_data.get("dimension") or dim_data.get("name", "unknown")
        detail = ScoreDetail(
            score_id=session_score.id,
            dimension=dimension_name,
            score=dim_data["score"],
            weight=dim_data["weight"],
            strengths=json.dumps(dim_data.get("strengths", [])),
            weaknesses=json.dumps(dim_data.get("weaknesses", [])),
            suggestions=json.dumps(dim_data.get("suggestions", [])),
            category=dim_data.get("category", "content"),
        )
        db.add(detail)

    # Update session status
    session.status = "scored"
    session.overall_score = overall_score
    session.passed = passed
    await _sync_group_run_item_after_scoring(db, session)

    await db.flush()

    # Reload score with details for response
    score_result = await db.execute(
        select(SessionScore)
        .options(selectinload(SessionScore.details))
        .where(SessionScore.id == session_score.id)
    )
    return score_result.scalar_one()


async def _sync_group_run_item_after_scoring(db: AsyncSession, session: CoachingSession) -> None:
    """Update a scenario group run item after its child session is scored."""
    from app.models.scenario_group import ScenarioGroupRunItem

    result = await db.execute(
        select(ScenarioGroupRunItem).where(ScenarioGroupRunItem.session_id == session.id)
    )
    run_item = result.scalar_one_or_none()
    if run_item is not None:
        run_item.status = "scored"
        run_item.score = session.overall_score
        run_item.passed = session.passed


async def rescore_session(db: AsyncSession, session_id: str) -> SessionScore:
    """Re-score an already-scored session with current rubric dimensions.

    Deletes existing scores (SessionScore + ScoreDetails), resets session status
    to 'completed', then runs the full scoring pipeline with current criteria.
    This enables re-evaluation when scoring rubrics or modes have changed.
    """
    # Load session with scenario and HCP profile
    result = await db.execute(
        select(CoachingSession)
        .options(
            selectinload(CoachingSession.scenario).selectinload(Scenario.hcp_profile),
            selectinload(CoachingSession.scenario).selectinload(Scenario.skill),
        )
        .where(CoachingSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise NotFoundException("Session not found")

    if session.status != "scored":
        raise AppException(
            status_code=409,
            code="NOT_SCORED",
            message=f"Cannot rescore session with status '{session.status}'. "
            "Session must have been scored previously.",
        )

    # Delete existing score details first (child FK), then the session score
    existing_score = await db.execute(
        select(SessionScore).where(SessionScore.session_id == session_id)
    )
    score_record = existing_score.scalar_one_or_none()
    if score_record:
        # Delete all score details for this score
        detail_result = await db.execute(
            select(ScoreDetail).where(ScoreDetail.score_id == score_record.id)
        )
        for detail in detail_result.scalars().all():
            await db.delete(detail)
        await db.delete(score_record)
        await db.flush()

    # Reset session status to completed so score_session can process it
    session.status = "completed"
    session.overall_score = None
    session.passed = None
    await db.flush()

    # Run normal scoring pipeline (reuses current rubric dimensions)
    return await score_session(db, session_id)


async def get_session_score(db: AsyncSession, session_id: str) -> SessionScore | None:
    """Fetch the SessionScore with eager-loaded ScoreDetail for a session.

    Returns None if the session has not been scored yet.
    """
    result = await db.execute(
        select(SessionScore)
        .options(selectinload(SessionScore.details))
        .where(SessionScore.session_id == session_id)
    )
    return result.scalar_one_or_none()


async def get_score_history(db: AsyncSession, user_id: str, limit: int = 10) -> list[dict]:
    """Return last N scored sessions with dimension scores and trend data.

    For each session, computes improvement_pct per dimension by comparing
    with the previous (older) session's scores.
    """
    # Load scored sessions with score + details in a single query (fix N+1)
    # Exclude sessions with no messages (prematurely ended/scored without conversation)
    from sqlalchemy import exists

    has_messages = exists().where(SessionMessage.session_id == CoachingSession.id)

    result = await db.execute(
        select(CoachingSession)
        .options(
            selectinload(CoachingSession.scenario),
            selectinload(CoachingSession.score).selectinload(SessionScore.details),
        )
        .where(
            CoachingSession.user_id == user_id,
            CoachingSession.status == "scored",
            has_messages,
        )
        .order_by(CoachingSession.completed_at.desc())
        .limit(limit)
    )
    sessions = list(result.scalars().all())

    if not sessions:
        return []

    # Build history entries with dimension details
    history: list[dict] = []
    for session in sessions:
        score = session.score
        if score is None:
            continue

        dimensions = [
            {
                "dimension": detail.dimension,
                "score": detail.score,
                "weight": detail.weight,
            }
            for detail in score.details
            if detail.category == "content"
        ]

        history.append(
            {
                "session_id": session.id,
                "scenario_name": session.scenario.name if session.scenario else "",
                "overall_score": score.overall_score,
                "passed": score.passed,
                "completed_at": (
                    session.completed_at.isoformat() if session.completed_at else None
                ),
                "dimensions": dimensions,
            }
        )

    # Compute trends: compare each entry with the next (older) one
    for i, entry in enumerate(history):
        next_entry = history[i + 1] if i + 1 < len(history) else None
        if next_entry is None:
            # Oldest session — no previous to compare
            for dim in entry["dimensions"]:
                dim["improvement_pct"] = None
        else:
            # Build lookup for previous session dimensions
            prev_dims = {d["dimension"]: d["score"] for d in next_entry["dimensions"]}
            for dim in entry["dimensions"]:
                prev_score = prev_dims.get(dim["dimension"])
                if prev_score is not None:
                    dim["improvement_pct"] = round(dim["score"] - prev_score, 1)
                else:
                    dim["improvement_pct"] = None

    return history


async def get_combined_score_report(db: AsyncSession, session_id: str, user_id: str) -> dict:
    """Get combined content + voice scoring report for a session (D-09, D-11).

    Separates ScoreDetail records by category and computes combined overall score
    using rubric's content_weight/voice_weight (not hardcoded).
    """
    result = await db.execute(
        select(CoachingSession)
        .options(
            selectinload(CoachingSession.score).selectinload(SessionScore.details),
            selectinload(CoachingSession.voice_score).selectinload(VoiceScore.details),
            selectinload(CoachingSession.scenario),
        )
        .where(CoachingSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise NotFoundException("Session not found")
    if session.user_id != user_id:
        raise AppException(status_code=403, code="FORBIDDEN", message="Not your session")

    score = session.score
    if not score:
        raise NotFoundException("Score not found for session")

    # Load rubric weights
    rubric = await get_rubric(db, session.scenario.rubric_id)
    content_weight = rubric.content_weight
    voice_weight = rubric.voice_weight

    content_dims = [d for d in score.details if d.category == "content"]
    voice_dims = (
        list(session.voice_score.details)
        if session.voice_score
        else [d for d in score.details if d.category == "voice"]
    )

    content_score = score.overall_score or 0
    voice_score = 0.0
    if session.voice_score:
        voice_score = session.voice_score.overall_voice_score
    elif voice_dims:
        total_w = sum(d.weight for d in voice_dims)
        if total_w > 0:
            voice_score = sum(d.score * d.weight for d in voice_dims) / total_w

    has_voice = bool(voice_dims)
    if has_voice:
        total_weight = content_weight + voice_weight
        combined_score = (
            content_score * content_weight + voice_score * voice_weight
        ) / total_weight
    else:
        combined_score = content_score

    strengths = (
        json.loads(score.feedback_summary)
        if score.feedback_summary and score.feedback_summary.startswith("[")
        else []
    )

    return {
        "session_id": session_id,
        "overall_score": content_score,
        "overall_combined_score": round(combined_score, 1),
        "passed": score.passed,
        "content_dimensions": content_dims,
        "voice_dimensions": voice_dims,
        "voice_summary": {
            "overall_voice_score": round(voice_score, 1),
            "voice_score_status": session.voice_score_status,
            "dimensions": voice_dims,
        },
        "strengths": strengths if isinstance(strengths, list) else [],
        "weaknesses": [],
        "suggestions": [],
        "feedback_summary": score.feedback_summary,
        "audio_url": session.audio_url,
        "content_total": round(content_score, 1),
        "voice_total": round(voice_score, 1) if has_voice else None,
        "content_weight": content_weight if has_voice else 100,
        "voice_weight": voice_weight if has_voice else None,
    }
