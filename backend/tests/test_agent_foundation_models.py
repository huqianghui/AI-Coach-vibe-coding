"""Tests for the Agent Foundation Model catalog service + admin endpoint (D-14).

Covers:
  - Defensive filtering (_is_chat_capable): exclusion by VOICE_LIVE_MODELS name,
    unknown/empty capabilities default-include, positive/negative signal keys.
  - Cache behavior: reuse within TTL, stale-on-failure, empty-on-failure-no-cache.
  - Endpoint: admin-only (403 for non-admin), minimal response fields (no
    connection_name/sku leak).
"""

from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_current_user
from app.main import app
from app.models.user import User
from app.services import agent_foundation_models as afm_service

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_cache():
    """Reset the module-level cache before and after every test for isolation."""
    afm_service._cache["data"] = None
    afm_service._cache["fetched_at"] = 0.0
    yield
    afm_service._cache["data"] = None
    afm_service._cache["fetched_at"] = 0.0


def _fake_deployment(name: str, model_name: str, capabilities: dict | None = None):
    dep = MagicMock()
    dep.name = name
    dep.model_name = model_name
    dep.capabilities = capabilities
    return dep


def _fake_admin() -> User:
    user = MagicMock(spec=User)
    user.id = "admin-afm-test-001"
    user.role = "admin"
    user.username = "testadmin"
    user.is_active = True
    return user


def _fake_regular_user() -> User:
    user = MagicMock(spec=User)
    user.id = "user-afm-test-001"
    user.role = "user"
    user.username = "testuser"
    user.is_active = True
    return user


# ---------------------------------------------------------------------------
# _is_chat_capable filtering (Tests 1-4)
# ---------------------------------------------------------------------------


class TestIsChatCapable:
    def test_excludes_voice_live_model_name_case_insensitive(self):
        """Test 1: a deployment whose model_name matches a VOICE_LIVE_MODELS key
        (case-insensitive) is excluded."""
        assert afm_service._is_chat_capable("GPT-Realtime", None) is False
        assert afm_service._is_chat_capable("gpt-4o", {}) is False

    def test_includes_unknown_empty_capabilities(self):
        """Test 2: a deployment with capabilities={} (empty/unknown) is included."""
        assert afm_service._is_chat_capable("my-custom-chat-model", {}) is True
        assert afm_service._is_chat_capable("my-custom-chat-model", None) is True

    def test_includes_chat_completion_positive_signal(self):
        """Test 3: a deployment with capabilities={"chat_completion": "true"} is included."""
        assert (
            afm_service._is_chat_capable("my-custom-chat-model", {"chat_completion": "true"})
            is True
        )

    def test_excludes_embeddings_negative_signal(self):
        """Test 4: a deployment with capabilities={"embeddings": "true"} and no
        chat-signal key is excluded."""
        assert afm_service._is_chat_capable("my-embedding-model", {"embeddings": "true"}) is False


class TestProjectClient:
    """Cover project endpoint composition and both supported credential paths."""

    def test_build_project_endpoint_variants(self):
        assert (
            afm_service._build_project_endpoint(
                "https://foundry.test/api/projects/existing", "ignored"
            )
            == "https://foundry.test/api/projects/existing"
        )
        assert (
            afm_service._build_project_endpoint("https://foundry.test/", "project-a")
            == "https://foundry.test/api/projects/project-a"
        )
        assert afm_service._build_project_endpoint("https://foundry.test/", "") == (
            "https://foundry.test"
        )

    def test_get_project_client_prefers_entra_id(self):
        credential = MagicMock()
        client = MagicMock()
        with (
            patch("azure.identity.DefaultAzureCredential", return_value=credential),
            patch("azure.ai.projects.AIProjectClient", return_value=client) as create_client,
        ):
            result = afm_service._get_project_client("https://project.test", "fallback-key")

        assert result is client
        credential.get_token.assert_called_once_with("https://ai.azure.com/.default")
        create_client.assert_called_once_with(
            endpoint="https://project.test", credential=credential
        )

    def test_get_project_client_falls_back_to_api_key(self):
        client = MagicMock()
        with (
            patch(
                "azure.identity.DefaultAzureCredential",
                side_effect=RuntimeError("no entra credential"),
            ),
            patch("azure.ai.projects.AIProjectClient", return_value=client) as create_client,
        ):
            result = afm_service._get_project_client("https://project.test", "api-key")

        assert result is client
        kwargs = create_client.call_args.kwargs
        assert kwargs["endpoint"] == "https://project.test"
        assert kwargs["credential"]._key == "api-key"
        assert kwargs["authentication_policy"] is not None

    def test_get_project_client_rejects_missing_credentials(self):
        with (
            patch(
                "azure.identity.DefaultAzureCredential",
                side_effect=RuntimeError("no entra credential"),
            ),
            pytest.raises(ValueError, match="No valid credential"),
        ):
            afm_service._get_project_client("https://project.test")


# ---------------------------------------------------------------------------
# Cache behavior (Tests 5-7)
# ---------------------------------------------------------------------------


class TestCacheBehavior:
    def test_cache_reuse_within_ttl(self):
        """Test 5: two calls within 300s call the mocked deployments.list exactly once."""
        mock_client = MagicMock()
        mock_client.deployments.list.return_value = [
            _fake_deployment("dep-1", "my-chat-model", {"chat_completion": "true"}),
        ]
        with patch.object(afm_service, "_get_project_client", return_value=mock_client):
            models_1, stale_1, error_1 = afm_service.list_agent_foundation_models()
            models_2, stale_2, error_2 = afm_service.list_agent_foundation_models()

        assert mock_client.deployments.list.call_count == 1
        assert models_1 == models_2
        assert stale_1 is False and stale_2 is False
        assert error_1 is None and error_2 is None

    def test_stale_data_returned_when_ttl_expired_and_fetch_fails(self):
        """Test 6: after TTL expiry, a failing fetch returns previous cached
        models with stale=True."""
        mock_client = MagicMock()
        mock_client.deployments.list.return_value = [
            _fake_deployment("dep-1", "my-chat-model", {"chat_completion": "true"}),
        ]
        with patch.object(afm_service, "_get_project_client", return_value=mock_client):
            first_models, _, _ = afm_service.list_agent_foundation_models()

        # Simulate TTL expiry
        afm_service._cache["fetched_at"] -= afm_service.CACHE_TTL_SECONDS + 1

        with patch.object(
            afm_service, "_get_project_client", side_effect=RuntimeError("Foundry unreachable")
        ):
            models, stale, error = afm_service.list_agent_foundation_models()

        assert models == first_models
        assert stale is True
        assert error is not None and "Foundry unreachable" in error

    def test_empty_and_no_error_flag_when_fetch_fails_without_prior_cache(self):
        """Test 7: a failing fetch with no prior cache returns ([], False, error)."""
        with patch.object(
            afm_service, "_get_project_client", side_effect=RuntimeError("no credential")
        ):
            models, stale, error = afm_service.list_agent_foundation_models()

        assert models == []
        assert stale is False
        assert error is not None and "no credential" in error


# ---------------------------------------------------------------------------
# Endpoint: admin-only + minimal fields (Tests 8-9)
# ---------------------------------------------------------------------------


class TestEndpoint:
    @pytest.fixture(autouse=True)
    def _clear_overrides(self):
        yield
        app.dependency_overrides.clear()

    async def test_non_admin_gets_403(self):
        """Test 8: GET as a non-admin user returns 403."""

        async def override_get_current_user():
            return _fake_regular_user()

        app.dependency_overrides[get_current_user] = override_get_current_user

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/v1/agent-foundation-models")

        assert response.status_code == 403

    async def test_admin_gets_200_with_minimal_fields_only(self):
        """Test 9: GET as admin returns 200 with only id/label fields — no
        connection_name/sku leak (T-29-08-01)."""

        async def override_get_current_user():
            return _fake_admin()

        app.dependency_overrides[get_current_user] = override_get_current_user

        mock_client = MagicMock()
        mock_client.deployments.list.return_value = [
            _fake_deployment("dep-1", "my-chat-model", {"chat_completion": "true"}),
        ]
        with patch.object(afm_service, "_get_project_client", return_value=mock_client):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.get("/api/v1/agent-foundation-models")

        assert response.status_code == 200
        body = response.json()
        assert body["models"] == [{"id": "dep-1", "label": "my-chat-model"}]
        assert "connection_name" not in response.text
        assert "sku" not in response.text
