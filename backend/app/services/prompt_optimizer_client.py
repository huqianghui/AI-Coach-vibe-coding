"""MCP client for the prompt-optimizer sidecar.

Wraps the optimizer's MCP tools (optimize-system-prompt / optimize-user-prompt /
iterate-prompt) behind a single async ``optimize_prompt`` coroutine. The optimizer runs
as an unmodified upstream AGPL image and is reached only over the internal compose network
via Streamable HTTP (JSON-RPC 2.0). No optimizer source is modified.
"""

from __future__ import annotations

from datetime import timedelta

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from app.config import get_settings

__all__ = ["optimize_prompt", "PromptOptimizerError"]

# mode -> MCP tool name
_TOOL_BY_MODE = {
    "system": "optimize-system-prompt",
    "user": "optimize-user-prompt",
    "iterate": "iterate-prompt",
}


class PromptOptimizerError(RuntimeError):
    """Raised when the prompt-optimizer sidecar returns an error or malformed result."""


def _build_arguments(
    prompt: str,
    mode: str,
    requirements: str | None,
    template: str | None,
) -> dict[str, str]:
    if mode == "iterate" and not requirements:
        raise PromptOptimizerError("mode=iterate requires non-empty requirements")

    arguments: dict[str, str] = {"prompt": prompt}
    if mode == "iterate":
        arguments["requirements"] = requirements or ""
    if template:
        arguments["template"] = template
    return arguments


def _extract_text(result) -> str:
    """Return the text of the first content block, raising on error/malformed results."""
    if getattr(result, "isError", False):
        raise PromptOptimizerError(f"prompt-optimizer returned an error: {result}")

    content = getattr(result, "content", None) or []
    for block in content:
        text = getattr(block, "text", None)
        if text is not None:
            return text
    raise PromptOptimizerError("prompt-optimizer returned no text content")


async def optimize_prompt(
    prompt: str,
    mode: str = "system",
    requirements: str | None = None,
    template: str | None = None,
    *,
    mcp_url: str | None = None,
    timeout_seconds: float | None = None,
) -> str:
    """Optimize ``prompt`` via the prompt-optimizer MCP sidecar and return optimized text.

    Args:
        prompt: The prompt text to optimize.
        mode: One of ``system``, ``user`` or ``iterate``.
        requirements: Required when ``mode`` is ``iterate`` (the change request).
        template: Optional optimizer template name.
        mcp_url: Override the configured MCP endpoint (mainly for tests).
        timeout_seconds: Override the configured request timeout.

    Raises:
        PromptOptimizerError: On unknown mode, missing requirements, or upstream failure.
    """
    if mode not in _TOOL_BY_MODE:
        raise PromptOptimizerError(f"unknown optimize mode: {mode!r}")

    settings = get_settings()
    url = mcp_url or settings.prompt_optimizer_mcp_url
    timeout = timeout_seconds or settings.prompt_optimizer_timeout_seconds

    arguments = _build_arguments(prompt, mode, requirements, template)
    tool_name = _TOOL_BY_MODE[mode]

    async with streamablehttp_client(url, timeout=timedelta(seconds=timeout)) as (
        read,
        write,
        _,
    ):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)

    return _extract_text(result)
