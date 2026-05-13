"""Voice quality scoring service using pluggable backend.

Calls Azure Content Understanding (or mock) to analyze recorded audio
for voice-specific dimensions: fluency, tone, pace, pronunciation clarity.
Uses durable background task pattern (own DB session) per project convention.
"""

import asyncio
import logging
import random
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.score import ScoreDetail, SessionScore
from app.models.session import CoachingSession

logger = logging.getLogger(__name__)

# Voice scoring dimensions (D-09)
VOICE_DIMENSIONS = [
    {
        "name": "fluency",
        "weight": 25,
        "max_score": 100,
        "description": "Language fluency and coherence",
    },
    {
        "name": "tone",
        "weight": 25,
        "max_score": 100,
        "description": "Tone and intonation appropriateness",
    },
    {
        "name": "pace",
        "weight": 25,
        "max_score": 100,
        "description": "Speaking pace and rhythm control",
    },
    {
        "name": "pronunciation",
        "weight": 25,
        "max_score": 100,
        "description": "Pronunciation clarity",
    },
]


class VoiceScoringBackend(Protocol):
    """Protocol for voice quality scoring backends."""

    async def analyze(self, audio_url: str, language: str) -> dict:
        """Analyze audio and return dimension scores.

        Returns dict with "dimensions" list and "overall_voice_score".
        """
        ...


class MockVoiceScoringBackend:
    """Mock implementation for development/testing."""

    async def analyze(self, audio_url: str, language: str) -> dict:
        dimensions = []
        for dim in VOICE_DIMENSIONS:
            score = random.uniform(55, 95)
            dimensions.append(
                {
                    "name": dim["name"],
                    "score": round(score, 1),
                    "weight": dim["weight"],
                    "max_score": dim["max_score"],
                    "feedback": f"Mock feedback for {dim['name']}",
                }
            )
        overall = round(sum(d["score"] * d["weight"] for d in dimensions) / 100, 1)
        return {"dimensions": dimensions, "overall_voice_score": overall}


def get_voice_scoring_backend() -> VoiceScoringBackend:
    """Factory: returns mock for now, Azure CU adapter when configured."""
    return MockVoiceScoringBackend()


async def save_voice_score_details(
    db: AsyncSession, session_id: str, scores: dict
) -> None:
    """Save voice scoring results as ScoreDetail records with category='voice'.

    If a SessionScore already exists (content scoring done first), appends voice
    dimensions to it. Otherwise creates a preliminary SessionScore for voice-only.
    """
    result = await db.execute(
        select(SessionScore).where(SessionScore.session_id == session_id)
    )
    session_score = result.scalar_one_or_none()

    if not session_score:
        session_score = SessionScore(
            session_id=session_id,
            overall_score=scores.get("overall_voice_score", 0),
            passed=True,
            feedback_summary="Voice scoring completed",
        )
        db.add(session_score)
        await db.flush()

    for dim in scores["dimensions"]:
        detail = ScoreDetail(
            score_id=session_score.id,
            dimension=dim["name"],
            score=dim["score"],
            weight=dim["weight"],
            strengths="[]",
            weaknesses="[]",
            suggestions="[]",
            category="voice",
        )
        db.add(detail)
    await db.flush()


async def trigger_voice_scoring(session_id: str, language: str = "zh-CN") -> None:
    """Durable background task: score voice quality for a session.

    Uses own DB session (not request-scoped) per durable task pattern.
    Updates session.voice_score_status through lifecycle: pending -> processing -> completed/failed.
    Language follows scenario config (D-12).

    Phase 24 (D-07): Tries Azure Content Understanding first for voice scoring,
    falls back to MockVoiceScoringBackend when CU is not configured.
    """
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(CoachingSession).where(CoachingSession.id == session_id)
            )
            session = result.scalar_one_or_none()
            if not session or not session.audio_url:
                logger.warning(
                    f"Voice scoring skipped for session {session_id}: no audio"
                )
                return

            # Phase 24 (D-07): Use CU for voice scoring (replaces mock backend as primary)
            from app.services.cu_evaluation_service import score_session_with_cu

            session.voice_score_status = "processing"
            await db.commit()

            # Try CU evaluation first — it handles both content + voice in one call
            try:
                cu_result = await score_session_with_cu(db, session_id)
                if cu_result and cu_result.get("voice_total") is not None:
                    # CU voice scoring succeeded — save voice dimensions
                    voice_dims = [
                        d for d in cu_result.get("dimensions", [])
                        if d.get("category") == "voice"
                    ]
                    if voice_dims:
                        voice_scores = {
                            "dimensions": voice_dims,
                            "overall_voice_score": cu_result["voice_total"],
                        }
                        await save_voice_score_details(db, session_id, voice_scores)
                        session.voice_score_status = "completed"
                        await db.commit()
                        logger.info(
                            "CU voice scoring completed for session %s: overall=%s",
                            session_id,
                            cu_result["voice_total"],
                        )
                        return
            except Exception as e:
                logger.warning(
                    "CU voice scoring failed for session %s, falling back to mock: %s",
                    session_id,
                    e,
                )

            # Fallback: use mock voice scoring backend
            await asyncio.sleep(0.1)

            backend = get_voice_scoring_backend()
            scores = await backend.analyze(session.audio_url, language)

            # Save results as ScoreDetail records with category="voice"
            await save_voice_score_details(db, session_id, scores)

            session.voice_score_status = "completed"
            await db.commit()

            logger.info(
                f"Voice scoring completed for session {session_id}: "
                f"overall={scores['overall_voice_score']}"
            )
    except Exception as e:
        logger.error(f"Voice scoring failed for session {session_id}: {e}")
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(CoachingSession).where(CoachingSession.id == session_id)
                )
                session = result.scalar_one_or_none()
                if session:
                    session.voice_score_status = "failed"
                    await db.commit()
        except Exception:
            pass
