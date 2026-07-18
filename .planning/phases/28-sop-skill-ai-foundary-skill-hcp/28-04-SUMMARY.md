---
phase: 28-sop-skill-ai-foundary-skill-hcp
plan: 04
subsystem: testing
tags: [playwright, e2e, skill-editor, foundry-sync, admin-ui]

# Dependency graph
requires:
  - phase: 28-sop-skill-ai-foundary-skill-hcp (28-03)
    provides: "Foundry sync status API routes (foundry-sync, foundry-portal-url) and SkillFoundryStatusSection component wired into the Skill editor's Settings tab"
provides:
  - "Playwright E2E coverage for the Skill Foundry sync admin user story: status badge visibility, retry-sync flow, portal-link popup, no-sync regression guard"
  - "Shared buildSkillFixture() schema-complete SkillOut mock builder pattern for future Skill editor E2E specs"
affects: [testing, skill-editor, foundry-sync]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Shared fixture builder function (buildSkillFixture) at module scope, reused via overrides across every mocked GET response in a spec file, instead of inline partial objects — prevents unrelated page regions from breaking due to missing mock fields"

key-files:
  created:
    - frontend/e2e/skill-foundry-sync.spec.ts
  modified: []

key-decisions:
  - "Used real (unmocked) backend for status-badge and no-sync-regression tests since a freshly-created skill already has the correct default foundry_sync_status=none state; mocking reserved for retry-sync and portal-url flows which require simulating post-sync state without live Azure Foundry"

patterns-established:
  - "buildSkillFixture(): complete SkillOut-shaped fixture builder with typed overrides, used for every mocked GET /api/v1/skills/{id} response in a spec, closing the LOW-10 review gap of partial/placeholder mock objects"

requirements-completed: [D-06, D-07]

# Metrics
duration: 20min
completed: 2026-07-18
---

# Phase 28 Plan 04: Skill Foundry Sync E2E Coverage Summary

**Playwright E2E spec covering the Skill editor's Foundry sync status badge, retry-sync flow, portal-link popup, and no-sync regression guard, backed by a schema-complete SkillOut fixture builder**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-07-18T10:28:00Z (approx)
- **Completed:** 2026-07-18T10:48:25Z
- **Tasks:** 1 completed
- **Files modified:** 1 created

## Accomplishments
- Added `frontend/e2e/skill-foundry-sync.spec.ts` with 4 tests exercising the full D-06/D-07 user story: admin sees the sync status badge, retries a sync and sees the badge update, opens the Azure Portal via the portal link, and a never-synced skill's Settings tab renders the status section without console errors.
- Every mocked `GET /api/v1/skills/{id}` response uses a single shared `buildSkillFixture()` builder confirmed field-for-field against `backend/app/schemas/skill.py`'s `SkillOut`, closing the LOW-10 cross-AI review finding (no `/* full Skill shape */` placeholder comments).
- Retry-sync mock fixture uses `status: "published"`, matching Plan 28-03's MEDIUM-5 fix that returns 400 for non-published skills on retry.
- Confirmed rendered en-US locale strings ("Not Synced", "Foundry Synced", "Retry Sync", "View in Azure Portal") directly against `frontend/public/locales/en-US/skill.json` and `skill-foundry-status-section.tsx` rather than assuming.
- Installed missing Playwright Chromium browser binaries (environment blocker) and ran the spec against the real dev stack (backend `uvicorn` + frontend `vite`) via the existing `webServer` config — all 4 tests + 2 auth-setup tests pass (6/6).

## Task Commits

Each task was committed atomically:

1. **Task 1: Playwright E2E spec for Skill Foundry sync status section** - `ecb4d4c` (test)

**Plan metadata:** (this commit)

## Files Created/Modified
- `frontend/e2e/skill-foundry-sync.spec.ts` - E2E spec: status badge, retry-sync, portal-link, no-sync regression; shared `buildSkillFixture()` builder

## Decisions Made
- Reused real backend (no route mocking) for the status-badge-visibility and no-sync-regression tests since a freshly-created skill's default `foundry_sync_status="none"` state is exactly what those tests need to verify — mocking only where a post-sync state (`synced`) must be simulated without live Azure Foundry connectivity.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed missing Playwright browser binaries**
- **Found during:** Task 1 verification (`npx playwright test`)
- **Issue:** `browserType.launch: Executable doesn't exist at .../chromium_headless_shell-1208/...` — Playwright browsers were never downloaded in this environment, blocking all E2E execution (not just this spec's).
- **Fix:** Ran `npx playwright install chromium` to download the missing Chromium + headless-shell + ffmpeg binaries.
- **Files modified:** None (browser cache only, outside repo)
- **Verification:** Subsequent `npx playwright test` run launched successfully; all 6 tests (2 auth setup + 4 spec) passed.
- **Committed in:** N/A (no repo files changed by this fix)

---

**Total deviations:** 1 auto-fixed (1 blocking environment issue)
**Impact on plan:** Necessary one-time environment setup step to execute any Playwright spec in this workspace; no scope creep, no code changes beyond the planned spec file.

## Issues Encountered
None beyond the Playwright browser installation documented above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 28's Skill Foundry sync feature (D-01 through D-07) is now fully covered by both backend tests (Plans 28-01/28-02/28-03) and this Playwright E2E spec (Plan 28-04), closing the CLAUDE.md top-priority E2E gap (BLOCKER-2 from gsd-plan-checker).
- Phase 28 is complete (4/4 plans executed). No blockers for subsequent phases.

---
*Phase: 28-sop-skill-ai-foundary-skill-hcp*
*Completed: 2026-07-18*

## Self-Check: PASSED
- FOUND: frontend/e2e/skill-foundry-sync.spec.ts
- FOUND: commit ecb4d4c
