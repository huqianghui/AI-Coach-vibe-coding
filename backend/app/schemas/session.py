"""Coaching Session request/response schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class SessionCreate(BaseModel):
    """Create a new coaching session."""

    scenario_id: str
    mode: Literal[
        "text",
        "voice_pipeline",
        "digital_human_pipeline",
        "voice_realtime_model",
        "digital_human_realtime_model",
        "voice_realtime_agent",
        "digital_human_realtime_agent",
    ] = "text"


class SendMessageRequest(BaseModel):
    """Send a message in a coaching session."""

    message: str


class TranscriptMessageRequest(BaseModel):
    """Persist a voice transcript message (no LLM response triggered)."""

    message: str
    role: Literal["user", "assistant"] = "user"


class MessageResponse(BaseModel):
    """Individual message response."""

    id: str
    session_id: str
    role: str
    content: str
    message_index: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SessionResponse(BaseModel):
    """Coaching session response with all fields."""

    id: str
    user_id: str
    scenario_id: str
    scenario_name: str | None = None
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    duration_seconds: int | None
    key_messages_status: str  # JSON string from DB
    overall_score: float | None
    passed: bool | None
    mode: str = "text"
    audio_url: str | None = None
    voice_score_status: str = "none"
    message_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
