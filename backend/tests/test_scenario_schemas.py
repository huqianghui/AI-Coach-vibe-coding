"""Tests for Scenario Pydantic schemas: validation, defaults, and serialization."""

import pytest
from pydantic import ValidationError

from app.schemas.scenario import ScenarioCreate, ScenarioUpdate


class TestScenarioCreate:
    """Tests for ScenarioCreate schema validation."""

    def test_requires_name(self):
        with pytest.raises(ValidationError):
            ScenarioCreate(
                hcp_profile_id="hcp-1",
                rubric_id="rubric-1",
                skill_id="skill-1",
            )

    def test_requires_hcp_profile_id(self):
        with pytest.raises(ValidationError):
            ScenarioCreate(
                name="S",
                rubric_id="rubric-1",
                skill_id="skill-1",
            )

    def test_requires_rubric_id(self):
        with pytest.raises(ValidationError):
            ScenarioCreate(
                name="S",
                hcp_profile_id="hcp-1",
                skill_id="skill-1",
            )

    def test_requires_skill_id(self):
        with pytest.raises(ValidationError):
            ScenarioCreate(
                name="S",
                hcp_profile_id="hcp-1",
                rubric_id="rubric-1",
            )

    def test_minimal_valid_create(self):
        data = ScenarioCreate(
            name="Test",
            hcp_profile_id="hcp-1",
            rubric_id="rubric-1",
            skill_id="skill-1",
        )
        assert data.name == "Test"
        assert data.skill_id == "skill-1"
        assert data.tags == []
        assert data.key_messages == []
        assert data.mode == "f2f"
        assert data.difficulty == "medium"
        assert data.pass_threshold == 70
        assert data.description == ""

    def test_full_create(self):
        data = ScenarioCreate(
            name="Full",
            hcp_profile_id="hcp-1",
            rubric_id="rubric-1",
            skill_id="skill-1",
            description="A full scenario",
            tags=["product:Drug", "area:Oncology"],
            mode="conference",
            difficulty="hard",
            key_messages=["KM1", "KM2"],
            pass_threshold=80,
        )
        assert data.tags == ["product:Drug", "area:Oncology"]
        assert data.mode == "conference"
        assert data.difficulty == "hard"
        assert data.pass_threshold == 80

    def test_no_product_field(self):
        """ScenarioCreate should NOT have product field."""
        data = ScenarioCreate(
            name="S",
            hcp_profile_id="hcp-1",
            rubric_id="rubric-1",
            skill_id="skill-1",
        )
        assert not hasattr(data, "product")

    def test_no_status_field(self):
        """ScenarioCreate should NOT have status field."""
        data = ScenarioCreate(
            name="S",
            hcp_profile_id="hcp-1",
            rubric_id="rubric-1",
            skill_id="skill-1",
        )
        # status should not be a field in the schema
        assert "status" not in data.model_fields


class TestScenarioUpdate:
    """Tests for ScenarioUpdate schema validation."""

    def test_all_fields_optional(self):
        data = ScenarioUpdate()
        assert data.name is None
        assert data.tags is None
        assert data.skill_id is None

    def test_partial_update(self):
        data = ScenarioUpdate(name="New", tags=["tag1"])
        assert data.name == "New"
        assert data.tags == ["tag1"]
        assert data.mode is None

    def test_no_status_field(self):
        """ScenarioUpdate should NOT have status field (transitions via API only)."""
        assert "status" not in ScenarioUpdate.model_fields

    def test_no_product_field(self):
        """ScenarioUpdate should NOT have product field."""
        assert "product" not in ScenarioUpdate.model_fields

    def test_exclude_unset(self):
        data = ScenarioUpdate(name="X")
        dumped = data.model_dump(exclude_unset=True)
        assert dumped == {"name": "X"}


# NOTE: ScenarioResponse and HcpProfileSummary were removed (Phase 30 review, WR-03)
# as dead, manually-synced duplicates of the live ScenarioOut/HcpProfileBrief
# schemas in backend/app/api/scenarios.py. Their coverage of the live response
# contract lives in backend/tests/test_scenarios_api.py and
# backend/tests/test_scenario_avatar_fields.py instead.
