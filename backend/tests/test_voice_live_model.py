"""Tests for Voice Live model selection (Phase 13-01).

Covers: VOICE_LIVE_MODELS constant, HcpProfile ORM model, schemas,
VoiceLiveModelsResponse, and GET /api/v1/voice-live/models endpoint.
"""

from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import get_db
from app.dependencies import get_current_user
from app.main import app
from app.models.hcp_profile import HcpProfile
from app.models.user import User
from app.schemas.hcp_profile import HcpProfileCreate, HcpProfileResponse, HcpProfileUpdate
from app.schemas.voice_live import VoiceLiveModelInfo, VoiceLiveModelsResponse
from app.services.voice_live_models import VOICE_LIVE_MODEL_TIERS, VOICE_LIVE_MODELS

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _fake_user() -> User:
    """Create a fake authenticated user for dependency override."""
    user = MagicMock(spec=User)
    user.id = "test-user-id-001"
    user.role = "user"
    user.username = "testuser"
    user.is_active = True
    return user


@pytest.fixture
def auth_client(db_session):
    """Async HTTP client with auth + db overrides."""

    async def override_get_db():
        yield db_session

    async def override_get_current_user():
        return _fake_user()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    yield
    app.dependency_overrides.clear()


@pytest.fixture
async def aclient(auth_client):
    """Async HTTP client with overrides applied."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# VOICE_LIVE_MODELS constant tests
# ---------------------------------------------------------------------------


class TestVoiceLiveModelsConstant:
    """Tests for the VOICE_LIVE_MODELS constant."""

    def test_has_12_models(self):
        """VOICE_LIVE_MODELS contains exactly 12 entries."""
        assert len(VOICE_LIVE_MODELS) == 12

    def test_gpt_4o_exists(self):
        """gpt-4o is a supported model (the default)."""
        assert "gpt-4o" in VOICE_LIVE_MODELS

    def test_each_model_has_required_keys(self):
        """Every model entry has tier, label, and description keys."""
        for model_id, info in VOICE_LIVE_MODELS.items():
            assert "tier" in info, f"{model_id} missing 'tier'"
            assert "label" in info, f"{model_id} missing 'label'"
            assert "description" in info, f"{model_id} missing 'description'"

    def test_all_tiers_valid(self):
        """All model tiers are in the valid set."""
        for model_id, info in VOICE_LIVE_MODELS.items():
            assert info["tier"] in VOICE_LIVE_MODEL_TIERS, (
                f"{model_id} has invalid tier: {info['tier']}"
            )

    def test_tier_distribution(self):
        """Each tier has at least one model."""
        tiers_seen = {info["tier"] for info in VOICE_LIVE_MODELS.values()}
        for tier in VOICE_LIVE_MODEL_TIERS:
            assert tier in tiers_seen, f"No models in tier: {tier}"

    def test_tiers_list(self):
        """VOICE_LIVE_MODEL_TIERS contains the 3 expected tiers."""
        assert VOICE_LIVE_MODEL_TIERS == ["pro", "basic", "lite"]


# ---------------------------------------------------------------------------
# ORM model tests
# ---------------------------------------------------------------------------


class TestHcpProfileOrm:
    """Tests for HcpProfile ORM model voice_live_model field.

    D-09: voice_live_model was one of the 14 deprecated inline voice/avatar
    columns dropped from hcp_profiles. Model selection now lives exclusively
    on VoiceLiveInstance. These tests assert the column stays gone (regression
    guard) instead of asserting its former presence/default.
    """

    def test_does_not_have_voice_live_model_attribute(self):
        """HcpProfile model no longer has the voice_live_model attribute."""
        assert not hasattr(HcpProfile, "voice_live_model")

    def test_voice_live_model_column_removed(self):
        """voice_live_model is not a mapped column in the table."""
        columns = {c.name for c in HcpProfile.__table__.columns}
        assert "voice_live_model" not in columns


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestHcpProfileSchemas:
    """Tests for HcpProfile schema fields.

    D-09/D-13: voice_live_model no longer exists as an inline schema field --
    model selection lives exclusively on VoiceLiveInstance. voice_live_instance_id
    is now required on HcpProfileCreate. These tests assert the current contract
    instead of the removed voice_live_model field.
    """

    def test_create_schema_requires_voice_live_instance_id(self):
        """HcpProfileCreate requires voice_live_instance_id (D-13)."""
        schema = HcpProfileCreate(
            name="Test",
            specialty="Oncology",
            created_by="user1",
            voice_live_instance_id="vl-instance-1",
        )
        assert schema.voice_live_instance_id == "vl-instance-1"

    def test_create_schema_no_voice_live_model_field(self):
        """HcpProfileCreate no longer exposes a voice_live_model field."""
        assert "voice_live_model" not in HcpProfileCreate.model_fields

    def test_update_schema_default_none(self):
        """HcpProfileUpdate defaults voice_live_instance_id to None (optional)."""
        schema = HcpProfileUpdate()
        assert schema.voice_live_instance_id is None

    def test_update_schema_with_value(self):
        """HcpProfileUpdate accepts a voice_live_instance_id value."""
        schema = HcpProfileUpdate(voice_live_instance_id="vl-instance-2")
        assert schema.voice_live_instance_id == "vl-instance-2"

    def test_response_schema_no_voice_live_model_field(self):
        """HcpProfileResponse no longer exposes a voice_live_model field."""
        data = {
            "id": "test-id",
            "name": "Dr. Test",
            "specialty": "Oncology",
            "hospital": "",
            "title": "",
            "avatar_url": "",
            "personality_type": "friendly",
            "emotional_state": 50,
            "communication_style": 50,
            "expertise_areas": "[]",
            "prescribing_habits": "",
            "concerns": "",
            "objections": "[]",
            "probe_topics": "[]",
            "difficulty": "medium",
            "is_active": True,
            "created_by": "user1",
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        }
        schema = HcpProfileResponse(**data)
        assert not hasattr(schema, "voice_live_model")


# ---------------------------------------------------------------------------
# VoiceLiveModelsResponse schema test
# ---------------------------------------------------------------------------


class TestVoiceLiveModelsResponseSchema:
    """Tests for VoiceLiveModelsResponse schema."""

    def test_models_response_schema(self):
        """VoiceLiveModelsResponse serializes a list of VoiceLiveModelInfo."""
        models = [
            VoiceLiveModelInfo(
                id="gpt-4o",
                label="GPT-4o",
                tier="pro",
                description="GPT-4o + Azure STT/TTS",
            ),
        ]
        resp = VoiceLiveModelsResponse(models=models)
        assert len(resp.models) == 1
        assert resp.models[0].id == "gpt-4o"
        assert resp.models[0].tier == "pro"


# ---------------------------------------------------------------------------
# API endpoint integration tests
# ---------------------------------------------------------------------------


class TestVoiceLiveModelsEndpoint:
    """Integration tests for GET /api/v1/voice-live/models."""

    @pytest.mark.asyncio
    async def test_get_models_returns_200(self, aclient: AsyncClient):
        """GET /api/v1/voice-live/models returns 200."""
        resp = await aclient.get("/api/v1/voice-live/models")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_models_returns_12_models(self, aclient: AsyncClient):
        """GET /api/v1/voice-live/models returns exactly 12 models."""
        resp = await aclient.get("/api/v1/voice-live/models")
        data = resp.json()
        assert "models" in data
        assert len(data["models"]) == 12

    @pytest.mark.asyncio
    async def test_get_models_structure(self, aclient: AsyncClient):
        """Each model in the response has id, label, tier, description."""
        resp = await aclient.get("/api/v1/voice-live/models")
        data = resp.json()
        for model in data["models"]:
            assert "id" in model
            assert "label" in model
            assert "tier" in model
            assert "description" in model

    @pytest.mark.asyncio
    async def test_get_models_contains_gpt_4o(self, aclient: AsyncClient):
        """The model list includes gpt-4o (the default model)."""
        resp = await aclient.get("/api/v1/voice-live/models")
        data = resp.json()
        model_ids = [m["id"] for m in data["models"]]
        assert "gpt-4o" in model_ids

    @pytest.mark.asyncio
    async def test_get_models_tiers(self, aclient: AsyncClient):
        """Models span all 3 tiers: pro, basic, lite."""
        resp = await aclient.get("/api/v1/voice-live/models")
        data = resp.json()
        tiers = {m["tier"] for m in data["models"]}
        assert tiers == {"pro", "basic", "lite"}
