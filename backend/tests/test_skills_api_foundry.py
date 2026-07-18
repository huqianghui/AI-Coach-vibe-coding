"""Tests for Skill API Foundry sync exposure (D-06, D-07, Plan 28-03).

Covers: foundry_* fields on list/detail responses, admin-gated manual retry-sync
route restricted to published skills (MEDIUM-5 regression guard against
resurrecting a deleted Foundry entity on archived skills), portal-url route
with generic fallback, and 403 for non-admin users.
"""

from unittest.mock import AsyncMock, patch

from app.models.user import User
from app.services.auth import create_access_token, get_password_hash
from tests.conftest import TestSessionLocal


async def _create_admin_and_token(username: str = "foundry_api_admin") -> tuple[str, str]:
    """Create an admin user and return (user_id, bearer_token)."""
    async with TestSessionLocal() as session:
        user = User(
            username=username,
            email=f"{username}@test.com",
            hashed_password=get_password_hash("pass"),
            full_name="Foundry API Admin",
            role="admin",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token = create_access_token(data={"sub": user.id})
        return user.id, token


async def _create_user_and_token(username: str = "foundry_api_user") -> tuple[str, str]:
    """Create a regular (non-admin) user and return (user_id, bearer_token)."""
    async with TestSessionLocal() as session:
        user = User(
            username=username,
            email=f"{username}@test.com",
            hashed_password=get_password_hash("pass"),
            full_name="Foundry API Regular User",
            role="user",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token = create_access_token(data={"sub": user.id})
        return user.id, token


async def _create_skill(client, token: str, name: str = "Foundry Skill") -> str:
    response = await client.post(
        "/api/v1/skills",
        json={"name": name, "product": "P"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _set_skill_status(skill_id: str, status: str) -> None:
    """Directly set a skill's status in the DB, bypassing quality gates/lifecycle hooks."""
    from sqlalchemy import select

    from app.models.skill import Skill

    async with TestSessionLocal() as session:
        result = await session.execute(select(Skill).where(Skill.id == skill_id))
        skill = result.scalar_one()
        skill.status = status
        await session.commit()


class TestFoundryFieldsOnResponses:
    """GET /skills and GET /skills/{id} expose foundry_* fields (D-07)."""

    async def test_list_skills_includes_foundry_fields(self, client):
        _, token = await _create_admin_and_token("list_foundry_admin")
        await _create_skill(client, token, "List Foundry Skill")

        response = await client.get(
            "/api/v1/skills",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        item = response.json()["items"][0]
        assert item["foundry_sync_status"] == "none"
        assert item["foundry_skill_name"] == ""
        assert item["foundry_cloud_version"] == ""
        assert item["foundry_sync_error"] == ""

    async def test_get_skill_includes_foundry_fields(self, client):
        _, token = await _create_admin_and_token("get_foundry_admin")
        skill_id = await _create_skill(client, token, "Get Foundry Skill")

        response = await client.get(
            f"/api/v1/skills/{skill_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["foundry_sync_status"] == "none"
        assert "foundry_skill_name" in data
        assert "foundry_cloud_version" in data
        assert "foundry_sync_error" in data


class TestRetryFoundrySync:
    """POST /skills/{id}/foundry-sync -- admin-gated, published-only (D-06, MEDIUM-5)."""

    async def test_retry_sync_on_published_skill_calls_service(self, client):
        _, token = await _create_admin_and_token("retry_foundry_admin")
        skill_id = await _create_skill(client, token, "Published Foundry Skill")
        await _set_skill_status(skill_id, "published")

        async def _fake_sync(db, skill):
            skill.foundry_skill_name = "published-foundry-skill-abcd1234"
            skill.foundry_sync_status = "synced"
            skill.foundry_cloud_version = "1"
            skill.foundry_sync_error = ""

        with patch(
            "app.api.skills.skill_foundry_service.sync_skill_to_foundry",
            new=AsyncMock(side_effect=_fake_sync),
        ) as mock_sync:
            response = await client.post(
                f"/api/v1/skills/{skill_id}/foundry-sync",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["foundry_sync_status"] == "synced"
        assert data["foundry_skill_name"] == "published-foundry-skill-abcd1234"
        mock_sync.assert_awaited_once()

    async def test_retry_sync_rejected_for_draft_skill(self, client):
        _, token = await _create_admin_and_token("retry_draft_admin")
        skill_id = await _create_skill(client, token, "Draft Foundry Skill")

        with patch(
            "app.api.skills.skill_foundry_service.sync_skill_to_foundry",
            new=AsyncMock(),
        ) as mock_sync:
            response = await client.post(
                f"/api/v1/skills/{skill_id}/foundry-sync",
                headers={"Authorization": f"Bearer {token}"},
            )

        # NOTE: this project's bad_request() helper raises ValidationException,
        # which the global exception handler maps to HTTP 422 (not a literal 400) --
        # see app/utils/exceptions.py. This matches every other bad_request()-guarded
        # lifecycle route in this codebase (test_skill_service.py asserts
        # ValidationException throughout for identical guard patterns).
        assert response.status_code == 422
        mock_sync.assert_not_awaited()

    async def test_retry_sync_rejected_for_archived_skill(self, client):
        """MEDIUM-5 regression guard: archived skills must NOT be retryable --
        their Foundry entity was already deleted by the archive lifecycle hook
        (D-03); allowing retry here would silently resurrect it."""
        _, token = await _create_admin_and_token("retry_archived_admin")
        skill_id = await _create_skill(client, token, "Archived Foundry Skill")
        await _set_skill_status(skill_id, "archived")

        with patch(
            "app.api.skills.skill_foundry_service.sync_skill_to_foundry",
            new=AsyncMock(),
        ) as mock_sync:
            response = await client.post(
                f"/api/v1/skills/{skill_id}/foundry-sync",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 422
        mock_sync.assert_not_awaited()

    async def test_retry_sync_non_admin_gets_403(self, client):
        _, admin_token = await _create_admin_and_token("retry_403_admin")
        skill_id = await _create_skill(client, admin_token, "403 Foundry Skill")
        await _set_skill_status(skill_id, "published")

        _, user_token = await _create_user_and_token("retry_403_user")
        response = await client.post(
            f"/api/v1/skills/{skill_id}/foundry-sync",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 403


class TestFoundryPortalUrl:
    """GET /skills/{id}/foundry-portal-url -- admin-gated, graceful fallback (D-07)."""

    async def test_portal_url_returns_deep_link_when_synced(self, client):
        _, token = await _create_admin_and_token("portal_synced_admin")
        skill_id = await _create_skill(client, token, "Synced Portal Skill")
        await _set_skill_status(skill_id, "published")

        with patch(
            "app.api.skills.skill_foundry_service.get_skill_portal_url",
            new=AsyncMock(return_value="https://ai.azure.com/nextgen/r/deadbeef/build/skills/x"),
        ) as mock_url:
            response = await client.get(
                f"/api/v1/skills/{skill_id}/foundry-portal-url",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["url"] == "https://ai.azure.com/nextgen/r/deadbeef/build/skills/x"
        assert "skill_name" in data
        assert "foundry_version" in data
        mock_url.assert_awaited_once()

    async def test_portal_url_falls_back_generically_when_not_synced(self, client):
        """A skill that has never synced must NOT 4xx -- degrades gracefully to the
        generic Foundry URL."""
        _, token = await _create_admin_and_token("portal_unsynced_admin")
        skill_id = await _create_skill(client, token, "Unsynced Portal Skill")

        with patch(
            "app.api.skills.skill_foundry_service.get_skill_portal_url",
            new=AsyncMock(return_value="https://ai.azure.com"),
        ):
            response = await client.get(
                f"/api/v1/skills/{skill_id}/foundry-portal-url",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        assert response.json()["url"] == "https://ai.azure.com"

    async def test_portal_url_non_admin_gets_403(self, client):
        _, admin_token = await _create_admin_and_token("portal_403_admin")
        skill_id = await _create_skill(client, admin_token, "403 Portal Skill")

        _, user_token = await _create_user_and_token("portal_403_user")
        response = await client.get(
            f"/api/v1/skills/{skill_id}/foundry-portal-url",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 403
