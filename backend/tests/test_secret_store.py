"""Secret-store backend unit tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.secret_store import (
    DatabaseSecretStore,
    KeyVaultSecretStore,
    get_secret_store,
    is_keyvault_secret_store,
    mask_secret_value,
    secret_name_for_service,
)


def _http_client(response):
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    client.put = AsyncMock(return_value=response)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=None)
    return context, client


@pytest.mark.asyncio
async def test_database_secret_store_round_trip_and_mask():
    store = DatabaseSecretStore()
    encrypted = await store.set_secret("azure_voice_live", "super-secret")
    assert await store.get_secret("azure_voice_live", encrypted) == "super-secret"
    assert await store.mask_secret("azure_voice_live", encrypted) == "****cret"
    assert mask_secret_value("") == ""


@pytest.mark.asyncio
async def test_keyvault_get_handles_missing_success_and_invalid_value():
    store = KeyVaultSecretStore("https://vault.test/")
    store._headers = AsyncMock(return_value={"Authorization": "Bearer token"})

    missing = MagicMock(status_code=404)
    context, client = _http_client(missing)
    with patch("app.services.secret_store.httpx.AsyncClient", return_value=context):
        assert await store.get_secret("azure_voice_live") == ""
    assert "azure-voice-live-api-key" in client.get.await_args.args[0]

    success = MagicMock(status_code=200)
    success.json.return_value = {"value": "vault-secret"}
    context, _ = _http_client(success)
    with patch("app.services.secret_store.httpx.AsyncClient", return_value=context):
        assert await store.get_secret("azure_voice_live") == "vault-secret"

    success.json.return_value = {"value": 123}
    context, _ = _http_client(success)
    with patch("app.services.secret_store.httpx.AsyncClient", return_value=context):
        assert await store.get_secret("azure_voice_live") == ""


@pytest.mark.asyncio
async def test_keyvault_get_and_set_surface_http_errors():
    store = KeyVaultSecretStore("https://vault.test")
    store._headers = AsyncMock(return_value={})
    failure = MagicMock(status_code=500, text="vault unavailable")
    context, _ = _http_client(failure)
    with (
        patch("app.services.secret_store.httpx.AsyncClient", return_value=context),
        pytest.raises(RuntimeError, match="Failed to read Key Vault secret"),
    ):
        await store.get_secret("azure_voice_live")

    context, _ = _http_client(failure)
    with (
        patch("app.services.secret_store.httpx.AsyncClient", return_value=context),
        pytest.raises(RuntimeError, match="Failed to write Key Vault secret"),
    ):
        await store.set_secret("azure_voice_live", "secret")


@pytest.mark.asyncio
async def test_keyvault_set_mask_and_headers():
    store = KeyVaultSecretStore("https://vault.test")
    store._headers = AsyncMock(return_value={"Authorization": "Bearer token"})
    success = MagicMock(status_code=201)
    context, client = _http_client(success)
    with patch("app.services.secret_store.httpx.AsyncClient", return_value=context):
        assert await store.set_secret("azure_voice_live", "secret-value") == ""
    assert client.put.await_args.kwargs["json"] == {"value": "secret-value"}

    store.get_secret = AsyncMock(return_value="secret-value")
    assert await store.mask_secret("azure_voice_live") == "****alue"

    with patch("app.services.secret_store.get_bearer_token", AsyncMock(return_value="token")):
        assert await KeyVaultSecretStore("https://vault.test")._headers() == {
            "Authorization": "Bearer token",
            "Content-Type": "application/json",
        }
    with (
        patch("app.services.secret_store.get_bearer_token", AsyncMock(return_value="")),
        pytest.raises(RuntimeError, match="could not get a Key Vault token"),
    ):
        await KeyVaultSecretStore("https://vault.test")._headers()


def test_secret_mapping_and_store_selection():
    assert secret_name_for_service("azure_voice_live") == "azure-voice-live-api-key"
    with pytest.raises(ValueError, match="No Key Vault secret mapping"):
        secret_name_for_service("unknown")

    with patch(
        "app.services.secret_store.get_settings",
        return_value=SimpleNamespace(secret_store="database", azure_key_vault_url=""),
    ):
        assert isinstance(get_secret_store(), DatabaseSecretStore)
        assert is_keyvault_secret_store() is False

    with patch(
        "app.services.secret_store.get_settings",
        return_value=SimpleNamespace(
            secret_store="keyvault", azure_key_vault_url="https://vault.test/"
        ),
    ):
        store = get_secret_store()
        assert isinstance(store, KeyVaultSecretStore)
        assert store.vault_url == "https://vault.test"
        assert is_keyvault_secret_store() is True

    with (
        patch(
            "app.services.secret_store.get_settings",
            return_value=SimpleNamespace(secret_store="keyvault", azure_key_vault_url=""),
        ),
        pytest.raises(RuntimeError, match="AZURE_KEY_VAULT_URL"),
    ):
        get_secret_store()

    with (
        patch(
            "app.services.secret_store.get_settings",
            return_value=SimpleNamespace(secret_store="invalid", azure_key_vault_url=""),
        ),
        pytest.raises(RuntimeError, match="database.*keyvault"),
    ):
        get_secret_store()
