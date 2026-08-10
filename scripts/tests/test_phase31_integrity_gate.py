"""Behavior tests for the Phase 31 integrity gate."""

from __future__ import annotations

import importlib.util
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "phase31_integrity_gate.py"
SPEC = importlib.util.spec_from_file_location("phase31_integrity_gate", SCRIPT)
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def test_protected_manifest_detects_mutation(tmp_path: Path) -> None:
    protected = tmp_path / "protected.txt"
    protected.write_text("before", encoding="utf-8")
    manifest = GATE.capture_manifest(tmp_path, ["protected.txt"])
    GATE.verify_manifest(tmp_path, manifest)
    protected.write_text("after", encoding="utf-8")
    with pytest.raises(GATE.IntegrityError, match="protected mutation"):
        GATE.verify_manifest(tmp_path, manifest)


def test_forbidden_sweep_rejects_dangerous_release_and_agent_patterns(tmp_path: Path) -> None:
    safe = tmp_path / "safe.py"
    safe.write_text("value = 1\n", encoding="utf-8")
    GATE.forbidden_sweep(tmp_path, ["safe.py"])
    safe.write_text("run('git add .')\n", encoding="utf-8")
    with pytest.raises(GATE.IntegrityError, match="broad git add"):
        GATE.forbidden_sweep(tmp_path, ["safe.py"])
    safe.write_text("agents.update(name)\n", encoding="utf-8")
    with pytest.raises(GATE.IntegrityError, match="Agent write"):
        GATE.forbidden_sweep(tmp_path, ["safe.py"])


def test_forbidden_sweep_rejects_missing_non_utf8_and_other_patterns(tmp_path: Path) -> None:
    with pytest.raises(GATE.IntegrityError, match="sweep path missing"):
        GATE.forbidden_sweep(tmp_path, ["missing.py"])
    source = tmp_path / "source.py"
    source.write_bytes(b"\xff")
    with pytest.raises(GATE.IntegrityError, match="not UTF-8"):
        GATE.forbidden_sweep(tmp_path, ["source.py"])
    for text, message in [
        ("git reset --hard", "destructive Git command"),
        ("previous_response_id = value", "forbidden Session response field"),
    ]:
        source.write_text(text, encoding="utf-8")
        with pytest.raises(GATE.IntegrityError, match=message):
            GATE.forbidden_sweep(tmp_path, ["source.py"])


def _junit(path: Path, *, tests: int = 1, failures: int = 0, skipped: int = 0) -> None:
    suite = ET.Element(
        "testsuite",
        tests=str(tests),
        failures=str(failures),
        errors="0",
        skipped=str(skipped),
    )
    ET.SubElement(suite, "testcase", name="test_acceptance")
    ET.ElementTree(suite).write(path, encoding="unicode")


def test_report_gate_rejects_skipped_junit_and_playwright(tmp_path: Path) -> None:
    junit = tmp_path / "result.xml"
    _junit(junit)
    playwright = tmp_path / "playwright.json"
    playwright.write_text(
        json.dumps({"suites": [{"specs": [{"tests": [{"results": [{"status": "passed"}]}]}]}]}),
        encoding="utf-8",
    )
    assert GATE.verify_reports([junit], [playwright]) == (2, 0, 0)
    _junit(junit, skipped=1)
    with pytest.raises(GATE.IntegrityError, match="zero skipped"):
        GATE.verify_reports([junit], [playwright])


def test_report_gate_rejects_malformed_empty_failed_and_zero_reports(tmp_path: Path) -> None:
    junit = tmp_path / "junit.xml"
    playwright = tmp_path / "playwright.json"
    with pytest.raises(GATE.IntegrityError, match="no machine-readable"):
        GATE.verify_reports([], [])
    junit.write_text("<broken", encoding="utf-8")
    with pytest.raises(GATE.IntegrityError, match="invalid JUnit report"):
        GATE.verify_reports([junit], [])
    junit.write_text("<testsuites />", encoding="utf-8")
    with pytest.raises(GATE.IntegrityError, match="no suite"):
        GATE.verify_reports([junit], [])
    junit.write_text('<testsuite tests="bad" />', encoding="utf-8")
    with pytest.raises(GATE.IntegrityError, match="invalid JUnit counters"):
        GATE.verify_reports([junit], [])
    playwright.write_text("not-json", encoding="utf-8")
    with pytest.raises(GATE.IntegrityError, match="invalid Playwright report"):
        GATE.verify_reports([], [playwright])
    playwright.write_text('{"suites": "bad"}', encoding="utf-8")
    with pytest.raises(GATE.IntegrityError, match="invalid Playwright report schema"):
        GATE.verify_reports([], [playwright])
    playwright.write_text(
        json.dumps(
            {
                "suites": [
                    {
                        "specs": [{"tests": [{"results": [{"status": "failed"}]}]}],
                        "suites": [
                            {
                                "specs": [
                                    {"tests": [{"results": [{"status": "passed"}]}]}
                                ]
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(GATE.IntegrityError, match="zero failed"):
        GATE.verify_reports([], [playwright])
    _junit(junit)
    playwright.write_text(
        json.dumps({"suites": [{"specs": [{"tests": [{"results": [{"status": "skipped"}]}]}]}]}),
        encoding="utf-8",
    )
    with pytest.raises(GATE.IntegrityError, match="zero skipped"):
        GATE.verify_reports([junit], [playwright])


def test_exact_allowlist_rejects_status_hash_and_extra_path(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    source.write_text("value = 1\n", encoding="utf-8")
    allowlist = GATE.build_allowlist(tmp_path, {"source.py": "M"})
    GATE.verify_allowlist(tmp_path, allowlist, {"source.py": "M"})
    with pytest.raises(GATE.IntegrityError, match="allowlist membership"):
        GATE.verify_allowlist(tmp_path, allowlist, {"source.py": "M", "extra.py": "A"})
    with pytest.raises(GATE.IntegrityError, match="allowlist status"):
        GATE.verify_allowlist(tmp_path, allowlist, {"source.py": "A"})
    source.write_text("value = 2\n", encoding="utf-8")
    with pytest.raises(GATE.IntegrityError, match="allowlist hash"):
        GATE.verify_allowlist(tmp_path, allowlist, {"source.py": "M"})
