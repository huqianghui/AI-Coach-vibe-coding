"""Phase 31 non-mutating live capability gate for the exact pinned Foundry Agent."""

# ruff: noqa: E501

import asyncio
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest
from openai.types.responses.easy_input_message_param import EasyInputMessageParam
from openai.types.responses.response_input_item_param import Message
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models.scenario import Scenario
from app.models.session import CoachingSession
from app.services import agent_sync_service, config_service

pytestmark = [pytest.mark.integration, pytest.mark.timeout(1500)]

EXPECTED_PROJECT = "ai-coach-demo"
EXPECTED_AGENT = "Dr-Chen-Jun"
EXPECTED_VERSION = "5"
MCP_NAME = "knowledge_base_retrieve"
ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_PATH = (
    ROOT
    / ".planning/phases/31-session-skill-temporary-context-pinned-foundry-agent/31-CAPABILITY-EVIDENCE.md"
)
ALLOWLIST = {
    "backend/tests/integration/test_phase31_live_capabilities.py",
    ".planning/phases/31-session-skill-temporary-context-pinned-foundry-agent/31-CAPABILITY-EVIDENCE.md",
    ".planning/phases/31-session-skill-temporary-context-pinned-foundry-agent/31-01-SUMMARY.md",
}
WRITE_METHODS = {
    "create",
    "create_agent",
    "create_version",
    "create_version_from_code",
    "create_version_from_manifest",
    "delete",
    "delete_version",
    "patch_agent_details",
    "publish",
    "update",
    "update_details",
    "update_version",
}
DEADLINES = {
    "connection": 30.0,
    "behavior_response": 90.0,
    "cleanup": 10.0,
}
CANDIDATES = (
    ("RESPONSE_INPUT_DEVELOPER", "response_input", "developer"),
    ("RESPONSE_INPUT_SYSTEM", "response_input", "system"),
    ("CONVERSATION_ITEM_DEVELOPER", "conversation", "developer"),
    ("CONVERSATION_ITEM_SYSTEM", "conversation", "system"),
    ("SERVER_PREFIXED_USER", "server_prefix", "user"),
)
SENSITIVE = re.compile(
    r"(?i)(api[-_ ]?key|authorization|bearer|token|secret|credential)([\s:=]+)([^\s,;]+)"
)
URL = re.compile(r"(?i)(?:https?|wss?)://[^\s,;]+")


@dataclass
class GateState:
    preflight: dict[str, Any] = field(default_factory=dict)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    verdict: str = "BLOCKED: NO VIABLE TEXT TEMPORARY CONTEXT SURFACE"
    fingerprints: dict[str, str] = field(default_factory=dict)
    after_fingerprints: dict[str, str] = field(default_factory=dict)
    protected_before: dict[str, str] = field(default_factory=dict)
    protected_after: dict[str, str] = field(default_factory=dict)
    git_before: list[str] = field(default_factory=list)
    git_after: list[str] = field(default_factory=list)
    static_guard: str = "NOT RUN"
    write_count: int = 0
    cleanup: str = "NOT NEEDED"
    blockers: list[str] = field(default_factory=list)


class ReadOnlyAgents:
    """Expose only the two Agent read operations used by this gate."""

    def __init__(self, agents: object, state: GateState) -> None:
        self._agents = agents
        self._state = state

    def get_exact(self, name: str, version: str) -> object:
        return getattr(self._agents, "get_version")(agent_name=name, agent_version=version)

    def versions(self, name: str) -> list[object]:
        return list(getattr(self._agents, "list_versions")(agent_name=name, include_drafts=True))

    def __getattr__(self, name: str) -> Any:
        if name.casefold() in WRITE_METHODS:
            self._state.write_count += 1
            raise AssertionError(f"Agent write operation trapped: {name}")
        raise AttributeError(name)


def _sanitize(value: object) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ")
    text = SENSITIVE.sub(r"\1\2<redacted>", text)
    text = URL.sub("<redacted-url>", text)
    return text[:500]


def _sha(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(payload).hexdigest()


def _as_dict(value: object) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _as_dict(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_as_dict(item) for item in value]
    converter = getattr(value, "model_dump", None) or getattr(value, "as_dict", None)
    if callable(converter):
        return _as_dict(converter())
    if hasattr(value, "__dict__"):
        return {key: _as_dict(item) for key, item in vars(value).items() if not key.startswith("_")}
    return str(value)


def _protected_files() -> list[Path]:
    files: set[Path] = set()
    for directory in (ROOT / ".planning/debug", ROOT / "backend/storage/db-backups"):
        if directory.exists():
            files.update(path for path in directory.rglob("*") if path.is_file())
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        name = path.name.casefold()
        if rel in ALLOWLIST or "/.venv/" in f"/{rel}" or "/node_modules/" in f"/{rel}":
            continue
        if re.search(r"\.(?:db|sqlite|sqlite3)(?:-(?:wal|shm|journal))?$", name):
            files.add(path)
        if "phase30" in name and ("evidence" in name or "summary" in name):
            files.add(path)
        if "/30-" in f"/{rel}" and ("acceptance" in name or "summary" in name):
            files.add(path)
    return sorted(files)


def _file_hashes() -> dict[str, str]:
    return {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in _protected_files()
    }


def _static_guard() -> str:
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden_parameter = "instruc" + "tions"
    request_builder = source.split("def _request_kwargs", 1)[-1].split("\n\nasync def", 1)[0]
    if (
        f'"{forbidden_parameter}"' in request_builder
        or f"{forbidden_parameter}=" in request_builder
    ):
        raise AssertionError("Forbidden top-level temporary-context parameter is present")
    forbidden_calls = re.findall(
        r"\.\s*(create_version|delete_version|update_details|patch_agent_details|publish)\s*\(",
        source,
    )
    if forbidden_calls:
        raise AssertionError(f"Static Agent write guard rejected calls: {sorted(forbidden_calls)}")
    production = [
        ROOT / "backend/app/services/agent_chat_service.py",
    ]
    for path in production:
        if not path.is_file():
            raise AssertionError(f"Required read-only production surface missing: {path.name}")
    return "CLEAN"


def _git_status() -> list[str]:
    result = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return sorted(line.rstrip() for line in result.stdout.splitlines() if line.strip())


def _sdk_versions() -> dict[str, str]:
    packages = ("openai", "azure-ai-projects", "azure-identity")
    result: dict[str, str] = {"python": sys.version.split()[0]}
    for package in packages:
        try:
            result[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            result[package] = "MISSING"
    return result


def _host(value: str) -> str:
    parsed = urlparse(value)
    return parsed.hostname or ""


def _fingerprints(agents: ReadOnlyAgents) -> tuple[dict[str, str], object]:
    agent = agents.get_exact(EXPECTED_AGENT, EXPECTED_VERSION)
    definition = _as_dict(agent)
    versions = sorted(
        (_as_dict(item) for item in agents.versions(EXPECTED_AGENT)),
        key=lambda item: json.dumps(item, sort_keys=True, default=str),
    )
    return {
        "definition_tool_sha256": _sha(definition),
        "version_inventory_sha256": _sha(versions),
        "version_count": str(len(versions)),
    }, agent


def _event_payload(event: object) -> dict[str, Any]:
    payload = _as_dict(event)
    return payload if isinstance(payload, dict) else {"value": payload}


def _event_type(event: object, payload: dict[str, Any]) -> str:
    return str(getattr(event, "type", "") or payload.get("type", ""))


def _extract_response_id(payload: dict[str, Any]) -> str:
    response = payload.get("response")
    if isinstance(response, dict):
        return str(response.get("id", "") or "")
    return str(payload.get("response_id", "") or "")


def _extract_call_id(payload: dict[str, Any], item: dict[str, Any] | None) -> str:
    sources = [item or {}, payload]
    for source in sources:
        call_id = source.get("id") or source.get("call_id") or source.get("item_id")
        if call_id:
            return str(call_id)
    return ""


def _mcp_item(payload: dict[str, Any]) -> dict[str, Any] | None:
    item = payload.get("item")
    if isinstance(item, dict) and item.get("type") == "mcp_call":
        return item
    return payload if payload.get("type") == "mcp_call" else None


def _consume_text_stream(stream: object) -> dict[str, Any]:
    event_types: list[str] = []
    response_id = ""
    output_text: list[str] = []
    calls: dict[tuple[str, str], str] = {}
    completed: set[tuple[str, str]] = set()
    failed: set[tuple[str, str]] = set()
    final_output_mcp_exposed = False
    for stream_event in stream:
        payload = _event_payload(stream_event)
        event_type = _event_type(stream_event, payload)
        event_types.append(event_type)
        response_id = _extract_response_id(payload) or response_id
        if event_type == "response.output_text.delta":
            output_text.append(str(payload.get("delta", "")))
        item = _mcp_item(payload)
        if item:
            call_id = _extract_call_id(payload, item)
            if call_id:
                key = (str(item.get("response_id") or response_id), call_id)
                calls[key] = str(item.get("name", ""))
                if item.get("status") == "completed":
                    completed.add(key)
                elif item.get("status") == "failed":
                    failed.add(key)
                final_output_mcp_exposed = (
                    final_output_mcp_exposed or event_type == "response.completed"
                )
        item_id = _extract_call_id(payload, item)
        key = (str(payload.get("response_id") or response_id), item_id)
        if event_type.startswith("response.mcp_call.") and item_id:
            name = str(payload.get("name", "") or (item or {}).get("name", ""))
            if name:
                calls[key] = name
        if event_type == "response.mcp_call.completed" and item_id:
            completed.add(key)
        if event_type == "response.mcp_call.failed" and item_id:
            failed.add(key)
        if event_type == "response.completed":
            response = payload.get("response")
            if isinstance(response, dict):
                for output in response.get("output", []) or []:
                    if isinstance(output, dict) and output.get("type") == "mcp_call":
                        call_id = str(output.get("id") or output.get("call_id") or "")
                        key = (str(response.get("id") or response_id), call_id)
                        calls[key] = str(output.get("name", ""))
                        if output.get("status") == "completed":
                            completed.add(key)
                        elif output.get("status") == "failed":
                            failed.add(key)
                        final_output_mcp_exposed = True
    close = getattr(stream, "close", None)
    if callable(close):
        close()
    successful = sorted(
        call_id
        for (call_response_id, call_id), name in calls.items()
        if call_response_id == response_id
        and name == MCP_NAME
        and (call_response_id, call_id) in completed
        and (call_response_id, call_id) not in failed
    )
    return {
        "response_id": response_id,
        "text": "".join(output_text),
        "event_types": sorted(set(event_types)),
        "mcp_calls": sorted(call_id for _, call_id in calls),
        "successful_mcp_calls": successful,
        "failed_mcp_calls": sorted(call_id for _, call_id in failed),
        "final_output_mcp_exposed": final_output_mcp_exposed,
    }


@asynccontextmanager
async def _read_only_db() -> AsyncGenerator[AsyncSession, None]:
    """Open a separate read-only engine without importing the production WAL engine."""
    configured = make_url(str(get_settings().database_url))
    temporary_directory: tempfile.TemporaryDirectory[str] | None = None
    if configured.drivername.startswith("sqlite"):
        database = Path(configured.database or "")
        if not database.is_absolute():
            database = (ROOT / "backend" / database).resolve()
        temporary_directory = tempfile.TemporaryDirectory(prefix="phase31-readonly-")
        database_copy = Path(temporary_directory.name) / database.name
        shutil.copy2(database, database_copy)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{database}{suffix}")
            if sidecar.exists():
                shutil.copy2(sidecar, Path(f"{database_copy}{suffix}"))
        read_only_url = f"sqlite+aiosqlite:///file:{database_copy.as_posix()}?mode=ro&uri=true"
        engine = create_async_engine(read_only_url)
    else:
        engine = create_async_engine(configured)

        @sqlalchemy_event.listens_for(engine.sync_engine, "begin")
        def _force_read_only(connection: object) -> None:
            getattr(connection, "exec_driver_sql")("SET TRANSACTION READ ONLY")

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as db:
            yield db
            await db.rollback()
    finally:
        await engine.dispose()
        if temporary_directory is not None:
            temporary_directory.cleanup()


def _render_evidence(state: GateState) -> None:
    definition_match = state.fingerprints.get(
        "definition_tool_sha256"
    ) == state.after_fingerprints.get("definition_tool_sha256")
    inventory_match = state.fingerprints.get(
        "version_inventory_sha256"
    ) == state.after_fingerprints.get("version_inventory_sha256")
    protected_match = state.protected_before == state.protected_after
    lines = [
        "# Phase 31 Capability Evidence",
        "",
        "> Alternative text-only Requirement 2 gate. Directives, IQ question/marker, secrets, tokens, policy text, and tokenized URLs are excluded.",
        "",
        "## Deterministic verdicts",
        "",
        f"- Text Responses verdict: {state.verdict}",
        "- Voice WS verdict: BLOCKED: ENDPOINT 404",
        "- Avatar verdict: BLOCKED: ENDPOINT 404",
        "- WebRTC verdict: FAIL-CLOSED",
        "",
        "## Sanitized preflight",
        "",
        f"- Timestamp (UTC): {state.preflight.get('timestamp', 'not-run')}",
        f"- Project: {state.preflight.get('project', 'missing')}",
        f"- Session ID: {state.preflight.get('session_id', 'missing')}",
        f"- HCP ID: {state.preflight.get('hcp_id', 'missing')}",
        f"- Scenario ID: {state.preflight.get('scenario_id', 'missing')}",
        f"- Exact Agent pin: {state.preflight.get('agent_pin', 'missing')}",
        f"- Foundry endpoint host present: {state.preflight.get('foundry_host_present', False)}",
        f"- Credential source: {state.preflight.get('credential_source', 'unavailable')}",
        f"- IQ question present: {state.preflight.get('iq_question_present', False)}",
        f"- IQ marker present: {state.preflight.get('iq_marker_present', False)}",
        f"- SDK versions: {json.dumps(state.preflight.get('sdk_versions', {}), sort_keys=True)}",
        "- Exact candidate order: RESPONSE_INPUT_DEVELOPER -> RESPONSE_INPUT_SYSTEM -> CONVERSATION_ITEM_DEVELOPER -> CONVERSATION_ITEM_SYSTEM -> SERVER_PREFIXED_USER",
        "- Historical top-level instructions result: REJECTED 400 invalid_payload; not retried",
        "- Request tools/tool_choice supplied: false",
        "",
        "## Candidate matrix",
        "",
    ]
    for candidate in state.candidates:
        lines.extend(
            [
                f"### {candidate['name']}",
                "",
                f"- Status: {candidate.get('status', 'NOT ATTEMPTED')}",
                f"- A response ID: {candidate.get('a_response_id', 'none')}",
                f"- B response ID: {candidate.get('b_response_id', 'none')}",
                f"- Continuation mechanism: {candidate.get('continuation', 'none')}",
                f"- Disposable Conversation ID: {candidate.get('conversation_id', 'none')}",
                f"- A correlated call IDs: {json.dumps(candidate.get('a_call_ids', []))}",
                f"- B correlated call IDs: {json.dumps(candidate.get('b_call_ids', []))}",
                f"- A correlated successful knowledge_base_retrieve: {candidate.get('a_iq', False)}",
                f"- B correlated successful knowledge_base_retrieve: {candidate.get('b_iq', False)}",
                f"- Accepted event types: {json.dumps(candidate.get('event_types', []))}",
            ]
        )
        if candidate.get("reason"):
            lines.append(f"- Sanitized reason: {_sanitize(candidate['reason'])}")
        lines.append("")
    lines.extend(
        [
            "## Immutability and trust controls",
            "",
            f"- Static Agent write guard: {state.static_guard}",
            f"- Agent resource writes: {state.write_count}",
            f"- Definition/tool fingerprint before: {state.fingerprints.get('definition_tool_sha256', 'unavailable')}",
            f"- Definition/tool fingerprint after: {state.after_fingerprints.get('definition_tool_sha256', 'unavailable')}",
            f"- Definition/tool fingerprint: {'MATCH' if definition_match else 'MISMATCH'}",
            f"- Version inventory fingerprint before: {state.fingerprints.get('version_inventory_sha256', 'unavailable')}",
            f"- Version inventory fingerprint after: {state.after_fingerprints.get('version_inventory_sha256', 'unavailable')}",
            f"- Version inventory fingerprint: {'MATCH' if inventory_match else 'MISMATCH'}",
            f"- Protected hash manifest: {'MATCH' if protected_match else 'MISMATCH'}",
            f"- Disposable Conversation cleanup: {state.cleanup}",
            "- Database writes: 0 (read-only Session lookup; explicit rollback; no create fallback)",
            "",
            "## Blockers",
            "",
        ]
    )
    lines.extend(f"- {_sanitize(blocker)}" for blocker in state.blockers)
    if not state.blockers:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Authorization boundary",
            "",
            "This verdict authorizes only subsequent GSD replanning. Production code/tests, schema/migrations, databases, commit, and push are not authorized.",
            "Withdrawn Plans 31-02 through 31-07 remain non-executable.",
            "Text evidence does not prove Voice, avatar, or WebRTC capability.",
            "",
        ]
    )
    EVIDENCE_PATH.write_text("\n".join(lines), encoding="utf-8")


async def _project_context(
    state: GateState,
) -> tuple[object, ReadOnlyAgents, str]:
    session_id = os.getenv("PHASE31_SESSION_ID", "").strip()
    async with _read_only_db() as db:
        query = (
            select(CoachingSession)
            .options(selectinload(CoachingSession.scenario).selectinload(Scenario.hcp_profile))
            .where(CoachingSession.skill_id.is_not(None))
            .order_by(CoachingSession.created_at.desc())
        )
        if session_id:
            query = query.where(CoachingSession.id == session_id)
        session = await db.scalar(query)
        if session is None:
            raise AssertionError(
                "No existing Skill-bound CoachingSession is available as context anchor"
            )
        scenario = session.scenario
        profile = scenario.hcp_profile
        configured_hcp = os.getenv("UNIFIED_TRAINING_HCP_PROFILE_ID", "").strip()
        configured_scenario = os.getenv("UNIFIED_TRAINING_SCENARIO_ID", "").strip()
        if configured_hcp and configured_hcp != profile.id:
            raise AssertionError("Configured HCP does not match the exact-pinned Session")
        if configured_scenario and configured_scenario != scenario.id:
            raise AssertionError("Configured scenario does not match the exact-pinned Session")
        project_endpoint, project_api_key = await agent_sync_service.get_project_endpoint(db)
        master = await config_service.get_master_config(db)
        project = str(master.default_project or "").strip() if master else ""
        model = str(master.model_or_deployment or "").strip() if master else ""
        anchor = {
            "session_id": session.id,
            "hcp_id": profile.id,
            "scenario_id": scenario.id,
            "session_pin_source": (
                "persisted"
                if session.agent_name == EXPECTED_AGENT
                and session.agent_version == EXPECTED_VERSION
                else "legacy-read-only-anchor-plus-hard-exact-target"
            ),
        }
    if project != EXPECTED_PROJECT:
        raise AssertionError(
            f"Foundry project mismatch: expected {EXPECTED_PROJECT}, got {_sanitize(project)}"
        )
    if not project_endpoint or not model:
        raise AssertionError("Foundry DB configuration is incomplete or inactive")
    client = agent_sync_service._get_project_client(project_endpoint, project_api_key)
    credential_source = "database-api-key" if project_api_key else "DefaultAzureCredential"
    state.preflight.update(
        {
            "timestamp": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "project": project,
            "session_id": anchor["session_id"],
            "hcp_id": anchor["hcp_id"],
            "scenario_id": anchor["scenario_id"],
            "agent_pin": f"{EXPECTED_AGENT}/{EXPECTED_VERSION}",
            "session_pin_source": anchor["session_pin_source"],
            "foundry_host_present": bool(_host(project_endpoint)),
            "credential_source": credential_source,
        }
    )
    return client, ReadOnlyAgents(client.agents, state), model


def _directive(marker: str) -> str:
    token = f"P31-ALT-{marker}"
    excluded = "P31-ALT-B" if marker == "A" else "P31-ALT-A"
    return (
        f"For this response only, begin with the exact token {token}; do not include {excluded}. "
        "Then answer the knowledge question using the Agent's native knowledge tool."
    )


def _typed_message(role: str, text: str) -> EasyInputMessageParam:
    return {"type": "message", "role": role, "content": text}  # type: ignore[typeddict-item]


def _conversation_message(role: str, text: str) -> Message:
    return {
        "type": "message",
        "role": role,  # type: ignore[typeddict-item]
        "content": [{"type": "input_text", "text": text}],
    }


def _request_kwargs(model: str, input_items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "model": model,
        "input": input_items,
        "stream": True,
        "extra_body": {
            "agent_reference": {
                "name": EXPECTED_AGENT,
                "version": EXPECTED_VERSION,
                "type": "agent_reference",
            }
        },
    }


async def _response(openai_client: object, kwargs: dict[str, Any]) -> dict[str, Any]:
    stream = await asyncio.wait_for(
        asyncio.to_thread(getattr(openai_client.responses, "create"), **kwargs),
        timeout=DEADLINES["connection"],
    )
    return await asyncio.wait_for(
        asyncio.to_thread(_consume_text_stream, stream),
        timeout=DEADLINES["behavior_response"],
    )


def _classify(a: dict[str, Any], b: dict[str, Any], marker: str) -> tuple[str, bool]:
    a_text = a["text"].casefold()
    b_text = b["text"].casefold()
    behavior = (
        "p31-alt-a" in a_text
        and "p31-alt-b" not in a_text
        and "p31-alt-b" in b_text
        and "p31-alt-a" not in b_text
        and marker.casefold() in a_text
        and marker.casefold() in b_text
    )
    if not a["response_id"] or not b["response_id"] or a["response_id"] == b["response_id"]:
        return "CORRELATION_FAILED", False
    if not behavior:
        return "BEHAVIOR_FAILED", False
    if not a["successful_mcp_calls"] or not b["successful_mcp_calls"]:
        return "IQ_FAILED", False
    return "PROVEN", True


async def _candidate(
    openai_client: object,
    name: str,
    kind: str,
    role: str,
    model: str,
    question: str,
    marker: str,
    state: GateState,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": name,
        "status": "REJECTED",
        "continuation": "same Conversation" if kind == "conversation" else "previous_response_id",
        "conversation_id": "none",
    }
    conversation_id = ""
    try:
        if kind == "response_input":
            a = await _response(
                openai_client,
                _request_kwargs(
                    model,
                    [_typed_message(role, _directive("A")), {"role": "user", "content": question}],
                ),
            )
            b_kwargs = _request_kwargs(
                model,
                [_typed_message(role, _directive("B")), {"role": "user", "content": question}],
            )
            b_kwargs["previous_response_id"] = a["response_id"]
            b = await _response(openai_client, b_kwargs)
        elif kind == "conversation":
            conversation = await asyncio.wait_for(
                asyncio.to_thread(
                    openai_client.conversations.create,
                    items=[_conversation_message(role, _directive("A"))],
                ),
                timeout=DEADLINES["connection"],
            )
            conversation_id = str(getattr(conversation, "id", "") or "")
            if not conversation_id:
                raise AssertionError("Disposable Conversation create returned no ID")
            result["conversation_id"] = conversation_id
            state.cleanup = "PENDING"
            a_kwargs = _request_kwargs(model, [{"role": "user", "content": question}])
            a_kwargs["conversation"] = conversation_id
            a = await _response(openai_client, a_kwargs)
            await asyncio.wait_for(
                asyncio.to_thread(
                    openai_client.conversations.items.create,
                    conversation_id,
                    items=[_conversation_message(role, _directive("B"))],
                ),
                timeout=DEADLINES["connection"],
            )
            b_kwargs = _request_kwargs(model, [{"role": "user", "content": question}])
            b_kwargs["conversation"] = conversation_id
            b = await _response(openai_client, b_kwargs)
        else:
            a_message = (
                f"[SERVER TEMPORARY CONTEXT]\n{_directive('A')}\n"
                f"[/SERVER TEMPORARY CONTEXT]\n{question}"
            )
            a = await _response(
                openai_client,
                _request_kwargs(model, [{"role": "user", "content": a_message}]),
            )
            b_message = (
                f"[SERVER TEMPORARY CONTEXT]\n{_directive('B')}\n"
                f"[/SERVER TEMPORARY CONTEXT]\n{question}"
            )
            b_kwargs = _request_kwargs(model, [{"role": "user", "content": b_message}])
            b_kwargs["previous_response_id"] = a["response_id"]
            b = await _response(openai_client, b_kwargs)
        status, viable = _classify(a, b, marker)
        result.update(
            {
                "status": status,
                "viable": viable,
                "a_response_id": a["response_id"],
                "b_response_id": b["response_id"],
                "a_call_ids": a["successful_mcp_calls"],
                "b_call_ids": b["successful_mcp_calls"],
                "a_iq": bool(a["successful_mcp_calls"]),
                "b_iq": bool(b["successful_mcp_calls"]),
                "event_types": sorted(set(a["event_types"] + b["event_types"])),
            }
        )
    except Exception as exc:
        status = "CORRELATION_FAILED" if "correlat" in str(exc).casefold() else "REJECTED"
        result.update({"status": status, "viable": False, "reason": _sanitize(exc)})
    finally:
        if conversation_id:
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(openai_client.conversations.delete, conversation_id),
                    timeout=DEADLINES["cleanup"],
                )
                state.cleanup = "CONFIRMED"
            except Exception as exc:
                state.cleanup = "FAILED"
                result.update(
                    {"status": "CLEANUP_FAILED", "viable": False, "reason": _sanitize(exc)}
                )
                state.blockers.append(f"{name}: disposable Conversation cleanup failed")
    return result


@pytest.mark.asyncio
async def test_phase31_exact_pin_temporary_context_capabilities() -> None:
    """Try five text surfaces in strict order and render fail-closed evidence."""
    state = GateState()
    agents: ReadOnlyAgents | None = None
    state.protected_before = _file_hashes()
    state.git_before = _git_status()
    state.static_guard = _static_guard()
    state.preflight.update(
        {
            "sdk_versions": _sdk_versions(),
            "iq_question_present": bool(os.getenv("UNIFIED_TRAINING_KB_QUESTION", "").strip()),
            "iq_marker_present": bool(os.getenv("UNIFIED_TRAINING_KB_EXPECTED_MARKER", "").strip()),
        }
    )
    try:
        if os.getenv("PHASE31_TEXT_ALT_GATE", "") != "1":
            raise AssertionError("PHASE31_TEXT_ALT_GATE=1 explicit live opt-in is required")
        if not state.preflight["iq_question_present"] or not state.preflight["iq_marker_present"]:
            raise AssertionError(
                "IQ question/expected marker are unavailable in local configuration"
            )
        client, agents, model = await _project_context(state)
        state.fingerprints, agent = await asyncio.to_thread(_fingerprints, agents)
        definition = _as_dict(agent)
        tools = (
            definition.get("definition", {}).get("tools", [])
            if isinstance(definition, dict)
            else []
        )
        if MCP_NAME not in json.dumps(tools, sort_keys=True, default=str):
            raise AssertionError(
                "Exact Agent definition does not restrict IQ to knowledge_base_retrieve"
            )
        question = os.environ["UNIFIED_TRAINING_KB_QUESTION"]
        marker = os.environ["UNIFIED_TRAINING_KB_EXPECTED_MARKER"]
        openai_client = getattr(client, "get_openai_client")()
        for index, (name, kind, role) in enumerate(CANDIDATES):
            candidate = await _candidate(
                openai_client, name, kind, role, model, question, marker, state
            )
            state.candidates.append(candidate)
            if candidate.get("viable"):
                state.verdict = f"PROVEN: {name}"
                for lower_name, _, _ in CANDIDATES[index + 1 :]:
                    state.candidates.append(
                        {
                            "name": lower_name,
                            "status": "NOT ATTEMPTED: FIRST VIABLE SURFACE FOUND",
                        }
                    )
                break
        if state.verdict.startswith("BLOCKED"):
            state.blockers.append("No candidate satisfied distinct A/B behavior and two IQ calls")
    except Exception as exc:
        state.blockers.append(_sanitize(exc))
        attempted = {candidate["name"] for candidate in state.candidates}
        for name, _, _ in CANDIDATES:
            if name not in attempted:
                state.candidates.append(
                    {"name": name, "status": "NOT ATTEMPTED: PREFLIGHT BLOCKED"}
                )
    finally:
        if agents is not None and state.fingerprints:
            try:
                state.after_fingerprints, _ = await asyncio.to_thread(_fingerprints, agents)
            except Exception as exc:
                state.blockers.append("Agent postflight: " + _sanitize(exc))
        state.protected_after = _file_hashes()
        state.git_after = _git_status()
        _render_evidence(state)

    assert state.static_guard == "CLEAN"
    assert state.write_count == 0
    assert state.protected_after == state.protected_before
    assert state.git_after == state.git_before
    assert state.fingerprints and state.after_fingerprints == state.fingerprints
    assert state.cleanup in {"NOT NEEDED", "CONFIRMED"}
    assert state.preflight.get("agent_pin") == "Dr-Chen-Jun/5"
    assert state.verdict.startswith("PROVEN: "), state.verdict
