"""Unit tests for skill_consumption_service: Toolbox mount + MCP probe +
download fallback + local-degradation abstraction with a TTL cache.

Covers D-02 (best-effort Toolbox mount), D-04 (real MCP probe with honest
degrade), D-05 (single SkillContent abstraction consumed by text + Voice
Live), D-06 (local-DB fallback), HIGH-1 (TTL cache absorbing per-message
cloud round-trips), MEDIUM-4 (version-pin bypass of the cloud path), and
LOW-9 (defensive getattr in the MCP probe).
"""

import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.hcp_profile import HcpProfile
from app.models.scenario import Scenario
from app.models.skill import Skill
from app.models.user import User
from app.services.skill_manager import SkillContent
from tests.conftest import TestSessionLocal

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_content_cache():
    """Reset the module-level TTL cache between tests for isolation."""
    import app.services.skill_consumption_service as scs

    scs._content_cache.clear()
    yield
    scs._content_cache.clear()


def make_skill(
    name: str = "My Skill",
    skill_id: str | None = None,
    foundry_skill_name: str = "",
    foundry_sync_status: str = "none",
    foundry_cloud_version: str = "",
) -> Skill:
    """Build an in-memory Skill instance (not persisted) for pure unit tests."""
    return Skill(
        id=skill_id or str(uuid.uuid4()),
        name=name,
        created_by="test-user",
        foundry_skill_name=foundry_skill_name,
        foundry_sync_status=foundry_sync_status,
        foundry_cloud_version=foundry_cloud_version,
    )


async def _seed_user() -> str:
    from app.services.auth import get_password_hash

    async with TestSessionLocal() as session:
        user = User(
            username="skill_consumption_admin",
            email="skill_consumption_admin@test.com",
            hashed_password=get_password_hash("pass"),
            full_name="Skill Consumption Admin",
            role="admin",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user.id


async def _seed_hcp_profile(user_id: str) -> str:
    async with TestSessionLocal() as session:
        hcp = HcpProfile(name="Dr. Test", specialty="Oncology", created_by=user_id)
        session.add(hcp)
        await session.commit()
        await session.refresh(hcp)
        return hcp.id


async def _seed_skill(user_id: str, **kwargs) -> str:
    async with TestSessionLocal() as session:
        skill = Skill(
            name=kwargs.get("name", "Cloud Skill"),
            description=kwargs.get("description", ""),
            content=kwargs.get("content", "Local fallback content"),
            status=kwargs.get("status", "published"),
            created_by=user_id,
            foundry_skill_name=kwargs.get("foundry_skill_name", ""),
            foundry_sync_status=kwargs.get("foundry_sync_status", "none"),
            foundry_cloud_version=kwargs.get("foundry_cloud_version", ""),
        )
        session.add(skill)
        await session.commit()
        await session.refresh(skill)
        return skill.id


async def _seed_scenario(
    user_id: str, hcp_id: str, skill_id: str, skill_version_id: str | None = None
) -> str:
    async with TestSessionLocal() as session:
        scenario = Scenario(
            name="Consumption test scenario",
            hcp_profile_id=hcp_id,
            skill_id=skill_id,
            skill_version_id=skill_version_id,
            created_by=user_id,
            rubric_id="test-rubric-id",
        )
        session.add(scenario)
        await session.commit()
        await session.refresh(scenario)
        return scenario.id


def _toolbox_client(create_version_result=None, create_version_side_effect=None):
    client = MagicMock()
    toolboxes_op = MagicMock()
    if create_version_side_effect is not None:
        toolboxes_op.create_version = MagicMock(side_effect=create_version_side_effect)
    else:
        toolboxes_op.create_version = MagicMock(return_value=create_version_result or MagicMock())
    client.toolboxes = toolboxes_op
    return client


# ---------------------------------------------------------------------------
# mount_skill_toolbox
# ---------------------------------------------------------------------------


class TestMountSkillToolbox:
    async def test_not_synced_returns_none_no_network(self):
        from app.services.skill_consumption_service import mount_skill_toolbox

        skill = make_skill(foundry_sync_status="pending", foundry_skill_name="my-skill-abcd1234")
        mock_db = AsyncMock()

        with patch(
            "app.services.skill_consumption_service.get_skills_client", new=AsyncMock()
        ) as mock_get_client:
            result = await mount_skill_toolbox(mock_db, skill)

        assert result is None
        mock_get_client.assert_not_called()

    async def test_no_foundry_skill_name_returns_none(self):
        from app.services.skill_consumption_service import mount_skill_toolbox

        skill = make_skill(foundry_sync_status="synced", foundry_skill_name="")
        mock_db = AsyncMock()

        result = await mount_skill_toolbox(mock_db, skill)
        assert result is None

    async def test_synced_typed_kwarg_success_returns_toolbox_name(self):
        from app.services.skill_consumption_service import mount_skill_toolbox

        skill = make_skill(foundry_sync_status="synced", foundry_skill_name="my-skill-abcd1234")
        client = _toolbox_client()
        mock_db = AsyncMock()

        with patch(
            "app.services.skill_consumption_service.get_skills_client",
            new=AsyncMock(return_value=client),
        ):
            result = await mount_skill_toolbox(mock_db, skill)

        assert result is not None
        client.toolboxes.create_version.assert_called_once()

    async def test_typed_kwarg_raises_falls_back_to_raw_dict(self):
        from app.services.skill_consumption_service import mount_skill_toolbox

        skill = make_skill(foundry_sync_status="synced", foundry_skill_name="my-skill-abcd1234")
        client = MagicMock()
        toolboxes_op = MagicMock()
        # First call (typed kwarg) raises, second call (raw dict) succeeds.
        toolboxes_op.create_version = MagicMock(
            side_effect=[TypeError("unexpected kwarg 'skills'"), MagicMock()]
        )
        client.toolboxes = toolboxes_op
        mock_db = AsyncMock()

        with patch(
            "app.services.skill_consumption_service.get_skills_client",
            new=AsyncMock(return_value=client),
        ):
            result = await mount_skill_toolbox(mock_db, skill)

        assert result is not None
        assert toolboxes_op.create_version.call_count == 2

    async def test_both_attempts_fail_returns_none_never_raises(self):
        from app.services.skill_consumption_service import mount_skill_toolbox

        skill = make_skill(foundry_sync_status="synced", foundry_skill_name="my-skill-abcd1234")
        client = _toolbox_client(create_version_side_effect=RuntimeError("boom"))
        mock_db = AsyncMock()

        with patch(
            "app.services.skill_consumption_service.get_skills_client",
            new=AsyncMock(return_value=client),
        ):
            result = await mount_skill_toolbox(mock_db, skill)  # must not raise

        assert result is None

    async def test_get_skills_client_raises_returns_none_never_raises(self):
        from app.services.skill_consumption_service import mount_skill_toolbox

        skill = make_skill(foundry_sync_status="synced", foundry_skill_name="my-skill-abcd1234")
        mock_db = AsyncMock()

        with patch(
            "app.services.skill_consumption_service.get_skills_client",
            new=AsyncMock(side_effect=RuntimeError("no credential")),
        ):
            result = await mount_skill_toolbox(mock_db, skill)  # must not raise

        assert result is None


# ---------------------------------------------------------------------------
# _try_mcp_fetch
# ---------------------------------------------------------------------------


class TestTryMcpFetch:
    def _client_with_config(self):
        client = MagicMock()
        client._config = MagicMock()
        client._config.credential = MagicMock()
        client._config.credential.get_token = MagicMock(return_value=MagicMock(token="tok"))
        client._config.endpoint = "https://endpoint.azure.com/api/projects/proj"
        toolboxes_op = MagicMock()
        toolboxes_op._config = MagicMock(api_version="v1")
        client.toolboxes = toolboxes_op
        return client

    async def test_non_200_returns_none(self):
        from app.services.skill_consumption_service import _try_mcp_fetch

        client = self._client_with_config()
        mock_db = AsyncMock()
        mock_resp = MagicMock(status_code=405)

        with (
            patch(
                "app.services.skill_consumption_service.get_skills_client",
                new=AsyncMock(return_value=client),
            ),
            patch("app.services.skill_consumption_service.httpx.get", return_value=mock_resp),
        ):
            result = await _try_mcp_fetch(mock_db, "toolbox-name", "skill-name")

        assert result is None

    async def test_connection_error_returns_none_never_raises(self):
        from app.services.skill_consumption_service import _try_mcp_fetch

        client = self._client_with_config()
        mock_db = AsyncMock()

        with (
            patch(
                "app.services.skill_consumption_service.get_skills_client",
                new=AsyncMock(return_value=client),
            ),
            patch(
                "app.services.skill_consumption_service.httpx.get",
                side_effect=ConnectionError("down"),
            ),
        ):
            result = await _try_mcp_fetch(mock_db, "toolbox-name", "skill-name")

        assert result is None

    async def test_missing_config_attrs_returns_none_low9(self):
        """LOW-9: client/toolboxes_op missing _config entirely must not raise."""
        from app.services.skill_consumption_service import _try_mcp_fetch

        client = MagicMock(spec=[])  # no attributes at all, not even _config
        mock_db = AsyncMock()

        with patch(
            "app.services.skill_consumption_service.get_skills_client",
            new=AsyncMock(return_value=client),
        ):
            result = await _try_mcp_fetch(mock_db, "toolbox-name", "skill-name")

        assert result is None

    async def test_200_with_content_key_returns_content(self):
        from app.services.skill_consumption_service import _try_mcp_fetch

        client = self._client_with_config()
        mock_db = AsyncMock()
        mock_resp = MagicMock(status_code=200)
        mock_resp.json = MagicMock(return_value={"content": "MCP-sourced skill body"})

        with (
            patch(
                "app.services.skill_consumption_service.get_skills_client",
                new=AsyncMock(return_value=client),
            ),
            patch("app.services.skill_consumption_service.httpx.get", return_value=mock_resp),
        ):
            result = await _try_mcp_fetch(mock_db, "toolbox-name", "skill-name")

        assert result == "MCP-sourced skill body"

    async def test_200_with_empty_content_returns_none(self):
        from app.services.skill_consumption_service import _try_mcp_fetch

        client = self._client_with_config()
        mock_db = AsyncMock()
        mock_resp = MagicMock(status_code=200)
        mock_resp.json = MagicMock(return_value={"content": ""})

        with (
            patch(
                "app.services.skill_consumption_service.get_skills_client",
                new=AsyncMock(return_value=client),
            ),
            patch("app.services.skill_consumption_service.httpx.get", return_value=mock_resp),
        ):
            result = await _try_mcp_fetch(mock_db, "toolbox-name", "skill-name")

        assert result is None


# ---------------------------------------------------------------------------
# download_and_extract_skill_content
# ---------------------------------------------------------------------------


def _make_skill_zip(skill_md_content: str) -> bytes:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w") as zf:
        zf.writestr("SKILL.md", skill_md_content)
    return buf.getvalue()


class TestDownloadAndExtractSkillContent:
    async def test_no_foundry_skill_name_returns_none(self):
        from app.services.skill_consumption_service import download_and_extract_skill_content

        skill = make_skill(foundry_skill_name="")
        mock_db = AsyncMock()

        result = await download_and_extract_skill_content(mock_db, skill)
        assert result is None

    async def test_successful_roundtrip_returns_skill_content(self):
        from app.services.skill_consumption_service import download_and_extract_skill_content

        skill_md = "---\nname: Cloud Skill\n---\n\nExtracted body text"
        zip_bytes = _make_skill_zip(skill_md)

        skill = make_skill(
            name="Cloud Skill", foundry_skill_name="cloud-skill-abcd1234", foundry_cloud_version="1"
        )
        client = MagicMock()
        client.beta.skills.download = MagicMock(return_value=[zip_bytes])
        mock_db = AsyncMock()

        with patch(
            "app.services.skill_consumption_service.get_skills_client",
            new=AsyncMock(return_value=client),
        ):
            result = await download_and_extract_skill_content(mock_db, skill)

        assert result is not None
        assert result.content == "Extracted body text"
        assert result.version_id == "1"

    async def test_zip_security_validation_failure_returns_none(self):
        from app.services.skill_consumption_service import download_and_extract_skill_content

        skill = make_skill(foundry_skill_name="cloud-skill-abcd1234")
        client = MagicMock()
        client.beta.skills.download = MagicMock(return_value=[b"not-a-real-zip"])
        mock_db = AsyncMock()

        with (
            patch(
                "app.services.skill_consumption_service.get_skills_client",
                new=AsyncMock(return_value=client),
            ),
            patch(
                "app.services.skill_consumption_service.validate_zip_security",
                return_value=["invalid zip"],
            ),
        ):
            result = await download_and_extract_skill_content(mock_db, skill)

        assert result is None

    async def test_download_raises_returns_none_never_raises(self):
        from app.services.skill_consumption_service import download_and_extract_skill_content

        skill = make_skill(foundry_skill_name="cloud-skill-abcd1234")
        mock_db = AsyncMock()

        with patch(
            "app.services.skill_consumption_service.get_skills_client",
            new=AsyncMock(side_effect=RuntimeError("no credential")),
        ):
            result = await download_and_extract_skill_content(mock_db, skill)  # must not raise

        assert result is None


# ---------------------------------------------------------------------------
# get_skill_content_for_session — top-level abstraction
# ---------------------------------------------------------------------------


class TestGetSkillContentForSession:
    async def test_no_skill_id_returns_none(self):
        from app.services.skill_consumption_service import get_skill_content_for_session

        async with TestSessionLocal() as session:
            result = await get_skill_content_for_session(session, "nonexistent-scenario")
        assert result is None

    async def test_scenario_with_pin_never_calls_cloud_chain_medium4(self):
        from app.services.skill_consumption_service import get_skill_content_for_session

        user_id = await _seed_user()
        hcp_id = await _seed_hcp_profile(user_id)
        skill_id = await _seed_skill(
            user_id,
            foundry_sync_status="synced",
            foundry_skill_name="pinned-skill-abcd1234",
            foundry_cloud_version="1",
        )
        scenario_id = await _seed_scenario(
            user_id, hcp_id, skill_id, skill_version_id="some-pinned-version-id"
        )

        async with TestSessionLocal() as session:
            with (
                patch(
                    "app.services.skill_consumption_service.mount_skill_toolbox", new=AsyncMock()
                ) as mock_mount,
                patch(
                    "app.services.skill_consumption_service._try_mcp_fetch", new=AsyncMock()
                ) as mock_mcp,
                patch(
                    "app.services.skill_consumption_service.download_and_extract_skill_content",
                    new=AsyncMock(),
                ) as mock_download,
                patch(
                    "app.services.skill_consumption_service.load_skill_for_scenario",
                    new=AsyncMock(return_value=None),
                ) as mock_local,
            ):
                await get_skill_content_for_session(session, scenario_id)

        mock_mount.assert_not_called()
        mock_mcp.assert_not_called()
        mock_download.assert_not_called()
        mock_local.assert_awaited_once()

    async def test_not_synced_skill_falls_back_to_local_d06(self):
        from app.services.skill_consumption_service import get_skill_content_for_session

        user_id = await _seed_user()
        hcp_id = await _seed_hcp_profile(user_id)
        skill_id = await _seed_skill(user_id, foundry_sync_status="none")
        scenario_id = await _seed_scenario(user_id, hcp_id, skill_id)

        local_content = SkillContent(
            name="Local", description="", content="local body", version_id="", token_estimate=1
        )

        async with TestSessionLocal() as session:
            with patch(
                "app.services.skill_consumption_service.load_skill_for_scenario",
                new=AsyncMock(return_value=local_content),
            ):
                result = await get_skill_content_for_session(session, scenario_id)

        assert result is local_content

    async def test_mcp_available_used_without_calling_download(self):
        from app.services.skill_consumption_service import get_skill_content_for_session

        user_id = await _seed_user()
        hcp_id = await _seed_hcp_profile(user_id)
        skill_id = await _seed_skill(
            user_id,
            foundry_sync_status="synced",
            foundry_skill_name="mcp-skill-abcd1234",
            foundry_cloud_version="1",
        )
        scenario_id = await _seed_scenario(user_id, hcp_id, skill_id)

        async with TestSessionLocal() as session:
            with (
                patch(
                    "app.services.skill_consumption_service.mount_skill_toolbox",
                    new=AsyncMock(return_value="toolbox-name"),
                ),
                patch(
                    "app.services.skill_consumption_service._try_mcp_fetch",
                    new=AsyncMock(return_value="MCP body content"),
                ),
                patch(
                    "app.services.skill_consumption_service.download_and_extract_skill_content",
                    new=AsyncMock(),
                ) as mock_download,
            ):
                result = await get_skill_content_for_session(session, scenario_id)

        assert result is not None
        assert result.content == "MCP body content"
        mock_download.assert_not_called()

    async def test_mcp_unavailable_falls_through_to_download(self):
        from app.services.skill_consumption_service import get_skill_content_for_session

        user_id = await _seed_user()
        hcp_id = await _seed_hcp_profile(user_id)
        skill_id = await _seed_skill(
            user_id,
            foundry_sync_status="synced",
            foundry_skill_name="download-skill-abcd1234",
            foundry_cloud_version="1",
        )
        scenario_id = await _seed_scenario(user_id, hcp_id, skill_id)

        downloaded_content = SkillContent(
            name="Cloud",
            description="",
            content="downloaded body",
            version_id="1",
            token_estimate=1,
        )

        async with TestSessionLocal() as session:
            with (
                patch(
                    "app.services.skill_consumption_service.mount_skill_toolbox",
                    new=AsyncMock(return_value="toolbox-name"),
                ),
                patch(
                    "app.services.skill_consumption_service._try_mcp_fetch",
                    new=AsyncMock(return_value=None),
                ),
                patch(
                    "app.services.skill_consumption_service.download_and_extract_skill_content",
                    new=AsyncMock(return_value=downloaded_content),
                ),
            ):
                result = await get_skill_content_for_session(session, scenario_id)

        assert result is downloaded_content

    async def test_both_mcp_and_download_fail_falls_back_to_local_d06(self):
        from app.services.skill_consumption_service import get_skill_content_for_session

        user_id = await _seed_user()
        hcp_id = await _seed_hcp_profile(user_id)
        skill_id = await _seed_skill(
            user_id,
            foundry_sync_status="synced",
            foundry_skill_name="fail-skill-abcd1234",
            foundry_cloud_version="1",
        )
        scenario_id = await _seed_scenario(user_id, hcp_id, skill_id)

        local_content = SkillContent(
            name="Local", description="", content="local fallback", version_id="", token_estimate=1
        )

        async with TestSessionLocal() as session:
            with (
                patch(
                    "app.services.skill_consumption_service.mount_skill_toolbox",
                    new=AsyncMock(return_value="toolbox-name"),
                ),
                patch(
                    "app.services.skill_consumption_service._try_mcp_fetch",
                    new=AsyncMock(return_value=None),
                ),
                patch(
                    "app.services.skill_consumption_service.download_and_extract_skill_content",
                    new=AsyncMock(return_value=None),
                ),
                patch(
                    "app.services.skill_consumption_service.load_skill_for_scenario",
                    new=AsyncMock(return_value=local_content),
                ),
            ):
                result = await get_skill_content_for_session(session, scenario_id)

        assert result is local_content

    async def test_cloud_chain_exception_falls_back_to_local_never_raises(self):
        from app.services.skill_consumption_service import get_skill_content_for_session

        user_id = await _seed_user()
        hcp_id = await _seed_hcp_profile(user_id)
        skill_id = await _seed_skill(
            user_id,
            foundry_sync_status="synced",
            foundry_skill_name="explode-skill-abcd1234",
            foundry_cloud_version="1",
        )
        scenario_id = await _seed_scenario(user_id, hcp_id, skill_id)

        local_content = SkillContent(
            name="Local", description="", content="local fallback", version_id="", token_estimate=1
        )

        async with TestSessionLocal() as session:
            with (
                patch(
                    "app.services.skill_consumption_service.mount_skill_toolbox",
                    new=AsyncMock(side_effect=RuntimeError("unexpected")),
                ),
                patch(
                    "app.services.skill_consumption_service.load_skill_for_scenario",
                    new=AsyncMock(return_value=local_content),
                ),
            ):
                result = await get_skill_content_for_session(session, scenario_id)  # must not raise

        assert result is local_content

    async def test_cache_hit_calls_cloud_chain_only_once_high1(self):
        from app.services.skill_consumption_service import get_skill_content_for_session

        user_id = await _seed_user()
        hcp_id = await _seed_hcp_profile(user_id)
        skill_id = await _seed_skill(
            user_id,
            foundry_sync_status="synced",
            foundry_skill_name="cached-skill-abcd1234",
            foundry_cloud_version="1",
        )
        scenario_id = await _seed_scenario(user_id, hcp_id, skill_id)

        async with TestSessionLocal() as session:
            with (
                patch(
                    "app.services.skill_consumption_service.mount_skill_toolbox",
                    new=AsyncMock(return_value="toolbox-name"),
                ) as mock_mount,
                patch(
                    "app.services.skill_consumption_service._try_mcp_fetch",
                    new=AsyncMock(return_value="MCP body"),
                ) as mock_mcp,
            ):
                result1 = await get_skill_content_for_session(session, scenario_id)
                result2 = await get_skill_content_for_session(session, scenario_id)

        assert result1 is not None
        assert result2 is not None
        assert result1.content == result2.content
        mock_mount.assert_called_once()
        mock_mcp.assert_called_once()

    async def test_cache_miss_after_version_change(self):
        """Cache key includes foundry_cloud_version -- a re-sync (version bump)
        must not reuse the stale cache entry."""
        from app.services.skill_consumption_service import get_skill_content_for_session

        user_id = await _seed_user()
        hcp_id = await _seed_hcp_profile(user_id)
        skill_id = await _seed_skill(
            user_id,
            foundry_sync_status="synced",
            foundry_skill_name="version-bump-skill-abcd1234",
            foundry_cloud_version="1",
        )
        scenario_id = await _seed_scenario(user_id, hcp_id, skill_id)

        with (
            patch(
                "app.services.skill_consumption_service.mount_skill_toolbox",
                new=AsyncMock(return_value="toolbox-name"),
            ),
            patch(
                "app.services.skill_consumption_service._try_mcp_fetch",
                new=AsyncMock(return_value="MCP body v1"),
            ),
        ):
            async with TestSessionLocal() as session:
                await get_skill_content_for_session(session, scenario_id)

        # Simulate a re-sync bumping the cloud version.
        from sqlalchemy import select as sa_select

        async with TestSessionLocal() as session:
            row = (await session.execute(sa_select(Skill).where(Skill.id == skill_id))).scalar_one()
            row.foundry_cloud_version = "2"
            await session.commit()

        with (
            patch(
                "app.services.skill_consumption_service.mount_skill_toolbox",
                new=AsyncMock(return_value="toolbox-name"),
            ) as mock_mount_2,
            patch(
                "app.services.skill_consumption_service._try_mcp_fetch",
                new=AsyncMock(return_value="MCP body v2"),
            ),
        ):
            async with TestSessionLocal() as session:
                result = await get_skill_content_for_session(session, scenario_id)

        assert result.content == "MCP body v2"
        mock_mount_2.assert_called_once()  # re-ran the cloud chain, did not reuse v1's cache entry


# ---------------------------------------------------------------------------
# _cache_get / _cache_set TTL expiry
# ---------------------------------------------------------------------------


class TestContentCacheTTL:
    def test_expired_entry_reports_miss(self):
        from app.services.skill_consumption_service import (
            _CACHE_MISS,
            _cache_get,
            _cache_set,
        )

        key = ("skill-1", "1")
        _cache_set(key, SkillContent("N", "D", "C", "v", 1))

        with patch(
            "app.services.skill_consumption_service.time.monotonic",
            return_value=time.monotonic() + 100000,
        ):
            result = _cache_get(key)

        assert result is _CACHE_MISS

    def test_fresh_entry_is_returned(self):
        from app.services.skill_consumption_service import _CACHE_MISS, _cache_get, _cache_set

        key = ("skill-2", "1")
        content = SkillContent("N", "D", "C", "v", 1)
        _cache_set(key, content)

        result = _cache_get(key)
        assert result is content
        assert result is not _CACHE_MISS

    def test_cache_miss_key_not_present(self):
        from app.services.skill_consumption_service import _CACHE_MISS, _cache_get

        result = _cache_get(("nonexistent", "0"))
        assert result is _CACHE_MISS


# ---------------------------------------------------------------------------
# _scenario_pin_is_stale
# ---------------------------------------------------------------------------


class TestScenarioPinIsStale:
    def test_no_pin_returns_false(self):
        from app.services.skill_consumption_service import _scenario_pin_is_stale

        scenario = Scenario(skill_version_id=None)
        assert _scenario_pin_is_stale(scenario) is False

    def test_pin_set_returns_true(self):
        from app.services.skill_consumption_service import _scenario_pin_is_stale

        scenario = Scenario(skill_version_id="some-version-id")
        assert _scenario_pin_is_stale(scenario) is True
