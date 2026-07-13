"""Secret storage backends for Azure service API keys.

Local development defaults to encrypted database storage. Cloud deployments can
switch to Key Vault so service keys are not stored in the application database.
"""

import logging
from typing import Protocol
from urllib.parse import quote

import httpx

from app.config import get_settings
from app.services.azure_auth import get_bearer_token
from app.utils.encryption import decrypt_value, encrypt_value

logger = logging.getLogger(__name__)

KEY_VAULT_SCOPE = "https://vault.azure.net/.default"
KEY_VAULT_API_VERSION = "7.4"

SERVICE_SECRET_NAMES = {
    "ai_foundry": "ai-foundry-api-key",
    "azure_openai": "azure-openai-api-key",
    "azure_speech_stt": "azure-speech-stt-api-key",
    "azure_speech_tts": "azure-speech-tts-api-key",
    "azure_avatar": "azure-avatar-api-key",
    "azure_content": "azure-content-understanding-api-key",
    "content_understanding": "azure-content-understanding-api-key",
    "azure_voice_live": "azure-voice-live-api-key",
    "azure_openai_realtime": "azure-openai-realtime-api-key",
    "prompt_optimizer": "prompt-optimizer-api-key",
}


class SecretStore(Protocol):
    """Storage backend for service API keys."""

    async def get_secret(self, service_name: str, encrypted_value: str = "") -> str:
        """Return a secret value for a service, or an empty string."""

    async def set_secret(self, service_name: str, value: str) -> str:
        """Persist a secret and return the DB encrypted value to store."""

    async def mask_secret(self, service_name: str, encrypted_value: str = "") -> str:
        """Return a masked representation suitable for API responses."""


class DatabaseSecretStore:
    """Existing local behavior: Fernet-encrypted value stored in the DB."""

    async def get_secret(self, service_name: str, encrypted_value: str = "") -> str:
        return decrypt_value(encrypted_value)

    async def set_secret(self, service_name: str, value: str) -> str:
        return encrypt_value(value)

    async def mask_secret(self, service_name: str, encrypted_value: str = "") -> str:
        value = await self.get_secret(service_name, encrypted_value)
        return mask_secret_value(value)


class KeyVaultSecretStore:
    """Azure Key Vault backed service key storage."""

    def __init__(self, vault_url: str):
        self.vault_url = vault_url.rstrip("/")

    async def get_secret(self, service_name: str, encrypted_value: str = "") -> str:
        secret_name = secret_name_for_service(service_name)
        url = f"{self.vault_url}/secrets/{quote(secret_name)}?api-version={KEY_VAULT_API_VERSION}"
        headers = await self._headers()
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
        if response.status_code == 404:
            return ""
        if response.status_code != 200:
            raise RuntimeError(
                f"Failed to read Key Vault secret '{secret_name}': "
                f"HTTP {response.status_code} - {response.text[:200]}"
            )
        value = response.json().get("value", "")
        return value if isinstance(value, str) else ""

    async def set_secret(self, service_name: str, value: str) -> str:
        secret_name = secret_name_for_service(service_name)
        url = f"{self.vault_url}/secrets/{quote(secret_name)}?api-version={KEY_VAULT_API_VERSION}"
        headers = await self._headers()
        body = {"value": value}
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.put(url, headers=headers, json=body)
        if response.status_code not in (200, 201):
            raise RuntimeError(
                f"Failed to write Key Vault secret '{secret_name}': "
                f"HTTP {response.status_code} - {response.text[:200]}"
            )
        return ""

    async def mask_secret(self, service_name: str, encrypted_value: str = "") -> str:
        value = await self.get_secret(service_name, encrypted_value)
        return mask_secret_value(value)

    async def _headers(self) -> dict[str, str]:
        token = await get_bearer_token(KEY_VAULT_SCOPE)
        if not token:
            raise RuntimeError("DefaultAzureCredential could not get a Key Vault token")
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }


def mask_secret_value(value: str) -> str:
    """Return a stable masked display value."""
    return ("****" + value[-4:]) if value else ""


def secret_name_for_service(service_name: str) -> str:
    """Map an application service name to a fixed Key Vault secret name."""
    if service_name not in SERVICE_SECRET_NAMES:
        raise ValueError(f"No Key Vault secret mapping exists for service '{service_name}'")
    return SERVICE_SECRET_NAMES[service_name]


def get_secret_store() -> SecretStore:
    """Return the configured service secret store."""
    settings = get_settings()
    store = settings.secret_store.lower()
    if store == "database":
        return DatabaseSecretStore()
    if store == "keyvault":
        if not settings.azure_key_vault_url:
            raise RuntimeError("AZURE_KEY_VAULT_URL is required when SECRET_STORE=keyvault")
        return KeyVaultSecretStore(settings.azure_key_vault_url)
    raise RuntimeError("SECRET_STORE must be either 'database' or 'keyvault'")


def is_keyvault_secret_store() -> bool:
    """Return whether service API keys should be stored in Key Vault."""
    return get_settings().secret_store.lower() == "keyvault"
