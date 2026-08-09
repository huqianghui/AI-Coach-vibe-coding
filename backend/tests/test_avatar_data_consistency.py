"""Tests: Avatar character data consistency between VL Instance and HCP Profile.

D-09/D-10 (Phase 30): HcpProfile no longer carries inline avatar_character/
avatar_style columns -- avatar config lives exclusively on VoiceLiveInstance
and is exposed as a nested `voice_live_instance` object on the scenario API's
`hcp_profile` (see app/api/scenarios.py::HcpProfileBrief). There is no more
"sync to HcpProfile" step; assigning/updating a VL Instance simply changes
what the *next* read resolves to.

Verifies that:
1. assign_to_hcp links the VL Instance so scenario reads resolve its avatar
2. update_instance changes what assigned HCPs' scenario reads resolve to
3. Scenario API resolves avatar from nested hcp_profile.voice_live_instance
4. No VL Instance assigned -> scenario API returns hcp_profile.voice_live_instance
   as null (graceful, not a crash)
"""

from httpx import AsyncClient

from app.models.hcp_profile import HcpProfile
from app.models.scenario import Scenario
from app.models.skill import Skill
from app.models.user import User
from app.models.voice_live_instance import VoiceLiveInstance
from app.services.auth import create_access_token, get_password_hash
from tests.conftest import TestSessionLocal


async def _seed_hcp_with_vl_instance(
    avatar_character: str = "lisa",
    avatar_style: str = "graceful-standing",
) -> tuple[str, str, str, str]:
    """Seed an HCP profile and a VL Instance (NOT yet assigned).

    Returns (hcp_id, vl_instance_id, admin_token, scenario_id).
    """
    async with TestSessionLocal() as db:
        admin = User(
            username="avatar_sync_admin",
            email="avatar_sync_admin@test.com",
            hashed_password=get_password_hash("admin"),
            full_name="Admin",
            role="admin",
        )
        db.add(admin)
        await db.flush()

        hcp = HcpProfile(
            name="Dr. Wang Fang",
            specialty="Oncology",
            created_by=admin.id,
        )
        db.add(hcp)
        await db.flush()

        vl_instance = VoiceLiveInstance(
            name="Lisa Instance",
            avatar_character=avatar_character,
            avatar_style=avatar_style,
            created_by=admin.id,
        )
        db.add(vl_instance)
        await db.flush()

        skill = Skill(
            id="avatar-sync-skill",
            name="Avatar Sync Skill",
            status="published",
            created_by=admin.id,
        )
        db.add(skill)
        await db.flush()

        scenario = Scenario(
            name="Avatar Sync Scenario",
            hcp_profile_id=hcp.id,
            key_messages='["test"]',
            skill_id=skill.id,
            status="active",
            created_by=admin.id,
            rubric_id="test-rubric",
        )
        db.add(scenario)
        await db.flush()
        await db.commit()

        token = create_access_token(data={"sub": admin.id})
        return hcp.id, vl_instance.id, token, scenario.id


class TestAvatarSyncOnAssign:
    """Verify assign_to_hcp links the VL Instance so avatar resolves via it.

    D-09: HcpProfile has no avatar_character/avatar_style column to "sync"
    into anymore -- assignment just links voice_live_instance_id, and the
    scenario API resolves avatar live from the linked VoiceLiveInstance
    (see TestScenarioApiAvatarResolution for the read-side contract). These
    tests assert the link itself takes effect and is visible.
    """

    async def test_assign_links_instance_and_scenario_resolves_its_avatar(
        self, client: AsyncClient
    ):
        """After assigning VL Instance, hcp_profile.voice_live_instance_id is set
        and the scenario API resolves avatar from that instance."""
        hcp_id, vl_id, token, scenario_id = await _seed_hcp_with_vl_instance(
            avatar_character="lisa",
            avatar_style="graceful-standing",
        )

        # Assign VL Instance to HCP
        response = await client.post(
            f"/api/v1/voice-live/instances/{vl_id}/assign",
            headers={"Authorization": f"Bearer {token}"},
            json={"hcp_profile_id": hcp_id},
        )
        assert response.status_code == 200

        # Verify HCP profile now links the VL Instance
        hcp_response = await client.get(
            f"/api/v1/hcp-profiles/{hcp_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert hcp_response.status_code == 200
        assert hcp_response.json()["voice_live_instance_id"] == vl_id

        # Verify scenario API resolves the linked instance's avatar
        scenario_response = await client.get(
            f"/api/v1/scenarios/{scenario_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert scenario_response.status_code == 200
        hcp_data = scenario_response.json()["hcp_profile"]
        assert hcp_data["voice_live_instance"]["avatar_character"] == "lisa"
        assert hcp_data["voice_live_instance"]["avatar_style"] == "graceful-standing"

    async def test_assign_syncs_avatar_customized(self, client: AsyncClient):
        """After assigning VL Instance with avatar_customized=True, the instance
        itself (source of truth) reflects it."""
        hcp_id, vl_id, token, scenario_id = await _seed_hcp_with_vl_instance(
            avatar_character="harry",
            avatar_style="casual",
        )

        # Update VL Instance to have customized=True
        await client.put(
            f"/api/v1/voice-live/instances/{vl_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"avatar_customized": True},
        )

        # Assign VL Instance to HCP
        response = await client.post(
            f"/api/v1/voice-live/instances/{vl_id}/assign",
            headers={"Authorization": f"Bearer {token}"},
            json={"hcp_profile_id": hcp_id},
        )
        assert response.status_code == 200
        assert response.json()["avatar_character"] == "harry"
        assert response.json()["avatar_customized"] is True

        # Scenario API resolves the same instance's avatar
        scenario_response = await client.get(
            f"/api/v1/scenarios/{scenario_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert scenario_response.status_code == 200
        hcp_data = scenario_response.json()["hcp_profile"]
        assert hcp_data["voice_live_instance"]["avatar_character"] == "harry"


class TestAvatarSyncOnUpdate:
    """Verify update_instance changes what assigned HCPs resolve to at read time."""

    async def test_update_instance_avatar_propagates_to_hcp(self, client: AsyncClient):
        """Changing VL Instance avatar_character updates resolution for all assigned HCPs."""
        hcp_id, vl_id, token, scenario_id = await _seed_hcp_with_vl_instance(
            avatar_character="lisa",
            avatar_style="graceful-standing",
        )

        # Assign first
        await client.post(
            f"/api/v1/voice-live/instances/{vl_id}/assign",
            headers={"Authorization": f"Bearer {token}"},
            json={"hcp_profile_id": hcp_id},
        )

        # Now update VL Instance avatar to a different character
        update_resp = await client.put(
            f"/api/v1/voice-live/instances/{vl_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"avatar_character": "meg", "avatar_style": "formal"},
        )
        assert update_resp.status_code == 200

        # Verify scenario API resolution reflects the update
        scenario_response = await client.get(
            f"/api/v1/scenarios/{scenario_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert scenario_response.status_code == 200
        hcp_data = scenario_response.json()["hcp_profile"]
        assert hcp_data["voice_live_instance"]["avatar_character"] == "meg"
        assert hcp_data["voice_live_instance"]["avatar_style"] == "formal"

    async def test_update_instance_non_avatar_field_does_not_change_hcp_avatar(
        self, client: AsyncClient
    ):
        """Updating non-avatar VL Instance fields does NOT change resolved avatar."""
        hcp_id, vl_id, token, scenario_id = await _seed_hcp_with_vl_instance(
            avatar_character="lisa",
            avatar_style="graceful-standing",
        )

        # Assign
        await client.post(
            f"/api/v1/voice-live/instances/{vl_id}/assign",
            headers={"Authorization": f"Bearer {token}"},
            json={"hcp_profile_id": hcp_id},
        )

        # Update non-avatar field (e.g., voice_name)
        await client.put(
            f"/api/v1/voice-live/instances/{vl_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"voice_name": "en-US-JennyNeural"},
        )

        # Resolved avatar should remain "lisa"
        scenario_response = await client.get(
            f"/api/v1/scenarios/{scenario_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert scenario_response.status_code == 200
        hcp_data = scenario_response.json()["hcp_profile"]
        assert hcp_data["voice_live_instance"]["avatar_character"] == "lisa"


class TestScenarioApiAvatarResolution:
    """Verify scenario API returns resolved avatar from VL Instance."""

    async def test_scenario_api_returns_vl_instance_avatar(self, client: AsyncClient):
        """GET /scenarios/{id} returns avatar from VL Instance, not stale HCP field."""
        hcp_id, vl_id, token, scenario_id = await _seed_hcp_with_vl_instance(
            avatar_character="lisa",
            avatar_style="graceful-standing",
        )

        # Assign VL Instance to HCP
        await client.post(
            f"/api/v1/voice-live/instances/{vl_id}/assign",
            headers={"Authorization": f"Bearer {token}"},
            json={"hcp_profile_id": hcp_id},
        )

        # Get scenario — avatar should be from VL Instance
        response = await client.get(
            f"/api/v1/scenarios/{scenario_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["hcp_profile"]["voice_live_instance"]["avatar_character"] == "lisa"
        assert data["hcp_profile"]["voice_live_instance"]["avatar_style"] == "graceful-standing"

    async def test_scenario_list_returns_vl_instance_avatar(self, client: AsyncClient):
        """GET /scenarios returns avatar from VL Instance for each scenario."""
        hcp_id, vl_id, token, _ = await _seed_hcp_with_vl_instance(
            avatar_character="harry",
            avatar_style="business",
        )

        # Assign VL Instance
        await client.post(
            f"/api/v1/voice-live/instances/{vl_id}/assign",
            headers={"Authorization": f"Bearer {token}"},
            json={"hcp_profile_id": hcp_id},
        )

        # List scenarios
        response = await client.get(
            "/api/v1/scenarios",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        item = data["items"][0]
        assert item["hcp_profile"]["voice_live_instance"]["avatar_character"] == "harry"
        assert item["hcp_profile"]["voice_live_instance"]["avatar_style"] == "business"

    async def test_active_scenarios_returns_vl_instance_avatar(self, client: AsyncClient):
        """GET /scenarios/active returns resolved avatar."""
        hcp_id, vl_id, token, _ = await _seed_hcp_with_vl_instance(
            avatar_character="jeff",
            avatar_style="formal",
        )

        # Assign VL Instance
        await client.post(
            f"/api/v1/voice-live/instances/{vl_id}/assign",
            headers={"Authorization": f"Bearer {token}"},
            json={"hcp_profile_id": hcp_id},
        )

        # Active scenarios
        response = await client.get(
            "/api/v1/scenarios/active",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["hcp_profile"]["voice_live_instance"]["avatar_character"] == "jeff"
        assert data[0]["hcp_profile"]["voice_live_instance"]["avatar_style"] == "formal"

    async def test_scenario_without_vl_instance_uses_safe_defaults(self, client: AsyncClient):
        """When no VL Instance assigned, scenario API returns a graceful null, not a crash.

        D-09/D-10 (Phase 30): HcpProfile has no inline avatar_character/avatar_style
        columns to fall back to anymore, and HcpProfileBrief no longer flattens the
        VL Instance relationship -- it exposes it as a nested `voice_live_instance`
        object. When unassigned (D-13: legacy rows are not backfilled), that field
        must resolve to `None` rather than 500ing or fabricating fake defaults.
        """
        _, _, token, scenario_id = await _seed_hcp_with_vl_instance(
            avatar_character="lisa",
            avatar_style="graceful-standing",
        )
        # Do NOT assign VL Instance — graceful null should be used

        response = await client.get(
            f"/api/v1/scenarios/{scenario_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        # No VL Instance assigned -> nested field is null, not fabricated defaults
        assert data["hcp_profile"]["voice_live_instance"] is None
        assert data["hcp_profile"]["voice_live_instance_id"] is None
