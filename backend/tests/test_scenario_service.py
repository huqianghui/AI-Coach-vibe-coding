"""Tests for the scenario service: CRUD operations and scenario cloning."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.models.hcp_profile import HcpProfile
from app.models.skill import Skill, SkillVersion
from app.models.user import User
from app.models.voice_live_instance import VoiceLiveInstance
from app.schemas.scenario import ScenarioCreate, ScenarioUpdate
from app.services.auth import get_password_hash
from app.services.scenario_service import (
    clone_scenario,
    create_scenario,
    delete_scenario,
    get_scenario,
    get_scenarios,
    update_scenario,
)
from app.utils.exceptions import NotFoundException


async def _seed_user_and_hcp(db) -> tuple[str, str]:
    """Create a user and HCP profile. Returns (user_id, hcp_profile_id)."""
    user = User(
        username="scnuser",
        email="scn@test.com",
        hashed_password=get_password_hash("pass"),
        full_name="Scenario User",
        role="admin",
    )
    db.add(user)
    await db.flush()

    hcp = HcpProfile(
        name="Dr. Test",
        specialty="Oncology",
        created_by=user.id,
    )
    db.add(hcp)
    await db.flush()

    return user.id, hcp.id


async def _seed_skill(db, user_id: str) -> str:
    """Create a published skill with a published version. Returns skill_id."""
    skill = Skill(
        name="Test Skill",
        description="A test skill",
        status="published",
        created_by=user_id,
    )
    db.add(skill)
    await db.flush()

    version = SkillVersion(
        skill_id=skill.id,
        version_number=1,
        content="test content",
        is_published=True,
        created_by=user_id,
    )
    db.add(version)
    await db.flush()

    return skill.id


class TestCreateScenario:
    """Tests for create_scenario."""

    async def test_creates_scenario_with_required_fields(self, db_session):
        user_id, hcp_id = await _seed_user_and_hcp(db_session)
        skill_id = await _seed_skill(db_session, user_id)
        data = ScenarioCreate(
            name="Test Scenario",
            hcp_profile_id=hcp_id,
            rubric_id="test-rubric-id",
            skill_id=skill_id,
        )
        scenario = await create_scenario(db_session, data, user_id)

        assert scenario.name == "Test Scenario"
        assert scenario.hcp_profile_id == hcp_id
        assert scenario.created_by == user_id
        assert scenario.skill_id == skill_id
        assert scenario.id is not None

    async def test_serializes_key_messages(self, db_session):
        user_id, hcp_id = await _seed_user_and_hcp(db_session)
        skill_id = await _seed_skill(db_session, user_id)
        data = ScenarioCreate(
            name="S",
            hcp_profile_id=hcp_id,
            rubric_id="test-rubric-id",
            skill_id=skill_id,
            key_messages=["Key msg 1", "Key msg 2"],
        )
        scenario = await create_scenario(db_session, data, user_id)

        assert json.loads(scenario.key_messages) == ["Key msg 1", "Key msg 2"]

    async def test_serializes_tags(self, db_session):
        user_id, hcp_id = await _seed_user_and_hcp(db_session)
        skill_id = await _seed_skill(db_session, user_id)
        data = ScenarioCreate(
            name="S",
            hcp_profile_id=hcp_id,
            rubric_id="test-rubric-id",
            skill_id=skill_id,
            tags=["product:Brukinsa", "area:Oncology"],
        )
        scenario = await create_scenario(db_session, data, user_id)

        assert json.loads(scenario.tags) == ["product:Brukinsa", "area:Oncology"]

    async def test_default_tags_empty_list(self, db_session):
        user_id, hcp_id = await _seed_user_and_hcp(db_session)
        skill_id = await _seed_skill(db_session, user_id)
        data = ScenarioCreate(
            name="S",
            hcp_profile_id=hcp_id,
            rubric_id="test-rubric-id",
            skill_id=skill_id,
        )
        scenario = await create_scenario(db_session, data, user_id)

        assert json.loads(scenario.tags) == []

    async def test_raises_for_nonexistent_hcp_profile(self, db_session):
        user_id, _ = await _seed_user_and_hcp(db_session)
        skill_id = await _seed_skill(db_session, user_id)
        data = ScenarioCreate(
            name="S",
            hcp_profile_id="nonexistent-hcp",
            rubric_id="test-rubric-id",
            skill_id=skill_id,
        )
        with pytest.raises(NotFoundException):
            await create_scenario(db_session, data, user_id)

    async def test_applies_rubric_id_and_defaults(self, db_session):
        user_id, hcp_id = await _seed_user_and_hcp(db_session)
        skill_id = await _seed_skill(db_session, user_id)
        data = ScenarioCreate(
            name="S",
            hcp_profile_id=hcp_id,
            rubric_id="test-rubric-id",
            skill_id=skill_id,
        )
        scenario = await create_scenario(db_session, data, user_id)

        assert scenario.rubric_id == "test-rubric-id"
        assert scenario.pass_threshold == 70
        assert scenario.mode == "f2f"
        assert scenario.difficulty == "medium"
        assert scenario.status == "draft"

    async def test_pins_skill_version(self, db_session):
        user_id, hcp_id = await _seed_user_and_hcp(db_session)
        skill_id = await _seed_skill(db_session, user_id)
        data = ScenarioCreate(
            name="S",
            hcp_profile_id=hcp_id,
            rubric_id="test-rubric-id",
            skill_id=skill_id,
        )
        scenario = await create_scenario(db_session, data, user_id)

        assert scenario.skill_id == skill_id
        assert scenario.skill_version_id is not None


class TestGetScenarios:
    """Tests for get_scenarios (list with filters)."""

    async def test_returns_all_scenarios(self, db_session):
        user_id, hcp_id = await _seed_user_and_hcp(db_session)
        skill_id = await _seed_skill(db_session, user_id)
        for name in ["S1", "S2"]:
            data = ScenarioCreate(
                name=name,
                hcp_profile_id=hcp_id,
                rubric_id="test-rubric-id",
                skill_id=skill_id,
            )
            await create_scenario(db_session, data, user_id)

        scenarios, total = await get_scenarios(db_session)
        assert total == 2
        assert len(scenarios) == 2

    async def test_filters_by_status(self, db_session):
        user_id, hcp_id = await _seed_user_and_hcp(db_session)
        skill_id = await _seed_skill(db_session, user_id)
        # Create a draft (default)
        await create_scenario(
            db_session,
            ScenarioCreate(
                name="Draft",
                hcp_profile_id=hcp_id,
                rubric_id="test-rubric-id",
                skill_id=skill_id,
            ),
            user_id,
        )
        # Create and manually set to active
        active = await create_scenario(
            db_session,
            ScenarioCreate(
                name="Active",
                hcp_profile_id=hcp_id,
                rubric_id="test-rubric-id",
                skill_id=skill_id,
            ),
            user_id,
        )
        active.status = "active"
        await db_session.flush()

        scenarios, total = await get_scenarios(db_session, status="active")
        assert total == 1
        assert scenarios[0].name == "Active"

    async def test_filters_by_mode(self, db_session):
        user_id, hcp_id = await _seed_user_and_hcp(db_session)
        skill_id = await _seed_skill(db_session, user_id)
        for mode in ["f2f", "conference"]:
            data = ScenarioCreate(
                name=f"Mode {mode}",
                hcp_profile_id=hcp_id,
                rubric_id="test-rubric-id",
                skill_id=skill_id,
                mode=mode,
            )
            await create_scenario(db_session, data, user_id)

        scenarios, total = await get_scenarios(db_session, mode="conference")
        assert total == 1
        assert scenarios[0].mode == "conference"

    async def test_search_by_name(self, db_session):
        user_id, hcp_id = await _seed_user_and_hcp(db_session)
        skill_id = await _seed_skill(db_session, user_id)
        await create_scenario(
            db_session,
            ScenarioCreate(
                name="Brukinsa F2F",
                hcp_profile_id=hcp_id,
                rubric_id="test-rubric-id",
                skill_id=skill_id,
            ),
            user_id,
        )
        await create_scenario(
            db_session,
            ScenarioCreate(
                name="Other",
                hcp_profile_id=hcp_id,
                rubric_id="test-rubric-id",
                skill_id=skill_id,
            ),
            user_id,
        )

        scenarios, total = await get_scenarios(db_session, search="Brukinsa")
        assert total == 1

    async def test_pagination(self, db_session):
        user_id, hcp_id = await _seed_user_and_hcp(db_session)
        skill_id = await _seed_skill(db_session, user_id)
        for i in range(5):
            await create_scenario(
                db_session,
                ScenarioCreate(
                    name=f"S{i}",
                    hcp_profile_id=hcp_id,
                    rubric_id="test-rubric-id",
                    skill_id=skill_id,
                ),
                user_id,
            )

        scenarios, total = await get_scenarios(db_session, page=1, page_size=2)
        assert total == 5
        assert len(scenarios) == 2


class TestGetScenario:
    """Tests for get_scenario (single by ID)."""

    async def test_returns_scenario_by_id(self, db_session):
        user_id, hcp_id = await _seed_user_and_hcp(db_session)
        skill_id = await _seed_skill(db_session, user_id)
        data = ScenarioCreate(
            name="Single",
            hcp_profile_id=hcp_id,
            rubric_id="test-rubric-id",
            skill_id=skill_id,
        )
        created = await create_scenario(db_session, data, user_id)
        fetched = await get_scenario(db_session, created.id)
        assert fetched.name == "Single"

    async def test_raises_not_found(self, db_session):
        with pytest.raises(NotFoundException):
            await get_scenario(db_session, "nonexistent-id")


class TestUpdateScenario:
    """Tests for update_scenario."""

    async def test_updates_partial_fields(self, db_session):
        user_id, hcp_id = await _seed_user_and_hcp(db_session)
        skill_id = await _seed_skill(db_session, user_id)
        data = ScenarioCreate(
            name="Old Name",
            hcp_profile_id=hcp_id,
            rubric_id="test-rubric-id",
            skill_id=skill_id,
        )
        scenario = await create_scenario(db_session, data, user_id)

        update = ScenarioUpdate(name="New Name")
        updated = await update_scenario(db_session, scenario.id, update)

        assert updated.name == "New Name"
        assert updated.skill_id == skill_id  # unchanged

    async def test_updates_key_messages(self, db_session):
        user_id, hcp_id = await _seed_user_and_hcp(db_session)
        skill_id = await _seed_skill(db_session, user_id)
        data = ScenarioCreate(
            name="S",
            hcp_profile_id=hcp_id,
            rubric_id="test-rubric-id",
            skill_id=skill_id,
        )
        scenario = await create_scenario(db_session, data, user_id)

        update = ScenarioUpdate(key_messages=["New KM 1", "New KM 2"])
        updated = await update_scenario(db_session, scenario.id, update)
        assert json.loads(updated.key_messages) == ["New KM 1", "New KM 2"]

    async def test_updates_tags(self, db_session):
        user_id, hcp_id = await _seed_user_and_hcp(db_session)
        skill_id = await _seed_skill(db_session, user_id)
        data = ScenarioCreate(
            name="S",
            hcp_profile_id=hcp_id,
            rubric_id="test-rubric-id",
            skill_id=skill_id,
            tags=["old-tag"],
        )
        scenario = await create_scenario(db_session, data, user_id)

        update = ScenarioUpdate(tags=["new-tag-1", "new-tag-2"])
        updated = await update_scenario(db_session, scenario.id, update)
        assert json.loads(updated.tags) == ["new-tag-1", "new-tag-2"]

    async def test_validates_new_hcp_profile_exists(self, db_session):
        user_id, hcp_id = await _seed_user_and_hcp(db_session)
        skill_id = await _seed_skill(db_session, user_id)
        data = ScenarioCreate(
            name="S",
            hcp_profile_id=hcp_id,
            rubric_id="test-rubric-id",
            skill_id=skill_id,
        )
        scenario = await create_scenario(db_session, data, user_id)

        update = ScenarioUpdate(hcp_profile_id="nonexistent")
        with pytest.raises(NotFoundException):
            await update_scenario(db_session, scenario.id, update)


class TestDeleteScenario:
    """Tests for delete_scenario."""

    async def test_deletes_existing_scenario(self, db_session):
        user_id, hcp_id = await _seed_user_and_hcp(db_session)
        skill_id = await _seed_skill(db_session, user_id)
        data = ScenarioCreate(
            name="Del",
            hcp_profile_id=hcp_id,
            rubric_id="test-rubric-id",
            skill_id=skill_id,
        )
        scenario = await create_scenario(db_session, data, user_id)
        await delete_scenario(db_session, scenario.id)

        with pytest.raises(NotFoundException):
            await get_scenario(db_session, scenario.id)

    async def test_raises_for_nonexistent(self, db_session):
        with pytest.raises(NotFoundException):
            await delete_scenario(db_session, "nonexistent")


class TestSkillValidation:
    """Tests for skill validation in create/update scenarios."""

    async def test_nonexistent_skill_raises_not_found(self, db_session):
        user_id, hcp_id = await _seed_user_and_hcp(db_session)
        data = ScenarioCreate(
            name="S",
            hcp_profile_id=hcp_id,
            rubric_id="test-rubric-id",
            skill_id="nonexistent-skill-id",
        )
        with pytest.raises(NotFoundException):
            await create_scenario(db_session, data, user_id)

    async def test_draft_skill_raises_bad_request(self, db_session):
        from app.utils.exceptions import ValidationException

        user_id, hcp_id = await _seed_user_and_hcp(db_session)
        # Create a draft skill (not published)
        skill = Skill(
            name="Draft Skill",
            status="draft",
            created_by=user_id,
        )
        db_session.add(skill)
        await db_session.flush()

        data = ScenarioCreate(
            name="S",
            hcp_profile_id=hcp_id,
            rubric_id="test-rubric-id",
            skill_id=skill.id,
        )
        with pytest.raises(ValidationException):
            await create_scenario(db_session, data, user_id)

    async def test_skill_without_published_version_raises(self, db_session):
        from app.utils.exceptions import ValidationException

        user_id, hcp_id = await _seed_user_and_hcp(db_session)
        # Create published skill but NO published version
        skill = Skill(
            name="No Version Skill",
            status="published",
            created_by=user_id,
        )
        db_session.add(skill)
        await db_session.flush()

        # Add unpublished version only
        version = SkillVersion(
            skill_id=skill.id,
            version_number=1,
            content="draft content",
            is_published=False,
            created_by=user_id,
        )
        db_session.add(version)
        await db_session.flush()

        data = ScenarioCreate(
            name="S",
            hcp_profile_id=hcp_id,
            rubric_id="test-rubric-id",
            skill_id=skill.id,
        )
        with pytest.raises(ValidationException):
            await create_scenario(db_session, data, user_id)

    async def test_update_skill_change_validates_new_skill(self, db_session):
        user_id, hcp_id = await _seed_user_and_hcp(db_session)
        skill_id = await _seed_skill(db_session, user_id)

        # Create second published skill
        skill2 = Skill(
            name="Skill 2",
            status="published",
            created_by=user_id,
        )
        db_session.add(skill2)
        await db_session.flush()
        version2 = SkillVersion(
            skill_id=skill2.id,
            version_number=1,
            content="v2 content",
            is_published=True,
            created_by=user_id,
        )
        db_session.add(version2)
        await db_session.flush()

        data = ScenarioCreate(
            name="S",
            hcp_profile_id=hcp_id,
            rubric_id="test-rubric-id",
            skill_id=skill_id,
        )
        scenario = await create_scenario(db_session, data, user_id)

        # Update to new skill
        update = ScenarioUpdate(skill_id=skill2.id)
        updated = await update_scenario(db_session, scenario.id, update)
        assert updated.skill_id == skill2.id
        assert updated.skill_version_id == version2.id

    async def test_update_same_skill_no_revalidation(self, db_session):
        user_id, hcp_id = await _seed_user_and_hcp(db_session)
        skill_id = await _seed_skill(db_session, user_id)

        data = ScenarioCreate(
            name="S",
            hcp_profile_id=hcp_id,
            rubric_id="test-rubric-id",
            skill_id=skill_id,
        )
        scenario = await create_scenario(db_session, data, user_id)

        # Update with same skill_id - should not revalidate
        update = ScenarioUpdate(skill_id=skill_id)
        updated = await update_scenario(db_session, scenario.id, update)
        assert updated.skill_id == skill_id


class TestCloneScenario:
    """Tests for clone_scenario."""

    async def test_clones_with_copy_suffix(self, db_session):
        user_id, hcp_id = await _seed_user_and_hcp(db_session)
        skill_id = await _seed_skill(db_session, user_id)
        data = ScenarioCreate(
            name="Original",
            hcp_profile_id=hcp_id,
            rubric_id="test-rubric-id",
            skill_id=skill_id,
            key_messages=["KM 1"],
            tags=["product:Brukinsa"],
        )
        original = await create_scenario(db_session, data, user_id)

        clone = await clone_scenario(db_session, original.id, user_id)

        assert clone.name == "Original (Copy)"
        assert clone.id != original.id
        assert clone.tags == original.tags
        assert clone.status == "draft"
        assert clone.hcp_profile_id == hcp_id
        assert clone.skill_id == skill_id

    async def test_clone_preserves_rubric_id(self, db_session):
        user_id, hcp_id = await _seed_user_and_hcp(db_session)
        skill_id = await _seed_skill(db_session, user_id)
        data = ScenarioCreate(
            name="With Rubric",
            hcp_profile_id=hcp_id,
            rubric_id="test-rubric-id",
            skill_id=skill_id,
        )
        original = await create_scenario(db_session, data, user_id)
        clone = await clone_scenario(db_session, original.id, user_id)

        assert clone.rubric_id == "test-rubric-id"

    async def test_clone_raises_for_nonexistent(self, db_session):
        with pytest.raises(NotFoundException):
            await clone_scenario(db_session, "nonexistent", "user")


class TestTransitionScenarioStatus:
    """Tests for state machine transitions (D-04)."""

    async def test_draft_to_active(self, db_session):
        from app.services.scenario_service import transition_scenario_status

        user_id, hcp_id = await _seed_user_and_hcp(db_session)
        skill_id = await _seed_skill(db_session, user_id)
        data = ScenarioCreate(
            name="Trans", hcp_profile_id=hcp_id, rubric_id="r1", skill_id=skill_id
        )
        scenario = await create_scenario(db_session, data, user_id)
        assert scenario.status == "draft"

        result = await transition_scenario_status(db_session, scenario.id, "active")
        assert result.status == "active"

    async def test_active_to_archived(self, db_session):
        from app.services.scenario_service import transition_scenario_status

        user_id, hcp_id = await _seed_user_and_hcp(db_session)
        skill_id = await _seed_skill(db_session, user_id)
        data = ScenarioCreate(
            name="Trans2", hcp_profile_id=hcp_id, rubric_id="r1", skill_id=skill_id
        )
        scenario = await create_scenario(db_session, data, user_id)
        await transition_scenario_status(db_session, scenario.id, "active")
        result = await transition_scenario_status(db_session, scenario.id, "archived")
        assert result.status == "archived"

    async def test_invalid_transition_raises(self, db_session):
        from app.services.scenario_service import transition_scenario_status
        from app.utils.exceptions import ValidationException

        user_id, hcp_id = await _seed_user_and_hcp(db_session)
        skill_id = await _seed_skill(db_session, user_id)
        data = ScenarioCreate(
            name="Trans3", hcp_profile_id=hcp_id, rubric_id="r1", skill_id=skill_id
        )
        scenario = await create_scenario(db_session, data, user_id)
        # draft -> archived is invalid (must go through active)
        with pytest.raises(ValidationException):
            await transition_scenario_status(db_session, scenario.id, "archived")

    async def test_archived_no_outgoing(self, db_session):
        from app.services.scenario_service import transition_scenario_status
        from app.utils.exceptions import ValidationException

        user_id, hcp_id = await _seed_user_and_hcp(db_session)
        skill_id = await _seed_skill(db_session, user_id)
        data = ScenarioCreate(
            name="Trans4", hcp_profile_id=hcp_id, rubric_id="r1", skill_id=skill_id
        )
        scenario = await create_scenario(db_session, data, user_id)
        await transition_scenario_status(db_session, scenario.id, "active")
        await transition_scenario_status(db_session, scenario.id, "archived")
        # archived -> anything is invalid
        with pytest.raises(ValidationException):
            await transition_scenario_status(db_session, scenario.id, "active")


class TestArchivedGuard:
    """Tests for archived scenario edit protection."""

    async def test_update_archived_raises(self, db_session):
        from app.services.scenario_service import transition_scenario_status
        from app.utils.exceptions import ValidationException

        user_id, hcp_id = await _seed_user_and_hcp(db_session)
        skill_id = await _seed_skill(db_session, user_id)
        data = ScenarioCreate(name="Arch", hcp_profile_id=hcp_id, rubric_id="r1", skill_id=skill_id)
        scenario = await create_scenario(db_session, data, user_id)
        await transition_scenario_status(db_session, scenario.id, "active")
        await transition_scenario_status(db_session, scenario.id, "archived")

        with pytest.raises(ValidationException, match="Cannot edit an archived"):
            await update_scenario(db_session, scenario.id, ScenarioUpdate(name="New"))

    async def test_update_draft_allowed(self, db_session):
        user_id, hcp_id = await _seed_user_and_hcp(db_session)
        skill_id = await _seed_skill(db_session, user_id)
        data = ScenarioCreate(
            name="Draft", hcp_profile_id=hcp_id, rubric_id="r1", skill_id=skill_id
        )
        scenario = await create_scenario(db_session, data, user_id)
        result = await update_scenario(db_session, scenario.id, ScenarioUpdate(name="Updated"))
        assert result.name == "Updated"

    async def test_update_active_allowed(self, db_session):
        from app.services.scenario_service import transition_scenario_status

        user_id, hcp_id = await _seed_user_and_hcp(db_session)
        skill_id = await _seed_skill(db_session, user_id)
        data = ScenarioCreate(
            name="Active", hcp_profile_id=hcp_id, rubric_id="r1", skill_id=skill_id
        )
        scenario = await create_scenario(db_session, data, user_id)
        await transition_scenario_status(db_session, scenario.id, "active")
        result = await update_scenario(db_session, scenario.id, ScenarioUpdate(name="Still OK"))
        assert result.name == "Still OK"


class TestTriggerAgentResync:
    """Regression tests for _trigger_agent_resync's HcpProfile eager-loading.

    _trigger_agent_resync loads HcpProfile via a plain select() then calls
    agent_sync_service.sync_agent_for_profile, which reads
    profile.voice_live_instance (a default lazy relationship) inside
    resolve_voice_config(). Without selectinload(HcpProfile.voice_live_instance) on
    the query, the first access to that relationship triggers an implicit lazy DB
    load with no greenlet_spawn trampoline active, raising
    sqlalchemy.exc.MissingGreenlet. These tests intentionally do NOT mock
    sync_agent_for_profile itself -- only the Azure SDK boundary functions -- so the
    real ORM relationship-loading behavior is exercised against the real aiosqlite
    async session.
    """

    async def test_trigger_agent_resync_with_assigned_voice_live_instance_no_missing_greenlet(
        self, db_session
    ):
        """_trigger_agent_resync must not raise MissingGreenlet when the HCP profile
        has an assigned VoiceLiveInstance.

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
        from app.services.scenario_service import _trigger_agent_resync

        user_id, hcp_id = await _seed_user_and_hcp(db_session)

        vl_instance = VoiceLiveInstance(name="Scenario Resync Test VL", created_by=user_id)
        db_session.add(vl_instance)
        await db_session.flush()
        vl_instance_id = vl_instance.id
        db_session.expunge(vl_instance)

        profile = await db_session.get(HcpProfile, hcp_id)
        profile.voice_live_instance_id = vl_instance_id
        profile.agent_id = "existing-agent"
        await db_session.flush()

        with (
            patch(
                "app.services.agent_sync_service.create_agent",
                new_callable=AsyncMock,
                return_value={"id": "existing-agent", "version": "3"},
            ),
            patch(
                "app.services.agent_sync_service.update_agent",
                new_callable=AsyncMock,
                return_value={"id": "existing-agent", "version": "3"},
            ),
            patch(
                "app.services.agent_sync_service.get_agent_latest_version",
                new_callable=AsyncMock,
                return_value="3",
            ),
        ):
            await _trigger_agent_resync(db_session, hcp_id)

        # sync_agent_for_profile only reaches this assignment after successfully
        # completing create_agent/update_agent + get_agent_latest_version -- if
        # MissingGreenlet had been raised inside resolve_voice_config, execution
        # would never get here and agent_version would remain unset. NOTE: do not
        # db.refresh(profile) here -- _trigger_agent_resync (unlike its
        # knowledge_base_service counterpart) never flushes after syncing (the
        # calling request's db session commits at the request boundary), so a
        # refresh would silently discard this in-memory-only assignment and read
        # back the stale persisted value instead.
        assert profile.agent_version == "3"
