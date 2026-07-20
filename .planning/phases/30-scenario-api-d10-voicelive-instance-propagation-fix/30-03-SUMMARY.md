---
phase: 30-scenario-api-d10-voicelive-instance-propagation-fix
plan: 03
subsystem: ui
tags: [react, typescript, vitest, scenario, hcp-profile, voice-live, gating]

# Dependency graph
requires:
  - phase: 30 (Plan 30-02)
    provides: "HcpProfileSummary/VoiceLiveInstanceSummary type contract (Scenario.hcp_profile narrowed, stray flat avatar_enabled removed from HcpProfile) — the tsc break list this plan's fixes resolve"
provides:
  - "training.tsx::getScenarioModes/getConferenceModes read avatar availability from hcp.voice_live_instance.avatar_enabled instead of the removed flat hcp.avatar_enabled"
  - "scenario-group-run.tsx::getAvailableModes (now exported) reads avatar availability from the same nested path for both conference and non-conference branches"
  - "scenario-group-run.test.tsx — first-ever automated test coverage for scenario-group-run.tsx's mode-gating logic (6 tests)"
affects: [30-04-test-fixtures, 30-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Export module-scope pure gating functions (getAvailableModes) for direct unit testing instead of testing only through full component render + hook mocks"

key-files:
  created:
    - frontend/src/pages/user/scenario-group-run.test.tsx
  modified:
    - frontend/src/pages/user/training.tsx
    - frontend/src/pages/user/scenario-group-run.tsx

key-decisions:
  - "Exported getAvailableModes from scenario-group-run.tsx (was module-private) to enable direct unit testing of the gating matrix without mocking useScenarioGroupRun/useFeatureFlags/router — matches the plan's stated preference"
  - "Built local makeScenario/makeHcpProfile/makeVoiceLiveInstance fixture factories in the new test file using the correct HcpProfileSummary/VoiceLiveInstanceSummary nested shape, rather than reusing any other file's stale flat-shape fixtures"

patterns-established:
  - "New gating tests assert the full {modes, defaultMode} return shape per scenario (voice-only, voice+avatar, conference avatar-disabled, unbound-HCP, conference avatar-enabled, null-scenario) rather than only checking modes.includes(...)"

requirements-completed: ["D-10 propagation (v1.0 audit integration gap, critical)"]

# Metrics
duration: ~20min
completed: 2026-07-20
---

# Phase 30 Plan 03: Scenario-Driven Avatar Gating Fix Summary

**Both `training.tsx` and `scenario-group-run.tsx` now derive digital-human/avatar availability from `hcp.voice_live_instance.avatar_enabled` (the real nested field) instead of the deleted flat `hcp.avatar_enabled`, and `scenario-group-run.tsx`'s gating logic has automated test coverage for the first time (6 passing tests).**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-07-20
- **Tasks:** 2 completed
- **Files modified:** 2, created: 1

## Accomplishments
- `training.tsx`'s `getScenarioModes` and `getConferenceModes` no longer read the compile-error-producing `hcp?.avatar_enabled`; both now read `hcp?.voice_live_instance?.avatar_enabled`
- `scenario-group-run.tsx`'s `getAvailableModes` fixed identically for both its conference-mode and non-conference branches; function exported for direct unit testing
- New `frontend/src/pages/user/scenario-group-run.test.tsx` (6 tests, all passing) covers: voice+avatar available, avatar disabled on VL instance, conference mode with `features.avatar_enabled=false`, unbound HCP (no VoiceLiveInstance → text-only), conference mode with avatar fully enabled, and a null/undefined scenario edge case
- `npx tsc -b` confirms zero remaining errors in `training.tsx` or `scenario-group-run.tsx` (the two files this plan owns) — the 3 remaining project-wide `tsc -b` errors are in `scenario-table.test.tsx` / `scenario-card.test.tsx` / `scenario-panel.test.tsx`, explicitly Plan 30-04's scope per its own frontmatter `files_modified`

## Task Commits

1. **Task 1: Fix training.tsx avatar-gating reads (getScenarioModes + getConferenceModes)** - `0c96914` (fix)
2. **Task 2: Fix scenario-group-run.tsx gating + add first-ever test coverage for it** - `6ced908` (fix)

## Files Created/Modified
- `frontend/src/pages/user/training.tsx` - Both `hcp?.avatar_enabled` reads replaced with `hcp?.voice_live_instance?.avatar_enabled` (one in `getScenarioModes`, one in `getConferenceModes`); `hcp?.voice_live_instance?.enabled` (voice) and `features?.avatar_enabled` (global flag) reads left untouched, as instructed
- `frontend/src/pages/user/scenario-group-run.tsx` - `getAvailableModes` exported; both `hcp?.avatar_enabled` reads (conference and non-conference branches) replaced with `hcp?.voice_live_instance?.avatar_enabled`
- `frontend/src/pages/user/scenario-group-run.test.tsx` (new) - 6 unit tests calling the exported `getAvailableModes` directly with local `makeScenario`/`makeHcpProfile`/`makeVoiceLiveInstance` fixture factories built against the correct `HcpProfileSummary`/`VoiceLiveInstanceSummary` nested shape

## Decisions Made
- Exported `getAvailableModes` rather than testing only through full component render, per the plan's stated preference — keeps the new test file dependency-free (no need to mock `useScenarioGroupRun`, `useFeatureFlags`, `useCreateScenarioGroupRunSession`, `useRefreshScenarioGroupRunScore`, or router hooks)
- Built fresh fixture factories scoped to this test file rather than importing/reusing fixtures from `scenario-table.test.tsx` (which still uses the old flat `HcpProfile` shape with a `hospital` field and is Plan 30-04's responsibility to fix, not this plan's)

## Deviations from Plan

None — plan executed exactly as written. Both tasks matched their acceptance criteria exactly (`grep -c` counts and `npx vitest run` exit codes as specified).

## Issues Encountered

- **`frontend/node_modules` was not installed in this worktree** — ran `npm ci` in `frontend/` to restore the dependency tree before any test/tsc verification could run. Not a plan deviation (environment setup, not code), but noted for completeness.
- **`training.test.tsx` has 3 pre-existing test failures that this plan's fix causes to surface** (not introduces as new bugs, but converts from "passing against the old buggy read" to "failing against stale fixtures"). This was explicitly flagged in advance by Plan 30-02's SUMMARY.md ("Expected-but-absent" section) and is explicitly out of scope for this plan — Plan 30-03's own `<tasks>` block states verbatim: *"training.test.tsx ... this plan does NOT modify this file, that is Plan 30-04's job"*. `training.test.tsx`'s 6 stale `hcp_profile.avatar_enabled` fixtures (lines 75, 219, 273, 327, 340, 428, 455 per 30-02's catalog) were never caught by `tsc -b` because the mock array is typed `unknown[]`, so they silently diverged from the real API shape; now that `training.tsx` reads the correct nested path, those specific fixtures without `voice_live_instance.avatar_enabled` set no longer produce a truthy avatar-available result, causing 3 assertions (which expected a `digital_human_realtime_model` button to render) to fail. This is precisely the bug this plan is fixing — the failing assertions were testing incorrect (pre-fix) behavior. Left untouched per plan scope; Plan 30-04 (same wave, sibling worktree) owns `training.test.tsx` fixture repair.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Both scenario-driven avatar-gating call sites (`training.tsx`, `scenario-group-run.tsx`) now correctly derive availability from `hcp.voice_live_instance.avatar_enabled`; `scenario-group-run.tsx` has automated gating-matrix test coverage for the first time
- Plan 30-04 (parallel, same wave) still needs to update `training.test.tsx`'s stale fixtures (as it already planned to, independent of this plan's completion) plus the 3 remaining `tsc -b` errors in `scenario-table.test.tsx`/`scenario-card.test.tsx`/`scenario-panel.test.tsx`
- No blockers for downstream plans in this phase

## Known Stubs
None.

## Threat Flags
None — this plan only changed client-side UI gating logic (which buttons render); no new network surface, auth path, or schema change was introduced. Consistent with the plan's own threat model (T-30-05: accept, server-side token broker independently re-derives mode availability).

---
*Phase: 30-scenario-api-d10-voicelive-instance-propagation-fix*
*Completed: 2026-07-20*

## Self-Check: PASSED

All created/modified files confirmed present on disk (training.tsx, scenario-group-run.tsx, scenario-group-run.test.tsx, this SUMMARY.md); both task commits (0c96914, 6ced908) confirmed present in git log.
