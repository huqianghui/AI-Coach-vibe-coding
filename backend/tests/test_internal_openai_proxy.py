"""Tests for the internal OpenAI-compatible prompt optimizer proxy."""

from unittest.mock import AsyncMock, patch

from app.config import get_settings
from app.models.service_config import ServiceConfig
from app.models.user import User
from app.services.auth import get_password_hash
from tests.conftest import TestSessionLocal


class _FakeCompletion:
    def model_dump(self, mode="json"):
        return {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "choices": [{"message": {"role": "assistant", "content": "optimized"}}],
        }


class _FakeChatCompletions:
    last_payload = None

    async def create(self, **payload):
        type(self).last_payload = payload
        return _FakeCompletion()


class _FakeClient:
    def __init__(self):
        self.chat = type("Chat", (), {"completions": _FakeChatCompletions()})()


async def _seed_configs() -> None:
    async with TestSessionLocal() as session:
        user = User(
            username="proxy_admin",
            email="proxy_admin@test.com",
            hashed_password=get_password_hash("admin123"),
            full_name="Proxy Admin",
            role="admin",
        )
        session.add(user)
        session.add(
            ServiceConfig(
                service_name="ai_foundry",
                display_name="Azure AI Foundry",
                endpoint="https://foundry.services.ai.azure.com",
                api_key_encrypted="",
                model_or_deployment="gpt-4o",
                is_master=True,
                is_active=True,
                updated_by="test",
            )
        )
        session.add(
            ServiceConfig(
                service_name="prompt_optimizer",
                display_name="Prompt Optimizer",
                endpoint="",
                api_key_encrypted="",
                model_or_deployment="gpt-4o-mini",
                is_active=True,
                updated_by="test",
            )
        )
        await session.commit()


async def test_proxy_requires_configured_secret(client):
    get_settings().prompt_optimizer_proxy_secret = ""
    response = await client.get("/api/v1/internal/openai/v1/models")
    assert response.status_code == 503
    assert response.json()["code"] == "PROMPT_OPTIMIZER_PROXY_NOT_CONFIGURED"


async def test_proxy_rejects_invalid_secret(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "prompt_optimizer_proxy_secret", "expected")
    response = await client.get(
        "/api/v1/internal/openai/v1/models",
        headers={"Authorization": "Bearer wrong"},
    )

    assert response.status_code == 401


async def test_models_returns_optimizer_override_model(client, monkeypatch):
    await _seed_configs()
    monkeypatch.setattr(get_settings(), "prompt_optimizer_proxy_secret", "expected")

    response = await client.get(
        "/api/v1/internal/openai/v1/models",
        headers={"Authorization": "Bearer expected"},
    )

    assert response.status_code == 200
    assert response.json()["data"][0]["id"] == "gpt-4o-mini"


async def test_chat_completion_replaces_model_with_optimizer_override(client, monkeypatch):
    await _seed_configs()
    monkeypatch.setattr(get_settings(), "prompt_optimizer_proxy_secret", "expected")
    fake_client = _FakeClient()

    with patch(
        "app.services.azure_auth.get_azure_openai_client",
        new=AsyncMock(return_value=fake_client),
    ):
        response = await client.post(
            "/api/v1/internal/openai/v1/chat/completions",
            headers={"Authorization": "Bearer expected"},
            json={
                "model": "third-party-requested-model",
                "messages": [{"role": "user", "content": "Optimize this"}],
                "temperature": 0.2,
            },
        )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "optimized"
    assert _FakeChatCompletions.last_payload["model"] == "gpt-4o-mini"
    assert _FakeChatCompletions.last_payload["temperature"] == 0.2
