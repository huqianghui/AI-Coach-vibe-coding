"""Deterministic Phase 31 protected-content, report, and allowlist integrity gate."""

from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable


class IntegrityError(RuntimeError):
    """Raised when release integrity evidence is incomplete or inconsistent."""


def _normal(path: str | Path) -> str:
    return str(path).replace("\\", "/").removeprefix("./")


def _sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def capture_manifest(root: Path, paths: Iterable[str]) -> dict[str, dict[str, str | int | None]]:
    """Capture exact path, digest, and size without following broad mutable globs."""
    manifest = {}
    for name in sorted({_normal(path) for path in paths}):
        target = root / name
        manifest[name] = {
            "sha256": _sha(target),
            "size": target.stat().st_size if target.is_file() else None,
        }
    return manifest


def verify_manifest(root: Path, manifest: dict[str, dict[str, str | int | None]]) -> None:
    current = capture_manifest(root, manifest)
    if current != manifest:
        changed = sorted(path for path in manifest if current.get(path) != manifest[path])
        raise IntegrityError(f"protected mutation detected: {changed}")


FORBIDDEN = (
    (
        re.compile(r"\bgit\s+add\s+(?:\.(?=[\s'\")\]]|$)|-A\b|--all\b)", re.I),
        "broad git add",
    ),
    (re.compile(r"\bgit\s+(?:clean|reset|stash)\b", re.I), "destructive Git command"),
    (re.compile(r"\bagents\.(?:create|update|delete|publish|create_version)\s*\(", re.I), "Agent write"),
    (re.compile(r"previous_response_id|tool_choice", re.I), "forbidden Session response field"),
)


def forbidden_sweep(root: Path, paths: Iterable[str]) -> None:
    """Reject release-dangerous source text from a reviewed finite path set."""
    for name in sorted({_normal(path) for path in paths}):
        target = root / name
        if not target.is_file():
            raise IntegrityError(f"sweep path missing: {name}")
        try:
            text = target.read_text(encoding="utf-8")
        except UnicodeError as exc:
            raise IntegrityError(f"sweep path is not UTF-8 text: {name}") from exc
        for pattern, description in FORBIDDEN:
            if pattern.search(text):
                raise IntegrityError(f"{description} found in {name}")


def _junit_counts(path: Path) -> tuple[int, int, int]:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise IntegrityError(f"invalid JUnit report: {path}: {exc}") from exc
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    if not suites:
        raise IntegrityError(f"JUnit report has no suite: {path}")
    top = suites[0]
    try:
        tests = int(top.attrib.get("tests", 0))
        failed = int(top.attrib.get("failures", 0)) + int(top.attrib.get("errors", 0))
        skipped = int(top.attrib.get("skipped", 0))
    except ValueError as exc:
        raise IntegrityError(f"invalid JUnit counters: {path}") from exc
    return tests - failed - skipped, failed, skipped


def _playwright_counts(path: Path) -> tuple[int, int, int]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IntegrityError(f"invalid Playwright report: {path}: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("suites"), list):
        raise IntegrityError(f"invalid Playwright report schema: {path}")
    passed = failed = skipped = 0

    def walk(suite: dict) -> None:
        nonlocal passed, failed, skipped
        for spec in suite.get("specs", []):
            for test in spec.get("tests", []):
                for result in test.get("results", []):
                    status = result.get("status")
                    if status == "passed":
                        passed += 1
                    elif status == "skipped":
                        skipped += 1
                    else:
                        failed += 1
        for child in suite.get("suites", []):
            walk(child)

    for suite in payload["suites"]:
        walk(suite)
    return passed, failed, skipped


def verify_reports(junit: Iterable[Path], playwright: Iterable[Path]) -> tuple[int, int, int]:
    counts = [_junit_counts(path) for path in junit]
    counts.extend(_playwright_counts(path) for path in playwright)
    if not counts:
        raise IntegrityError("no machine-readable reports supplied")
    passed = sum(item[0] for item in counts)
    failed = sum(item[1] for item in counts)
    skipped = sum(item[2] for item in counts)
    if passed <= 0 or failed or skipped:
        raise IntegrityError(
            f"reports require nonzero passed and zero failed/zero skipped: "
            f"passed={passed}, failed={failed}, skipped={skipped}"
        )
    return passed, failed, skipped


def build_allowlist(root: Path, statuses: dict[str, str]) -> dict[str, dict[str, str | None]]:
    return {
        _normal(path): {"status": status, "sha256": _sha(root / _normal(path))}
        for path, status in sorted(statuses.items())
    }


def verify_allowlist(
    root: Path,
    allowlist: dict[str, dict[str, str | None]],
    statuses: dict[str, str],
) -> None:
    normalized = {_normal(path): status for path, status in statuses.items()}
    if set(normalized) != set(allowlist):
        raise IntegrityError(
            f"allowlist membership mismatch: actual={sorted(normalized)}, expected={sorted(allowlist)}"
        )
    for path, expected in allowlist.items():
        if normalized[path] != expected["status"]:
            raise IntegrityError(f"allowlist status mismatch: {path}")
        if _sha(root / path) != expected["sha256"]:
            raise IntegrityError(f"allowlist hash mismatch: {path}")
