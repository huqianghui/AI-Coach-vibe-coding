"""Tests for HCP profile service: CRUD operations."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.models.user import User
from app.models.voice_live_instance import VoiceLiveInstance
from app.schemas.hcp_profile import HcpProfileCreate, HcpProfileUpdate
from app.services.auth import get_password_hash
from app.services.hcp_profile_service import (
    create_hcp_profile,
    delete_hcp_profile,
    get_hcp_profile,
    get_hcp_profiles,
    retry_agent_sync,
    update_hcp_profile,
)
from app.utils.exceptions import NotFoundException


async def _seed_user(db) -> str:
    """Create a test user and return user_id."""
    user = User(
        username="hcpuser",
        email="hcp@test.com",
        hashed_password=get_password_hash("pass"),
        full_name="HCP User",
        role="admin",
    )
    db.add(user)
    await db.flush()
    return user.id


async def _create_vl_instance(db, user_id: str) -> str:
    """Create a minimal VoiceLiveInstance and return its id.

    D-13: HcpProfileCreate requires voice_live_instance_id -- every test that
    constructs one needs a real VoiceLiveInstance row to link.
    """
    inst = VoiceLiveInstance(name="HCP Service Test VL Instance", created_by=user_id)
    db.add(inst)
    await db.flush()
    return inst.id


class TestCreateHcpProfile:
    """Tests for create_hcp_profile."""

    async def test_creates_profile_with_required_fields(self, db_session):
        user_id = await _seed_user(db_session)
        vl_id = await _create_vl_instance(db_session, user_id)
        data = HcpProfileCreate(
            name="Dr. Zhang",
            specialty="Oncology",
            created_by=user_id,
            voice_live_instance_id=vl_id,
        )
        profile = await create_hcp_profile(db_session, data, user_id)

        assert profile.name == "Dr. Zhang"
        assert profile.specialty == "Oncology"
        assert profile.created_by == user_id
        assert profile.id is not None

    async def test_serializes_list_fields_to_json(self, db_session):
        user_id = await _seed_user(db_session)
        vl_id = await _create_vl_instance(db_session, user_id)
        data = HcpProfileCreate(
            name="Dr. Li",
            specialty="Cardiology",
            created_by=user_id,
            voice_live_instance_id=vl_id,
            expertise_areas=["interventional", "heart failure"],
            objections=["Cost concerns"],
            probe_topics=["Long-term data"],
        )
        profile = await create_hcp_profile(db_session, data, user_id)

        # In DB, list fields are stored as JSON strings
        assert json.loads(profile.expertise_areas) == ["interventional", "heart failure"]
        assert json.loads(profile.objections) == ["Cost concerns"]
        assert json.loads(profile.probe_topics) == ["Long-term data"]

    async def test_defaults_are_applied(self, db_session):
        user_id = await _seed_user(db_session)
        vl_id = await _create_vl_instance(db_session, user_id)
        data = HcpProfileCreate(
            name="Dr. A",
            specialty="Derm",
            created_by=user_id,
            voice_live_instance_id=vl_id,
        )
        profile = await create_hcp_profile(db_session, data, user_id)

        assert profile.personality_type == "friendly"
        assert profile.emotional_state == 50
        assert profile.communication_style == 50
        assert profile.is_active is True


class TestGetHcpProfiles:
    """Tests for get_hcp_profiles (list with search/filter)."""

    async def test_returns_all_profiles(self, db_session):
        user_id = await _seed_user(db_session)
        vl_id = await _create_vl_instance(db_session, user_id)
        for name in ["Dr. Zhang", "Dr. Li"]:
            data = HcpProfileCreate(
                name=name, specialty="Oncology", created_by=user_id, voice_live_instance_id=vl_id
            )
            await create_hcp_profile(db_session, data, user_id)

        profiles, total = await get_hcp_profiles(db_session)
        assert total == 2
        assert len(profiles) == 2

    async def test_search_by_name(self, db_session):
        user_id = await _seed_user(db_session)
        vl_id = await _create_vl_instance(db_session, user_id)
        await create_hcp_profile(
            db_session,
            HcpProfileCreate(
                name="Dr. Zhang",
                specialty="Oncology",
                created_by=user_id,
                voice_live_instance_id=vl_id,
            ),
            user_id,
        )
        await create_hcp_profile(
            db_session,
            HcpProfileCreate(
                name="Dr. Li",
                specialty="Cardiology",
                created_by=user_id,
                voice_live_instance_id=vl_id,
            ),
            user_id,
        )

        profiles, total = await get_hcp_profiles(db_session, search="Zhang")
        assert total == 1
        assert profiles[0].name == "Dr. Zhang"

    async def test_filter_by_is_active(self, db_session):
        user_id = await _seed_user(db_session)
        vl_id = await _create_vl_instance(db_session, user_id)
        await create_hcp_profile(
            db_session,
            HcpProfileCreate(
                name="Active",
                specialty="Onc",
                created_by=user_id,
                voice_live_instance_id=vl_id,
                is_active=True,
            ),
            user_id,
        )
        await create_hcp_profile(
            db_session,
            HcpProfileCreate(
                name="Inactive",
                specialty="Onc",
                created_by=user_id,
                voice_live_instance_id=vl_id,
                is_active=False,
            ),
            user_id,
        )

        profiles, total = await get_hcp_profiles(db_session, is_active=True)
        assert total == 1
        assert profiles[0].name == "Active"


class TestGetHcpProfile:
    """Tests for get_hcp_profile (single by ID)."""

    async def test_returns_profile_by_id(self, db_session):
        user_id = await _seed_user(db_session)
        vl_id = await _create_vl_instance(db_session, user_id)
        data = HcpProfileCreate(
            name="Dr. X", specialty="Neuro", created_by=user_id, voice_live_instance_id=vl_id
        )
        created = await create_hcp_profile(db_session, data, user_id)

        fetched = await get_hcp_profile(db_session, created.id)
        assert fetched.name == "Dr. X"

    async def test_raises_not_found(self, db_session):
        with pytest.raises(NotFoundException):
            await get_hcp_profile(db_session, "nonexistent-id")


class TestUpdateHcpProfile:
    """Tests for update_hcp_profile."""

    async def test_updates_partial_fields(self, db_session):
        user_id = await _seed_user(db_session)
        vl_id = await _create_vl_instance(db_session, user_id)
        data = HcpProfileCreate(
            name="Dr. Old", specialty="Onc", created_by=user_id, voice_live_instance_id=vl_id
        )
        profile = await create_hcp_profile(db_session, data, user_id)

        update = HcpProfileUpdate(name="Dr. New", personality_type="skeptical")
        updated = await update_hcp_profile(db_session, profile.id, update)

        assert updated.name == "Dr. New"
        assert updated.personality_type == "skeptical"
        assert updated.specialty == "Onc"  # unchanged

    async def test_updates_list_fields(self, db_session):
        user_id = await _seed_user(db_session)
        vl_id = await _create_vl_instance(db_session, user_id)
        data = HcpProfileCreate(
            name="Dr. Y", specialty="Onc", created_by=user_id, voice_live_instance_id=vl_id
        )
        profile = await create_hcp_profile(db_session, data, user_id)

        update = HcpProfileUpdate(expertise_areas=["new_area_1", "new_area_2"])
        updated = await update_hcp_profile(db_session, profile.id, update)

        assert json.loads(updated.expertise_areas) == ["new_area_1", "new_area_2"]


class TestDeleteHcpProfile:
    """Tests for delete_hcp_profile."""

    async def test_deletes_existing_profile(self, db_session):
        user_id = await _seed_user(db_session)
        vl_id = await _create_vl_instance(db_session, user_id)
        data = HcpProfileCreate(
            name="Dr. Del", specialty="Onc", created_by=user_id, voice_live_instance_id=vl_id
        )
        profile = await create_hcp_profile(db_session, data, user_id)

        await delete_hcp_profile(db_session, profile.id)

        with pytest.raises(NotFoundException):
            await get_hcp_profile(db_session, profile.id)

    async def test_raises_for_nonexistent(self, db_session):
        with pytest.raises(NotFoundException):
            await delete_hcp_profile(db_session, "nonexistent")


class TestAgentSyncOnCreate:
    """Tests for agent sync triggered on profile creation."""

    async def test_create_syncs_agent_on_success(self, db_session):
        """create_hcp_profile sets agent_id and sync_status=synced on sync success."""
        user_id = await _seed_user(db_session)
        vl_id = await _create_vl_instance(db_session, user_id)
        data = HcpProfileCreate(
            name="Dr. Sync", specialty="Oncology", created_by=user_id, voice_live_instance_id=vl_id
        )

        with patch(
            "app.services.hcp_profile_service.agent_sync_service.sync_agent_for_profile",
            new_callable=AsyncMock,
            return_value={"id": "asst_created_123", "name": "Dr. Sync", "model": "gpt-4o"},
        ):
            profile = await create_hcp_profile(db_session, data, user_id)

        assert profile.agent_id == "asst_created_123"
        assert profile.agent_sync_status == "synced"
        assert profile.agent_sync_error == ""


class TestAgentSyncOnUpdate:
    """Tests for agent sync triggered on profile update."""

    async def test_update_resyncs_agent_on_success(self, db_session):
        """update_hcp_profile sets sync_status=synced on re-sync success."""
        user_id = await _seed_user(db_session)
        vl_id = await _create_vl_instance(db_session, user_id)
        data = HcpProfileCreate(
            name="Dr. Up", specialty="Neuro", created_by=user_id, voice_live_instance_id=vl_id
        )

        # Create with sync success
        with patch(
            "app.services.hcp_profile_service.agent_sync_service.sync_agent_for_profile",
            new_callable=AsyncMock,
            return_value={"id": "asst_up_456", "name": "Dr. Up", "model": "gpt-4o"},
        ):
            profile = await create_hcp_profile(db_session, data, user_id)

        # Update with sync success
        with patch(
            "app.services.hcp_profile_service.agent_sync_service.sync_agent_for_profile",
            new_callable=AsyncMock,
            return_value={"id": "asst_up_456", "name": "Dr. Updated", "model": "gpt-4o"},
        ):
            updated = await update_hcp_profile(
                db_session, profile.id, HcpProfileUpdate(name="Dr. Updated")
            )

        assert updated.agent_sync_status == "synced"
        assert updated.agent_sync_error == ""

    async def test_update_assigns_agent_id_when_missing(self, db_session):
        """update_hcp_profile sets agent_id if profile had no agent_id."""
        user_id = await _seed_user(db_session)
        vl_id = await _create_vl_instance(db_session, user_id)
        data = HcpProfileCreate(
            name="Dr. NoAgent", specialty="Derm", created_by=user_id, voice_live_instance_id=vl_id
        )

        # Create with sync failure (no agent_id)
        with patch(
            "app.services.hcp_profile_service.agent_sync_service.sync_agent_for_profile",
            new_callable=AsyncMock,
            side_effect=Exception("Network error"),
        ):
            profile = await create_hcp_profile(db_session, data, user_id)

        assert profile.agent_id in ("", None)

        # Update with sync success (should assign agent_id)
        with patch(
            "app.services.hcp_profile_service.agent_sync_service.sync_agent_for_profile",
            new_callable=AsyncMock,
            return_value={"id": "asst_new_789", "name": "Dr. NoAgent", "model": "gpt-4o"},
        ):
            updated = await update_hcp_profile(
                db_session, profile.id, HcpProfileUpdate(name="Dr. NoAgent Updated")
            )

        assert updated.agent_id == "asst_new_789"
        assert updated.agent_sync_status == "synced"


class TestDeleteWithAgent:
    """Tests for delete_hcp_profile that has an agent_id."""

    async def test_delete_calls_agent_delete(self, db_session):
        """delete_hcp_profile calls agent_sync_service.delete_agent when agent_id exists."""
        user_id = await _seed_user(db_session)
        vl_id = await _create_vl_instance(db_session, user_id)
        data = HcpProfileCreate(
            name="Dr. Del Agent", specialty="Onc", created_by=user_id, voice_live_instance_id=vl_id
        )

        with patch(
            "app.services.hcp_profile_service.agent_sync_service.sync_agent_for_profile",
            new_callable=AsyncMock,
            return_value={"id": "asst_del_999", "name": "Dr. Del Agent", "model": "gpt-4o"},
        ):
            profile = await create_hcp_profile(db_session, data, user_id)

        assert profile.agent_id == "asst_del_999"

        with patch(
            "app.services.hcp_profile_service.agent_sync_service.delete_agent",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_delete:
            await delete_hcp_profile(db_session, profile.id)

        mock_delete.assert_called_once_with(db_session, "asst_del_999")

    async def test_delete_tolerates_agent_deletion_failure(self, db_session):
        """delete_hcp_profile succeeds even if agent deletion fails."""
        user_id = await _seed_user(db_session)
        vl_id = await _create_vl_instance(db_session, user_id)
        data = HcpProfileCreate(
            name="Dr. Del Fail", specialty="Onc", created_by=user_id, voice_live_instance_id=vl_id
        )

        with patch(
            "app.services.hcp_profile_service.agent_sync_service.sync_agent_for_profile",
            new_callable=AsyncMock,
            return_value={"id": "asst_fail_del", "name": "Dr. Del Fail", "model": "gpt-4o"},
        ):
            profile = await create_hcp_profile(db_session, data, user_id)

        profile_id = profile.id

        with patch(
            "app.services.hcp_profile_service.agent_sync_service.delete_agent",
            new_callable=AsyncMock,
            side_effect=Exception("Agent not found"),
        ):
            await delete_hcp_profile(db_session, profile_id)

        # Profile should still be deleted
        with pytest.raises(NotFoundException):
            await get_hcp_profile(db_session, profile_id)


class TestRetryAgentSync:
    """Tests for retry_agent_sync."""

    async def test_retry_syncs_agent_on_success(self, db_session):
        """retry_agent_sync sets agent_id and sync_status=synced."""
        user_id = await _seed_user(db_session)
        vl_id = await _create_vl_instance(db_session, user_id)
        data = HcpProfileCreate(
            name="Dr. Retry", specialty="Onc", created_by=user_id, voice_live_instance_id=vl_id
        )

        # Create with sync failure
        with patch(
            "app.services.hcp_profile_service.agent_sync_service.sync_agent_for_profile",
            new_callable=AsyncMock,
            side_effect=Exception("Temp failure"),
        ):
            profile = await create_hcp_profile(db_session, data, user_id)

        assert profile.agent_sync_status == "failed"

        # Retry with success
        with patch(
            "app.services.hcp_profile_service.agent_sync_service.sync_agent_for_profile",
            new_callable=AsyncMock,
            return_value={"id": "asst_retry_ok", "name": "Dr. Retry", "model": "gpt-4o"},
        ):
            retried = await retry_agent_sync(db_session, profile.id)

        assert retried.agent_id == "asst_retry_ok"
        assert retried.agent_sync_status == "synced"
        assert retried.agent_sync_error == ""

    async def test_retry_handles_second_failure(self, db_session):
        """retry_agent_sync sets failed status on repeated failure."""
        user_id = await _seed_user(db_session)
        vl_id = await _create_vl_instance(db_session, user_id)
        data = HcpProfileCreate(
            name="Dr. Retry2", specialty="Onc", created_by=user_id, voice_live_instance_id=vl_id
        )

        # Create with sync failure
        with patch(
            "app.services.hcp_profile_service.agent_sync_service.sync_agent_for_profile",
            new_callable=AsyncMock,
            side_effect=Exception("First failure"),
        ):
            profile = await create_hcp_profile(db_session, data, user_id)

        # Retry also fails
        with patch(
            "app.services.hcp_profile_service.agent_sync_service.sync_agent_for_profile",
            new_callable=AsyncMock,
            side_effect=Exception("Second failure"),
        ):
            retried = await retry_agent_sync(db_session, profile.id)

        assert retried.agent_sync_status == "failed"
        assert "Second failure" in retried.agent_sync_error


class TestBatchSyncAgents:
    """Regression tests for batch_sync_agents' HcpProfile eager-loading.

    batch_sync_agents queries profiles needing sync via a plain select() then calls
    agent_sync_service.sync_agent_for_profile, which reads profile.voice_live_instance
    (a default lazy relationship) inside resolve_voice_config(). Without
    selectinload(HcpProfile.voice_live_instance) on the query, the first access to
    that relationship triggers an implicit lazy DB load with no greenlet_spawn
    trampoline active, raising sqlalchemy.exc.MissingGreenlet. This test
    intentionally does NOT mock sync_agent_for_profile itself -- only the Azure SDK
    boundary functions -- so the real ORM relationship-loading behavior is exercised
    against the real aiosqlite async session.
    """

    async def test_batch_sync_with_assigned_voice_live_instance_no_missing_greenlet(
        self, db_session
    ):
        """batch_sync_agents must not raise MissingGreenlet for a profile with an
        assigned VoiceLiveInstance and no agent_id yet.

        db_session.expunge(vl_instance) is required to make this test valid: without
        it, the VoiceLiveInstance stays in this session's identity map (it was just
        created+flushed here), and SQLAlchemy's many-to-one lazy loader satisfies
        profile.voice_live_instance via an identity-map lookup by primary key
        ("use_get" optimization) with NO actual DB IO -- which would pass whether or
        not selectinload is applied, silently defeating the regression test.
        Expunging forces a genuine lazy load (a real DB round-trip) on first access,
        matching a fresh production request where the VL instance was never
        independently queried.
        """
        from app.models.voice_live_instance import VoiceLiveInstance
        from app.services.hcp_profile_service import batch_sync_agents

        user_id = await _seed_user(db_session)
        vl_id = await _create_vl_instance(db_session, user_id)
        vl_instance = await db_session.get(VoiceLiveInstance, vl_id)
        db_session.expunge(vl_instance)

        data = HcpProfileCreate(
            name="Dr. Batch", specialty="Onc", created_by=user_id, voice_live_instance_id=vl_id
        )
        # Create with sync failure so agent_id stays empty -- batch_sync_agents only
        # picks up profiles with agent_id == "" / None / agent_sync_status == "failed".
        with patch(
            "app.services.hcp_profile_service.agent_sync_service.sync_agent_for_profile",
            new_callable=AsyncMock,
            side_effect=Exception("Not yet synced"),
        ):
            profile = await create_hcp_profile(db_session, data, user_id)

        assert profile.agent_id in ("", None)

        with (
            patch(
                "app.services.agent_sync_service.create_agent",
                new_callable=AsyncMock,
                return_value={"id": "asst_batch_1", "version": "1"},
            ),
            patch(
                "app.services.agent_sync_service.update_agent",
                new_callable=AsyncMock,
                return_value={"id": "asst_batch_1", "version": "1"},
            ),
            patch(
                "app.services.agent_sync_service.get_agent_latest_version",
                new_callable=AsyncMock,
                return_value="1",
            ),
        ):
            summary = await batch_sync_agents(db_session)

        assert summary["synced"] == 1
        assert summary["failed"] == 0

        await db_session.refresh(profile)
        assert profile.agent_sync_status == "synced"
        assert profile.agent_id == "asst_batch_1"
