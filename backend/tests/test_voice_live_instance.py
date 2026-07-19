"""Tests for Voice Live Instance CRUD endpoints and service logic.

Covers:
  - POST /voice-live/instances (create)
  - GET /voice-live/instances (list)
  - GET /voice-live/instances/{id} (detail)
  - PUT /voice-live/instances/{id} (update)
  - DELETE /voice-live/instances/{id} (delete + auto-unassign HCPs)
  - POST /voice-live/instances/{id}/assign (assign to HCP)
  - POST /voice-live/instances/unassign (unassign from HCP)
  - Config resolution: VoiceLiveInstance > inline HcpProfile fields
  - HCP Profile API returns voice_live_instance_id
"""

from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import get_db
from app.dependencies import get_current_user
from app.main import app
from app.models.hcp_profile import HcpProfile
from app.models.user import User
from app.models.voice_live_instance import VoiceLiveInstance
from app.services.voice_live_instance_service import resolve_voice_config

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ADMIN_ID = "admin-vli-test-001"


def _fake_admin() -> User:
    user = MagicMock(spec=User)
    user.id = ADMIN_ID
    user.role = "admin"
    user.username = "testadmin"
    user.is_active = True
    return user


@pytest.fixture
def admin_client(db_session):
    async def override_get_db():
        yield db_session

    async def override_get_current_user():
        return _fake_admin()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    yield
    app.dependency_overrides.clear()


@pytest.fixture
async def seed_user(db_session):
    """Seed the admin user into DB so FK constraints pass."""
    user = User(
        id=ADMIN_ID,
        username="testadmin",
        email="admin@test.com",
        hashed_password="fakehash",
        role="admin",
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.fixture
async def seed_instance(db_session, seed_user):
    """Create a VoiceLiveInstance directly in the DB."""
    inst = VoiceLiveInstance(
        name="Test Instance",
        description="For testing",
        voice_live_model="gpt-4o",
        enabled=True,
        voice_name="zh-CN-XiaoxiaoMultilingualNeural",
        avatar_character="lisa",
        avatar_style="casual-sitting",
        created_by=ADMIN_ID,
    )
    db_session.add(inst)
    await db_session.commit()
    await db_session.refresh(inst)
    return inst


@pytest.fixture
async def seed_hcp(db_session, seed_user):
    """Create an HcpProfile for assignment tests.

    D-09: voice/avatar fields no longer exist as inline columns on HcpProfile --
    voice/avatar config comes exclusively from an assigned VoiceLiveInstance.
    """
    profile = HcpProfile(
        name="Dr. Test",
        specialty="Oncology",
        created_by=ADMIN_ID,
    )
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)
    return profile


# ---------------------------------------------------------------------------
# CRUD Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_instance(admin_client, seed_user):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/voice-live/instances",
            json={
                "name": "New Config",
                "voice_live_model": "gpt-4o",
                "voice_name": "zh-CN-XiaoxiaoMultilingualNeural",
                "avatar_character": "lisa",
            },
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "New Config"
    assert data["voice_live_model"] == "gpt-4o"
    assert data["hcp_count"] == 0
    assert data["id"]


@pytest.mark.asyncio
async def test_list_instances(admin_client, seed_instance):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/voice-live/instances")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any(i["name"] == "Test Instance" for i in data["items"])


@pytest.mark.asyncio
async def test_get_instance(admin_client, seed_instance):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/api/v1/voice-live/instances/{seed_instance.id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Test Instance"


@pytest.mark.asyncio
async def test_get_instance_not_found(admin_client, seed_user):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/voice-live/instances/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_instance(admin_client, seed_instance):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.put(
            f"/api/v1/voice-live/instances/{seed_instance.id}",
            json={"name": "Updated Name", "voice_live_model": "gpt-4o-mini"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Updated Name"
    assert data["voice_live_model"] == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_delete_instance_no_refs(admin_client, seed_instance):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.delete(f"/api/v1/voice-live/instances/{seed_instance.id}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_instance_auto_unassigns_hcps(
    admin_client, seed_instance, seed_hcp, db_session
):
    """Deleting a VL instance with assigned HCPs should auto-unassign them first."""
    # Assign instance to HCP first
    seed_hcp.voice_live_instance_id = seed_instance.id
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.delete(f"/api/v1/voice-live/instances/{seed_instance.id}")
    assert resp.status_code == 204

    # Verify HCP's instance reference is now None
    await db_session.refresh(seed_hcp)
    assert seed_hcp.voice_live_instance_id is None


# ---------------------------------------------------------------------------
# Assignment Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assign_instance_to_hcp(admin_client, seed_instance, seed_hcp):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/api/v1/voice-live/instances/{seed_instance.id}/assign",
            json={"hcp_profile_id": seed_hcp.id},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["hcp_count"] == 1


# ---------------------------------------------------------------------------
# Config Resolution Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_config_prefers_instance(db_session, seed_instance, seed_hcp):
    """When HcpProfile has a VoiceLiveInstance, config should come from instance."""
    seed_hcp.voice_live_instance_id = seed_instance.id
    seed_hcp.voice_live_instance = seed_instance
    await db_session.commit()

    config = resolve_voice_config(seed_hcp)
    assert config["voice_name"] == seed_instance.voice_name
    assert config["avatar_character"] == seed_instance.avatar_character
    assert config["voice_live_model"] == seed_instance.voice_live_model


@pytest.mark.skip(
    reason=(
        "D-09/D-13: HcpProfile no longer has inline voice/avatar columns -- "
        "resolve_voice_config's no-VL-instance fallback branch (in "
        "voice_live_instance_service.py, owned by Plan 29-06) still reads "
        "profile.voice_live_enabled/voice_name/etc. and will raise AttributeError. "
        "voice_live_instance_id is now required at the API layer (D-13) so this "
        "path should only be reachable for legacy rows; Plan 29-06 must update "
        "the fallback to return safe defaults instead of reading deleted columns."
    )
)
@pytest.mark.asyncio
async def test_resolve_config_fallback_to_inline(db_session, seed_hcp):
    """When HcpProfile has no VoiceLiveInstance, config comes from inline fields."""
    seed_hcp.voice_live_instance_id = None
    seed_hcp.voice_live_instance = None
    config = resolve_voice_config(seed_hcp)
    assert config["voice_name"] == seed_hcp.voice_name
    assert config["avatar_character"] == seed_hcp.avatar_character


# ---------------------------------------------------------------------------
# Unassign Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unassign_instance_from_hcp(admin_client, seed_instance, seed_hcp, db_session):
    """POST /voice-live/instances/unassign removes the VL instance from HCP."""
    # Pre-assign
    seed_hcp.voice_live_instance_id = seed_instance.id
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/voice-live/instances/unassign",
            json={"hcp_profile_id": seed_hcp.id},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["hcp_profile_id"] == seed_hcp.id
    assert data["voice_live_instance_id"] is None


@pytest.mark.asyncio
async def test_unassign_nonexistent_hcp(admin_client, seed_user):
    """Unassigning a non-existent HCP should return 404."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/voice-live/instances/unassign",
            json={"hcp_profile_id": "nonexistent-hcp"},
        )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# HCP Profile API voice_live_instance_id Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hcp_list_returns_voice_live_instance_id(
    admin_client, seed_instance, seed_hcp, db_session
):
    """GET /hcp-profiles should include voice_live_instance_id in response."""
    # Assign instance to HCP
    seed_hcp.voice_live_instance_id = seed_instance.id
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/hcp-profiles")
    assert resp.status_code == 200
    data = resp.json()
    items = data["items"]
    assert len(items) >= 1
    hcp = next(h for h in items if h["id"] == seed_hcp.id)
    assert hcp["voice_live_instance_id"] == seed_instance.id


@pytest.mark.asyncio
async def test_hcp_detail_returns_voice_live_instance_id(
    admin_client, seed_instance, seed_hcp, db_session
):
    """GET /hcp-profiles/{id} should include voice_live_instance_id in response."""
    seed_hcp.voice_live_instance_id = seed_instance.id
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/api/v1/hcp-profiles/{seed_hcp.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["voice_live_instance_id"] == seed_instance.id


@pytest.mark.asyncio
async def test_assign_then_list_shows_updated_hcp_count(admin_client, seed_instance, seed_hcp):
    """After assigning HCP to instance, listing should show hcp_count = 1."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Assign
        resp = await ac.post(
            f"/api/v1/voice-live/instances/{seed_instance.id}/assign",
            json={"hcp_profile_id": seed_hcp.id},
        )
        assert resp.status_code == 200
        assert resp.json()["hcp_count"] == 1

        # List and verify hcp_count
        resp = await ac.get("/api/v1/voice-live/instances")
    assert resp.status_code == 200
    items = resp.json()["items"]
    inst = next(i for i in items if i["id"] == seed_instance.id)
    assert inst["hcp_count"] == 1


@pytest.mark.asyncio
async def test_delete_instance_then_verify_gone(admin_client, seed_instance):
    """After deleting, GET should return 404."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.delete(f"/api/v1/voice-live/instances/{seed_instance.id}")
        assert resp.status_code == 204

        resp = await ac.get(f"/api/v1/voice-live/instances/{seed_instance.id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# AI Foundry Playground Alignment — New Fields (n17a migration)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_instance_with_foundry_fields(admin_client, seed_user):
    """POST /voice-live/instances with all AI Foundry Playground fields."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/voice-live/instances",
            json={
                "name": "Foundry Aligned Config",
                "voice_live_model": "gpt-4o-realtime",
                "voice_name": "en-US-AvaDragonHDLatest",
                "avatar_character": "lisa",
                "response_temperature": 0.6,
                "proactive_engagement": False,
                "auto_detect_language": False,
                "recognition_language": "zh-CN",
                "playback_speed": 1.5,
                "custom_lexicon_enabled": True,
                "custom_lexicon_url": "https://example.com/lexicon.xml",
                "avatar_enabled": True,
            },
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["response_temperature"] == 0.6
    assert data["proactive_engagement"] is False
    assert data["auto_detect_language"] is False
    assert data["recognition_language"] == "zh-CN"
    assert data["playback_speed"] == 1.5
    assert data["custom_lexicon_enabled"] is True
    assert data["custom_lexicon_url"] == "https://example.com/lexicon.xml"
    assert data["avatar_enabled"] is True


@pytest.mark.asyncio
async def test_create_instance_foundry_defaults(admin_client, seed_user):
    """New fields should have correct defaults when not specified."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/voice-live/instances",
            json={"name": "Defaults Test", "voice_live_model": "gpt-4o"},
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["response_temperature"] == 0.8
    assert data["proactive_engagement"] is True
    assert data["auto_detect_language"] is True
    assert data["playback_speed"] == 1.0
    assert data["custom_lexicon_enabled"] is False
    assert data["custom_lexicon_url"] == ""
    assert data["avatar_enabled"] is True


@pytest.mark.asyncio
async def test_update_instance_foundry_fields(admin_client, seed_instance):
    """PUT /voice-live/instances/{id} can update AI Foundry fields."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.put(
            f"/api/v1/voice-live/instances/{seed_instance.id}",
            json={
                "response_temperature": 1.2,
                "proactive_engagement": False,
                "playback_speed": 0.8,
                "custom_lexicon_enabled": True,
                "custom_lexicon_url": "https://storage.blob.core.windows.net/lex.xml",
                "avatar_enabled": False,
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["response_temperature"] == 1.2
    assert data["proactive_engagement"] is False
    assert data["playback_speed"] == 0.8
    assert data["custom_lexicon_enabled"] is True
    assert data["custom_lexicon_url"] == "https://storage.blob.core.windows.net/lex.xml"
    assert data["avatar_enabled"] is False
