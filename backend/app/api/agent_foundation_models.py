"""Admin-scoped endpoint exposing the Agent Foundation Model catalog (D-14)."""

from fastapi import APIRouter, Depends

from app.dependencies import require_role
from app.models.user import User
from app.schemas.agent_foundation_model import (
    AgentFoundationModelInfo,
    AgentFoundationModelsResponse,
)
from app.services.agent_foundation_models import list_agent_foundation_models

router = APIRouter(prefix="/agent-foundation-models", tags=["agent-foundation-models"])


@router.get("", response_model=AgentFoundationModelsResponse, status_code=200)
async def get_agent_foundation_models(
    _admin: User = Depends(require_role("admin")),
) -> AgentFoundationModelsResponse:
    """Return the live, cached, chat-capable Foundry deployments catalog.

    Admin-only (T-29-08-01 mitigation): non-admin callers get 403 before the
    Foundry call is ever reached.
    """
    models, stale, error = list_agent_foundation_models()
    return AgentFoundationModelsResponse(
        models=[AgentFoundationModelInfo(**m) for m in models],
        stale=stale,
        error=error,
    )
