"""API integration tests for region-capabilities and azure_openai_realtime acceptance."""

from app.models.user import User
from app.services.auth import create_access_token, get_password_hash
from tests.conftest import TestSessionLocal


async def _create_admin_token() -> str:
    """Create an admin user and return bearer token."""
    async with TestSessionLocal() as session:
        user = User(
            username="admin_ext",
            email="admin_ext@test.com",
            hashed_password=get_password_hash("admin123"),
            full_name="Admin Ext",
            role="admin",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return create_access_token(data={"sub": user.id})


async def _create_user_token() -> str:
    """Create a regular user and return bearer token."""
    async with TestSessionLocal() as session:
        user = User(
            username="user_ext",
            email="user_ext@test.com",
            hashed_password=get_password_hash("pass"),
            full_name="Regular Ext",
            role="user",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return create_access_token(data={"sub": user.id})


class TestRegionCapabilitiesEndpoint:
    """Tests for GET /api/v1/azure-config/region-capabilities/{region}."""

    async def test_region_capabilities_eastus2(self, client):
        """eastus2 returns 200 with service availability map."""
        token = await _create_admin_token()
        response = await client.get(
            "/api/v1/azure-config/region-capabilities/eastus2",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "services" in data
        services = data["services"]

        # Azure OpenAI is unrestricted
        assert services["azure_openai"]["available"] is True

        # Avatar is available in eastus2
        assert services["azure_avatar"]["available"] is True

        # All 8 services present
        assert len(services) == 8
        assert services["prompt_optimizer"]["available"] is True

    async def test_region_capabilities_unknown_region(self, client):
        """Unknown region: avatar unavailable, openai available."""
        token = await _create_admin_token()
        response = await client.get(
            "/api/v1/azure-config/region-capabilities/unknown-region",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        services = data["services"]

        assert services["azure_avatar"]["available"] is False
        assert services["azure_openai"]["available"] is True

    async def test_region_capabilities_requires_admin(self, client):
        """Region capabilities endpoint requires admin auth."""
        # No token
        response = await client.get(
            "/api/v1/azure-config/region-capabilities/eastus2",
        )
        assert response.status_code == 401

        # Regular user
        user_token = await _create_user_token()
        response = await client.get(
            "/api/v1/azure-config/region-capabilities/eastus2",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 403


class TestAzureOpenAIRealtimeAcceptance:
    """Tests for PUT /api/v1/azure-config/services/azure_openai_realtime."""

    async def test_put_azure_openai_realtime_accepted(self, client):
        """PUT azure_openai_realtime returns 200 (not 400)."""
        token = await _create_admin_token()
        response = await client.put(
            "/api/v1/azure-config/services/azure_openai_realtime",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "endpoint": "https://test.openai.azure.com",
                "api_key": "test-key",
                "model_or_deployment": "gpt-4o-realtime-preview",
                "region": "eastus2",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["service_name"] == "azure_openai_realtime"
        assert data["display_name"] == "Azure OpenAI Realtime"

    async def test_list_services_includes_realtime(self, client):
        """After saving azure_openai_realtime, GET /services includes it."""
        token = await _create_admin_token()
        # Save realtime config
        await client.put(
            "/api/v1/azure-config/services/azure_openai_realtime",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "endpoint": "https://test.openai.azure.com",
                "api_key": "test-key",
                "model_or_deployment": "gpt-4o-realtime-preview",
                "region": "eastus2",
            },
        )
        # List all services
        response = await client.get(
            "/api/v1/azure-config/services",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        service_names = [svc["service_name"] for svc in data]
        assert "azure_openai_realtime" in service_names

    async def test_put_unknown_service_rejected(self, client):
        """PUT with unknown service name returns 400."""
        token = await _create_admin_token()
        response = await client.put(
            "/api/v1/azure-config/services/nonexistent_service",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "endpoint": "https://test.com",
                "api_key": "key123",
                "model_or_deployment": "",
                "region": "",
            },
        )
        assert response.status_code == 400


class TestPromptOptimizerConfigAcceptance:
    """Tests for PUT /api/v1/azure-config/services/prompt_optimizer."""

    async def test_put_prompt_optimizer_accepted(self, client):
        token = await _create_admin_token()
        response = await client.put(
            "/api/v1/azure-config/services/prompt_optimizer",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "endpoint": "",
                "api_key": "",
                "model_or_deployment": "gpt-4o-mini",
                "region": "",
                "is_active": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["service_name"] == "prompt_optimizer"
        assert data["display_name"] == "Prompt Optimizer"
        assert data["model_or_deployment"] == "gpt-4o-mini"

    async def test_prompt_optimizer_has_keyvault_secret_mapping(self):
        from app.services.secret_store import secret_name_for_service

        assert secret_name_for_service("prompt_optimizer") == "prompt-optimizer-api-key"
