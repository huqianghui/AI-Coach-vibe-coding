"""Deterministic changed-Python statement/branch coverage and test-execution gate."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
from typing import Any

PYTHON_SUFFIXES = {".py"}


class VerificationError(RuntimeError):
    """Raised when a changed-code verification invariant fails."""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _normal(path: str | Path) -> str:
    return PurePosixPath(str(path).replace("\\", "/")).as_posix().lstrip("./")


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(_repo_root()), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise VerificationError(result.stderr.strip() or "git command failed")
    return result.stdout


def _changed_from_baseline(baseline: str) -> dict[str, str]:
    if not baseline:
        raise VerificationError("baseline SHA is required")
    _git("cat-file", "-e", f"{baseline}^{{commit}}")
    changed: dict[str, str] = {}
    for line in _git(
        "diff", "--name-status", "--find-renames", baseline, "--"
    ).splitlines():
        parts = line.split("\t")
        status = parts[0]
        path = parts[-1]
        changed[_normal(path)] = status[0]
    for path in _git("ls-files", "--others", "--exclude-standard").splitlines():
        changed[_normal(path)] = "A"
    return changed


def _changed_lines_from_diff(diff: str) -> dict[str, set[int]]:
    """Parse added-side line numbers from a zero-context unified Git diff."""
    changed: dict[str, set[int]] = {}
    current: str | None = None
    new_line: int | None = None
    hunk = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:]
            current = None if target == "/dev/null" else _normal(target.removeprefix("b/"))
            continue
        if line.startswith("@@"):
            match = hunk.match(line)
            if not match or current is None:
                raise VerificationError(f"malformed diff hunk: {line}")
            new_line = int(match.group(1))
            continue
        if new_line is None or current is None:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            changed.setdefault(current, set()).add(new_line)
            new_line += 1
        elif line.startswith("-") and not line.startswith("---"):
            continue
        elif not line.startswith("\\"):
            new_line += 1
    return changed


def _changed_lines(baseline: str, sources: set[str]) -> dict[str, set[int]]:
    tracked = sorted(source for source in sources if _git("ls-files", "--", source).strip())
    result = _changed_lines_from_diff(
        _git("diff", "--unified=0", "--no-ext-diff", baseline, "--", *tracked)
        if tracked
        else ""
    )
    root = _repo_root()
    for source in sources - set(tracked):
        path = root / source
        if path.is_file():
            result[source] = set(range(1, len(path.read_text(encoding="utf-8").splitlines()) + 1))
    return result


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _facts(changed: dict[str, str]) -> list[dict[str, str | None]]:
    root = _repo_root()
    return [
        {"path": path, "status": status, "sha256": _sha256(root / path)}
        for path, status in sorted(changed.items())
    ]


def snapshot(baseline: str, output: Path) -> None:
    """Atomically create a non-overwritable changed-file snapshot."""
    if output.exists():
        raise VerificationError(f"snapshot already exists: {output}")
    payload = {
        "version": 1,
        "baseline": baseline,
        "files": _facts(_changed_from_baseline(baseline)),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VerificationError(
            f"malformed or unreadable JSON report: {path}: {exc}"
        ) from exc


def _manifest(path: Path) -> set[str]:
    try:
        entries = {
            _normal(line.strip())
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
    except OSError as exc:
        raise VerificationError(f"cannot read manifest: {path}: {exc}") from exc
    if not entries:
        raise VerificationError(f"manifest is empty: {path}")
    return entries


def _changed_from_snapshot(path: Path) -> dict[str, str]:
    payload = _load_json(path)
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise VerificationError("invalid start snapshot schema")
    previous = {
        item["path"]: item.get("sha256")
        for item in payload.get("files", [])
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }
    current = _changed_from_baseline(str(payload.get("baseline", "")))
    facts = {item["path"]: item["sha256"] for item in _facts(current)}
    return {
        path: current.get(path, "D")
        for path in set(previous) | set(facts)
        if previous.get(path) != facts.get(path)
    }


def _coverage_entry(files: dict[str, Any], source: str) -> dict[str, Any] | None:
    source_parts = PurePosixPath(source).parts
    matches = []
    for key, value in files.items():
        key_parts = PurePosixPath(_normal(key)).parts
        if (
            key_parts == source_parts
            or (
                len(key_parts) <= len(source_parts)
                and source_parts[-len(key_parts) :] == key_parts
            )
            or (
                len(source_parts) <= len(key_parts)
                and key_parts[-len(source_parts) :] == source_parts
            )
        ):
            matches.append(value)
    if len(matches) > 1:
        raise VerificationError(f"ambiguous coverage entries for {source}")
    return matches[0] if matches else None


def _percent(
    summary: dict[str, Any], key: str, covered_key: str, total_key: str
) -> float:
    value = summary.get(key)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict) and isinstance(value.get("percent"), (int, float)):
        return float(value["percent"])
    covered = summary.get(covered_key)
    total = summary.get(total_key)
    if isinstance(covered, int) and isinstance(total, int):
        return 100.0 if total == 0 else covered * 100.0 / total
    raise VerificationError(f"coverage summary lacks {key} data")


def _executable_lines(source: str) -> set[int]:
    try:
        tree = ast.parse((_repo_root() / source).read_text(encoding="utf-8"), filename=source)
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise VerificationError(f"cannot parse changed Python source {source}: {exc}") from exc
    structural = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    return {
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.stmt)
        and not isinstance(node, structural)
        and not (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        )
        and hasattr(node, "lineno")
    }


def _verify_changed_entry(source: str, entry: dict[str, Any], changed: set[int]) -> None:
    executed = {int(line) for line in entry.get("executed_lines", [])}
    missing = {int(line) for line in entry.get("missing_lines", [])}
    mapped = executed | missing
    executable_changed = changed & _executable_lines(source)
    absent = executable_changed - mapped
    if absent:
        raise VerificationError(
            f"changed executable locations absent from coverage mapping: {source}: {sorted(absent)}"
        )
    uncovered = executable_changed & missing
    if uncovered:
        raise VerificationError(f"uncovered changed statements: {source}: {sorted(uncovered)}")
    missing_arcs = {
        (int(arc[0]), int(arc[1]))
        for arc in entry.get("missing_branches", [])
        if isinstance(arc, list) and len(arc) == 2
    }
    changed_arcs = sorted(
        arc for arc in missing_arcs if arc[0] in executable_changed or arc[1] in executable_changed
    )
    if changed_arcs:
        raise VerificationError(f"uncovered changed branch arcs: {source}: {changed_arcs}")


def _verify_coverage(path: Path, sources: set[str], changed_lines: dict[str, set[int]]) -> None:
    payload = _load_json(path)
    if not isinstance(payload, dict) or not isinstance(payload.get("files"), dict):
        raise VerificationError("coverage JSON lacks a files object")
    if payload.get("meta", {}).get("branch_coverage") is False:
        raise VerificationError("coverage report is not branch-aware")
    for source in sorted(sources):
        entry = _coverage_entry(payload["files"], source)
        if not isinstance(entry, dict):
            raise VerificationError(f"source absent from coverage: {source}")
        _verify_changed_entry(source, entry, changed_lines.get(source, set()))


def _verify_junit(paths: list[Path], tests: set[str]) -> None:
    if not paths:
        raise VerificationError("at least one --junit report is required")
    report_text = ""
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for path in paths:
        try:
            root = ET.parse(path).getroot()
            report_text += path.read_text(encoding="utf-8")
        except (OSError, UnicodeError, ET.ParseError) as exc:
            raise VerificationError(
                f"malformed or unreadable JUnit report: {path}: {exc}"
            ) from exc
        suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
        if not suites:
            raise VerificationError(f"JUnit report contains no testsuite: {path}")
        top = suites[0] if root.tag == "testsuites" else root
        for key in totals:
            try:
                totals[key] += int(top.attrib.get(key, 0))
            except ValueError as exc:
                raise VerificationError(f"invalid JUnit {key} count: {path}") from exc
    if totals["tests"] <= 0 or any(
        totals[key] for key in ("failures", "errors", "skipped")
    ):
        raise VerificationError(
            "JUnit reports do not prove nonzero pass and zero fail/error/skip: "
            f"{totals}"
        )
    normalized_text = report_text.replace("\\", "/")
    for test in sorted(tests):
        if PurePosixPath(test).name not in normalized_text:
            raise VerificationError(
                f"test manifest entry not executed in JUnit: {test}"
            )


def verify(
    coverage_json: Path,
    source_manifest: Path,
    test_manifest: Path,
    baseline: str | None,
    start_snapshot: Path | None,
    junit: list[Path],
) -> None:
    """Verify exact manifest membership, branch coverage, and test execution."""
    if bool(baseline) == bool(start_snapshot):
        raise VerificationError("provide exactly one of --baseline or --start-snapshot")
    sources = _manifest(source_manifest)
    tests = _manifest(test_manifest)
    overlap = sources & tests
    if overlap:
        raise VerificationError(f"paths are dual-classified: {sorted(overlap)}")
    if baseline:
        changed = _changed_from_baseline(baseline)
    else:
        assert start_snapshot is not None
        changed = _changed_from_snapshot(start_snapshot)
    changed_python = {
        path
        for path, status in changed.items()
        if Path(path).suffix in PYTHON_SUFFIXES and status != "D"
    }
    classified = sources | tests
    missing = changed_python - classified
    stale = classified - changed_python
    if missing or stale:
        raise VerificationError(
            f"manifest membership mismatch; missing={sorted(missing)}, stale={sorted(stale)}"
        )
    root = _repo_root()
    absent = sorted(path for path in classified if not (root / path).is_file())
    if absent:
        raise VerificationError(f"manifest paths do not exist: {absent}")
    if not baseline:
        raise VerificationError("aggregate verification requires an explicit recorded baseline SHA")
    _verify_coverage(coverage_json, sources, _changed_lines(baseline, sources))
    _verify_junit(junit, tests)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    snapshot_parser = subparsers.add_parser("snapshot")
    snapshot_parser.add_argument("--baseline", required=True)
    snapshot_parser.add_argument("--output", type=Path, required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--coverage-json", type=Path, required=True)
    verify_parser.add_argument("--source-manifest", type=Path, required=True)
    verify_parser.add_argument("--test-manifest", type=Path, required=True)
    identity = verify_parser.add_mutually_exclusive_group(required=True)
    identity.add_argument("--baseline")
    identity.add_argument("--start-snapshot", type=Path)
    verify_parser.add_argument("--junit", type=Path, action="append", default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one of the two supported verifier subcommands."""
    args = _parser().parse_args(argv)
    try:
        if args.command == "snapshot":
            snapshot(args.baseline, args.output)
        else:
            verify(
                args.coverage_json,
                args.source_manifest,
                args.test_manifest,
                args.baseline,
                args.start_snapshot,
                args.junit,
            )
    except VerificationError as exc:
        print(f"verification failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
