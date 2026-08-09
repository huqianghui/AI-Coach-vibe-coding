"""Regression tests: ScenarioOut includes nested HCP voice_live_instance data.

Ensures hcp_profile.voice_live_instance (nested object per D-10/Phase 29 pattern)
is returned in scenario API responses so the frontend can render the digital
human static preview immediately, and that HCPs with no VL Instance assigned
still serialize without error (D-13: unbound legacy rows are not backfilled).
"""

from httpx import AsyncClient

from app.models.hcp_profile import HcpProfile
from app.models.scenario import Scenario
from app.models.skill import Skill
from app.models.user import User
from app.models.voice_live_instance import VoiceLiveInstance
from app.services.auth import create_access_token, get_password_hash
from tests.conftest import TestSessionLocal


async def _seed_scenario_with_avatar(
    avatar_character: str = "lisa", avatar_style: str = "graceful-standing"
) -> tuple[str, str]:
    """Create scenario with HCP profile that has avatar fields set.

    Returns (scenario_id, user_token).
    """
    async with TestSessionLocal() as db:
        admin = User(
            username="avatar_admin",
            email="avatar_admin@test.com",
            hashed_password=get_password_hash("admin"),
            full_name="Admin",
            role="admin",
        )
        db.add(admin)
        await db.flush()

        instance = VoiceLiveInstance(
            name="Avatar Test Instance",
            enabled=True,
            avatar_enabled=True,
            avatar_character=avatar_character,
            avatar_style=avatar_style,
            created_by=admin.id,
        )
        db.add(instance)
        await db.flush()

        hcp = HcpProfile(
            name="Dr. Avatar Test",
            specialty="Cardiology",
            voice_live_instance_id=instance.id,
            created_by=admin.id,
        )
        db.add(hcp)
        await db.flush()

        skill = Skill(
            id="avatar-skill-id",
            name="Avatar Skill",
            status="published",
            created_by=admin.id,
        )
        db.add(skill)
        await db.flush()

        scenario = Scenario(
            name="Avatar Scenario",
            hcp_profile_id=hcp.id,
            key_messages='["Key message"]',
            skill_id=skill.id,
            status="active",
            created_by=admin.id,
            rubric_id="test-rubric",
        )
        db.add(scenario)
        await db.flush()
        await db.commit()

        token = create_access_token(data={"sub": admin.id})
        return scenario.id, token


class TestScenarioAvatarFields:
    """Verify scenario API responses expose nested hcp_profile.voice_live_instance."""

    async def test_get_scenario_includes_avatar_fields(self, client: AsyncClient):
        """GET /scenarios/{id} response includes nested hcp_profile.voice_live_instance."""
        scenario_id, token = await _seed_scenario_with_avatar("lisa", "graceful-standing")

        response = await client.get(
            f"/api/v1/scenarios/{scenario_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["hcp_profile"] is not None
        assert data["hcp_profile"]["voice_live_instance"] is not None
        assert data["hcp_profile"]["voice_live_instance"]["avatar_character"] == "lisa"
        assert data["hcp_profile"]["voice_live_instance"]["avatar_style"] == "graceful-standing"
        assert data["hcp_profile"]["voice_live_instance"]["enabled"] is True
        assert data["hcp_profile"]["voice_live_instance"]["avatar_enabled"] is True
        assert data["hcp_profile"]["name"] == "Dr. Avatar Test"
        assert "avatar_url" in data["hcp_profile"]
        assert "personality_type" in data["hcp_profile"]

    async def test_list_scenarios_includes_avatar_fields(self, client: AsyncClient):
        """GET /scenarios response includes nested voice_live_instance for each item."""
        _, token = await _seed_scenario_with_avatar("harry", "casual")

        response = await client.get(
            "/api/v1/scenarios",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        item = data["items"][0]
        assert item["hcp_profile"] is not None
        assert item["hcp_profile"]["voice_live_instance"] is not None
        assert item["hcp_profile"]["voice_live_instance"]["avatar_character"] == "harry"
        assert item["hcp_profile"]["voice_live_instance"]["avatar_style"] == "casual"

    async def test_active_scenarios_includes_avatar_fields(self, client: AsyncClient):
        """GET /scenarios/active response includes nested voice_live_instance."""
        _, token = await _seed_scenario_with_avatar("lori", "casual")

        response = await client.get(
            "/api/v1/scenarios/active",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["hcp_profile"]["voice_live_instance"]["avatar_character"] == "lori"

    async def test_scenario_resolves_voice_live_instance_avatar_enabled(self, client: AsyncClient):
        """Scenario HCP summary exposes resolved Voice Live Instance capabilities."""
        async with TestSessionLocal() as db:
            admin = User(
                username="vl_instance_admin",
                email="vl_instance_admin@test.com",
                hashed_password=get_password_hash("admin"),
                full_name="Admin",
                role="admin",
            )
            db.add(admin)
            await db.flush()

            instance = VoiceLiveInstance(
                name="Voice only",
                enabled=True,
                avatar_enabled=False,
                avatar_character="lisa",
                avatar_style="casual-sitting",
                created_by=admin.id,
            )
            db.add(instance)
            await db.flush()

            hcp = HcpProfile(
                name="Dr. Voice Only",
                specialty="Oncology",
                voice_live_instance_id=instance.id,
                created_by=admin.id,
            )
            db.add(hcp)
            await db.flush()

            skill = Skill(
                id="vl-instance-skill-id",
                name="VL Instance Skill",
                status="published",
                created_by=admin.id,
            )
            db.add(skill)
            await db.flush()

            scenario = Scenario(
                name="VL Instance Scenario",
                hcp_profile_id=hcp.id,
                key_messages='["Key message"]',
                skill_id=skill.id,
                status="active",
                created_by=admin.id,
                rubric_id="test-rubric",
            )
            db.add(scenario)
            await db.flush()
            await db.commit()

            token = create_access_token(data={"sub": admin.id})

        response = await client.get(
            f"/api/v1/scenarios/{scenario.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["hcp_profile"]["voice_live_instance"]["avatar_character"] == "lisa"
        assert data["hcp_profile"]["voice_live_instance"]["avatar_style"] == "casual-sitting"
        assert data["hcp_profile"]["voice_live_instance"]["enabled"] is True
        assert data["hcp_profile"]["voice_live_instance"]["avatar_enabled"] is False

    async def test_scenario_with_unbound_hcp_returns_null_voice_live_instance(
        self, client: AsyncClient
    ):
        """HCP with no VL Instance assigned (legacy/unbound row, D-13) serializes with null.

        GET /scenarios/{id} must return 200 with hcp_profile.voice_live_instance == null,
        not a 500 error, when voice_live_instance_id is None.
        """
        async with TestSessionLocal() as db:
            admin = User(
                username="unbound_admin",
                email="unbound_admin@test.com",
                hashed_password=get_password_hash("admin"),
                full_name="Admin",
                role="admin",
            )
            db.add(admin)
            await db.flush()

            hcp = HcpProfile(
                name="Dr. Unbound",
                specialty="Neurology",
                voice_live_instance_id=None,
                created_by=admin.id,
            )
            db.add(hcp)
            await db.flush()

            skill = Skill(
                id="unbound-skill-id",
                name="Unbound Skill",
                status="published",
                created_by=admin.id,
            )
            db.add(skill)
            await db.flush()

            scenario = Scenario(
                name="Unbound Scenario",
                hcp_profile_id=hcp.id,
                key_messages='["Key message"]',
                skill_id=skill.id,
                status="active",
                created_by=admin.id,
                rubric_id="test-rubric",
            )
            db.add(scenario)
            await db.flush()
            await db.commit()

            token = create_access_token(data={"sub": admin.id})

        response = await client.get(
            f"/api/v1/scenarios/{scenario.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["hcp_profile"]["voice_live_instance"] is None
        assert data["hcp_profile"]["voice_live_instance_id"] is None
        assert data["hcp_profile"]["name"] == "Dr. Unbound"
