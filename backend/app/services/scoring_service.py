"""Post-session scoring service: multi-dimensional analysis and feedback."""

import json
import logging
import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.message import SessionMessage
from app.models.scenario import Scenario
from app.models.score import ScoreDetail, SessionScore
from app.models.session import CoachingSession
from app.models.skill import Skill
from app.services.cu_evaluation_service import score_session_with_cu
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

    # Get scenario and key messages status
    scenario = session.scenario
    key_messages_status = json.loads(session.key_messages_status)

    # Resolve rubric dimensions — rubric_id is NOT NULL per D-05
    rubric_dimensions = await resolve_rubric_dimensions(db, scenario)
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

    # Extract Skill-specific assessment criteria if a Skill is assigned
    skill_criteria = _extract_skill_criteria(scenario.skill)

    # Phase 24 (D-07): Try CU evaluation first, then LLM fallback, then mock
    cu_result = await score_session_with_cu(db, session_id)

    if cu_result:
        # CU scoring succeeded — use structured results
        logger.info("CU scoring succeeded for session %s", session_id)
        scores = cu_result
    else:
        # CU unavailable — fall back to LLM scoring engine
        scores = await score_with_llm(
            db, scenario_data, message_dicts, key_messages_status,
            rubric_dimensions, scenario.pass_threshold, skill_criteria=skill_criteria,
        )
        if scores is None:
            logger.info(
                "LLM scoring unavailable for session %s, using mock fallback", session_id
            )
            scores = _generate_mock_scores(
                scenario, messages, key_messages_status, rubric_dimensions
            )

    # Create SessionScore
    session_score = SessionScore(
        session_id=session_id,
        overall_score=scores["overall_score"],
        passed=scores["passed"],
        feedback_summary=scores["feedback_summary"],
    )
    db.add(session_score)
    await db.flush()

    # Create ScoreDetail records
    for dim_data in scores["dimensions"]:
        detail = ScoreDetail(
            score_id=session_score.id,
            dimension=dim_data["dimension"],
            score=dim_data["score"],
            weight=dim_data["weight"],
            strengths=json.dumps(dim_data["strengths"]),
            weaknesses=json.dumps(dim_data["weaknesses"]),
            suggestions=json.dumps(dim_data["suggestions"]),
        )
        db.add(detail)

    # Update session status
    session.status = "scored"
    session.overall_score = scores["overall_score"]
    session.passed = scores["passed"]

    await db.flush()

    # Reload score with details for response
    score_result = await db.execute(
        select(SessionScore)
        .options(selectinload(SessionScore.details))
        .where(SessionScore.id == session_score.id)
    )
    return score_result.scalar_one()


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
    result = await db.execute(
        select(CoachingSession)
        .options(
            selectinload(CoachingSession.scenario),
            selectinload(CoachingSession.score).selectinload(SessionScore.details),
        )
        .where(
            CoachingSession.user_id == user_id,
            CoachingSession.status == "scored",
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


async def get_combined_score_report(
    db: AsyncSession, session_id: str, user_id: str
) -> dict:
    """Get combined content + voice scoring report for a session (D-09, D-11).

    Separates ScoreDetail records by category and computes combined overall score.
    Content weighted 70%, voice weighted 30% when voice scores exist.
    """
    result = await db.execute(
        select(CoachingSession)
        .options(
            selectinload(CoachingSession.score).selectinload(SessionScore.details),
        )
        .where(CoachingSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise NotFoundException("Session not found")
    if session.user_id != user_id:
        raise AppException(
            status_code=403, code="FORBIDDEN", message="Not your session"
        )

    score = session.score
    if not score:
        raise NotFoundException("Score not found for session")

    content_dims = [d for d in score.details if d.category == "content"]
    voice_dims = [d for d in score.details if d.category == "voice"]

    content_score = score.overall_score or 0
    voice_score = 0.0
    if voice_dims:
        total_weight = sum(d.weight for d in voice_dims)
        if total_weight > 0:
            voice_score = sum(d.score * d.weight for d in voice_dims) / total_weight

    combined_score = (
        content_score
        if not voice_dims
        else (content_score * 0.7 + voice_score * 0.3)
    )

    strengths = (
        json.loads(score.feedback_summary)
        if score.feedback_summary.startswith("[")
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
    }


def _extract_skill_criteria(skill: Skill | None) -> str:
    """Extract assessment criteria section from Skill content for scoring enrichment.

    Looks for the "## Assessment Rubric" section in the Skill's Markdown content.
    Returns the section text, or empty string if no skill or no criteria found.
    """
    if skill is None or not skill.content:
        return ""

    content = skill.content
    # Find the Assessment Rubric section
    import re

    match = re.search(
        r"## Assessment Rubric\s*\n(.*?)(?=\n## |\Z)",
        content,
        re.DOTALL,
    )
    if match:
        return match.group(0).strip()

    # Fallback: look for assessment criteria in any format
    match = re.search(
        r"## Assessment\s*\n(.*?)(?=\n## |\Z)",
        content,
        re.DOTALL,
    )
    if match:
        return match.group(0).strip()

    return ""


def _generate_mock_scores(
    scenario: Scenario,
    messages: list[SessionMessage],
    key_messages_status: list[dict],
    rubric_dimensions: list[dict],
) -> dict:
    """Generate realistic-looking mock scores for development/testing.

    Loops over rubric_dimensions (arbitrary count) instead of hardcoded 5 blocks.
    Produces scores between 60-95 with personality-appropriate feedback,
    strengths with transcript quotes, weaknesses referencing missed key messages,
    and actionable suggestions per dimension.
    """
    key_messages = json.loads(scenario.key_messages)

    # Determine delivered/missed key messages
    delivered = [km for km in key_messages_status if km.get("delivered")]
    missed = [km for km in key_messages_status if not km.get("delivered")]
    delivery_ratio = len(delivered) / max(len(key_messages_status), 1)

    # Collect MR quotes for referencing in strengths
    mr_quotes = [msg.content for msg in messages if msg.role == "user"]
    sample_quote = mr_quotes[0] if mr_quotes else "Thank you for your time."

    # Generate dimension scores (slightly randomized but realistic)
    base_score = 65 + int(delivery_ratio * 25)  # 65-90 range based on delivery
    dimensions = []

    for dim_config in rubric_dimensions:
        dim_name = dim_config["name"]
        dim_weight = dim_config["weight"]
        score = min(95, max(60, base_score + random.randint(-8, 10)))

        # Generic strengths/weaknesses based on dimension name
        strengths = [
            {
                "text": f"Demonstrated competence in {dim_name}",
                "quote": sample_quote[:80] if mr_quotes else None,
            }
        ]
        weaknesses = [{"text": f"Room for improvement in {dim_name}", "quote": None}]
        suggestions = [
            f"Focus on strengthening {dim_name} skills",
            f"Review best practices for {dim_name}",
        ]

        # Special handling for key_message dimension (if present)
        if "key_message" in dim_name.lower() or "message" in dim_name.lower():
            if delivered:
                strengths = [
                    {
                        "text": (
                            f"Successfully delivered {len(delivered)} "
                            f"of {len(key_messages)} key messages"
                        ),
                        "quote": sample_quote[:100] if sample_quote else None,
                    }
                ]
            if missed:
                weaknesses = [
                    {"text": f"Missed key message: {m['message']}", "quote": None}
                    for m in missed[:2]
                ]
            suggestions = [
                "Prepare a structured approach to ensure all key messages are covered"
            ]

        dimensions.append(
            {
                "dimension": dim_name,
                "score": score,
                "weight": dim_weight,
                "strengths": strengths,
                "weaknesses": weaknesses,
                "suggestions": suggestions,
            }
        )

    # Calculate weighted overall score
    overall_score = sum(dim["score"] * dim["weight"] / 100 for dim in dimensions)
    overall_score = round(overall_score, 1)
    passed = overall_score >= scenario.pass_threshold

    # Generate feedback summary
    if passed:
        feedback_summary = (
            f"Good performance with an overall score of {overall_score}. "
            f"Successfully delivered {len(delivered)} of {len(key_messages)} key messages. "
            "Focus on strengthening weaker dimensions for continued improvement."
        )
    else:
        feedback_summary = (
            f"Score of {overall_score} is below the passing threshold of "
            f"{scenario.pass_threshold}. "
            f"Delivered {len(delivered)} of {len(key_messages)} key messages. "
            "Review key message coverage and practice across all dimensions."
        )

    return {
        "overall_score": overall_score,
        "passed": passed,
        "feedback_summary": feedback_summary,
        "dimensions": dimensions,
    }
