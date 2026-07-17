"""Health check endpoints.

- /api/health — lightweight liveness probe (no DB)
- /api/health/deep — readiness probe checking DB, adapters, and config
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health_liveness():
    """Liveness probe — always returns healthy if the process is running."""
    from app.config import get_settings

    settings = get_settings()
    return {"status": "healthy", "service": settings.app_name}


@router.get("/api/health/deep")
async def health_deep(db: AsyncSession = Depends(get_db)):
    """Readiness probe — checks database, adapters, and config."""
    checks: dict[str, dict] = {}

    # 1. Database
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok"}
    except Exception as e:
        checks["database"] = {"status": "error", "detail": str(e)[:200]}

    # 2. Adapters
    from app.services.agents.registry import registry

    adapter_status = {}
    for category in ("llm", "stt", "tts", "avatar"):
        adapters = registry._categories.get(category, {})
        if adapters:
            adapter_status[category] = list(adapters.keys())
        else:
            adapter_status[category] = []
    checks["adapters"] = {"status": "ok", "registered": adapter_status}

    # 3. Azure config
    from app.services import config_service

    try:
        azure_config = await config_service.get_master_config(db)
        if azure_config:
            checks["azure_foundry"] = {
                "status": "ok",
                "endpoint_set": bool(azure_config.endpoint),
            }
        else:
            checks["azure_foundry"] = {"status": "not_configured"}
    except Exception as e:
        checks["azure_foundry"] = {"status": "error", "detail": str(e)[:200]}

    # 4. Active providers
    from app.config import get_settings

    settings = get_settings()
    checks["active_providers"] = {
        "llm": settings.default_llm_provider,
        "stt": settings.default_stt_provider,
        "tts": settings.default_tts_provider,
    }

    # Overall status
    has_error = any(c.get("status") == "error" for c in checks.values())
    overall = "degraded" if has_error else "healthy"

    return {"status": overall, "checks": checks}
