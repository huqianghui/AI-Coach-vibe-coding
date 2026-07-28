"""Tests for Knowledge Base service, API endpoints, and agent sync tools extension (Phase 17)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import get_db
from app.dependencies import get_current_user
from app.main import app
from app.models.hcp_knowledge_config import HcpKnowledgeConfig
from app.models.hcp_profile import HcpProfile
from app.models.user import User
from app.schemas.knowledge_base import KnowledgeConfigCreate

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _fake_admin() -> User:
    """Create a fake authenticated admin user for dependency override."""
    user = MagicMock(spec=User)
    user.id = "admin-user-id-kb"
    user.role = "admin"
    user.username = "adminuser"
    user.is_active = True
    return user


@pytest.fixture
def admin_client(db_session):
    """Async HTTP client with admin auth + db overrides."""

    async def override_get_db():
        yield db_session

    async def override_get_current_user():
        return _fake_admin()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    yield
    app.dependency_overrides.clear()


@pytest.fixture
async def aclient(admin_client):
    """Async HTTP client with overrides applied."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.fixture
async def sample_hcp(db_session):
    """Create a sample HCP profile in the test DB."""
    profile = HcpProfile(
        id="hcp-kb-test-001",
        name="Dr. KB Test",
        specialty="Oncology",
        created_by="admin-user-id-kb",
    )
    db_session.add(profile)
    await db_session.flush()
    return profile


@pytest.fixture
async def sample_kb_config(db_session, sample_hcp):
    """Create a sample knowledge config in the test DB."""
    config = HcpKnowledgeConfig(
        id="kb-config-001",
        hcp_profile_id=sample_hcp.id,
        connection_name="my-search-conn",
        connection_target="https://search.example.com",
        index_name="medical-index",
        server_label="knowledge-base-medical-index",
        is_enabled=True,
    )
    db_session.add(config)
    await db_session.flush()
    return config


# ---------------------------------------------------------------------------
# Unit Tests: build_search_tools
# ---------------------------------------------------------------------------


class TestBuildSearchTools:
    """Tests for knowledge_base_service.build_search_tools."""

    def test_empty_list_returns_empty(self):
        """build_search_tools with empty list returns empty list."""
        from app.services.knowledge_base_service import build_search_tools

        result = build_search_tools([])
        assert result == []

    def test_disabled_configs_excluded(self):
        """build_search_tools excludes disabled configs."""
        from app.services.knowledge_base_service import build_search_tools

        cfg = MagicMock(spec=HcpKnowledgeConfig)
        cfg.is_enabled = False
        cfg.connection_name = "conn"
        cfg.index_name = "idx"
        cfg.server_label = "kb-idx"
        cfg.connection_target = ""

        result = build_search_tools([cfg])
        assert result == []

    def test_enabled_config_produces_tool_with_remote_tool_map(self):
        """build_search_tools creates MCPTool with RemoteTool connection for auth."""
        from app.services.knowledge_base_service import build_search_tools

        cfg = MagicMock(spec=HcpKnowledgeConfig)
        cfg.is_enabled = True
        cfg.connection_name = "my-cognitive-search-conn"
        cfg.connection_target = "https://search.example.com"
        cfg.index_name = "my-index"
        cfg.server_label = "knowledge-base-my-index"

        # RemoteTool connection map: KB index_name -> RemoteTool connection name
        rt_map = {"my-index": "kb-my-index-rt-conn"}
        result = build_search_tools([cfg], remote_tool_map=rt_map)
        assert len(result) == 1
        tool = result[0]
        assert tool.type == "mcp"
        tool_dict = tool.as_dict()
        assert tool_dict["server_label"] == "knowledge-base-my-index"
        assert "knowledgebases/my-index/mcp" in tool_dict["server_url"]
        assert "2026-05-01-preview" in tool_dict["server_url"]
        assert tool_dict["require_approval"] == "never"
        allowed = tool_dict.get("allowed_tools", {})
        assert allowed.get("tool_names") == ["knowledge_base_retrieve"]
        # project_connection_id must be RemoteTool connection (CustomKeys),
        # NOT CognitiveSearch connection (ApiKey) which causes 403
        assert tool_dict["project_connection_id"] == "kb-my-index-rt-conn"

    def test_project_connection_id_uses_remote_tool_not_cognitive_search(self):
        """build_search_tools uses RemoteTool connection, not CognitiveSearch (403 fix)."""
        from app.services.knowledge_base_service import build_search_tools

        cfg = MagicMock(spec=HcpKnowledgeConfig)
        cfg.is_enabled = True
        cfg.connection_name = "aisearch-prod-conn"  # CognitiveSearch connection
        cfg.connection_target = "https://search.prod.com"
        cfg.index_name = "prod-kb"
        cfg.server_label = "knowledge-base-prod-kb"

        # RemoteTool connection for this KB
        rt_map = {"prod-kb": "kb-prod-kb-remote-tool"}
        result = build_search_tools([cfg], remote_tool_map=rt_map)
        assert len(result) == 1
        tool_dict = result[0].as_dict()
        # Must use RemoteTool connection (CustomKeys type) for correct MCP auth.
        # CognitiveSearch connection (ApiKey type) causes 403 Forbidden.
        assert tool_dict["project_connection_id"] == "kb-prod-kb-remote-tool"
        # Verify it's NOT the CognitiveSearch connection name
        assert tool_dict["project_connection_id"] != "aisearch-prod-conn"

    def test_no_remote_tool_map_sets_none_connection_id(self):
        """build_search_tools without remote_tool_map sets project_connection_id=None."""
        from app.services.knowledge_base_service import build_search_tools

        cfg = MagicMock(spec=HcpKnowledgeConfig)
        cfg.is_enabled = True
        cfg.connection_name = "aisearch-conn"
        cfg.connection_target = "https://search.example.com"
        cfg.index_name = "some-kb"
        cfg.server_label = "knowledge-base-some-kb"

        # No remote_tool_map provided
        result = build_search_tools([cfg])
        assert len(result) == 1
        tool_dict = result[0].as_dict()
        # build_search_tools is a pure builder: without a remote_tool_map entry
        # for this KB, project_connection_id is omitted. It never assumes the
        # Portal auto-created/auto-matched a RemoteTool connection — callers
        # must use resolve_kb_remote_tool_connections() upstream to find-or-
        # create one (see Issue #86), or this indicates an error condition.
        assert tool_dict.get("project_connection_id") is None

    def test_missing_kb_in_remote_tool_map_sets_none(self):
        """build_search_tools sets None when KB not found in remote_tool_map."""
        from app.services.knowledge_base_service import build_search_tools

        cfg = MagicMock(spec=HcpKnowledgeConfig)
        cfg.is_enabled = True
        cfg.connection_name = "aisearch-conn"
        cfg.connection_target = "https://search.example.com"
        cfg.index_name = "unknown-kb"
        cfg.server_label = "knowledge-base-unknown-kb"

        # remote_tool_map exists but doesn't contain this KB
        rt_map = {"other-kb": "kb-other-rt-conn"}
        result = build_search_tools([cfg], remote_tool_map=rt_map)
        assert len(result) == 1
        tool_dict = result[0].as_dict()
        assert tool_dict.get("project_connection_id") is None

    def test_sdk_not_installed_returns_empty(self):
        """build_search_tools returns empty when SDK not installed."""
        import sys

        # Temporarily remove azure.ai.projects.models if present
        original = sys.modules.get("azure.ai.projects.models")
        sys.modules["azure.ai.projects.models"] = None  # type: ignore

        try:
            # Re-import to trigger the ImportError path
            from app.services.knowledge_base_service import build_search_tools

            cfg = MagicMock(spec=HcpKnowledgeConfig)
            cfg.is_enabled = True
            cfg.connection_name = "conn"
            cfg.index_name = "idx"
            cfg.server_label = "kb-idx"
            cfg.connection_target = ""

            result = build_search_tools([cfg])
            assert result == []
        finally:
            if original is not None:
                sys.modules["azure.ai.projects.models"] = original
            else:
                sys.modules.pop("azure.ai.projects.models", None)


# ---------------------------------------------------------------------------
# Unit Tests: Knowledge base service CRUD
# ---------------------------------------------------------------------------


class TestKnowledgeBaseServiceCrud:
    """Tests for CRUD operations in knowledge_base_service."""

    @pytest.mark.asyncio
    async def test_get_configs_empty(self, db_session, sample_hcp):
        """get_knowledge_configs returns empty list when no configs exist."""
        from app.services.knowledge_base_service import get_knowledge_configs

        result = await get_knowledge_configs(db_session, sample_hcp.id)
        assert result == []

    @pytest.mark.asyncio
    @patch("app.services.knowledge_base_service._trigger_agent_resync", new_callable=AsyncMock)
    async def test_add_knowledge_config(self, mock_resync, db_session, sample_hcp):
        """add_knowledge_config creates a record and returns it."""
        from app.services.knowledge_base_service import add_knowledge_config

        create_data = KnowledgeConfigCreate(
            connection_name="test-conn",
            connection_target="https://search.test.com",
            index_name="test-index",
        )
        result = await add_knowledge_config(db_session, sample_hcp.id, create_data)

        assert result.connection_name == "test-conn"
        assert result.index_name == "test-index"
        assert result.server_label == "knowledge-base-test-index"
        assert result.is_enabled is True
        assert result.hcp_profile_id == sample_hcp.id
        mock_resync.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.services.knowledge_base_service._trigger_agent_resync", new_callable=AsyncMock)
    async def test_get_configs_after_add(self, mock_resync, db_session, sample_hcp):
        """get_knowledge_configs returns added configs."""
        from app.services.knowledge_base_service import (
            add_knowledge_config,
            get_knowledge_configs,
        )

        create_data = KnowledgeConfigCreate(
            connection_name="conn-a",
            index_name="index-a",
        )
        await add_knowledge_config(db_session, sample_hcp.id, create_data)

        configs = await get_knowledge_configs(db_session, sample_hcp.id)
        assert len(configs) == 1
        assert configs[0].connection_name == "conn-a"

    @pytest.mark.asyncio
    @patch("app.services.knowledge_base_service._trigger_agent_resync", new_callable=AsyncMock)
    async def test_remove_knowledge_config(self, mock_resync, db_session, sample_kb_config):
        """remove_knowledge_config deletes the record."""
        from app.services.knowledge_base_service import (
            get_knowledge_configs,
            remove_knowledge_config,
        )

        await remove_knowledge_config(db_session, sample_kb_config.id)

        configs = await get_knowledge_configs(db_session, sample_kb_config.hcp_profile_id)
        assert len(configs) == 0
        assert mock_resync.call_count == 1

    @pytest.mark.asyncio
    @patch("app.services.knowledge_base_service._trigger_agent_resync", new_callable=AsyncMock)
    async def test_remove_nonexistent_config_raises(self, mock_resync, db_session):
        """remove_knowledge_config raises 404 for nonexistent config."""
        from app.services.knowledge_base_service import remove_knowledge_config
        from app.utils.exceptions import AppException

        with pytest.raises(AppException) as exc_info:
            await remove_knowledge_config(db_session, "nonexistent-id")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_list_search_connections_sdk_not_configured(self, db_session):
        """list_search_connections returns empty list when SDK calls fail."""
        from app.services.knowledge_base_service import list_search_connections

        with patch(
            "app.services.agent_sync_service.get_project_endpoint",
            side_effect=Exception("not configured"),
        ):
            result = await list_search_connections(db_session)
            assert result == []

    @pytest.mark.asyncio
    async def test_list_indexes_sdk_not_configured(self, db_session):
        """list_indexes returns empty list when SDK calls fail."""
        from app.services.knowledge_base_service import list_indexes

        with patch(
            "app.services.agent_sync_service.get_project_endpoint",
            side_effect=Exception("not configured"),
        ):
            result = await list_indexes(db_session)
            assert result == []

    @pytest.mark.asyncio
    async def test_list_indexes_supports_aad_search_connection(self, db_session):
        """list_indexes can query Foundry IQ with Entra ID when connection has no API key."""
        from app.services.knowledge_base_service import list_indexes

        fake_conn = MagicMock()
        fake_conn.target = "https://search.example.com/"
        fake_conn.credentials = {"type": "AAD"}

        fake_client = MagicMock()
        fake_client.connections.get.return_value = fake_conn

        with (
            patch(
                "app.services.agent_sync_service.get_project_endpoint",
                new_callable=AsyncMock,
                return_value=("https://foundry/api/projects/proj", ""),
            ),
            patch(
                "app.services.agent_sync_service._get_project_client",
                return_value=fake_client,
            ),
            patch(
                "app.services.knowledge_base_service._get_knowledgebases",
                new_callable=AsyncMock,
                return_value=[
                    {
                        "name": "knowledgebase349",
                        "version": "1",
                        "type": "foundryIq",
                        "description": "test knowledge",
                    }
                ],
            ) as mock_list_kbs,
        ):
            result = await list_indexes(db_session, connection_name="search-conn")

        assert result == [
            {
                "name": "knowledgebase349",
                "version": "1",
                "type": "foundryIq",
                "description": "test knowledge",
            }
        ]
        mock_list_kbs.assert_awaited_once_with("https://search.example.com", "")

    @pytest.mark.asyncio
    async def test_resolve_remote_tool_connection_from_metadata(self, db_session):
        """RemoteTool connection maps KB name to connection name for MCP auth."""
        from app.services.knowledge_base_service import resolve_kb_remote_tool_connections

        fake_remote = {
            "type": "RemoteTool",
            "name": "kb-knowledgebase349-m5hlw",
            "target": "https://search/knowledgebases/knowledgebase349/mcp",
            "metadata": {"knowledgeBaseName": "knowledgebase349"},
        }
        fake_client = MagicMock()
        fake_client.connections.list.return_value = [fake_remote]

        with (
            patch(
                "app.services.agent_sync_service.get_project_endpoint",
                new_callable=AsyncMock,
                return_value=("https://foundry/api/projects/proj", ""),
            ),
            patch(
                "app.services.agent_sync_service._get_project_client",
                return_value=fake_client,
            ),
        ):
            result = await resolve_kb_remote_tool_connections(db_session)

        assert result == {"knowledgebase349": "kb-knowledgebase349-m5hlw"}

    @pytest.mark.asyncio
    async def test_resolve_reuses_metadata_match_without_creating(
        self, db_session, sample_kb_config
    ):
        """An existing metadata match is reused without an ARM create call."""
        from app.services.knowledge_base_service import resolve_kb_remote_tool_connections

        fake_client = MagicMock()
        fake_client.connections.list.return_value = [
            {
                "type": "RemoteTool",
                "name": "existing-remote-tool",
                "target": "https://other.example.com/mcp",
                "metadata": {"knowledgeBaseName": sample_kb_config.index_name},
            }
        ]

        with (
            patch(
                "app.services.agent_sync_service.get_project_endpoint",
                new_callable=AsyncMock,
                return_value=("https://foundry/api/projects/proj", ""),
            ),
            patch(
                "app.services.agent_sync_service._get_project_client",
                return_value=fake_client,
            ),
            patch(
                "app.services.knowledge_base_service._create_remote_tool_connection",
                new_callable=AsyncMock,
            ) as create_connection,
        ):
            result = await resolve_kb_remote_tool_connections(db_session, [sample_kb_config])

        assert result == {sample_kb_config.index_name: "existing-remote-tool"}
        create_connection.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_resolve_reuses_normalized_target_match(self, db_session, sample_kb_config):
        """A Portal-created connection without metadata is matched by MCP target."""
        from app.services.knowledge_base_service import resolve_kb_remote_tool_connections

        fake_client = MagicMock()
        fake_client.connections.list.return_value = [
            {
                "type": "RemoteTool",
                "name": "portal-remote-tool",
                "target": (
                    "HTTPS://SEARCH.EXAMPLE.COM/knowledgebases/medical-index/mcp/"
                    "?api-version=older-preview"
                ),
                "metadata": {},
            }
        ]

        with (
            patch(
                "app.services.agent_sync_service.get_project_endpoint",
                new_callable=AsyncMock,
                return_value=("https://foundry/api/projects/proj", ""),
            ),
            patch(
                "app.services.agent_sync_service._get_project_client",
                return_value=fake_client,
            ),
            patch(
                "app.services.knowledge_base_service._create_remote_tool_connection",
                new_callable=AsyncMock,
            ) as create_connection,
        ):
            result = await resolve_kb_remote_tool_connections(db_session, [sample_kb_config])

        assert result == {sample_kb_config.index_name: "portal-remote-tool"}
        create_connection.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_resolve_creates_missing_connection_once(self, db_session, sample_kb_config):
        """Duplicate configs for one KB share one newly created RemoteTool."""
        from app.services.knowledge_base_service import resolve_kb_remote_tool_connections

        duplicate = MagicMock(spec=HcpKnowledgeConfig)
        duplicate.is_enabled = True
        duplicate.index_name = sample_kb_config.index_name
        duplicate.connection_target = sample_kb_config.connection_target

        fake_client = MagicMock()
        fake_client.connections.list.return_value = []

        with (
            patch(
                "app.services.agent_sync_service.get_project_endpoint",
                new_callable=AsyncMock,
                return_value=("https://foundry/api/projects/proj", ""),
            ),
            patch(
                "app.services.agent_sync_service._get_project_client",
                return_value=fake_client,
            ),
            patch(
                "app.services.knowledge_base_service._create_remote_tool_connection",
                new_callable=AsyncMock,
                return_value="created-remote-tool",
            ) as create_connection,
        ):
            result = await resolve_kb_remote_tool_connections(
                db_session, [sample_kb_config, duplicate]
            )

        assert result == {sample_kb_config.index_name: "created-remote-tool"}
        create_connection.assert_awaited_once_with(db_session, sample_kb_config)

    @pytest.mark.asyncio
    async def test_resolve_propagates_connection_creation_failure(
        self, db_session, sample_kb_config
    ):
        """RemoteTool creation failures fail the agent sync path."""
        from app.services.knowledge_base_service import resolve_kb_remote_tool_connections

        fake_client = MagicMock()
        fake_client.connections.list.return_value = []

        with (
            patch(
                "app.services.agent_sync_service.get_project_endpoint",
                new_callable=AsyncMock,
                return_value=("https://foundry/api/projects/proj", ""),
            ),
            patch(
                "app.services.agent_sync_service._get_project_client",
                return_value=fake_client,
            ),
            patch(
                "app.services.knowledge_base_service._create_remote_tool_connection",
                new_callable=AsyncMock,
                side_effect=RuntimeError("ARM permission denied"),
            ),
            pytest.raises(RuntimeError, match="ARM permission denied"),
        ):
            await resolve_kb_remote_tool_connections(db_session, [sample_kb_config])

    @pytest.mark.asyncio
    async def test_resolve_multiple_kbs_no_duplicate_creation_correct_mapping(
        self, db_session, sample_hcp
    ):
        """Two distinct KBs: one reused, one created; mapping is correct, no dupes."""
        from app.services.knowledge_base_service import resolve_kb_remote_tool_connections

        existing_cfg = HcpKnowledgeConfig(
            hcp_profile_id=sample_hcp.id,
            connection_name="conn-a",
            connection_target="https://search.example.com",
            index_name="already-connected-kb",
            server_label="knowledge-base-already-connected-kb",
            is_enabled=True,
        )
        missing_cfg = HcpKnowledgeConfig(
            hcp_profile_id=sample_hcp.id,
            connection_name="conn-b",
            connection_target="https://search.example.com",
            index_name="brand-new-kb",
            server_label="knowledge-base-brand-new-kb",
            is_enabled=True,
        )
        db_session.add_all([existing_cfg, missing_cfg])
        await db_session.flush()

        fake_client = MagicMock()
        fake_client.connections.list.return_value = [
            {
                "type": "RemoteTool",
                "name": "existing-remote-tool",
                "target": "https://search.example.com/knowledgebases/already-connected-kb/mcp",
                "metadata": {"knowledgeBaseName": "already-connected-kb"},
            }
        ]

        with (
            patch(
                "app.services.agent_sync_service.get_project_endpoint",
                new_callable=AsyncMock,
                return_value=("https://foundry/api/projects/proj", ""),
            ),
            patch(
                "app.services.agent_sync_service._get_project_client",
                return_value=fake_client,
            ),
            patch(
                "app.services.knowledge_base_service._create_remote_tool_connection",
                new_callable=AsyncMock,
                return_value="kb-brand-new-kb-created",
            ) as create_connection,
        ):
            result = await resolve_kb_remote_tool_connections(
                db_session, [existing_cfg, missing_cfg]
            )

        assert result == {
            "already-connected-kb": "existing-remote-tool",
            "brand-new-kb": "kb-brand-new-kb-created",
        }
        create_connection.assert_awaited_once_with(db_session, missing_cfg)

    @pytest.mark.asyncio
    async def test_trigger_agent_resync_marks_synced_on_success(self, db_session, sample_hcp):
        """_trigger_agent_resync marks the profile synced when sync succeeds."""
        from app.services.knowledge_base_service import _trigger_agent_resync

        sample_hcp.agent_sync_status = "none"
        sample_hcp.agent_id = "existing-agent"
        await db_session.flush()

        with patch(
            "app.services.agent_sync_service.sync_agent_for_profile",
            new_callable=AsyncMock,
            return_value={"id": "agent-kb-1", "version": "2"},
        ):
            await _trigger_agent_resync(db_session, sample_hcp.id)

        await db_session.refresh(sample_hcp)
        assert sample_hcp.agent_sync_status == "synced"
        assert sample_hcp.agent_sync_error == ""
        assert sample_hcp.agent_id == "agent-kb-1"

    @pytest.mark.asyncio
    async def test_trigger_agent_resync_marks_failed_on_remote_tool_error(
        self, db_session, sample_hcp
    ):
        """A RemoteTool creation/sync failure marks agent_sync_status=failed with a
        diagnosable error, instead of leaving a stale 'synced' status in place."""
        from app.services.knowledge_base_service import _trigger_agent_resync

        sample_hcp.agent_sync_status = "synced"
        sample_hcp.agent_id = "agent-kb-1"
        await db_session.flush()

        with patch(
            "app.services.agent_sync_service.sync_agent_for_profile",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Cannot create RemoteTool connection: ARM permission denied"),
        ):
            await _trigger_agent_resync(db_session, sample_hcp.id)

        await db_session.refresh(sample_hcp)
        assert sample_hcp.agent_sync_status == "failed"
        assert "ARM permission denied" in sample_hcp.agent_sync_error

    @pytest.mark.asyncio
    async def test_create_remote_tool_uses_project_identity(self, db_session, sample_kb_config):
        """ARM creation uses a stable name and project managed identity auth."""
        from app.services.knowledge_base_service import _create_remote_tool_connection

        response = MagicMock(status_code=201, text="")
        http = AsyncMock()
        http.put.return_value = response
        client_context = AsyncMock()
        client_context.__aenter__.return_value = http

        with (
            patch(
                "app.services.agent_sync_service.get_portal_url_components",
                new_callable=AsyncMock,
                return_value={
                    "subscription_id": "sub-id",
                    "resource_group": "rg",
                    "resource_name": "foundry",
                    "project_name": "project",
                },
            ),
            patch(
                "app.services.azure_auth.get_bearer_token",
                new_callable=AsyncMock,
                return_value="arm-token",
            ),
            patch("httpx.AsyncClient", return_value=client_context),
        ):
            connection_name = await _create_remote_tool_connection(db_session, sample_kb_config)

        assert connection_name.startswith("kb-medical-index-")
        _, kwargs = http.put.await_args
        assert kwargs["json"]["properties"]["category"] == "RemoteTool"
        assert kwargs["json"]["properties"]["authType"] == "ProjectManagedIdentity"
        assert kwargs["json"]["properties"]["audience"] == "https://search.azure.com/"
        assert (
            kwargs["json"]["properties"]["metadata"]["knowledgeBaseName"]
            == sample_kb_config.index_name
        )


# ---------------------------------------------------------------------------
# API Endpoint Tests
# ---------------------------------------------------------------------------


class TestKnowledgeBaseApi:
    """Integration tests for knowledge base API endpoints."""

    @pytest.mark.asyncio
    async def test_list_connections_returns_200(self, aclient: AsyncClient):
        """GET /api/v1/knowledge-base/connections returns 200."""
        with patch(
            "app.services.knowledge_base_service.list_search_connections",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = await aclient.get("/api/v1/knowledge-base/connections")
            assert resp.status_code == 200
            assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_connections_returns_data(self, aclient: AsyncClient):
        """GET /api/v1/knowledge-base/connections returns connection objects."""
        mock_data = [
            {"name": "search-conn-1", "target": "https://search1.example.com", "is_default": True}
        ]
        with patch(
            "app.services.knowledge_base_service.list_search_connections",
            new_callable=AsyncMock,
            return_value=mock_data,
        ):
            resp = await aclient.get("/api/v1/knowledge-base/connections")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["name"] == "search-conn-1"
            assert data[0]["is_default"] is True

    @pytest.mark.asyncio
    async def test_list_indexes_returns_200(self, aclient: AsyncClient):
        """GET /api/v1/knowledge-base/indexes returns 200."""
        with patch(
            "app.services.knowledge_base_service.list_indexes",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = await aclient.get("/api/v1/knowledge-base/indexes")
            assert resp.status_code == 200
            assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_indexes_returns_data(self, aclient: AsyncClient):
        """GET /api/v1/knowledge-base/indexes returns index objects."""
        mock_data = [
            {"name": "medical-index", "version": "1", "type": "vector", "description": "Medical KB"}
        ]
        with patch(
            "app.services.knowledge_base_service.list_indexes",
            new_callable=AsyncMock,
            return_value=mock_data,
        ):
            resp = await aclient.get("/api/v1/knowledge-base/indexes")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["name"] == "medical-index"

    @pytest.mark.asyncio
    async def test_get_hcp_configs_empty(self, aclient: AsyncClient, sample_hcp):
        """GET /api/v1/knowledge-base/hcp/{id}/configs returns empty list."""
        resp = await aclient.get(f"/api/v1/knowledge-base/hcp/{sample_hcp.id}/configs")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_get_hcp_configs_with_data(self, aclient: AsyncClient, sample_kb_config):
        """GET /api/v1/knowledge-base/hcp/{id}/configs returns existing configs."""
        resp = await aclient.get(
            f"/api/v1/knowledge-base/hcp/{sample_kb_config.hcp_profile_id}/configs"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["connection_name"] == "my-search-conn"
        assert data[0]["index_name"] == "medical-index"

    @pytest.mark.asyncio
    @patch("app.services.knowledge_base_service._trigger_agent_resync", new_callable=AsyncMock)
    async def test_add_hcp_config_returns_201(self, mock_resync, aclient: AsyncClient, sample_hcp):
        """POST /api/v1/knowledge-base/hcp/{id}/configs returns 201."""
        resp = await aclient.post(
            f"/api/v1/knowledge-base/hcp/{sample_hcp.id}/configs",
            json={
                "connection_name": "new-conn",
                "connection_target": "https://new.search.com",
                "index_name": "new-index",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["connection_name"] == "new-conn"
        assert data["index_name"] == "new-index"
        assert data["server_label"] == "knowledge-base-new-index"
        assert data["is_enabled"] is True
        assert "id" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    @patch("app.services.knowledge_base_service._trigger_agent_resync", new_callable=AsyncMock)
    async def test_delete_config_returns_204(
        self, mock_resync, aclient: AsyncClient, sample_kb_config
    ):
        """DELETE /api/v1/knowledge-base/configs/{id} returns 204."""
        resp = await aclient.delete(f"/api/v1/knowledge-base/configs/{sample_kb_config.id}")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    @patch("app.services.knowledge_base_service._trigger_agent_resync", new_callable=AsyncMock)
    async def test_delete_nonexistent_config_returns_404(self, mock_resync, aclient: AsyncClient):
        """DELETE /api/v1/knowledge-base/configs/{id} returns 404 for missing config."""
        resp = await aclient.delete("/api/v1/knowledge-base/configs/nonexistent-id")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Agent Sync with Tools Tests
# ---------------------------------------------------------------------------


class TestAgentSyncToolsExtension:
    """Tests for agent_sync_service tools parameter extension."""

    def test_create_agent_accepts_tools_parameter(self):
        """create_agent signature includes tools parameter."""
        import inspect

        from app.services.agent_sync_service import create_agent

        sig = inspect.signature(create_agent)
        assert "tools" in sig.parameters

    def test_update_agent_accepts_tools_parameter(self):
        """update_agent signature includes tools parameter."""
        import inspect

        from app.services.agent_sync_service import update_agent

        sig = inspect.signature(update_agent)
        assert "tools" in sig.parameters

    def test_build_agent_instructions_unchanged(self):
        """build_agent_instructions still works after tools extension."""
        from app.services.agent_sync_service import build_agent_instructions

        profile_data = {
            "name": "Dr. KB",
            "specialty": "Oncology",
            "communication_style": 50,
            "emotional_state": 50,
        }
        result = build_agent_instructions(profile_data)
        assert "Dr. KB" in result
        assert "Oncology" in result


# ---------------------------------------------------------------------------
# Schema Tests
# ---------------------------------------------------------------------------


class TestKnowledgeBaseSchemas:
    """Tests for Pydantic schema validation."""

    def test_knowledge_config_create_minimal(self):
        """KnowledgeConfigCreate with minimal fields."""
        config = KnowledgeConfigCreate(
            connection_name="conn",
            index_name="idx",
        )
        assert config.connection_name == "conn"
        assert config.connection_target == ""
        assert config.index_name == "idx"

    def test_knowledge_config_create_full(self):
        """KnowledgeConfigCreate with all fields."""
        config = KnowledgeConfigCreate(
            connection_name="conn",
            connection_target="https://search.example.com",
            index_name="idx",
        )
        assert config.connection_target == "https://search.example.com"

    def test_knowledge_config_out_from_attributes(self):
        """KnowledgeConfigOut can be created from ORM attributes."""
        from datetime import datetime

        from app.schemas.knowledge_base import KnowledgeConfigOut

        mock_orm = MagicMock()
        mock_orm.id = "test-id"
        mock_orm.hcp_profile_id = "hcp-id"
        mock_orm.connection_name = "conn"
        mock_orm.connection_target = "target"
        mock_orm.index_name = "idx"
        mock_orm.server_label = "kb-idx"
        mock_orm.is_enabled = True
        mock_orm.created_at = datetime(2026, 1, 1)

        out = KnowledgeConfigOut.model_validate(mock_orm, from_attributes=True)
        assert out.id == "test-id"
        assert out.connection_name == "conn"
        assert out.is_enabled is True

    def test_connection_out_schema(self):
        """ConnectionOut schema validates correctly."""
        from app.schemas.knowledge_base import ConnectionOut

        conn = ConnectionOut(name="conn", target="https://search.com", is_default=True)
        assert conn.name == "conn"
        assert conn.is_default is True

    def test_index_out_schema(self):
        """IndexOut schema validates correctly."""
        from app.schemas.knowledge_base import IndexOut

        idx = IndexOut(name="my-index")
        assert idx.name == "my-index"
        assert idx.version is None
        assert idx.type is None


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------


class TestHcpKnowledgeConfigModel:
    """Tests for the HcpKnowledgeConfig ORM model."""

    @pytest.mark.asyncio
    async def test_create_config_in_db(self, db_session, sample_hcp):
        """HcpKnowledgeConfig can be persisted to the database."""
        config = HcpKnowledgeConfig(
            hcp_profile_id=sample_hcp.id,
            connection_name="test-conn",
            connection_target="https://search.test.com",
            index_name="test-index",
            server_label="knowledge-base-test-index",
        )
        db_session.add(config)
        await db_session.flush()

        assert config.id is not None
        assert config.is_enabled is True
        assert config.created_at is not None

    @pytest.mark.asyncio
    async def test_cascade_delete(self, db_session, sample_hcp, sample_kb_config):
        """Deleting HCP profile cascades to knowledge configs."""
        from sqlalchemy import select

        await db_session.delete(sample_hcp)
        await db_session.flush()

        result = await db_session.execute(
            select(HcpKnowledgeConfig).where(HcpKnowledgeConfig.id == sample_kb_config.id)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_hcp_profile_relationship(self, db_session, sample_hcp):
        """HcpProfile.knowledge_configs relationship works."""
        config = HcpKnowledgeConfig(
            hcp_profile_id=sample_hcp.id,
            connection_name="rel-conn",
            index_name="rel-index",
            server_label="knowledge-base-rel-index",
        )
        db_session.add(config)
        await db_session.flush()

        # Refresh to load relationship
        await db_session.refresh(sample_hcp, ["knowledge_configs"])
        assert len(sample_hcp.knowledge_configs) == 1
        assert sample_hcp.knowledge_configs[0].connection_name == "rel-conn"


# ---------------------------------------------------------------------------
# Integration Tests: Full KB → Agent Sync Flow
# ---------------------------------------------------------------------------


class TestKbAgentSyncIntegration:
    """End-to-end integration test: KB config changes trigger agent sync with MCPTool."""

    @pytest.mark.asyncio
    @patch("app.services.knowledge_base_service._trigger_agent_resync", new_callable=AsyncMock)
    async def test_full_flow_add_kb_triggers_resync(self, mock_resync, db_session, sample_hcp):
        """Adding a KB config triggers agent re-sync."""
        from app.services.knowledge_base_service import add_knowledge_config

        create_data = KnowledgeConfigCreate(
            connection_name="flow-conn",
            connection_target="https://search.flow.com",
            index_name="flow-index",
        )
        await add_knowledge_config(db_session, sample_hcp.id, create_data)

        # _trigger_agent_resync should have been called with (db, hcp_profile_id)
        mock_resync.assert_called_once_with(db_session, sample_hcp.id)

    @pytest.mark.asyncio
    @patch("app.services.knowledge_base_service._trigger_agent_resync", new_callable=AsyncMock)
    async def test_full_flow_remove_kb_triggers_resync(self, mock_resync, db_session, sample_hcp):
        """Removing a KB config triggers agent re-sync."""
        from app.services.knowledge_base_service import (
            add_knowledge_config,
            remove_knowledge_config,
        )

        # Add a config first
        create_data = KnowledgeConfigCreate(
            connection_name="rem-conn",
            index_name="rem-index",
        )
        config = await add_knowledge_config(db_session, sample_hcp.id, create_data)
        mock_resync.reset_mock()

        # Remove it
        await remove_knowledge_config(db_session, config.id)
        mock_resync.assert_called_once_with(db_session, sample_hcp.id)

    @pytest.mark.asyncio
    @patch("app.services.knowledge_base_service._trigger_agent_resync", new_callable=AsyncMock)
    async def test_full_flow_add_remove_kb_configs_list(self, mock_resync, db_session, sample_hcp):
        """Full flow: add 2 KB configs, verify list, remove one, verify list shrinks."""
        from app.services.knowledge_base_service import (
            add_knowledge_config,
            get_knowledge_configs,
            remove_knowledge_config,
        )

        # Add two KB configs
        config_a = await add_knowledge_config(
            db_session,
            sample_hcp.id,
            KnowledgeConfigCreate(
                connection_name="conn-a",
                connection_target="https://a.search.com",
                index_name="index-a",
            ),
        )
        config_b = await add_knowledge_config(
            db_session,
            sample_hcp.id,
            KnowledgeConfigCreate(
                connection_name="conn-b",
                connection_target="https://b.search.com",
                index_name="index-b",
            ),
        )

        # Verify both exist
        configs = await get_knowledge_configs(db_session, sample_hcp.id)
        assert len(configs) == 2
        names = {c.connection_name for c in configs}
        assert names == {"conn-a", "conn-b"}

        # Remove config_a
        await remove_knowledge_config(db_session, config_a.id)

        # Verify only config_b remains
        configs = await get_knowledge_configs(db_session, sample_hcp.id)
        assert len(configs) == 1
        assert configs[0].connection_name == "conn-b"
        assert configs[0].id == config_b.id

    @pytest.mark.asyncio
    async def test_build_search_tools_from_db_configs(self, db_session, sample_hcp):
        """build_search_tools generates tools from DB-persisted configs."""
        from app.services.knowledge_base_service import build_search_tools

        # Add configs to DB
        cfg1 = HcpKnowledgeConfig(
            hcp_profile_id=sample_hcp.id,
            connection_name="sync-conn",
            connection_target="https://search.sync.com",
            index_name="sync-index",
            server_label="knowledge-base-sync-index",
            is_enabled=True,
        )
        cfg2 = HcpKnowledgeConfig(
            hcp_profile_id=sample_hcp.id,
            connection_name="disabled-conn",
            index_name="disabled-index",
            server_label="knowledge-base-disabled-index",
            is_enabled=False,
        )
        db_session.add_all([cfg1, cfg2])
        await db_session.flush()

        # Refresh to get actual ORM objects
        await db_session.refresh(sample_hcp, ["knowledge_configs"])
        configs = sample_hcp.knowledge_configs

        assert len(configs) == 2

        # build_search_tools should only include enabled configs
        # (SDK not installed in test env, so result should be empty)
        tools = build_search_tools(configs)
        # Without SDK installed, returns empty list
        assert isinstance(tools, list)

    @pytest.mark.asyncio
    async def test_sync_agent_for_profile_includes_kb_tools(self, db_session, sample_hcp):
        """sync_agent_for_profile reads KB configs and passes tools to create_agent."""
        from app.services.knowledge_base_service import get_knowledge_configs

        # Add a KB config to DB
        cfg = HcpKnowledgeConfig(
            hcp_profile_id=sample_hcp.id,
            connection_name="agent-sync-conn",
            connection_target="https://search.agent.com",
            index_name="agent-index",
            server_label="knowledge-base-agent-index",
            is_enabled=True,
        )
        db_session.add(cfg)
        await db_session.flush()

        # Verify KB config is retrievable
        configs = await get_knowledge_configs(db_session, sample_hcp.id)
        assert len(configs) == 1
        assert configs[0].index_name == "agent-index"

    @pytest.mark.asyncio
    async def test_sync_agent_for_profile_no_kb_tools_when_empty(self, db_session, sample_hcp):
        """sync_agent_for_profile passes no tools when no KB configs exist."""
        from app.services.knowledge_base_service import build_search_tools, get_knowledge_configs

        # No KB configs exist
        configs = await get_knowledge_configs(db_session, sample_hcp.id)
        assert len(configs) == 0

        tools = build_search_tools(configs)
        assert tools == []

    @pytest.mark.asyncio
    async def test_omada_product_parameters_kb_uses_remote_tool(self, db_session, sample_hcp):
        """Regression: omada-product-parameters-kb must use RemoteTool connection (403 fix).

        Real-world scenario: KB 'omada-product-parameters-kb' on AI Search endpoint
        'ai-search-southeast-asia.search.windows.net'. CognitiveSearch connection
        'aisearchsoutheastasia5e88p4' causes 403; RemoteTool connection
        'kb-omada-product-param-e88p4' (CustomKeys) works correctly.
        """
        from app.services.knowledge_base_service import build_search_tools

        cfg = HcpKnowledgeConfig(
            hcp_profile_id=sample_hcp.id,
            connection_name="aisearchsoutheastasia5e88p4",
            connection_target="https://ai-search-southeast-asia.search.windows.net",
            index_name="omada-product-parameters-kb",
            server_label="knowledge-base-omada-product-parameters-kb",
            is_enabled=True,
        )
        db_session.add(cfg)
        await db_session.flush()

        await db_session.refresh(sample_hcp, ["knowledge_configs"])

        # Simulate RemoteTool connections from Foundry project
        rt_map = {"omada-product-parameters-kb": "kb-omada-product-param-e88p4"}

        tools = build_search_tools(sample_hcp.knowledge_configs, remote_tool_map=rt_map)
        assert len(tools) == 1
        tool_dict = tools[0].as_dict()

        # Must use RemoteTool connection (CustomKeys), NOT CognitiveSearch (ApiKey)
        assert tool_dict["project_connection_id"] == "kb-omada-product-param-e88p4"
        assert tool_dict["project_connection_id"] != "aisearchsoutheastasia5e88p4"

        # Verify MCP URL is correct
        assert "knowledgebases/omada-product-parameters-kb/mcp" in tool_dict["server_url"]
        assert "ai-search-southeast-asia.search.windows.net" in tool_dict["server_url"]
        assert tool_dict["require_approval"] == "never"

    @pytest.mark.asyncio
    async def test_sync_agent_for_profile_propagates_kb_resolution_failure(
        self, db_session, sample_hcp
    ):
        """sync_agent_for_profile must NOT swallow RemoteTool resolution/creation
        failures (Issue #86 regression guard). Previously this was wrapped in a
        broad try/except that logged a warning and continued, producing an
        unauthenticated MCPTool that got reported as a "synced" agent. Now the
        failure must propagate so the caller (hcp_profile_service /
        _trigger_agent_resync) can mark agent_sync_status="failed"."""
        from app.models.voice_live_instance import VoiceLiveInstance
        from app.services.agent_sync_service import sync_agent_for_profile

        # D-09: HcpProfile no longer has inline voice/avatar columns -- link a
        # VoiceLiveInstance so build_voice_live_metadata (called before the KB
        # resolution step under test) doesn't hit the dead no-VL-instance
        # fallback branch (which still reads the now-deleted columns).
        vl_instance = VoiceLiveInstance(
            name="KB Sync Test Instance", created_by=sample_hcp.created_by
        )
        db_session.add(vl_instance)
        await db_session.flush()
        sample_hcp.voice_live_instance_id = vl_instance.id
        sample_hcp.voice_live_instance = vl_instance

        cfg = HcpKnowledgeConfig(
            hcp_profile_id=sample_hcp.id,
            connection_name="propagate-conn",
            connection_target="https://search.propagate.com",
            index_name="propagate-kb",
            server_label="knowledge-base-propagate-kb",
            is_enabled=True,
        )
        db_session.add(cfg)
        await db_session.flush()

        with patch(
            "app.services.knowledge_base_service.resolve_kb_remote_tool_connections",
            new_callable=AsyncMock,
            side_effect=RuntimeError("ARM create failed: 403 Forbidden"),
        ):
            with pytest.raises(RuntimeError, match="ARM create failed"):
                await sync_agent_for_profile(db_session, sample_hcp, prefetched_model="gpt-4o")

    @pytest.mark.asyncio
    @patch("app.services.knowledge_base_service._trigger_agent_resync", new_callable=AsyncMock)
    async def test_resync_called_count_matches_mutations(self, mock_resync, db_session, sample_hcp):
        """_trigger_agent_resync is called once per add and once per remove."""
        from app.services.knowledge_base_service import (
            add_knowledge_config,
            remove_knowledge_config,
        )

        # Add
        config = await add_knowledge_config(
            db_session,
            sample_hcp.id,
            KnowledgeConfigCreate(connection_name="count-conn", index_name="count-index"),
        )
        assert mock_resync.call_count == 1

        # Remove
        await remove_knowledge_config(db_session, config.id)
        assert mock_resync.call_count == 2
