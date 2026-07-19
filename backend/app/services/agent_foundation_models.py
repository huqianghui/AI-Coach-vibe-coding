"""Agent Foundation Model catalog service (D-14).

Live-pulls chat-capable model deployments from the connected AI Foundry
project via ``AIProjectClient.deployments.list()`` (data-plane, same
endpoint/credential already used by ``agent_sync_service``), defensively
filters out anything matching the Voice Live realtime catalog
(``VOICE_LIVE_MODELS``) or lacking chat-completion capability signals, and
caches the result in-process for ``CACHE_TTL_SECONDS`` to avoid hammering
the live Foundry API (T-29-08-02 mitigation).

This catalog is intentionally separate from ``VOICE_LIVE_MODELS`` — the two
must never be mixed (see 29-CONTEXT.md "两者不再混用").
"""

import logging
import time

from app.services.voice_live_models import VOICE_LIVE_MODELS

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 300

_cache: dict = {"data": None, "fetched_at": 0.0}

_EXCLUDED_NAMES = {k.lower() for k in VOICE_LIVE_MODELS}
_POSITIVE_SIGNALS = {"chat_completion", "chat", "responses", "completion"}
_NEGATIVE_SIGNALS = {"embeddings", "embedding", "image_generation", "audio_transcription"}


def _is_chat_capable(model_name: str, capabilities: dict[str, str] | None) -> bool:
    """Return True if the deployment should be surfaced as a chat model.

    Defensive filter: excludes anything already in the Voice Live realtime
    catalog (by model_name, case-insensitive), then checks capability keys
    for positive/negative chat-completion signals. Unknown/empty capability
    shapes default to INCLUDED (defensive default — better to over-include
    than to silently hide a real deployment).
    """
    if (model_name or "").lower() in _EXCLUDED_NAMES:
        return False
    caps_keys = {k.lower() for k in (capabilities or {})}
    if caps_keys & _POSITIVE_SIGNALS:
        return True
    if caps_keys & _NEGATIVE_SIGNALS:
        return False
    return True


def _build_project_endpoint(base_endpoint: str, project_name: str) -> str:
    """Compose the project-scoped endpoint AIProjectClient requires.

    AIProjectClient needs ``{base}/api/projects/{project_name}``, not the
    bare account endpoint (live-verified in 29-01 POC). Mirrors the
    composition logic in ``agent_sync_service.get_project_endpoint`` but
    operates on Settings fields only (this service has no DB session).
    """
    base = (base_endpoint or "").rstrip("/")
    if "/api/projects/" in base:
        return base
    if project_name:
        return f"{base}/api/projects/{project_name}"
    return base


def _get_project_client(endpoint: str, api_key: str = ""):
    """Create an AIProjectClient — prefers Entra ID, falls back to API Key.

    Mirrors ``agent_sync_service._get_project_client`` exactly, reusing
    ``_ApiKeyTokenCredential`` from that module rather than re-implementing it.
    """
    from azure.ai.projects import AIProjectClient

    try:
        from azure.identity import DefaultAzureCredential

        credential = DefaultAzureCredential()
        credential.get_token("https://ai.azure.com/.default")
        logger.info("_get_project_client: using DefaultAzureCredential (Entra ID)")
        return AIProjectClient(endpoint=endpoint, credential=credential)
    except Exception as exc:
        logger.debug("_get_project_client: DefaultAzureCredential unavailable: %s", exc)

    if api_key:
        from azure.core.credentials import AzureKeyCredential
        from azure.core.pipeline.policies import AzureKeyCredentialPolicy

        from app.services.agent_sync_service import _ApiKeyTokenCredential

        logger.info("_get_project_client: using API Key authentication")
        return AIProjectClient(
            endpoint=endpoint,
            credential=_ApiKeyTokenCredential(api_key),
            authentication_policy=AzureKeyCredentialPolicy(
                credential=AzureKeyCredential(api_key),
                name="api-key",
            ),
        )

    raise ValueError(
        "No valid credential available. Either run 'az login' for Entra ID or provide an API key."
    )


def list_agent_foundation_models(
    force_refresh: bool = False,
) -> tuple[list[dict], bool, str | None]:
    """Return (models, stale, error) — cached, defensively-filtered Foundry deployments.

    - Cache hit (within CACHE_TTL_SECONDS, no force_refresh): (cached_data, False, None)
    - Fresh fetch success: (models, False, None), cache updated
    - Fetch failure with prior cache: (stale_cached_data, True, error_message)
    - Fetch failure with no prior cache: ([], False, error_message)
    """
    if (
        not force_refresh
        and _cache["data"] is not None
        and (time.time() - _cache["fetched_at"]) < CACHE_TTL_SECONDS
    ):
        return _cache["data"], False, None

    from app.config import get_settings

    settings = get_settings()
    try:
        endpoint = _build_project_endpoint(
            settings.azure_foundry_endpoint, settings.azure_foundry_default_project
        )
        client = _get_project_client(endpoint, settings.azure_foundry_api_key)
        models = [
            {"id": d.name, "label": d.model_name or d.name}
            for d in client.deployments.list()
            if _is_chat_capable(d.model_name, getattr(d, "capabilities", None))
        ]
        _cache["data"] = models
        _cache["fetched_at"] = time.time()
        return models, False, None
    except Exception as exc:
        logger.warning("list_agent_foundation_models: fetch failed: %s", exc)
        if _cache["data"] is not None:
            return _cache["data"], True, str(exc)
        return [], False, str(exc)
