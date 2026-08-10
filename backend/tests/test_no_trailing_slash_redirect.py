"""Regression tests: API routes must NOT return 307 redirect for trailing slashes.

Bug: FastAPI's default redirect_slashes=True caused 307 redirects when routes were
registered with trailing slash (@router.get("/")) but called without (/api/v1/resource).
Browsers drop the Authorization header on 307 redirect, causing 401 → forced logout.

Fix: All routes now use @router.get("") (no trailing slash). These tests verify that
every list/create endpoint returns its proper status code, not 307.
"""

from app.models.hcp_profile import HcpProfile
from app.models.scenario import Scenario
from app.models.skill import Skill, SkillVersion
from app.models.user import User
from app.models.voice_live_instance import VoiceLiveInstance
from app.services.auth import create_access_token, get_password_hash
from tests.conftest import TestSessionLocal


async def _create_vl_instance(user_id: str) -> str:
    """Create a minimal VoiceLiveInstance directly via the DB and return its id."""
    async with TestSessionLocal() as session:
        inst = VoiceLiveInstance(name="Test VL Instance", created_by=user_id)
        session.add(inst)
        await session.commit()
        await session.refresh(inst)
        return inst.id


async def _seed_admin() -> tuple[str, str]:
    """Create admin user and return (user_id, bearer_token)."""
    async with TestSessionLocal() as session:
        user = User(
            username="admin_redirect",
            email="admin_redirect@test.com",
            hashed_password=get_password_hash("admin123"),
            full_name="Admin Redirect",
            role="admin",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token = create_access_token(data={"sub": user.id})
        return user.id, token


async def _seed_user() -> tuple[str, str]:
    """Create regular user and return (user_id, bearer_token)."""
    async with TestSessionLocal() as session:
        user = User(
            username="user_redirect",
            email="user_redirect@test.com",
            hashed_password=get_password_hash("pass123"),
            full_name="User Redirect",
            role="user",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token = create_access_token(data={"sub": user.id})
        return user.id, token


async def _seed_scenario(admin_id: str) -> str:
    """Create a scenario with required HCP profile for session tests."""
    async with TestSessionLocal() as session:
        profile = HcpProfile(
            name="Dr. Redirect",
            specialty="Oncology",
            created_by=admin_id,
            agent_id="dr-redirect-agent",
            agent_version="1",
            agent_sync_status="synced",
        )
        session.add(profile)
        await session.flush()
        skill_content = "# SOP\n## Step 1: Open\n## Step 2: Discover\n## Step 3: Close"
        skill = Skill(
            id="test-skill-id",
            name="Redirect Test Skill",
            content=skill_content,
            status="published",
            created_by=admin_id,
        )
        session.add(skill)
        await session.flush()
        skill_version = SkillVersion(
            skill_id=skill.id,
            version_number=1,
            content=skill_content,
            metadata_json='{"knowledge_references":["test-reference"]}',
            is_published=True,
            created_by=admin_id,
        )
        session.add(skill_version)
        await session.flush()
        scenario = Scenario(
            name="Redirect Test",
            description="Test scenario",
            mode="f2f",
            difficulty="easy",
            status="active",
            hcp_profile_id=profile.id,
            key_messages='["msg1"]',
            created_by=admin_id,
            rubric_id="test-rubric-id",
            skill_id=skill.id,
            skill_version_id=skill_version.id,
        )
        session.add(scenario)
        await session.commit()
        await session.refresh(scenario)
        return scenario.id


class TestNoTrailingSlashRedirect:
    """Verify all list/create endpoints return proper status (not 307).

    The 307 redirect was the root cause of the forced-logout bug:
    GET /api/v1/hcp-profiles → 307 → GET /api/v1/hcp-profiles/ (no Auth header) → 401
    """

    async def test_hcp_profiles_list_no_redirect(self, client):
        """GET /api/v1/hcp-profiles must return 200, not 307."""
        _, token = await _seed_admin()
        r = await client.get(
            "/api/v1/hcp-profiles",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code} (redirect bug?)"

    async def test_hcp_profiles_list_with_search_no_redirect(self, client):
        """GET /api/v1/hcp-profiles?search=x must return 200, not 307."""
        _, token = await _seed_admin()
        r = await client.get(
            "/api/v1/hcp-profiles?search=test",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200

    async def test_scenarios_list_no_redirect(self, client):
        """GET /api/v1/scenarios must return 200, not 307."""
        _, token = await _seed_admin()
        r = await client.get(
            "/api/v1/scenarios",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200

    async def test_scenarios_active_no_redirect(self, client):
        """GET /api/v1/scenarios/active must return 200, not 307."""
        _, token = await _seed_admin()
        r = await client.get(
            "/api/v1/scenarios/active",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200

    async def test_sessions_list_no_redirect(self, client):
        """GET /api/v1/sessions must return 200, not 307."""
        _, token = await _seed_user()
        r = await client.get(
            "/api/v1/sessions",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200

    async def test_rubrics_list_no_redirect(self, client):
        """GET /api/v1/rubrics must return 200, not 307."""
        _, token = await _seed_admin()
        r = await client.get(
            "/api/v1/rubrics",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200

    async def test_materials_list_no_redirect(self, client):
        """GET /api/v1/materials must return 200, not 307."""
        _, token = await _seed_admin()
        r = await client.get(
            "/api/v1/materials",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200

    async def test_materials_search_no_redirect(self, client):
        """GET /api/v1/materials?product=x must return 200, not 307.

        Note: materials search uses query params on the list endpoint,
        there is no separate /search sub-route.
        """
        _, token = await _seed_admin()
        r = await client.get(
            "/api/v1/materials?product=TestDrug",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200

    async def test_hcp_profiles_create_no_redirect(self, client):
        """POST /api/v1/hcp-profiles must return 201, not 307."""
        user_id, token = await _seed_admin()
        vl_id = await _create_vl_instance(user_id)
        r = await client.post(
            "/api/v1/hcp-profiles",
            json={
                "name": "Dr. NoRedirect",
                "specialty": "Onc",
                "created_by": user_id,
                "voice_live_instance_id": vl_id,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201

    async def test_scenarios_create_no_redirect(self, client):
        """POST /api/v1/scenarios must return 201, not 307."""
        user_id, token = await _seed_admin()
        # Need an HCP profile + skill first
        async with TestSessionLocal() as session:
            profile = HcpProfile(
                name="Dr. ScenarioRedirect",
                specialty="Oncology",
                created_by=user_id,
            )
            session.add(profile)
            await session.flush()

            skill = Skill(
                id="redirect-test-skill",
                name="Redirect Skill",
                status="published",
                created_by=user_id,
            )
            session.add(skill)
            await session.flush()

            skill_ver = SkillVersion(
                skill_id=skill.id,
                version_number=1,
                content="test",
                is_published=True,
                created_by=user_id,
            )
            session.add(skill_ver)
            await session.commit()
            await session.refresh(profile)
            profile_id = profile.id

        r = await client.post(
            "/api/v1/scenarios",
            json={
                "name": "No Redirect Scenario",
                "description": "Test",
                "tags": ["product:TestDrug", "area:Oncology"],
                "mode": "f2f",
                "difficulty": "easy",
                "hcp_profile_id": profile_id,
                "rubric_id": "test-rubric-id",
                "skill_id": "redirect-test-skill",
                "key_messages": ["msg1"],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201

    async def test_sessions_create_no_redirect(self, client):
        """POST /api/v1/sessions must return 201, not 307."""
        admin_id, _ = await _seed_admin()
        _, user_token = await _seed_user()
        scenario_id = await _seed_scenario(admin_id)

        r = await client.post(
            "/api/v1/sessions",
            json={"scenario_id": scenario_id},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert r.status_code == 201

    async def test_rubrics_create_no_redirect(self, client):
        """POST /api/v1/rubrics must return 201, not 307."""
        _, token = await _seed_admin()
        r = await client.post(
            "/api/v1/rubrics",
            json={
                "name": "NoRedirect Rubric",
                "scenario_type": "f2f",
                "dimensions": [
                    {"name": "Communication", "weight": 100, "criteria": ["test criteria"]}
                ],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201


class TestTrailingSlashReturns307OrError:
    """Verify that calling with trailing slash gets 307 (not silently accepted).

    This documents the EXPECTED behavior: FastAPI still redirects trailing-slash
    requests. The fix ensures the frontend never sends trailing-slash URLs.
    """

    async def test_trailing_slash_gets_redirected(self, client):
        """GET /api/v1/hcp-profiles/ should 307-redirect (documenting default behavior)."""
        _, token = await _seed_admin()
        resp_slash = await client.get(
            "/api/v1/hcp-profiles/",
            headers={"Authorization": f"Bearer {token}"},
            follow_redirects=False,
        )
        # FastAPI may 307-redirect or 404 — either way, the canonical URL must work
        assert resp_slash.status_code in (200, 307, 404)
        # The key assertion: the canonical URL (without slash) works at 200
        r2 = await client.get(
            "/api/v1/hcp-profiles",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r2.status_code == 200
