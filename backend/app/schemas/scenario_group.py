"""Scenario group request/response schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.api.scenarios import ScenarioOut


class ScenarioGroupItemCreate(BaseModel):
    """Create or update a weighted scenario inside a group."""

    scenario_id: str
    weight: int = Field(default=100, ge=1, le=1000)
    sort_order: int = 0


class ScenarioGroupCreate(BaseModel):
    """Create a scenario group."""

    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    pass_threshold: int = Field(default=70, ge=0, le=100)
    items: list[ScenarioGroupItemCreate] = Field(min_length=1)

    @model_validator(mode="after")
    def ensure_unique_scenarios(self) -> "ScenarioGroupCreate":
        ids = [item.scenario_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Scenario group cannot contain duplicate scenarios")
        if sum(item.weight for item in self.items) != 100:
            raise ValueError("Scenario group weights must sum to 100")
        return self


class ScenarioGroupUpdate(BaseModel):
    """Update a scenario group."""

    name: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    pass_threshold: int | None = Field(default=None, ge=0, le=100)
    items: list[ScenarioGroupItemCreate] | None = None

    @model_validator(mode="after")
    def ensure_unique_scenarios(self) -> "ScenarioGroupUpdate":
        if self.items is None:
            return self
        ids = [item.scenario_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Scenario group cannot contain duplicate scenarios")
        if sum(item.weight for item in self.items) != 100:
            raise ValueError("Scenario group weights must sum to 100")
        return self


class ScenarioGroupItemResponse(BaseModel):
    """Weighted scenario group item response."""

    id: str
    group_id: str
    scenario_id: str
    weight: int
    sort_order: int
    scenario: ScenarioOut | None = None

    model_config = ConfigDict(from_attributes=True)


class ScenarioGroupResponse(BaseModel):
    """Scenario group response."""

    id: str
    name: str
    description: str
    tags: list[str]
    status: str
    pass_threshold: int
    created_by: str
    items: list[ScenarioGroupItemResponse]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            import json

            return json.loads(value)
        return value


class ScenarioGroupTransitionRequest(BaseModel):
    """Request body for scenario group status transition."""

    status: str


class ScenarioGroupRunItemResponse(BaseModel):
    """Per-scenario progress within a group run."""

    id: str
    run_id: str
    group_item_id: str
    scenario_id: str
    session_id: str | None = None
    status: str
    weight: int
    sort_order: int
    score: float | None = None
    passed: bool | None = None
    scenario: ScenarioOut | None = None

    model_config = ConfigDict(from_attributes=True)


class ScenarioGroupRunResponse(BaseModel):
    """Scenario group run response."""

    id: str
    user_id: str
    group_id: str
    group_name: str | None = None
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    overall_score: float | None = None
    passed: bool | None = None
    items: list[ScenarioGroupRunItemResponse]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ScenarioGroupRunSessionCreate(BaseModel):
    """Create a child session for one scenario in a group run."""

    mode: str = "text"
    retrain: bool = False
