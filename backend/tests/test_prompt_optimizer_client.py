"""Unit tests for prompt_optimizer_client (no live sidecar; MCP is mocked)."""

import pytest

import app.services.prompt_optimizer_client as opt
from app.services.prompt_optimizer_client import PromptOptimizerError, optimize_prompt


class _Block:
    def __init__(self, text):
        self.text = text


class _Result:
    def __init__(self, content, is_error=False):
        self.content = content
        self.isError = is_error


class _FakeStream:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return (None, None, None)

    async def __aexit__(self, *args):
        return False


class _FakeSession:
    """Records the last call_tool invocation; returns a preset result."""

    result = _Result([_Block("OPTIMIZED")])
    last_call = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def initialize(self):
        return None

    async def call_tool(self, name, arguments):
        type(self).last_call = (name, arguments)
        return type(self).result


@pytest.fixture(autouse=True)
def _patch_mcp(monkeypatch):
    _FakeSession.result = _Result([_Block("OPTIMIZED")])
    _FakeSession.last_call = None
    monkeypatch.setattr(opt, "streamablehttp_client", lambda *a, **k: _FakeStream())
    monkeypatch.setattr(opt, "ClientSession", _FakeSession)


async def test_system_mode_maps_to_tool():
    out = await optimize_prompt("hello", mode="system", mcp_url="http://x/mcp")
    assert out == "OPTIMIZED"
    assert _FakeSession.last_call[0] == "optimize-system-prompt"
    assert _FakeSession.last_call[1] == {"prompt": "hello"}


async def test_user_mode_maps_to_tool():
    await optimize_prompt("hi", mode="user", mcp_url="http://x/mcp")
    assert _FakeSession.last_call[0] == "optimize-user-prompt"


async def test_iterate_mode_includes_requirements():
    await optimize_prompt(
        "hi", mode="iterate", requirements="make it shorter", mcp_url="http://x/mcp"
    )
    assert _FakeSession.last_call[0] == "iterate-prompt"
    assert _FakeSession.last_call[1]["requirements"] == "make it shorter"


async def test_template_passed_when_provided():
    await optimize_prompt("hi", mode="system", template="tpl-1", mcp_url="http://x/mcp")
    assert _FakeSession.last_call[1]["template"] == "tpl-1"


async def test_unknown_mode_raises():
    with pytest.raises(PromptOptimizerError):
        await optimize_prompt("hi", mode="bogus", mcp_url="http://x/mcp")


async def test_iterate_without_requirements_raises():
    with pytest.raises(PromptOptimizerError):
        await optimize_prompt("hi", mode="iterate", mcp_url="http://x/mcp")


async def test_upstream_error_result_raises():
    _FakeSession.result = _Result([_Block("boom")], is_error=True)
    with pytest.raises(PromptOptimizerError):
        await optimize_prompt("hi", mode="system", mcp_url="http://x/mcp")


async def test_missing_text_content_raises():
    _FakeSession.result = _Result([])
    with pytest.raises(PromptOptimizerError):
        await optimize_prompt("hi", mode="system", mcp_url="http://x/mcp")
