"""Knowledge base service: Foundry IQ Knowledge Base integration for HCP Agents.

Lists available search connections and knowledge bases from the AI Foundry project,
manages per-HCP knowledge base configurations, and builds MCPTool definitions
that appear in the Portal 'Knowledge' section (not 'Tools').

RemoteTool connections (required for MCPTool auth) are found-or-created:
resolve_kb_remote_tool_connections() first tries to reuse an existing RemoteTool
connection (matched by metadata or by normalized MCP target URL), and only
creates a new one via the ARM control-plane API when no match exists. This
replaces the previous assumption that the Portal always auto-creates the
RemoteTool connection for a KB before our code runs — that assumption doesn't
hold for KBs added purely via this app's API, so an explicit create step is
required.
"""

import hashlib
import logging
import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.hcp_knowledge_config import HcpKnowledgeConfig
from app.models.hcp_profile import HcpProfile
from app.schemas.knowledge_base import KnowledgeConfigCreate

logger = logging.getLogger(__name__)

SEARCH_API_VERSION = "2026-05-01-preview"
SEARCH_TOKEN_SCOPE = "https://search.azure.com/.default"

# ARM control-plane API version for Microsoft.CognitiveServices/accounts/projects/connections.
# Matches the accounts/projects resource version already used in
# infra/azure/modules/ai-foundry.bicep for consistency.
CONNECTIONS_ARM_API_VERSION = "2026-03-01"
ARM_TOKEN_SCOPE = "https://management.azure.com/.default"


def _get_field(obj: Any, *names: str, default: Any = "") -> Any:
    """Read a field from SDK model or dict response, trying several possible names."""
    for name in names:
        if isinstance(obj, dict) and name in obj:
            return obj[name]
        if hasattr(obj, name):
            value = getattr(obj, name)
            if value is not None:
                return value
    return default


def _extract_api_key(credentials: Any) -> str:
    """Extract an API key from possible Foundry connection credential shapes."""
    if not credentials:
        return ""

    for name in ("api_key", "apiKey", "key"):
        value = _get_field(credentials, name)
        if value:
            return str(value)

    keys = _get_field(credentials, "keys", default=None)
    if isinstance(keys, dict):
        for value in keys.values():
            if value:
                return str(value)
    if isinstance(keys, list):
        for item in keys:
            value = _get_field(item, "value", "key", "apiKey")
            if value:
                return str(value)

    return ""


async def _search_auth_headers(search_key: str) -> dict[str, str]:
    """Build Search data-plane auth headers, preferring API key only when present."""
    if search_key:
        return {"api-key": search_key}

    from app.services.azure_auth import get_bearer_token

    token = await get_bearer_token(SEARCH_TOKEN_SCOPE)
    if not token:
        raise RuntimeError(
            "Azure AI Search connection uses Entra ID but backend Managed Identity "
            "could not acquire a Search token."
        )
    return {"Authorization": f"Bearer {token}"}


async def _get_knowledgebases(search_endpoint: str, search_key: str) -> list[dict]:
    """List Foundry IQ knowledgebases from Azure AI Search with Entra ID or API key."""
    import httpx

    endpoint = search_endpoint.rstrip("/")
    headers = await _search_auth_headers(search_key)

    async with httpx.AsyncClient(timeout=15) as http:
        resp = await http.get(
            f"{endpoint}/knowledgebases",
            params={"api-version": SEARCH_API_VERSION},
            headers=headers,
        )

        if resp.status_code in (401, 403) and search_key:
            logger.info(
                "Search knowledgebases API rejected API key auth with %d; retrying with Entra ID",
                resp.status_code,
            )
            resp = await http.get(
                f"{endpoint}/knowledgebases",
                params={"api-version": SEARCH_API_VERSION},
                headers=await _search_auth_headers(""),
            )

    if resp.status_code != 200:
        raise RuntimeError(
            f"Foundry IQ knowledgebases API returned {resp.status_code}: {resp.text[:300]}"
        )

    data = resp.json()
    value = data.get("value", [])
    return value if isinstance(value, list) else []


async def list_search_connections(db: AsyncSession) -> list[dict]:
    """List Azure AI Search connections from the Foundry project.

    Returns list of dicts with name, target, is_default keys.
    Returns empty list if Foundry SDK is not installed or not configured.
    """
    try:
        from app.services.agent_sync_service import _get_project_client, get_project_endpoint

        project_endpoint, api_key = await get_project_endpoint(db)
        client = _get_project_client(project_endpoint, api_key)

        import asyncio

        from azure.ai.projects.models import ConnectionType

        connections = await asyncio.to_thread(
            client.connections.list, connection_type=ConnectionType.AZURE_AI_SEARCH
        )

        result = []
        for conn in connections:
            name = _get_field(conn, "name")
            target = _get_field(conn, "target")
            is_default = bool(_get_field(conn, "is_default", "isDefault", default=False))
            result.append({"name": name, "target": target, "is_default": bool(is_default)})
        return result
    except ImportError:
        logger.info("Azure AI Projects SDK not installed, returning empty connections list")
        return []
    except Exception as e:
        logger.warning("Failed to list search connections: %s", e)
        return []


async def list_indexes(db: AsyncSession, connection_name: str = "") -> list[dict]:
    """List indexes from an AI Search connection via direct REST API.

    AI Foundry's client.indexes.list() requires workspace-level permissions (403).
    Instead, we get the connection's API key via connections.get(include_credentials=True)
    and call the AI Search REST API directly — matching how AI Foundry portal works.

    If connection_name is empty, uses the default AI Search connection.

    Returns list of dicts with name and optional description keys.
    Returns empty list if SDK not installed or connection unavailable.
    """
    try:
        import asyncio

        from app.services.agent_sync_service import _get_project_client, get_project_endpoint

        project_endpoint, api_key = await get_project_endpoint(db)
        client = _get_project_client(project_endpoint, api_key)

        # Resolve connection: specific name or default AI Search connection
        if connection_name:
            conn = await asyncio.to_thread(
                client.connections.get, name=connection_name, include_credentials=True
            )
        else:
            from azure.ai.projects.models import ConnectionType

            conns = await asyncio.to_thread(
                client.connections.list, connection_type=ConnectionType.AZURE_AI_SEARCH
            )
            conn_list = list(conns)
            if not conn_list:
                return []
            # Pick default or first
            conn = next((c for c in conn_list if getattr(c, "is_default", False)), conn_list[0])
            conn_name = getattr(conn, "name", "")
            conn = await asyncio.to_thread(
                client.connections.get, name=conn_name, include_credentials=True
            )

        search_endpoint = str(_get_field(conn, "target")).rstrip("/")
        creds = _get_field(conn, "credentials", default=None)
        search_key = _extract_api_key(creds)

        if not search_endpoint:
            logger.warning("AI Search connection missing endpoint")
            return []

        knowledgebases = await _get_knowledgebases(search_endpoint, search_key)
        return [
            {
                "name": kb.get("name", ""),
                "version": kb.get("version", None),
                "type": kb.get("type", None),
                "description": kb.get("description", kb.get("name", "")),
            }
            for kb in knowledgebases
        ]
    except ImportError:
        logger.info("Azure AI Projects SDK not installed, returning empty indexes list")
        return []
    except Exception as e:
        logger.warning("Failed to list indexes: %s", e)
        return []


async def get_knowledge_configs(db: AsyncSession, hcp_profile_id: str) -> list[HcpKnowledgeConfig]:
    """Query all knowledge base configs for an HCP profile."""
    result = await db.execute(
        select(HcpKnowledgeConfig)
        .where(HcpKnowledgeConfig.hcp_profile_id == hcp_profile_id)
        .order_by(HcpKnowledgeConfig.created_at)
    )
    return list(result.scalars().all())


async def add_knowledge_config(
    db: AsyncSession,
    hcp_profile_id: str,
    config: KnowledgeConfigCreate,
) -> HcpKnowledgeConfig:
    """Create an HcpKnowledgeConfig record and trigger agent re-sync."""
    server_label = f"knowledge-base-{config.index_name}"
    record = HcpKnowledgeConfig(
        id=str(uuid.uuid4()),
        hcp_profile_id=hcp_profile_id,
        connection_name=config.connection_name,
        connection_target=config.connection_target,
        index_name=config.index_name,
        server_label=server_label,
        is_enabled=True,
    )
    db.add(record)
    await db.flush()

    # Trigger agent re-sync in background (best effort)
    await _trigger_agent_resync(db, hcp_profile_id)

    return record


async def remove_knowledge_config(db: AsyncSession, config_id: str) -> None:
    """Delete a knowledge base config and trigger agent re-sync."""
    result = await db.execute(select(HcpKnowledgeConfig).where(HcpKnowledgeConfig.id == config_id))
    record = result.scalar_one_or_none()
    if record is None:
        from app.utils.exceptions import not_found

        not_found("Knowledge config not found")

    hcp_profile_id = record.hcp_profile_id
    await db.delete(record)
    await db.flush()

    # Trigger agent re-sync in background (best effort)
    await _trigger_agent_resync(db, hcp_profile_id)


def _build_kb_mcp_url(connection_target: str, index_name: str) -> str:
    """Build the Foundry IQ Knowledge Base MCP endpoint URL for an index.

    Shared by build_search_tools() and the RemoteTool connection find/create
    logic so both sides always compute the same endpoint URL.
    """
    endpoint = (connection_target or "").rstrip("/")
    return f"{endpoint}/knowledgebases/{index_name}/mcp?api-version={SEARCH_API_VERSION}"


def _normalize_mcp_endpoint(url: str) -> str:
    """Normalize an MCP endpoint URL for equality comparison.

    Strips the query string (api-version may legitimately differ between an
    older Portal-created connection and our current SEARCH_API_VERSION),
    trailing slash, and case, so target-based matching isn't fooled by
    cosmetic differences.
    """
    if not url:
        return ""
    return url.split("?", 1)[0].rstrip("/").lower()


def _kb_name_from_target(target: str) -> str:
    """Best-effort extraction of the KB index name from a connection target URL."""
    match = re.search(r"/knowledgebases/([^/?]+)", target, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def _remote_tool_connection_name(index_name: str) -> str:
    """Build a stable, ARM-legal RemoteTool connection name for a KB index.

    Deterministic: the same index_name always produces the same name, so a
    repeated ARM PUT is an idempotent update rather than a duplicate
    connection. A short content hash suffix guards against two different KB
    names sanitizing to the same prefix (handles potential name collisions).
    """
    sanitized = re.sub(r"[^a-zA-Z0-9-]", "-", index_name.strip().lower())
    sanitized = re.sub(r"-+", "-", sanitized).strip("-")
    suffix = hashlib.sha1(index_name.encode("utf-8")).hexdigest()[:6]
    base = f"kb-{sanitized}" if sanitized else "kb"
    max_base_len = 63 - len(suffix) - 1
    return f"{base[:max_base_len]}-{suffix}"


async def _create_remote_tool_connection(db: AsyncSession, cfg: HcpKnowledgeConfig) -> str:
    """Create a RemoteTool project connection via the ARM control-plane API.

    Foundry's data-plane connections API (client.connections.*) has no
    create/update method (PUT/POST return 405) — RemoteTool connections must
    be created through Azure Resource Manager on the project's `connections`
    sub-resource. Uses authType="ProjectManagedIdentity" (per Microsoft's
    2026-06-02 connections documentation) so the connection stores no secret:
    the Foundry project's system-assigned managed identity authenticates to
    the KB MCP endpoint at request time. The ARM call itself is authenticated
    with an Entra ID bearer token (azure_auth.get_bearer_token) — never a
    stored secret/API key.

    Raises on any failure (missing ARM resource ID, missing Entra ID token,
    non-2xx ARM response) — callers must NOT swallow this, since a Knowledge
    Base that fails to get an authenticated connection must not be reported
    as part of a successfully synced agent.
    """
    import httpx

    from app.services.agent_sync_service import get_portal_url_components
    from app.services.azure_auth import get_bearer_token

    components = await get_portal_url_components(db)
    required_keys = ("subscription_id", "resource_group", "resource_name", "project_name")
    if not all(components.get(key) for key in required_keys):
        raise RuntimeError(
            f"Cannot create RemoteTool connection for Knowledge Base '{cfg.index_name}': "
            "unable to discover the Foundry project's ARM resource ID. At least one "
            "existing project connection (e.g. the AI Search connection used to browse "
            "this KB) is required to derive subscription/resource group/account/project."
        )

    token = await get_bearer_token(ARM_TOKEN_SCOPE)
    if not token:
        raise RuntimeError(
            f"Cannot create RemoteTool connection for Knowledge Base '{cfg.index_name}': "
            "no Entra ID token available for Azure Resource Manager. Configure Managed "
            "Identity or run 'az login', and grant Contributor on the Foundry project."
        )

    connection_name = _remote_tool_connection_name(cfg.index_name)
    mcp_url = _build_kb_mcp_url(cfg.connection_target, cfg.index_name)
    resource_id = (
        f"/subscriptions/{components['subscription_id']}"
        f"/resourceGroups/{components['resource_group']}"
        f"/providers/Microsoft.CognitiveServices/accounts/{components['resource_name']}"
        f"/projects/{components['project_name']}"
        f"/connections/{connection_name}"
    )
    url = f"https://management.azure.com{resource_id}?api-version={CONNECTIONS_ARM_API_VERSION}"
    body = {
        "name": connection_name,
        "type": "Microsoft.CognitiveServices/accounts/projects/connections",
        "properties": {
            "category": "RemoteTool",
            "target": mcp_url,
            "authType": "ProjectManagedIdentity",
            "isSharedToAll": True,
            "audience": "https://search.azure.com/",
            "metadata": {
                "type": "knowledgeBase_MCP",
                "knowledgeBaseName": cfg.index_name,
            },
        },
    }

    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.put(
            url,
            json=body,
            headers={"Authorization": f"Bearer {token}"},
        )

    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"Failed to create RemoteTool connection '{connection_name}' for Knowledge "
            f"Base '{cfg.index_name}' via ARM: {resp.status_code} {resp.text[:300]}"
        )

    logger.info(
        "Created RemoteTool connection '%s' for KB '%s' via ARM "
        "(category=RemoteTool, authType=ProjectManagedIdentity)",
        connection_name,
        cfg.index_name,
    )
    return connection_name


async def resolve_kb_remote_tool_connections(
    db: AsyncSession,
    configs: list[HcpKnowledgeConfig] | None = None,
) -> dict[str, str]:
    """Find or create RemoteTool connections for Knowledge Bases.

    RemoteTool connections are required for MCPTool auth (credentials/identity
    type CustomKeys or ProjectManagedIdentity), NOT a CognitiveSearch connection
    (ApiKey type causes 403). This function:

    1. Lists existing RemoteTool connections from the Foundry project and
       matches them to KBs by metadata.knowledgeBaseName first, then by the
       normalized MCP target URL (handles connections created without our
       metadata convention, e.g. via Portal).
    2. When `configs` is provided, for each *enabled* config with no match,
       creates a new RemoteTool connection via ARM (see
       _create_remote_tool_connection) — reusing any existing match is always
       preferred, and a connection is never created twice for the same KB.

    Returns a dict mapping KB index_name -> RemoteTool connection name.

    Behavior differs based on `configs`:
    - `configs=None` (legacy discovery-only mode, e.g. tooling/inspection):
      only lists existing connections; SDK-not-installed or any other
      discovery error is swallowed and an empty dict is returned.
    - `configs` provided (the real agent-sync path): discovery errors and
      RemoteTool creation failures ARE propagated (raised) to the caller.
      A Knowledge Base that fails to bind to an authenticated connection must
      never be silently dropped from what the UI reports as a "synced" agent.
    """
    enabled = [c for c in (configs or []) if c.is_enabled]
    require_success = bool(enabled)

    result: dict[str, str] = {}
    target_index: dict[str, str] = {}

    try:
        import asyncio

        from app.services.agent_sync_service import _get_project_client, get_project_endpoint

        project_endpoint, api_key = await get_project_endpoint(db)
        client = _get_project_client(project_endpoint, api_key)

        connections = await asyncio.to_thread(client.connections.list)

        for conn in connections:
            conn_type = _get_field(conn, "type")
            if conn_type != "RemoteTool":
                continue
            metadata = _get_field(conn, "metadata", default={})
            kb_name = _get_field(metadata, "knowledgeBaseName")
            target = str(_get_field(conn, "target"))
            if not kb_name:
                kb_name = _kb_name_from_target(target)
            conn_name = _get_field(conn, "name")
            if kb_name and conn_name:
                result[kb_name] = conn_name
            norm_target = _normalize_mcp_endpoint(target)
            if norm_target and conn_name:
                target_index[norm_target] = conn_name

        logger.info(
            "resolve_kb_remote_tool_connections: found %d RemoteTool KB connections", len(result)
        )
    except ImportError:
        if require_success:
            raise
        logger.info("Azure AI Projects SDK not installed, cannot resolve RemoteTool connections")
        return {}
    except Exception as e:
        if require_success:
            raise
        logger.warning("Failed to resolve RemoteTool connections: %s", e)
        return {}

    if not configs:
        return result

    for cfg in enabled:
        if cfg.index_name in result:
            continue
        expected = _normalize_mcp_endpoint(_build_kb_mcp_url(cfg.connection_target, cfg.index_name))
        matched_name = target_index.get(expected) if expected else None
        if matched_name:
            logger.info(
                "resolve_kb_remote_tool_connections: KB '%s' matched RemoteTool '%s' by target URL",
                cfg.index_name,
                matched_name,
            )
            result[cfg.index_name] = matched_name
            continue

        # No match found — create a new RemoteTool connection via ARM. Any failure
        # here propagates (see docstring); it is NOT caught and converted into a
        # silent no-op fallback.
        conn_name = await _create_remote_tool_connection(db, cfg)
        result[cfg.index_name] = conn_name
        if expected:
            target_index[expected] = conn_name

    return result


def build_search_tools(
    configs: list[HcpKnowledgeConfig],
    remote_tool_map: dict[str, str] | None = None,
) -> list:
    """Build MCPTool list from KB configs for agent definition.

    Each enabled config creates an MCPTool pointing to the KB's MCP endpoint.
    This matches how AI Foundry Portal connects Knowledge Bases to agents
    via the 'Knowledge' section (Preview), using the knowledgebases MCP protocol.

    The key difference from AzureAISearchTool (which shows under 'Tools'):
    - MCPTool with server_url pointing to /knowledgebases/{name}/mcp
    - allowed_tools = {"tool_names": ["knowledge_base_retrieve"]}
    - Shows in Portal 'Knowledge' section, not 'Tools' section.

    Authentication: MCPTool requires project_connection_id pointing to a RemoteTool
    connection, NOT a CognitiveSearch connection (credentials type=ApiKey causes
    403). Pass remote_tool_map (from resolve_kb_remote_tool_connections, which
    finds-or-creates the RemoteTool connection for each KB) to look up the
    correct connection name. This function itself never creates connections —
    it is a pure builder; if a KB is missing from remote_tool_map, its
    project_connection_id is omitted (callers should treat that as an error
    condition upstream, not rely on any implicit Portal auto-matching).

    Returns empty list if SDK is not installed or no enabled configs exist.
    """
    enabled = [c for c in configs if c.is_enabled]
    if not enabled:
        return []

    try:
        from azure.ai.projects.models import MCPTool, MCPToolFilter
    except ImportError:
        logger.info("Azure AI Projects SDK not installed, cannot build search tools")
        return []

    rt_map = remote_tool_map or {}

    tools = []
    for cfg in enabled:
        mcp_url = _build_kb_mcp_url(cfg.connection_target, cfg.index_name)

        # Use RemoteTool connection for MCP auth, NOT CognitiveSearch (ApiKey type
        # causes 403). resolve_kb_remote_tool_connections() finds-or-creates this.
        rt_connection_name = rt_map.get(cfg.index_name)
        if rt_connection_name:
            logger.info(
                "build_search_tools: KB '%s' -> RemoteTool connection '%s'",
                cfg.index_name,
                rt_connection_name,
            )
        else:
            logger.warning(
                "build_search_tools: no RemoteTool connection found for KB '%s'. "
                "MCPTool will have no project_connection_id and will likely fail "
                "MCP endpoint authentication at runtime.",
                cfg.index_name,
            )

        tool = MCPTool(
            server_label=cfg.server_label or f"knowledge-base-{cfg.index_name}",
            server_url=mcp_url,
            require_approval="never",
            allowed_tools=MCPToolFilter(tool_names=["knowledge_base_retrieve"]),
            project_connection_id=rt_connection_name,
        )
        tools.append(tool)
    return tools


async def _trigger_agent_resync(db: AsyncSession, hcp_profile_id: str) -> None:
    """Re-sync the HCP's AI Foundry agent after a Knowledge Base config change.

    Mirrors the pending/synced/failed pattern used by hcp_profile_service
    (create/update/retry_agent_sync) instead of the previous broad
    try/except-and-log, which silently swallowed sync failures — including
    RemoteTool connection creation failures — and left agent_sync_status
    unchanged (often still "synced" from a prior sync), hiding real errors
    from the admin UI (D-11 retry flow depends on agent_sync_status/
    agent_sync_error being accurate).
    """
    from app.services import agent_sync_service

    result = await db.execute(
        select(HcpProfile)
        .options(selectinload(HcpProfile.voice_live_instance))
        .where(HcpProfile.id == hcp_profile_id)
    )
    profile = result.scalar_one_or_none()
    if not profile or not profile.agent_id:
        return

    profile.agent_sync_status = "pending"
    profile.agent_sync_error = ""
    await db.flush()
    try:
        sync_result = await agent_sync_service.sync_agent_for_profile(db, profile)
        if sync_result.get("id"):
            profile.agent_id = sync_result["id"]
        profile.agent_version = str(sync_result.get("version", ""))
        profile.agent_sync_status = "synced"
        profile.agent_sync_error = ""
        logger.info("KB change triggered agent re-sync for profile %s", hcp_profile_id)
    except Exception as e:
        profile.agent_sync_status = "failed"
        profile.agent_sync_error = str(e)[:500]
        logger.warning(
            "Failed to re-sync agent after KB change for profile %s: %s",
            hcp_profile_id,
            e,
        )
    await db.flush()
