# Phase 31 Final Validation Authority

**Status:** Gate specification only. It contains no executable implementation instructions and assumes no gate has passed.

## Per-plan invariant

Each final plan must finish its focused unit/integration tests and prove 100% changed executable statements **and branches** before the next exact dependency begins. A typecheck is never coverage proof.

## Persistence and state-machine gates

- Actual single Alembic head is discovered and used as `down_revision`.
- Upgrade, data checks, downgrade, and re-upgrade pass on isolated SQLite and a real PostgreSQL instance.
- PostgreSQL proof covers transaction boundaries, unique constraints, lease/CAS winner selection, RESTRICT parent lifecycle, and preserved pre-migration data.
- Mutable outbox transitions are limited to declared states and compare-and-set transitions.
- Immutable attempt-start, attempt-event, and audit rows reject update/delete. Every post-call outcome, reconciliation, winner, and duplicate classification appends an event; retries append attempts; exactly one winner can commit.
- Timeout/unknown outcomes never trigger blind resend; reconciliation handles provider IDs/idempotency metadata where supported and fails closed otherwise.

## Behavioral authority gates

- Immutable focus appears only as quoted reference material.
- The final developer item contains a highest-precedence current-step directive that explicitly supersedes stale progress in focus and earlier developer items.
- Tests include adversarial stale-focus text and prove resulting behavior follows the current step.
- Session Responses use exact Session pin and explicit Conversation only; request-shape tests reject top-level instructions, Response-input developer/system, `previous_response_id`, tools/tool_choice, browser continuation, and Agent writes.
- Standalone HCP admin playground and Phase 30 paths retain their contracts.

## Conversation lifecycle gates

Create, persisted create, unknown create, reuse, response retry, end, delete, expiry, startup cleanup, periodic cleanup, retry/backoff, retention, and RESTRICT parent behavior all have automated tests. New turns are blocked once cleanup starts. The system never claims provider exactly-once and never creates a replacement for an unresolved mapping.

## Coverage gates

- Python: coverage.py branch data plus diff verifier against the recorded implementation baseline; changed executable statements and branch arcs = 100%.
- TypeScript/TSX application/library source: Vitest V8 JSON/LCOV plus a deterministic source-map-aware script enumerates changed executable statement/branch locations and requires 100%. Playwright specs use a narrow reviewed test manifest: actual execution must report nonzero pass/zero failure/skip and executable helper logic must be unit-covered; the plan never falsely labels Playwright runner JSON as V8 source coverage.
- Full frontend: statements >=71%, branches >=82%, functions >=70%, lines >=71%, without threshold/exclusion reduction.
- Full configured backend coverage, Ruff check/format, TypeScript, build, and tests pass.
- Plan 03 creates and self-tests both changed-branch verifiers. Plans 03–07 freeze non-overwritable start snapshots, create exact reviewed manifests, and pass branch-aware verification before the next dependency. Plan 08 hardens the verifiers and creates/tests the aggregate manifests, production live harness, and integrity/release scripts; one aggregate branch-aware run measures changed app, scripts, and test/harness modules before Plan 09. Plan 09 creates no executable source.

## User-story and live gates

- Primary Playwright uses the actual Unified Training route for two text turns and verifies browser non-authority and fail-closed Voice/avatar/WebRTC with zero fallback requests.
- Required Playwright and live suites report nonzero passed, zero failed, zero skipped.
- Production-path live A/B proves two distinct final current-step directives on the exact Session pin.
- Each A/B response has its own correlated successful exact `knowledge_base_retrieve` lifecycle.
- Agent definition/tool/version fingerprints remain unchanged.

## Protected/release gates

Before staging and again after validation/push:

1. SHA-256 manifests cover `.planning/debug/**`, `backend/storage/db-backups/**`, DB files/sidecars, and Phase 30 acceptance/summary artifacts.
2. Forbidden sweep fails on Agent writes, mutable-latest/generic/model/transport fallback, browser authority, prohibited instructions/input roles/continuation, bare Session response creation, broad Git add, or protected paths.
3. Staging names equal the exact recorded allowlist; cached diff and `git diff --cached --check` pass.
4. Baseline commit count proves exactly one new Requirement 2 commit.
5. Exactly one push command is attempted and its exit code/stdout/stderr digest/timestamp are recorded.
6. Remote branch SHA equals local SHA on success.
7. Post-push receipt is written after push and honestly remains uncommitted; no amend or second commit/push.
8. A frozen post-freeze evidence allowlist permits only the post-push receipt and final summary; all other worktree paths and hashes remain frozen.

Any failed gate blocks release. This file does not claim current success.

Required live pytest emits JUnit XML and Playwright emits JSON. The integrity gate parses both and requires nonzero passed, zero failed, and zero skipped before it freezes the pre-release allowlist. No executable file or allowlist may change after that freeze.
