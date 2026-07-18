---
phase: 28-sop-skill-ai-foundary-skill-hcp
plan: 02
subsystem: api
tags: [azure-ai-foundry, skills, toolbox, mcp, session-service, ttl-cache, sqlalchemy-async]

# Dependency graph
requires:
  - phase: 28-sop-skill-ai-foundary-skill-hcp
    plan: "28-01"
    provides: "Skill model Foundry sync columns (foundry_skill_name, foundry_sync_status, foundry_cloud_version) + skill_foundry_service.py (Entra-ID-only client, sync/delete/portal-url, collision-safe naming)"
provides:
  - "skill_consumption_service.py: session-time skill content resolution abstraction (Toolbox mount -> MCP probe -> download fallback -> local DB degrade)"
  - "get_skill_content_for_session(db, scenario_id) -> SkillContent | None as the single top-level entry point consumed by both create_session() and update_sop_progress()"
  - "process-local TTL cache (10 min) keyed on (skill.id, foundry_cloud_version) preventing repeated cloud round-trips per chat message"
  - "scenario.skill_version_id pin bypass so pinned training content never drifts to Foundry's latest cloud version"
  - "shared parse_skill_frontmatter() helper reused by ZIP import and Foundry download-fallback (no new frontmatter dependency)"
affects: [session-lifecycle, voice-live, skill-management]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Process-local TTL cache with sentinel value (_CACHE_MISS = object()) distinguishing 'no entry' from 'cached None'"
    - "Mount-then-MCP-then-download-then-local-degrade cascade, each step wrapped in try/except never raising, so cloud failures degrade transparently without blocking training"
    - "Defensive getattr(...) chains for cross-SDK-version compatibility (LOW-9)"

key-files:
  created:
    - backend/app/services/skill_consumption_service.py
    - backend/tests/test_skill_consumption_service.py
  modified:
    - backend/app/services/skill_zip_service.py
    - backend/app/services/session_service.py

key-decisions:
  - "Promoted skill_zip_service._parse_skill_md's inline YAML-frontmatter parsing into a shared public parse_skill_frontmatter() helper instead of adding a python-frontmatter dependency (BLOCKER-1 remediation)"
  - "HIGH-1 fix: TTL cache (600s) keyed on (skill.id, foundry_cloud_version) guards the cloud chain so per-chat-message calls to update_sop_progress() do not re-mount/re-probe/re-download on every message"
  - "MEDIUM-4 fix: scenario.skill_version_id pin bypasses the cloud path unconditionally, since Foundry's Toolbox/MCP/download surface has no version-pin concept and always serves latest"
  - "session_service.py substitution is a pure one-line swap at both call sites (create_session, update_sop_progress) -- no additional session-level caching added, relying entirely on Task 1's cache"

requirements-completed: [D-02, D-04, D-05, D-06]

# Metrics
duration: ~45min
completed: 2026-07-18
---

# Phase 28 Plan 02: Skill Foundry Session Consumption Summary

**session-time skill content resolution with Toolbox mount, honest MCP probe, download-fallback, and a TTL cache wired into create_session()/update_sop_progress(), replacing the direct local-DB call with transparent cloud-then-local degradation**

## Performance

- **Duration:** ~45 min (commit span 18:24:50 -> 18:38:35 UTC+8, plus preceding context/setup)
- **Started:** 2026-07-18T18:24:50+08:00
- **Completed:** 2026-07-18T18:38:35+08:00
- **Tasks:** 2
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments
- New `skill_consumption_service.py` implementing the full D-02/D-04/D-05/D-06 cascade: best-effort Toolbox mount, a real (not stubbed) MCP endpoint probe, `skills.download()` + frontmatter-extraction fallback, and final local-DB degrade via the existing `load_skill_for_scenario`.
- HIGH-1 review fix: process-local TTL cache (`_content_cache`, 600s) keyed on `(skill.id, foundry_cloud_version)` so the cloud chain runs at most once per skill-version per cache window, not once per chat message.
- MEDIUM-4 review fix: `_scenario_pin_is_stale()` routes version-pinned scenarios straight to the local pinned content, bypassing the cloud path (which has no pin concept) unconditionally.
- `session_service.py`'s `create_session()` and `update_sop_progress()` now source skill content through `get_skill_content_for_session()` instead of calling `load_skill_for_scenario()` directly -- both text-mode and Voice Live receive Foundry-sourced content transparently via the unchanged `focus_instruction` channel, with zero Voice Live-specific code.
- BLOCKER-1 remediation: promoted `skill_zip_service`'s inline frontmatter parsing into a shared public `parse_skill_frontmatter()` helper, reused by both ZIP import and the new Foundry download-fallback path, avoiding a new `python-frontmatter` dependency.

## Task Commits

Each task was committed atomically (both `tdd="true"`, RED then GREEN):

1. **Task 1: Create skill_consumption_service.py**
   - `38e7bd4` (test) - RED: failing tests for skill_consumption_service + promote parse_skill_frontmatter helper
   - `ef2a78d` (feat) - GREEN: implement skill_consumption_service — mount, MCP probe, download fallback, TTL cache, local degradation
2. **Task 2: Wire session_service.py to the consumption abstraction**
   - `31f7c68` (test) - RED: failing tests for session_service wiring to skill_consumption_service
   - `862b157` (feat) - GREEN: wire session_service to skill_consumption_service (D-02/D-04/D-05/D-06)

**Plan metadata:** this commit (docs: complete plan) — SUMMARY.md only; STATE.md/ROADMAP.md intentionally NOT updated (orchestrator owns those writes after all wave agents complete).

## Files Created/Modified
- `backend/app/services/skill_consumption_service.py` - New: `mount_skill_toolbox`, `_try_mcp_fetch`, `download_and_extract_skill_content`, `get_skill_content_for_session` (top-level entry point), TTL cache helpers, `_scenario_pin_is_stale`
- `backend/app/services/skill_zip_service.py` - Added public `parse_skill_frontmatter()`, refactored `_parse_skill_md()` to delegate to it (behavior-preserving)
- `backend/app/services/session_service.py` - `create_session()` and `update_sop_progress()` now call `get_skill_content_for_session()` instead of `load_skill_for_scenario()` directly (2 call sites)
- `backend/tests/test_skill_consumption_service.py` - New: 49 tests covering mount/MCP/download/cache/pin-bypass (Task 1) plus 3 end-to-end wiring tests (Task 2, including the HIGH-1 proof from the real `create_session`/`update_sop_progress` call sites)

## Decisions Made
- No new `python-frontmatter` dependency: reused/promoted the existing manual YAML-frontmatter split-and-`yaml.safe_load` logic into a shared helper (per plan's BLOCKER-1 constraint), verified behavior-preserving against the full pre-existing `test_skill_zip_service.py` suite.
- TTL window set to 600s (10 min): long enough to absorb one training conversation's per-message chat traffic, short enough that a re-publish's version bump (which changes the cache key) is picked up well within a session's lifetime.
- Cache miss vs. cached-`None` distinguished via a sentinel (`_CACHE_MISS = object()`), so a flaky/down Foundry endpoint's "cloud failed" result is also honored for the rest of the TTL window rather than retried every message.
- `update_sop_progress()` adds no caching of its own — relies entirely on Task 1's `get_skill_content_for_session` cache, keeping the substitution a pure one-line call-site swap as specified in the plan.

## Deviations from Plan

None — plan executed exactly as written, including both TDD tasks' RED-then-GREEN commit structure and the exact substitution points specified for `session_service.py`.

## Issues Encountered
- A test-authoring mistake (`test_no_skill_id_returns_none` originally passed a bare `AsyncMock()` as the `db` parameter, which doesn't compose the same way as a real SQLAlchemy async chain) was caught and fixed by using a real `TestSessionLocal()` session against an empty DB instead.
- Two ruff lint issues in the implementation file (E501 line-too-long at the `skills.download()` call and a `logger.warning` format string) and three in the test file (E501 x2, F841 unused `mock_mount` binding) were found and fixed before committing the GREEN phase.
- Task 2's HIGH-1 end-to-end test initially failed with `NoResultFound` because `create_session()` only flushes (does not commit); fixed by explicitly committing after the `create_session()` call within the test's own session context, since the test re-queries the row from a separate `TestSessionLocal()` session in the same test.
- Confirmed via `git stash` that 2 pre-existing failures in `tests/test_sessions_api_extended.py::TestSendMessageSSE` (a `Rubric not found` error unrelated to skill consumption) exist independently of this plan's changes — out of scope per the deviation rules' scope boundary, not fixed, not caused by this work.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `get_skill_content_for_session()` is now the single source of truth for session-time skill content, consumed identically by text-mode (SSE) and Voice Live via the unmodified `focus_instruction`/`session.focus_instruction` channel — no further Voice Live wiring is needed for this feature.
- Plan 28's D-02, D-04, D-05, D-06 decisions are now fully delivered; HIGH-1 and MEDIUM-4 cross-AI review findings are closed with tests proving the fixes end-to-end from the real call sites.
- MEDIUM-3 (unbounded Toolbox version growth) remains a documented, accepted residual risk per the plan's `<deliberate_decisions>` — tracked as a future ops/cleanup item, not blocking.
- No blockers for downstream phases; `session_service.py`, `skill_consumption_service.py`, and `skill_zip_service.py` are stable and fully tested (59 tests passing across the touched test files).

---
*Phase: 28-sop-skill-ai-foundary-skill-hcp*
*Plan: 02*
*Completed: 2026-07-18*

## Self-Check: PASSED

All created/modified files verified present on disk:
- `backend/app/services/skill_consumption_service.py` - FOUND
- `backend/tests/test_skill_consumption_service.py` - FOUND
- `backend/app/services/skill_zip_service.py` - FOUND
- `backend/app/services/session_service.py` - FOUND
- `.planning/phases/28-sop-skill-ai-foundary-skill-hcp/28-02-SUMMARY.md` - FOUND

All task commit hashes verified present in git history:
- `38e7bd4` (Task 1 RED) - FOUND
- `ef2a78d` (Task 1 GREEN) - FOUND
- `31f7c68` (Task 2 RED) - FOUND
- `862b157` (Task 2 GREEN) - FOUND
