"""Azure service configuration API: CRUD backed by DB with dynamic adapter registration.

Includes unified AI Foundry master config endpoints and per-service toggle management.
"""

import logging

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.dependencies import get_db, require_role
from app.models.user import User
from app.schemas.azure_config import (
    AIFoundryConfigUpdate,
    AIFoundryTestResult,
    ConnectionTestResult,
    ServiceConfigResponse,
    ServiceConfigUpdate,
)
from app.services import config_service
from app.services.connection_tester import (
    detect_region_from_endpoint,
    test_ai_foundry_endpoint,
    test_service_connection,
)
from app.services.region_capabilities import get_region_capabilities
from app.utils.exceptions import AppException

router = APIRouter(prefix="/azure-config", tags=["azure-config"])

settings = get_settings()

# Valid service names and their display labels
SERVICE_DISPLAY_NAMES = {
    "azure_openai": "Azure OpenAI",
    "azure_speech_stt": "Azure Speech (STT)",
    "azure_speech_tts": "Azure Speech (TTS)",
    "azure_avatar": "Azure AI Avatar",
    "azure_content": "Azure Content Understanding",
    "azure_voice_live": "Azure Voice Live API",
    "azure_openai_realtime": "Azure OpenAI Realtime",
}


async def register_adapter_from_config(
    service_name: str,
    endpoint: str,
    api_key: str,
    deployment: str,
    region: str,
    master_endpoint: str = "",
    master_key: str = "",
    master_region: str = "",
    master_model: str = "",
) -> None:
    """Dynamically register an adapter in the ServiceRegistry based on saved config.

    When per-service endpoint/key/model are empty, falls back to master AI Foundry values.
    """
    from app.services.agents.registry import registry

    effective_key = api_key or master_key
    effective_region = region or master_region
    effective_deployment = deployment or master_model
    effective_endpoint = endpoint or master_endpoint

    if service_name == "azure_openai" and effective_key:
        from app.services.agents.adapters.azure_openai import AzureOpenAIAdapter

        effective_endpoint = endpoint or (
            f"{master_endpoint.rstrip('/')}/" if master_endpoint else ""
        )
        adapter = AzureOpenAIAdapter(
            endpoint=effective_endpoint, api_key=effective_key, deployment=effective_deployment
        )
        registry.register("llm", adapter)
        settings.default_llm_provider = "azure_openai"

    elif (
        service_name == "azure_speech_stt"
        and effective_region
        and (effective_key or effective_endpoint)
    ):
        from app.services.agents.stt.azure import AzureSTTAdapter

        registry.register(
            "stt",
            AzureSTTAdapter(effective_key, effective_region, effective_endpoint),
        )
        settings.default_stt_provider = "azure"

    elif (
        service_name == "azure_speech_tts"
        and effective_region
        and (effective_key or effective_endpoint)
    ):
        from app.services.agents.tts.azure import AzureTTSAdapter

        registry.register(
            "tts",
            AzureTTSAdapter(effective_key, effective_region, effective_endpoint),
        )
        settings.default_tts_provider = "azure"

    elif service_name == "azure_avatar" and effective_key:
        from app.services.agents.avatar.azure import AzureAvatarAdapter

        registry.register(
            "avatar",
            AzureAvatarAdapter(effective_endpoint, effective_key, region=effective_region),
        )

    elif service_name == "azure_openai_realtime" and effective_key:
        from app.services.agents.adapters.azure_realtime import AzureRealtimeAdapter

        effective_endpoint = endpoint or master_endpoint
        adapter = AzureRealtimeAdapter(
            endpoint=effective_endpoint, api_key=effective_key, deployment=effective_deployment
        )
        registry.register("realtime", adapter)

    elif service_name == "azure_content" and effective_key:
        from app.services.agents.adapters.azure_content import AzureContentUnderstandingAdapter

        effective_endpoint = endpoint or master_endpoint
        adapter = AzureContentUnderstandingAdapter(
            endpoint=effective_endpoint, api_key=effective_key
        )
        registry.register("content_understanding", adapter)

    elif service_name == "azure_voice_live" and effective_key:
        from app.services.agents.adapters.azure_voice_live import AzureVoiceLiveAdapter

        effective_endpoint = endpoint or master_endpoint
        adapter = AzureVoiceLiveAdapter(
            endpoint=effective_endpoint,
            api_key=effective_key,
            model_or_deployment=effective_deployment,
            region=effective_region,
        )
        registry.register("voice_live", adapter)


# --- AI Foundry master config endpoints ---


@router.get("/ai-foundry", response_model=ServiceConfigResponse)
async def get_ai_foundry_config(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
) -> ServiceConfigResponse:
    """Return the master AI Foundry configuration."""
    master = await config_service.get_master_config(db)
    if not master:
        return ServiceConfigResponse(
            service_name="ai_foundry",
            display_name="Azure AI Foundry",
            endpoint="",
            masked_key="",
            model_or_deployment="",
            region="",
            default_project="",
            is_master=True,
            is_active=False,
            updated_at=None,
        )
    configs = await config_service.get_all_configs(db)
    masked_key = next(
        (cfg.masked_key for cfg in configs if cfg.service_name == master.service_name),
        "",
    )
    return ServiceConfigResponse(
        service_name=master.service_name,
        display_name=master.display_name,
        endpoint=master.endpoint,
        masked_key=masked_key,
        model_or_deployment=master.model_or_deployment,
        region=master.region,
        default_project=master.default_project,
        is_master=True,
        is_active=master.is_active,
        updated_at=master.updated_at,
    )


@router.put("/ai-foundry", response_model=ServiceConfigResponse, status_code=200)
async def update_ai_foundry_config(
    update: AIFoundryConfigUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role("admin")),
) -> ServiceConfigResponse:
    """Create or update the master AI Foundry configuration.

    After saving, re-registers all active per-service adapters with the new
    master endpoint/key for unified config propagation.
    """
    master = await config_service.upsert_master_config(db, update, admin.id)

    # Re-register all active per-service adapters with updated master config
    master_key = await config_service.get_decrypted_key(db, master.service_name)
    all_configs = await config_service.get_all_configs(db)
    for cfg in all_configs:
        if cfg.service_name in SERVICE_DISPLAY_NAMES and cfg.is_active:
            per_key = ""
            per_config = await config_service.get_config(db, cfg.service_name)
            if per_config:
                per_key = await config_service.get_decrypted_key(db, per_config.service_name)
            await register_adapter_from_config(
                cfg.service_name,
                cfg.endpoint,
                per_key,
                cfg.model_or_deployment,
                cfg.region,
                master_endpoint=master.endpoint,
                master_key=master_key,
                master_region=master.region,
                master_model=master.model_or_deployment,
            )

    masked_key = next(
        (cfg.masked_key for cfg in all_configs if cfg.service_name == master.service_name),
        "",
    )
    return ServiceConfigResponse(
        service_name=master.service_name,
        display_name=master.display_name,
        endpoint=master.endpoint,
        masked_key=masked_key,
        model_or_deployment=master.model_or_deployment,
        region=master.region,
        is_master=True,
        is_active=master.is_active,
        updated_at=master.updated_at,
    )


@router.post("/ai-foundry/test", response_model=AIFoundryTestResult)
async def test_ai_foundry(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
) -> AIFoundryTestResult:
    """Test AI Foundry connectivity and auto-detect region.

    Uses saved master config. If a model is configured, tests via chat completion.
    Returns the auto-detected Azure region on success.
    """
    master = await config_service.get_master_config(db)
    if not master:
        return AIFoundryTestResult(success=False, message="AI Foundry not configured")

    api_key = await config_service.get_decrypted_key(db, master.service_name)
    success, message = await test_ai_foundry_endpoint(
        master.endpoint, api_key, master.model_or_deployment
    )

    detected_region = ""
    if success:
        detected_region = await detect_region_from_endpoint(master.endpoint, api_key)
        if detected_region and detected_region != master.region:
            # Auto-update the region in the DB
            master.region = detected_region
            await db.flush()
            await db.commit()

    return AIFoundryTestResult(
        success=success,
        message=message,
        region=detected_region or master.region,
    )


# --- Shared lookups ---


@router.get("/model-deployments")
async def list_model_deployments(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
) -> list[dict[str, str]]:
    """Return model deployments from Azure AI Foundry.

    Uses the AI Foundry project-scoped deployments API
    (GET /api/projects/{project}/deployments?api-version=v1) to get the
    real-time list of deployed models.  Falls back to the legacy Azure OpenAI
    deployments API, then to DB service configs.

    This is a system-level service used by every page that needs a model
    selector dropdown (meta-skills, scoring config, etc.).
    """
    logger = logging.getLogger(__name__)

    master = await config_service.get_master_config(db)
    api_key = await config_service.get_decrypted_key(db, "ai_foundry") if master else ""
    if master and master.endpoint and api_key:
        base = master.endpoint.rstrip("/")
        project = master.default_project

        async with httpx.AsyncClient(timeout=10.0) as client:
            # --- Strategy 1: AI Foundry project-scoped deployments API ---
            if project:
                try:
                    url = f"{base}/api/projects/{project}/deployments?api-version=v1"
                    response = await client.get(url, headers={"api-key": api_key})
                    if response.status_code == 200:
                        items = response.json().get("data", response.json().get("value", []))
                        return [
                            {
                                "value": d["name"],
                                "label": f"{d['name']} ({d.get('modelName', '')})",
                            }
                            for d in items
                            if d.get("name")
                        ]
                except Exception as exc:
                    logger.warning("AI Foundry deployments API failed: %s", exc)

            # --- Strategy 2: legacy Azure OpenAI deployments API ---
            try:
                url = f"{base}/openai/deployments?api-version=2024-10-21"
                response = await client.get(url, headers={"api-key": api_key})
                if response.status_code == 200:
                    deployments = response.json().get("data", [])
                    return [
                        {
                            "value": d["id"],
                            "label": f"{d['id']} ({d.get('model', '')})",
                        }
                        for d in deployments
                        if d.get("id")
                    ]
            except Exception as exc:
                logger.warning("Azure OpenAI deployments API failed: %s", exc)

    # --- Strategy 3: fall back to DB master config deployment ---
    if master and master.model_or_deployment:
        return [
            {
                "value": master.model_or_deployment,
                "label": master.model_or_deployment,
            }
        ]
    return []


# --- Per-service config endpoints ---


@router.get("/region-capabilities/{region}")
async def get_capabilities(
    region: str,
    _admin: User = Depends(require_role("admin")),
) -> dict:
    """Return which Azure AI services are available in the given region."""
    return get_region_capabilities(region)


@router.get("/services", response_model=list[ServiceConfigResponse])
async def list_services(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
) -> list[ServiceConfigResponse]:
    """List all Azure services with their current configuration from the database."""
    return await config_service.get_all_configs(db)


@router.put("/services/{service_name}", response_model=ServiceConfigResponse, status_code=200)
async def update_service(
    service_name: str,
    update: ServiceConfigUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role("admin")),
) -> ServiceConfigResponse:
    """Create or update an Azure service configuration."""
    if service_name not in SERVICE_DISPLAY_NAMES:
        raise AppException(
            status_code=400,
            code="INVALID_SERVICE",
            message=f"Unknown service: {service_name}. Valid: {list(SERVICE_DISPLAY_NAMES.keys())}",
        )

    config = await config_service.upsert_config(
        db, service_name, SERVICE_DISPLAY_NAMES[service_name], update, admin.id
    )

    # Determine the effective API key (per-service or master fallback)
    api_key = update.api_key or await config_service.get_effective_key(db, service_name)

    # Get master config for fallback endpoint/region/model
    master = await config_service.get_master_config(db)
    master_endpoint = master.endpoint if master else ""
    master_key = await config_service.get_decrypted_key(db, master.service_name) if master else ""
    master_region = master.region if master else ""
    master_model = master.model_or_deployment if master else ""

    await register_adapter_from_config(
        service_name,
        config.endpoint,
        api_key,
        config.model_or_deployment,
        config.region,
        master_endpoint=master_endpoint,
        master_key=master_key,
        master_region=master_region,
        master_model=master_model,
    )

    # Return the saved config with masked key
    all_configs = await config_service.get_all_configs(db)
    for cfg in all_configs:
        if cfg.service_name == service_name:
            return cfg

    # Fallback (should not happen after upsert)
    return ServiceConfigResponse(
        service_name=service_name,
        display_name=SERVICE_DISPLAY_NAMES[service_name],
        endpoint=config.endpoint,
        masked_key="****",
        model_or_deployment=config.model_or_deployment,
        region=config.region,
        is_active=config.is_active,
        updated_at=config.updated_at,
    )


@router.post("/services/{service_name}/test", response_model=ConnectionTestResult)
async def test_service(
    service_name: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
) -> ConnectionTestResult:
    """Test connection to a specific Azure service using saved credentials.

    Falls back to master AI Foundry config when per-service credentials are empty.
    """
    config = await config_service.get_config(db, service_name)

    if config is None:
        return ConnectionTestResult(
            service_name=service_name,
            success=False,
            message="Service not configured",
        )

    api_key = await config_service.get_decrypted_key(db, service_name)

    # Get master config for fallback
    master = await config_service.get_master_config(db)
    master_endpoint = master.endpoint if master else ""
    master_key = await config_service.get_decrypted_key(db, master.service_name) if master else ""
    master_region = master.region if master else ""
    master_model = master.model_or_deployment if master else ""

    success, message = await test_service_connection(
        service_name,
        config.endpoint,
        api_key,
        config.model_or_deployment,
        config.region,
        master_endpoint=master_endpoint,
        master_key=master_key,
        master_region=master_region,
        master_model=master_model,
    )

    return ConnectionTestResult(
        service_name=service_name,
        success=success,
        message=message,
    )
