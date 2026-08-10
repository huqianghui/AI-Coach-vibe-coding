"""Agent chat service: send messages to AI Foundry Agents and get responses.

Uses the OpenAI-compatible client from azure-ai-projects SDK to chat with
agents via the Responses API. Chat sessions appear in Azure Portal's agent
playground under the agent's session list.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import agent_sync_service

logger = logging.getLogger(__name__)


class AgentChatError(RuntimeError):
    """Foundry Agent request failed or returned an invalid stream."""


@dataclass(frozen=True)
class AgentResponseEvent:
    """One ordered event from a Foundry Responses stream."""

    kind: Literal["text", "completed"]
    text: str = ""
    response_id: str | None = None


@dataclass(frozen=True, slots=True)
class SessionAgentResponse:
    """Known terminal result from one explicit-Conversation Session request."""

    text: str
    response_id: str
    iq_correlations: tuple[dict[str, str], ...]


def _validate_agent_reference(agent_name: str, agent_version: str) -> tuple[str, str]:
    """Validate an exact hosted Prompt Agent reference without substituting values."""
    name = agent_name.strip() if agent_name else ""
    version = agent_version.strip() if agent_version else ""
    if not name:
        raise AgentChatError("Agent name is required")
    if name.lower().startswith("asst_"):
        raise AgentChatError("Agent name must reference a hosted Prompt Agent")
    if not version:
        raise AgentChatError("Agent version is required")
    return name, version


async def _build_openai_request(
    db: AsyncSession,
    agent_name: str,
    agent_version: str,
    message: str,
    previous_response_id: str | None,
) -> tuple[object, dict, str]:
    """Resolve the configured client/model and construct exact Responses kwargs."""
    from app.config import get_settings
    from app.services import config_service

    name, version = _validate_agent_reference(agent_name, agent_version)
    project_endpoint, api_key = await agent_sync_service.get_project_endpoint(db)
    client = agent_sync_service._get_project_client(project_endpoint, api_key)
    master = await config_service.get_master_config(db)
    model = master.model_or_deployment if master else get_settings().voice_live_default_model
    kwargs: dict = {
        "model": model,
        "input": [{"role": "user", "content": message}],
        "extra_body": {
            "agent_reference": {
                "name": name,
                "version": version,
                "type": "agent_reference",
            }
        },
    }
    if previous_response_id:
        kwargs["previous_response_id"] = previous_response_id
    return client.get_openai_client(), kwargs, project_endpoint


async def _build_session_request(
    db: AsyncSession,
    agent_name: str,
    agent_version: str,
    conversation_id: str,
) -> tuple[object, dict[str, Any]]:
    """Construct the restricted exact-Agent request for a server-owned Conversation."""
    from app.config import get_settings
    from app.services import config_service

    if not conversation_id.strip():
        raise AgentChatError("Conversation ID is required")
    name, version = _validate_agent_reference(agent_name, agent_version)
    project_endpoint, api_key = await agent_sync_service.get_project_endpoint(db)
    project_client = agent_sync_service._get_project_client(project_endpoint, api_key)
    master = await config_service.get_master_config(db)
    model = master.model_or_deployment if master else get_settings().voice_live_default_model
    kwargs: dict[str, Any] = {
        "model": model,
        "conversation": conversation_id,
        "stream": True,
        "extra_body": {
            "agent_reference": {"name": name, "version": version, "type": "agent_reference"}
        },
    }
    return project_client.get_openai_client(), kwargs


def _iq_correlation(event: object) -> dict[str, str] | None:
    """Accept only a successful exact knowledge_base_retrieve MCP terminal event."""
    if getattr(event, "type", "") != "response.mcp_call.completed":
        return None
    item = getattr(event, "item", None) or getattr(event, "mcp_call", None) or event
    name = str(getattr(item, "name", "") or "")
    call_id = str(getattr(item, "id", "") or getattr(item, "call_id", "") or "")
    status = str(getattr(item, "status", "completed") or "")
    if (
        not call_id
        or name != "knowledge_base_retrieve"
        or status not in {"completed", "success", "succeeded"}
    ):
        return None
    return {"call_id": call_id, "name": name}


async def respond_in_session_conversation(
    db: AsyncSession,
    *,
    agent_name: str,
    agent_version: str,
    conversation_id: str,
    timeout: float = 60.0,
) -> SessionAgentResponse:
    """Stream one exact-Agent Response on an explicit Conversation.

    Developer and user items must already have been appended to the Conversation. This
    request intentionally has no instructions, previous_response_id, tools, or tool_choice.
    """
    client, kwargs = await _build_session_request(db, agent_name, agent_version, conversation_id)

    def produce() -> SessionAgentResponse:
        text: list[str] = []
        response_id = ""
        correlations: dict[str, dict[str, str]] = {}
        stream = client.responses.create(**kwargs)
        try:
            for event in stream:
                event_type = getattr(event, "type", "")
                if event_type == "response.output_text.delta":
                    text.append(str(getattr(event, "delta", "") or ""))
                elif event_type == "response.completed":
                    response = getattr(event, "response", None)
                    response_id = str(getattr(response, "id", "") or "")
                correlation = _iq_correlation(event)
                if correlation:
                    correlations[correlation["call_id"]] = correlation
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                close()
        if not response_id:
            raise AgentChatError("Agent stream ended without completion")
        return SessionAgentResponse("".join(text), response_id, tuple(correlations.values()))

    try:
        return await asyncio.wait_for(asyncio.to_thread(produce), timeout=timeout)
    except TimeoutError as exc:
        raise AgentChatError("Session Agent response outcome is unknown") from exc
    except AgentChatError:
        raise
    except Exception as exc:
        raise AgentChatError(f"Session Agent stream failed: {exc}") from exc


async def chat_with_agent(
    db: AsyncSession,
    agent_name: str,
    agent_version: str,
    message: str,
    previous_response_id: str | None = None,
) -> dict:
    """Send a message to an AI Foundry Agent and return the response.

    Uses project_client.get_openai_client() + responses.create() with
    agent_reference, matching Azure AI Foundry's agent chat pattern.

    The model parameter must match an actual deployment in the Azure project.
    We read it from the master config (model_or_deployment field).

    Args:
        db: Database session for config lookup.
        agent_name: The agent name (agent_id from HcpProfile).
        agent_version: The agent version string.
        message: User message to send.
        previous_response_id: Optional response ID for multi-turn conversation.

    Returns:
        Dict with response_text, response_id (for multi-turn), and agent info.
    """
    openai_client, kwargs, project_endpoint = await _build_openai_request(
        db, agent_name, agent_version, message, previous_response_id
    )

    logger.info(
        "chat_with_agent: endpoint=%s, agent=%s, version=%s, model=%s",
        project_endpoint,
        agent_name,
        agent_version,
        kwargs["model"],
    )

    try:
        response = openai_client.responses.create(**kwargs)
    except Exception as e:
        logger.error("chat_with_agent failed: agent=%s, error=%s", agent_name, e)
        raise AgentChatError(f"Agent chat failed: {e}") from e

    return {
        "response_text": response.output_text,
        "response_id": response.id,
        "agent_name": agent_name,
        "agent_version": agent_version,
    }


async def stream_agent_response(
    db: AsyncSession,
    agent_name: str,
    agent_version: str,
    message: str,
    previous_response_id: str | None = None,
) -> AsyncIterator[AgentResponseEvent]:
    """Stream an exact Foundry Prompt Agent response without blocking the event loop."""
    openai_client, kwargs, _ = await _build_openai_request(
        db, agent_name, agent_version, message, previous_response_id
    )
    kwargs["stream"] = True
    queue: asyncio.Queue[AgentResponseEvent | BaseException | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()
    stream_holder: list[object] = []

    def produce() -> None:
        try:
            stream = openai_client.responses.create(**kwargs)
            stream_holder.append(stream)
            for event in stream:
                event_type = getattr(event, "type", "")
                if event_type == "response.output_text.delta":
                    loop.call_soon_threadsafe(
                        queue.put_nowait,
                        AgentResponseEvent(kind="text", text=getattr(event, "delta", "")),
                    )
                elif event_type == "response.completed":
                    response = getattr(event, "response", None)
                    response_id = getattr(response, "id", None)
                    if not response_id:
                        raise AgentChatError("Agent stream completed without a response ID")
                    loop.call_soon_threadsafe(
                        queue.put_nowait,
                        AgentResponseEvent(kind="completed", response_id=response_id),
                    )
        except BaseException as exc:
            failure = (
                exc
                if isinstance(exc, AgentChatError)
                else AgentChatError(f"Agent stream failed: {exc}")
            )
            loop.call_soon_threadsafe(queue.put_nowait, failure)
        finally:
            if stream_holder:
                close = getattr(stream_holder[0], "close", None)
                if callable(close):
                    close()
            loop.call_soon_threadsafe(queue.put_nowait, None)

    worker = asyncio.create_task(asyncio.to_thread(produce))
    completed = False
    try:
        while True:
            item = await queue.get()
            if item is None:
                break
            if isinstance(item, BaseException):
                raise item
            if item.kind == "completed":
                completed = True
            yield item
        await worker
        if not completed:
            raise AgentChatError("Agent stream ended without completion")
    finally:
        if not worker.done():
            if stream_holder:
                close = getattr(stream_holder[0], "close", None)
                if callable(close):
                    await asyncio.to_thread(close)
            worker.cancel()
