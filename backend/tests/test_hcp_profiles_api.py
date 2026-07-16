"""Tests for HCP Profiles API endpoints (admin-only CRUD)."""

from app.models.user import User
from app.services.auth import create_access_token, get_password_hash
from tests.conftest import TestSessionLocal


async def _create_admin_and_token() -> tuple[str, str]:
    """Create an admin user and return (user_id, bearer_token)."""
    async with TestSessionLocal() as session:
        user = User(
            username="admin_hcp",
            email="admin_hcp@test.com",
            hashed_password=get_password_hash("admin123"),
            full_name="Admin HCP",
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
            username="regular_hcp",
            email="regular_hcp@test.com",
            hashed_password=get_password_hash("pass123"),
            full_name="Regular User",
            role="user",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token = create_access_token(data={"sub": user.id})
        return user.id, token


class TestCreateProfileEndpoint:
    """Tests for POST /api/v1/hcp-profiles/."""

    async def test_admin_can_create_profile(self, client):
        user_id, token = await _create_admin_and_token()
        response = await client.post(
            "/api/v1/hcp-profiles",
            json={
                "name": "Dr. API",
                "specialty": "Oncology",
                "created_by": user_id,
                "personality_type": "skeptical",
                "expertise_areas": ["immunotherapy"],
                "objections": ["Cost"],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Dr. API"
        assert data["specialty"] == "Oncology"
        assert data["personality_type"] == "skeptical"
        assert data["expertise_areas"] == ["immunotherapy"]
        assert "id" in data

    async def test_admin_can_create_cautious_profile(self, client):
        """The API accepts the cautious personality exposed by the editor."""
        _, token = await _create_admin_and_token()
        response = await client.post(
            "/api/v1/hcp-profiles",
            json={
                "name": "Dr. Cautious",
                "specialty": "Oncology",
                "personality_type": "cautious",
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 201
        assert response.json()["personality_type"] == "cautious"

    async def test_non_admin_gets_403(self, client):
        user_id, token = await _create_user_and_token()
        response = await client.post(
            "/api/v1/hcp-profiles",
            json={
                "name": "Dr. Nope",
                "specialty": "Onc",
                "created_by": user_id,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403

    async def test_no_auth_returns_401(self, client):
        response = await client.post(
            "/api/v1/hcp-profiles",
            json={"name": "Dr. X", "specialty": "Onc", "created_by": "u1"},
        )
        assert response.status_code == 401


class TestListProfilesEndpoint:
    """Tests for GET /api/v1/hcp-profiles/."""

    async def test_list_returns_paginated_profiles(self, client):
        user_id, token = await _create_admin_and_token()
        # Create two profiles
        for name in ["Dr. A", "Dr. B"]:
            await client.post(
                "/api/v1/hcp-profiles",
                json={"name": name, "specialty": "Onc", "created_by": user_id},
                headers={"Authorization": f"Bearer {token}"},
            )

        response = await client.get(
            "/api/v1/hcp-profiles",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        assert "page" in data
        assert "total_pages" in data

    async def test_search_filter(self, client):
        user_id, token = await _create_admin_and_token()
        await client.post(
            "/api/v1/hcp-profiles",
            json={"name": "Dr. UniqueSearch", "specialty": "Onc", "created_by": user_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        await client.post(
            "/api/v1/hcp-profiles",
            json={"name": "Dr. Other", "specialty": "Card", "created_by": user_id},
            headers={"Authorization": f"Bearer {token}"},
        )

        response = await client.get(
            "/api/v1/hcp-profiles?search=UniqueSearch",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1


class TestGetProfileEndpoint:
    """Tests for GET /api/v1/hcp-profiles/{profile_id}."""

    async def test_get_existing_profile(self, client):
        user_id, token = await _create_admin_and_token()
        create_resp = await client.post(
            "/api/v1/hcp-profiles",
            json={"name": "Dr. Single", "specialty": "Neuro", "created_by": user_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        profile_id = create_resp.json()["id"]

        response = await client.get(
            f"/api/v1/hcp-profiles/{profile_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Dr. Single"

    async def test_get_nonexistent_returns_404(self, client):
        _, token = await _create_admin_and_token()
        response = await client.get(
            "/api/v1/hcp-profiles/nonexistent-id",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404


class TestUpdateProfileEndpoint:
    """Tests for PUT /api/v1/hcp-profiles/{profile_id}."""

    async def test_updates_profile_fields(self, client):
        user_id, token = await _create_admin_and_token()
        create_resp = await client.post(
            "/api/v1/hcp-profiles",
            json={"name": "Dr. Old", "specialty": "Onc", "created_by": user_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        profile_id = create_resp.json()["id"]

        response = await client.put(
            f"/api/v1/hcp-profiles/{profile_id}",
            json={"name": "Dr. Updated", "personality_type": "analytical"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Dr. Updated"
        assert data["personality_type"] == "analytical"

    async def test_updates_profile_to_cautious(self, client):
        """The update schema uses the same personality values as creation."""
        user_id, token = await _create_admin_and_token()
        create_resp = await client.post(
            "/api/v1/hcp-profiles",
            json={"name": "Dr. Careful", "specialty": "Onc", "created_by": user_id},
            headers={"Authorization": f"Bearer {token}"},
        )

        response = await client.put(
            f"/api/v1/hcp-profiles/{create_resp.json()['id']}",
            json={"personality_type": "cautious"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.json()["personality_type"] == "cautious"


class TestDeleteProfileEndpoint:
    """Tests for DELETE /api/v1/hcp-profiles/{profile_id}."""

    async def test_deletes_profile(self, client):
        user_id, token = await _create_admin_and_token()
        create_resp = await client.post(
            "/api/v1/hcp-profiles",
            json={"name": "Dr. Delete", "specialty": "Onc", "created_by": user_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        profile_id = create_resp.json()["id"]

        response = await client.delete(
            f"/api/v1/hcp-profiles/{profile_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 204

        # Verify deleted
        get_resp = await client.get(
            f"/api/v1/hcp-profiles/{profile_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert get_resp.status_code == 404

    async def test_delete_nonexistent_returns_404(self, client):
        _, token = await _create_admin_and_token()
        response = await client.delete(
            "/api/v1/hcp-profiles/nonexistent-id",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404


class TestPreviewInstructionsEndpoint:
    """Tests for POST /api/v1/hcp-profiles/preview-instructions."""

    async def test_preview_instructions_auto_generated(self, client):
        """POST /preview-instructions returns auto-generated instructions when no override."""
        _, token = await _create_admin_and_token()
        response = await client.post(
            "/api/v1/hcp-profiles/preview-instructions",
            json={
                "name": "Dr. Test",
                "specialty": "Oncology",
                "hospital": "Test Hospital",
                "personality_type": "friendly",
                "emotional_state": 30,
                "communication_style": 70,
                "expertise_areas": ["Breast Cancer", "Immunotherapy"],
                "objections": ["Cost concerns"],
                "agent_instructions_override": "",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "instructions" in data
        assert "is_override" in data
        assert data["is_override"] is False
        assert "Dr. Test" in data["instructions"]
        assert "Oncology" in data["instructions"]

    async def test_preview_instructions_with_override(self, client):
        """POST /preview-instructions returns override text when provided."""
        _, token = await _create_admin_and_token()
        override_text = "You are a custom agent with special instructions."
        response = await client.post(
            "/api/v1/hcp-profiles/preview-instructions",
            json={
                "name": "Dr. Override",
                "specialty": "Hematology",
                "agent_instructions_override": override_text,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_override"] is True
        assert data["instructions"] == override_text

    async def test_preview_instructions_unauthorized(self, client):
        """POST /preview-instructions rejects unauthenticated request."""
        response = await client.post(
            "/api/v1/hcp-profiles/preview-instructions",
            json={"name": "Test"},
        )
        assert response.status_code in (401, 403)

    async def test_preview_instructions_non_admin_rejected(self, client):
        """POST /preview-instructions rejects non-admin user."""
        _, token = await _create_user_and_token()
        response = await client.post(
            "/api/v1/hcp-profiles/preview-instructions",
            json={"name": "Test"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403

    async def test_preview_instructions_empty_body_defaults(self, client):
        """POST /preview-instructions works with all-default values (empty body)."""
        _, token = await _create_admin_and_token()
        response = await client.post(
            "/api/v1/hcp-profiles/preview-instructions",
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_override"] is False
        assert isinstance(data["instructions"], str)
        assert len(data["instructions"]) > 0

    async def test_preview_instructions_whitespace_override_not_counted(self, client):
        """Override with only whitespace is treated as empty (is_override=False)."""
        _, token = await _create_admin_and_token()
        response = await client.post(
            "/api/v1/hcp-profiles/preview-instructions",
            json={"agent_instructions_override": "   "},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_override"] is False


class TestToPromptDictOverride:
    """Tests for HcpProfile.to_prompt_dict() including agent_instructions_override."""

    def test_to_prompt_dict_includes_override(self):
        """HcpProfile.to_prompt_dict() includes agent_instructions_override field."""
        from app.models.hcp_profile import HcpProfile

        profile = HcpProfile(
            name="Dr. Prompt",
            specialty="Neurology",
            created_by="test-user",
            expertise_areas="[]",
            objections="[]",
            probe_topics="[]",
            agent_instructions_override="Custom override text",
        )
        prompt_dict = profile.to_prompt_dict()
        assert "agent_instructions_override" in prompt_dict
        assert prompt_dict["agent_instructions_override"] == "Custom override text"

    def test_to_prompt_dict_override_empty_default(self):
        """HcpProfile.to_prompt_dict() returns empty string for default override."""
        from app.models.hcp_profile import HcpProfile

        profile = HcpProfile(
            name="Dr. Default",
            specialty="Cardiology",
            created_by="test-user",
            expertise_areas="[]",
            objections="[]",
            probe_topics="[]",
            agent_instructions_override="",
        )
        prompt_dict = profile.to_prompt_dict()
        assert "agent_instructions_override" in prompt_dict
        assert prompt_dict["agent_instructions_override"] == ""


class TestPreviewInstructionsRouteOrder:
    """Test that /preview-instructions route is reachable (not shadowed by /{profile_id})."""

    async def test_route_not_shadowed(self, client):
        """The /preview-instructions static route should not be matched by /{profile_id}."""
        _, token = await _create_admin_and_token()
        # If route ordering is wrong, "preview-instructions" would be treated as a profile_id
        # and return 404 (no profile with that ID). Correct ordering returns 200.
        response = await client.post(
            "/api/v1/hcp-profiles/preview-instructions",
            json={"name": "Route Test"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200, (
            f"Route shadowed by /{{profile_id}} — got {response.status_code}. "
            "Move /preview-instructions BEFORE /{profile_id} in hcp_profiles.py"
        )
