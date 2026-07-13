"""MCP client for the prompt-optimizer sidecar.

Wraps the optimizer's MCP tools (optimize-system-prompt / optimize-user-prompt /
iterate-prompt) behind a single async ``optimize_prompt`` coroutine. The optimizer runs
as an unmodified upstream AGPL image and is reached only over the internal compose network
via Streamable HTTP (JSON-RPC 2.0). No optimizer source is modified.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

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


def _extract_text(result: dict[str, Any]) -> str:
    """Return the text of the first content block, raising on error/malformed results."""
    if result.get("isError"):
        raise PromptOptimizerError(f"prompt-optimizer returned an error: {result}")

    content = result.get("content") or []
    for block in content:
        text = block.get("text") if isinstance(block, dict) else None
        if text is not None:
            return text
    raise PromptOptimizerError("prompt-optimizer returned no text content")


def _extract_jsonrpc_result(response: httpx.Response) -> dict[str, Any]:
    if response.status_code >= 400:
        raise PromptOptimizerError(
            f"prompt-optimizer HTTP {response.status_code}: {response.text[:300]}"
        )

    payload = _decode_jsonrpc_payload(response)
    if not isinstance(payload, dict):
        raise PromptOptimizerError("prompt-optimizer returned a non-object JSON-RPC response")
    if payload.get("error"):
        raise PromptOptimizerError(f"prompt-optimizer JSON-RPC error: {payload['error']}")

    result = payload.get("result")
    if not isinstance(result, dict):
        raise PromptOptimizerError("prompt-optimizer returned no JSON-RPC result object")
    return result


def _decode_jsonrpc_payload(response: httpx.Response) -> Any:
    try:
        return response.json()
    except json.JSONDecodeError:
        pass

    content_type = response.headers.get("content-type", "")
    if "text/event-stream" not in content_type:
        raise PromptOptimizerError(
            "prompt-optimizer returned non-JSON response: "
            f"content-type={content_type!r}, body={response.text[:300]!r}"
        )

    data_lines: list[str] = []
    for line in response.text.splitlines():
        if line.startswith("data:"):
            data = line.removeprefix("data:").strip()
            if data and data != "[DONE]":
                data_lines.append(data)

    if not data_lines:
        raise PromptOptimizerError("prompt-optimizer returned an empty SSE response")

    return json.loads("\n".join(data_lines))


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

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        init_response = await client.post(
            url,
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "ai-coach-backend", "version": "0.1.0"},
                },
            },
        )
        _extract_jsonrpc_result(init_response)
        session_id = init_response.headers.get("mcp-session-id")
        if not session_id:
            raise PromptOptimizerError("prompt-optimizer did not return mcp-session-id")

        session_headers = {**headers, "mcp-session-id": session_id}
        initialized_response = await client.post(
            url,
            headers=session_headers,
            json={
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            },
        )
        if initialized_response.status_code >= 400:
            raise PromptOptimizerError(
                "prompt-optimizer initialized notification failed: "
                f"HTTP {initialized_response.status_code} - {initialized_response.text[:300]}"
            )

        call_response = await client.post(
            url,
            headers=session_headers,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments,
                },
            },
        )

    return _extract_text(_extract_jsonrpc_result(call_response))
