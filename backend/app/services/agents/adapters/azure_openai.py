"""Azure OpenAI adapter for streaming LLM chat completions."""

from collections.abc import AsyncIterator

from app.services.agents.base import (
    BaseCoachingAdapter,
    CoachEvent,
    CoachEventType,
    CoachRequest,
)


class AzureOpenAIAdapter(BaseCoachingAdapter):
    """Azure OpenAI adapter wrapping AsyncAzureOpenAI for streaming chat completions.

    Uses the openai SDK with Azure configuration to provide real AI-powered
    coaching conversations. Supports multi-turn dialogue via conversation_history
    and streams responses as TEXT events.

    Authentication: Uses centralized azure_auth module (AAD token first, API key fallback).
    """

    name = "azure_openai"

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        deployment: str,
        api_version: str = "2024-06-01",
    ) -> None:
        self._endpoint = endpoint
        self._api_key = api_key
        self._deployment = deployment
        self._api_version = api_version
        self._client = None
        self._client_initialized = False
        # Tracks which token limit param this deployment accepts.
        # None = not yet probed; True = max_completion_tokens; False = max_tokens
        self._use_max_completion_tokens: bool | None = None

    async def _ensure_client(self) -> bool:
        """Lazily initialize the AsyncAzureOpenAI client using centralized auth.

        Returns True if client is ready, False otherwise.
        """
        if self._client is not None:
            return True

        try:
            from app.services.azure_auth import get_azure_openai_client

            self._client = await get_azure_openai_client(
                endpoint=self._endpoint,
                api_key=self._api_key,
                api_version=self._api_version,
            )
            self._client_initialized = True
            return True
        except ImportError:
            self._client = None
            self._client_initialized = False
            return False
        except RuntimeError:
            self._client = None
            self._client_initialized = False
            return False

    def _token_limit_kwargs(self, limit: int) -> dict:
        """Return the correct token limit kwarg for the current deployment.

        Newer models (gpt-4o, gpt-5.4-mini, o1, o3) require max_completion_tokens.
        Older models (gpt-4, gpt-35-turbo) require max_tokens.
        """
        if self._use_max_completion_tokens is False:
            return {"max_tokens": limit}
        return {"max_completion_tokens": limit}

    async def execute(self, request: CoachRequest) -> AsyncIterator[CoachEvent]:
        """Execute a coaching interaction via Azure OpenAI streaming chat completion."""
        if not await self._ensure_client():
            yield CoachEvent(
                type=CoachEventType.ERROR,
                content="Azure OpenAI error: openai not installed or no credentials",
            )
            yield CoachEvent(type=CoachEventType.DONE, content="")
            return

        try:
            # Build messages array
            messages: list[dict[str, str]] = []

            # System prompt from scenario context
            if request.scenario_context:
                messages.append({"role": "system", "content": request.scenario_context})

            # Include conversation history for multi-turn dialogue
            if request.conversation_history:
                messages.extend(request.conversation_history)

            # Current user message
            messages.append({"role": "user", "content": request.message})

            # Stream chat completion with auto-detection of token limit param
            try:
                stream = await self._client.chat.completions.create(
                    model=self._deployment,
                    messages=messages,
                    stream=True,
                    temperature=0.7,
                    **self._token_limit_kwargs(1024),
                )
            except Exception as param_err:
                # If the param was rejected, flip and retry once
                err_msg = str(param_err)
                if "max_completion_tokens" in err_msg or "max_tokens" in err_msg:
                    self._use_max_completion_tokens = not (
                        self._use_max_completion_tokens is not False
                    )
                    stream = await self._client.chat.completions.create(
                        model=self._deployment,
                        messages=messages,
                        stream=True,
                        temperature=0.7,
                        **self._token_limit_kwargs(1024),
                    )
                else:
                    raise

            # If we got here, remember which param worked
            if self._use_max_completion_tokens is None:
                self._use_max_completion_tokens = True

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield CoachEvent(
                        type=CoachEventType.TEXT,
                        content=chunk.choices[0].delta.content,
                    )

            yield CoachEvent(type=CoachEventType.DONE, content="")

        except Exception as e:
            yield CoachEvent(
                type=CoachEventType.ERROR,
                content=f"Azure OpenAI error: {e!s}",
            )
            yield CoachEvent(type=CoachEventType.DONE, content="")

    async def is_available(self) -> bool:
        """Check if Azure OpenAI endpoint, key, and deployment are configured."""
        if not (self._endpoint and self._deployment):
            return False
        # Need either api_key or the ability to get AAD token
        if self._api_key:
            return True
        # Try to check if AAD credential is available
        try:
            from app.services.azure_auth import get_bearer_token

            token = await get_bearer_token()
            return token is not None
        except Exception:
            return False

    async def get_version(self) -> str | None:
        """Get adapter version info."""
        return f"azure-openai-{self._api_version}"
