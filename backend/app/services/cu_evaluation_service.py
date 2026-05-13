"""Azure Content Understanding (CU) evaluation service.

Replaces LLM-based scoring_engine with Azure CU multimodal evaluation (D-07).
Provides unified scoring for both content and voice dimensions.

Falls back gracefully when CU is not configured — returns None so callers
can use their existing mock/fallback scoring paths.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.message import SessionMessage
from app.models.scenario import Scenario
from app.models.session import CoachingSession

logger = logging.getLogger(__name__)


async def score_session_with_cu(db: AsyncSession, session_id: str) -> dict | None:
    """Score a session using Azure Content Understanding.

    Returns a structured dict with:
    - dimensions: list of {name, score, weight, strengths, weaknesses, suggestions}
    - overall_score: float
    - feedback_summary: str
    - voice_total: float | None (if voice scoring was performed)

    Returns None if CU is not configured or unavailable.
    """
    from app.services import config_service

    # Check if CU endpoint is configured
    endpoint = await config_service.get_effective_endpoint(db, "content_understanding")
    api_key = await config_service.get_effective_key(db, "content_understanding")

    if not endpoint or not api_key:
        logger.info("CU scoring unavailable: no Content Understanding endpoint/key configured")
        return None

    # Load session with scenario
    result = await db.execute(
        select(CoachingSession)
        .options(
            selectinload(CoachingSession.scenario).selectinload(Scenario.hcp_profile),
        )
        .where(CoachingSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        logger.error("CU scoring: session %s not found", session_id)
        return None

    # Load messages
    msg_result = await db.execute(
        select(SessionMessage)
        .where(SessionMessage.session_id == session_id)
        .order_by(SessionMessage.message_index)
    )
    messages = list(msg_result.scalars().all())

    # Build transcript for CU analysis
    transcript = "\n".join(
        f"{'MR' if m.role == 'user' else 'HCP'}: {m.content}" for m in messages
    )

    try:
        cu_result = await _call_cu_api(endpoint, api_key, transcript, session)
        return cu_result
    except Exception as e:
        logger.error("CU evaluation failed for session %s: %s", session_id, e)
        return None


async def _call_cu_api(
    endpoint: str, api_key: str, transcript: str, session: CoachingSession
) -> dict | None:
    """Call Azure Content Understanding API for evaluation.

    Currently returns None (CU API integration pending full Azure SDK setup).
    When implemented, will:
    1. Submit transcript + audio (if available) to CU analyzer
    2. Parse structured evaluation response
    3. Map to standard scoring dimensions format
    """
    # TODO: Implement actual Azure CU API call when SDK is available
    # The CU analyzer IDs are stored in scoring_rubric.cu_content_analyzer_id
    # and scoring_rubric.cu_voice_analyzer_id (from Plan 01 schema extensions)
    #
    # For now, return None to trigger fallback to existing scoring paths.
    # This ensures the system works without CU configured while providing
    # the integration point for when CU becomes available.
    logger.info(
        "CU API call placeholder for session %s (endpoint: %s)",
        session.id,
        endpoint[:50],
    )
    return None
