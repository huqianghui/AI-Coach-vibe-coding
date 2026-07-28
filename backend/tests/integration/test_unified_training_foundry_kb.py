"""Real Azure acceptance for Unified Training's exact pinned Agent and Foundry IQ."""

import asyncio
import hashlib
import os
from datetime import UTC, datetime
from urllib.parse import urlparse

import pytest
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.hcp_profile import HcpProfile
from app.models.scenario import Scenario
from app.models.user import User
from app.services import agent_sync_service
from app.services.agent_chat_service import chat_with_agent
from app.services.session_service import create_session

pytestmark = [pytest.mark.integration, pytest.mark.timeout(120)]

_REQUIRED_ENV = (
    "AZURE_FOUNDRY_ENDPOINT",
    "AZURE_FOUNDRY_DEFAULT_PROJECT",
    "UNIFIED_TRAINING_HCP_PROFILE_ID",
    "UNIFIED_TRAINING_SCENARIO_ID",
    "UNIFIED_TRAINING_KB_QUESTION",
    "UNIFIED_TRAINING_KB_EXPECTED_MARKER",
)


def _required_environment() -> dict[str, str]:
    values = {name: os.environ.get(name, "").strip() for name in _REQUIRED_ENV}
    missing = [name for name, value in values.items() if not value]
    if missing:
        pytest.skip("Phase 30 real-Azure inputs are not configured: " + ", ".join(missing))
    return values


def _allowed_tool_names(tool: object) -> list[str]:
    allowed = getattr(tool, "allowed_tools", None)
    if isinstance(allowed, list):
        return [str(name) for name in allowed]
    names = getattr(allowed, "tool_names", None)
    return [str(name) for name in names] if names else []


async def test_pinned_agent_has_restricted_iq_and_retrieves_kb_marker() -> None:
    """Inspect and invoke the exact Agent version snapshotted by production session creation."""
    env = _required_environment()

    async with AsyncSessionLocal() as db:
        try:
            scenario = await db.get(Scenario, env["UNIFIED_TRAINING_SCENARIO_ID"])
            assert scenario is not None, "Configured Unified Training scenario does not exist"
            assert scenario.status == "active", "Configured scenario must be active"
            assert scenario.mode == "f2f", "Configured scenario must be F2F"
            assert scenario.hcp_profile_id == env["UNIFIED_TRAINING_HCP_PROFILE_ID"]

            profile = await db.get(HcpProfile, scenario.hcp_profile_id)
            assert profile is not None
            assert profile.agent_sync_status == "synced"

            owner = await db.scalar(
                select(User).where(User.is_active.is_(True)).order_by(User.created_at)
            )
            assert owner is not None, "A pre-existing active owner is required"

            session = await create_session(db, scenario.id, owner.id, mode="text")
            assert session.agent_name == profile.agent_id
            assert session.agent_version == profile.agent_version

            project_endpoint, api_key = await agent_sync_service.get_project_endpoint(db)
            expected_base = env["AZURE_FOUNDRY_ENDPOINT"].rstrip("/")
            assert project_endpoint.startswith(expected_base)
            assert env["AZURE_FOUNDRY_DEFAULT_PROJECT"] in project_endpoint

            client = agent_sync_service._get_project_client(project_endpoint, api_key)
            agent = await asyncio.to_thread(
                client.agents.get_version,
                agent_name=session.agent_name,
                agent_version=session.agent_version,
            )
            assert str(agent.name) == session.agent_name
            assert str(agent.version) == session.agent_version

            tools = list(getattr(agent.definition, "tools", None) or [])
            mcp_tools = [tool for tool in tools if str(getattr(tool, "type", "")) == "mcp"]
            assert mcp_tools, "Pinned Agent version does not contain an MCP tool"

            restricted_tools = [
                tool
                for tool in mcp_tools
                if _allowed_tool_names(tool) == ["knowledge_base_retrieve"]
            ]
            assert restricted_tools, (
                "Pinned Agent MCP tools must allow only knowledge_base_retrieve"
            )
            mcp_tool = restricted_tools[0]
            connection_id = str(getattr(mcp_tool, "project_connection_id", "") or "").strip()
            server_url = str(getattr(mcp_tool, "server_url", "") or "").strip()
            parsed_url = urlparse(server_url)
            assert connection_id, "Foundry IQ MCP tool is not authenticated by project connection"
            assert parsed_url.scheme == "https" and parsed_url.hostname

            result = await chat_with_agent(
                db,
                session.agent_name,
                session.agent_version,
                env["UNIFIED_TRAINING_KB_QUESTION"],
            )
            answer = str(result.get("response_text", ""))
            response_id = str(result.get("response_id", "") or "").strip()
            marker = env["UNIFIED_TRAINING_KB_EXPECTED_MARKER"]
            assert marker.casefold() in answer.casefold()
            assert response_id

            evidence = {
                "timestamp_utc": datetime.now(UTC).isoformat(),
                "session_id": session.id,
                "agent_name": session.agent_name,
                "agent_version": session.agent_version,
                "mcp_server_label": str(getattr(mcp_tool, "server_label", "")),
                "mcp_server_host": parsed_url.hostname,
                "allowed_tools": _allowed_tool_names(mcp_tool),
                "response_id": response_id,
                "question_sha256": hashlib.sha256(
                    env["UNIFIED_TRAINING_KB_QUESTION"].encode("utf-8")
                ).hexdigest(),
                "marker_matched": True,
            }
            print(f"PHASE30_AZURE_EVIDENCE={evidence}")
        finally:
            await db.rollback()
