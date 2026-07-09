"""Conference session orchestration: create, question generation, respond, score."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import AsyncSessionLocal
from app.models.conference import ConferenceAudienceHcp
from app.models.hcp_profile import HcpProfile
from app.models.message import SessionMessage
from app.models.scenario import Scenario
from app.models.session import CoachingSession
from app.services.agents.base import CoachEventType, CoachRequest
from app.services.agents.registry import registry
from app.services.conference_prompt_config import normalize_conference_prompt_config
from app.services.prompt_builder import build_conference_audience_prompt
from app.services.turn_manager import QueuedQuestion, turn_manager
from app.services.voice_live_instance_service import resolve_voice_config
from app.utils.datetime import as_utc_aware, utc_now_naive
from app.utils.exceptions import AppException, NotFoundException

logger = logging.getLogger(__name__)

# Pause (seconds) inserted between speakers so they appear one at a time in the UI
# rather than all at once. Module-level so tests can monkeypatch it to 0.
SPEAKER_PACING_SECONDS = 0.6

# Number of contextual follow-up replies an HCP can make before the floor moves
# to the next HCP. Users can still move on earlier by saying "下一位" / "next".
HCP_FOLLOWUPS_BEFORE_NEXT = 3


async def create_conference_session(
    db: AsyncSession, scenario_id: str, user_id: str, mode: str = "text"
) -> CoachingSession:
    """Create a conference session with multi-HCP audience setup.

    Verifies the scenario is conference mode, loads audience HCPs,
    and initializes session with audience_config and key_messages_status.
    """
    result = await db.execute(select(Scenario).where(Scenario.id == scenario_id))
    scenario = result.scalar_one_or_none()
    if scenario is None:
        raise NotFoundException("Scenario not found")
    if scenario.mode != "conference":
        raise AppException(
            status_code=409,
            code="NOT_CONFERENCE_SCENARIO",
            message="Scenario is not configured for conference mode",
        )

    # Load audience HCPs with profile data
    audience_result = await db.execute(
        select(ConferenceAudienceHcp)
        .options(
            selectinload(ConferenceAudienceHcp.hcp_profile).selectinload(
                HcpProfile.voice_live_instance
            )
        )
        .where(ConferenceAudienceHcp.scenario_id == scenario_id)
        .order_by(ConferenceAudienceHcp.sort_order)
    )
    audience_hcps = list(audience_result.scalars().all())
    if len(audience_hcps) < 2:
        raise AppException(
            status_code=409,
            code="INSUFFICIENT_AUDIENCE",
            message="Conference scenario needs at least 2 HCP audience members",
        )

    conference_prompt_config = normalize_conference_prompt_config(scenario.conference_prompt_config)
    asking_audience = [ah for ah in audience_hcps if ah.role_in_conference != "moderator"]
    primary_hcp_id = asking_audience[0].hcp_profile_id if asking_audience else ""

    # Build audience config JSON from HCP profiles
    audience_config = [
        {
            "hcp_profile_id": ah.hcp_profile_id,
            "name": ah.hcp_profile.name,
            "specialty": ah.hcp_profile.specialty,
            "personality_type": ah.hcp_profile.personality_type,
            "role": ah.role_in_conference,
            "voice_id": ah.voice_id,
            "voice_live_instance_id": ah.hcp_profile.voice_live_instance_id,
            "voice_name": vc["voice_name"],
            "voice_live_enabled": vc["voice_live_enabled"],
            "avatar_enabled": vc["avatar_enabled"],
            "avatar_character": vc["avatar_character"],
            "avatar_style": vc["avatar_style"],
            "sort_order": ah.sort_order,
            "speaker_priority": "primary" if ah.hcp_profile_id == primary_hcp_id else "secondary",
            "speaker_order_policy": conference_prompt_config["speaker_order_policy"],
        }
        for ah in audience_hcps
        for vc in [resolve_voice_config(ah.hcp_profile)]
    ]
    if audience_config:
        audience_config[0]["conference_prompt_config"] = conference_prompt_config

    # Initialize key messages tracking
    key_messages = json.loads(scenario.key_messages)
    key_messages_status = [
        {"message": msg, "delivered": False, "detected_at": None} for msg in key_messages
    ]

    session = CoachingSession(
        user_id=user_id,
        scenario_id=scenario_id,
        status="created",
        mode=mode,
        session_type="conference",
        sub_state="presenting",
        presentation_topic=scenario.description,
        audience_config=json.dumps(audience_config),
        key_messages_status=json.dumps(key_messages_status),
    )
    db.add(session)
    await db.flush()
    return session


async def start_conference_round(db: AsyncSession, session: CoachingSession) -> AsyncIterator[dict]:
    """Start the conference with a moderator invitation for the MR to present."""
    audience_config = json.loads(session.audience_config or "[]")
    moderator = next((h for h in audience_config if h.get("role") == "moderator"), None)
    if moderator is not None:
        async for event_data in _emit_moderator_remark(db, session, "", moderator, "invite"):
            yield event_data
    yield {
        "event": "sub_state",
        "data": json.dumps(
            {
                "sub_state": "presenting",
                "message": "Please begin your presentation.",
            }
        ),
    }


async def run_presentation_round(
    db: AsyncSession, session: CoachingSession, mr_text: str
) -> AsyncIterator[dict]:
    """Start a presentation round and release only the first HCP question.

    Speaking order in this phase:
        1. Moderator opening remark (if a moderator is configured)
        2. First audience HCP question only

    Subsequent HCP questions are released one-by-one in ``handle_respond``
    after each MR response.
    """
    # Persist the MR presentation and echo it back as a transcription line
    await _save_conference_message(db, session.id, "user", mr_text)
    yield {
        "event": "transcription",
        "data": json.dumps({"speaker": "MR", "text": mr_text, "timestamp": _now_iso()}),
    }

    # Detect key messages delivered in the presentation
    from app.services.session_service import detect_key_messages

    km_status = await detect_key_messages(db, session, mr_text)
    yield {"event": "key_messages", "data": json.dumps(km_status)}

    audience_config = json.loads(session.audience_config or "[]")
    moderator = next((h for h in audience_config if h.get("role") == "moderator"), None)

    # 1. Moderator opening
    if moderator is not None:
        async for event_data in _emit_moderator_remark(db, session, mr_text, moderator, "opening"):
            yield event_data
        await asyncio.sleep(SPEAKER_PACING_SECONDS)

    # 2. Generate and release only the first audience question now.
    first_question = await _generate_next_hcp_question(db, session, mr_text)
    if first_question is not None:
        async for event_data in _emit_question_event(db, session, first_question):
            yield event_data
        yield {
            "event": "queue_update",
            "data": json.dumps(_serialize_queue(_current_queue_view(session.id))),
        }
        return

    # No HCP question generated: moderator closes immediately.
    if moderator is not None:
        await asyncio.sleep(SPEAKER_PACING_SECONDS)
        async for event_data in _emit_moderator_remark(db, session, mr_text, moderator, "closing"):
            yield event_data


async def _emit_moderator_remark(
    db: AsyncSession,
    session: CoachingSession,
    mr_text: str,
    moderator: dict,
    phase: str,
) -> AsyncIterator[dict]:
    """Emit a moderator opening/closing remark as a single sequential speaker turn."""
    text = _moderator_remark_from_session(session, mr_text, phase)
    if not text:
        return
    hcp_id = moderator.get("hcp_profile_id", "")
    name = moderator.get("name", "Moderator")
    yield {
        "event": "turn_change",
        "data": json.dumps({"speaker_id": hcp_id, "speaker_name": name, "action": "asking"}),
    }
    yield {
        "event": "speaker_text",
        "data": json.dumps({"speaker_id": hcp_id, "speaker_name": name, "content": text}),
    }
    await _save_conference_message(
        db, session.id, "assistant", text, speaker_id=hcp_id, speaker_name=name
    )
    yield {
        "event": "transcription",
        "data": json.dumps({"speaker": name, "text": text, "timestamp": _now_iso()}),
    }
    yield {
        "event": "turn_change",
        "data": json.dumps({"speaker_id": hcp_id, "speaker_name": name, "action": "listening"}),
    }


async def _emit_question_event(
    db: AsyncSession,
    session: CoachingSession,
    question: QueuedQuestion,
) -> AsyncIterator[dict]:
    """Emit one queued HCP question as a single speaker turn."""
    turn_manager.activate_question(session.id, question.hcp_profile_id)
    yield {
        "event": "turn_change",
        "data": json.dumps(
            {
                "speaker_id": question.hcp_profile_id,
                "speaker_name": question.hcp_name,
                "action": "asking",
            }
        ),
    }
    yield {
        "event": "speaker_text",
        "data": json.dumps(
            {
                "speaker_id": question.hcp_profile_id,
                "speaker_name": question.hcp_name,
                "content": question.question,
            }
        ),
    }
    await _save_conference_message(
        db,
        session.id,
        "assistant",
        question.question,
        speaker_id=question.hcp_profile_id,
        speaker_name=question.hcp_name,
    )
    yield {
        "event": "transcription",
        "data": json.dumps(
            {
                "speaker": question.hcp_name,
                "text": question.question,
                "timestamp": _now_iso(),
            }
        ),
    }
    yield {
        "event": "turn_change",
        "data": json.dumps(
            {
                "speaker_id": question.hcp_profile_id,
                "speaker_name": question.hcp_name,
                "action": "listening",
            }
        ),
    }


def _current_queue_view(session_id: str) -> list[QueuedQuestion]:
    """Expose at most one waiting question to enforce one-by-one dialogues."""
    active = turn_manager.get_active_speaker(session_id)
    if active is not None:
        return [active]
    waiting = turn_manager.get_queue(session_id)
    return waiting[:1]


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


def _contains_cjk(text: str) -> bool:
    """Return True if the text contains any CJK character (used for language choice)."""
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def _moderator_remark(mr_text: str, phase: str) -> str:
    """Pick a scripted moderator remark matching the presentation language."""
    lang = "zh" if not mr_text or _contains_cjk(mr_text) else "en"
    return (
        normalize_conference_prompt_config(None)
        .get("moderator_remarks", {})
        .get(phase, {})
        .get(lang, "")
    )


def _conference_prompt_config_from_session(session: CoachingSession) -> dict:
    """Read the prompt config snapshot stored in audience_config."""
    audience_config = json.loads(session.audience_config or "[]")
    for member in audience_config:
        if isinstance(member, dict) and member.get("conference_prompt_config"):
            return normalize_conference_prompt_config(member.get("conference_prompt_config"))
    return normalize_conference_prompt_config(None)


def _moderator_remark_from_session(session: CoachingSession, mr_text: str, phase: str) -> str:
    """Pick a configured moderator remark matching the presentation language."""
    config = _conference_prompt_config_from_session(session)
    lang = "zh" if not mr_text or _contains_cjk(mr_text) else "en"
    return config.get("moderator_remarks", {}).get(phase, {}).get(lang, "")


def _normalize_generated_text(text: str) -> str:
    """Trim model output and remove wrapping quotation marks."""
    normalized = text.strip()
    quote_chars = "'\"“”‘’"
    normalized = normalized.strip(quote_chars).strip()
    return normalized


def _mr_requests_next_hcp(text: str) -> bool:
    """Return True when the MR explicitly asks to move to the next HCP."""
    normalized = text.strip().lower()
    return any(token in normalized for token in ("下一位", "下一个", "换一个", "next"))


def _hcp_signals_done(text: str) -> bool:
    """Return True when an HCP reply clearly closes their thread."""
    normalized = text.lower()
    return any(
        token in normalized
        for token in (
            "没有其他问题",
            "我的问题就这些",
            "我没有更多问题",
            "no further questions",
            "no more questions",
        )
    )


def _fallback_hcp_question(hcp_config: dict, mr_text: str) -> str:
    """Build a conservative HCP question when the LLM returns no usable text."""
    specialty = hcp_config.get("specialty") or "临床"
    if not mr_text or _contains_cjk(mr_text):
        return (
            f"从{specialty}医生的角度，我想请你先说明一下这次主题的核心患者人群和临床价值是什么？"
        )
    return (
        f"From a {specialty} perspective, could you clarify the core patient population "
        "and clinical value for this topic?"
    )


async def _collect_coach_text(request: CoachRequest) -> tuple[str, str | None]:
    """Collect streamed text from the configured LLM adapter.

    Returns ``(text, error)``. The conference flow must not silently treat adapter
    errors as empty model output, because that can leave an HCP active with no
    visible response.
    """
    from app.config import get_settings

    settings = get_settings()
    adapter = registry.get("llm", settings.default_llm_provider)
    if adapter is None:
        return "", "No LLM adapter available"

    full_text = ""
    async for event in adapter.execute(request):
        if event.type == CoachEventType.TEXT:
            full_text += event.content
        elif event.type == CoachEventType.ERROR:
            return full_text, event.content or "LLM adapter returned an error"
        elif event.type == CoachEventType.DONE:
            break

    return _normalize_generated_text(full_text), None


async def generate_hcp_questions(
    db: AsyncSession, session: CoachingSession, mr_text: str
) -> list[QueuedQuestion]:
    """Generate HCP questions sequentially (not parallel, per RESEARCH Pitfall 4).

    For each HCP in the audience, builds a conference prompt and calls LLM
    to generate a question. Questions are queued in turn_manager.
    """
    audience_config = json.loads(session.audience_config or "[]")
    if not audience_config:
        return []

    # Load scenario for context
    scenario_result = await db.execute(select(Scenario).where(Scenario.id == session.scenario_id))
    scenario = scenario_result.scalar_one_or_none()

    # Get conversation history
    msg_result = await db.execute(
        select(SessionMessage)
        .where(SessionMessage.session_id == session.id)
        .order_by(SessionMessage.message_index)
    )
    messages = list(msg_result.scalars().all())
    conversation_history = [
        {"role": msg.role, "content": msg.content, "speaker_name": msg.speaker_name}
        for msg in messages
    ]

    generated_questions: list[QueuedQuestion] = []
    other_hcp_questions: list[dict] = []

    # Moderators introduce and close the session; they do not ask audience questions
    asking_hcps = [h for h in audience_config if h.get("role") != "moderator"]

    # Generate questions sequentially -- each HCP sees prior HCPs' questions
    from app.services.prompt_registry import get_prompt

    conference_base_template = await get_prompt(db, "conference.audience")

    for hcp_config in asking_hcps:
        hcp_prompt = build_conference_audience_prompt(
            hcp_config=hcp_config,
            scenario=scenario,
            presentation_topic=session.presentation_topic or "",
            conversation_history=conversation_history,
            other_hcp_questions=other_hcp_questions,
            prompt_config=_conference_prompt_config_from_session(session),
            base_template=conference_base_template,
        )

        coach_request = CoachRequest(
            session_id=session.id,
            message=mr_text,
            scenario_context=hcp_prompt,
            hcp_profile=hcp_config,
        )
        question_text, error = await _collect_coach_text(coach_request)
        if error:
            logger.warning(
                "generate_hcp_questions: LLM failed for session=%s hcp=%s: %s",
                session.id,
                hcp_config.get("hcp_profile_id"),
                error,
            )

        # Skip empty questions (HCP chose not to ask)
        question_text = _normalize_generated_text(question_text)
        if not question_text or question_text.lower() in ("", "none", "no question"):
            continue

        # Assign relevance score based on simple keyword matching (mock heuristic)
        relevance_score = _compute_relevance_score(question_text, mr_text)

        queued = QueuedQuestion(
            hcp_profile_id=hcp_config["hcp_profile_id"],
            hcp_name=hcp_config["name"],
            question=question_text,
            relevance_score=relevance_score,
            queued_at=datetime.now(UTC),
        )
        turn_manager.add_question(session.id, queued)
        generated_questions.append(queued)

        # Track for subsequent HCPs to avoid duplicates
        other_hcp_questions.append({"hcp_name": hcp_config["name"], "question": question_text})

    return generated_questions


async def _generate_next_hcp_question(
    db: AsyncSession, session: CoachingSession, mr_text: str
) -> QueuedQuestion | None:
    """Generate the next HCP question at the moment that HCP takes the floor."""
    audience_config = json.loads(session.audience_config or "[]")
    asking_hcps = [h for h in audience_config if h.get("role") != "moderator"]
    if not asking_hcps:
        return None
    asking_hcp_ids = {hcp.get("hcp_profile_id") for hcp in asking_hcps}

    msg_result = await db.execute(
        select(SessionMessage)
        .where(SessionMessage.session_id == session.id)
        .order_by(SessionMessage.message_index)
    )
    messages = list(msg_result.scalars().all())
    hcp_speakers_already_released = {
        msg.speaker_id
        for msg in messages
        if msg.role == "assistant" and msg.speaker_id in asking_hcp_ids
    }
    next_hcp = next(
        (
            hcp
            for hcp in asking_hcps
            if hcp.get("hcp_profile_id") not in hcp_speakers_already_released
        ),
        None,
    )
    if next_hcp is None:
        return None

    scenario_result = await db.execute(select(Scenario).where(Scenario.id == session.scenario_id))
    scenario = scenario_result.scalar_one_or_none()
    conversation_history = [
        {"role": msg.role, "content": msg.content, "speaker_name": msg.speaker_name}
        for msg in messages
    ]
    next_hcp_id = next_hcp.get("hcp_profile_id")
    other_hcp_questions = [
        {"hcp_name": msg.speaker_name or "HCP", "question": msg.content}
        for msg in messages
        if msg.role == "assistant"
        and msg.speaker_id in asking_hcp_ids
        and msg.speaker_id != next_hcp_id
    ]
    from app.services.prompt_registry import get_prompt

    conference_base_template = await get_prompt(db, "conference.audience")
    hcp_prompt = build_conference_audience_prompt(
        hcp_config=next_hcp,
        scenario=scenario,
        presentation_topic=session.presentation_topic or "",
        conversation_history=conversation_history,
        other_hcp_questions=other_hcp_questions,
        prompt_config=_conference_prompt_config_from_session(session),
        base_template=conference_base_template,
    )

    coach_request = CoachRequest(
        session_id=session.id,
        message=mr_text,
        scenario_context=hcp_prompt,
        hcp_profile=next_hcp,
    )
    question_text, error = await _collect_coach_text(coach_request)
    if error:
        logger.warning(
            "_generate_next_hcp_question: LLM failed for session=%s hcp=%s: %s",
            session.id,
            next_hcp.get("hcp_profile_id"),
            error,
        )
    if not question_text or question_text.lower() in ("", "none", "no question"):
        question_text = _fallback_hcp_question(next_hcp, mr_text)

    queued = QueuedQuestion(
        hcp_profile_id=next_hcp["hcp_profile_id"],
        hcp_name=next_hcp["name"],
        question=question_text,
        relevance_score=_compute_relevance_score(question_text, mr_text),
        queued_at=datetime.now(UTC),
    )
    turn_manager.add_question(session.id, queued)
    return queued


async def _generate_hcp_response_text(
    db: AsyncSession,
    session: CoachingSession,
    hcp_id: str,
    mr_response: str,
) -> tuple[str, str] | None:
    """Generate one contextual response from the current HCP."""
    audience_config = json.loads(session.audience_config or "[]")
    hcp_config = next((h for h in audience_config if h["hcp_profile_id"] == hcp_id), None)
    hcp_name = hcp_config["name"] if hcp_config else "HCP"

    scenario_result = await db.execute(select(Scenario).where(Scenario.id == session.scenario_id))
    scenario = scenario_result.scalar_one_or_none()

    msg_result = await db.execute(
        select(SessionMessage)
        .where(SessionMessage.session_id == session.id)
        .order_by(SessionMessage.message_index)
    )
    messages = list(msg_result.scalars().all())
    conversation_history = [
        {"role": msg.role, "content": msg.content, "speaker_name": msg.speaker_name}
        for msg in messages
    ]

    from app.services.prompt_registry import get_prompt

    conference_base_template = await get_prompt(db, "conference.audience")
    hcp_prompt = build_conference_audience_prompt(
        hcp_config=hcp_config or {},
        scenario=scenario,
        presentation_topic=session.presentation_topic or "",
        conversation_history=conversation_history,
        other_hcp_questions=[],
        prompt_config=_conference_prompt_config_from_session(session),
        base_template=conference_base_template,
    )

    coach_request = CoachRequest(
        session_id=session.id,
        message=mr_response,
        scenario_context=hcp_prompt,
        hcp_profile=hcp_config,
    )
    full_response, error = await _collect_coach_text(coach_request)
    if error:
        logger.warning(
            "_generate_hcp_response_text: LLM failed for session=%s hcp=%s: %s",
            session.id,
            hcp_id,
            error,
        )
        return None

    if not full_response or full_response.lower() in ("", "none", "no question"):
        logger.warning(
            "_generate_hcp_response_text: empty LLM response for session=%s hcp=%s",
            session.id,
            hcp_id,
        )
        return None

    return hcp_name, full_response


async def handle_respond(
    db: AsyncSession, session: CoachingSession, hcp_id: str, mr_response: str
) -> AsyncIterator[dict]:
    """Handle MR responding to the current HCP.

    The active HCP keeps the floor for multiple contextual follow-ups. The
    floor only moves to the next HCP after enough follow-ups, an explicit MR
    request to move on, or a clear closing response from the HCP.
    """
    active_question = turn_manager.get_active_speaker(session.id)
    if active_question is not None:
        if active_question.hcp_profile_id != hcp_id:
            yield {
                "event": "error",
                "data": json.dumps({"message": "Another HCP is currently active"}),
            }
            return
        activated = active_question
    else:
        activated = turn_manager.activate_question(session.id, hcp_id)
        if activated is None:
            yield {
                "event": "error",
                "data": json.dumps({"message": "No waiting question from this HCP"}),
            }
            return

    await _save_conference_message(db, session.id, "user", mr_response)

    should_move_before_followup = (
        _mr_requests_next_hcp(mr_response)
        or turn_manager.get_followup_count(session.id, hcp_id) >= HCP_FOLLOWUPS_BEFORE_NEXT
    )
    if should_move_before_followup:
        turn_manager.mark_answered(session.id, hcp_id)
        yield {
            "event": "turn_change",
            "data": json.dumps(
                {"speaker_id": hcp_id, "speaker_name": activated.hcp_name, "action": "listening"}
            ),
        }
        async for event_data in _release_next_hcp_or_close(db, session, mr_response):
            yield event_data
        return

    generated = await _generate_hcp_response_text(db, session, hcp_id, mr_response)
    if generated is None:
        turn_manager.mark_answered(session.id, hcp_id)
        yield {
            "event": "turn_change",
            "data": json.dumps(
                {"speaker_id": hcp_id, "speaker_name": activated.hcp_name, "action": "listening"}
            ),
        }
        async for event_data in _release_next_hcp_or_close(db, session, mr_response):
            yield event_data
        return
    hcp_name, full_response = generated

    yield {
        "event": "turn_change",
        "data": json.dumps({"speaker_id": hcp_id, "speaker_name": hcp_name, "action": "asking"}),
    }
    if full_response:
        yield {
            "event": "speaker_text",
            "data": json.dumps(
                {
                    "speaker_id": hcp_id,
                    "speaker_name": hcp_name,
                    "content": full_response,
                }
            ),
        }
    await _save_conference_message(
        db,
        session.id,
        "assistant",
        full_response,
        speaker_id=hcp_id,
        speaker_name=hcp_name,
    )

    turn_manager.increment_followup_count(session.id, hcp_id)
    should_release_next = _hcp_signals_done(full_response)

    yield {
        "event": "turn_change",
        "data": json.dumps({"speaker_id": hcp_id, "speaker_name": hcp_name, "action": "listening"}),
    }

    if should_release_next:
        turn_manager.mark_answered(session.id, hcp_id)
        async for event_data in _release_next_hcp_or_close(db, session, mr_response):
            yield event_data
        return

    yield {
        "event": "queue_update",
        "data": json.dumps(_serialize_queue(_current_queue_view(session.id))),
    }


async def _release_next_hcp_or_close(
    db: AsyncSession, session: CoachingSession, mr_text: str
) -> AsyncIterator[dict]:
    """Release the next HCP question, or close the Q&A if all HCPs are done."""
    audience_config = json.loads(session.audience_config or "[]")
    moderator = next((h for h in audience_config if h.get("role") == "moderator"), None)

    next_question = await _generate_next_hcp_question(db, session, mr_text)
    if next_question is not None:
        await asyncio.sleep(SPEAKER_PACING_SECONDS)
        if moderator is not None:
            async for event_data in _emit_moderator_remark(
                db, session, mr_text, moderator, "handoff"
            ):
                yield event_data
            await asyncio.sleep(SPEAKER_PACING_SECONDS)
        async for event_data in _emit_question_event(db, session, next_question):
            yield event_data
        yield {
            "event": "queue_update",
            "data": json.dumps(_serialize_queue(_current_queue_view(session.id))),
        }
        return

    if moderator is not None:
        await asyncio.sleep(SPEAKER_PACING_SECONDS)
        async for event_data in _emit_moderator_remark(db, session, mr_text, moderator, "closing"):
            yield event_data

    yield {
        "event": "queue_update",
        "data": json.dumps(_serialize_queue([])),
    }


async def transition_sub_state(db: AsyncSession, session_id: str, new_state: str) -> None:
    """Update conference session sub_state (presenting or qa)."""
    result = await db.execute(select(CoachingSession).where(CoachingSession.id == session_id))
    session = result.scalar_one_or_none()
    if session is None:
        raise NotFoundException("Session not found")
    session.sub_state = new_state
    await db.flush()


async def end_conference_session(
    db: AsyncSession, session_id: str, user_id: str
) -> CoachingSession:
    """End a conference session and cleanup turn_manager.

    Sets status to completed, calculates duration, and cleans up in-memory state.
    """
    result = await db.execute(select(CoachingSession).where(CoachingSession.id == session_id))
    session = result.scalar_one_or_none()
    if session is None:
        raise NotFoundException("Session not found")
    if session.user_id != user_id:
        raise AppException(
            status_code=403, code="FORBIDDEN", message="Session does not belong to this user"
        )
    if session.session_type != "conference":
        raise AppException(
            status_code=409,
            code="NOT_CONFERENCE_SESSION",
            message="Session is not a conference session",
        )
    if session.status not in ("created", "in_progress"):
        raise AppException(
            status_code=409,
            code="INVALID_STATUS",
            message=f"Cannot end session with status '{session.status}'",
        )

    now = utc_now_naive()
    session.status = "completed"
    session.completed_at = now
    if session.started_at:
        session.duration_seconds = int(
            (as_utc_aware(now) - as_utc_aware(session.started_at)).total_seconds()
        )

    # Cleanup turn_manager in-memory state
    turn_manager.cleanup_session(session_id)

    await db.flush()
    await db.refresh(session)

    return session


async def score_conference_session_background(session_id: str) -> None:
    """Score a completed conference session using an independent DB session."""
    from app.services.scoring_service import score_session

    async with AsyncSessionLocal() as db:
        try:
            await score_session(db, session_id)
            await db.commit()
        except AppException as exc:
            await db.rollback()
            logger.info(
                "Conference scoring skipped after session end: session_id=%s code=%s",
                session_id,
                exc.code,
            )
        except Exception:
            await db.rollback()
            logger.exception(
                "Conference scoring failed after session end: session_id=%s", session_id
            )


async def _save_conference_message(
    db: AsyncSession,
    session_id: str,
    role: str,
    content: str,
    speaker_id: str | None = None,
    speaker_name: str = "",
) -> SessionMessage:
    """Save a conference message with speaker attribution.

    Handles message_index counting and session state transitions.
    """
    count_result = await db.execute(
        select(func.count())
        .select_from(SessionMessage)
        .where(SessionMessage.session_id == session_id)
    )
    message_index = count_result.scalar_one()

    message = SessionMessage(
        session_id=session_id,
        role=role,
        content=content,
        message_index=message_index,
        speaker_id=speaker_id,
        speaker_name=speaker_name,
    )
    db.add(message)

    # Transition created -> in_progress on first user message
    if role == "user" and message_index == 0:
        result = await db.execute(select(CoachingSession).where(CoachingSession.id == session_id))
        session = result.scalar_one_or_none()
        if session and session.status == "created":
            session.status = "in_progress"
            session.started_at = utc_now_naive()

    await db.flush()
    return message


def _compute_relevance_score(question: str, mr_text: str) -> float:
    """Compute a simple relevance score based on keyword overlap (mock heuristic).

    Real implementation would use LLM-based scoring.
    """
    question_words = set(question.lower().split())
    mr_words = set(mr_text.lower().split())
    if not question_words or not mr_words:
        return 0.5
    overlap = len(question_words & mr_words)
    max_possible = min(len(question_words), len(mr_words))
    if max_possible == 0:
        return 0.5
    return round(0.3 + 0.7 * (overlap / max_possible), 2)


def _serialize_queue(queue: list[QueuedQuestion]) -> list[dict]:
    """Serialize question queue for SSE transmission."""
    return [
        {
            "hcp_profile_id": q.hcp_profile_id,
            "hcp_name": q.hcp_name,
            "question": q.question,
            "relevance_score": q.relevance_score,
            "status": q.status,
        }
        for q in queue
    ]
