"""Pydantic v2 schemas for the prompt management API (list/detail/versions/runs)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PromptVersionResponse(BaseModel):
    """One immutable prompt version."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    template_id: str
    version_no: int
    content: str
    source: str
    parent_version_id: str | None = None
    note: str = ""
    created_by: str | None = None
    is_active: bool
    created_at: datetime


class PromptSummary(BaseModel):
    """List-row view of a registered prompt."""

    key: str
    name: str
    category: str
    is_system: bool
    active_version_no: int | None = None
    updated_at: datetime
    last_optimized_at: datetime | None = None


class PromptResponse(BaseModel):
    """Detail view of a prompt template with its active version."""

    key: str
    name: str
    category: str
    description: str
    is_system: bool
    variables: list[str]
    active_version: PromptVersionResponse | None = None


class PromptOptimizationRunResponse(BaseModel):
    """An auditable record of one optimizer invocation."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    template_id: str
    base_version_id: str | None = None
    mode: str
    optimizer_template: str | None = None
    requirements: str | None = None
    result_content: str
    model: str
    status: str
    error_message: str | None = None
    resulting_version_id: str | None = None
    created_by: str | None = None
    created_at: datetime


class PromptUpdateRequest(BaseModel):
    """Save an edited prompt as a new manual version (and activate it)."""

    content: str
    note: str = ""


class PromptCreateRequest(BaseModel):
    """Register a brand-new prompt with its version 1 content."""

    key: str
    name: str
    content: str
    category: str = "general"
    description: str = ""
    variables: list[str] = []
    is_system: bool = False


class PromptMetaUpdateRequest(BaseModel):
    """Update editable prompt metadata (name/category/description/variables/is_system).

    Every field is optional; only provided fields are changed. Content is versioned
    separately via :class:`PromptUpdateRequest`.
    """

    name: str | None = None
    category: str | None = None
    description: str | None = None
    variables: list[str] | None = None
    is_system: bool | None = None


class OptimizeRecordRequest(BaseModel):
    """Optimize the active version of a prompt and record the run."""

    mode: str = "system"
    requirements: str | None = None
    template: str | None = None


class OptimizeRunResponse(BaseModel):
    """Result of a recorded optimization: the run id plus the optimized text."""

    run_id: str
    optimized_prompt: str


class AdoptRunRequest(BaseModel):
    """Adopt an optimization run's result as a new active version."""

    run_id: str
    note: str = ""
