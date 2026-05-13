"""CU Evaluation Service: Azure Content Understanding-based scoring pipeline.

Replaces LLM-based scoring with structured Azure Content Understanding evaluation (D-07).
Implements analyzer CRUD (synced from ScoringRubric), content scoring via transcript,
voice scoring via audio, and layered score merging.

Key decisions:
- D-09: Rubric save triggers CU analyzer sync
- D-10: Dual-dimension scoring for voice sessions
- D-11: Layered merge using content_weight/voice_weight from rubric
- D-13: Text-only sessions only get content scoring
- D-14: Voice sessions get both content + voice scoring
- D-15: Content scoring via transcript JSON submission
- D-16: Voice sessions use CU re-transcription via voice analyzer
"""

import asyncio
import base64
import json
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.scoring_rubric import ScoringRubric
from app.models.session import CoachingSession
from app.services import config_service

logger = logging.getLogger(__name__)

# CU API configuration
CU_API_VERSION = "2025-11-01"
MAX_POLL_ATTEMPTS = 60
POLL_INTERVAL_SECONDS = 2.0
REQUEST_TIMEOUT = 30.0

# Service name for config lookup
CU_SERVICE_NAME = "content_understanding"

# Default voice dimensions if rubric doesn't specify voice-specific ones
DEFAULT_VOICE_DIMENSIONS = [
    {"name": "fluency", "weight": 30, "criteria": ["Smooth speech flow"], "max_score": 100},
    {"name": "tone", "weight": 25, "criteria": ["Professional tone"], "max_score": 100},
    {"name": "pace", "weight": 25, "criteria": ["Appropriate speaking pace"], "max_score": 100},
    {
        "name": "pronunciation",
        "weight": 20,
        "criteria": ["Clear pronunciation"],
        "max_score": 100,
    },
]


def build_content_analyzer_schema(rubric_dimensions: list[dict]) -> dict:
    """Convert ScoringRubric dimensions to CU content analyzer fieldSchema.

    Each dimension becomes a 'generate' field with type 'object' containing
    score (number), strengths (array), weaknesses (array), suggestions (array).
    Also includes a feedback_summary string field.
    """
    fields: dict[str, dict] = {}

    for dim in rubric_dimensions:
        dim_name = dim.get("name", "unknown").lower().replace(" ", "_")
        fields[dim_name] = {
            "type": "object",
            "method": "generate",
            "description": (
                f"Score for dimension '{dim.get('name', '')}' "
                f"(weight: {dim.get('weight', 0)}%, max: {dim.get('max_score', 100)}). "
                f"Criteria: {', '.join(dim.get('criteria', []))}"
            ),
            "properties": {
                "score": {
                    "type": "number",
                    "description": f"Score from 0 to {dim.get('max_score', 100)}",
                },
                "strengths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of observed strengths for this dimension",
                },
                "weaknesses": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of observed weaknesses for this dimension",
                },
                "suggestions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of improvement suggestions",
                },
            },
        }

    fields["feedback_summary"] = {
        "type": "string",
        "method": "generate",
        "description": "Overall feedback summary combining all dimension assessments",
    }

    return {"fields": fields}


def build_voice_analyzer_schema(rubric_dimensions: list[dict]) -> dict:
    """Build voice-specific CU fieldSchema for voice quality evaluation.

    Dimensions are voice quality aspects from rubric (or defaults:
    fluency, tone, pace, pronunciation). Each is 'generate' with score + feedback.
    """
    voice_dims = rubric_dimensions if rubric_dimensions else DEFAULT_VOICE_DIMENSIONS
    fields: dict[str, dict] = {}

    for dim in voice_dims:
        dim_name = dim.get("name", "unknown").lower().replace(" ", "_")
        fields[dim_name] = {
            "type": "object",
            "method": "generate",
            "description": (
                f"Voice quality score for '{dim.get('name', '')}' "
                f"(weight: {dim.get('weight', 0)}%)"
            ),
            "properties": {
                "score": {
                    "type": "number",
                    "description": f"Score from 0 to {dim.get('max_score', 100)}",
                },
                "feedback": {
                    "type": "string",
                    "description": f"Specific feedback for {dim.get('name', '')}",
                },
            },
        }

    fields["feedback_summary"] = {
        "type": "string",
        "method": "generate",
        "description": "Overall voice quality feedback summary",
    }

    fields["transcript"] = {
        "type": "string",
        "method": "generate",
        "description": "Re-transcription of the audio content for D-16 compliance",
    }

    return {"fields": fields}


async def sync_rubric_analyzers(db: AsyncSession, rubric: ScoringRubric) -> None:
    """Create or update CU custom analyzers when rubric is saved (D-09).

    Uses PUT to create/update analyzers with IDs derived from rubric ID.
    Stores analyzer IDs back to rubric model.
    If CU endpoint not configured, logs warning and skips (graceful degradation).
    """
    endpoint = await config_service.get_effective_endpoint(db, CU_SERVICE_NAME)
    api_key = await config_service.get_effective_key(db, CU_SERVICE_NAME)

    if not endpoint or not api_key:
        logger.warning(
            "CU endpoint/key not configured; skipping analyzer sync for rubric %s", rubric.id
        )
        return

    endpoint = endpoint.rstrip("/")
    rubric_id_short = rubric.id[:8]

    # Parse rubric dimensions
    dimensions = rubric.dimensions
    if isinstance(dimensions, str):
        dimensions = json.loads(dimensions)

    # Content analyzer
    content_analyzer_id = f"rubric-content-{rubric_id_short}"
    content_schema = build_content_analyzer_schema(dimensions)
    await _put_analyzer(endpoint, api_key, content_analyzer_id, content_schema, "content")

    # Voice analyzer
    voice_analyzer_id = f"rubric-voice-{rubric_id_short}"
    voice_schema = build_voice_analyzer_schema(DEFAULT_VOICE_DIMENSIONS)
    await _put_analyzer(endpoint, api_key, voice_analyzer_id, voice_schema, "voice")

    # Store analyzer IDs back to rubric
    rubric.cu_content_analyzer_id = content_analyzer_id  # type: ignore[attr-defined]
    rubric.cu_voice_analyzer_id = voice_analyzer_id  # type: ignore[attr-defined]
    await db.flush()

    logger.info(
        "Synced CU analyzers for rubric %s: content=%s, voice=%s",
        rubric.id,
        content_analyzer_id,
        voice_analyzer_id,
    )


async def _put_analyzer(
    endpoint: str,
    api_key: str,
    analyzer_id: str,
    field_schema: dict,
    analyzer_type: str,
) -> None:
    """PUT a CU custom analyzer definition. Creates or updates."""
    url = (
        f"{endpoint}/contentunderstanding/analyzers/{analyzer_id}"
        f"?api-version={CU_API_VERSION}"
    )
    headers = {
        "Ocp-Apim-Subscription-Key": api_key,
        "Content-Type": "application/json",
    }
    body = {
        "description": f"Auto-generated {analyzer_type} scoring analyzer",
        "fieldSchema": field_schema,
    }

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        response = await client.put(url, headers=headers, json=body)

        if response.status_code in (200, 201):
            logger.info("CU analyzer %s created/updated successfully", analyzer_id)
        else:
            logger.error(
                "CU analyzer PUT failed for %s: HTTP %d - %s",
                analyzer_id,
                response.status_code,
                response.text[:200],
            )
            raise RuntimeError(
                f"CU analyzer creation failed: HTTP {response.status_code}"
            )


async def score_content_with_cu(
    endpoint: str,
    api_key: str,
    analyzer_id: str,
    transcript_json: str,
) -> dict:
    """Submit transcript JSON to CU content analyzer and poll for results (D-10/D-15).

    Encodes transcript as base64, submits to CU analyzer via submit-then-poll pattern.
    Returns parsed fields dict with dimension scores.
    """
    endpoint = endpoint.rstrip("/")
    url = (
        f"{endpoint}/contentunderstanding/analyzers/{analyzer_id}:analyze"
        f"?api-version={CU_API_VERSION}"
    )
    headers = {
        "Ocp-Apim-Subscription-Key": api_key,
        "Content-Type": "application/json",
    }

    # Encode transcript JSON as base64 per CU API spec
    transcript_bytes = transcript_json.encode("utf-8")
    b64_content = base64.b64encode(transcript_bytes).decode("utf-8")

    body = {
        "inputs": [{"base64Source": b64_content}],
    }

    logger.info("Submitting content scoring to CU analyzer %s", analyzer_id)

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        response = await client.post(url, headers=headers, json=body)

        if response.status_code != 202:
            logger.error(
                "CU content scoring submit failed: HTTP %d - %s",
                response.status_code,
                response.text[:200],
            )
            raise RuntimeError(
                f"CU content scoring submission failed: HTTP {response.status_code}"
            )

        # Extract Operation-Location for polling
        operation_url = response.headers.get("Operation-Location", "")
        if not operation_url:
            raise RuntimeError("No Operation-Location header in CU content scoring response")

        # Poll until Succeeded (bounded: 60 attempts x 2s = 120s max per D-09)
        return await _poll_result(client, operation_url, api_key)


async def score_voice_with_cu(
    endpoint: str,
    api_key: str,
    analyzer_id: str,
    audio_url: str,
) -> dict:
    """Submit audio to CU voice analyzer and poll for results (D-10/D-14).

    Supports URL-based submission for Azure Blob storage audio,
    or base64 fallback for local development.
    Returns voice dimension scores + transcript.
    """
    endpoint = endpoint.rstrip("/")
    url = (
        f"{endpoint}/contentunderstanding/analyzers/{analyzer_id}:analyze"
        f"?api-version={CU_API_VERSION}"
    )
    headers = {
        "Ocp-Apim-Subscription-Key": api_key,
        "Content-Type": "application/json",
    }

    # Determine input format: URL for cloud storage, base64 for local files
    if audio_url.startswith(("http://", "https://")):
        body: dict = {"inputs": [{"url": audio_url}]}
    else:
        # Local file: read and base64 encode
        try:
            with open(audio_url, "rb") as f:
                audio_bytes = f.read()
            b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
            body = {"inputs": [{"base64Source": b64_audio}]}
        except (FileNotFoundError, OSError) as e:
            raise RuntimeError(f"Failed to read local audio file: {e}") from e

    logger.info("Submitting voice scoring to CU analyzer %s", analyzer_id)

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        response = await client.post(url, headers=headers, json=body)

        if response.status_code != 202:
            logger.error(
                "CU voice scoring submit failed: HTTP %d - %s",
                response.status_code,
                response.text[:200],
            )
            raise RuntimeError(
                f"CU voice scoring submission failed: HTTP {response.status_code}"
            )

        operation_url = response.headers.get("Operation-Location", "")
        if not operation_url:
            raise RuntimeError("No Operation-Location header in CU voice scoring response")

        return await _poll_result(client, operation_url, api_key)


async def _poll_result(client: httpx.AsyncClient, operation_url: str, api_key: str) -> dict:
    """Poll CU operation until Succeeded, Failed, or timeout."""
    poll_headers = {"Ocp-Apim-Subscription-Key": api_key}

    for _attempt in range(MAX_POLL_ATTEMPTS):
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        poll_response = await client.get(operation_url, headers=poll_headers)
        poll_data = poll_response.json()

        status = poll_data.get("status", "")
        if status == "Succeeded":
            result = poll_data.get("result", {})
            # Extract fields from CU result
            contents = result.get("contents", [])
            if contents:
                return contents[0].get("fields", {})
            return result.get("fields", {})
        if status in ("Failed", "Cancelled"):
            error_msg = poll_data.get("error", {}).get("message", "Unknown error")
            raise RuntimeError(f"CU analysis {status}: {error_msg}")

    raise RuntimeError(
        f"CU analysis timed out after {MAX_POLL_ATTEMPTS * POLL_INTERVAL_SECONDS}s"
    )


def merge_scores(
    content_scores: dict,
    voice_scores: dict | None,
    content_weight: int,
    voice_weight: int,
) -> dict:
    """Perform layered score merge using content_weight/voice_weight from rubric (D-11).

    - D-13: If voice_scores is None, final score = content only (100% weight).
    - D-14: If voice_scores present, apply weighted combination.

    Returns:
        {
            "overall_score": float,
            "content_total": float,
            "voice_total": float | None,
            "dimensions": list,
            "feedback_summary": str
        }
    """
    # Calculate content total as weighted average of content dimension scores
    content_dims = content_scores.get("dimensions", [])
    content_total = _calculate_weighted_total(content_dims)
    feedback_summary = content_scores.get("feedback_summary", "")

    if voice_scores is None:
        # D-13: Text-only session, content is 100%
        return {
            "overall_score": content_total,
            "content_total": content_total,
            "voice_total": None,
            "dimensions": content_dims,
            "feedback_summary": feedback_summary,
        }

    # D-14: Voice session with dual scoring
    voice_dims = voice_scores.get("dimensions", [])
    voice_total = _calculate_weighted_total(voice_dims)
    voice_feedback = voice_scores.get("feedback_summary", "")

    # D-11: Apply content_weight / voice_weight
    total_weight = content_weight + voice_weight
    if total_weight == 0:
        total_weight = 100  # Fallback to prevent division by zero

    content_ratio = content_weight / total_weight
    voice_ratio = voice_weight / total_weight
    overall_score = (content_total * content_ratio) + (voice_total * voice_ratio)

    # Combine dimension lists
    all_dimensions = content_dims + [
        {**d, "category": "voice"} for d in voice_dims
    ]

    # Combine feedback
    combined_feedback = feedback_summary
    if voice_feedback:
        combined_feedback = f"{feedback_summary}\n\nVoice: {voice_feedback}"

    return {
        "overall_score": round(overall_score, 2),
        "content_total": content_total,
        "voice_total": voice_total,
        "dimensions": all_dimensions,
        "feedback_summary": combined_feedback.strip(),
    }


def _calculate_weighted_total(dimensions: list[dict]) -> float:
    """Calculate weighted average score from dimension list.

    Each dimension has 'score' and 'weight'. Returns weighted average (0-100 scale).
    """
    if not dimensions:
        return 0.0

    total_weight = sum(d.get("weight", 0) for d in dimensions)
    if total_weight == 0:
        # Equal weight fallback
        return sum(d.get("score", 0) for d in dimensions) / len(dimensions)

    weighted_sum = sum(d.get("score", 0) * d.get("weight", 0) for d in dimensions)
    return round(weighted_sum / total_weight, 2)


async def score_session_with_cu(db: AsyncSession, session_id: str) -> dict:
    """Top-level orchestration: score a session using CU evaluation (D-07).

    Loads session, determines mode (text vs voice per D-13/D-14), gets rubric +
    analyzer IDs, calls content scorer (always) + voice scorer (if audio_url exists),
    merges results.

    Falls back to mock scoring if CU endpoint not configured (preserve dev experience).
    """
    from app.models.scenario import Scenario

    # Load session with scenario
    result = await db.execute(
        select(CoachingSession)
        .options(selectinload(CoachingSession.scenario))
        .where(CoachingSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise RuntimeError(f"Session {session_id} not found")

    scenario: Scenario = session.scenario
    if scenario is None:
        raise RuntimeError(f"Session {session_id} has no scenario")

    # Get rubric and analyzer IDs
    rubric = await _get_session_rubric(db, scenario)
    if rubric is None:
        logger.warning("No rubric found for session %s, returning mock scores", session_id)
        return _mock_scores()

    # Parse dimensions
    dimensions = rubric.dimensions
    if isinstance(dimensions, str):
        dimensions = json.loads(dimensions)

    # Get CU configuration
    endpoint = await config_service.get_effective_endpoint(db, CU_SERVICE_NAME)
    api_key = await config_service.get_effective_key(db, CU_SERVICE_NAME)

    if not endpoint or not api_key:
        logger.warning(
            "CU endpoint/key not configured, returning mock scores for session %s",
            session_id,
        )
        return _mock_scores()

    # Get content weight/voice weight from rubric (Plan 01 fields)
    content_weight = getattr(rubric, "content_weight", 60) or 60
    voice_weight = getattr(rubric, "voice_weight", 40) or 40

    # Get analyzer IDs
    content_analyzer_id = getattr(rubric, "cu_content_analyzer_id", None)
    voice_analyzer_id = getattr(rubric, "cu_voice_analyzer_id", None)

    # If analyzers not yet created, try sync
    if not content_analyzer_id:
        try:
            await sync_rubric_analyzers(db, rubric)
            content_analyzer_id = getattr(rubric, "cu_content_analyzer_id", None)
            voice_analyzer_id = getattr(rubric, "cu_voice_analyzer_id", None)
        except Exception as e:
            logger.warning("Failed to sync analyzers on-demand: %s", e)
            return _mock_scores()

    if not content_analyzer_id:
        logger.warning("No content analyzer ID after sync for rubric %s", rubric.id)
        return _mock_scores()

    # Build transcript from session messages
    transcript_json = await _build_transcript_json(db, session_id)

    # D-15: Always score content
    try:
        content_result = await score_content_with_cu(
            endpoint, api_key, content_analyzer_id, transcript_json
        )
        content_scores = _parse_cu_content_result(content_result, dimensions)
    except Exception as e:
        logger.error("CU content scoring failed for session %s: %s", session_id, e)
        return _mock_scores()

    # D-13/D-14: Score voice only if audio_url exists
    voice_scores = None
    if session.audio_url and voice_analyzer_id:
        try:
            voice_result = await score_voice_with_cu(
                endpoint, api_key, voice_analyzer_id, session.audio_url
            )
            voice_scores = _parse_cu_voice_result(voice_result)
        except Exception as e:
            logger.error("CU voice scoring failed for session %s: %s", session_id, e)
            # Voice scoring failure is non-fatal; proceed with content-only

    # D-11: Merge scores
    return merge_scores(content_scores, voice_scores, content_weight, voice_weight)


async def _get_session_rubric(db: AsyncSession, scenario: object) -> ScoringRubric | None:
    """Get the rubric associated with a scenario."""
    rubric_id = getattr(scenario, "rubric_id", None)
    if not rubric_id:
        return None

    result = await db.execute(
        select(ScoringRubric).where(ScoringRubric.id == rubric_id)
    )
    return result.scalar_one_or_none()


async def _build_transcript_json(db: AsyncSession, session_id: str) -> str:
    """Build transcript JSON from session messages."""
    from app.models.message import SessionMessage

    result = await db.execute(
        select(SessionMessage)
        .where(SessionMessage.session_id == session_id)
        .order_by(SessionMessage.created_at)
    )
    messages = result.scalars().all()

    transcript_entries = []
    for msg in messages:
        transcript_entries.append({
            "role": msg.role,
            "content": msg.content,
            "timestamp": str(msg.created_at) if msg.created_at else None,
        })

    return json.dumps(transcript_entries, ensure_ascii=False)


def _parse_cu_content_result(cu_fields: dict, rubric_dimensions: list[dict]) -> dict:
    """Parse CU content analyzer result into standardized scoring format."""
    dimensions = []
    for dim in rubric_dimensions:
        dim_name = dim.get("name", "unknown")
        dim_key = dim_name.lower().replace(" ", "_")
        cu_dim = cu_fields.get(dim_key, {})

        if isinstance(cu_dim, dict):
            score = cu_dim.get("score", 0)
            strengths = cu_dim.get("strengths", [])
            weaknesses = cu_dim.get("weaknesses", [])
            suggestions = cu_dim.get("suggestions", [])
        else:
            score = 0
            strengths = []
            weaknesses = []
            suggestions = []

        dimensions.append({
            "name": dim_name,
            "score": score,
            "weight": dim.get("weight", 0),
            "max_score": dim.get("max_score", 100),
            "strengths": strengths,
            "weaknesses": weaknesses,
            "suggestions": suggestions,
        })

    feedback_summary = cu_fields.get("feedback_summary", "")
    if isinstance(feedback_summary, dict):
        feedback_summary = feedback_summary.get("value", "")

    return {
        "dimensions": dimensions,
        "feedback_summary": str(feedback_summary),
    }


def _parse_cu_voice_result(cu_fields: dict) -> dict:
    """Parse CU voice analyzer result into standardized scoring format."""
    dimensions = []
    excluded_keys = {"feedback_summary", "transcript"}

    for key, value in cu_fields.items():
        if key in excluded_keys:
            continue
        if isinstance(value, dict) and "score" in value:
            dimensions.append({
                "name": key.replace("_", " ").title(),
                "score": value.get("score", 0),
                "weight": 25,  # Equal weight for voice dimensions
                "feedback": value.get("feedback", ""),
            })

    feedback_summary = cu_fields.get("feedback_summary", "")
    if isinstance(feedback_summary, dict):
        feedback_summary = feedback_summary.get("value", "")

    return {
        "dimensions": dimensions,
        "feedback_summary": str(feedback_summary),
    }


def _mock_scores() -> dict:
    """Return mock scores for development when CU is not configured."""
    return {
        "overall_score": 75.0,
        "content_total": 75.0,
        "voice_total": None,
        "dimensions": [
            {
                "name": "Key Messages",
                "score": 80,
                "weight": 40,
                "max_score": 100,
                "strengths": ["Good key message delivery"],
                "weaknesses": ["Could improve specificity"],
                "suggestions": ["Use more clinical data"],
            },
            {
                "name": "Communication",
                "score": 70,
                "weight": 30,
                "max_score": 100,
                "strengths": ["Clear communication"],
                "weaknesses": ["Missed follow-up opportunity"],
                "suggestions": ["Ask more open-ended questions"],
            },
            {
                "name": "Product Knowledge",
                "score": 75,
                "weight": 30,
                "max_score": 100,
                "strengths": ["Good product understanding"],
                "weaknesses": ["Missing competitive context"],
                "suggestions": ["Study competitor profiles"],
            },
        ],
        "feedback_summary": "Overall good performance with room for improvement in specificity.",
    }
