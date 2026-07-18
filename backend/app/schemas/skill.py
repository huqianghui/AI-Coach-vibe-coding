"""Skill request/response schemas (Pydantic v2)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SkillCreate(BaseModel):
    """Create a new skill."""

    name: str
    description: str = ""
    product: str = ""
    therapeutic_area: str = ""
    compatibility: str = ""
    tags: str = ""
    content: str = ""
    metadata_json: str = "{}"


class SkillUpdate(BaseModel):
    """Update an existing skill. All fields optional for partial updates."""

    name: str | None = None
    description: str | None = None
    product: str | None = None
    therapeutic_area: str | None = None
    compatibility: str | None = None
    tags: str | None = None
    content: str | None = None
    metadata_json: str | None = None
    status: str | None = None


class SkillResourceOut(BaseModel):
    """Response schema for a skill resource."""

    id: str
    skill_id: str
    version_id: str | None
    resource_type: str
    filename: str
    content_type: str
    file_size: int
    extraction_status: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SkillVersionOut(BaseModel):
    """Response schema for a skill version snapshot."""

    id: str
    skill_id: str
    version_number: int
    content: str
    metadata_json: str
    change_notes: str
    is_published: bool
    created_by: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SkillListOut(BaseModel):
    """Skill list item response (without full content or relationships)."""

    id: str
    name: str
    description: str
    product: str
    status: str
    tags: str
    quality_score: int | None
    quality_verdict: str | None
    structure_check_passed: bool | None
    conversion_status: str | None
    current_version: int
    created_by: str
    created_at: datetime
    updated_at: datetime
    foundry_skill_name: str
    foundry_sync_status: str
    foundry_cloud_version: str
    foundry_sync_error: str

    model_config = ConfigDict(from_attributes=True)


class SourceMaterialInfo(BaseModel):
    """Lightweight reference to a source training material."""

    id: str
    name: str
    product: str

    model_config = ConfigDict(from_attributes=True)


class SkillOut(SkillListOut):
    """Full skill response with content and relationships."""

    therapeutic_area: str
    compatibility: str
    metadata_json: str
    content: str
    structure_check_details: str
    quality_details: str
    conversion_error: str
    resources: list[SkillResourceOut] = []
    versions: list[SkillVersionOut] = []
    source_materials: list[SourceMaterialInfo] = []


class StructureCheckOut(BaseModel):
    """Response schema for L1 structure check result."""

    passed: bool
    score: int
    issues: list[dict]


class QualityEvaluationOut(BaseModel):
    """Response schema for L2 AI quality evaluation result."""

    overall_score: int
    overall_verdict: str
    dimensions: list[dict]
    summary: str
    top_improvements: list[str]


class SkillFoundryPortalUrlResponse(BaseModel):
    """Response schema for the Skill Foundry portal deep-link."""

    url: str
    skill_name: str
    foundry_version: str
