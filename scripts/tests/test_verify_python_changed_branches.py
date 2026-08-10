"""Adversarial self-tests for the changed-Python verifier."""

from __future__ import annotations

import importlib.util
import json
import runpy
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "verify_python_changed_branches.py"
SPEC = importlib.util.spec_from_file_location("changed_python_verifier", SCRIPT)
assert SPEC and SPEC.loader
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


def _coverage(
    path: Path, source: str, statement: float = 100, branch: float = 100
) -> None:
    path.write_text(
        json.dumps(
            {
                "meta": {"branch_coverage": True},
                "files": {
                    source: {
                        "executed_lines": [1] if statement == 100 else [],
                        "missing_lines": [] if statement == 100 else [1],
                        "executed_branches": [[1, -1]] if branch == 100 else [],
                        "missing_branches": [] if branch == 100 else [[1, -1]],
                        "summary": {
                            "percent_covered": statement,
                            "percent_covered_branches": branch,
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def _junit(path: Path, test_file: str, *, failures: int = 0, skipped: int = 0) -> None:
    suite = ET.Element(
        "testsuite", tests="1", failures=str(failures), errors="0", skipped=str(skipped)
    )
    ET.SubElement(suite, "testcase", classname=test_file, name="test_gate")
    ET.ElementTree(suite).write(path, encoding="unicode")


def test_parser_exposes_exactly_two_subcommands() -> None:
    parser = VERIFIER._parser()
    subparsers = next(action for action in parser._actions if action.dest == "command")
    assert set(subparsers.choices) == {"snapshot", "verify"}
    with pytest.raises(SystemExit):
        parser.parse_args(["check"])


def test_snapshot_is_atomic_hashed_and_refuses_overwrite(tmp_path, monkeypatch) -> None:
    source = tmp_path / "source.py"
    source.write_text("value = 1\n", encoding="utf-8")
    monkeypatch.setattr(VERIFIER, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        VERIFIER, "_changed_from_baseline", lambda _baseline: {"source.py": "M"}
    )
    output = tmp_path / "snapshot.json"
    VERIFIER.snapshot("abc", output)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["files"][0]["sha256"]
    source.write_text("value = 2\n", encoding="utf-8")
    with pytest.raises(VERIFIER.VerificationError, match="already exists"):
        VERIFIER.snapshot("abc", output)


def test_snapshot_delta_detects_hash_status_and_missing_file(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / "changed.py").write_text("new\n", encoding="utf-8")
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(
        json.dumps(
            {
                "version": 1,
                "baseline": "abc",
                "files": [
                    {"path": "changed.py", "status": "M", "sha256": "old"},
                    {"path": "gone.py", "status": "M", "sha256": "old"},
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(VERIFIER, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        VERIFIER, "_changed_from_baseline", lambda _baseline: {"changed.py": "M"}
    )
    assert VERIFIER._changed_from_snapshot(snapshot) == {
        "changed.py": "M",
        "gone.py": "D",
    }


def test_verify_success_and_coverage_failures(tmp_path, monkeypatch) -> None:
    source = "src/feature.py"
    test = "tests/test_feature.py"
    for name in (source, test):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("pass\n", encoding="utf-8")
    source_manifest = tmp_path / "source.txt"
    test_manifest = tmp_path / "tests.txt"
    source_manifest.write_text(f"{source}\n", encoding="utf-8")
    test_manifest.write_text(f"{test}\n", encoding="utf-8")
    coverage = tmp_path / "coverage.json"
    junit = tmp_path / "junit.xml"
    _coverage(coverage, source)
    _junit(junit, test)
    monkeypatch.setattr(VERIFIER, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        VERIFIER,
        "_changed_from_baseline",
        lambda _baseline: {source: "M", test: "M"},
    )
    monkeypatch.setattr(VERIFIER, "_changed_lines", lambda _baseline, _sources: {source: {1}})
    VERIFIER.verify(coverage, source_manifest, test_manifest, "abc", None, [junit])
    _coverage(coverage, source, statement=99)
    with pytest.raises(VERIFIER.VerificationError, match="uncovered changed statements"):
        VERIFIER.verify(coverage, source_manifest, test_manifest, "abc", None, [junit])
    _coverage(coverage, source, branch=99)
    with pytest.raises(VERIFIER.VerificationError, match="uncovered changed branch arcs"):
        VERIFIER.verify(coverage, source_manifest, test_manifest, "abc", None, [junit])
    _coverage(coverage, "src/missing.py")
    with pytest.raises(VERIFIER.VerificationError, match="absent from coverage"):
        VERIFIER.verify(coverage, source_manifest, test_manifest, "abc", None, [junit])


def test_verify_rejects_malformed_membership_and_bad_reports(
    tmp_path, monkeypatch
) -> None:
    for name in ("src/feature.py", "tests/test_feature.py"):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("pass\n", encoding="utf-8")
    source_manifest = tmp_path / "source.txt"
    test_manifest = tmp_path / "tests.txt"
    source_manifest.write_text("src/feature.py\n", encoding="utf-8")
    test_manifest.write_text("tests/test_feature.py\n", encoding="utf-8")
    coverage = tmp_path / "coverage.json"
    junit = tmp_path / "junit.xml"
    _coverage(coverage, "src/feature.py")
    _junit(junit, "tests/test_feature.py")
    monkeypatch.setattr(VERIFIER, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        VERIFIER,
        "_changed_lines",
        lambda _baseline, _sources: {"src/feature.py": {1}},
    )
    monkeypatch.setattr(
        VERIFIER,
        "_changed_from_baseline",
        lambda _baseline: {
            "src/feature.py": "M",
            "tests/test_feature.py": "M",
            "src/unreviewed.py": "M",
        },
    )
    with pytest.raises(VERIFIER.VerificationError, match="missing="):
        VERIFIER.verify(coverage, source_manifest, test_manifest, "abc", None, [junit])
    monkeypatch.setattr(
        VERIFIER,
        "_changed_from_baseline",
        lambda _baseline: {"src/feature.py": "M"},
    )
    with pytest.raises(VERIFIER.VerificationError, match="stale="):
        VERIFIER.verify(coverage, source_manifest, test_manifest, "abc", None, [junit])
    monkeypatch.setattr(
        VERIFIER,
        "_changed_from_baseline",
        lambda _baseline: {"src/feature.py": "M", "tests/test_feature.py": "M"},
    )
    test_manifest.write_text(
        "src/feature.py\ntests/test_feature.py\n", encoding="utf-8"
    )
    with pytest.raises(VERIFIER.VerificationError, match="dual-classified"):
        VERIFIER.verify(coverage, source_manifest, test_manifest, "abc", None, [junit])
    test_manifest.write_text("tests/test_feature.py\n", encoding="utf-8")
    coverage.write_text("not json", encoding="utf-8")
    with pytest.raises(VERIFIER.VerificationError, match="malformed"):
        VERIFIER.verify(coverage, source_manifest, test_manifest, "abc", None, [junit])
    _coverage(coverage, "src/feature.py")
    _junit(junit, "tests/test_feature.py", skipped=1)
    with pytest.raises(VERIFIER.VerificationError, match="zero fail/error/skip"):
        VERIFIER.verify(coverage, source_manifest, test_manifest, "abc", None, [junit])
    _junit(junit, "other_test.py")
    with pytest.raises(VERIFIER.VerificationError, match="not executed"):
        VERIFIER.verify(coverage, source_manifest, test_manifest, "abc", None, [junit])


def test_cli_returns_failure_for_invalid_snapshot(tmp_path) -> None:
    result = subprocess.run(
        [
            str(Path(__import__("sys").executable)),
            str(SCRIPT),
            "snapshot",
            "--baseline",
            "bad",
            "--output",
            str(tmp_path / "out.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "verification failed" in result.stderr


def test_parse_zero_context_diff_handles_moved_and_deleted_only_hunks() -> None:
    diff = """diff --git a/src/feature.py b/src/feature.py
--- a/src/feature.py
+++ b/src/feature.py
@@ -2,2 +2,0 @@
-old = True
-gone = True
@@ -8 +6,2 @@
-moved = False
+moved = True
+result = moved
"""
    assert VERIFIER._changed_lines_from_diff(diff) == {"src/feature.py": {6, 7}}
    with pytest.raises(VERIFIER.VerificationError, match="malformed diff"):
        VERIFIER._changed_lines_from_diff("@@ not-a-hunk @@\n")


def test_changed_locations_require_covered_statements_and_arcs() -> None:
    source_path = Path(VERIFIER.__file__).resolve().parent / "_synthetic_feature.py"
    source_path.write_text("value = True\nif value:\n    result = value\n", encoding="utf-8")
    entry = {
        "executed_lines": [1, 2, 3],
        "missing_lines": [],
        "executed_branches": [[2, 3], [2, -1]],
        "missing_branches": [],
        "summary": {"num_statements": 2, "num_branches": 2},
    }
    source = "scripts/_synthetic_feature.py"
    try:
        VERIFIER._verify_changed_entry(source, entry, {1, 2, 3})
        uncovered_statement = {**entry, "executed_lines": [1, 2], "missing_lines": [3]}
        with pytest.raises(VERIFIER.VerificationError, match="uncovered changed statements.*3"):
            VERIFIER._verify_changed_entry(source, uncovered_statement, {1, 2, 3})
        uncovered_arc = {**entry, "executed_branches": [[2, 3]], "missing_branches": [[2, -1]]}
        with pytest.raises(VERIFIER.VerificationError, match="uncovered changed branch arcs"):
            VERIFIER._verify_changed_entry(source, uncovered_arc, {1, 2, 3})
        missing_mapping = {**entry, "executed_lines": [1, 2]}
        with pytest.raises(VERIFIER.VerificationError, match="absent from coverage mapping"):
            VERIFIER._verify_changed_entry(source, missing_mapping, {1, 2, 3})
    finally:
        source_path.unlink(missing_ok=True)


def test_executable_lines_exclude_docstrings_and_structural_declarations() -> None:
    source_path = Path(VERIFIER.__file__).resolve().parent / "_synthetic_structure.py"
    source_path.write_text(
        '"""Module docs."""\n\nclass Example:\n    """Class docs."""\n\n'
        '    def method(self):\n        """Method docs."""\n        return 1\n',
        encoding="utf-8",
    )
    try:
        assert VERIFIER._executable_lines("scripts/_synthetic_structure.py") == {8}
    finally:
        source_path.unlink(missing_ok=True)


def test_normalizes_windows_paths_without_losing_drive() -> None:
    assert VERIFIER._normal(r"frontend\src\feature.py") == "frontend/src/feature.py"
    assert VERIFIER._coverage_entry(
        {r"C:\repo\backend\app\feature.py": {"executed_lines": [1]}},
        "backend/app/feature.py",
    ) == {"executed_lines": [1]}


def test_git_and_changed_baseline_cover_success_failure_rename_and_untracked(monkeypatch) -> None:
    calls: list[tuple[str, ...]] = []

    def successful_run(command, **_kwargs):
        assert command[:2] == ["git", "-C"]
        return SimpleNamespace(returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr(VERIFIER.subprocess, "run", successful_run)
    assert VERIFIER._git("status") == "ok\n"

    for stderr, message in [("fatal detail", "fatal detail"), ("", "git command failed")]:
        monkeypatch.setattr(
            VERIFIER.subprocess,
            "run",
            lambda *_args, stderr=stderr, **_kwargs: SimpleNamespace(
                returncode=1, stdout="", stderr=stderr
            ),
        )
        with pytest.raises(VERIFIER.VerificationError, match=message):
            VERIFIER._git("status")

    with pytest.raises(VERIFIER.VerificationError, match="baseline SHA"):
        VERIFIER._changed_from_baseline("")

    def fake_git(*args):
        calls.append(args)
        if args[0] == "cat-file":
            return ""
        if args[0] == "diff":
            return "M\tsrc/a.py\nR100\tsrc/old.py\tsrc/new.py\nA\tsrc/new file.py\n"
        return "src/untracked.py\n"

    monkeypatch.setattr(VERIFIER, "_git", fake_git)
    assert VERIFIER._changed_from_baseline("abc") == {
        "src/a.py": "M",
        "src/new.py": "R",
        "src/new file.py": "A",
        "src/untracked.py": "A",
    }
    assert calls[0] == ("cat-file", "-e", "abc^{commit}")


def test_changed_lines_tracks_diff_and_all_untracked_lines(tmp_path, monkeypatch) -> None:
    tracked = "src/tracked.py"
    untracked = "src/untracked.py"
    target = tmp_path / untracked
    target.parent.mkdir(parents=True)
    target.write_text("one\ntwo\nthree\n", encoding="utf-8")
    monkeypatch.setattr(VERIFIER, "_repo_root", lambda: tmp_path)

    def fake_git(*args):
        if args[:2] == ("ls-files", "--"):
            return f"{args[-1]}\n" if args[-1] == tracked else ""
        assert args[0] == "diff"
        return """diff --git a/src/tracked.py b/src/tracked.py
--- a/src/tracked.py
+++ b/src/tracked.py
@@ -4 +4,2 @@
 context
+changed = True
\\ No newline at end of file
"""

    monkeypatch.setattr(VERIFIER, "_git", fake_git)
    assert VERIFIER._changed_lines("abc", {tracked, untracked, "src/absent.py"}) == {
        tracked: {5},
        untracked: {1, 2, 3},
    }


def test_hash_facts_manifest_percent_and_atomic_cleanup(tmp_path, monkeypatch) -> None:
    present = tmp_path / "present.py"
    present.write_text("value = 1\n", encoding="utf-8")
    monkeypatch.setattr(VERIFIER, "_repo_root", lambda: tmp_path)
    assert VERIFIER._sha256(tmp_path / "missing.py") is None
    assert len(VERIFIER._sha256(present)) == 64
    facts = VERIFIER._facts({"missing.py": "D", "present.py": "M"})
    assert [item["path"] for item in facts] == ["missing.py", "present.py"]
    assert facts[0]["sha256"] is None and facts[1]["sha256"]

    manifest = tmp_path / "manifest.txt"
    manifest.write_text("# comment\n\nfolder\\test.py\n", encoding="utf-8")
    assert VERIFIER._manifest(manifest) == {"folder/test.py"}
    manifest.write_text("# comment only\n", encoding="utf-8")
    with pytest.raises(VERIFIER.VerificationError, match="manifest is empty"):
        VERIFIER._manifest(manifest)
    with pytest.raises(VERIFIER.VerificationError, match="cannot read manifest"):
        VERIFIER._manifest(tmp_path / "absent.txt")

    assert VERIFIER._percent({"rate": 75}, "rate", "covered", "total") == 75
    assert VERIFIER._percent({"rate": {"percent": 80}}, "rate", "covered", "total") == 80
    assert VERIFIER._percent({"covered": 0, "total": 0}, "rate", "covered", "total") == 100
    assert VERIFIER._percent({"covered": 1, "total": 4}, "rate", "covered", "total") == 25
    with pytest.raises(VERIFIER.VerificationError, match="lacks rate"):
        VERIFIER._percent({}, "rate", "covered", "total")

    monkeypatch.setattr(VERIFIER, "_changed_from_baseline", lambda _baseline: {})
    monkeypatch.setattr(VERIFIER.os, "replace", lambda *_args: (_ for _ in ()).throw(OSError()))
    output = tmp_path / "snapshot.json"
    with pytest.raises(OSError):
        VERIFIER.snapshot("abc", output)
    assert not list(tmp_path.glob(".snapshot.json.*"))


def test_coverage_and_junit_defensive_schemas(tmp_path) -> None:
    coverage = tmp_path / "coverage.json"
    coverage.write_text("[]", encoding="utf-8")
    with pytest.raises(VERIFIER.VerificationError, match="files object"):
        VERIFIER._verify_coverage(coverage, {"source.py"}, {})
    coverage.write_text(json.dumps({"meta": {"branch_coverage": False}, "files": {}}))
    with pytest.raises(VERIFIER.VerificationError, match="not branch-aware"):
        VERIFIER._verify_coverage(coverage, {"source.py"}, {})
    coverage.write_text(json.dumps({"meta": {}, "files": {}}))
    with pytest.raises(VERIFIER.VerificationError, match="absent from coverage"):
        VERIFIER._verify_coverage(coverage, {"source.py"}, {})

    with pytest.raises(VERIFIER.VerificationError, match="at least one"):
        VERIFIER._verify_junit([], set())
    malformed = tmp_path / "malformed.xml"
    malformed.write_text("<broken", encoding="utf-8")
    with pytest.raises(VERIFIER.VerificationError, match="malformed"):
        VERIFIER._verify_junit([malformed], set())
    empty = tmp_path / "empty.xml"
    empty.write_text("<root />", encoding="utf-8")
    with pytest.raises(VERIFIER.VerificationError, match="no testsuite"):
        VERIFIER._verify_junit([empty], set())
    invalid = tmp_path / "invalid.xml"
    invalid.write_text('<testsuite tests="bad" />', encoding="utf-8")
    with pytest.raises(VERIFIER.VerificationError, match="invalid JUnit tests"):
        VERIFIER._verify_junit([invalid], set())
    suites = tmp_path / "suites.xml"
    suites.write_text(
        '<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0">'
        '<testcase classname="tests/test_ok.py" /></testsuite></testsuites>',
        encoding="utf-8",
    )
    VERIFIER._verify_junit([suites], {"tests/test_ok.py"})


def test_invalid_snapshot_ambiguous_coverage_and_unparseable_source_fail_closed(
    tmp_path, monkeypatch
) -> None:
    invalid = tmp_path / "snapshot.json"
    invalid.write_text("[]", encoding="utf-8")
    with pytest.raises(VERIFIER.VerificationError, match="invalid start snapshot"):
        VERIFIER._changed_from_snapshot(invalid)

    with pytest.raises(VERIFIER.VerificationError, match="ambiguous coverage"):
        VERIFIER._coverage_entry(
            {"repo/src/feature.py": {}, "other/src/feature.py": {}},
            "src/feature.py",
        )

    monkeypatch.setattr(VERIFIER, "_repo_root", lambda: tmp_path)
    bad = tmp_path / "bad.py"
    bad.write_text("if", encoding="utf-8")
    with pytest.raises(VERIFIER.VerificationError, match="cannot parse"):
        VERIFIER._executable_lines("bad.py")
    with pytest.raises(VERIFIER.VerificationError, match="cannot parse"):
        VERIFIER._executable_lines("missing.py")


def test_verify_snapshot_identity_missing_paths_main_and_module_entry(tmp_path, monkeypatch, capsys) -> None:
    source_manifest = tmp_path / "sources.txt"
    test_manifest = tmp_path / "tests.txt"
    coverage = tmp_path / "coverage.json"
    junit = tmp_path / "junit.xml"
    source_manifest.write_text("src/feature.py\n", encoding="utf-8")
    test_manifest.write_text("tests/test_feature.py\n", encoding="utf-8")
    monkeypatch.setattr(VERIFIER, "_repo_root", lambda: tmp_path)
    with pytest.raises(VERIFIER.VerificationError, match="exactly one"):
        VERIFIER.verify(coverage, source_manifest, test_manifest, None, None, [junit])
    with pytest.raises(VERIFIER.VerificationError, match="exactly one"):
        VERIFIER.verify(
            coverage,
            source_manifest,
            test_manifest,
            "abc",
            tmp_path / "start.json",
            [junit],
        )
    monkeypatch.setattr(
        VERIFIER,
        "_changed_from_snapshot",
        lambda _path: {"src/feature.py": "M", "tests/test_feature.py": "M"},
    )
    with pytest.raises(VERIFIER.VerificationError, match="paths do not exist"):
        VERIFIER.verify(coverage, source_manifest, test_manifest, None, tmp_path / "start.json", [junit])
    for name in ("src/feature.py", "tests/test_feature.py"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("pass\n", encoding="utf-8")
    with pytest.raises(VERIFIER.VerificationError, match="explicit recorded baseline"):
        VERIFIER.verify(coverage, source_manifest, test_manifest, None, tmp_path / "start.json", [junit])

    monkeypatch.setattr(VERIFIER, "snapshot", lambda *_args: None)
    assert VERIFIER.main(["snapshot", "--baseline", "abc", "--output", str(tmp_path / "out")]) == 0
    monkeypatch.setattr(VERIFIER, "verify", lambda *_args: None)
    assert VERIFIER.main([
        "verify", "--coverage-json", str(coverage), "--source-manifest", str(source_manifest),
        "--test-manifest", str(test_manifest), "--baseline", "abc", "--junit", str(junit),
    ]) == 0
    monkeypatch.setattr(
        VERIFIER,
        "snapshot",
        lambda *_args: (_ for _ in ()).throw(VERIFIER.VerificationError("expected")),
    )
    assert VERIFIER.main(["snapshot", "--baseline", "abc", "--output", str(tmp_path / "out")]) == 1
    assert "verification failed: expected" in capsys.readouterr().err

    old_argv = sys.argv
    sys.argv = [str(SCRIPT), "snapshot", "--baseline", "bad", "--output", str(tmp_path / "entry")]
    try:
        with pytest.raises(SystemExit) as exit_info:
            runpy.run_path(str(SCRIPT), run_name="__main__")
        assert exit_info.value.code == 1
    finally:
        sys.argv = old_argv
