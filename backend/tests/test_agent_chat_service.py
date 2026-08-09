"""Unit + integration tests for agent_chat_service: real Agent chat via OpenAI Responses API."""

import os
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# --- Helper: mock master config for all mock tests ---


def _mock_master_config():
    """Return a mock master config with model_or_deployment."""
    cfg = MagicMock()
    cfg.model_or_deployment = "gpt-4o"
    return cfg


def _patch_config_service():
    """Patch config_service.get_master_config in agent_chat_service."""
    return patch(
        "app.services.config_service.get_master_config",
        new_callable=AsyncMock,
        return_value=_mock_master_config(),
    )


# --- Mock tests ---


@pytest.mark.asyncio
async def test_chat_with_agent_mock():
    """chat_with_agent calls openai_client.responses.create with correct params."""
    from app.services.agent_chat_service import chat_with_agent

    mock_response = MagicMock()
    mock_response.output_text = "Hello, I am Dr. Chen Wei."
    mock_response.id = "resp_mock_001"

    mock_openai_client = MagicMock()
    mock_openai_client.responses.create.return_value = mock_response

    mock_project_client = MagicMock()
    mock_project_client.get_openai_client.return_value = mock_openai_client

    mock_db = AsyncMock()

    with (
        patch(
            "app.services.agent_chat_service.agent_sync_service.get_project_endpoint",
            new_callable=AsyncMock,
            return_value=("https://foundry.test/api/projects/test-prj", "test-key"),
        ),
        patch(
            "app.services.agent_chat_service.agent_sync_service._get_project_client",
            return_value=mock_project_client,
        ),
        _patch_config_service(),
    ):
        result = await chat_with_agent(
            mock_db,
            agent_name="Dr-Chen-Wei",
            agent_version="1",
            message="Tell me about your practice.",
        )

    assert result["response_text"] == "Hello, I am Dr. Chen Wei."
    assert result["response_id"] == "resp_mock_001"
    assert result["agent_name"] == "Dr-Chen-Wei"
    assert result["agent_version"] == "1"

    # Verify correct API call
    call_kwargs = mock_openai_client.responses.create.call_args[1]
    assert call_kwargs["model"] == "gpt-4o"
    assert call_kwargs["input"] == [{"role": "user", "content": "Tell me about your practice."}]
    assert call_kwargs["extra_body"]["agent_reference"]["name"] == "Dr-Chen-Wei"
    assert call_kwargs["extra_body"]["agent_reference"]["version"] == "1"
    assert call_kwargs["extra_body"]["agent_reference"]["type"] == "agent_reference"


@pytest.mark.asyncio
async def test_chat_with_agent_multiturn_mock():
    """chat_with_agent passes previous_response_id for multi-turn conversation."""
    from app.services.agent_chat_service import chat_with_agent

    mock_response = MagicMock()
    mock_response.output_text = "Follow-up response."
    mock_response.id = "resp_mock_002"

    mock_openai_client = MagicMock()
    mock_openai_client.responses.create.return_value = mock_response

    mock_project_client = MagicMock()
    mock_project_client.get_openai_client.return_value = mock_openai_client

    mock_db = AsyncMock()

    with (
        patch(
            "app.services.agent_chat_service.agent_sync_service.get_project_endpoint",
            new_callable=AsyncMock,
            return_value=("https://foundry.test/api/projects/test-prj", "test-key"),
        ),
        patch(
            "app.services.agent_chat_service.agent_sync_service._get_project_client",
            return_value=mock_project_client,
        ),
        _patch_config_service(),
    ):
        result = await chat_with_agent(
            mock_db,
            agent_name="Dr-Li",
            agent_version="2",
            message="What about side effects?",
            previous_response_id="resp_mock_001",
        )

    assert result["response_text"] == "Follow-up response."
    assert result["response_id"] == "resp_mock_002"

    call_kwargs = mock_openai_client.responses.create.call_args[1]
    assert call_kwargs["previous_response_id"] == "resp_mock_001"


@pytest.mark.asyncio
async def test_chat_with_agent_error_mock():
    """chat_with_agent raises RuntimeError when API call fails."""
    from app.services.agent_chat_service import chat_with_agent

    mock_openai_client = MagicMock()
    mock_openai_client.responses.create.side_effect = Exception("API timeout")

    mock_project_client = MagicMock()
    mock_project_client.get_openai_client.return_value = mock_openai_client

    mock_db = AsyncMock()

    with (
        patch(
            "app.services.agent_chat_service.agent_sync_service.get_project_endpoint",
            new_callable=AsyncMock,
            return_value=("https://foundry.test/api/projects/test-prj", "test-key"),
        ),
        patch(
            "app.services.agent_chat_service.agent_sync_service._get_project_client",
            return_value=mock_project_client,
        ),
        _patch_config_service(),
    ):
        with pytest.raises(RuntimeError, match="Agent chat failed"):
            await chat_with_agent(
                mock_db,
                agent_name="Dr-Error",
                agent_version="1",
                message="Hello",
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("agent_name", "agent_version"),
    [("", "1"), ("   ", "1"), ("asst_legacy", "1"), ("Dr-Valid", ""), ("Dr-Valid", "   ")],
)
async def test_agent_reference_validation_fails_before_client_lookup(agent_name, agent_version):
    """Invalid hosted Agent references fail before any Azure/config call."""
    from app.services.agent_chat_service import AgentChatError, chat_with_agent

    endpoint = AsyncMock()
    with (
        patch(
            "app.services.agent_chat_service.agent_sync_service.get_project_endpoint",
            endpoint,
        ),
        pytest.raises(AgentChatError, match="Agent"),
    ):
        await chat_with_agent(
            AsyncMock(),
            agent_name=agent_name,
            agent_version=agent_version,
            message="Hello",
        )

    endpoint.assert_not_awaited()


@pytest.mark.asyncio
async def test_stream_agent_response_uses_exact_reference_and_orders_events():
    """Streaming preserves deltas and reports the actual terminal response ID."""
    from app.services.agent_chat_service import stream_agent_response

    delta_1 = MagicMock(type="response.output_text.delta", delta="Hello ")
    delta_2 = MagicMock(type="response.output_text.delta", delta="doctor")
    completed = MagicMock(type="response.completed")
    completed.response.id = "resp_stream_001"
    mock_stream = MagicMock()
    mock_stream.__iter__.return_value = iter([delta_1, delta_2, completed])
    mock_openai_client = MagicMock()
    mock_openai_client.responses.create.return_value = mock_stream
    mock_project_client = MagicMock()
    mock_project_client.get_openai_client.return_value = mock_openai_client

    with (
        patch(
            "app.services.agent_chat_service.agent_sync_service.get_project_endpoint",
            new_callable=AsyncMock,
            return_value=("https://foundry.test/api/projects/test-prj", "test-key"),
        ),
        patch(
            "app.services.agent_chat_service.agent_sync_service._get_project_client",
            return_value=mock_project_client,
        ),
        _patch_config_service(),
    ):
        events = [
            event
            async for event in stream_agent_response(
                AsyncMock(),
                agent_name="Dr-Exact",
                agent_version="0042",
                message="Hello",
                previous_response_id="resp_previous",
            )
        ]

    assert [(event.kind, event.text, event.response_id) for event in events] == [
        ("text", "Hello ", None),
        ("text", "doctor", None),
        ("completed", "", "resp_stream_001"),
    ]
    call_kwargs = mock_openai_client.responses.create.call_args.kwargs
    assert call_kwargs == {
        "model": "gpt-4o",
        "input": [{"role": "user", "content": "Hello"}],
        "extra_body": {
            "agent_reference": {
                "name": "Dr-Exact",
                "version": "0042",
                "type": "agent_reference",
            }
        },
        "previous_response_id": "resp_previous",
        "stream": True,
    }
    mock_stream.close.assert_called_once()


@pytest.mark.asyncio
async def test_stream_agent_response_translates_upstream_failure_without_completion():
    """An iterator failure is surfaced once and cannot fabricate completion."""
    from app.services.agent_chat_service import AgentChatError, stream_agent_response

    class FailingStream:
        def __iter__(self):
            yield MagicMock(type="response.output_text.delta", delta="partial")
            raise ValueError("upstream broke")

        def close(self):
            self.closed = True

    stream = FailingStream()
    mock_openai_client = MagicMock()
    mock_openai_client.responses.create.return_value = stream
    mock_project_client = MagicMock()
    mock_project_client.get_openai_client.return_value = mock_openai_client

    with (
        patch(
            "app.services.agent_chat_service.agent_sync_service.get_project_endpoint",
            new_callable=AsyncMock,
            return_value=("https://foundry.test/api/projects/test-prj", "test-key"),
        ),
        patch(
            "app.services.agent_chat_service.agent_sync_service._get_project_client",
            return_value=mock_project_client,
        ),
        _patch_config_service(),
    ):
        iterator = stream_agent_response(AsyncMock(), "Dr-Exact", "2", "Hello").__aiter__()
        first = await anext(iterator)
        assert first.kind == "text"
        assert first.text == "partial"
        with pytest.raises(AgentChatError, match="upstream broke"):
            await anext(iterator)

    assert stream.closed is True


@pytest.mark.asyncio
async def test_stream_agent_response_rejects_completion_without_response_id():
    """A malformed terminal event cannot be treated as successful completion."""
    from app.services.agent_chat_service import AgentChatError, stream_agent_response

    completed = MagicMock(type="response.completed")
    completed.response.id = None
    mock_stream = MagicMock()
    mock_stream.__iter__.return_value = iter([completed])
    mock_openai_client = MagicMock()
    mock_openai_client.responses.create.return_value = mock_stream
    mock_project_client = MagicMock()
    mock_project_client.get_openai_client.return_value = mock_openai_client

    with (
        patch(
            "app.services.agent_chat_service.agent_sync_service.get_project_endpoint",
            new_callable=AsyncMock,
            return_value=("https://foundry.test/api/projects/test-prj", "test-key"),
        ),
        patch(
            "app.services.agent_chat_service.agent_sync_service._get_project_client",
            return_value=mock_project_client,
        ),
        _patch_config_service(),
        pytest.raises(AgentChatError, match="without a response ID"),
    ):
        async for _ in stream_agent_response(AsyncMock(), "Dr-Exact", "2", "Hello"):
            pass

    assert mock_stream.close.call_count >= 1


@pytest.mark.asyncio
async def test_stream_agent_response_rejects_clean_end_without_completion():
    """A stream ending after non-terminal events cannot fabricate completion."""
    from app.services.agent_chat_service import AgentChatError, stream_agent_response

    mock_stream = MagicMock()
    mock_stream.__iter__.return_value = iter([MagicMock(type="response.created")])
    mock_openai_client = MagicMock()
    mock_openai_client.responses.create.return_value = mock_stream
    mock_project_client = MagicMock()
    mock_project_client.get_openai_client.return_value = mock_openai_client

    with (
        patch(
            "app.services.agent_chat_service.agent_sync_service.get_project_endpoint",
            new_callable=AsyncMock,
            return_value=("https://foundry.test/api/projects/test-prj", "test-key"),
        ),
        patch(
            "app.services.agent_chat_service.agent_sync_service._get_project_client",
            return_value=mock_project_client,
        ),
        _patch_config_service(),
        pytest.raises(AgentChatError, match="ended without completion"),
    ):
        async for _ in stream_agent_response(AsyncMock(), "Dr-Exact", "2", "Hello"):
            pass


@pytest.mark.asyncio
async def test_stream_agent_response_closes_worker_when_consumer_stops_early():
    """Closing the async iterator also closes and cancels a pending worker."""
    from app.services.agent_chat_service import stream_agent_response

    release_worker = threading.Event()

    class BlockingStream:
        closed = False

        def __iter__(self):
            yield MagicMock(type="response.output_text.delta", delta="partial")
            release_worker.wait(timeout=5)

        def close(self):
            self.closed = True
            release_worker.set()

    stream = BlockingStream()
    mock_openai_client = MagicMock()
    mock_openai_client.responses.create.return_value = stream
    mock_project_client = MagicMock()
    mock_project_client.get_openai_client.return_value = mock_openai_client

    with (
        patch(
            "app.services.agent_chat_service.agent_sync_service.get_project_endpoint",
            new_callable=AsyncMock,
            return_value=("https://foundry.test/api/projects/test-prj", "test-key"),
        ),
        patch(
            "app.services.agent_chat_service.agent_sync_service._get_project_client",
            return_value=mock_project_client,
        ),
        _patch_config_service(),
    ):
        iterator = stream_agent_response(AsyncMock(), "Dr-Exact", "2", "Hello").__aiter__()
        assert (await anext(iterator)).text == "partial"
        await iterator.aclose()

    assert stream.closed is True


@pytest.mark.asyncio
async def test_session_conversation_response_has_restricted_shape_and_exact_iq_correlation():
    """Session API uses explicit Conversation and deduplicates exact successful IQ calls."""
    from app.services.agent_chat_service import respond_in_session_conversation

    delta = MagicMock(type="response.output_text.delta", delta="current step")
    iq = MagicMock(type="response.mcp_call.completed")
    iq.item.name = "knowledge_base_retrieve"
    iq.item.id = "call-1"
    iq.item.status = "completed"
    wrong = MagicMock(type="response.mcp_call.completed")
    wrong.item.name = "other_tool"
    wrong.item.id = "call-2"
    wrong.item.status = "completed"
    failed = MagicMock(type="response.mcp_call.completed")
    failed.item.name = "knowledge_base_retrieve"
    failed.item.id = "call-3"
    failed.item.status = "failed"
    blank = MagicMock(type="response.mcp_call.completed")
    blank.item.name = "knowledge_base_retrieve"
    blank.item.id = ""
    blank.item.call_id = ""
    blank.item.status = "completed"
    completed = MagicMock(type="response.completed")
    completed.response.id = "resp-session"
    stream = MagicMock()
    stream.__iter__.return_value = iter([delta, iq, iq, wrong, failed, blank, completed])
    openai_client = MagicMock()
    openai_client.responses.create.return_value = stream
    project_client = MagicMock()
    project_client.get_openai_client.return_value = openai_client

    with (
        patch(
            "app.services.agent_chat_service.agent_sync_service.get_project_endpoint",
            new_callable=AsyncMock,
            return_value=("https://foundry.test/api/projects/test-prj", "test-key"),
        ),
        patch(
            "app.services.agent_chat_service.agent_sync_service._get_project_client",
            return_value=project_client,
        ),
        _patch_config_service(),
    ):
        result = await respond_in_session_conversation(
            AsyncMock(),
            agent_name="Dr-Exact",
            agent_version="5",
            conversation_id="conv-1",
        )

    assert result.text == "current step"
    assert result.response_id == "resp-session"
    assert result.iq_correlations == ({"call_id": "call-1", "name": "knowledge_base_retrieve"},)
    assert openai_client.responses.create.call_args.kwargs == {
        "model": "gpt-4o",
        "conversation": "conv-1",
        "stream": True,
        "extra_body": {
            "agent_reference": {
                "name": "Dr-Exact",
                "version": "5",
                "type": "agent_reference",
            }
        },
    }
    forbidden = {"instructions", "previous_response_id", "tools", "tool_choice"}
    assert forbidden.isdisjoint(openai_client.responses.create.call_args.kwargs)


@pytest.mark.asyncio
async def test_session_conversation_response_rejects_missing_id_and_requires_conversation():
    """Session API fails closed for absent authority or malformed terminal streams."""
    from app.services.agent_chat_service import AgentChatError, respond_in_session_conversation

    with pytest.raises(AgentChatError, match="Conversation ID"):
        await respond_in_session_conversation(
            AsyncMock(), agent_name="Dr", agent_version="1", conversation_id=" "
        )


@pytest.mark.asyncio
async def test_standalone_request_contract_does_not_gain_conversation_semantics():
    """Standalone chat retains previous_response_id and user input semantics."""
    from app.services.agent_chat_service import chat_with_agent

    response = MagicMock(output_text="ok", id="resp-new")
    openai_client = MagicMock()
    openai_client.responses.create.return_value = response
    project_client = MagicMock()
    project_client.get_openai_client.return_value = openai_client
    with (
        patch(
            "app.services.agent_chat_service.agent_sync_service.get_project_endpoint",
            new_callable=AsyncMock,
            return_value=("endpoint", "key"),
        ),
        patch(
            "app.services.agent_chat_service.agent_sync_service._get_project_client",
            return_value=project_client,
        ),
        _patch_config_service(),
    ):
        await chat_with_agent(AsyncMock(), "Dr", "1", "hello", "resp-old")
    kwargs = openai_client.responses.create.call_args.kwargs
    assert kwargs["previous_response_id"] == "resp-old"
    assert kwargs["input"] == [{"role": "user", "content": "hello"}]
    assert "conversation" not in kwargs


# ===========================================================================
# Real Azure integration tests — use actual .env credentials when available
# ===========================================================================


def _get_real_azure_config() -> tuple[str, str, str]:
    """Read Azure AI Foundry config from .env."""
    from dotenv import load_dotenv

    load_dotenv()
    endpoint = os.getenv("AZURE_FOUNDRY_ENDPOINT", "").rstrip("/")
    api_key = os.getenv("AZURE_FOUNDRY_API_KEY", "")
    project = os.getenv("AZURE_FOUNDRY_DEFAULT_PROJECT", "")
    return endpoint, api_key, project


def _get_real_deployment_model() -> str:
    """Read the actual deployment model name from .env.

    Checks AZURE_OPENAI_DEPLOYMENT first, then VOICE_LIVE_DEFAULT_MODEL,
    falls back to gpt-4o.
    """
    from dotenv import load_dotenv

    load_dotenv()
    return os.getenv("AZURE_OPENAI_DEPLOYMENT") or os.getenv("VOICE_LIVE_DEFAULT_MODEL") or "gpt-4o"


def _has_real_azure_config() -> bool:
    endpoint, api_key, project = _get_real_azure_config()
    return bool(endpoint and api_key and project)


_skip_no_creds = pytest.mark.skipif(
    not _has_real_azure_config(),
    reason="No Azure AI Foundry credentials in .env",
)

# Track agents created for cleanup
_created_agents: list[str] = []


@_skip_no_creds
@pytest.mark.asyncio
async def test_real_chat_with_existing_agent():
    """[REAL] Create an agent, then chat with it using the Responses API.

    This verifies the full flow:
    1. Create agent via Agent Registry API
    2. Chat with agent via openai_client.responses.create + agent_reference
    3. Verify response is non-empty
    4. Cleanup: delete the agent
    """
    from app.services.agent_sync_service import (
        _get_project_client,
        _sanitize_agent_name,
        build_agent_instructions,
    )

    endpoint, api_key, project = _get_real_azure_config()
    model = _get_real_deployment_model()
    project_endpoint = f"{endpoint}/api/projects/{project}"
    client = _get_project_client(project_endpoint, api_key)

    # Step 1: Create a test agent with the ACTUAL deployment model
    from azure.ai.projects.models import PromptAgentDefinition

    agent_name = _sanitize_agent_name("UT-Chat-Dr-Chen")
    instructions = build_agent_instructions(
        {
            "name": "UT-Chat-Dr-Chen",
            "specialty": "Oncology",
            "hospital": "Test Hospital",
            "title": "Physician",
            "personality_type": "friendly",
            "emotional_state": 30,
            "communication_style": 60,
            "expertise_areas": ["testing"],
            "prescribing_habits": "N/A",
            "concerns": "test",
            "objections": ["none"],
            "probe_topics": ["test"],
        }
    )

    definition = PromptAgentDefinition(model=model, instructions=instructions)
    create_result = client.agents.create_version(
        agent_name=agent_name,
        definition=definition,
        description="Unit test chat agent — safe to delete",
    )
    _created_agents.append(create_result.name)
    print(f"  Created agent: {create_result.name} v{create_result.version} (model={model})")

    # Step 2: Chat with the agent using OpenAI Responses API
    openai_client = client.get_openai_client()

    response = openai_client.responses.create(
        model=model,
        input=[{"role": "user", "content": "Hello doctor, tell me about your specialty."}],
        extra_body={
            "agent_reference": {
                "name": create_result.name,
                "version": str(create_result.version),
                "type": "agent_reference",
            }
        },
    )

    print(f"  Response ID: {response.id}")
    print(f"  Response text: {response.output_text[:200]}")

    # Verify response
    assert response.id, "Response ID must not be empty"
    assert response.output_text, "Response text must not be empty"
    assert len(response.output_text) > 10, "Response should have substantial content"

    # Step 3: Multi-turn — send a follow-up
    response2 = openai_client.responses.create(
        model=model,
        input=[{"role": "user", "content": "What treatments do you recommend?"}],
        previous_response_id=response.id,
        extra_body={
            "agent_reference": {
                "name": create_result.name,
                "version": str(create_result.version),
                "type": "agent_reference",
            }
        },
    )

    print(f"  Follow-up response: {response2.output_text[:200]}")
    assert response2.output_text, "Follow-up response must not be empty"
    assert response2.id != response.id, "Follow-up should have a different response ID"


@_skip_no_creds
@pytest.mark.asyncio
async def test_real_chat_cleanup():
    """[REAL] Cleanup: delete agents created during chat tests."""
    from app.services.agent_sync_service import _get_project_client

    endpoint, api_key, project = _get_real_azure_config()
    project_endpoint = f"{endpoint}/api/projects/{project}"
    client = _get_project_client(project_endpoint, api_key)

    deleted = 0
    for agent_name in _created_agents:
        try:
            client.agents.delete(agent_name=agent_name)
            deleted += 1
        except Exception as e:
            print(f"  Cleanup: could not delete {agent_name}: {e}")

    print(f"  Cleanup: deleted {deleted}/{len(_created_agents)} test agents")
    _created_agents.clear()


# ===========================================================================
# Real integration tests for the chat_with_agent() SERVICE FUNCTION
# ===========================================================================
# The tests above call the Azure API directly (bypassing the service layer).
# The tests below exercise the actual chat_with_agent() function end-to-end,
# patching only the DB config lookup (since we don't have a real DB in tests)
# but keeping all Azure API calls real.
# ===========================================================================


class TestRealAgentChatService:
    """[REAL] Integration tests for the chat_with_agent() service function.

    These tests create a real agent on Azure AI Foundry, then call the
    chat_with_agent() service function with real Azure credentials.
    Only the DB config layer is patched (get_project_endpoint, get_master_config).
    """

    _agent_name: str = ""
    _agent_version: str = ""

    @staticmethod
    def _build_config_patches():
        """Build context managers that patch DB-dependent config lookups."""
        endpoint, api_key, project = _get_real_azure_config()
        project_endpoint = f"{endpoint}/api/projects/{project}"
        model = _get_real_deployment_model()

        mock_master = MagicMock()
        mock_master.model_or_deployment = model

        patch_endpoint = patch(
            "app.services.agent_chat_service.agent_sync_service.get_project_endpoint",
            new_callable=AsyncMock,
            return_value=(project_endpoint, api_key),
        )
        patch_config = patch(
            "app.services.config_service.get_master_config",
            new_callable=AsyncMock,
            return_value=mock_master,
        )
        return patch_endpoint, patch_config

    @_skip_no_creds
    @pytest.mark.asyncio
    async def test_real_service_setup_agent(self):
        """[REAL] Create a test agent for service-level chat tests."""
        from app.services.agent_sync_service import (
            _get_project_client,
            _sanitize_agent_name,
            build_agent_instructions,
        )

        endpoint, api_key, project = _get_real_azure_config()
        model = _get_real_deployment_model()
        project_endpoint = f"{endpoint}/api/projects/{project}"
        client = _get_project_client(project_endpoint, api_key)

        from azure.ai.projects.models import PromptAgentDefinition

        agent_name = _sanitize_agent_name("UT-SvcChat-Dr-Wang")
        instructions = build_agent_instructions(
            {
                "name": "UT-SvcChat-Dr-Wang",
                "specialty": "Cardiology",
                "hospital": "Service Test Hospital",
                "title": "Chief Physician",
                "personality_type": "professional",
                "emotional_state": 50,
                "communication_style": 70,
                "expertise_areas": ["interventional cardiology"],
                "prescribing_habits": "evidence-based",
                "concerns": "patient outcomes",
                "objections": ["cost concerns"],
                "probe_topics": ["new therapies"],
            }
        )

        definition = PromptAgentDefinition(model=model, instructions=instructions)
        result = client.agents.create_version(
            agent_name=agent_name,
            definition=definition,
            description="Service-level chat test agent — safe to delete",
        )

        TestRealAgentChatService._agent_name = result.name
        TestRealAgentChatService._agent_version = str(result.version)
        _created_agents.append(result.name)

        print(f"  Created service test agent: {result.name} v{result.version}")
        assert result.name, "Agent name must not be empty"

    @_skip_no_creds
    @pytest.mark.asyncio
    async def test_real_service_single_turn(self):
        """[REAL] chat_with_agent() single-turn with real Azure API."""
        if not TestRealAgentChatService._agent_name:
            pytest.skip("Agent not created (setup test may have been skipped)")

        from app.services.agent_chat_service import chat_with_agent

        mock_db = AsyncMock()
        patch_endpoint, patch_config = self._build_config_patches()

        with patch_endpoint, patch_config:
            result = await chat_with_agent(
                mock_db,
                agent_name=TestRealAgentChatService._agent_name,
                agent_version=TestRealAgentChatService._agent_version,
                message="Hello doctor, what is your medical specialty?",
            )

        print(f"  Service single-turn response: {result['response_text'][:200]}")

        # Verify service function returns correct structure
        assert result["response_text"], "response_text must not be empty"
        assert result["response_id"], "response_id must not be empty"
        assert result["agent_name"] == TestRealAgentChatService._agent_name
        assert result["agent_version"] == TestRealAgentChatService._agent_version
        assert len(result["response_text"]) > 5, "Response should have substantial content"

        # Store for multi-turn test
        TestRealAgentChatService._last_response_id = result["response_id"]

    @_skip_no_creds
    @pytest.mark.asyncio
    async def test_real_service_multi_turn(self):
        """[REAL] chat_with_agent() multi-turn with previous_response_id."""
        if not TestRealAgentChatService._agent_name:
            pytest.skip("Agent not created (setup test may have been skipped)")
        if not getattr(TestRealAgentChatService, "_last_response_id", ""):
            pytest.skip("Single-turn test did not run")

        from app.services.agent_chat_service import chat_with_agent

        mock_db = AsyncMock()
        patch_endpoint, patch_config = self._build_config_patches()

        with patch_endpoint, patch_config:
            result = await chat_with_agent(
                mock_db,
                agent_name=TestRealAgentChatService._agent_name,
                agent_version=TestRealAgentChatService._agent_version,
                message="Can you tell me more about the treatments you typically recommend?",
                previous_response_id=TestRealAgentChatService._last_response_id,
            )

        print(f"  Service multi-turn response: {result['response_text'][:200]}")

        assert result["response_text"], "Multi-turn response_text must not be empty"
        assert result["response_id"], "Multi-turn response_id must not be empty"
        assert result["response_id"] != TestRealAgentChatService._last_response_id, (
            "Follow-up should produce a different response_id"
        )
        assert result["agent_name"] == TestRealAgentChatService._agent_name
        assert result["agent_version"] == TestRealAgentChatService._agent_version

    @_skip_no_creds
    @pytest.mark.asyncio
    async def test_real_service_cleanup(self):
        """[REAL] Cleanup: delete agents created by service-level tests."""
        from app.services.agent_sync_service import _get_project_client

        endpoint, api_key, project = _get_real_azure_config()
        project_endpoint = f"{endpoint}/api/projects/{project}"
        client = _get_project_client(project_endpoint, api_key)

        deleted = 0
        # Clean up any agents this class created (tracked in _created_agents)
        to_remove = []
        for name in _created_agents:
            if "SvcChat" in name or "svcchat" in name.lower():
                try:
                    client.agents.delete(agent_name=name)
                    deleted += 1
                    to_remove.append(name)
                except Exception as e:
                    print(f"  Service cleanup: could not delete {name}: {e}")

        for name in to_remove:
            _created_agents.remove(name)

        print(f"  Service cleanup: deleted {deleted} test agents")
