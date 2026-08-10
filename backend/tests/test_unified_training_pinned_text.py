"""Pinned Foundry Prompt Agent transport tests for Unified Training text SSE."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.sessions import send_message
from app.schemas.session import SendMessageRequest
from app.services.agent_chat_service import AgentChatError, AgentResponseEvent
from app.utils.exceptions import AppException


async def _collect_sse(response) -> str:
    chunks = []
    async for chunk in response.body_iterator:
        if isinstance(chunk, bytes):
            chunks.append(chunk.decode())
        elif isinstance(chunk, dict):
            chunks.append(f"event: {chunk.get('event')}\ndata: {chunk.get('data')}\n\n")
        else:
            chunks.append(chunk)
    return "".join(chunks)


def _session(*, status="created", response_id=None):
    scenario = MagicMock()
    scenario.key_messages = json.dumps(["Superior PFS data"])
    return SimpleNamespace(
        id="session-1",
        status=status,
        scenario=scenario,
        skill_id=None,
        skill_version_id=None,
        agent_name="hcp-pinned-agent",
        agent_version="0042",
        agent_response_id=response_id,
        key_messages_status=json.dumps(
            [{"message": "Superior PFS data", "delivered": False, "detected_at": None}]
        ),
    )


@pytest.mark.asyncio
async def test_first_turn_uses_exact_pin_and_persists_terminal_continuation():
    """A completed first turn preserves text/key-message/hint/done behavior."""
    session = _session()
    db = AsyncMock()
    user = SimpleNamespace(id="owner-1")
    saved_roles = []

    async def save_message(_db, _session_id, role, content):
        saved_roles.append((role, content))

    stream_calls = []

    async def stream(_db, name, version, message, previous_response_id):
        stream_calls.append((name, version, message, previous_response_id))
        yield AgentResponseEvent(kind="text", text="Hello ")
        yield AgentResponseEvent(kind="text", text="doctor")
        yield AgentResponseEvent(kind="completed", response_id="resp-1")

    suggestion = SimpleNamespace(
        message="Mention the trial endpoint",
        type=SimpleNamespace(value="key_message"),
        trigger="missing",
        relevance_score=0.9,
    )
    with (
        patch("app.api.sessions.session_service.get_session", AsyncMock(return_value=session)),
        patch("app.api.sessions.session_service.save_message", side_effect=save_message),
        patch(
            "app.api.sessions.session_service.detect_key_messages",
            AsyncMock(return_value=json.loads(session.key_messages_status)),
        ),
        patch(
            "app.api.sessions.session_service.get_session_messages",
            AsyncMock(return_value=[]),
        ),
        patch("app.api.sessions.resolve_rubric_dimensions", AsyncMock(return_value=[])),
        patch("app.api.sessions.generate_suggestions", AsyncMock(return_value=[suggestion])),
        patch("app.api.sessions.stream_agent_response", stream),
    ):
        response = await send_message(
            "session-1", SendMessageRequest(message="Tell me about PFS"), db, user
        )
        body = await _collect_sse(response)

    assert stream_calls == [("hcp-pinned-agent", "0042", "Tell me about PFS", None)]
    assert saved_roles == [
        ("user", "Tell me about PFS"),
        ("assistant", "Hello doctor"),
    ]
    assert session.agent_response_id == "resp-1"
    assert "event: text" in body
    assert "event: key_messages" in body
    assert "event: hint" in body
    assert "event: done" in body
    assert "event: error" not in body
    db.flush.assert_awaited()


@pytest.mark.asyncio
async def test_second_turn_uses_existing_continuation_and_unchanged_pin():
    """The stored response ID and session pin are authoritative on later turns."""
    session = _session(status="in_progress", response_id="resp-1")
    session.scenario.hcp_profile.agent_id = "latest-agent"
    session.scenario.hcp_profile.agent_version = "99"
    calls = []

    async def stream(_db, name, version, message, previous_response_id):
        calls.append((name, version, previous_response_id))
        yield AgentResponseEvent(kind="completed", response_id="resp-2")

    with (
        patch("app.api.sessions.session_service.get_session", AsyncMock(return_value=session)),
        patch("app.api.sessions.session_service.save_message", AsyncMock()),
        patch(
            "app.api.sessions.session_service.detect_key_messages",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.api.sessions.session_service.get_session_messages",
            AsyncMock(return_value=[]),
        ),
        patch("app.api.sessions.resolve_rubric_dimensions", AsyncMock(return_value=[])),
        patch("app.api.sessions.generate_suggestions", AsyncMock(return_value=[])),
        patch("app.api.sessions.stream_agent_response", stream),
    ):
        response = await send_message(
            "session-1",
            SendMessageRequest(message="Follow up"),
            AsyncMock(),
            SimpleNamespace(id="owner-1"),
        )
        await _collect_sse(response)

    assert calls == [("hcp-pinned-agent", "0042", "resp-1")]
    assert session.agent_response_id == "resp-2"


@pytest.mark.asyncio
async def test_invalid_pin_rejects_before_message_or_azure():
    """Preflight pin validation runs before message persistence or Azure streaming."""
    session = _session()
    session.agent_version = " "
    save = AsyncMock()
    stream = MagicMock()

    with (
        patch("app.api.sessions.session_service.get_session", AsyncMock(return_value=session)),
        patch("app.api.sessions.session_service.save_message", save),
        patch("app.api.sessions.stream_agent_response", stream),
        pytest.raises(AppException) as exc_info,
    ):
        await send_message(
            "session-1",
            SendMessageRequest(message="Hello"),
            AsyncMock(),
            SimpleNamespace(id="owner-1"),
        )

    assert exc_info.value.code == "AGENT_PIN_MISSING"
    save.assert_not_awaited()
    stream.assert_not_called()


@pytest.mark.asyncio
async def test_upstream_failure_has_structured_error_and_preserves_state():
    """Partial Agent output is not persisted as a successful assistant turn."""
    session = _session(status="in_progress", response_id="resp-prior")
    save = AsyncMock()

    async def failing_stream(*_args):
        yield AgentResponseEvent(kind="text", text="partial")
        raise AgentChatError("Foundry unavailable")

    with (
        patch("app.api.sessions.session_service.get_session", AsyncMock(return_value=session)),
        patch("app.api.sessions.session_service.save_message", save),
        patch("app.api.sessions.resolve_rubric_dimensions", AsyncMock(return_value=[])),
        patch("app.api.sessions.stream_agent_response", failing_stream),
    ):
        response = await send_message(
            "session-1",
            SendMessageRequest(message="Hello"),
            AsyncMock(),
            SimpleNamespace(id="owner-1"),
        )
        body = await _collect_sse(response)

    assert save.await_args_list[0].args[2:] == ("user", "Hello")
    assert save.await_count == 1
    assert session.agent_response_id == "resp-prior"
    assert "event: error" in body
    assert "AGENT_RESPONSE_FAILED" in body
    assert "event: done" not in body


@pytest.mark.asyncio
async def test_stream_without_terminal_completion_preserves_state():
    """A stream that ends without completion cannot persist assistant state."""
    session = _session(status="in_progress", response_id="resp-prior")
    save = AsyncMock()

    async def incomplete_stream(*_args):
        yield AgentResponseEvent(kind="text", text="partial")

    with (
        patch("app.api.sessions.session_service.get_session", AsyncMock(return_value=session)),
        patch("app.api.sessions.session_service.save_message", save),
        patch("app.api.sessions.resolve_rubric_dimensions", AsyncMock(return_value=[])),
        patch("app.api.sessions.stream_agent_response", incomplete_stream),
    ):
        response = await send_message(
            "session-1",
            SendMessageRequest(message="Hello"),
            AsyncMock(),
            SimpleNamespace(id="owner-1"),
        )
        body = await _collect_sse(response)

    assert save.await_count == 1
    assert session.agent_response_id == "resp-prior"
    assert "AGENT_RESPONSE_INCOMPLETE" in body
    assert "event: done" not in body
