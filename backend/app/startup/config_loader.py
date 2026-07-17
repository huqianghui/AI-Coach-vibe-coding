"""Load service configs from DB and register real adapters at startup."""

import logging

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.service_config import ServiceConfig
from app.services import config_service

logger = logging.getLogger(__name__)


async def load_service_configs() -> None:
    """Load active ServiceConfig rows and register real adapters.

    Reads the master AI Foundry config first, then registers per-service
    adapters with master fallback for endpoint/key/region.

    Tolerates missing tables on first run.
    """
    from app.api.azure_config import register_adapter_from_config

    try:
        async with AsyncSessionLocal() as session:
            # Load master AI Foundry config
            master_endpoint = ""
            master_key = ""
            master_region = ""
            master_model = ""

            master_result = await session.execute(
                select(ServiceConfig).where(ServiceConfig.is_master == True)  # noqa: E712
            )
            master_cfg = master_result.scalar_one_or_none()
            if master_cfg:
                master_endpoint = master_cfg.endpoint
                master_key = await config_service.get_decrypted_key(
                    session,
                    master_cfg.service_name,
                )
                master_region = master_cfg.region
                master_model = master_cfg.model_or_deployment

            # Register per-service adapters with master fallback
            result = await session.execute(
                select(ServiceConfig).where(
                    ServiceConfig.is_active == True,  # noqa: E712
                    ServiceConfig.is_master == False,  # noqa: E712
                )
            )
            configs = result.scalars().all()
            registered = 0
            for cfg in configs:
                try:
                    api_key = await config_service.get_decrypted_key(session, cfg.service_name)
                    await register_adapter_from_config(
                        cfg.service_name,
                        cfg.endpoint,
                        api_key,
                        cfg.model_or_deployment,
                        cfg.region,
                        master_endpoint=master_endpoint,
                        master_key=master_key,
                        master_region=master_region,
                        master_model=master_model,
                    )
                    registered += 1
                except Exception:
                    logger.warning(
                        "Failed to register adapter for %s, skipping",
                        cfg.service_name,
                        exc_info=True,
                    )

            from app.config import get_settings

            settings = get_settings()
            logger.info(
                "Service configs loaded (%d active, %d registered, llm_provider=%s)",
                len(configs),
                registered,
                settings.default_llm_provider,
            )
    except Exception:
        logger.warning(
            "Service config loading skipped (table may not exist yet)",
            exc_info=True,
        )
