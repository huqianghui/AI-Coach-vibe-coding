"""Tests for AzureOpenAIAdapter: streaming, error handling, conversation history, availability."""

from unittest.mock import AsyncMock, patch

from app.services.agents.adapters.azure_openai import AzureOpenAIAdapter
from app.services.agents.base import CoachEventType, CoachRequest


class _MockDelta:
    """Mock for streaming chunk delta."""

    def __init__(self, content: str | None = None) -> None:
        self.content = content


class _MockChoice:
    """Mock for streaming chunk choice."""

    def __init__(self, content: str | None = None) -> None:
        self.delta = _MockDelta(content)


class _MockChunk:
    """Mock for streaming completion chunk."""

    def __init__(self, content: str | None = None) -> None:
        self.choices = [_MockChoice(content)] if content is not None else []


class _MockAsyncStream:
    """Mock async iterator for streaming chat completions."""

    def __init__(self, chunks: list) -> None:
        self._chunks = chunks
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._index]
        self._index += 1
        return chunk


def _make_adapter(
    endpoint: str = "https://test.openai.azure.com",
    api_key: str = "test-key",
    deployment: str = "gpt-4o",
    api_version: str = "2024-06-01",
) -> AzureOpenAIAdapter:
    """Create an AzureOpenAIAdapter instance (uses real openai SDK for init)."""
    return AzureOpenAIAdapter(
        endpoint=endpoint,
        api_key=api_key,
        deployment=deployment,
        api_version=api_version,
    )


def _make_mock_client(chunks: list | None = None, error: Exception | None = None) -> AsyncMock:
    """Create a mock AsyncAzureOpenAI client."""
    mock_client = AsyncMock()
    if error:
        mock_client.chat.completions.create = AsyncMock(side_effect=error)
    else:
        mock_client.chat.completions.create = AsyncMock(return_value=_MockAsyncStream(chunks or []))
    return mock_client


def _set_mock_client(adapter: AzureOpenAIAdapter, mock_client) -> None:
    """Set a mock client on adapter, bypassing lazy init."""
    adapter._client = mock_client
    adapter._client_initialized = True


class TestAzureOpenAIAdapterStreaming:
    """Tests for AzureOpenAIAdapter.execute streaming."""

    async def test_execute_streaming(self):
        """Execute yields TEXT events for each streaming chunk and DONE at the end."""
        chunks = [
            _MockChunk("Hello "),
            _MockChunk("world"),
            _MockChunk(None),  # finish reason stop, empty choices content
        ]

        adapter = _make_adapter()
        _set_mock_client(adapter, _make_mock_client(chunks))

        request = CoachRequest(session_id="test-1", message="Hello doctor")
        events = []
        async for event in adapter.execute(request):
            events.append(event)

        # Should have TEXT events for "Hello " and "world", plus DONE
        text_events = [e for e in events if e.type == CoachEventType.TEXT]
        assert len(text_events) == 2
        assert text_events[0].content == "Hello "
        assert text_events[1].content == "world"

        # Last event should be DONE
        assert events[-1].type == CoachEventType.DONE

    async def test_execute_with_conversation_history(self):
        """Execute includes conversation_history in messages passed to API."""
        chunks = [_MockChunk("Response")]

        adapter = _make_adapter()
        mock_client = _make_mock_client(chunks)
        _set_mock_client(adapter, mock_client)

        history = [
            {"role": "user", "content": "prior msg"},
            {"role": "assistant", "content": "prior response"},
        ]
        request = CoachRequest(
            session_id="test-2",
            message="follow up",
            scenario_context="You are a doctor.",
            conversation_history=history,
        )

        events = []
        async for event in adapter.execute(request):
            events.append(event)

        # Verify messages passed to API include system, history, and user message
        call_kwargs = mock_client.chat.completions.create.call_args
        messages = call_kwargs.kwargs["messages"]

        # System message
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are a doctor."

        # History messages
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "prior msg"
        assert messages[2]["role"] == "assistant"
        assert messages[2]["content"] == "prior response"

        # Current user message
        assert messages[3]["role"] == "user"
        assert messages[3]["content"] == "follow up"

    async def test_execute_without_scenario_context(self):
        """Execute omits system message when scenario_context is empty."""
        chunks = [_MockChunk("Hi")]

        adapter = _make_adapter()
        mock_client = _make_mock_client(chunks)
        _set_mock_client(adapter, mock_client)

        request = CoachRequest(
            session_id="test-5",
            message="hello",
            scenario_context="",
        )

        events = []
        async for event in adapter.execute(request):
            events.append(event)

        call_kwargs = mock_client.chat.completions.create.call_args
        messages = call_kwargs.kwargs["messages"]

        # Should only have user message, no system message
        assert len(messages) == 1
        assert messages[0]["role"] == "user"

    async def test_execute_error_handling(self):
        """Execute yields ERROR then DONE when API raises exception."""
        adapter = _make_adapter()
        _set_mock_client(adapter, _make_mock_client(error=Exception("API down")))

        request = CoachRequest(session_id="test-3", message="hello")
        events = []
        async for event in adapter.execute(request):
            events.append(event)

        assert len(events) == 2
        assert events[0].type == CoachEventType.ERROR
        assert "Azure OpenAI error" in events[0].content
        assert "API down" in events[0].content
        assert events[1].type == CoachEventType.DONE

    async def test_execute_without_openai_client(self):
        """Execute yields ERROR when client is None (init failed)."""
        adapter = _make_adapter()

        request = CoachRequest(session_id="test-4", message="hello")
        events = []
        with patch(
            "app.services.azure_auth.get_azure_openai_client",
            new_callable=AsyncMock,
            side_effect=RuntimeError("no credentials"),
        ):
            async for event in adapter.execute(request):
                events.append(event)

        assert len(events) == 2
        assert events[0].type == CoachEventType.ERROR
        assert "not installed" in events[0].content or "credentials" in events[0].content
        assert events[1].type == CoachEventType.DONE

    async def test_client_initialization_retries_after_transient_failure(self):
        """A temporary credential failure does not disable the adapter for the process lifetime."""
        adapter = _make_adapter(api_key="")
        mock_client = _make_mock_client([_MockChunk("Recovered")])

        with patch(
            "app.services.azure_auth.get_azure_openai_client",
            new_callable=AsyncMock,
            side_effect=[RuntimeError("credential temporarily unavailable"), mock_client],
        ) as get_client:
            assert await adapter._ensure_client() is False
            assert adapter._client_initialized is False
            assert await adapter._ensure_client() is True

        assert get_client.await_count == 2
        assert adapter._client is mock_client

    async def test_execute_streaming_params(self):
        """Execute passes correct streaming parameters to API."""
        chunks = [_MockChunk("OK")]

        adapter = _make_adapter()
        mock_client = _make_mock_client(chunks)
        _set_mock_client(adapter, mock_client)

        request = CoachRequest(session_id="test-6", message="test")
        async for _ in adapter.execute(request):
            pass

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o"
        assert call_kwargs["stream"] is True
        assert call_kwargs["temperature"] == 0.7
        # Default is max_completion_tokens for newer models
        has_max = (
            call_kwargs.get("max_completion_tokens") == 1024
            or call_kwargs.get("max_tokens") == 1024
        )
        assert has_max


class TestAzureOpenAIAdapterAvailability:
    """Tests for AzureOpenAIAdapter.is_available."""

    async def test_is_available_true(self):
        """Adapter with endpoint, api_key, and deployment returns True."""
        adapter = _make_adapter()
        assert await adapter.is_available() is True

    async def test_is_available_false_missing_endpoint(self):
        """Adapter with empty endpoint returns False."""
        adapter = _make_adapter(endpoint="")
        assert await adapter.is_available() is False

    async def test_is_available_false_missing_key(self):
        """Adapter with empty api_key and no AAD credential returns False."""
        adapter = _make_adapter(api_key="")
        with patch(
            "app.services.azure_auth.get_bearer_token",
            new_callable=AsyncMock,
            return_value=None,
        ):
            assert await adapter.is_available() is False

    async def test_is_available_false_missing_deployment(self):
        """Adapter with empty deployment returns False."""
        adapter = _make_adapter(deployment="")
        assert await adapter.is_available() is False

    async def test_is_available_false_no_client(self):
        """Adapter with no api_key and no AAD credential returns False."""
        adapter = _make_adapter(api_key="")
        with patch(
            "app.services.azure_auth.get_bearer_token",
            new_callable=AsyncMock,
            return_value=None,
        ):
            assert await adapter.is_available() is False

    async def test_is_available_true_with_aad_only(self):
        """Adapter with no api_key but valid AAD credential returns True."""
        adapter = _make_adapter(api_key="")
        with patch(
            "app.services.azure_auth.get_bearer_token",
            new_callable=AsyncMock,
            return_value="fake-token",
        ):
            assert await adapter.is_available() is True


class TestAzureOpenAIAdapterVersion:
    """Tests for AzureOpenAIAdapter.get_version."""

    async def test_get_version(self):
        """Returns string containing 'azure-openai'."""
        adapter = _make_adapter()
        version = await adapter.get_version()
        assert version is not None
        assert "azure-openai" in version

    async def test_get_version_includes_api_version(self):
        """Version string includes the configured API version."""
        adapter = _make_adapter(api_version="2024-10-01")
        version = await adapter.get_version()
        assert version == "azure-openai-2024-10-01"

    async def test_get_version_default_api_version(self):
        """Default API version is reflected in version string."""
        adapter = _make_adapter()
        version = await adapter.get_version()
        assert version == "azure-openai-2024-06-01"


class TestAzureOpenAIAdapterName:
    """Tests for AzureOpenAIAdapter name attribute."""

    def test_adapter_name(self):
        """Adapter name is 'azure_openai'."""
        adapter = _make_adapter()
        assert adapter.name == "azure_openai"
