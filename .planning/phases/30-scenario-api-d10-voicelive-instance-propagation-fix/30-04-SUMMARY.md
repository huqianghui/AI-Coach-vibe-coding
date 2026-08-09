---
phase: 30-scenario-api-d10-voicelive-instance-propagation-fix
plan: 04
subsystem: testing
tags: [typescript, vitest, test-fixtures, scenario, hcp-profile, voice-live]

# Dependency graph
requires:
  - phase: 30 (Plan 30-02)
    provides: "HcpProfileSummary TypeScript interface narrowing Scenario.hcp_profile, plus the full tsc -b break catalog (including the undocumented training.test.tsx gap)"
provides:
  - "All 5 in-scope frontend test files (training.test.tsx, scenario-card.test.tsx, scenario-panel.test.tsx, scenario-table.test.tsx, unified-session.test.tsx) rewritten to the narrowed HcpProfileSummary/nested VoiceLiveInstanceSummary fixture shape"
  - "unified-session.test.tsx now genuinely exercises the nested avatar_character/avatar_style propagation path instead of mutating dead flat fields"
  - "Confirmed and documented cross-plan integration dependency: 3 tests in training.test.tsx will only pass once Plan 30-03's production fix (training.tsx reading hcp.voice_live_instance.avatar_enabled) lands alongside this plan's fixtures"
affects: [30-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Test fixtures for narrowed API response types must be written as HcpProfileSummary/VoiceLiveInstanceSummary literals, not the full domain HcpProfile shape, even in untyped (unknown[]) mock arrays where tsc -b won't catch drift"

key-files:
  created: []
  modified:
    - frontend/src/pages/user/training.test.tsx
    - frontend/src/components/coach/scenario-card.test.tsx
    - frontend/src/components/coach/scenario-panel.test.tsx
    - frontend/src/components/admin/scenario-table.test.tsx
    - frontend/src/pages/user/unified-session.test.tsx
    - .planning/phases/30-scenario-api-d10-voicelive-instance-propagation-fix/deferred-items.md

key-decisions:
  - "training.test.tsx's 6 stale flat hcp_profile.avatar_enabled fixtures were nested inline as voice_live_instance: { enabled: true, avatar_enabled: true } (single-line) rather than split across lines, so the fixture is unambiguously nested (not just re-indented) and satisfies the plan's intent that no flat avatar_enabled sibling of hcp_profile remains"
  - "3 of training.test.tsx's 22 tests (expecting digital_human_realtime_model to appear once avatar_enabled is nested) will only pass once Plan 30-03 lands its training.tsx production fix in the same branch -- confirmed as an intentional, documented cross-plan wave dependency (30-03's own <verification> section runs training.test.tsx too), not a defect in this plan's fixture work"
  - "Logged the pre-existing scenario-panel.test.tsx 'DrugX' failure (tags-vs-flat-field mismatch, confirmed present on unmodified main via git stash) to deferred-items.md rather than fixing it, since it is unrelated to the hcp_profile shape this plan addresses"

patterns-established:
  - "When a test's mock data array is typed unknown[] (bypassing tsc -b's excess-property checks), fixture correctness must be verified by direct inspection/grep against the production read path, not by relying on a green tsc -b"

requirements-completed: ["D-10 propagation (v1.0 audit integration gap, critical)"]

# Metrics
duration: ~25min
completed: 2026-07-20
---

# Phase 30 Plan 04: Frontend Test Fixture Repair for HcpProfileSummary Summary

**Rewrote 5 test files' `hcp_profile` fixtures from the old flat `HcpProfile` shape to the narrowed `HcpProfileSummary`/nested `VoiceLiveInstanceSummary` contract, and restructured `unified-session.test.tsx` to genuinely assert `avatar_character`/`avatar_style` propagation instead of mutating dead flat fields.**

## Performance

- **Duration:** ~25 min
- **Completed:** 2026-07-20
- **Tasks:** 3 completed
- **Files modified:** 6 (5 test files + deferred-items.md)

## Accomplishments
- `frontend/src/pages/user/training.test.tsx`'s 6 stale flat `hcp_profile.avatar_enabled` fixtures nested inside `voice_live_instance` — this file's `scenarioData: unknown[]` typing meant `tsc -b` never flagged these, so they had to be found and fixed by direct grep/inspection (per 30-02's documented gap)
- `scenario-card.test.tsx`, `scenario-panel.test.tsx`, and `scenario-table.test.tsx`'s typed `Scenario`/`makeScenario()` fixtures replaced with the narrow `HcpProfileSummary` literal (`id`, `name`, `specialty`, `avatar_url`, `personality_type`, `voice_live_instance_id`, `voice_live_instance`), resolving all `tsc -b` excess-property errors cataloged by Plan 30-02
- `unified-session.test.tsx`'s `mockScenario.hcp_profile` restructured to nest `avatar_character`/`avatar_style`/`avatar_enabled` inside `voice_live_instance`; the dead `beforeEach` mutation of flat `voice_live_enabled`/`avatar_enabled` (fields the component never read) was deleted
- `unified-session.test.tsx`'s `AvatarView` mock extended to surface `avatarCharacter`/`avatarStyle` as data attributes, and the "starts digital human mode with avatar enabled" test now asserts `data-avatar-character="lisa"` / `data-avatar-style="casual-sitting"` — the fixture is now genuinely exercised through the real production read path (`scenario?.hcp_profile?.voice_live_instance?.avatar_character/style`) instead of just avoiding a compile error
- Project-wide `tsc -b` confirmed clean of all errors in this plan's 5 files; the only remaining errors are in `training.tsx`/`scenario-group-run.tsx`, explicitly reserved for the parallel Plan 30-03

## Task Commits

1. **Task 1: Nest avatar_enabled inside voice_live_instance in training.test.tsx** - `208509c` (test)
2. **Task 2: Narrow typed hcp_profile fixtures in scenario-card/scenario-panel/scenario-table test files** - `5399dbf` (test)
3. **Task 3: Restructure unified-session.test.tsx for genuine nested avatar propagation** - `9b9101e` (test)

## Files Created/Modified
- `frontend/src/pages/user/training.test.tsx` - 6 flat `hcp_profile.avatar_enabled` occurrences moved into `voice_live_instance.avatar_enabled` (written as single-line literals so grep-based drift checks distinguish nested from flat)
- `frontend/src/components/coach/scenario-card.test.tsx` - `mockScenario.hcp_profile` narrowed to `HcpProfileSummary` (dropped 20 fields not on the type: `hospital`, `title`, `emotional_state`, `communication_style`, `expertise_areas`, `prescribing_habits`, `concerns`, `objections`, `probe_topics`, `difficulty`, `is_active`, `created_by`, `created_at`, `updated_at`, `agent_id`, `agent_version`, `agent_sync_status`, `agent_sync_error`, `agent_instructions_override`, `knowledge_config_count`)
- `frontend/src/components/coach/scenario-panel.test.tsx` - same narrowing as above
- `frontend/src/components/admin/scenario-table.test.tsx` - `makeScenario()` factory's `hcp_profile` narrowed the same way; the existing `hcp_profile: undefined` override test left untouched (still valid against the new optional `hcp_profile?: HcpProfileSummary`)
- `frontend/src/pages/user/unified-session.test.tsx` - `mockScenario.hcp_profile` restructured to the nested shape; dead `beforeEach` mutations deleted; `AvatarView` mock extended with `avatarCharacter`/`avatarStyle` data attributes; new assertions added to the digital-human test
- `.planning/phases/30-scenario-api-d10-voicelive-instance-propagation-fix/deferred-items.md` - Logged the pre-existing, unrelated `scenario-panel.test.tsx` "DrugX" failure (Item 2)

## Decisions Made
- Wrote `training.test.tsx`'s nested fixture as an inline single-line object literal (`voice_live_instance: { enabled: true, avatar_enabled: true }`) rather than multi-line, since the plan's own acceptance-criteria grep (`^\s*avatar_enabled:`) is line-anchored and cannot structurally distinguish "nested inside voice_live_instance" from "flat sibling of hcp_profile" when each key is on its own line — writing it inline unambiguously satisfies the intent (no flat top-level `avatar_enabled` sibling remains) without relying on an imprecise grep pattern
- Accepted that 3 of `training.test.tsx`'s tests will fail until Plan 30-03's production fix (`training.tsx` reading `hcp.voice_live_instance.avatar_enabled` instead of the now-removed flat `hcp.avatar_enabled`) lands in the same integrated branch — confirmed this is intentional wave-level design, not a plan defect, since Plan 30-03's own `<verification>` section itself re-runs `training.test.tsx`
- Left the confirmed pre-existing `scenario-panel.test.tsx` "DrugX" failure untouched and logged it, rather than fixing the unrelated `tags`-vs-flat-`product`/`therapeutic_area` drift in `scenario-panel.tsx`, per SCOPE BOUNDARY

## Deviations from Plan

### Auto-fixed Issues

None — no bugs, missing functionality, or blocking issues requiring an in-scope code fix were introduced by this plan's own changes.

### Documented Cross-Plan Dependency (not an auto-fix — explicit plan-author intent)

**1. [Expected] 3 training.test.tsx tests fail pending Plan 30-03's merge**
- **Found during:** Task 1 verification (`npx vitest run training.test.tsx`)
- **Detail:** After nesting `avatar_enabled` inside `voice_live_instance` per this plan's contract, the tests `"passes text, voice, and digital human modes to F2F scenario cards"`, `"allows digital human mode on avatar-capable conference scenario cards"`, and `"starts conference digital human mode through the conference session page"` fail, because `training.tsx` (owned by the parallel Plan 30-03, explicitly out of scope for this plan per the orchestrator's upstream_context) still reads the now-removed flat `hcp.avatar_enabled` rather than the nested `hcp.voice_live_instance.avatar_enabled`.
- **Why not fixed:** Touching `training.tsx` was explicitly forbidden by the orchestrator to avoid conflicting with Plan 30-03's simultaneous work on the same lines. Plan 30-03's own `<verification>` block ("`cd frontend && npx vitest run training.test.tsx scenario-group-run.test.tsx --reporter=dot` passes") confirms the plan authors always intended both plans' changes to be present together before this file's full suite goes green — this is wave-level integration behavior, not a per-plan regression.
- **Verification of no other regression:** Full-suite `npx vitest run` before (baseline, checked out at commit `1cb1098`) vs. after this plan's 3 commits: 101 failed/2320 passed → 104 failed/2317 passed. The +3/-3 delta exactly matches these 3 documented tests; no other file's pass/fail count changed.
- **Resolution:** Automatic once Plan 30-03 merges into the same branch; no further action needed from this plan.

---

**Total deviations:** 0 auto-fixed. 1 documented, expected cross-plan integration gap (resolves automatically on merge with Plan 30-03).
**Impact on plan:** None on this plan's own scope or correctness — the fixture changes are correct per the `HcpProfileSummary` contract; only full-suite-green requires Plan 30-03's parallel commits.

## Issues Encountered
- Confirmed (via `git stash` / checkout-based baseline comparison) that `scenario-panel.test.tsx`'s "renders scenario product and area when expanded" failure pre-dates this plan and is unrelated to the `hcp_profile` shape change — logged to `deferred-items.md` rather than fixed, per SCOPE BOUNDARY.
- 14 other pre-existing failing test files (admin pages, azure-config, dashboard, reports, settings, training-materials, users, session-history, api-clients, i18n, voice-test-playground, voice-session navigation, analytics-components) were confirmed present in the baseline run and are unrelated to this plan's `hcp_profile` fixture scope — not touched.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All 5 files in this plan's scope compile clean under `tsc -b` and assert the correct nested `HcpProfileSummary`/`VoiceLiveInstanceSummary` shape
- `unified-session.test.tsx` now genuinely validates the `avatar_character`/`avatar_style` propagation path the production code reads, closing the gap flagged in this plan's `<interfaces>` block
- Once Plan 30-03 lands its `training.tsx`/`scenario-group-run.tsx` production fix, `training.test.tsx`'s remaining 3 tests will pass with no further changes needed on this plan's side
- Plan 30-05 (if it runs full-suite verification) should expect the 3 documented `training.test.tsx` failures to disappear once 30-03 is integrated

---
*Phase: 30-scenario-api-d10-voicelive-instance-propagation-fix*
*Completed: 2026-07-20*
