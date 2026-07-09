import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import (
    admin_users_router,
    analytics_router,
    auth_router,
    azure_config_router,
    conference_router,
    config_router,
    dry_runs_router,
    hcp_profiles_router,
    knowledge_base_router,
    materials_router,
    meta_skills_router,
    prompts_router,
    rubrics_router,
    scenario_groups_router,
    scenarios_router,
    scoring_router,
    sessions_router,
    skills_router,
    speech_router,
    system_enums_router,
    voice_live_router,
)
from app.api.health import router as health_router
from app.config import get_settings
from app.database import engine
from app.middleware import RequestLoggingMiddleware
from app.startup import init_tables, load_service_configs, register_adapters, run_seed
from app.utils.exceptions import AppException

# Configure root logger so all app.* loggers produce output.
# Without this, only uvicorn's own logger produces output.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)
settings = get_settings()

# Apply configurable log level (LOG_LEVEL env var → settings.log_level)
logging.getLogger().setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s", settings.app_name)
    await init_tables()
    register_adapters()
    await run_seed()
    await load_service_configs()
    # Seed default meta skill configs (creator + evaluator)
    from app.database import AsyncSessionLocal
    from app.services.meta_skill_service import ensure_defaults

    async with AsyncSessionLocal() as db:
        await ensure_defaults(db)
    logger.info("Startup complete")
    yield
    await engine.dispose()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
)

# Middleware (order matters: CORS first, then logging)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)


# Global exception handlers
@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all: logs full traceback so 500 errors are visible in server logs."""
    logger.exception(
        "Unhandled exception on %s %s: %s",
        request.method,
        request.url.path,
        exc,
    )
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred. Please try again later.",
            "details": None,
        },
    )


# Routers
app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(config_router, prefix=settings.api_prefix)
app.include_router(hcp_profiles_router, prefix=settings.api_prefix)
app.include_router(scenarios_router, prefix=settings.api_prefix)
app.include_router(scenario_groups_router, prefix=settings.api_prefix)
app.include_router(sessions_router, prefix=settings.api_prefix)
app.include_router(scoring_router, prefix=settings.api_prefix)
app.include_router(rubrics_router, prefix=settings.api_prefix)
app.include_router(azure_config_router, prefix=settings.api_prefix)
app.include_router(knowledge_base_router, prefix=settings.api_prefix)
app.include_router(materials_router, prefix=settings.api_prefix)
app.include_router(conference_router, prefix=settings.api_prefix)
app.include_router(analytics_router, prefix=settings.api_prefix)
app.include_router(voice_live_router, prefix=settings.api_prefix)
app.include_router(skills_router, prefix=settings.api_prefix)
app.include_router(dry_runs_router, prefix=settings.api_prefix)
app.include_router(meta_skills_router, prefix=settings.api_prefix)
app.include_router(speech_router, prefix=settings.api_prefix)
app.include_router(prompts_router, prefix=settings.api_prefix)
app.include_router(admin_users_router, prefix=settings.api_prefix)
app.include_router(system_enums_router, prefix=settings.api_prefix)

# Health check (standalone router, no api_prefix)
app.include_router(health_router)
