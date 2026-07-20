"""Tests for Phase 2 Pydantic schemas: validation rules and serialization."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas.hcp_profile import HcpProfileCreate, HcpProfileResponse, HcpProfileUpdate
from app.schemas.scenario import ScenarioCreate, ScenarioUpdate
from app.schemas.score import ScoreDetailResponse, SessionScoreResponse
from app.schemas.session import MessageResponse, SendMessageRequest, SessionCreate, SessionResponse


class TestScenarioCreateSchema:
    """Tests for ScenarioCreate validation with rubric_id and skill_id."""

    async def test_requires_rubric_id(self):
        data = ScenarioCreate(
            name="Test",
            tags=["product:Drug"],
            hcp_profile_id="p1",
            rubric_id="rubric-1",
            skill_id="skill-1",
        )
        assert data.rubric_id == "rubric-1"

    async def test_default_mode_and_difficulty(self):
        data = ScenarioCreate(
            name="Test",
            tags=["product:Drug"],
            hcp_profile_id="p1",
            rubric_id="rubric-1",
            skill_id="skill-1",
        )
        assert data.mode == "f2f"
        assert data.difficulty == "medium"
        assert data.pass_threshold == 70

    async def test_missing_rubric_id_raises(self):
        with pytest.raises(ValidationError):
            ScenarioCreate(
                name="Test",
                tags=["product:Drug"],
                hcp_profile_id="p1",
                skill_id="skill-1",
            )

    async def test_missing_skill_id_raises(self):
        with pytest.raises(ValidationError):
            ScenarioCreate(
                name="Test",
                tags=["product:Drug"],
                hcp_profile_id="p1",
                rubric_id="rubric-1",
            )


class TestScenarioUpdateSchema:
    """Tests for ScenarioUpdate validation with optional rubric_id."""

    async def test_partial_update_no_rubric(self):
        data = ScenarioUpdate(name="New Name")
        assert data.name == "New Name"
        assert data.rubric_id is None

    async def test_update_with_rubric_id(self):
        data = ScenarioUpdate(rubric_id="new-rubric-id")
        assert data.rubric_id == "new-rubric-id"


# NOTE: ScenarioResponse was removed (Phase 30 review, WR-03) as a dead,
# manually-synced duplicate of the live ScenarioOut schema in
# backend/app/api/scenarios.py. Its from_attributes contract is covered there
# via backend/tests/test_scenarios_api.py instead.


class TestHcpProfileSchemas:
    """Tests for HCP profile schemas."""

    async def test_create_with_defaults(self):
        data = HcpProfileCreate(
            name="Dr. Zhang",
            specialty="Oncology",
            voice_live_instance_id="vl-instance-placeholder",
        )
        assert data.personality_type == "friendly"
        assert data.emotional_state == 50
        assert data.communication_style == 50
        assert data.is_active is True
        assert data.expertise_areas == []
        assert data.objections == []

    async def test_create_with_all_fields(self):
        data = HcpProfileCreate(
            name="Dr. Li",
            specialty="Cardiology",
            hospital="Beijing Hospital",
            title="Chief Physician",
            personality_type="skeptical",
            emotional_state=80,
            communication_style=30,
            expertise_areas=["intervention", "imaging"],
            objections=["Cost", "Safety"],
            probe_topics=["Outcomes"],
            difficulty="hard",
            voice_live_instance_id="vl-instance-placeholder",
        )
        assert data.emotional_state == 80
        assert data.expertise_areas == ["intervention", "imaging"]

    async def test_update_partial(self):
        data = HcpProfileUpdate(name="Dr. New Name")
        assert data.name == "Dr. New Name"
        assert data.specialty is None

    async def test_response_from_attributes(self):
        resp = HcpProfileResponse(
            id="p1",
            name="Dr. X",
            specialty="Neuro",
            hospital="H",
            title="T",
            avatar_url="",
            personality_type="friendly",
            emotional_state=50,
            communication_style=50,
            expertise_areas="[]",
            prescribing_habits="",
            concerns="",
            objections="[]",
            probe_topics="[]",
            difficulty="medium",
            is_active=True,
            created_by="user1",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        assert resp.id == "p1"


class TestSessionSchemas:
    """Tests for session-related schemas."""

    async def test_session_create(self):
        data = SessionCreate(scenario_id="s1")
        assert data.scenario_id == "s1"

    async def test_send_message_request(self):
        data = SendMessageRequest(message="Hello doctor")
        assert data.message == "Hello doctor"

    async def test_message_response(self):
        resp = MessageResponse(
            id="m1",
            session_id="s1",
            role="assistant",
            content="How does this compare?",
            message_index=0,
            speaker_id="hcp-1",
            speaker_name="Dr. Chen",
            created_at=datetime.now(),
        )
        assert resp.role == "assistant"
        assert resp.speaker_id == "hcp-1"
        assert resp.speaker_name == "Dr. Chen"

    async def test_message_response_defaults_to_no_speaker(self):
        resp = MessageResponse(
            id="m1",
            session_id="s1",
            role="user",
            content="Hello",
            message_index=0,
            created_at=datetime.now(),
        )
        assert resp.speaker_id is None
        assert resp.speaker_name == ""

    async def test_session_response_optional_fields(self):
        resp = SessionResponse(
            id="s1",
            user_id="u1",
            scenario_id="sc1",
            status="created",
            started_at=None,
            completed_at=None,
            duration_seconds=None,
            key_messages_status="[]",
            overall_score=None,
            passed=None,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        assert resp.started_at is None
        assert resp.overall_score is None


class TestScoreSchemas:
    """Tests for score-related schemas."""

    async def test_score_detail_response(self):
        resp = ScoreDetailResponse(
            id="d1",
            dimension="key_message",
            score=85.0,
            weight=30,
            strengths='[{"text": "Good", "quote": null}]',
            weaknesses="[]",
            suggestions='["Improve"]',
            created_at=datetime.now(),
        )
        assert resp.dimension == "key_message"
        assert resp.score == 85.0

    async def test_session_score_response(self):
        resp = SessionScoreResponse(
            id="sc1",
            session_id="s1",
            overall_score=78.5,
            passed=True,
            feedback_summary="Good performance",
            details=[],
            created_at=datetime.now(),
        )
        assert resp.overall_score == 78.5
        assert resp.passed is True
        assert resp.details == []
