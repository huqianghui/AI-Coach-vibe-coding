"""Centralized Azure authentication module.

ALL Azure service authentication MUST go through this module.
Strategy: DefaultAzureCredential (AAD token) first, API Key fallback.

Local development: `az login` provides credentials via DefaultAzureCredential.
Server (Azure): Managed Identity provides credentials via DefaultAzureCredential.
Fallback: API Key from config_service (admin panel settings).

Usage:
    from app.services.azure_auth import get_azure_openai_client, get_azure_credential

    # For OpenAI chat completions:
    client = await get_azure_openai_client(endpoint, api_key, api_version="2024-06-01")

    # For raw bearer tokens (e.g., Content Understanding):
    token = await get_bearer_token("https://cognitiveservices.azure.com/.default")
"""

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# Azure Cognitive Services scope (used for OpenAI, Speech, CU, etc.)
COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"

# Cache for the credential singleton
_credential_instance: Any = None
_credential_lock_time: float = 0.0
# TTL for credential instance (recreate if older than 30 min to handle token refresh)
_CREDENTIAL_TTL_SECONDS = 1800


def _get_credential_sync() -> Any:
    """Get or create a cached DefaultAzureCredential (sync version for sync clients).

    Returns the credential or None if azure-identity is not installed or fails to initialize.
    """
    global _credential_instance, _credential_lock_time

    now = time.time()
    if _credential_instance is not None and (now - _credential_lock_time) < _CREDENTIAL_TTL_SECONDS:
        return _credential_instance

    try:
        from azure.identity import DefaultAzureCredential

        _credential_instance = DefaultAzureCredential()
        _credential_lock_time = now
        logger.debug("azure_auth: DefaultAzureCredential (sync) initialized")
        return _credential_instance
    except Exception as exc:
        logger.debug("azure_auth: Failed to initialize DefaultAzureCredential: %s", exc)
        _credential_instance = None
        return None


def get_token_credential_sync() -> Any:
    """Return a sync DefaultAzureCredential for Azure SDKs that accept TokenCredential.

    Speech SDK token-credential constructors are synchronous, so they cannot use
    the async helper below. The credential is cached and can use local az login
    or the Container App managed identity via DefaultAzureCredential.
    """
    return _get_credential_sync()


async def get_azure_credential() -> Any:
    """Get a cached async DefaultAzureCredential instance.

    Returns the credential or None if unavailable.
    """
    try:
        from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential

        # For async credential, we create a new instance each time but rely on
        # the SDK's internal token caching. The async credential should be closed
        # by the caller or used as context manager where appropriate.
        credential = AsyncDefaultAzureCredential()
        return credential
    except Exception as exc:
        logger.debug("azure_auth: Failed to initialize async DefaultAzureCredential: %s", exc)
        return None


async def get_bearer_token(scope: str = COGNITIVE_SERVICES_SCOPE) -> str | None:
    """Get a bearer token for the specified scope using DefaultAzureCredential.

    Returns the token string, or None if AAD auth is unavailable.
    """
    credential = await get_azure_credential()
    if credential is None:
        return None

    try:
        token = await credential.get_token(scope)
        logger.debug("azure_auth: obtained bearer token for scope %s", scope)
        return token.token
    except Exception as exc:
        logger.debug("azure_auth: get_bearer_token failed: %s", exc)
        return None
    finally:
        await credential.close()


async def get_azure_openai_client(
    endpoint: str,
    api_key: str = "",
    api_version: str = "2024-06-01",
    timeout: float | None = None,
) -> Any:
    """Create an AsyncAzureOpenAI client with AAD-first, API-key-fallback auth.

    Authentication priority:
      1. DefaultAzureCredential (az login / Managed Identity) - preferred
      2. API Key fallback - if AAD is unavailable or fails

    Args:
        endpoint: Azure OpenAI endpoint URL
        api_key: API key for fallback authentication (from config_service)
        api_version: Azure OpenAI API version string
        timeout: Optional request timeout in seconds

    Returns:
        AsyncAzureOpenAI client instance

    Raises:
        RuntimeError: If neither AAD nor API key authentication is available
        ImportError: If openai package is not installed
    """
    from openai import AsyncAzureOpenAI

    # 1. Try AAD token via get_bearer_token_provider
    try:
        from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential

        credential = AsyncDefaultAzureCredential()
        # Verify we can actually get a token (probes az login / MI availability)
        token = await credential.get_token(COGNITIVE_SERVICES_SCOPE)
        if token and token.token:
            logger.debug("azure_auth: creating AsyncAzureOpenAI with AAD token for %s", endpoint)
            # Use ad_token directly (simpler than token provider for async)
            kwargs: dict[str, Any] = {
                "azure_endpoint": endpoint,
                "azure_ad_token": token.token,
                "api_version": api_version,
            }
            if timeout is not None:
                kwargs["timeout"] = timeout
            # Close the credential after getting token
            await credential.close()
            return AsyncAzureOpenAI(**kwargs)
        await credential.close()
    except Exception as exc:
        logger.debug(
            "azure_auth: DefaultAzureCredential unavailable (%s), falling back to API Key",
            exc,
        )
        # Ensure credential is closed on error
        try:
            await credential.close()  # type: ignore[possibly-undefined]
        except Exception:
            pass

    # 2. Fallback to API Key
    if api_key:
        logger.debug("azure_auth: creating AsyncAzureOpenAI with API Key for %s", endpoint)
        kwargs = {
            "azure_endpoint": endpoint,
            "api_key": api_key,
            "api_version": api_version,
        }
        if timeout is not None:
            kwargs["timeout"] = timeout
        return AsyncAzureOpenAI(**kwargs)

    raise RuntimeError(
        f"No Azure credentials available for {endpoint}. "
        "Either run 'az login' for Entra ID or configure an API key in admin panel."
    )


async def get_auth_headers(api_key: str = "") -> dict[str, str]:
    """Get authentication headers for Azure Cognitive Services REST calls.

    Uses AAD token first, falls back to API key.
    This is useful for services like Content Understanding that use raw HTTP.

    Returns:
        Dict with Authorization or Ocp-Apim-Subscription-Key header + Content-Type.

    Raises:
        RuntimeError: If no credentials are available.
    """
    # 1. Try AAD token
    token = await get_bearer_token(COGNITIVE_SERVICES_SCOPE)
    if token:
        logger.debug("azure_auth: using Entra ID token for HTTP headers")
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    # 2. Fallback to API Key
    if api_key:
        logger.debug("azure_auth: using API Key for HTTP headers")
        return {
            "Ocp-Apim-Subscription-Key": api_key,
            "Content-Type": "application/json",
        }

    raise RuntimeError(
        "No Azure credentials available. "
        "Either run 'az login' for Entra ID or configure an API key."
    )
