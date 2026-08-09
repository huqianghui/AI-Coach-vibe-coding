"""Scenario request/response schemas."""

from pydantic import BaseModel, Field


class ModeratorRemarks(BaseModel):
    """Localized moderator remarks for conference flow phases."""

    zh: str = ""
    en: str = ""


class ConferencePromptConfig(BaseModel):
    """Configurable conference orchestration prompts."""

    speaker_order_policy: str = ""
    audience_prompt_template: str = ""
    moderator_remarks: dict[str, ModeratorRemarks] = Field(default_factory=dict)


class ScenarioCreate(BaseModel):
    """Create a new scenario."""

    name: str
    hcp_profile_id: str
    rubric_id: str
    skill_id: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    mode: str = "f2f"
    difficulty: str = "medium"
    key_messages: list[str] = Field(default_factory=list)
    conference_prompt_config: ConferencePromptConfig | None = None
    pass_threshold: int = 70


class ScenarioUpdate(BaseModel):
    """Update an existing scenario. All fields optional for partial updates."""

    name: str | None = None
    hcp_profile_id: str | None = None
    rubric_id: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    mode: str | None = None
    difficulty: str | None = None
    key_messages: list[str] | None = None
    conference_prompt_config: ConferencePromptConfig | None = None
    skill_id: str | None = None
    pass_threshold: int | None = None
