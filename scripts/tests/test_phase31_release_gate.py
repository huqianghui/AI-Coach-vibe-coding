"""Behavior tests for the Phase 31 one-shot release gate."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "phase31_release_gate.py"
SPEC = importlib.util.spec_from_file_location("phase31_release_gate", SCRIPT)
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def test_release_refuses_second_commit_or_push(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.json"
    GATE.assert_release_unused(ledger, 0)
    ledger.write_text(json.dumps({"push_attempts": [{"id": "one"}]}), encoding="utf-8")
    with pytest.raises(GATE.ReleaseError, match="push attempt already recorded"):
        GATE.assert_release_unused(ledger, 0)
    ledger.unlink()
    with pytest.raises(GATE.ReleaseError, match="commit count changed"):
        GATE.assert_release_unused(ledger, 1)


def test_release_rejects_malformed_ledger_and_covers_default_runner(tmp_path: Path, monkeypatch) -> None:
    ledger = tmp_path / "ledger.json"
    ledger.write_text("not-json", encoding="utf-8")
    with pytest.raises(GATE.ReleaseError, match="invalid release ledger"):
        GATE.assert_release_unused(ledger, 0)
    ledger.write_text('{"push_attempts": "bad"}', encoding="utf-8")
    with pytest.raises(GATE.ReleaseError, match="invalid release ledger schema"):
        GATE.assert_release_unused(ledger, 0)

    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    monkeypatch.setattr(GATE.subprocess, "run", lambda *args, **kwargs: Result())
    assert GATE._runner(["git", "status"]) == (0, "ok", "")


def test_push_failure_is_receipted_once(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.json"
    calls: list[list[str]] = []

    def runner(command: list[str]):
        calls.append(command)
        return 1, "", "network unavailable"

    receipt = GATE.push_once(ledger, "feature", "abc123", runner=runner)
    assert receipt["exit_code"] == 1
    assert receipt["stderr_sha256"]
    assert len(calls) == 1
    with pytest.raises(GATE.ReleaseError, match="push attempt already recorded"):
        GATE.push_once(ledger, "feature", "abc123", runner=runner)
    assert len(calls) == 1


def test_remote_mismatch_and_post_freeze_allowlist_fail_closed(tmp_path: Path) -> None:
    GATE.verify_remote("same", "same")
    with pytest.raises(GATE.ReleaseError, match="remote SHA mismatch"):
        GATE.verify_remote("local", "remote")
    allowlist = tmp_path / "allowlist.txt"
    allowlist.write_text("receipt.md\nsummary.md\n", encoding="utf-8")
    GATE.verify_post_freeze_paths(allowlist, {"receipt.md", "summary.md"})
    with pytest.raises(GATE.ReleaseError, match="post-freeze path mismatch"):
        GATE.verify_post_freeze_paths(allowlist, {"receipt.md", "source.py"})
    with pytest.raises(GATE.ReleaseError, match="cannot read post-freeze allowlist"):
        GATE.verify_post_freeze_paths(tmp_path / "missing.txt", set())


def test_receipt_verifier_requires_success_when_remote_equality_requested(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.json"
    ledger.write_text(
        json.dumps(
            {
                "push_attempts": [
                    {"exit_code": 1, "local_sha": "abc", "remote_sha": None}
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(GATE.ReleaseError, match="push did not succeed"):
        GATE.verify_receipt(ledger, expect_push_attempts=1, require_remote_equals_local=True)
    with pytest.raises(GATE.ReleaseError, match="push attempt count mismatch"):
        GATE.verify_receipt(ledger, expect_push_attempts=2, require_remote_equals_local=False)
    assert GATE.verify_receipt(
        ledger,
        expect_push_attempts=1,
        require_remote_equals_local=False,
    )["push_attempts"][0]["exit_code"] == 1


def test_successful_push_receipt_and_remote_equality(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.json"

    def runner(_command: list[str]):
        return 0, "pushed", ""

    attempt = GATE.push_once(ledger, "feature", "abc", runner=runner)
    payload = json.loads(ledger.read_text(encoding="utf-8"))
    payload["push_attempts"][0]["remote_sha"] = "abc"
    ledger.write_text(json.dumps(payload), encoding="utf-8")
    assert attempt["exit_code"] == 0
    assert GATE.verify_receipt(
        ledger,
        expect_push_attempts=1,
        require_remote_equals_local=True,
    )["push_attempts"][0]["remote_sha"] == "abc"
