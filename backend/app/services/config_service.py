"""Config service: CRUD operations for Azure service configurations with encryption.

Supports unified AI Foundry master config pattern: a single master row
(service_name='ai_foundry', is_master=True) stores the shared endpoint, region,
and API key. Per-service rows are enable/disable toggles with service-specific
deployment names, inheriting endpoint and key from master when empty.
"""

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.service_config import ServiceConfig
from app.schemas.azure_config import (
    AIFoundryConfigUpdate,
    ServiceConfigResponse,
    ServiceConfigUpdate,
)
from app.services.secret_store import get_secret_store, is_keyvault_secret_store


async def get_all_configs(db: AsyncSession) -> list[ServiceConfigResponse]:
    """Return all service configs with masked API keys."""
    result = await db.execute(select(ServiceConfig))
    rows = result.scalars().all()
    configs = []
    secret_store = get_secret_store()
    for row in rows:
        masked_key = await secret_store.mask_secret(row.service_name, row.api_key_encrypted)
        configs.append(
            ServiceConfigResponse(
                service_name=row.service_name,
                display_name=row.display_name,
                endpoint=row.endpoint,
                masked_key=masked_key,
                model_or_deployment=row.model_or_deployment,
                region=row.region,
                default_project=row.default_project,
                is_master=row.is_master,
                is_active=row.is_active,
                updated_at=row.updated_at,
            )
        )
    return configs


async def get_config(db: AsyncSession, service_name: str) -> ServiceConfig | None:
    """Return a single ServiceConfig by service_name, or None if not found."""
    result = await db.execute(
        select(ServiceConfig).where(ServiceConfig.service_name == service_name)
    )
    return result.scalar_one_or_none()


async def get_master_config(db: AsyncSession) -> ServiceConfig | None:
    """Return the AI Foundry master config row, or None if not configured."""
    result = await db.execute(
        select(ServiceConfig).where(ServiceConfig.is_master == True)  # noqa: E712
    )
    return result.scalar_one_or_none()


async def ensure_voice_live_config(
    db: AsyncSession, master: ServiceConfig, updated_by: str
) -> None:
    """Create the Voice Live service toggle when Foundry has enough config.

    Voice Live inherits endpoint and credentials from the master AI Foundry row.
    The per-service row is still required because the rest of the app uses it as
    an explicit feature toggle.
    """
    if not master.endpoint or not master.default_project:
        return

    existing = await get_config(db, "azure_voice_live")
    if existing is not None:
        return

    mode_json = json.dumps(
        {
            "mode": "agent",
            "agent_id": "",
            "project_name": master.default_project,
        }
    )
    db.add(
        ServiceConfig(
            service_name="azure_voice_live",
            display_name="Azure Voice Live",
            endpoint="",
            api_key_encrypted="",
            model_or_deployment=mode_json,
            region="",
            is_master=False,
            is_active=True,
            updated_by=updated_by,
        )
    )
    await db.flush()


async def upsert_master_config(
    db: AsyncSession,
    update: AIFoundryConfigUpdate,
    updated_by: str,
) -> ServiceConfig:
    """Create or update the AI Foundry master configuration row.

    The master row stores the shared endpoint, region, and encrypted API key
    used by all per-service toggle rows that lack their own credentials.
    """
    existing = await get_master_config(db)
    secret_store = get_secret_store()

    if existing:
        existing.endpoint = update.endpoint
        existing.region = update.region
        existing.model_or_deployment = update.model_or_deployment
        existing.default_project = update.default_project
        existing.updated_by = updated_by
        existing.is_active = True
        if update.api_key:
            existing.api_key_encrypted = await secret_store.set_secret(
                "ai_foundry",
                update.api_key,
            )
        elif is_keyvault_secret_store():
            existing.api_key_encrypted = ""
        await db.flush()
        await ensure_voice_live_config(db, existing, updated_by)
        return existing
    else:
        config = ServiceConfig(
            service_name="ai_foundry",
            display_name="Azure AI Foundry",
            endpoint=update.endpoint,
            api_key_encrypted=(
                await secret_store.set_secret("ai_foundry", update.api_key)
                if update.api_key
                else ""
            ),
            model_or_deployment=update.model_or_deployment,
            default_project=update.default_project,
            region=update.region,
            is_master=True,
            is_active=True,
            updated_by=updated_by,
        )
        db.add(config)
        await db.flush()
        await ensure_voice_live_config(db, config, updated_by)
        return config


async def upsert_config(
    db: AsyncSession,
    service_name: str,
    display_name: str,
    update: ServiceConfigUpdate,
    updated_by: str,
) -> ServiceConfig:
    """Create or update a service configuration.

    If the service_name already exists, update its fields.
    If update.api_key is non-empty, encrypt and store it.
    If update.api_key is empty, preserve the existing encrypted key.
    """
    existing = await get_config(db, service_name)
    secret_store = get_secret_store()

    if existing:
        existing.display_name = display_name
        existing.endpoint = update.endpoint
        existing.model_or_deployment = update.model_or_deployment
        existing.region = update.region
        existing.is_active = (
            update.is_active if update.is_active is not None else existing.is_active
        )
        existing.updated_by = updated_by
        if update.api_key:
            existing.api_key_encrypted = await secret_store.set_secret(
                service_name,
                update.api_key,
            )
        elif is_keyvault_secret_store():
            existing.api_key_encrypted = ""
        await db.flush()
        return existing
    else:
        config = ServiceConfig(
            service_name=service_name,
            display_name=display_name,
            endpoint=update.endpoint,
            api_key_encrypted=(
                await secret_store.set_secret(service_name, update.api_key)
                if update.api_key
                else ""
            ),
            model_or_deployment=update.model_or_deployment,
            region=update.region,
            is_active=update.is_active if update.is_active is not None else True,
            updated_by=updated_by,
        )
        db.add(config)
        await db.flush()
        return config


async def get_decrypted_key(db: AsyncSession, service_name: str) -> str:
    """Return the decrypted API key for a given service_name, or empty string."""
    config = await get_config(db, service_name)
    if config is None:
        return ""
    return await get_secret_store().get_secret(config.service_name, config.api_key_encrypted)


async def get_effective_key(db: AsyncSession, service_name: str) -> str:
    """Return the effective API key for a service.

    If the per-service row has its own encrypted key, return that.
    Otherwise, fall back to the master AI Foundry key.
    """
    per_service_key = await get_decrypted_key(db, service_name)
    if per_service_key:
        return per_service_key
    master = await get_master_config(db)
    if master:
        return await get_secret_store().get_secret(
            master.service_name,
            master.api_key_encrypted,
        )
    return ""


async def get_effective_endpoint(db: AsyncSession, service_name: str) -> str:
    """Return the effective endpoint for a service.

    If the per-service row has its own endpoint, return that.
    Otherwise, fall back to the master AI Foundry endpoint.
    """
    config = await get_config(db, service_name)
    if config and config.endpoint:
        return config.endpoint
    master = await get_master_config(db)
    if master:
        return master.endpoint
    return ""


async def get_effective_region(db: AsyncSession, service_name: str) -> str:
    """Return the effective Azure region for a service, falling back to master config."""
    config = await get_config(db, service_name)
    if config and config.region:
        return config.region
    master = await get_master_config(db)
    if master:
        return master.region
    return ""


async def get_effective_model(db: AsyncSession, service_name: str) -> str:
    """Return the effective model/deployment for a service, falling back to master config."""
    config = await get_config(db, service_name)
    if config and config.model_or_deployment:
        return config.model_or_deployment
    master = await get_master_config(db)
    if master:
        return master.model_or_deployment
    return ""
