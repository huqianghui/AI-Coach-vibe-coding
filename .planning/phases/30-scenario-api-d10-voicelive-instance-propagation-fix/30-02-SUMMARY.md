---
phase: 30-scenario-api-d10-voicelive-instance-propagation-fix
plan: 02
subsystem: types
tags: [typescript, type-contract, frontend, scenario, hcp-profile]

# Dependency graph
requires:
  - phase: 30 (Plan 30-01)
    provides: "HcpProfileBrief backend schema shape (locked by 30-CONTEXT.md D-01/D-02/D-03) — this plan's target contract does not require the backend to already exist"
provides:
  - "HcpProfileSummary TypeScript interface in frontend/src/types/scenario.ts, matching backend HcpProfileBrief exactly"
  - "Scenario.hcp_profile narrowed from HcpProfile to HcpProfileSummary"
  - "Stray avatar_enabled field removed from HcpProfile interface (D-05)"
  - "Full tsc -b break catalog for downstream Plans 30-03/30-04, including one undocumented gap (training.test.tsx) not caught by the compiler"
affects: [30-03-scenario-gating-fix, 30-04-test-fixtures]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Narrow API response type (HcpProfileSummary) distinct from full domain type (HcpProfile) to prevent tsc from silently allowing reads of fields the API never returns"

key-files:
  created: []
  modified:
    - frontend/src/types/hcp.ts
    - frontend/src/types/scenario.ts

key-decisions:
  - "Kept avatar_enabled on VoiceLiveInstanceSummary (its correct home) while deleting only the stray copy on HcpProfile, per plan's own reference interface"
  - "HcpProfileSummary import path uses existing hcp.ts relative import style (./hcp) rather than @/types/hcp alias, matching scenario.ts's existing import convention"

patterns-established:
  - "Type-only plans record their tsc -b break list verbatim in SUMMARY.md so downstream plans in the same wave/phase don't need to rediscover the compiler impact"

requirements-completed: ["D-10 propagation (v1.0 audit integration gap, critical)"]

# Metrics
duration: 6min
completed: 2026-07-20
---

# Phase 30 Plan 02: HcpProfileSummary Type Contract Summary

**Added `HcpProfileSummary` interface mirroring backend `HcpProfileBrief` exactly, narrowed `Scenario.hcp_profile` to it, deleted the stray `avatar_enabled` field from `HcpProfile`, and catalogued the resulting `tsc -b` break list (7 errors across 5 files) for Plans 30-03/30-04.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-07-20T02:39:00Z
- **Completed:** 2026-07-20T02:45:00Z
- **Tasks:** 2 completed
- **Files modified:** 2

## Accomplishments
- `HcpProfileSummary` type added to `frontend/src/types/scenario.ts`, matching backend's `HcpProfileBrief` field-for-field (id, name, specialty, avatar_url, personality_type, voice_live_instance_id, voice_live_instance)
- `Scenario.hcp_profile` narrowed from the full `HcpProfile` domain type to the new `HcpProfileSummary`, so `tsc -b` now catches any consumer reading a field the scenario API never sends
- Stray `avatar_enabled?: boolean` field removed from `HcpProfile` in `frontend/src/types/hcp.ts` (D-05) — the field remains, correctly, only on `VoiceLiveInstanceSummary`
- Full `tsc -b` break catalog captured at `/tmp/phase30-tsc-errors.txt` and reproduced below for Plans 30-03/30-04

## Task Commits

1. **Task 1: Add HcpProfileSummary type, narrow Scenario.hcp_profile, delete stray avatar_enabled** - `ac79b87` (feat)
2. **Task 2: Run tsc -b to catalog every downstream break** - no commit (discovery only, no files modified per plan frontmatter)

**Plan metadata:** (this commit, docs)

## Files Created/Modified
- `frontend/src/types/hcp.ts` - Removed stray `avatar_enabled?: boolean` from `HcpProfile` interface (kept correctly on `VoiceLiveInstanceSummary`)
- `frontend/src/types/scenario.ts` - Added `HcpProfileSummary` interface; changed import from `HcpProfile` to `VoiceLiveInstanceSummary`; narrowed `Scenario.hcp_profile` to `HcpProfileSummary`

## tsc -b Break Catalog (verbatim)

Ran `cd frontend && npx tsc -b 2>&1 | tee /tmp/phase30-tsc-errors.txt`. Exit code: 1 (expected failure — Plans 30-03/30-04 have not yet run).

```
src/components/admin/scenario-table.test.tsx(55,5): error TS2353: Object literal may only specify known properties, and 'hospital' does not exist in type 'HcpProfileSummary'.
src/components/coach/scenario-card.test.tsx(28,5): error TS2353: Object literal may only specify known properties, and 'hospital' does not exist in type 'HcpProfileSummary'.
src/components/coach/scenario-panel.test.tsx(35,5): error TS2353: Object literal may only specify known properties, and 'hospital' does not exist in type 'HcpProfileSummary'.
src/pages/user/scenario-group-run.tsx(42,16): error TS2339: Property 'avatar_enabled' does not exist on type 'HcpProfileSummary'.
src/pages/user/scenario-group-run.tsx(44,66): error TS2339: Property 'avatar_enabled' does not exist on type 'HcpProfileSummary'.
src/pages/user/training.tsx(39,56): error TS2339: Property 'avatar_enabled' does not exist on type 'HcpProfileSummary'.
src/pages/user/training.tsx(74,12): error TS2339: Property 'avatar_enabled' does not exist on type 'HcpProfileSummary'.
```

**Files appearing in the error list (5, deduplicated):**
- `src/components/admin/scenario-table.test.tsx` (expected per D-07)
- `src/components/coach/scenario-card.test.tsx` (expected per D-07)
- `src/components/coach/scenario-panel.test.tsx` (expected per D-07)
- `src/pages/user/scenario-group-run.tsx` (expected per D-07)
- `src/pages/user/training.tsx` (expected per D-07)

**Expected-but-absent (1) — IMPORTANT for Plan 30-04:**
- `src/pages/user/training.test.tsx` was predicted in D-07's consumer set but does **not** appear in the `tsc -b` output. Root cause: `training.test.tsx` declares `let scenarioData: unknown[] | undefined;` (line 11) — because the mock fixture array is typed as `unknown[]`, TypeScript's structural/excess-property checks never run against `Scenario`/`HcpProfileSummary` for this variable, so the compiler silently accepts `hcp_profile: { voice_live_instance: {...}, avatar_enabled: true }` fixtures (6 occurrences at lines 75, 219, 273, 327, 340, 428, 455) even though `avatar_enabled` no longer exists on `HcpProfileSummary`.
  - **Consequence:** Plan 30-04 must still update these fixtures at the source level (they no longer reflect the real API shape and will produce incorrect runtime behavior once Plan 30-03 changes `training.tsx` to read `avatar_enabled` from the correct location — e.g., `hcp_profile.voice_live_instance?.avatar_enabled`). `tsc -b` passing will NOT prove this file is correct; it must be fixed by inspection/test-behavior review, not by chasing a compiler error.

**Confirmed absent as predicted (no regression):**
- Production display components `scenario-table.tsx`, `scenario-card.tsx`, `scenario-panel.tsx` — absent, as expected (D-07 predicted only their `.test.tsx` counterparts would break)
- `unified-session.tsx` / `unified-session.test.tsx` — absent, as expected

## Decisions Made
- Kept `avatar_enabled` on `VoiceLiveInstanceSummary` (its correct home) — only the stray copy on `HcpProfile` was deleted, matching the plan's own reference interface for `VoiceLiveInstanceSummary`
- Used relative import (`./hcp`) for `VoiceLiveInstanceSummary` in `scenario.ts`, matching that file's existing import convention (it previously imported `HcpProfile` the same way)

## Deviations from Plan

### Auto-fixed Issues

None — no bugs, missing functionality, or blocking issues were encountered. This was a pure type-only change executed exactly as specified.

### Acceptance-Criteria Note (not a deviation, documented for clarity)

The plan's Task 1 acceptance criterion `grep -c "avatar_enabled" frontend/src/types/hcp.ts` returning `0` is not literally satisfied — the grep returns `1`, because `VoiceLiveInstanceSummary` (defined in the same file) legitimately retains its own `avatar_enabled?: boolean` field. This is correct and intended: the plan's action section explicitly states the stray field "exists correctly on `VoiceLiveInstanceSummary`" and the plan's own `<interfaces>` reference block shows `VoiceLiveInstanceSummary` keeping `avatar_enabled`. The actual intent — removing the stray field from the `HcpProfile` interface specifically — was verified by direct file inspection (line 27 of `hcp.ts` now goes straight from `voice_live_instance` to the `agent_instructions_override` comment, with no `avatar_enabled` line inside `HcpProfile`). No fix needed; the literal grep command in the plan text is file-wide rather than scoped to the `HcpProfile` interface.

### Discovery (not a deviation — informational for Plan 30-04)

**[Informational] `training.test.tsx` not caught by tsc -b despite containing stale `avatar_enabled` fixtures**
- **Found during:** Task 2 (tsc -b cataloging)
- **Detail:** See "Expected-but-absent" section above. `scenarioData: unknown[]` bypasses TypeScript's excess-property/type checks, so this file's 6 stale `avatar_enabled` mock fixtures compile cleanly but are semantically wrong post-narrowing.
- **Action taken:** None (Task 2 is discovery-only per plan `files_modified: []` / `<files>none</files>`). Recorded here so Plan 30-04's executor does not need to rediscover this gap and knows to fix `training.test.tsx` by inspection rather than relying on `tsc -b` green as proof of correctness.

---

**Total deviations:** 0 auto-fixed. 1 acceptance-criteria clarification (non-blocking). 1 informational discovery flagged for downstream plan.
**Impact on plan:** None on this plan's scope — both notes are forward-looking context for Plans 30-03/30-04, not corrections to this plan's work.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `HcpProfileSummary` type contract is locked and available for Plans 30-03 (gating logic fix) and 30-04 (test fixture updates) to code against
- Plan 30-03 should read `avatar_enabled` via `hcp_profile.voice_live_instance?.avatar_enabled` (or equivalent), not `hcp_profile.avatar_enabled`, in `training.tsx` and `scenario-group-run.tsx`
- Plan 30-04 must fix `training.test.tsx`'s 6 stale `hcp_profile.avatar_enabled` fixtures (lines 75, 219, 273, 327, 340, 428, 455) even though `tsc -b` will not flag them — this file was NOT caught by the compiler due to its `unknown[]` typed mock array
- No blockers for downstream plans

## Known Stubs
None.

## Threat Flags
None — pure compile-time type definitions, no new runtime surface introduced, consistent with this plan's threat model (T-30-04: accept, zero attack surface).

---
*Phase: 30-scenario-api-d10-voicelive-instance-propagation-fix*
*Completed: 2026-07-20*

## Self-Check: PASSED

- FOUND: frontend/src/types/hcp.ts
- FOUND: frontend/src/types/scenario.ts
- FOUND: /tmp/phase30-tsc-errors.txt
- FOUND: commit ac79b87
