"""Unit tests for prompt_optimizer_client (no live sidecar; HTTP is mocked)."""

import pytest

import app.services.prompt_optimizer_client as opt
from app.services.prompt_optimizer_client import PromptOptimizerError, optimize_prompt


class _FakeResponse:
    def __init__(self, payload=None, status_code=200, headers=None, text=""):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text

    def json(self):
        if self._payload is None:
            raise opt.json.JSONDecodeError("Expecting value", self.text, 0)
        return self._payload


class _FakeAsyncClient:
    responses = []
    calls = []

    def __init__(self, *args, **kwargs):
        self.timeout = kwargs.get("timeout")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, headers, json):
        type(self).calls.append((url, headers, json))
        return type(self).responses.pop(0)


@pytest.fixture(autouse=True)
def _patch_http(monkeypatch):
    _FakeAsyncClient.calls = []
    _FakeAsyncClient.responses = [
        _FakeResponse({"jsonrpc": "2.0", "id": 1, "result": {}}, headers={"mcp-session-id": "s1"}),
        _FakeResponse({}, status_code=202),
        _FakeResponse(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "result": {"content": [{"type": "text", "text": "OPTIMIZED"}]},
            }
        ),
    ]
    monkeypatch.setattr(opt.httpx, "AsyncClient", _FakeAsyncClient)


async def test_system_mode_maps_to_tool():
    out = await optimize_prompt("hello", mode="system", mcp_url="http://x/mcp")
    assert out == "OPTIMIZED"
    call_payload = _FakeAsyncClient.calls[-1][2]
    assert call_payload["params"]["name"] == "optimize-system-prompt"
    assert call_payload["params"]["arguments"] == {"prompt": "hello"}


async def test_user_mode_maps_to_tool():
    await optimize_prompt("hi", mode="user", mcp_url="http://x/mcp")
    assert _FakeAsyncClient.calls[-1][2]["params"]["name"] == "optimize-user-prompt"


async def test_iterate_mode_includes_requirements():
    await optimize_prompt(
        "hi", mode="iterate", requirements="make it shorter", mcp_url="http://x/mcp"
    )
    assert _FakeAsyncClient.calls[-1][2]["params"]["name"] == "iterate-prompt"
    assert _FakeAsyncClient.calls[-1][2]["params"]["arguments"]["requirements"] == "make it shorter"


async def test_template_passed_when_provided():
    await optimize_prompt("hi", mode="system", template="tpl-1", mcp_url="http://x/mcp")
    assert _FakeAsyncClient.calls[-1][2]["params"]["arguments"]["template"] == "tpl-1"


async def test_unknown_mode_raises():
    with pytest.raises(PromptOptimizerError):
        await optimize_prompt("hi", mode="bogus", mcp_url="http://x/mcp")


async def test_iterate_without_requirements_raises():
    with pytest.raises(PromptOptimizerError):
        await optimize_prompt("hi", mode="iterate", mcp_url="http://x/mcp")


async def test_upstream_error_result_raises():
    _FakeAsyncClient.responses[-1] = _FakeResponse(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {"isError": True, "content": [{"type": "text", "text": "boom"}]},
        }
    )
    with pytest.raises(PromptOptimizerError):
        await optimize_prompt("hi", mode="system", mcp_url="http://x/mcp")


async def test_missing_text_content_raises():
    _FakeAsyncClient.responses[-1] = _FakeResponse(
        {"jsonrpc": "2.0", "id": 2, "result": {"content": []}}
    )
    with pytest.raises(PromptOptimizerError):
        await optimize_prompt("hi", mode="system", mcp_url="http://x/mcp")


async def test_sse_jsonrpc_response_is_supported():
    _FakeAsyncClient.responses[0] = _FakeResponse(
        text='event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{}}\n\n',
        headers={"mcp-session-id": "s1", "content-type": "text/event-stream"},
    )
    _FakeAsyncClient.responses[-1] = _FakeResponse(
        text=(
            'event: message\n'
            'data: {"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text",'
            '"text":"OPTIMIZED SSE"}]}}\n\n'
        ),
        headers={"content-type": "text/event-stream"},
    )

    out = await optimize_prompt("hi", mode="system", mcp_url="http://x/mcp")

    assert out == "OPTIMIZED SSE"


async def test_initialize_requires_session_id():
    _FakeAsyncClient.responses[0] = _FakeResponse({"jsonrpc": "2.0", "id": 1, "result": {}})

    with pytest.raises(PromptOptimizerError, match="mcp-session-id"):
        await optimize_prompt("hi", mode="system", mcp_url="http://x/mcp")
