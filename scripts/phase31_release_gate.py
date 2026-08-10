"""One-shot Phase 31 commit/push transaction primitives and receipt verification."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable
from uuid import uuid4


class ReleaseError(RuntimeError):
    """Raised when one-commit/one-push release invariants are violated."""


def _load_ledger(path: Path) -> dict:
    if not path.exists():
        return {"push_attempts": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseError(f"invalid release ledger: {path}: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("push_attempts"), list):
        raise ReleaseError("invalid release ledger schema")
    return payload


def _write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def assert_release_unused(ledger: Path, commits_since_baseline: int) -> None:
    if commits_since_baseline:
        raise ReleaseError("baseline commit count changed; refusing second commit")
    if _load_ledger(ledger)["push_attempts"]:
        raise ReleaseError("push attempt already recorded; refusing retry")


def _runner(command: list[str]) -> tuple[int, str, str]:
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def push_once(
    ledger_path: Path,
    branch: str,
    local_sha: str,
    *,
    runner: Callable[[list[str]], tuple[int, str, str]] = _runner,
) -> dict:
    """Atomically record intent before making exactly one push attempt."""
    ledger = _load_ledger(ledger_path)
    if ledger["push_attempts"]:
        raise ReleaseError("push attempt already recorded; refusing retry")
    command = ["git", "push", "origin", branch]
    attempt = {
        "id": uuid4().hex,
        "timestamp": datetime.now(UTC).isoformat(),
        "branch": branch,
        "local_sha": local_sha,
        "command_sha256": _digest("\0".join(command)),
        "exit_code": None,
    }
    ledger["push_attempts"].append(attempt)
    _write_atomic(ledger_path, ledger)
    exit_code, stdout, stderr = runner(command)
    attempt.update(
        {
            "exit_code": exit_code,
            "stdout_sha256": _digest(stdout),
            "stderr_sha256": _digest(stderr),
        }
    )
    _write_atomic(ledger_path, ledger)
    return attempt


def verify_remote(local_sha: str, remote_sha: str | None) -> None:
    if not remote_sha or remote_sha != local_sha:
        raise ReleaseError(f"remote SHA mismatch: local={local_sha}, remote={remote_sha}")


def verify_post_freeze_paths(allowlist_path: Path, changed_paths: set[str]) -> None:
    try:
        allowed = {
            line.strip().replace("\\", "/")
            for line in allowlist_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
    except OSError as exc:
        raise ReleaseError(f"cannot read post-freeze allowlist: {exc}") from exc
    normalized = {path.replace("\\", "/") for path in changed_paths}
    if normalized != allowed:
        raise ReleaseError(
            f"post-freeze path mismatch: actual={sorted(normalized)}, expected={sorted(allowed)}"
        )


def verify_receipt(
    ledger_path: Path,
    *,
    expect_push_attempts: int,
    require_remote_equals_local: bool,
) -> dict:
    ledger = _load_ledger(ledger_path)
    attempts = ledger["push_attempts"]
    if len(attempts) != expect_push_attempts:
        raise ReleaseError(
            f"push attempt count mismatch: actual={len(attempts)}, expected={expect_push_attempts}"
        )
    attempt = attempts[-1] if attempts else {}
    if require_remote_equals_local:
        if attempt.get("exit_code") != 0:
            raise ReleaseError("push did not succeed")
        verify_remote(attempt.get("local_sha", ""), attempt.get("remote_sha"))
    return ledger
