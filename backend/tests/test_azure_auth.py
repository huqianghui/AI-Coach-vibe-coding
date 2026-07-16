"""Tests for centralized Azure authentication module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.azure_auth import (
    COGNITIVE_SERVICES_SCOPE,
    get_auth_headers,
    get_azure_credential,
    get_azure_openai_client,
    get_bearer_token,
)


class TestGetAzureCredential:
    """Tests for get_azure_credential."""

    async def test_returns_credential_when_available(self):
        """Should return an async DefaultAzureCredential instance."""
        mock_cred = MagicMock()
        with patch(
            "azure.identity.aio.DefaultAzureCredential",
            return_value=mock_cred,
        ):
            result = await get_azure_credential()
            assert result is mock_cred

    async def test_returns_none_when_import_fails(self):
        """Should return None when azure.identity is not importable."""
        with patch.dict("sys.modules", {"azure.identity.aio": None}):
            with patch(
                "builtins.__import__",
                side_effect=ImportError("no module"),
            ):
                result = await get_azure_credential()
                assert result is None


class TestGetBearerToken:
    """Tests for get_bearer_token."""

    async def test_returns_token_on_success(self):
        """Should return token string when credential works."""
        mock_token = MagicMock()
        mock_token.token = "test-aad-token"

        mock_cred = AsyncMock()
        mock_cred.get_token = AsyncMock(return_value=mock_token)
        mock_cred.close = AsyncMock()

        with patch(
            "app.services.azure_auth.get_azure_credential",
            new=AsyncMock(return_value=mock_cred),
        ):
            result = await get_bearer_token()
            assert result == "test-aad-token"
            mock_cred.get_token.assert_called_once_with(COGNITIVE_SERVICES_SCOPE)
            mock_cred.close.assert_called_once()

    async def test_returns_none_when_no_credential(self):
        """Should return None when no credential available."""
        with patch(
            "app.services.azure_auth.get_azure_credential",
            new=AsyncMock(return_value=None),
        ):
            result = await get_bearer_token()
            assert result is None

    async def test_returns_none_on_token_error(self):
        """Should return None when get_token raises."""
        mock_cred = AsyncMock()
        mock_cred.get_token = AsyncMock(side_effect=Exception("auth failed"))
        mock_cred.close = AsyncMock()

        with patch(
            "app.services.azure_auth.get_azure_credential",
            new=AsyncMock(return_value=mock_cred),
        ):
            result = await get_bearer_token()
            assert result is None
            mock_cred.close.assert_called_once()

    async def test_custom_scope(self):
        """Should pass custom scope to get_token."""
        mock_token = MagicMock()
        mock_token.token = "custom-token"

        mock_cred = AsyncMock()
        mock_cred.get_token = AsyncMock(return_value=mock_token)
        mock_cred.close = AsyncMock()

        custom_scope = "https://custom.scope/.default"
        with patch(
            "app.services.azure_auth.get_azure_credential",
            new=AsyncMock(return_value=mock_cred),
        ):
            result = await get_bearer_token(custom_scope)
            assert result == "custom-token"
            mock_cred.get_token.assert_called_once_with(custom_scope)


class TestGetAzureOpenAIClient:
    """Tests for get_azure_openai_client."""

    async def test_uses_aad_token_when_available(self):
        """Should create client with a refreshing AAD token provider when AAD works."""
        mock_cred = MagicMock()
        token_provider = MagicMock(return_value="aad-token-123")

        mock_client = MagicMock()
        with (
            patch(
                "app.services.azure_auth._get_credential_sync",
                return_value=mock_cred,
            ),
            patch("azure.identity.get_bearer_token_provider", return_value=token_provider),
            patch("openai.AsyncAzureOpenAI", return_value=mock_client) as mock_cls,
        ):
            result = await get_azure_openai_client(
                endpoint="https://test.openai.azure.com",
                api_key="fallback-key",
            )
            assert result is mock_client
            call_kwargs = mock_cls.call_args.kwargs
            assert call_kwargs["azure_ad_token_provider"] is token_provider
            assert "api_key" not in call_kwargs
            token_provider.assert_called_once_with()

    async def test_falls_back_to_api_key(self):
        """Should create client with api_key when AAD fails."""
        mock_cred = MagicMock()
        token_provider = MagicMock(side_effect=Exception("no az login"))

        mock_client = MagicMock()
        with (
            patch(
                "app.services.azure_auth._get_credential_sync",
                return_value=mock_cred,
            ),
            patch("azure.identity.get_bearer_token_provider", return_value=token_provider),
            patch("openai.AsyncAzureOpenAI", return_value=mock_client) as mock_cls,
        ):
            result = await get_azure_openai_client(
                endpoint="https://test.openai.azure.com",
                api_key="my-api-key",
            )
            assert result is mock_client
            call_kwargs = mock_cls.call_args.kwargs
            assert call_kwargs["api_key"] == "my-api-key"
            assert "azure_ad_token_provider" not in call_kwargs

    async def test_raises_when_no_credentials(self):
        """Should raise RuntimeError when neither AAD nor key available."""
        token_provider = MagicMock(side_effect=Exception("no cred"))

        with (
            patch("app.services.azure_auth._get_credential_sync", return_value=MagicMock()),
            patch("azure.identity.get_bearer_token_provider", return_value=token_provider),
        ):
            with pytest.raises(RuntimeError, match="No Azure credentials available"):
                await get_azure_openai_client(
                    endpoint="https://test.openai.azure.com",
                    api_key="",
                )

    async def test_passes_api_version(self):
        """Should pass api_version to the client."""
        token_provider = MagicMock(return_value="token")

        mock_client = MagicMock()
        with (
            patch(
                "app.services.azure_auth._get_credential_sync",
                return_value=MagicMock(),
            ),
            patch("azure.identity.get_bearer_token_provider", return_value=token_provider),
            patch("openai.AsyncAzureOpenAI", return_value=mock_client) as mock_cls,
        ):
            await get_azure_openai_client(
                endpoint="https://test.openai.azure.com",
                api_version="2024-12-01-preview",
            )
            call_kwargs = mock_cls.call_args.kwargs
            assert call_kwargs["api_version"] == "2024-12-01-preview"

    async def test_passes_timeout(self):
        """Should pass timeout to the client when specified."""
        token_provider = MagicMock(return_value="token")

        mock_client = MagicMock()
        with (
            patch(
                "app.services.azure_auth._get_credential_sync",
                return_value=MagicMock(),
            ),
            patch("azure.identity.get_bearer_token_provider", return_value=token_provider),
            patch("openai.AsyncAzureOpenAI", return_value=mock_client) as mock_cls,
        ):
            await get_azure_openai_client(
                endpoint="https://test.openai.azure.com",
                timeout=10.0,
            )
            call_kwargs = mock_cls.call_args.kwargs
            assert call_kwargs["timeout"] == 10.0

    async def test_no_timeout_by_default(self):
        """Should not pass timeout when not specified."""
        token_provider = MagicMock(return_value="token")

        mock_client = MagicMock()
        with (
            patch(
                "app.services.azure_auth._get_credential_sync",
                return_value=MagicMock(),
            ),
            patch("azure.identity.get_bearer_token_provider", return_value=token_provider),
            patch("openai.AsyncAzureOpenAI", return_value=mock_client) as mock_cls,
        ):
            await get_azure_openai_client(
                endpoint="https://test.openai.azure.com",
            )
            call_kwargs = mock_cls.call_args.kwargs
            assert "timeout" not in call_kwargs


class TestGetAuthHeaders:
    """Tests for get_auth_headers."""

    async def test_uses_aad_token_when_available(self):
        """Should return Authorization header with AAD token."""
        with patch(
            "app.services.azure_auth.get_bearer_token",
            new=AsyncMock(return_value="bearer-token-123"),
        ):
            headers = await get_auth_headers(api_key="fallback")
            assert headers["Authorization"] == "Bearer bearer-token-123"
            assert headers["Content-Type"] == "application/json"
            assert "Ocp-Apim-Subscription-Key" not in headers

    async def test_falls_back_to_api_key(self):
        """Should return Ocp-Apim-Subscription-Key header when AAD fails."""
        with patch(
            "app.services.azure_auth.get_bearer_token",
            new=AsyncMock(return_value=None),
        ):
            headers = await get_auth_headers(api_key="my-key")
            assert headers["Ocp-Apim-Subscription-Key"] == "my-key"
            assert headers["Content-Type"] == "application/json"
            assert "Authorization" not in headers

    async def test_raises_when_no_credentials(self):
        """Should raise RuntimeError when neither AAD nor key available."""
        with patch(
            "app.services.azure_auth.get_bearer_token",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(RuntimeError, match="No Azure credentials available"):
                await get_auth_headers(api_key="")
