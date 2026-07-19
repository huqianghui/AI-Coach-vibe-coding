"""Response schemas for the Agent Foundation Model catalog endpoint (D-14).

Deliberately minimal — only id/label are exposed. Do not add any other raw
deployment metadata fields to this schema (T-29-08-01 mitigation).
"""

from pydantic import BaseModel


class AgentFoundationModelInfo(BaseModel):
    """A single chat-capable Foundry deployment, minimal fields only."""

    id: str
    label: str


class AgentFoundationModelsResponse(BaseModel):
    """Response envelope for GET /agent-foundation-models."""

    models: list[AgentFoundationModelInfo]
    stale: bool = False
    error: str | None = None
