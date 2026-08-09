"""Offline acceptance-harness tests using a deterministic fake production provider."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parent / "integration" / "test_phase31_production_text_acceptance.py"
)  # noqa: E501
SPEC = importlib.util.spec_from_file_location("phase31_production_acceptance", SCRIPT)
assert SPEC and SPEC.loader
HARNESS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HARNESS)


class FakeProvider:
    def __init__(self, *, fail_turn: int | None = None, bad_iq: bool = False) -> None:
        self.fail_turn = fail_turn
        self.bad_iq = bad_iq
        self.cleaned = False
        self.directives: list[str] = []

    async def preflight(self):
        return {"agent_name": "Dr-Chen-Jun", "agent_version": "5", "cleanup": True}

    async def create_session(self):
        return "session-disposable"

    async def run_turn(self, session_id: str, directive: str, question: str):
        del session_id, question
        index = len(self.directives) + 1
        self.directives.append(directive)
        if self.fail_turn == index:
            raise RuntimeError("provider failure")
        return {
            "response_id": f"response-{index}",
            "text": f"followed-step-{index}",
            "iq_calls": [
                {
                    "call_id": f"call-{index}",
                    "name": "other" if self.bad_iq else "knowledge_base_retrieve",
                    "response_id": f"response-{index}",
                    "status": "completed",
                }
            ],
            "winner_count": 1,
            "audit_count": 1,
        }

    async def cleanup(self, session_id: str):
        assert session_id == "session-disposable"
        self.cleaned = True


@pytest.mark.asyncio
async def test_offline_harness_proves_ab_iq_winners_and_cleanup() -> None:
    provider = FakeProvider()
    result = await HARNESS.run_acceptance(provider, "question")
    assert result["session_id"] == "session-disposable"
    assert result["response_ids"] == ["response-1", "response-2"]
    assert result["iq_call_ids"] == ["call-1", "call-2"]
    assert "CURRENT STEP 1" in provider.directives[0]
    assert "CURRENT STEP 2" in provider.directives[1]
    assert provider.cleaned is True


@pytest.mark.asyncio
async def test_offline_harness_fails_bad_iq_and_always_cleans_up() -> None:
    provider = FakeProvider(bad_iq=True)
    with pytest.raises(HARNESS.AcceptanceError, match="IQ correlation"):
        await HARNESS.run_acceptance(provider, "question")
    assert provider.cleaned is True


@pytest.mark.asyncio
async def test_offline_harness_cleans_up_after_provider_failure() -> None:
    provider = FakeProvider(fail_turn=2)
    with pytest.raises(RuntimeError, match="provider failure"):
        await HARNESS.run_acceptance(provider, "question")
    assert provider.cleaned is True


@pytest.mark.asyncio
async def test_preflight_failure_happens_before_session_creation() -> None:
    class BadPreflight(FakeProvider):
        async def preflight(self):
            return {"agent_name": "", "agent_version": "5", "cleanup": True}

    provider = BadPreflight()
    with pytest.raises(HARNESS.AcceptanceError, match="preflight"):
        await HARNESS.run_acceptance(provider, "question")
    assert provider.cleaned is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"response_id": ""},
        {"iq_calls": []},
        {"iq_calls": "bad"},
        {"winner_count": 0},
        {"audit_count": 0},
    ],
)
async def test_harness_rejects_incomplete_turn_evidence(overrides: dict) -> None:
    class InvalidTurn(FakeProvider):
        async def run_turn(self, session_id: str, directive: str, question: str):
            result = await super().run_turn(session_id, directive, question)
            result.update(overrides)
            return result

    provider = InvalidTurn()
    with pytest.raises(HARNESS.AcceptanceError):
        await HARNESS.run_acceptance(provider, "question")
    assert provider.cleaned is True


@pytest.mark.asyncio
async def test_harness_rejects_reused_iq_call_id() -> None:
    class ReusedCall(FakeProvider):
        async def run_turn(self, session_id: str, directive: str, question: str):
            result = await super().run_turn(session_id, directive, question)
            result["iq_calls"][0]["call_id"] = "same-call"
            return result

    provider = ReusedCall()
    with pytest.raises(HARNESS.AcceptanceError, match="not distinct"):
        await HARNESS.run_acceptance(provider, "question")
    assert provider.cleaned is True


@pytest.mark.asyncio
async def test_strict_live_wrapper_fails_without_or_with_opt_in(monkeypatch) -> None:
    monkeypatch.delenv("PHASE31_PRODUCTION_ACCEPTANCE", raising=False)
    with pytest.raises(HARNESS.AcceptanceError, match="set PHASE31"):
        await HARNESS.test_phase31_production_text_acceptance()

    monkeypatch.setenv("PHASE31_PRODUCTION_ACCEPTANCE", "1")
    for name in HARNESS._REQUIRED_ENV:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(HARNESS.AcceptanceError, match="blocking environment"):
        await HARNESS.test_phase31_production_text_acceptance()


@pytest.mark.asyncio
async def test_strict_live_wrapper_runs_the_production_provider(monkeypatch) -> None:
    monkeypatch.setenv("PHASE31_PRODUCTION_ACCEPTANCE", "1")
    for name in HARNESS._REQUIRED_ENV:
        monkeypatch.setenv(name, f"configured-{name.casefold()}")

    provider = object()
    monkeypatch.setattr(HARNESS, "ProductionAcceptanceProvider", lambda: provider)
    run = pytest.MonkeyPatch()

    async def fake_run_acceptance(candidate, question):
        assert candidate is provider
        assert question == "configured-unified_training_kb_question"
        return {
            "response_ids": ["response-a", "response-b"],
            "iq_call_ids": ["call-a", "call-b"],
        }

    run.setattr(HARNESS, "run_acceptance", fake_run_acceptance)
    try:
        await HARNESS.test_phase31_production_text_acceptance()
    finally:
        run.undo()


def test_required_environment_returns_only_complete_inputs(monkeypatch) -> None:
    for name in HARNESS._REQUIRED_ENV:
        monkeypatch.setenv(name, f" value-{name} ")

    values = HARNESS._required_environment()

    assert values["UNIFIED_TRAINING_KB_QUESTION"] == "value-UNIFIED_TRAINING_KB_QUESTION"
    assert set(values) == set(HARNESS._REQUIRED_ENV)


def test_allowed_tool_names_supports_list_and_sdk_container() -> None:
    list_tool = type("Tool", (), {"allowed_tools": ["knowledge_base_retrieve"]})()
    sdk_allowed = type("Allowed", (), {"tool_names": ["knowledge_base_retrieve"]})()
    sdk_tool = type("Tool", (), {"allowed_tools": sdk_allowed})()
    empty_tool = type("Tool", (), {"allowed_tools": None})()

    assert HARNESS._allowed_tool_names(list_tool) == ["knowledge_base_retrieve"]
    assert HARNESS._allowed_tool_names(sdk_tool) == ["knowledge_base_retrieve"]
    assert HARNESS._allowed_tool_names(empty_tool) == []
