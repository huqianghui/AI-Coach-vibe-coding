"""Strict opt-in production acceptance orchestration for Phase 31 text turns.

The orchestration is provider-agnostic and is fully exercised offline. Plan 09 must
supply the real production adapter and explicitly opt in; this module never skips and
never treats missing prerequisites as success.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid
from typing import Protocol

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import AsyncSessionLocal
from app.models.hcp_profile import HcpProfile
from app.models.message import SessionMessage
from app.models.scenario import Scenario
from app.models.session import CoachingSession
from app.models.session_turn import SessionTurn
from app.models.session_turn_context_audit import SessionTurnContextAudit
from app.models.user import User
from app.services import agent_sync_service
from app.services.foundry_conversation_service import FoundryConversationService
from app.services.session_service import create_session, end_session
from app.services.session_skill_context import load_sop_snapshot
from app.services.session_turn_orchestrator import SessionTurnOrchestrator
from app.services.session_turn_progression import SessionProgressionDecision

IQ_TOOL = "knowledge_base_retrieve"
EXPECTED_PROJECT = "ai-coach-demo"
EXPECTED_AGENT = "Dr-Chen-Jun"
EXPECTED_VERSION = "5"

_REQUIRED_ENV = (
    "AZURE_FOUNDRY_ENDPOINT",
    "AZURE_FOUNDRY_DEFAULT_PROJECT",
    "UNIFIED_TRAINING_HCP_PROFILE_ID",
    "UNIFIED_TRAINING_SCENARIO_ID",
    "UNIFIED_TRAINING_KB_QUESTION",
    "UNIFIED_TRAINING_KB_EXPECTED_MARKER",
)


class AcceptanceError(RuntimeError):
    """Raised when production-path evidence fails closed."""


class AcceptanceProvider(Protocol):
    async def preflight(self) -> dict: ...

    async def create_session(self) -> str: ...

    async def run_turn(self, session_id: str, directive: str, question: str) -> dict: ...

    async def cleanup(self, session_id: str) -> None: ...


def _required_environment() -> dict[str, str]:
    values = {name: os.getenv(name, "").strip() for name in _REQUIRED_ENV}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise AcceptanceError("blocking environment is incomplete: " + ", ".join(missing))
    return values


def _as_dict(value: object) -> object:
    converter = getattr(value, "model_dump", None) or getattr(value, "as_dict", None)
    if callable(converter):
        return converter()
    if isinstance(value, dict):
        return value
    if hasattr(value, "__dict__"):
        return {key: item for key, item in vars(value).items() if not key.startswith("_")}
    return str(value)


def _fingerprint(value: object) -> str:
    payload = json.dumps(_as_dict(value), sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _allowed_tool_names(tool: object) -> list[str]:
    allowed = getattr(tool, "allowed_tools", None)
    if isinstance(allowed, list):
        return [str(name) for name in allowed]
    names = getattr(allowed, "tool_names", None)
    return [str(name) for name in names] if names else []


class ProductionAcceptanceProvider:
    """Strict adapter over the real Session/Conversation production path."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
    ) -> None:
        self._sessions = session_factory
        self._env: dict[str, str] = {}
        self._project_client: object | None = None
        self._openai_client: object | None = None
        self._conversations: FoundryConversationService | None = None
        self._orchestrator: SessionTurnOrchestrator | None = None
        self._agent_fingerprint = ""
        self._turn_number = 0
        self._owner_id = ""

    async def _agent(self) -> object:
        if self._project_client is None:
            raise AcceptanceError("production provider preflight has not completed")
        return await asyncio.to_thread(
            self._project_client.agents.get_version,
            agent_name=EXPECTED_AGENT,
            agent_version=EXPECTED_VERSION,
        )

    async def preflight(self) -> dict:
        self._env = _required_environment()
        if self._env["AZURE_FOUNDRY_DEFAULT_PROJECT"] != EXPECTED_PROJECT:
            raise AcceptanceError("configured Foundry project is not the approved project")

        async with self._sessions() as db:
            scenario = await db.get(Scenario, self._env["UNIFIED_TRAINING_SCENARIO_ID"])
            profile = await db.get(HcpProfile, self._env["UNIFIED_TRAINING_HCP_PROFILE_ID"])
            if scenario is None or profile is None:
                raise AcceptanceError("configured scenario or HCP profile does not exist")
            if scenario.status != "active" or scenario.hcp_profile_id != profile.id:
                raise AcceptanceError("configured scenario/HCP binding is not active and exact")
            if profile.agent_sync_status != "synced":
                raise AcceptanceError("configured HCP Agent is not synced")
            if profile.agent_id != EXPECTED_AGENT or profile.agent_version != EXPECTED_VERSION:
                raise AcceptanceError("configured HCP does not use the approved exact Agent pin")
            endpoint, api_key = await agent_sync_service.get_project_endpoint(db)

        expected_suffix = f"/api/projects/{EXPECTED_PROJECT}"
        if not endpoint.rstrip("/").endswith(expected_suffix):
            raise AcceptanceError("resolved Foundry endpoint is not the approved project")
        self._project_client = agent_sync_service._get_project_client(endpoint, api_key)
        self._openai_client = self._project_client.get_openai_client()
        self._conversations = FoundryConversationService(self._openai_client)
        self._orchestrator = SessionTurnOrchestrator(
            self._conversations,
            self._openai_client,
        )

        agent = await self._agent()
        tools = list(getattr(getattr(agent, "definition", None), "tools", None) or [])
        restricted_iq = [
            tool
            for tool in tools
            if str(getattr(tool, "type", "")) == "mcp" and _allowed_tool_names(tool) == [IQ_TOOL]
        ]
        if not restricted_iq:
            raise AcceptanceError("approved Agent lacks restricted knowledge_base_retrieve MCP")
        self._agent_fingerprint = _fingerprint(agent)
        return {
            "agent_name": EXPECTED_AGENT,
            "agent_version": EXPECTED_VERSION,
            "project": EXPECTED_PROJECT,
            "cleanup": True,
        }

    async def create_session(self) -> str:
        if not self._env:
            raise AcceptanceError("production provider preflight has not completed")
        async with self._sessions() as db, db.begin():
            owner = await db.scalar(
                select(User).where(User.is_active.is_(True)).order_by(User.created_at).limit(1)
            )
            if owner is None:
                raise AcceptanceError("a pre-existing active Session owner is required")
            self._owner_id = owner.id
            session = await create_session(
                db,
                self._env["UNIFIED_TRAINING_SCENARIO_ID"],
                owner.id,
                mode="text",
            )
            snapshot = load_sop_snapshot(session)
            if len(snapshot.sop_steps) < 3:
                raise AcceptanceError(
                    "pinned Skill requires at least three SOP steps for A/B proof"
                )
            session.focus_instruction = "Quoted immutable reference (stale): current step 99."
            session.sop_current_step = 1
            session.context_revision = 0
            await db.flush()
            return session.id

    async def run_turn(self, session_id: str, directive: str, question: str) -> dict:
        if self._orchestrator is None:
            raise AcceptanceError("production provider preflight has not completed")
        self._turn_number += 1
        expected_step = self._turn_number
        if f"CURRENT STEP {expected_step}" not in directive:
            raise AcceptanceError("harness directive does not match the expected A/B step")

        async with self._sessions() as db:
            session = await db.get(CoachingSession, session_id)
            if session is None:
                raise AcceptanceError("disposable Session disappeared before turn execution")
            from_step = session.sop_current_step
            revision = session.context_revision
        if from_step != expected_step or revision != expected_step - 1:
            raise AcceptanceError("Session progression is not at the expected A/B boundary")

        progression = SessionProgressionDecision(
            "advanced" if self._turn_number == 1 else "unchanged",
            from_step,
            from_step + 1 if self._turn_number == 1 else from_step,
            "production_acceptance_ab",
        )
        turn_key = str(uuid.uuid4())
        result = await self._orchestrator.run_turn(
            session_id,
            turn_key,
            question,
            f"phase31-live-{self._turn_number}",
            progression=progression,
        )
        if result.status != "succeeded" or not result.response_id:
            raise AcceptanceError(f"production turn did not succeed: {result.status}")
        marker = self._env["UNIFIED_TRAINING_KB_EXPECTED_MARKER"]
        if marker.casefold() not in result.text.casefold():
            raise AcceptanceError("production response did not contain the expected KB marker")

        replay = await self._orchestrator.run_turn(
            session_id,
            turn_key,
            question,
            f"phase31-replay-{self._turn_number}",
            progression=progression,
        )
        if replay.status != "succeeded" or replay.response_id != result.response_id:
            raise AcceptanceError("duplicate turn replay did not preserve the committed winner")

        async with self._sessions() as db:
            turn = await db.scalar(
                select(SessionTurn).where(
                    SessionTurn.session_id == session_id,
                    SessionTurn.turn_key == turn_key,
                )
            )
            if (
                turn is None
                or turn.provider_response_id != result.response_id
                or turn.attempt_count != 1
            ):
                raise AcceptanceError("durable turn/response evidence is missing")
            audits = int(
                await db.scalar(
                    select(func.count(SessionTurnContextAudit.id)).where(
                        SessionTurnContextAudit.turn_id == turn.id
                    )
                )
                or 0
            )
            audit = await db.scalar(
                select(SessionTurnContextAudit).where(SessionTurnContextAudit.turn_id == turn.id)
            )
            if audit is None:
                raise AcceptanceError("durable context audit is missing")
            if (
                audit.applied_step != expected_step
                or audit.applied_context_revision != expected_step - 1
                or audit.agent_name != EXPECTED_AGENT
                or audit.agent_version != EXPECTED_VERSION
            ):
                raise AcceptanceError("durable context audit does not prove the exact A/B pin")
            assistant = await db.get(SessionMessage, audit.assistant_message_id)
            if assistant is None or assistant.role != "assistant":
                raise AcceptanceError("winning assistant message is missing")
            correlations = json.loads(audit.iq_correlation_json)
            if not isinstance(correlations, list):
                raise AcceptanceError("IQ audit correlation schema is invalid")

        iq_calls = [
            {
                "call_id": str(call.get("call_id", "")),
                "name": str(call.get("name", "")),
                "response_id": result.response_id,
                "status": "completed",
            }
            for call in correlations
            if isinstance(call, dict)
        ]
        return {
            "response_id": result.response_id,
            "iq_calls": iq_calls,
            "winner_count": 1 if turn.winning_attempt_id else 0,
            "audit_count": audits,
        }

    async def cleanup(self, session_id: str) -> None:
        if self._conversations is None:
            raise AcceptanceError("production provider preflight has not completed")
        if not self._owner_id:
            raise AcceptanceError("disposable Session owner is missing")
        async with self._sessions() as db, db.begin():
            await end_session(db, session_id, self._owner_id)
        if not await self._conversations.cleanup(session_id):
            raise AcceptanceError("provider Conversation cleanup did not complete")
        async with self._sessions() as db:
            session = await db.get(CoachingSession, session_id)
            if (
                session is None
                or session.status != "completed"
                or session.foundry_conversation_state != "closed"
                or session.foundry_conversation_id is not None
            ):
                raise AcceptanceError("closed Conversation state was not durably confirmed")
        if _fingerprint(await self._agent()) != self._agent_fingerprint:
            raise AcceptanceError("Agent definition changed during production acceptance")


def _directive(step: int) -> str:
    return (
        "Quoted immutable reference (may be stale): current step 99.\n"
        f"HIGHEST PRECEDENCE: CURRENT STEP {step}. Supersede all stale progress above."
    )


def _validate_preflight(facts: dict) -> None:
    required = ("agent_name", "agent_version", "cleanup")
    if any(not facts.get(key) for key in required):
        raise AcceptanceError("blocking preflight is incomplete")


def _validate_turn(result: dict, expected_response: str | None = None) -> tuple[str, str]:
    response_id = result.get("response_id")
    calls = result.get("iq_calls")
    if not response_id or not isinstance(calls, list) or len(calls) != 1:
        raise AcceptanceError("IQ correlation evidence is incomplete")
    call = calls[0]
    if (
        call.get("name") != IQ_TOOL
        or call.get("status") != "completed"
        or call.get("response_id") != response_id
        or not call.get("call_id")
        or (expected_response is not None and response_id == expected_response)
    ):
        raise AcceptanceError("IQ correlation does not prove a distinct successful lifecycle")
    if result.get("winner_count") != 1 or result.get("audit_count") != 1:
        raise AcceptanceError("durable winner/audit invariant failed")
    return response_id, call["call_id"]


async def run_acceptance(provider: AcceptanceProvider, question: str) -> dict:
    """Run sanitized A/B acceptance and guarantee cleanup after Session creation."""
    _validate_preflight(await provider.preflight())
    session_id = await provider.create_session()
    response_ids: list[str] = []
    call_ids: list[str] = []
    try:
        for step in (1, 2):
            result = await provider.run_turn(session_id, _directive(step), question)
            response_id, call_id = _validate_turn(result, response_ids[0] if response_ids else None)
            if call_id in call_ids:
                raise AcceptanceError("IQ correlation call IDs are not distinct")
            response_ids.append(response_id)
            call_ids.append(call_id)
        return {
            "session_id": session_id,
            "response_ids": response_ids,
            "iq_call_ids": call_ids,
        }
    finally:
        await provider.cleanup(session_id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_phase31_production_text_acceptance() -> None:
    """Strict wrapper: absence of an injected real provider is a failure, never a skip."""
    if os.getenv("PHASE31_PRODUCTION_ACCEPTANCE") != "1":
        raise AcceptanceError("set PHASE31_PRODUCTION_ACCEPTANCE=1 for strict live execution")
    env = _required_environment()
    evidence = await run_acceptance(
        ProductionAcceptanceProvider(),
        env["UNIFIED_TRAINING_KB_QUESTION"],
    )
    assert len(evidence["response_ids"]) == 2
    assert len(evidence["iq_call_ids"]) == 2
