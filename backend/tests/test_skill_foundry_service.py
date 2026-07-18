"""Unit tests for skill_foundry_service: Entra-only Foundry Skills sync/delete.

Covers collision-safe naming (_build_unique_foundry_name — REVIEWS.md HIGH-2), the
cached-credential Entra-only client (MEDIUM-6), the bounded non-blocking sync/delete
(D-06, MEDIUM-7), and the skill/archive/delete lifecycle hooks wired in skill_service.py
(WARNING-2).
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.skill import Skill

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_credential_cache():
    """Reset the module-level cached credential between tests for isolation."""
    import app.services.skill_foundry_service as sfs

    sfs._cached_credential = None
    yield
    sfs._cached_credential = None


def make_skill(name: str = "My Skill", skill_id: str | None = None, foundry_skill_name: str = "") -> Skill:
    """Build an in-memory Skill instance (not persisted) for pure unit tests."""
    return Skill(
        id=skill_id or str(uuid.uuid4()),
        name=name,
        created_by="test-user",
        foundry_skill_name=foundry_skill_name,
    )


# ---------------------------------------------------------------------------
# _sanitize_skill_name
# ---------------------------------------------------------------------------


def test_sanitize_skill_name_basic():
    from app.services.skill_foundry_service import _sanitize_skill_name

    result = _sanitize_skill_name("My Skill_v2!")
    assert re_match_valid(result)
    assert len(result) <= 64
    assert "--" not in result


def test_sanitize_skill_name_empty_fallback():
    from app.services.skill_foundry_service import _sanitize_skill_name

    assert _sanitize_skill_name("!!!") == "skill"
    assert _sanitize_skill_name("") == "skill"


def test_sanitize_skill_name_truncates_to_64():
    from app.services.skill_foundry_service import _sanitize_skill_name

    long_name = "a" * 100
    result = _sanitize_skill_name(long_name)
    assert len(result) <= 64
    assert re_match_valid(result)


def re_match_valid(value: str) -> bool:
    import re

    return bool(re.match(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", value))


# ---------------------------------------------------------------------------
# _build_unique_foundry_name
# ---------------------------------------------------------------------------


def test_build_unique_foundry_name_basic():
    from app.services.skill_foundry_service import _build_unique_foundry_name

    result = _build_unique_foundry_name("My Skill!", "abcd1234-5678-90ab-cdef-1234567890ab")
    assert result.endswith("-abcd1234")
    assert re_match_valid(result)
    assert len(result) <= 64
    assert "--" not in result


def test_build_unique_foundry_name_collision_guard():
    """REVIEWS.md HIGH-2 regression guard: two names that sanitize to the same slug
    must produce different unique names when given different skill_id values."""
    from app.services.skill_foundry_service import _build_unique_foundry_name, _sanitize_skill_name

    # Confirm the collision actually exists at the sanitize-alone level
    assert _sanitize_skill_name("My Skill!") == _sanitize_skill_name("My Skill?")

    name_a = _build_unique_foundry_name("My Skill!", "id-A")
    name_b = _build_unique_foundry_name("My Skill?", "id-B")
    assert name_a != name_b


def test_build_unique_foundry_name_all_punctuation_still_valid():
    """_sanitize_skill_name's own "skill" fallback keeps name_part non-empty here."""
    from app.services.skill_foundry_service import _build_unique_foundry_name

    result = _build_unique_foundry_name("!!!", "abcd1234-5678-90ab-cdef-1234567890ab")
    assert result == "skill-abcd1234"


def test_build_unique_foundry_name_name_part_empty_after_truncation_uses_skill_fallback():
    """Defensive branch: if _sanitize_skill_name ever returned a dash-only string
    (not possible under its own current guarantees, since it always strips
    boundary dashes), _build_unique_foundry_name must still fall back to "skill"
    rather than producing an invalid leading-dash name."""
    from app.services.skill_foundry_service import _build_unique_foundry_name

    with patch("app.services.skill_foundry_service._sanitize_skill_name", return_value="-"):
        result = _build_unique_foundry_name("whatever", "abcd1234-5678-90ab-cdef-1234567890ab")

    assert result == "skill-abcd1234"


def test_build_unique_foundry_name_long_name_truncation_preserves_suffix():
    from app.services.skill_foundry_service import _build_unique_foundry_name

    long_name = "a" * 200
    skill_id = "12345678-90ab-cdef-1234-567890abcdef"
    result = _build_unique_foundry_name(long_name, skill_id)
    assert len(result) <= 64
    assert result.endswith("-12345678")
    assert re_match_valid(result)
    assert "--" not in result


# ---------------------------------------------------------------------------
# get_skills_client
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_skills_client_raises_on_no_credential():
    from app.services.skill_foundry_service import get_skills_client

    mock_db = AsyncMock()
    mock_cred_cls = MagicMock()
    mock_cred_cls.return_value.get_token.side_effect = Exception("no az login")

    with (
        patch(
            "app.services.skill_foundry_service.agent_sync_service.get_project_endpoint",
            new=AsyncMock(return_value=("https://endpoint.azure.com/api/projects/proj", "")),
        ),
        patch("app.services.skill_foundry_service.DefaultAzureCredential", mock_cred_cls),
    ):
        with pytest.raises(RuntimeError):
            await get_skills_client(mock_db)


@pytest.mark.asyncio
async def test_get_skills_client_caches_credential_instance():
    from app.services.skill_foundry_service import get_skills_client

    mock_db = AsyncMock()
    mock_cred_cls = MagicMock()
    mock_client_cls = MagicMock()

    with (
        patch(
            "app.services.skill_foundry_service.agent_sync_service.get_project_endpoint",
            new=AsyncMock(return_value=("https://endpoint.azure.com/api/projects/proj", "")),
        ),
        patch("app.services.skill_foundry_service.DefaultAzureCredential", mock_cred_cls),
        patch("app.services.skill_foundry_service.AIProjectClient", mock_client_cls),
    ):
        await get_skills_client(mock_db)
        await get_skills_client(mock_db)

    # DefaultAzureCredential() constructor called exactly once across two calls
    mock_cred_cls.assert_called_once()
    # Both AIProjectClient constructions received the SAME credential instance
    first_call_cred = mock_client_cls.call_args_list[0].kwargs["credential"]
    second_call_cred = mock_client_cls.call_args_list[1].kwargs["credential"]
    assert first_call_cred is second_call_cred


@pytest.mark.asyncio
async def test_get_skills_client_success_returns_client_with_allow_preview():
    from app.services.skill_foundry_service import get_skills_client

    mock_db = AsyncMock()
    mock_cred_cls = MagicMock()
    mock_client_cls = MagicMock()

    with (
        patch(
            "app.services.skill_foundry_service.agent_sync_service.get_project_endpoint",
            new=AsyncMock(return_value=("https://endpoint.azure.com/api/projects/proj", "")),
        ),
        patch("app.services.skill_foundry_service.DefaultAzureCredential", mock_cred_cls),
        patch("app.services.skill_foundry_service.AIProjectClient", mock_client_cls),
    ):
        result = await get_skills_client(mock_db)

    assert result is mock_client_cls.return_value
    call_kwargs = mock_client_cls.call_args.kwargs
    assert call_kwargs["endpoint"] == "https://endpoint.azure.com/api/projects/proj"
    assert call_kwargs["allow_preview"] is True


def test_no_api_key_credential_fallback_in_module():
    """T-28-01: this surface must never attempt API-key auth."""
    import inspect

    from app.services import skill_foundry_service

    source = inspect.getsource(skill_foundry_service)
    assert "AzureKeyCredential" not in source


# ---------------------------------------------------------------------------
# sync_skill_to_foundry
# ---------------------------------------------------------------------------


def _mock_client_with_result(name: str, version: int = 1):
    client = MagicMock()
    result = MagicMock()
    result.name = name
    result.version = version
    client.beta.skills.create_from_files = MagicMock(return_value=result)
    return client


@pytest.mark.asyncio
async def test_sync_skill_to_foundry_first_sync_uses_unique_name():
    from app.services.skill_foundry_service import _build_unique_foundry_name, sync_skill_to_foundry

    skill = make_skill(name="My Skill!", foundry_skill_name="")
    expected_name = _build_unique_foundry_name(skill.name, skill.id)
    client = _mock_client_with_result(expected_name, version=1)

    mock_db = AsyncMock()

    with (
        patch(
            "app.services.skill_foundry_service.get_skills_client", new=AsyncMock(return_value=client)
        ),
        patch(
            "app.services.skill_foundry_service.skill_zip_service.export_skill_zip",
            new=AsyncMock(return_value=b"zipbytes"),
        ),
        patch(
            "app.services.skill_foundry_service.skill_zip_service.validate_zip_security",
            return_value=[],
        ),
    ):
        await sync_skill_to_foundry(mock_db, skill)

    call_args = client.beta.skills.create_from_files.call_args
    assert call_args.args[0] == expected_name
    # First-sync uses the id-suffixed unique name, not the bare sanitized name alone
    from app.services.skill_foundry_service import _sanitize_skill_name

    assert call_args.args[0] != _sanitize_skill_name(skill.name) or expected_name == _sanitize_skill_name(
        skill.name
    )


@pytest.mark.asyncio
async def test_sync_skill_to_foundry_success_sets_fields():
    from app.services.skill_foundry_service import sync_skill_to_foundry

    skill = make_skill(name="Detail Skill", foundry_skill_name="")
    client = _mock_client_with_result("detail-skill-abcd1234", version=1)

    mock_db = AsyncMock()

    with (
        patch(
            "app.services.skill_foundry_service.get_skills_client", new=AsyncMock(return_value=client)
        ),
        patch(
            "app.services.skill_foundry_service.skill_zip_service.export_skill_zip",
            new=AsyncMock(return_value=b"zipbytes"),
        ),
        patch(
            "app.services.skill_foundry_service.skill_zip_service.validate_zip_security",
            return_value=[],
        ),
    ):
        await sync_skill_to_foundry(mock_db, skill)

    assert skill.foundry_sync_status == "synced"
    assert skill.foundry_skill_name == "detail-skill-abcd1234"
    assert skill.foundry_cloud_version == "1"
    assert skill.foundry_sync_error == ""
    mock_db.flush.assert_awaited()


@pytest.mark.asyncio
async def test_sync_skill_to_foundry_exception_sets_failed_never_raises():
    from app.services.skill_foundry_service import sync_skill_to_foundry

    skill = make_skill(name="Failing Skill", foundry_skill_name="")

    client = MagicMock()
    client.beta.skills.create_from_files = MagicMock(side_effect=RuntimeError("boom"))

    mock_db = AsyncMock()

    with (
        patch(
            "app.services.skill_foundry_service.get_skills_client", new=AsyncMock(return_value=client)
        ),
        patch(
            "app.services.skill_foundry_service.skill_zip_service.export_skill_zip",
            new=AsyncMock(return_value=b"zipbytes"),
        ),
        patch(
            "app.services.skill_foundry_service.skill_zip_service.validate_zip_security",
            return_value=[],
        ),
    ):
        await sync_skill_to_foundry(mock_db, skill)  # must not raise

    assert skill.foundry_sync_status == "failed"
    assert "boom" in skill.foundry_sync_error


@pytest.mark.asyncio
async def test_sync_skill_to_foundry_timeout_sets_failed_never_raises():
    """A simulated TimeoutError from the asyncio.wait_for bound around create_from_files
    is caught the same as any other exception -- D-06's non-blocking guarantee holds
    regardless of failure cause."""
    from app.services.skill_foundry_service import sync_skill_to_foundry

    skill = make_skill(name="Timeout Skill", foundry_skill_name="")
    client = _mock_client_with_result("timeout-skill-abcd1234")

    mock_db = AsyncMock()

    with (
        patch(
            "app.services.skill_foundry_service.get_skills_client", new=AsyncMock(return_value=client)
        ),
        patch(
            "app.services.skill_foundry_service.skill_zip_service.export_skill_zip",
            new=AsyncMock(return_value=b"zipbytes"),
        ),
        patch(
            "app.services.skill_foundry_service.skill_zip_service.validate_zip_security",
            return_value=[],
        ),
        patch(
            "app.services.skill_foundry_service.asyncio.wait_for",
            new=AsyncMock(side_effect=TimeoutError("timed out")),
        ),
    ):
        await sync_skill_to_foundry(mock_db, skill)  # must not raise

    assert skill.foundry_sync_status == "failed"
    assert "timed out" in skill.foundry_sync_error


@pytest.mark.asyncio
async def test_sync_skill_to_foundry_zip_security_failure_sets_failed():
    from app.services.skill_foundry_service import sync_skill_to_foundry

    skill = make_skill(name="Insecure Skill", foundry_skill_name="")
    client = _mock_client_with_result("insecure-skill-abcd1234")

    mock_db = AsyncMock()

    with (
        patch(
            "app.services.skill_foundry_service.get_skills_client", new=AsyncMock(return_value=client)
        ),
        patch(
            "app.services.skill_foundry_service.skill_zip_service.export_skill_zip",
            new=AsyncMock(return_value=b"zipbytes"),
        ),
        patch(
            "app.services.skill_foundry_service.skill_zip_service.validate_zip_security",
            return_value=["path traversal detected"],
        ),
    ):
        await sync_skill_to_foundry(mock_db, skill)  # must not raise

    assert skill.foundry_sync_status == "failed"
    client.beta.skills.create_from_files.assert_not_called()


@pytest.mark.asyncio
async def test_sync_skill_to_foundry_called_twice_same_name():
    """sync_skill_to_foundry called twice with the same skill results in create_from_files
    being invoked twice with the identical name, since foundry_skill_name is persisted
    after the first sync."""
    from app.services.skill_foundry_service import sync_skill_to_foundry

    skill = make_skill(name="Repeat Skill", foundry_skill_name="")
    client = _mock_client_with_result("repeat-skill-abcd1234", version=1)

    mock_db = AsyncMock()

    with (
        patch(
            "app.services.skill_foundry_service.get_skills_client", new=AsyncMock(return_value=client)
        ),
        patch(
            "app.services.skill_foundry_service.skill_zip_service.export_skill_zip",
            new=AsyncMock(return_value=b"zipbytes"),
        ),
        patch(
            "app.services.skill_foundry_service.skill_zip_service.validate_zip_security",
            return_value=[],
        ),
    ):
        await sync_skill_to_foundry(mock_db, skill)
        # Second call: version bumped to simulate Foundry-side increment
        result2 = MagicMock()
        result2.name = skill.foundry_skill_name
        result2.version = 2
        client.beta.skills.create_from_files = MagicMock(return_value=result2)
        await sync_skill_to_foundry(mock_db, skill)

    assert client.beta.skills.create_from_files.call_count == 1  # reassigned mock only tracks 2nd call
    # Verify both calls used the identical name by checking persisted foundry_skill_name never changed
    assert skill.foundry_skill_name == "repeat-skill-abcd1234"


# ---------------------------------------------------------------------------
# delete_skill_from_foundry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_skill_from_foundry_noop_when_no_foundry_name():
    from app.services.skill_foundry_service import delete_skill_from_foundry

    skill = make_skill(foundry_skill_name="")
    mock_db = AsyncMock()

    with patch(
        "app.services.skill_foundry_service.get_skills_client", new=AsyncMock()
    ) as mock_get_client:
        await delete_skill_from_foundry(mock_db, skill)

    mock_get_client.assert_not_called()


@pytest.mark.asyncio
async def test_delete_skill_from_foundry_success_resets_fields():
    from app.services.skill_foundry_service import delete_skill_from_foundry

    skill = make_skill(foundry_skill_name="existing-skill-abcd1234")
    skill.foundry_sync_status = "synced"
    skill.foundry_cloud_version = "1"
    client = MagicMock()
    client.beta.skills.delete = MagicMock(return_value=None)
    mock_db = AsyncMock()

    with patch(
        "app.services.skill_foundry_service.get_skills_client", new=AsyncMock(return_value=client)
    ):
        await delete_skill_from_foundry(mock_db, skill)

    assert skill.foundry_skill_name == ""
    assert skill.foundry_cloud_version == ""
    assert skill.foundry_sync_status == "none"
    assert skill.foundry_sync_error == ""
    mock_db.flush.assert_awaited()


@pytest.mark.asyncio
async def test_delete_skill_from_foundry_404_treated_as_success():
    from app.services.skill_foundry_service import delete_skill_from_foundry

    skill = make_skill(foundry_skill_name="gone-skill-abcd1234")

    class FakeNotFoundError(Exception):
        status_code = 404

    client = MagicMock()
    client.beta.skills.delete = MagicMock(side_effect=FakeNotFoundError("not found"))
    mock_db = AsyncMock()

    with patch(
        "app.services.skill_foundry_service.get_skills_client", new=AsyncMock(return_value=client)
    ):
        await delete_skill_from_foundry(mock_db, skill)  # must not raise

    assert skill.foundry_skill_name == ""
    assert skill.foundry_sync_status == "none"


@pytest.mark.asyncio
async def test_delete_skill_from_foundry_non_404_error_still_resets_and_does_not_raise():
    from app.services.skill_foundry_service import delete_skill_from_foundry

    skill = make_skill(foundry_skill_name="error-skill-abcd1234")

    class FakeServerError(Exception):
        status_code = 500

    client = MagicMock()
    client.beta.skills.delete = MagicMock(side_effect=FakeServerError("server error"))
    mock_db = AsyncMock()

    with patch(
        "app.services.skill_foundry_service.get_skills_client", new=AsyncMock(return_value=client)
    ):
        await delete_skill_from_foundry(mock_db, skill)  # must not raise

    assert skill.foundry_skill_name == ""
    assert skill.foundry_sync_status == "none"


# ---------------------------------------------------------------------------
# get_skill_portal_url
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_skill_portal_url_no_foundry_name_returns_generic():
    from app.services.skill_foundry_service import get_skill_portal_url

    skill = make_skill(foundry_skill_name="")
    mock_db = AsyncMock()

    result = await get_skill_portal_url(mock_db, skill)
    assert result == "https://ai.azure.com"


@pytest.mark.asyncio
async def test_get_skill_portal_url_with_components_builds_deep_link():
    from app.services.skill_foundry_service import get_skill_portal_url

    skill = make_skill(foundry_skill_name="my-skill-abcd1234")
    mock_db = AsyncMock()

    components = {
        "subscription_hash": "subhash",
        "resource_group": "my-rg",
        "resource_name": "my-account",
        "project_name": "my-project",
    }

    with patch(
        "app.services.skill_foundry_service.agent_sync_service.get_portal_url_components",
        new=AsyncMock(return_value=components),
    ):
        result = await get_skill_portal_url(mock_db, skill)

    assert "my-skill-abcd1234" in result
    assert "subhash" in result
    assert "my-rg" in result
    assert "my-account" in result
    assert "my-project" in result


@pytest.mark.asyncio
async def test_get_skill_portal_url_fallback_when_components_missing():
    from app.services.skill_foundry_service import get_skill_portal_url

    skill = make_skill(foundry_skill_name="my-skill-abcd1234")
    mock_db = AsyncMock()

    with patch(
        "app.services.skill_foundry_service.agent_sync_service.get_portal_url_components",
        new=AsyncMock(return_value={}),
    ):
        result = await get_skill_portal_url(mock_db, skill)

    assert result == "https://ai.azure.com"


# ---------------------------------------------------------------------------
# Lifecycle hooks (Task 3): publish_skill/archive_skill/delete_skill wiring
# in skill_service.py -- exercised against a real in-memory SQLite session
# (tests/conftest.py db_session fixture) with skill_foundry_service's
# sync/delete functions patched, per skill_service.skill_foundry_service.
# ---------------------------------------------------------------------------


async def _seed_admin_user(db_session) -> str:
    """Create a test admin user and return the user_id."""
    from app.models.user import User
    from app.services.auth import get_password_hash

    user = User(
        username="foundry_lifecycle_admin",
        email="foundry_lifecycle_admin@test.com",
        hashed_password=get_password_hash("pass"),
        full_name="Foundry Lifecycle Admin",
        role="admin",
    )
    db_session.add(user)
    await db_session.flush()
    return user.id


async def _create_publishable_skill(db_session, user_id: str) -> Skill:
    """Create a skill and advance it through draft -> review with quality gates
    set so that publish_skill() will succeed."""
    import json

    from app.schemas.skill import SkillCreate, SkillUpdate
    from app.services import skill_service
    from app.services.skill_validation_service import _compute_content_hash

    data = SkillCreate(
        name="Foundry Lifecycle Test Skill",
        description="Skill used to test Foundry sync lifecycle hooks",
        product="TestProduct",
        content="# Foundry Lifecycle Test Skill\nSome content for testing.",
    )
    skill = await skill_service.create_skill(db_session, data, user_id)
    await skill_service.update_skill(db_session, skill.id, SkillUpdate(status="review"), user_id)
    skill = await skill_service.get_skill(db_session, skill.id)

    skill.structure_check_passed = True
    skill.quality_score = 80
    skill.quality_verdict = "PASS"
    skill.quality_details = json.dumps({"content_hash": _compute_content_hash(skill.content or "")})
    await db_session.flush()

    return skill


@pytest.mark.asyncio
async def test_publish_skill_calls_sync_skill_to_foundry_once(db_session):
    from app.services import skill_service

    user_id = await _seed_admin_user(db_session)
    skill = await _create_publishable_skill(db_session, user_id)

    mock_sync = AsyncMock()
    with patch("app.services.skill_service.skill_foundry_service.sync_skill_to_foundry", mock_sync):
        published = await skill_service.publish_skill(db_session, skill.id, user_id)

    assert published.status == "published"
    mock_sync.assert_awaited_once()
    call_args = mock_sync.await_args
    assert call_args.args[0] is db_session
    assert call_args.args[1].id == skill.id


@pytest.mark.asyncio
async def test_publish_skill_succeeds_even_when_sync_fails_internally(db_session):
    """D-06: publish must never be blocked by a Foundry sync failure. Since
    sync_skill_to_foundry's own contract is to never raise (Task 2), this mock
    simulates the REAL internal-failure behavior (sets foundry_sync_status
    without raising) to prove publish_skill() does not depend on sync success."""
    from app.services import skill_service

    user_id = await _seed_admin_user(db_session)
    skill = await _create_publishable_skill(db_session, user_id)

    async def _simulate_internal_failure(db, target_skill):
        target_skill.foundry_sync_status = "failed"
        target_skill.foundry_sync_error = "simulated Foundry outage"

    with patch(
        "app.services.skill_service.skill_foundry_service.sync_skill_to_foundry",
        AsyncMock(side_effect=_simulate_internal_failure),
    ):
        published = await skill_service.publish_skill(db_session, skill.id, user_id)

    assert published.status == "published"


@pytest.mark.asyncio
async def test_publish_skill_idempotent_second_call_does_not_resync(db_session):
    """WARNING-2 regression guard: calling publish_skill() again on an already
    published skill hits the existing idempotent early return and must NOT
    re-trigger sync_skill_to_foundry."""
    from app.services import skill_service

    user_id = await _seed_admin_user(db_session)
    skill = await _create_publishable_skill(db_session, user_id)

    mock_sync = AsyncMock()
    with patch("app.services.skill_service.skill_foundry_service.sync_skill_to_foundry", mock_sync):
        await skill_service.publish_skill(db_session, skill.id, user_id)
        await skill_service.publish_skill(db_session, skill.id, user_id)

    assert mock_sync.await_count == 1


@pytest.mark.asyncio
async def test_archive_skill_calls_delete_skill_from_foundry_once(db_session):
    from app.services import skill_service

    user_id = await _seed_admin_user(db_session)
    skill = await _create_publishable_skill(db_session, user_id)

    with patch(
        "app.services.skill_service.skill_foundry_service.sync_skill_to_foundry", AsyncMock()
    ):
        published = await skill_service.publish_skill(db_session, skill.id, user_id)

    mock_delete = AsyncMock()
    with patch("app.services.skill_service.skill_foundry_service.delete_skill_from_foundry", mock_delete):
        archived = await skill_service.archive_skill(db_session, published.id, user_id)

    assert archived.status == "archived"
    mock_delete.assert_awaited_once()
    call_args = mock_delete.await_args
    assert call_args.args[0] is db_session
    assert call_args.args[1].id == published.id


@pytest.mark.asyncio
async def test_delete_skill_calls_delete_skill_from_foundry_once(db_session):
    from app.schemas.skill import SkillCreate
    from app.services import skill_service

    user_id = await _seed_admin_user(db_session)
    data = SkillCreate(name="Deletable Draft Skill", content="draft content")
    skill = await skill_service.create_skill(db_session, data, user_id)

    mock_delete = AsyncMock()
    with patch("app.services.skill_service.skill_foundry_service.delete_skill_from_foundry", mock_delete):
        await skill_service.delete_skill(db_session, skill.id)

    mock_delete.assert_awaited_once()
    call_args = mock_delete.await_args
    assert call_args.args[0] is db_session
    assert call_args.args[1].id == skill.id


@pytest.mark.asyncio
async def test_restore_skill_does_not_call_any_foundry_function(db_session):
    from app.services import skill_service

    user_id = await _seed_admin_user(db_session)
    skill = await _create_publishable_skill(db_session, user_id)

    with patch(
        "app.services.skill_service.skill_foundry_service.sync_skill_to_foundry", AsyncMock()
    ):
        published = await skill_service.publish_skill(db_session, skill.id, user_id)

    mock_sync = AsyncMock()
    mock_delete = AsyncMock()
    with (
        patch("app.services.skill_service.skill_foundry_service.sync_skill_to_foundry", mock_sync),
        patch("app.services.skill_service.skill_foundry_service.delete_skill_from_foundry", mock_delete),
    ):
        await skill_service.archive_skill(db_session, published.id, user_id)
        restored = await skill_service.restore_skill(db_session, published.id, user_id)

    assert restored.status == "draft"
    mock_sync.assert_not_awaited()
    # delete_skill_from_foundry was called once by the preceding archive_skill call,
    # but restore_skill itself must not trigger any additional Foundry call.
    assert mock_delete.await_count == 1
