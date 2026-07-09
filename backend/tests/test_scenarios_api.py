"""Tests for Scenarios API endpoints (admin CRUD + user access to active scenarios)."""

from app.models.skill import Skill, SkillVersion
from app.models.user import User
from app.services.auth import create_access_token, get_password_hash
from tests.conftest import TestSessionLocal


async def _create_admin_and_token() -> tuple[str, str]:
    """Create an admin user and return (user_id, bearer_token)."""
    async with TestSessionLocal() as session:
        user = User(
            username="admin_scn",
            email="admin_scn@test.com",
            hashed_password=get_password_hash("admin123"),
            full_name="Admin Scenarios",
            role="admin",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token = create_access_token(data={"sub": user.id})
        return user.id, token


async def _create_user_and_token() -> tuple[str, str]:
    """Create a regular user and return (user_id, bearer_token)."""
    async with TestSessionLocal() as session:
        user = User(
            username="user_scn",
            email="user_scn@test.com",
            hashed_password=get_password_hash("pass"),
            full_name="Regular Scn",
            role="user",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token = create_access_token(data={"sub": user.id})
        return user.id, token


async def _create_hcp_profile(client, token, user_id) -> str:
    """Create an HCP profile and return its ID."""
    resp = await client.post(
        "/api/v1/hcp-profiles",
        json={"name": "Dr. Scn", "specialty": "Oncology", "created_by": user_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    return resp.json()["id"]


async def _create_skill(user_id: str) -> str:
    """Create a published skill with a published version. Returns skill_id."""
    async with TestSessionLocal() as session:
        skill = Skill(
            name="Test Skill",
            description="A test skill",
            status="published",
            created_by=user_id,
        )
        session.add(skill)
        await session.flush()

        version = SkillVersion(
            skill_id=skill.id,
            version_number=1,
            content="test content",
            is_published=True,
            created_by=user_id,
        )
        session.add(version)
        await session.commit()
        await session.refresh(skill)
        return skill.id


class TestCreateScenarioEndpoint:
    """Tests for POST /api/v1/scenarios/."""

    async def test_admin_creates_scenario(self, client):
        user_id, token = await _create_admin_and_token()
        hcp_id = await _create_hcp_profile(client, token, user_id)
        skill_id = await _create_skill(user_id)

        response = await client.post(
            "/api/v1/scenarios",
            json={
                "name": "Test Scenario",
                "hcp_profile_id": hcp_id,
                "rubric_id": "test-rubric-id",
                "skill_id": skill_id,
                "tags": ["product:Brukinsa", "area:Oncology"],
                "key_messages": ["KM1", "KM2"],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Scenario"
        assert data["tags"] == ["product:Brukinsa", "area:Oncology"]
        assert data["key_messages"] == ["KM1", "KM2"]
        assert data["status"] == "draft"
        assert data["skill_id"] == skill_id
        assert data["rubric_id"] == "test-rubric-id"

    async def test_non_admin_gets_403(self, client):
        admin_id, admin_token = await _create_admin_and_token()
        hcp_id = await _create_hcp_profile(client, admin_token, admin_id)
        skill_id = await _create_skill(admin_id)
        _, user_token = await _create_user_and_token()

        response = await client.post(
            "/api/v1/scenarios",
            json={
                "name": "Nope",
                "hcp_profile_id": hcp_id,
                "rubric_id": "test-rubric-id",
                "skill_id": skill_id,
            },
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 403

    async def test_missing_rubric_id_returns_422(self, client):
        user_id, token = await _create_admin_and_token()
        hcp_id = await _create_hcp_profile(client, token, user_id)
        skill_id = await _create_skill(user_id)

        response = await client.post(
            "/api/v1/scenarios",
            json={
                "name": "No Rubric",
                "hcp_profile_id": hcp_id,
                "skill_id": skill_id,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422

    async def test_missing_skill_id_returns_422(self, client):
        user_id, token = await _create_admin_and_token()
        hcp_id = await _create_hcp_profile(client, token, user_id)

        response = await client.post(
            "/api/v1/scenarios",
            json={
                "name": "No Skill",
                "hcp_profile_id": hcp_id,
                "rubric_id": "test-rubric-id",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422

    async def test_nonexistent_hcp_returns_404(self, client):
        user_id, token = await _create_admin_and_token()
        skill_id = await _create_skill(user_id)
        response = await client.post(
            "/api/v1/scenarios",
            json={
                "name": "Bad HCP",
                "hcp_profile_id": "nonexistent-hcp",
                "rubric_id": "test-rubric-id",
                "skill_id": skill_id,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404


class TestListScenariosEndpoint:
    """Tests for GET /api/v1/scenarios/."""

    async def test_list_returns_paginated(self, client):
        user_id, token = await _create_admin_and_token()
        hcp_id = await _create_hcp_profile(client, token, user_id)
        skill_id = await _create_skill(user_id)

        for name in ["S1", "S2"]:
            await client.post(
                "/api/v1/scenarios",
                json={
                    "name": name,
                    "hcp_profile_id": hcp_id,
                    "rubric_id": "test-rubric-id",
                    "skill_id": skill_id,
                },
                headers={"Authorization": f"Bearer {token}"},
            )

        response = await client.get(
            "/api/v1/scenarios",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    async def test_filter_by_status(self, client):
        user_id, token = await _create_admin_and_token()
        hcp_id = await _create_hcp_profile(client, token, user_id)
        skill_id = await _create_skill(user_id)

        # Create a scenario (default draft)
        await client.post(
            "/api/v1/scenarios",
            json={
                "name": "Draft",
                "hcp_profile_id": hcp_id,
                "rubric_id": "test-rubric-id",
                "skill_id": skill_id,
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        response = await client.get(
            "/api/v1/scenarios?status=draft",
            headers={"Authorization": f"Bearer {token}"},
        )
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "Draft"


class TestListActiveScenariosEndpoint:
    """Tests for GET /api/v1/scenarios/active (user-accessible)."""

    async def test_user_can_list_active_scenarios(self, client):
        admin_id, admin_token = await _create_admin_and_token()
        hcp_id = await _create_hcp_profile(client, admin_token, admin_id)
        skill_id = await _create_skill(admin_id)

        # Create scenario and manually set active via update
        create_resp = await client.post(
            "/api/v1/scenarios",
            json={
                "name": "Active For User",
                "hcp_profile_id": hcp_id,
                "rubric_id": "test-rubric-id",
                "skill_id": skill_id,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        scn_id = create_resp.json()["id"]

        # Manually activate (since status is not in ScenarioCreate anymore)
        from sqlalchemy import select

        from app.models.scenario import Scenario
        from tests.conftest import TestSessionLocal

        async with TestSessionLocal() as session:
            result = await session.execute(select(Scenario).where(Scenario.id == scn_id))
            scn = result.scalar_one()
            scn.status = "active"
            await session.commit()

        # Regular user can access
        _, user_token = await _create_user_and_token()
        response = await client.get(
            "/api/v1/scenarios/active",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1


class TestGetScenarioEndpoint:
    """Tests for GET /api/v1/scenarios/{scenario_id}."""

    async def test_get_by_id(self, client):
        user_id, token = await _create_admin_and_token()
        hcp_id = await _create_hcp_profile(client, token, user_id)
        skill_id = await _create_skill(user_id)

        create_resp = await client.post(
            "/api/v1/scenarios",
            json={
                "name": "Single",
                "hcp_profile_id": hcp_id,
                "rubric_id": "test-rubric-id",
                "skill_id": skill_id,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        scn_id = create_resp.json()["id"]

        response = await client.get(
            f"/api/v1/scenarios/{scn_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Single"
        assert response.json()["tags"] == []


class TestUpdateScenarioEndpoint:
    """Tests for PUT /api/v1/scenarios/{scenario_id}."""

    async def test_updates_scenario(self, client):
        user_id, token = await _create_admin_and_token()
        hcp_id = await _create_hcp_profile(client, token, user_id)
        skill_id = await _create_skill(user_id)

        create_resp = await client.post(
            "/api/v1/scenarios",
            json={
                "name": "Old",
                "hcp_profile_id": hcp_id,
                "rubric_id": "test-rubric-id",
                "skill_id": skill_id,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        scn_id = create_resp.json()["id"]

        response = await client.put(
            f"/api/v1/scenarios/{scn_id}",
            json={"name": "New Name", "tags": ["new-tag"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "New Name"
        assert response.json()["tags"] == ["new-tag"]

    async def test_conference_prompt_version_bumps_on_config_change(self, client):
        user_id, token = await _create_admin_and_token()
        hcp_id = await _create_hcp_profile(client, token, user_id)
        skill_id = await _create_skill(user_id)

        create_resp = await client.post(
            "/api/v1/scenarios",
            json={
                "name": "ConfPrompt",
                "hcp_profile_id": hcp_id,
                "rubric_id": "test-rubric-id",
                "skill_id": skill_id,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        scn_id = create_resp.json()["id"]
        assert create_resp.json()["conference_prompt_version"] == 1

        # Changing the config bumps the version.
        first = await client.put(
            f"/api/v1/scenarios/{scn_id}",
            json={"conference_prompt_config": {"audience_prompt_template": "You are {hcp_name}."}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert first.status_code == 200
        assert first.json()["conference_prompt_version"] == 2

        # Re-sending the identical config does not bump the version.
        same = await client.put(
            f"/api/v1/scenarios/{scn_id}",
            json={"conference_prompt_config": {"audience_prompt_template": "You are {hcp_name}."}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert same.status_code == 200
        assert same.json()["conference_prompt_version"] == 2

        # A further change bumps again.
        third = await client.put(
            f"/api/v1/scenarios/{scn_id}",
            json={"conference_prompt_config": {"audience_prompt_template": "Updated {hcp_name}."}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert third.status_code == 200
        assert third.json()["conference_prompt_version"] == 3

    """Tests for DELETE /api/v1/scenarios/{scenario_id}."""

    async def test_deletes_scenario(self, client):
        user_id, token = await _create_admin_and_token()
        hcp_id = await _create_hcp_profile(client, token, user_id)
        skill_id = await _create_skill(user_id)

        create_resp = await client.post(
            "/api/v1/scenarios",
            json={
                "name": "Del",
                "hcp_profile_id": hcp_id,
                "rubric_id": "test-rubric-id",
                "skill_id": skill_id,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        scn_id = create_resp.json()["id"]

        response = await client.delete(
            f"/api/v1/scenarios/{scn_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 204


class TestGetScenarioSkillEndpoint:
    """Tests for GET /api/v1/scenarios/{scenario_id}/skill."""

    async def test_returns_skill_info(self, client):
        user_id, token = await _create_admin_and_token()
        hcp_id = await _create_hcp_profile(client, token, user_id)
        skill_id = await _create_skill(user_id)

        create_resp = await client.post(
            "/api/v1/scenarios",
            json={
                "name": "With Skill",
                "hcp_profile_id": hcp_id,
                "rubric_id": "test-rubric-id",
                "skill_id": skill_id,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        scn_id = create_resp.json()["id"]

        response = await client.get(
            f"/api/v1/scenarios/{scn_id}/skill",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == skill_id
        assert data["name"] == "Test Skill"
        assert data["status"] == "published"
        assert data["version_number"] == 1


class TestTransitionEndpoint:
    """Tests for POST /api/v1/scenarios/{scenario_id}/transition."""

    async def test_transition_draft_to_active(self, client):
        user_id, token = await _create_admin_and_token()
        hcp_id = await _create_hcp_profile(client, token, user_id)
        skill_id = await _create_skill(user_id)

        create_resp = await client.post(
            "/api/v1/scenarios",
            json={
                "name": "Trans",
                "hcp_profile_id": hcp_id,
                "rubric_id": "test-rubric-id",
                "skill_id": skill_id,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        scn_id = create_resp.json()["id"]

        response = await client.post(
            f"/api/v1/scenarios/{scn_id}/transition",
            json={"status": "active"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "active"

    async def test_invalid_transition_returns_400(self, client):
        user_id, token = await _create_admin_and_token()
        hcp_id = await _create_hcp_profile(client, token, user_id)
        skill_id = await _create_skill(user_id)

        create_resp = await client.post(
            "/api/v1/scenarios",
            json={
                "name": "Trans2",
                "hcp_profile_id": hcp_id,
                "rubric_id": "test-rubric-id",
                "skill_id": skill_id,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        scn_id = create_resp.json()["id"]

        # draft -> archived is invalid
        response = await client.post(
            f"/api/v1/scenarios/{scn_id}/transition",
            json={"status": "archived"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422

    async def test_update_archived_returns_422(self, client):
        user_id, token = await _create_admin_and_token()
        hcp_id = await _create_hcp_profile(client, token, user_id)
        skill_id = await _create_skill(user_id)

        create_resp = await client.post(
            "/api/v1/scenarios",
            json={
                "name": "ArchGuard",
                "hcp_profile_id": hcp_id,
                "rubric_id": "test-rubric-id",
                "skill_id": skill_id,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        scn_id = create_resp.json()["id"]

        # Transition to active then archived
        await client.post(
            f"/api/v1/scenarios/{scn_id}/transition",
            json={"status": "active"},
            headers={"Authorization": f"Bearer {token}"},
        )
        await client.post(
            f"/api/v1/scenarios/{scn_id}/transition",
            json={"status": "archived"},
            headers={"Authorization": f"Bearer {token}"},
        )

        # Try to update - should fail
        response = await client.put(
            f"/api/v1/scenarios/{scn_id}",
            json={"name": "Should Fail"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422
        assert "archived" in response.json()["message"].lower()


class TestCloneScenarioEndpoint:
    """Tests for POST /api/v1/scenarios/{scenario_id}/clone."""

    async def test_clones_scenario(self, client):
        user_id, token = await _create_admin_and_token()
        hcp_id = await _create_hcp_profile(client, token, user_id)
        skill_id = await _create_skill(user_id)

        create_resp = await client.post(
            "/api/v1/scenarios",
            json={
                "name": "Original",
                "hcp_profile_id": hcp_id,
                "rubric_id": "test-rubric-id",
                "skill_id": skill_id,
                "key_messages": ["KM1"],
                "tags": ["product:Drug"],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        scn_id = create_resp.json()["id"]

        response = await client.post(
            f"/api/v1/scenarios/{scn_id}/clone",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Original (Copy)"
        assert data["status"] == "draft"
        assert data["id"] != scn_id
        assert data["tags"] == ["product:Drug"]
        assert data["skill_id"] == skill_id


class TestActiveScenarioProtection:
    """Tests that active scenarios block changes to critical fields."""

    async def _make_active_scenario(self, client, token, user_id):
        """Helper: create scenario and transition to active."""
        hcp_id = await _create_hcp_profile(client, token, user_id)
        skill_id = await _create_skill(user_id)
        create_resp = await client.post(
            "/api/v1/scenarios",
            json={
                "name": "Protected Active",
                "hcp_profile_id": hcp_id,
                "rubric_id": "test-rubric-id",
                "skill_id": skill_id,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        scn_id = create_resp.json()["id"]
        await client.post(
            f"/api/v1/scenarios/{scn_id}/transition",
            json={"status": "active"},
            headers={"Authorization": f"Bearer {token}"},
        )
        return scn_id, hcp_id, skill_id

    async def test_active_blocks_hcp_change(self, client):
        """Cannot change hcp_profile_id on an active scenario."""
        user_id, token = await _create_admin_and_token()
        scn_id, _, _ = await self._make_active_scenario(client, token, user_id)

        response = await client.put(
            f"/api/v1/scenarios/{scn_id}",
            json={"hcp_profile_id": "some-other-hcp"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422
        assert "hcp_profile_id" in response.json()["message"]

    async def test_active_blocks_skill_change(self, client):
        """Cannot change skill_id on an active scenario."""
        user_id, token = await _create_admin_and_token()
        scn_id, _, _ = await self._make_active_scenario(client, token, user_id)

        response = await client.put(
            f"/api/v1/scenarios/{scn_id}",
            json={"skill_id": "some-other-skill"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422
        assert "skill_id" in response.json()["message"]

    async def test_active_blocks_key_messages_change(self, client):
        """Cannot change key_messages on an active scenario."""
        user_id, token = await _create_admin_and_token()
        scn_id, _, _ = await self._make_active_scenario(client, token, user_id)

        response = await client.put(
            f"/api/v1/scenarios/{scn_id}",
            json={"key_messages": ["new msg"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422
        assert "key_messages" in response.json()["message"]

    async def test_active_allows_name_change(self, client):
        """Can still change name/description/tags on an active scenario."""
        user_id, token = await _create_admin_and_token()
        scn_id, _, _ = await self._make_active_scenario(client, token, user_id)

        response = await client.put(
            f"/api/v1/scenarios/{scn_id}",
            json={"name": "Renamed Active", "description": "Updated", "tags": ["new-tag"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Renamed Active"

    async def test_draft_allows_all_changes(self, client):
        """Draft scenarios allow changing any field."""
        user_id, token = await _create_admin_and_token()
        hcp_id = await _create_hcp_profile(client, token, user_id)
        skill_id = await _create_skill(user_id)
        create_resp = await client.post(
            "/api/v1/scenarios",
            json={
                "name": "Draft Editable",
                "hcp_profile_id": hcp_id,
                "rubric_id": "test-rubric-id",
                "skill_id": skill_id,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        scn_id = create_resp.json()["id"]

        response = await client.put(
            f"/api/v1/scenarios/{scn_id}",
            json={"key_messages": ["new msg"], "skill_id": skill_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200


class TestHcpProfileInResponse:
    """Tests that hcp_profile is included in all scenario API responses."""

    async def test_create_returns_hcp_profile(self, client):
        """POST /scenarios returns nested hcp_profile with name."""
        user_id, token = await _create_admin_and_token()
        hcp_id = await _create_hcp_profile(client, token, user_id)
        skill_id = await _create_skill(user_id)

        response = await client.post(
            "/api/v1/scenarios",
            json={
                "name": "HCP Test Create",
                "hcp_profile_id": hcp_id,
                "rubric_id": "test-rubric-id",
                "skill_id": skill_id,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["hcp_profile"] is not None
        assert data["hcp_profile"]["id"] == hcp_id
        assert data["hcp_profile"]["name"] == "Dr. Scn"

    async def test_list_returns_hcp_profile(self, client):
        """GET /scenarios list includes hcp_profile in each item."""
        user_id, token = await _create_admin_and_token()
        hcp_id = await _create_hcp_profile(client, token, user_id)
        skill_id = await _create_skill(user_id)

        await client.post(
            "/api/v1/scenarios",
            json={
                "name": "HCP Test List",
                "hcp_profile_id": hcp_id,
                "rubric_id": "test-rubric-id",
                "skill_id": skill_id,
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        response = await client.get(
            "/api/v1/scenarios",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) >= 1
        item = next(i for i in items if i["name"] == "HCP Test List")
        assert item["hcp_profile"] is not None
        assert item["hcp_profile"]["id"] == hcp_id
        assert item["hcp_profile"]["name"] == "Dr. Scn"

    async def test_get_by_id_returns_hcp_profile(self, client):
        """GET /scenarios/{id} includes hcp_profile."""
        user_id, token = await _create_admin_and_token()
        hcp_id = await _create_hcp_profile(client, token, user_id)
        skill_id = await _create_skill(user_id)

        create_resp = await client.post(
            "/api/v1/scenarios",
            json={
                "name": "HCP Test Get",
                "hcp_profile_id": hcp_id,
                "rubric_id": "test-rubric-id",
                "skill_id": skill_id,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        scn_id = create_resp.json()["id"]

        response = await client.get(
            f"/api/v1/scenarios/{scn_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["hcp_profile"] is not None
        assert data["hcp_profile"]["name"] == "Dr. Scn"

    async def test_update_returns_hcp_profile(self, client):
        """PUT /scenarios/{id} returns hcp_profile after update."""
        user_id, token = await _create_admin_and_token()
        hcp_id = await _create_hcp_profile(client, token, user_id)
        skill_id = await _create_skill(user_id)

        create_resp = await client.post(
            "/api/v1/scenarios",
            json={
                "name": "HCP Test Update",
                "hcp_profile_id": hcp_id,
                "rubric_id": "test-rubric-id",
                "skill_id": skill_id,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        scn_id = create_resp.json()["id"]

        response = await client.put(
            f"/api/v1/scenarios/{scn_id}",
            json={"name": "Updated Name"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["hcp_profile"] is not None
        assert data["hcp_profile"]["id"] == hcp_id

    async def test_clone_returns_hcp_profile(self, client):
        """POST /scenarios/{id}/clone returns hcp_profile on cloned scenario."""
        user_id, token = await _create_admin_and_token()
        hcp_id = await _create_hcp_profile(client, token, user_id)
        skill_id = await _create_skill(user_id)

        create_resp = await client.post(
            "/api/v1/scenarios",
            json={
                "name": "HCP Test Clone",
                "hcp_profile_id": hcp_id,
                "rubric_id": "test-rubric-id",
                "skill_id": skill_id,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        scn_id = create_resp.json()["id"]

        response = await client.post(
            f"/api/v1/scenarios/{scn_id}/clone",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["hcp_profile"] is not None
        assert data["hcp_profile"]["id"] == hcp_id
        assert data["hcp_profile"]["name"] == "Dr. Scn"

    async def test_transition_returns_hcp_profile(self, client):
        """POST /scenarios/{id}/transition returns hcp_profile."""
        user_id, token = await _create_admin_and_token()
        hcp_id = await _create_hcp_profile(client, token, user_id)
        skill_id = await _create_skill(user_id)

        create_resp = await client.post(
            "/api/v1/scenarios",
            json={
                "name": "HCP Test Transition",
                "hcp_profile_id": hcp_id,
                "rubric_id": "test-rubric-id",
                "skill_id": skill_id,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        scn_id = create_resp.json()["id"]

        response = await client.post(
            f"/api/v1/scenarios/{scn_id}/transition",
            json={"status": "active"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["hcp_profile"] is not None
        assert data["hcp_profile"]["id"] == hcp_id
