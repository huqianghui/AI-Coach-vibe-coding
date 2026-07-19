"""Unit tests for voice_live_instance_service: CRUD + agent re-sync triggers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

# ===========================================================================
# Phase 16: Re-sync triggers on VL Instance update/assign/unassign/delete
# ===========================================================================


def _make_vl_instance_mock(**overrides):
    """Create a MagicMock VoiceLiveInstance with all required fields set to real values."""
    m = MagicMock()
    defaults = {
        "id": "inst-test",
        "name": "Test Instance",
        "enabled": True,
        "voice_live_model": "gpt-4o",
        "voice_name": "en-US-AvaNeural",
        "voice_type": "azure-standard",
        "voice_temperature": 0.9,
        "voice_custom": False,
        "avatar_character": "lori",
        "avatar_style": "casual",
        "avatar_customized": False,
        "turn_detection_type": "server_vad",
        "noise_suppression": False,
        "echo_cancellation": False,
        "eou_detection": False,
        "recognition_language": "auto",
        "model_instruction": "",
        "response_temperature": 0.8,
        "proactive_engagement": True,
        "auto_detect_language": True,
        "playback_speed": 1.0,
        "custom_lexicon_enabled": False,
        "custom_lexicon_url": "",
        "avatar_enabled": True,
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


@pytest.mark.asyncio
async def test_update_instance_triggers_resync():
    """update_instance triggers agent metadata re-sync for assigned HCPs with synced agents."""
    from app.schemas.voice_live_instance import VoiceLiveInstanceUpdate

    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.execute = AsyncMock()

    mock_instance = _make_vl_instance_mock(id="inst-001")

    # Create a mock HCP profile that has a synced agent
    mock_profile = MagicMock()
    mock_profile.id = "hcp-001"
    mock_profile.agent_id = "agent-001"
    mock_profile.agent_sync_status = "synced"
    mock_profile.voice_live_instance = mock_instance

    # Instance returned by get_instance has hcp_profiles.
    # Use _make_vl_instance_mock so resolve_voice_config can read voice attributes
    # (our code now sets profile.voice_live_instance = refreshed instance).
    mock_refreshed_instance = _make_vl_instance_mock(id="inst-001")
    mock_refreshed_instance.hcp_profiles = [mock_profile]

    update_data = VoiceLiveInstanceUpdate(voice_name="zh-CN-XiaoxiaoMultilingualNeural")

    with (
        patch(
            "app.services.voice_live_instance_service.get_instance",
            new_callable=AsyncMock,
            side_effect=[mock_instance, mock_refreshed_instance],
        ),
        patch(
            "app.services.agent_sync_service.update_agent_metadata_only",
            new_callable=AsyncMock,
            return_value="10",
        ) as mock_update_meta,
    ):
        from app.services.voice_live_instance_service import update_instance

        await update_instance(mock_db, "inst-001", update_data)

    # Verify agent metadata update was called
    mock_update_meta.assert_called_once()
    call_args = mock_update_meta.call_args
    assert call_args[0][1] == "agent-001"  # agent_id


@pytest.mark.asyncio
async def test_assign_triggers_resync():
    """assign_to_hcp triggers agent metadata sync for the assigned HCP."""
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.expire_all = MagicMock()

    # Use _make_vl_instance_mock so resolve_voice_config can read voice attributes
    # (our code now sets profile.voice_live_instance = loaded instance).
    mock_instance = _make_vl_instance_mock(id="inst-002")

    mock_profile = MagicMock()
    mock_profile.id = "hcp-002"
    mock_profile.agent_id = "agent-002"
    mock_profile.agent_sync_status = "synced"
    mock_profile.voice_live_instance_id = "inst-002"
    mock_profile.voice_live_instance = mock_instance

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_profile
    mock_db.execute = AsyncMock(return_value=mock_result)

    with (
        patch(
            "app.services.voice_live_instance_service.get_instance",
            new_callable=AsyncMock,
            return_value=mock_instance,
        ),
        patch(
            "app.services.agent_sync_service.update_agent_metadata_only",
            new_callable=AsyncMock,
            return_value="10",
        ) as mock_update_meta,
    ):
        from app.services.voice_live_instance_service import assign_to_hcp

        await assign_to_hcp(mock_db, "inst-002", "hcp-002")

    # Verify agent metadata sync was triggered
    mock_update_meta.assert_called_once()
    call_args = mock_update_meta.call_args
    assert call_args[0][1] == "agent-002"


@pytest.mark.asyncio
async def test_unassign_clears_metadata():
    """unassign_from_hcp clears agent voice metadata using build_cleared_voice_metadata (RD-4)."""
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    mock_profile = MagicMock()
    mock_profile.id = "hcp-003"
    mock_profile.agent_id = "agent-003"
    mock_profile.agent_sync_status = "synced"
    mock_profile.voice_live_instance_id = "inst-003"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_profile
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch(
        "app.services.agent_sync_service.update_agent_metadata_only",
        new_callable=AsyncMock,
        return_value="10",
    ) as mock_update_meta:
        from app.services.voice_live_instance_service import unassign_from_hcp

        await unassign_from_hcp(mock_db, "hcp-003")

    # Verify cleared metadata was sent
    mock_update_meta.assert_called_once()
    call_args = mock_update_meta.call_args
    assert call_args[0][1] == "agent-003"
    metadata = call_args[0][2]
    assert metadata["microsoft.voice-live.enabled"] == "false"
    assert metadata["microsoft.voice-live.configuration"] == "{}"


@pytest.mark.asyncio
async def test_delete_clears_metadata_for_all_assigned_hcps():
    """delete_instance clears agent metadata for all assigned HCPs with synced agents."""
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.flush = AsyncMock()
    mock_db.delete = AsyncMock()

    mock_profile1 = MagicMock()
    mock_profile1.id = "hcp-004"
    mock_profile1.agent_id = "agent-004"
    mock_profile1.agent_sync_status = "synced"
    mock_profile1.voice_live_instance_id = "inst-004"

    mock_profile2 = MagicMock()
    mock_profile2.id = "hcp-005"
    mock_profile2.agent_id = "agent-005"
    mock_profile2.agent_sync_status = "synced"
    mock_profile2.voice_live_instance_id = "inst-004"

    mock_profile3 = MagicMock()
    mock_profile3.id = "hcp-006"
    mock_profile3.agent_id = ""
    mock_profile3.agent_sync_status = "none"
    mock_profile3.voice_live_instance_id = "inst-004"

    mock_instance = MagicMock()
    mock_instance.id = "inst-004"
    mock_instance.hcp_profiles = [mock_profile1, mock_profile2, mock_profile3]

    with (
        patch(
            "app.services.voice_live_instance_service.get_instance",
            new_callable=AsyncMock,
            return_value=mock_instance,
        ),
        patch(
            "app.services.agent_sync_service.update_agent_metadata_only",
            new_callable=AsyncMock,
            return_value="10",
        ) as mock_update_meta,
    ):
        from app.services.voice_live_instance_service import delete_instance

        await delete_instance(mock_db, "inst-004")

    # Only 2 profiles had synced agents — profile3 has no agent
    assert mock_update_meta.call_count == 2
    agent_ids_called = [call.args[1] for call in mock_update_meta.call_args_list]
    assert "agent-004" in agent_ids_called
    assert "agent-005" in agent_ids_called


@pytest.mark.asyncio
async def test_sync_failure_does_not_break_crud():
    """Agent sync failure does not prevent CRUD operations from completing."""
    from app.schemas.voice_live_instance import VoiceLiveInstanceUpdate

    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    mock_instance = _make_vl_instance_mock(id="inst-005")

    mock_profile = MagicMock()
    mock_profile.id = "hcp-007"
    mock_profile.agent_id = "agent-007"
    mock_profile.agent_sync_status = "synced"
    mock_profile.voice_live_instance = mock_instance

    mock_refreshed_instance = MagicMock()
    mock_refreshed_instance.id = "inst-005"
    mock_refreshed_instance.hcp_profiles = [mock_profile]

    update_data = VoiceLiveInstanceUpdate(voice_name="test-voice")

    with (
        patch(
            "app.services.voice_live_instance_service.get_instance",
            new_callable=AsyncMock,
            side_effect=[mock_instance, mock_refreshed_instance],
        ),
        patch(
            "app.services.agent_sync_service.update_agent_metadata_only",
            new_callable=AsyncMock,
            side_effect=Exception("AI Foundry API timeout"),
        ),
    ):
        from app.services.voice_live_instance_service import update_instance

        # Should NOT raise despite sync failure
        result = await update_instance(mock_db, "inst-005", update_data)

    # CRUD succeeded
    assert result.id == "inst-005"
    mock_db.commit.assert_called()


# ===========================================================================
# Phase 16 coverage boost: CRUD operations (create, get, list),
# resolve_voice_config, NotFoundException paths, metadata sync failure logs
# ===========================================================================


@pytest.mark.asyncio
async def test_get_instance_not_found():
    """get_instance raises NotFoundException when instance doesn't exist."""
    from app.utils.exceptions import NotFoundException

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    from app.services.voice_live_instance_service import get_instance

    with pytest.raises(NotFoundException, match="not found"):
        await get_instance(mock_db, "nonexistent-id")


@pytest.mark.asyncio
async def test_list_instances():
    """list_instances returns paginated items and total count."""
    mock_db = AsyncMock()

    # Mock count query
    mock_count_result = MagicMock()
    mock_count_result.scalar.return_value = 3

    # Mock items query
    inst1 = _make_vl_instance_mock(id="inst-a")
    inst2 = _make_vl_instance_mock(id="inst-b")
    mock_items_result = MagicMock()
    mock_items_result.scalars.return_value.all.return_value = [inst1, inst2]

    mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_items_result])

    from app.services.voice_live_instance_service import list_instances

    items, total = await list_instances(mock_db, page=1, page_size=2)

    assert total == 3
    assert len(items) == 2


@pytest.mark.asyncio
async def test_create_instance():
    """create_instance creates a VoiceLiveInstance and returns it."""
    from app.schemas.voice_live_instance import VoiceLiveInstanceCreate

    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.add = MagicMock()

    created_inst = _make_vl_instance_mock(id="new-inst")

    create_data = VoiceLiveInstanceCreate(
        name="New Instance",
        voice_name="en-US-AvaNeural",
    )

    with patch(
        "app.services.voice_live_instance_service.get_instance",
        new_callable=AsyncMock,
        return_value=created_inst,
    ):
        from app.services.voice_live_instance_service import create_instance

        result = await create_instance(mock_db, create_data, "user-001")

    assert result.id == "new-inst"
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_assign_to_hcp_not_found():
    """assign_to_hcp raises NotFoundException when HCP profile doesn't exist."""
    from app.utils.exceptions import NotFoundException

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    mock_instance = MagicMock()
    mock_instance.id = "inst-x"

    with patch(
        "app.services.voice_live_instance_service.get_instance",
        new_callable=AsyncMock,
        return_value=mock_instance,
    ):
        from app.services.voice_live_instance_service import assign_to_hcp

        with pytest.raises(NotFoundException, match="HCP Profile"):
            await assign_to_hcp(mock_db, "inst-x", "nonexistent-hcp")


@pytest.mark.asyncio
async def test_unassign_from_hcp_not_found():
    """unassign_from_hcp raises NotFoundException when HCP profile doesn't exist."""
    from app.utils.exceptions import NotFoundException

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    from app.services.voice_live_instance_service import unassign_from_hcp

    with pytest.raises(NotFoundException, match="HCP Profile"):
        await unassign_from_hcp(mock_db, "nonexistent-hcp")


@pytest.mark.asyncio
async def test_assign_metadata_sync_failure_does_not_break():
    """assign_to_hcp continues even if agent metadata sync fails."""
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.expire_all = MagicMock()

    mock_profile = MagicMock()
    mock_profile.id = "hcp-sync-fail"
    mock_profile.agent_id = "agent-sync-fail"
    mock_profile.agent_sync_status = "synced"
    mock_profile.voice_live_instance_id = None
    # Inline fallback fields
    mock_profile.voice_live_instance = None
    mock_profile.voice_live_enabled = True
    mock_profile.voice_live_model = "gpt-4o"
    mock_profile.voice_name = "en-US-AvaNeural"
    mock_profile.voice_type = "azure-standard"
    mock_profile.voice_temperature = 0.9
    mock_profile.voice_custom = False
    mock_profile.avatar_character = "lori"
    mock_profile.avatar_style = "casual"
    mock_profile.avatar_customized = False
    mock_profile.turn_detection_type = "server_vad"
    mock_profile.noise_suppression = False
    mock_profile.echo_cancellation = False
    mock_profile.eou_detection = False
    mock_profile.recognition_language = "auto"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_profile
    mock_db.execute = AsyncMock(return_value=mock_result)

    mock_instance = MagicMock()
    mock_instance.id = "inst-fail"

    with (
        patch(
            "app.services.voice_live_instance_service.get_instance",
            new_callable=AsyncMock,
            return_value=mock_instance,
        ),
        patch(
            "app.services.agent_sync_service.update_agent_metadata_only",
            new_callable=AsyncMock,
            side_effect=Exception("metadata sync error"),
        ),
    ):
        from app.services.voice_live_instance_service import assign_to_hcp

        # Should NOT raise despite sync failure
        result = await assign_to_hcp(mock_db, "inst-fail", "hcp-sync-fail")

    assert result.id == "hcp-sync-fail"


@pytest.mark.asyncio
async def test_unassign_metadata_clear_failure_does_not_break():
    """unassign_from_hcp continues even if agent metadata clear fails."""
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    mock_profile = MagicMock()
    mock_profile.id = "hcp-clear-fail"
    mock_profile.agent_id = "agent-clear-fail"
    mock_profile.agent_sync_status = "synced"
    mock_profile.voice_live_instance_id = "inst-clear"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_profile
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch(
        "app.services.agent_sync_service.update_agent_metadata_only",
        new_callable=AsyncMock,
        side_effect=Exception("clear metadata error"),
    ):
        from app.services.voice_live_instance_service import unassign_from_hcp

        # Should NOT raise despite metadata clear failure
        result = await unassign_from_hcp(mock_db, "hcp-clear-fail")

    assert result.id == "hcp-clear-fail"


@pytest.mark.asyncio
async def test_delete_instance_metadata_clear_failure_does_not_break():
    """delete_instance continues even if clearing agent metadata fails."""
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.flush = AsyncMock()
    mock_db.delete = AsyncMock()

    mock_profile = MagicMock()
    mock_profile.id = "hcp-del-fail"
    mock_profile.agent_id = "agent-del-fail"
    mock_profile.agent_sync_status = "synced"
    mock_profile.voice_live_instance_id = "inst-del"

    mock_instance = MagicMock()
    mock_instance.id = "inst-del"
    mock_instance.hcp_profiles = [mock_profile]

    with (
        patch(
            "app.services.voice_live_instance_service.get_instance",
            new_callable=AsyncMock,
            return_value=mock_instance,
        ),
        patch(
            "app.services.agent_sync_service.update_agent_metadata_only",
            new_callable=AsyncMock,
            side_effect=Exception("clear metadata fail"),
        ),
    ):
        from app.services.voice_live_instance_service import delete_instance

        # Should NOT raise despite metadata clear failure
        await delete_instance(mock_db, "inst-del")

    mock_db.delete.assert_called_once()
    mock_db.commit.assert_called()


def test_resolve_voice_config_with_vl_instance():
    """resolve_voice_config returns VoiceLiveInstance fields when assigned."""
    from app.services.voice_live_instance_service import resolve_voice_config

    mock_profile = MagicMock()
    mock_instance = _make_vl_instance_mock(
        voice_name="zh-CN-XiaoxiaoMultilingualNeural",
        response_temperature=0.6,
        custom_lexicon_enabled=True,
        custom_lexicon_url="https://lexicon.example.com",
    )
    mock_profile.voice_live_instance = mock_instance
    mock_profile.id = "hcp-resolve"

    result = resolve_voice_config(mock_profile)

    assert result["voice_name"] == "zh-CN-XiaoxiaoMultilingualNeural"
    assert result["response_temperature"] == 0.6
    assert result["custom_lexicon_enabled"] is True
    assert result["custom_lexicon_url"] == "https://lexicon.example.com"


def test_resolve_voice_config_inline_fallback():
    """resolve_voice_config returns a hardcoded safe-defaults dict when no VL instance
    is assigned -- D-12: does not read any deprecated HcpProfile column (they no longer
    exist on the model post-Plan-29-05 migration)."""
    from app.services.voice_live_instance_service import resolve_voice_config

    mock_profile = MagicMock(spec=["voice_live_instance", "id"])
    mock_profile.voice_live_instance = None
    mock_profile.id = "hcp-inline"

    result = resolve_voice_config(mock_profile)

    assert result["voice_name"] == "en-US-AvaNeural"
    assert result["voice_live_enabled"] is False
    assert result["avatar_enabled"] is False
    assert result["avatar_character"] == "lori"
    assert result["avatar_style"] == "casual"
    assert result["model_instruction"] == ""
    assert result["response_temperature"] == 0.8  # default
    assert result["custom_lexicon_enabled"] is False  # default


# ===========================================================================
# Real-data integration tests: use real DB (in-memory SQLite via conftest)
# ===========================================================================


def _seed_user(db):
    """Create a test User and add to session (not flushed yet)."""
    from app.models.user import User
    from app.services.auth import get_password_hash

    user = User(
        username="vl_test_user",
        email="vltest@test.com",
        hashed_password=get_password_hash("password123"),
        full_name="VL Test User",
        role="admin",
    )
    db.add(user)
    return user


def _seed_hcp(db, user_id, *, name="Dr. VL Test", agent_id="", agent_sync_status="none"):
    """Create a test HcpProfile and add to session (not flushed yet)."""
    from app.models.hcp_profile import HcpProfile

    hcp = HcpProfile(
        name=name,
        specialty="Oncology",
        created_by=user_id,
        agent_id=agent_id,
        agent_sync_status=agent_sync_status,
    )
    db.add(hcp)
    return hcp


def _seed_vl_instance(db, user_id, *, name="Test VL Instance", **overrides):
    """Create a test VoiceLiveInstance and add to session (not flushed yet)."""
    from app.models.voice_live_instance import VoiceLiveInstance

    defaults = {
        "name": name,
        "created_by": user_id,
        "voice_name": "en-US-AvaNeural",
        "voice_live_model": "gpt-4o",
    }
    defaults.update(overrides)
    inst = VoiceLiveInstance(**defaults)
    db.add(inst)
    return inst


@pytest.mark.asyncio
class TestRealVoiceLiveInstanceService:
    """Integration tests using real async SQLite DB via db_session fixture."""

    async def test_create_instance_real_db(self, db_session):
        """create_instance persists a new VoiceLiveInstance in the real DB."""
        from app.schemas.voice_live_instance import VoiceLiveInstanceCreate
        from app.services.voice_live_instance_service import create_instance

        user = _seed_user(db_session)
        await db_session.flush()

        data = VoiceLiveInstanceCreate(
            name="Real DB Instance",
            voice_name="zh-CN-XiaoxiaoMultilingualNeural",
            response_temperature=0.6,
        )
        result = await create_instance(db_session, data, user.id)

        assert result.id is not None
        assert result.name == "Real DB Instance"
        assert result.voice_name == "zh-CN-XiaoxiaoMultilingualNeural"
        assert result.response_temperature == 0.6
        assert result.created_by == user.id
        # Defaults
        assert result.voice_live_model == "gpt-4o"
        assert result.enabled is True
        assert result.avatar_character == "lori"

    async def test_get_instance_real_db(self, db_session):
        """get_instance returns the VoiceLiveInstance with eagerly loaded hcp_profiles."""
        from app.services.voice_live_instance_service import get_instance

        user = _seed_user(db_session)
        await db_session.flush()

        inst = _seed_vl_instance(db_session, user.id, name="Fetchable Instance")
        await db_session.flush()

        result = await get_instance(db_session, inst.id)

        assert result.id == inst.id
        assert result.name == "Fetchable Instance"
        assert result.hcp_profiles == []

    async def test_get_instance_not_found_real_db(self, db_session):
        """get_instance raises NotFoundException for a nonexistent ID."""
        from app.services.voice_live_instance_service import get_instance
        from app.utils.exceptions import NotFoundException

        with pytest.raises(NotFoundException, match="not found"):
            await get_instance(db_session, "nonexistent-id-12345")

    async def test_list_instances_real_db(self, db_session):
        """list_instances returns paginated results from real DB."""
        from app.services.voice_live_instance_service import list_instances

        user = _seed_user(db_session)
        await db_session.flush()

        for i in range(5):
            _seed_vl_instance(db_session, user.id, name=f"Instance {i}")
        await db_session.flush()

        items, total = await list_instances(db_session, page=1, page_size=3)
        assert total == 5
        assert len(items) == 3

        items2, total2 = await list_instances(db_session, page=2, page_size=3)
        assert total2 == 5
        assert len(items2) == 2

    async def test_update_instance_real_db(self, db_session):
        """update_instance modifies fields in real DB and returns refreshed instance."""
        from app.schemas.voice_live_instance import VoiceLiveInstanceUpdate
        from app.services.voice_live_instance_service import update_instance

        user = _seed_user(db_session)
        await db_session.flush()

        inst = _seed_vl_instance(db_session, user.id, name="Before Update")
        await db_session.flush()

        update_data = VoiceLiveInstanceUpdate(
            name="After Update",
            voice_name="zh-CN-XiaoxiaoMultilingualNeural",
            response_temperature=0.5,
        )

        result = await update_instance(db_session, inst.id, update_data)

        assert result.name == "After Update"
        assert result.voice_name == "zh-CN-XiaoxiaoMultilingualNeural"
        assert result.response_temperature == 0.5
        # Unchanged fields remain
        assert result.voice_live_model == "gpt-4o"

    async def test_update_instance_triggers_resync_real_db(self, db_session):
        """update_instance re-syncs agent metadata for assigned HCPs with synced agents."""
        from app.schemas.voice_live_instance import VoiceLiveInstanceUpdate
        from app.services.voice_live_instance_service import update_instance

        user = _seed_user(db_session)
        await db_session.flush()

        inst = _seed_vl_instance(db_session, user.id, name="Sync Test Instance")
        await db_session.flush()

        hcp = _seed_hcp(
            db_session,
            user.id,
            name="Dr. Synced",
            agent_id="agent-real-001",
            agent_sync_status="synced",
        )
        hcp.voice_live_instance_id = inst.id
        await db_session.flush()

        update_data = VoiceLiveInstanceUpdate(voice_name="zh-CN-XiaoxiaoMultilingualNeural")

        with patch(
            "app.services.agent_sync_service.update_agent_metadata_only",
            new_callable=AsyncMock,
            return_value="10",
        ) as mock_meta:
            result = await update_instance(db_session, inst.id, update_data)

        assert result.voice_name == "zh-CN-XiaoxiaoMultilingualNeural"
        mock_meta.assert_called_once()
        assert mock_meta.call_args[0][1] == "agent-real-001"

    async def test_update_instance_skips_unsynced_hcps_real_db(self, db_session):
        """update_instance does NOT trigger resync for HCPs without synced agents."""
        from app.schemas.voice_live_instance import VoiceLiveInstanceUpdate
        from app.services.voice_live_instance_service import update_instance

        user = _seed_user(db_session)
        await db_session.flush()

        inst = _seed_vl_instance(db_session, user.id, name="No Sync Instance")
        await db_session.flush()

        # HCP with no agent
        hcp = _seed_hcp(db_session, user.id, name="Dr. NoAgent")
        hcp.voice_live_instance_id = inst.id
        await db_session.flush()

        update_data = VoiceLiveInstanceUpdate(voice_name="test-voice")

        with patch(
            "app.services.agent_sync_service.update_agent_metadata_only",
            new_callable=AsyncMock,
            return_value="10",
        ) as mock_meta:
            await update_instance(db_session, inst.id, update_data)

        mock_meta.assert_not_called()

    async def test_delete_instance_real_db(self, db_session):
        """delete_instance removes the instance and unassigns all HCPs."""
        from sqlalchemy import select

        from app.models.hcp_profile import HcpProfile
        from app.models.voice_live_instance import VoiceLiveInstance
        from app.services.voice_live_instance_service import delete_instance

        user = _seed_user(db_session)
        await db_session.flush()

        inst = _seed_vl_instance(db_session, user.id, name="To Delete")
        await db_session.flush()

        hcp = _seed_hcp(db_session, user.id, name="Dr. Assigned")
        hcp.voice_live_instance_id = inst.id
        await db_session.flush()

        inst_id = inst.id
        hcp_id = hcp.id

        await delete_instance(db_session, inst_id)

        # Instance is gone
        result = await db_session.execute(
            select(VoiceLiveInstance).where(VoiceLiveInstance.id == inst_id)
        )
        assert result.scalar_one_or_none() is None

        # HCP still exists but unassigned
        result = await db_session.execute(select(HcpProfile).where(HcpProfile.id == hcp_id))
        remaining_hcp = result.scalar_one_or_none()
        assert remaining_hcp is not None
        assert remaining_hcp.voice_live_instance_id is None

    async def test_delete_clears_metadata_for_synced_hcps_real_db(self, db_session):
        """delete_instance clears agent metadata for synced HCPs but skips unsynced ones."""
        from app.services.voice_live_instance_service import delete_instance

        user = _seed_user(db_session)
        await db_session.flush()

        inst = _seed_vl_instance(db_session, user.id, name="Delete Sync Test")
        await db_session.flush()

        # Synced HCP
        hcp1 = _seed_hcp(
            db_session,
            user.id,
            name="Dr. Synced1",
            agent_id="agent-del-1",
            agent_sync_status="synced",
        )
        hcp1.voice_live_instance_id = inst.id

        # Unsynced HCP — should NOT trigger metadata clear
        hcp2 = _seed_hcp(
            db_session,
            user.id,
            name="Dr. NoAgent",
        )
        hcp2.voice_live_instance_id = inst.id
        await db_session.flush()

        with patch(
            "app.services.agent_sync_service.update_agent_metadata_only",
            new_callable=AsyncMock,
            return_value="10",
        ) as mock_meta:
            await delete_instance(db_session, inst.id)

        # Only the synced HCP should have triggered metadata clear
        mock_meta.assert_called_once()
        assert mock_meta.call_args[0][1] == "agent-del-1"
        # Verify cleared metadata
        metadata = mock_meta.call_args[0][2]
        assert metadata["microsoft.voice-live.enabled"] == "false"

    async def test_assign_to_hcp_real_db(self, db_session):
        """assign_to_hcp links the VoiceLiveInstance to the HcpProfile in real DB."""
        from app.models.hcp_profile import HcpProfile
        from app.services.voice_live_instance_service import assign_to_hcp

        user = _seed_user(db_session)
        await db_session.flush()

        inst = _seed_vl_instance(db_session, user.id, name="Assign Test")
        await db_session.flush()

        hcp = _seed_hcp(db_session, user.id, name="Dr. ToAssign")
        await db_session.flush()
        hcp_id = hcp.id
        inst_id = inst.id

        await assign_to_hcp(db_session, inst_id, hcp_id)

        # Re-query to verify — assign_to_hcp calls expire_all() which breaks lazy loads
        result = await db_session.execute(select(HcpProfile).where(HcpProfile.id == hcp_id))
        reloaded = result.scalar_one()
        assert reloaded.voice_live_instance_id == inst_id

    async def test_assign_triggers_resync_real_db(self, db_session):
        """assign_to_hcp triggers agent metadata sync for HCP with synced agent."""
        from app.models.hcp_profile import HcpProfile
        from app.services.voice_live_instance_service import assign_to_hcp

        user = _seed_user(db_session)
        await db_session.flush()

        inst = _seed_vl_instance(db_session, user.id, name="Assign Sync Test")
        await db_session.flush()

        hcp = _seed_hcp(
            db_session,
            user.id,
            name="Dr. SyncAssign",
            agent_id="agent-assign-1",
            agent_sync_status="synced",
        )
        await db_session.flush()
        hcp_id = hcp.id
        inst_id = inst.id

        with patch(
            "app.services.agent_sync_service.update_agent_metadata_only",
            new_callable=AsyncMock,
            return_value="10",
        ) as mock_meta:
            await assign_to_hcp(db_session, inst_id, hcp_id)

        # Re-query to verify — assign_to_hcp calls expire_all()
        result = await db_session.execute(select(HcpProfile).where(HcpProfile.id == hcp_id))
        reloaded = result.scalar_one()
        assert reloaded.voice_live_instance_id == inst_id
        mock_meta.assert_called_once()
        assert mock_meta.call_args[0][1] == "agent-assign-1"

    async def test_assign_to_hcp_not_found_real_db(self, db_session):
        """assign_to_hcp raises NotFoundException for nonexistent HCP profile."""
        from app.services.voice_live_instance_service import assign_to_hcp
        from app.utils.exceptions import NotFoundException

        user = _seed_user(db_session)
        await db_session.flush()

        inst = _seed_vl_instance(db_session, user.id, name="Assign Fail Test")
        await db_session.flush()

        with pytest.raises(NotFoundException, match="HCP Profile"):
            await assign_to_hcp(db_session, inst.id, "nonexistent-hcp-id")

    async def test_assign_instance_not_found_real_db(self, db_session):
        """assign_to_hcp raises NotFoundException for nonexistent VL instance."""
        from app.services.voice_live_instance_service import assign_to_hcp
        from app.utils.exceptions import NotFoundException

        user = _seed_user(db_session)
        await db_session.flush()

        hcp = _seed_hcp(db_session, user.id, name="Dr. Orphan")
        await db_session.flush()

        with pytest.raises(NotFoundException, match="Voice Live Instance"):
            await assign_to_hcp(db_session, "nonexistent-inst-id", hcp.id)

    async def test_unassign_from_hcp_real_db(self, db_session):
        """unassign_from_hcp clears the voice_live_instance_id on the HCP profile."""
        from app.services.voice_live_instance_service import unassign_from_hcp

        user = _seed_user(db_session)
        await db_session.flush()

        inst = _seed_vl_instance(db_session, user.id, name="Unassign Test")
        await db_session.flush()

        hcp = _seed_hcp(db_session, user.id, name="Dr. ToUnassign")
        hcp.voice_live_instance_id = inst.id
        await db_session.flush()

        result = await unassign_from_hcp(db_session, hcp.id)

        assert result.voice_live_instance_id is None

    async def test_unassign_clears_metadata_real_db(self, db_session):
        """unassign_from_hcp sends cleared metadata to the agent for synced HCP."""
        from app.services.voice_live_instance_service import unassign_from_hcp

        user = _seed_user(db_session)
        await db_session.flush()

        inst = _seed_vl_instance(db_session, user.id, name="Unassign Meta Test")
        await db_session.flush()

        hcp = _seed_hcp(
            db_session,
            user.id,
            name="Dr. MetaClear",
            agent_id="agent-unassign-1",
            agent_sync_status="synced",
        )
        hcp.voice_live_instance_id = inst.id
        await db_session.flush()

        with patch(
            "app.services.agent_sync_service.update_agent_metadata_only",
            new_callable=AsyncMock,
            return_value="10",
        ) as mock_meta:
            result = await unassign_from_hcp(db_session, hcp.id)

        assert result.voice_live_instance_id is None
        mock_meta.assert_called_once()
        assert mock_meta.call_args[0][1] == "agent-unassign-1"
        metadata = mock_meta.call_args[0][2]
        assert metadata["microsoft.voice-live.enabled"] == "false"
        assert metadata["microsoft.voice-live.configuration"] == "{}"

    async def test_unassign_from_hcp_not_found_real_db(self, db_session):
        """unassign_from_hcp raises NotFoundException for nonexistent HCP profile."""
        from app.services.voice_live_instance_service import unassign_from_hcp
        from app.utils.exceptions import NotFoundException

        with pytest.raises(NotFoundException, match="HCP Profile"):
            await unassign_from_hcp(db_session, "nonexistent-hcp-id-xyz")

    async def test_resolve_voice_config_with_vl_instance_real_db(self, db_session):
        """resolve_voice_config returns VoiceLiveInstance fields when assigned (real DB)."""
        from sqlalchemy.orm import selectinload

        from app.models.hcp_profile import HcpProfile
        from app.services.voice_live_instance_service import resolve_voice_config

        user = _seed_user(db_session)
        await db_session.flush()

        inst = _seed_vl_instance(
            db_session,
            user.id,
            name="Config Resolve Test",
            voice_name="zh-CN-XiaoxiaoMultilingualNeural",
            response_temperature=0.6,
            custom_lexicon_enabled=True,
            custom_lexicon_url="https://lexicon.example.com",
        )
        await db_session.flush()

        hcp = _seed_hcp(db_session, user.id, name="Dr. Resolve")
        hcp.voice_live_instance_id = inst.id
        await db_session.flush()
        hcp_id = hcp.id

        # Eagerly load the relationship for resolve_voice_config
        result = await db_session.execute(
            select(HcpProfile)
            .options(selectinload(HcpProfile.voice_live_instance))
            .where(HcpProfile.id == hcp_id)
        )
        loaded_hcp = result.scalar_one()

        config = resolve_voice_config(loaded_hcp)

        assert config["voice_name"] == "zh-CN-XiaoxiaoMultilingualNeural"
        assert config["response_temperature"] == 0.6
        assert config["custom_lexicon_enabled"] is True
        assert config["custom_lexicon_url"] == "https://lexicon.example.com"
        assert config["voice_live_enabled"] is True
        assert config["voice_live_model"] == "gpt-4o"

    async def test_resolve_voice_config_inline_fallback_real_db(self, db_session):
        """resolve_voice_config returns the hardcoded safe-defaults dict when no VL
        instance is assigned (D-12)."""
        from app.services.voice_live_instance_service import resolve_voice_config

        user = _seed_user(db_session)
        await db_session.flush()

        hcp = _seed_hcp(db_session, user.id, name="Dr. Inline")
        await db_session.flush()

        # Load with relationship (should be None)
        from sqlalchemy.orm import selectinload

        from app.models.hcp_profile import HcpProfile

        result = await db_session.execute(
            select(HcpProfile)
            .options(selectinload(HcpProfile.voice_live_instance))
            .where(HcpProfile.id == hcp.id)
        )
        loaded_hcp = result.scalar_one()

        config = resolve_voice_config(loaded_hcp)

        assert config["voice_name"] == "en-US-AvaNeural"  # safe-defaults dict
        assert config["model_instruction"] == ""  # safe-defaults dict
        assert config["response_temperature"] == 0.8  # safe-defaults dict
        assert config["custom_lexicon_enabled"] is False  # safe-defaults dict
        assert config["voice_live_enabled"] is False  # D-12: no VL instance = voice disabled

    async def test_full_lifecycle_real_db(self, db_session):
        """End-to-end lifecycle: create -> assign -> update -> unassign -> delete."""
        from app.models.hcp_profile import HcpProfile
        from app.models.voice_live_instance import VoiceLiveInstance
        from app.schemas.voice_live_instance import (
            VoiceLiveInstanceCreate,
            VoiceLiveInstanceUpdate,
        )
        from app.services.voice_live_instance_service import (
            assign_to_hcp,
            create_instance,
            delete_instance,
            get_instance,
            unassign_from_hcp,
            update_instance,
        )

        user = _seed_user(db_session)
        await db_session.flush()

        # 1. Create
        data = VoiceLiveInstanceCreate(name="Lifecycle Test", voice_name="en-US-AvaNeural")
        inst = await create_instance(db_session, data, user.id)
        assert inst.name == "Lifecycle Test"
        inst_id = inst.id

        # 2. Create HCP and assign
        hcp = _seed_hcp(db_session, user.id, name="Dr. Lifecycle")
        await db_session.flush()
        hcp_id = hcp.id

        await assign_to_hcp(db_session, inst_id, hcp_id)

        # Re-query to verify (expire_all() in assign_to_hcp prevents lazy access)
        r = await db_session.execute(select(HcpProfile).where(HcpProfile.id == hcp_id))
        assert r.scalar_one().voice_live_instance_id == inst_id

        # 3. Update instance
        update_data = VoiceLiveInstanceUpdate(voice_name="zh-CN-XiaoxiaoMultilingualNeural")
        updated = await update_instance(db_session, inst_id, update_data)
        assert updated.voice_name == "zh-CN-XiaoxiaoMultilingualNeural"

        # 4. Verify HCP is in hcp_profiles
        refreshed = await get_instance(db_session, inst_id)
        assert len(refreshed.hcp_profiles) == 1
        assert refreshed.hcp_profiles[0].id == hcp_id

        # 5. Unassign
        await unassign_from_hcp(db_session, hcp_id)
        r2 = await db_session.execute(select(HcpProfile).where(HcpProfile.id == hcp_id))
        assert r2.scalar_one().voice_live_instance_id is None

        # 6. Delete
        await delete_instance(db_session, inst_id)
        result = await db_session.execute(
            select(VoiceLiveInstance).where(VoiceLiveInstance.id == inst_id)
        )
        assert result.scalar_one_or_none() is None
