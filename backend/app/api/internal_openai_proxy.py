"""Internal OpenAI-compatible proxy used by the prompt-optimizer sidecar."""

import hmac
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.dependencies import get_db
from app.models.service_config import ServiceConfig
from app.services import config_service
from app.utils.exceptions import AppException

router = APIRouter(prefix="/internal/openai/v1", tags=["internal-openai-proxy"])

_SERVICE_NAME = "prompt_optimizer"


def _extract_token(authorization: str, api_key: str) -> str:
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return api_key.strip()


def _require_proxy_secret(authorization: str = Header(""), api_key: str = Header("")) -> None:
    settings = get_settings()
    expected = settings.prompt_optimizer_proxy_secret
    if not expected:
        raise AppException(
            status_code=503,
            code="PROMPT_OPTIMIZER_PROXY_NOT_CONFIGURED",
            message="Prompt optimizer proxy secret is not configured.",
        )

    provided = _extract_token(authorization, api_key)
    if not provided or not hmac.compare_digest(provided, expected):
        raise AppException(
            status_code=401,
            code="PROMPT_OPTIMIZER_PROXY_UNAUTHORIZED",
            message="Invalid prompt optimizer proxy credential.",
        )


async def _get_active_optimizer_config(db: AsyncSession) -> ServiceConfig:
    config = await config_service.get_config(db, _SERVICE_NAME)
    if config is None or not config.is_active:
        raise AppException(
            status_code=503,
            code="PROMPT_OPTIMIZER_DISABLED",
            message="Prompt Optimizer is not enabled in Admin Azure Config.",
        )
    return config


async def _resolve_optimizer_target(db: AsyncSession) -> tuple[str, str, str]:
    await _get_active_optimizer_config(db)
    endpoint = await config_service.get_effective_endpoint(db, _SERVICE_NAME)
    model = await config_service.get_effective_model(db, _SERVICE_NAME)
    api_key = await config_service.get_effective_key(db, _SERVICE_NAME)

    if not endpoint:
        raise AppException(
            status_code=503,
            code="PROMPT_OPTIMIZER_MASTER_CONFIG_MISSING",
            message="AI Foundry master endpoint is required for Prompt Optimizer.",
        )
    if not model:
        raise AppException(
            status_code=503,
            code="PROMPT_OPTIMIZER_MODEL_MISSING",
            message="Prompt Optimizer requires a model in its config or AI Foundry master config.",
        )

    return endpoint, model, api_key


@router.get("/models")
async def list_models(
    _auth: None = Depends(_require_proxy_secret),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return the effective optimizer model in OpenAI-compatible shape."""
    _, model, _ = await _resolve_optimizer_target(db)
    return {
        "object": "list",
        "data": [
            {
                "id": model,
                "object": "model",
                "created": 0,
                "owned_by": "ai-coach",
            }
        ],
    }


@router.post("/chat/completions")
async def create_chat_completion(
    request: Request,
    _auth: None = Depends(_require_proxy_secret),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Proxy optimizer chat completions through configured Azure auth and model override."""
    body = await request.json()
    if not isinstance(body, dict):
        raise AppException(
            status_code=422,
            code="INVALID_OPENAI_PROXY_REQUEST",
            message="OpenAI-compatible request body must be a JSON object.",
        )

    endpoint, model, api_key = await _resolve_optimizer_target(db)
    payload = dict(body)
    payload["model"] = model

    try:
        from app.services.azure_auth import get_azure_openai_client

        client = await get_azure_openai_client(
            endpoint=endpoint,
            api_key=api_key,
            api_version=get_settings().prompt_optimizer_proxy_api_version,
            timeout=get_settings().prompt_optimizer_timeout_seconds,
        )
        response = await client.chat.completions.create(**payload)
    except AppException:
        raise
    except RuntimeError as exc:
        raise AppException(
            status_code=503,
            code="PROMPT_OPTIMIZER_AZURE_AUTH_UNAVAILABLE",
            message=str(exc),
        ) from exc
    except Exception as exc:
        raise AppException(
            status_code=502,
            code="PROMPT_OPTIMIZER_PROXY_UPSTREAM_ERROR",
            message=f"Prompt optimizer model proxy failed: {exc}",
        ) from exc

    return JSONResponse(content=response.model_dump(mode="json"))
