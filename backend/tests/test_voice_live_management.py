"""Tests for Voice Live Management page backend support (Phase 13-03 + 14-04).

Covers:
  - GET /api/v1/voice-live/models returns correct model list
  - Model response structure and tiers
  - POST /api/v1/hcp-profiles/batch-sync response format (via existing endpoint)
  - POST /api/v1/voice-live/instances/unassign (Phase 14 unassign endpoint)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import get_db
from app.dependencies import get_current_user
from app.main import app
from app.models.user import User
from app.models.voice_live_instance import VoiceLiveInstance
from app.services.voice_live_models import VOICE_LIVE_MODELS


async def _create_vl_instance(session, user_id: str) -> str:
    """Create a minimal VoiceLiveInstance directly via the DB and return its id."""
    inst = VoiceLiveInstance(name="Test VL Instance", created_by=user_id)
    session.add(inst)
    await session.flush()
    await session.refresh(inst)
    return inst.id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _fake_admin() -> User:
    """Create a fake authenticated admin user for dependency override."""
    user = MagicMock(spec=User)
    user.id = "admin-user-id-001"
    user.role = "admin"
    user.username = "adminuser"
    user.is_active = True
    return user


@pytest.fixture
def admin_client(db_session):
    """Async HTTP client with admin auth + db overrides."""

    async def override_get_db():
        yield db_session

    async def override_get_current_user():
        return _fake_admin()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    yield
    app.dependency_overrides.clear()


@pytest.fixture
async def aclient(admin_client):
    """Async HTTP client with overrides applied."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# GET /api/v1/voice-live/models — Management page model list
# ---------------------------------------------------------------------------


class TestVoiceLiveModelsForManagement:
    """Integration tests for model list API used by management page."""

    @pytest.mark.asyncio
    async def test_returns_200(self, aclient: AsyncClient):
        """GET /api/v1/voice-live/models returns 200."""
        resp = await aclient.get("/api/v1/voice-live/models")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_returns_12_models(self, aclient: AsyncClient):
        """Model list contains exactly 12 entries matching VOICE_LIVE_MODELS."""
        resp = await aclient.get("/api/v1/voice-live/models")
        data = resp.json()
        assert len(data["models"]) == 12
        assert len(data["models"]) == len(VOICE_LIVE_MODELS)

    @pytest.mark.asyncio
    async def test_model_has_required_fields(self, aclient: AsyncClient):
        """Each model in the response has id, label, tier, description."""
        resp = await aclient.get("/api/v1/voice-live/models")
        data = resp.json()
        for model in data["models"]:
            assert "id" in model, f"Missing 'id' in model: {model}"
            assert "label" in model, f"Missing 'label' in model: {model}"
            assert "tier" in model, f"Missing 'tier' in model: {model}"
            assert "description" in model, f"Missing 'description' in model: {model}"

    @pytest.mark.asyncio
    async def test_tiers_only_valid(self, aclient: AsyncClient):
        """Model tiers are only 'pro', 'basic', or 'lite'."""
        resp = await aclient.get("/api/v1/voice-live/models")
        data = resp.json()
        valid_tiers = {"pro", "basic", "lite"}
        for model in data["models"]:
            assert model["tier"] in valid_tiers, (
                f"Invalid tier '{model['tier']}' for model '{model['id']}'"
            )

    @pytest.mark.asyncio
    async def test_all_tiers_represented(self, aclient: AsyncClient):
        """Response includes models from all 3 tiers."""
        resp = await aclient.get("/api/v1/voice-live/models")
        data = resp.json()
        tiers = {m["tier"] for m in data["models"]}
        assert tiers == {"pro", "basic", "lite"}

    @pytest.mark.asyncio
    async def test_default_model_present(self, aclient: AsyncClient):
        """Default model gpt-4o is present in the model list."""
        resp = await aclient.get("/api/v1/voice-live/models")
        data = resp.json()
        model_ids = [m["id"] for m in data["models"]]
        assert "gpt-4o" in model_ids

    @pytest.mark.asyncio
    async def test_api_matches_constant(self, aclient: AsyncClient):
        """API response model IDs match the VOICE_LIVE_MODELS constant keys."""
        resp = await aclient.get("/api/v1/voice-live/models")
        data = resp.json()
        api_ids = sorted(m["id"] for m in data["models"])
        constant_ids = sorted(VOICE_LIVE_MODELS.keys())
        assert api_ids == constant_ids


# ---------------------------------------------------------------------------
# POST /api/v1/hcp-profiles/batch-sync — Batch agent re-sync
# ---------------------------------------------------------------------------


class TestBatchSyncEndpointFormat:
    """Integration tests for batch sync response format used by management page."""

    @pytest.mark.asyncio
    async def test_batch_sync_returns_200(self, aclient: AsyncClient):
        """POST /api/v1/hcp-profiles/batch-sync returns 200."""
        resp = await aclient.post("/api/v1/hcp-profiles/batch-sync")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_batch_sync_response_has_counts(self, aclient: AsyncClient):
        """Batch sync response contains synced, failed, and total counts."""
        resp = await aclient.post("/api/v1/hcp-profiles/batch-sync")
        data = resp.json()
        assert "synced" in data
        assert "failed" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_batch_sync_empty_db(self, aclient: AsyncClient):
        """Batch sync with no profiles returns zero counts."""
        resp = await aclient.post("/api/v1/hcp-profiles/batch-sync")
        data = resp.json()
        assert data["synced"] == 0
        assert data["failed"] == 0
        assert data["total"] == 0


# ---------------------------------------------------------------------------
# POST /api/v1/voice-live/instances/unassign — Phase 14 unassign endpoint
# ---------------------------------------------------------------------------


class TestUnassignInstanceFromHcp:
    """Integration tests for the unassign endpoint (Phase 14-01)."""

    @pytest.mark.asyncio
    @patch("app.services.agent_sync_service.update_agent_metadata_only", new_callable=AsyncMock)
    async def test_unassign_instance_from_hcp(
        self,
        mock_update_metadata,
        aclient: AsyncClient,
        db_session,
    ):
        """Unassign a VL Instance from an HCP Profile: full happy path."""
        mock_update_metadata.return_value = "2"

        # 1. Create VL Instance via API
        inst_resp = await aclient.post(
            "/api/v1/voice-live/instances",
            json={"name": "Test Instance"},
        )
        assert inst_resp.status_code == 201
        instance_id = inst_resp.json()["id"]

        # Create a separate initial VL instance to satisfy the required
        # voice_live_instance_id field on HCP profile creation (D-13) -- the
        # HCP is then reassigned to `instance_id` below and later unassigned.
        initial_vl_id = await _create_vl_instance(db_session, "admin-user-id-001")
        await db_session.commit()

        # 2. Create HCP Profile via API
        hcp_resp = await aclient.post(
            "/api/v1/hcp-profiles",
            json={
                "name": "Dr. Unassign Test",
                "specialty": "Oncology",
                "created_by": "admin-user-id-001",
                "voice_live_instance_id": initial_vl_id,
            },
        )
        assert hcp_resp.status_code == 201
        hcp_id = hcp_resp.json()["id"]

        # 3. Assign instance to HCP
        assign_resp = await aclient.post(
            f"/api/v1/voice-live/instances/{instance_id}/assign",
            json={"hcp_profile_id": hcp_id},
        )
        assert assign_resp.status_code == 200

        # 4. Unassign
        unassign_resp = await aclient.post(
            "/api/v1/voice-live/instances/unassign",
            json={"hcp_profile_id": hcp_id},
        )
        assert unassign_resp.status_code == 200
        data = unassign_resp.json()
        assert data["hcp_profile_id"] == hcp_id
        assert data["voice_live_instance_id"] is None

        # 5. Verify via instance GET: hcp_count should be 0 after unassign
        inst_get_resp = await aclient.get(f"/api/v1/voice-live/instances/{instance_id}")
        assert inst_get_resp.status_code == 200
        assert inst_get_resp.json()["hcp_count"] == 0

    @pytest.mark.asyncio
    async def test_unassign_nonexistent_hcp(self, aclient: AsyncClient):
        """Unassign with nonexistent HCP profile ID returns 404."""
        resp = await aclient.post(
            "/api/v1/voice-live/instances/unassign",
            json={"hcp_profile_id": "nonexistent-id"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    @patch("app.services.hcp_profile_service.agent_sync_service")
    async def test_unassign_already_unassigned_hcp(
        self, mock_sync, aclient: AsyncClient, db_session
    ):
        """Unassign on HCP with no instance is idempotent (returns 200)."""
        mock_sync.sync_agent_for_profile = AsyncMock(return_value={"id": "asst_test"})

        # Create HCP Profile with a VL Instance (required at creation, D-13),
        # then clear the reference directly in the DB to simulate an
        # already-unassigned HCP (the DB column itself stays nullable).
        vl_id = await _create_vl_instance(db_session, "admin-user-id-001")
        await db_session.commit()
        hcp_resp = await aclient.post(
            "/api/v1/hcp-profiles",
            json={
                "name": "Dr. No Instance",
                "specialty": "Cardiology",
                "created_by": "admin-user-id-001",
                "voice_live_instance_id": vl_id,
            },
        )
        assert hcp_resp.status_code == 201
        hcp_id = hcp_resp.json()["id"]

        from sqlalchemy import update

        from app.models.hcp_profile import HcpProfile

        await db_session.execute(
            update(HcpProfile).where(HcpProfile.id == hcp_id).values(voice_live_instance_id=None)
        )
        await db_session.commit()

        # Unassign (should be idempotent)
        resp = await aclient.post(
            "/api/v1/voice-live/instances/unassign",
            json={"hcp_profile_id": hcp_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["hcp_profile_id"] == hcp_id
        assert data["voice_live_instance_id"] is None
