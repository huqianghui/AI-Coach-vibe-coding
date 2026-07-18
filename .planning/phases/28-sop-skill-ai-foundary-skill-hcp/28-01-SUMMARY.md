---
phase: 28-sop-skill-ai-foundary-skill-hcp
plan: 01
subsystem: api
tags: [azure-ai-foundry, skills-api, entra-id, sqlalchemy, alembic, asyncio, pytest]

# Dependency graph
requires:
  - phase: 19-ai-coach-skill-module
    provides: Skill/SkillVersion model, lifecycle state machine (VALID_TRANSITIONS), skill_zip_service.export_skill_zip
  - phase: 11-hcp-profile-agent-integration
    provides: agent_sync_service.get_project_endpoint / get_portal_url_components (dual-mode Foundry client pattern, reused here for endpoint + portal URL only)
provides:
  - Skill model Foundry sync tracking columns (foundry_skill_name, foundry_sync_status, foundry_sync_error, foundry_cloud_version)
  - skill_foundry_service.py — Entra-ID-only Foundry Skills client, collision-safe first-sync naming, sync/delete/portal-url
  - publish_skill()/archive_skill()/delete_skill() lifecycle hooks wired to Foundry sync/delete, non-blocking (D-06)
affects: [28-02-sop-progress-cloud-chain, 28-03-foundry-sync-retry-route, 28-04-hcp-agent-skill-toolbox]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Entra-ID-only Azure SDK client with module-level cached DefaultAzureCredential (avoids per-call reconstruction / blocking IMDS probe)"
    - "asyncio.to_thread + asyncio.wait_for(timeout=60) to bound a blocking Azure SDK call inside an async function without indefinite hang"
    - "Collision-safe cloud entity naming: sanitize-then-suffix-with-id-prefix on first sync only, persisted name reused verbatim thereafter"
    - "D-06 non-blocking sync: internal try/except/finally in the service function so lifecycle callers never see an exception from a cloud sync side-effect"

key-files:
  created:
    - backend/app/services/skill_foundry_service.py
    - backend/alembic/versions/y32a_add_skill_foundry_sync.py
    - backend/tests/test_skill_foundry_service.py
  modified:
    - backend/app/models/skill.py
    - backend/app/services/skill_service.py

key-decisions:
  - "Entra-ID-only client construction for skill_foundry_service (no API-key fallback branch) since the Skills preview API rejects API keys with 403 AuthenticationTypeDisabled, confirmed via prior POC docs"
  - "_build_unique_foundry_name suffixes skill.id[:8] on FIRST sync only; foundry_skill_name is persisted and reused verbatim thereafter, so the id-suffix decision is made exactly once per skill and survives later skill.name edits (HIGH-2 fix)"
  - "publish_skill()'s existing idempotent early-return (status == 'published') is left unchanged and does NOT re-trigger sync — re-sync after content edits flows through create_new_version() -> publish_skill() on the new version; manual retry of a failed sync is deferred to Plan 28-03's dedicated route (WARNING-2)"
  - "Fixed a ruff E501 line-length violation in skill.py (introduced by the already-committed Task 1 migration commit) as a Rule 1 auto-fix, since CLAUDE.md's pre-commit checklist gates on `ruff check .`"

patterns-established:
  - "Foundry sync side-effects on skill lifecycle mutations are always wrapped in the sync_skill_to_foundry/delete_skill_from_foundry service functions' own try/except, never in the caller — keeps D-06's non-blocking guarantee enforceable by inspection at a single call site"

requirements-completed: [D-01, D-03, D-06]

# Metrics
duration: ~25min (this session, continuing from 3 prior commits)
completed: 2026-07-18
---

# Phase 28 Plan 01: Skill Foundry Sync Wiring Summary

**Skill model + Entra-ID-only skill_foundry_service.py + publish/archive/delete lifecycle hooks that register/remove skills as first-class Azure AI Foundry entities with collision-safe naming, never blocking the local skill lifecycle on cloud failure.**

## Performance

- **Duration:** ~25 min this session (Tasks 1-2 and RED-phase tests for Task 3 were already committed from a prior session; this session verified all prior work, completed the GREEN-phase lifecycle wiring, fixed a lint regression, and ran full verification)
- **Completed:** 2026-07-18T10:17:39Z
- **Tasks:** 3/3 complete
- **Files modified:** 5 (2 created new this plan beyond what existed: skill_foundry_service.py, migration, test file; 2 modified: skill.py, skill_service.py)

## Accomplishments

- Skill model carries 4 new Foundry sync columns (`foundry_skill_name`, `foundry_sync_status`, `foundry_sync_error`, `foundry_cloud_version`), migrated cleanly on top of `x31a_merge_heads`
- `skill_foundry_service.py` provides a real, Entra-ID-only Azure AI Foundry Skills client (no API-key fallback — the preview surface rejects API keys with 403), with:
  - a module-level cached `DefaultAzureCredential` to avoid blocking reconstruction on every call
  - `_build_unique_foundry_name` — a collision-safe naming scheme that suffixes the skill's UUID prefix on first sync only, fixing REVIEWS.md HIGH-2 (two skills with names that sanitize to the same slug can never collide on the same cloud entity, and can never cause archive/delete to remove the WRONG skill's cloud entity)
  - `sync_skill_to_foundry` / `delete_skill_from_foundry` bounded by a 60s `asyncio.wait_for` timeout, running the blocking Azure SDK calls via `asyncio.to_thread`, and NEVER raising (D-06) — any failure sets `foundry_sync_status="failed"` with a truncated error message and returns
  - `get_skill_portal_url` best-effort deep link, falling back to the generic Foundry URL when components aren't resolvable
- `publish_skill()` now syncs the newly-published skill to Foundry (D-01) without ever failing the publish itself (D-06); the existing idempotent early-return is documented as deliberately NOT re-triggering sync (WARNING-2)
- `archive_skill()` and `delete_skill()` both call `delete_skill_from_foundry` to remove the cloud entity (D-03), treating a 404-on-delete as success
- 100% test coverage of `skill_foundry_service.py` and `skill_service.py` (108 tests total across the touched test files, 0 regressions in the pre-existing skill test suite)

## Task Commits

Each task was committed atomically (Tasks 1-2 and the RED phase of Task 3 were committed in a prior session; this session completed and verified the GREEN phase):

1. **Task 1: Skill model Foundry sync columns + migration** — `ddad4dc` (feat) [prior session]
2. **Task 2 (TDD RED): failing tests for skill_foundry_service** — `abd9fc1` (test) [prior session]
3. **Task 2 (TDD GREEN): skill_foundry_service implementation** — `e7b1d65` (feat) [prior session]
4. **Task 3 (TDD RED): failing tests for skill lifecycle -> Foundry sync wiring** — `c27b3f0` (test) [prior session]
5. **Task 3 (TDD GREEN): wire Foundry sync into skill publish/archive/delete lifecycle** — `6634257` (feat) [this session — includes the ruff E501 auto-fix in skill.py]

**Plan metadata:** committed separately below (docs: complete plan)

_Note: TDD tasks span multiple commits (test -> feat), as expected._

## Files Created/Modified

- `backend/app/models/skill.py` — added 4 Foundry sync tracking columns to `Skill`; fixed a line-length lint violation on the status column comment
- `backend/alembic/versions/y32a_add_skill_foundry_sync.py` — migration adding the 4 columns via `batch_alter_table` (SQLite ALTER limitation)
- `backend/app/services/skill_foundry_service.py` — Entra-ID-only Foundry Skills client, collision-safe naming, sync/delete/portal-url functions
- `backend/app/services/skill_service.py` — wired `sync_skill_to_foundry` into `publish_skill()` and `delete_skill_from_foundry` into `archive_skill()`/`delete_skill()`
- `backend/tests/test_skill_foundry_service.py` — 31 unit tests covering naming, client construction, sync (success/failure/timeout/zip-security-failure), delete (success/404/non-404), portal URL, plus lifecycle-hook integration tests for publish/archive/delete/restore

## Decisions Made

- Entra-ID-only client construction, no API-key fallback branch (confirmed hard constraint per prior POC docs and 28-CONTEXT.md)
- `_build_unique_foundry_name` id-suffix applied on first sync only, persisted name reused verbatim thereafter (HIGH-2 fix)
- Idempotent re-publish deliberately does not re-trigger sync; recovery is deferred to Plan 28-03's dedicated retry route (WARNING-2)
- Ruff E501 lint fix in `skill.py` applied as Rule 1 auto-fix (pre-existing violation from the already-committed Task 1 migration commit, blocking the CLAUDE.md pre-commit checklist gate)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed ruff E501 line-length violation in skill.py**
- **Found during:** Task 3 pre-commit verification (running the plan's own `<verification>` block: `ruff check app/services/skill_foundry_service.py app/services/skill_service.py app/models/skill.py`)
- **Issue:** The `foundry_sync_status` column definition + inline comment on one line exceeded the project's 100-char line length (`backend/pyproject.toml` `[tool.ruff]`), introduced by the already-committed Task 1 migration commit (`ddad4dc`)
- **Fix:** Moved the `none|pending|synced|failed` value-comment to its own line above the column definition
- **Files modified:** `backend/app/models/skill.py`
- **Verification:** `ruff check` and `ruff format --check` both pass; `alembic current` still reports `y32a_skill_foundry_sync (head)` (no migration content changed, comment-only fix)
- **Committed in:** `6634257` (part of the Task 3 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 Rule 1 bug fix)
**Impact on plan:** Necessary to satisfy the plan's own `<verification>` block and CLAUDE.md's mandatory pre-commit ruff gate. No scope creep — comment-only change, no behavior or schema impact.

## Issues Encountered

None beyond the lint fix above. All prior-session work (Tasks 1-2, Task 3 RED-phase tests) was verified correct on inspection and via a fresh full test run — no rework was needed.

## D-03 Manual Smoke-Test Note (WARNING-1, per plan's `<verify><manual>` block)

**Not yet confirmed.** The plan flags that the version-increment assumption (`create_from_files` called twice with the same skill name causing Foundry to return an incremented `result.version`, e.g. "1" -> "2") is an UNTESTED ASSUMPTION on the Agents API Skills surface — prior POC evidence for this increment behavior comes from the separate, unused Responses API `.versions.create()` path (doc 10 §12.4 only invoked `create_from_files` once on this surface). This plan's own automated tests (`test_sync_skill_to_foundry_called_twice_same_name`) assert only the CALL PATTERN (same name, two calls), not the server-side version-increment outcome, per the plan's explicit instruction not to present this as verified behavior.

**This is a non-gating, one-time smoke test required before D-03 is considered fully delivered for the phase** (not before merging this plan's code). It has NOT been run in this session (would require a real, non-mocked Foundry project with Entra ID credentials configured, which is out of scope for an automated executor). Recorded here as a gap: **a follow-up action item** — before relying on D-03's re-publish/version-recovery semantics in production, run `sync_skill_to_foundry` twice against a real Foundry project for the same skill and confirm `skill.foundry_cloud_version` changes. If it does not increment, file a follow-up plan for an alternate versioning strategy (e.g., suffix-based naming per publish, or explicit version pinning).

## User Setup Required

None for this plan's automated code changes. However, **production/staging use of `skill_foundry_service.py` requires Entra ID credentials available to the backend process** (e.g. `az login` for local dev, or Managed Identity in Azure Container Apps) — `get_skills_client` raises `RuntimeError` with operator guidance if no credential can be obtained. No API key configuration is possible or supported on this surface.

## Next Phase Readiness

- Plan 28-02 (SOP progress cloud chain) can build on `foundry_sync_status` state without additional model changes
- Plan 28-03 (Foundry sync retry route) can call `skill_foundry_service.sync_skill_to_foundry` directly for a retry endpoint restricted to `published`-status skills, consistent with the idempotent-bypass design decision documented in `publish_skill()`
- Plan 28-04 (HCP agent skill toolbox) can rely on `skill.foundry_skill_name` being populated and unique once a skill has synced at least once
- Outstanding: the D-03 manual smoke test above should be run against a real Foundry project before the phase is considered fully verified end-to-end

---
*Phase: 28-sop-skill-ai-foundary-skill-hcp*
*Completed: 2026-07-18*

## Self-Check: PASSED

All files created/modified and all commit hashes referenced in this summary were verified to exist on disk / in git history.
