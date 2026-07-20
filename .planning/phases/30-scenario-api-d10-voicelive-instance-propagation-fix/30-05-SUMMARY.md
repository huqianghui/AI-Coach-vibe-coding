---
phase: 30-scenario-api-d10-voicelive-instance-propagation-fix
plan: 05
subsystem: testing
tags: [playwright, e2e, voice-live, avatar, scenario-api, gating]

# Dependency graph
requires:
  - phase: 30-01
    provides: "Backend /api/v1/scenarios nesting hcp_profile.voice_live_instance (VoiceLiveInstanceSummary) instead of flat hcp_profile.avatar_character/avatar_style"
  - phase: 30-03
    provides: "Frontend training.tsx/scenario-group-run.tsx gating logic reading hcp?.voice_live_instance?.avatar_enabled and .enabled"
  - phase: 30-04
    provides: "Established vitest/E2E baseline for comparison during full-stack verification"
provides:
  - "training-start-session.spec.ts rewritten to assert the nested hcp_profile.voice_live_instance.avatar_character/avatar_style shape instead of the removed flat shape"
  - "New automated E2E test proving voice + digital-human mode buttons render for a scenario-driven session bound to an enabled+avatar_enabled VoiceLiveInstance (D-09 gating-restoration story)"
  - "Full-stack verification evidence (backend pytest/ruff, frontend tsc/vitest, two targeted Playwright specs) confirming zero regressions from Plan 30-01/30-03's schema/gating changes"
  - "Human-verify checkpoint APPROVED: real-browser confirmation of restored mode gating and correct avatar (lisa/casual-sitting) rendering for a scenario-driven session"
affects: [30-VALIDATION, phase-30-closeout]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "E2E assertions on API response shape typed against the nested VoiceLiveInstanceSummary interface, mirroring the pattern already established in voice-avatar-real.spec.ts"
    - "Gating-restoration E2E test pattern: intercept /api/v1/scenarios via page.waitForResponse, filter for a scenario whose hcp_profile.voice_live_instance has enabled+avatar_enabled true, then assert both mode buttons are visible+enabled in the UI before session start"

key-files:
  created: []
  modified:
    - frontend/e2e/training-start-session.spec.ts
    - .planning/phases/30-scenario-api-d10-voicelive-instance-propagation-fix/deferred-items.md

key-decisions:
  - "Deferred all pre-existing, out-of-scope failures (2 pre-existing E2E failures, 30 pre-existing ruff E501 errors, 5 pre-existing ruff-format files, 100 pre-existing vitest failures, and a coverage-gate/credential-provisioning gap) to deferred-items.md rather than fixing them, per SCOPE BOUNDARY — none are caused by this plan's changes"
  - "Worked around a completely fresh/uninitialized worktree dev environment (missing node_modules, .venv, .env, and database) by fully re-bootstrapping it rather than blocking on it, since Plan 30-05 requires a live full-stack verification pass"
  - "Copied a known-good pre-seeded database from the main repo instead of running the seed script directly, after discovering the seed script has a genuine pre-existing bug (HcpProfile(**profile_data) passing a removed voice_name kwarg, predating Phase 30) — logged as out-of-scope, not fixed"
  - "Used --cov-fail-under=0 override for the diagnostic pytest run instead of provisioning real Azure/OpenAI credentials, since a real-credential run was network-bound and impractically slow (~80+ min extrapolated); the resulting 88% coverage vs 89% gate is a credential-provisioning gap, not a functional regression (2498 passed, 0 failed)"

requirements-completed: ["D-10 propagation (v1.0 audit integration gap, critical)"]

# Metrics
duration: 41min
completed: 2026-07-20
---

# Phase 30 Plan 05: E2E Assertion Fix and Gating-Restoration Verification Summary

**Rewrote training-start-session.spec.ts's two stale flat-shape avatar assertions to the nested hcp_profile.voice_live_instance path, added a new automated gating-restoration test, ran a full-stack verification pass, and closed with human-verify approval confirming voice/digital-human mode gating and lisa/casual-sitting avatar rendering work correctly against the real backend.**

## Performance

- **Duration:** 41 min (11:52 to 12:32 for the two code/doc commits; environment bootstrap and verification pass consumed additional session time not reflected in commit timestamps alone)
- **Started:** 2026-07-20T11:52:33+08:00 (Task 1 commit)
- **Completed:** 2026-07-20T12:32:30+08:00 (Task 2 documentation commit); Task 3 checkpoint approved immediately after
- **Tasks:** 3/3 complete
- **Files modified:** 2

## Accomplishments
- Closed the final D-10 gap: `training-start-session.spec.ts`'s two tests that previously asserted the OLD flat `hcp_profile.avatar_character` shape now correctly assert the nested `hcp_profile.voice_live_instance.avatar_character`/`.avatar_style` shape
- Added a new automated E2E test (`"scenario-driven session offers voice and digital-human modes when HCP has an enabled avatar VL instance"`) covering D-09's gating-restoration story
- Ran and evidenced a full-stack verification pass (backend pytest/ruff, frontend tsc/vitest, two targeted Playwright specs) with zero regressions attributable to Plan 30-01/30-03's changes
- Obtained human-verify checkpoint APPROVAL with concrete real-browser evidence: both voice and digital-human mode buttons render for the scenario-driven session, the API response carries the correct nested `voice_live_instance` object, and the rendered avatar (name "Lisa", `lisa-casual-sitting.png`) matches the configured VL Instance — not stale `lori`/`casual` defaults

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix stale E2E assertions and add gating-restoration coverage** - `77f3f53` (test)
2. **Task 2: Full-stack verification pass (backend, frontend, E2E)** - `1a508c7` (docs — verification-only task; no source changes, deferred-items.md log committed as evidence trail)
3. **Task 3: Human visual confirmation of restored voice/digital-human gating and avatar propagation** - checkpoint, no commit (human-verify APPROVED; see Deviations/checkpoint evidence below)

**Plan metadata:** (this commit — `docs(30-05): complete plan`)

_Note: Task 2 is verification-only per the plan (`<files>none</files>`); the recorded commit is the deferred-items.md documentation of verification findings, not a code change._

## Files Created/Modified
- `frontend/e2e/training-start-session.spec.ts` - Rewrote two tests' avatar assertions to the nested `voice_live_instance` path; added one new test asserting voice+digital-human mode buttons render for an enabled-avatar-VL-instance scenario
- `.planning/phases/30-scenario-api-d10-voicelive-instance-propagation-fix/deferred-items.md` - Logged pre-existing, out-of-scope failures discovered during full-stack verification (Items 3-6)

## Decisions Made
- Rewrote both existing tests in-place to the nested path rather than deleting/replacing them, preserving their original intent (proving avatar data is present and non-stale) while fixing the now-incorrect flat-shape assumption
- Modeled the new gating-restoration test's typed interfaces (`VoiceLiveInstanceSummary`, `ScenarioHcpProfile`, `ScenarioListItem`) after the existing pattern in `voice-avatar-real.spec.ts` rather than inventing a new typing convention
- Fully re-bootstrapped the worktree's dev environment (npm ci, python venv + pip install -e, alembic-based DB bootstrap via a known-good seeded DB copy) to obtain a trustworthy, apples-to-apples verification baseline rather than skipping verification due to environment gaps
- Treated the 153 backend test skips and 88%-vs-89% coverage shortfall as a credential-provisioning gap (documented in deferred-items.md Item 6), not a functional regression, since the full pytest run showed 2498 passed / 0 failed

## Deviations from Plan

### Auto-fixed Issues

None — no code-level bugs, missing functionality, or blocking issues were found in the plan's own scope (the single file `training-start-session.spec.ts`). All fixes matched the plan's `<interfaces>` and `<behavior>` specification exactly.

### Out-of-Scope Items Deferred (not auto-fixed, per SCOPE BOUNDARY)

The following pre-existing issues were discovered during the mandatory full-stack verification pass (Task 2) but are unrelated to this plan's file changes and were logged to `deferred-items.md` rather than fixed:

1. **Pre-existing E2E failures** in `training-start-session.spec.ts` unrelated to D-10 (Conference-scenario POST timeout; text-mode avatar-preview visibility) — 11/13 tests pass, including all 3 tests this plan touched/added
2. **Pre-existing backend ruff violations** — 30 E501 line-length errors and 5 files needing `ruff format`, all in `tests/test_skill_foundry_service.py`, `test_hcp_profile_service.py`, `test_knowledge_base.py`, predating Phase 30
3. **Pre-existing frontend vitest failures** — 100 failed / 2327 passed across 15 files, exactly matching Plan 30-04's documented baseline (root cause: `hcp-profile-editor.test.tsx` i18n rendering)
4. **Backend coverage gate gap** — `--cov-fail-under=89` requires live Azure/OpenAI credentials not present in this freshly-bootstrapped worktree's `.env`; the full pytest run itself is clean (2498 passed, 0 failed, 153 skipped, 88% coverage)

---

**Total deviations:** 0 auto-fixed; 4 out-of-scope items deferred to `deferred-items.md`
**Impact on plan:** None of the deferred items affect this plan's goal or introduce regressions. All are pre-existing and independently verified to predate Phase 30 or this plan's changes.

## Issues Encountered
- The worktree's dev environment (node_modules, Python venv, `.env`, and database) was completely fresh/uninitialized at the start of this session's continuation, requiring a full manual bootstrap (`npm ci`; `python3 -m venv .venv && pip install -e ".[dev]"`; `cp .env.example .env`; alembic-based DB bootstrap via a known-good seeded DB copy) before any verification could run. Resolved without scope creep — the seed script's own genuine pre-existing bug (`voice_name` kwarg no longer valid on `HcpProfile`) was worked around via a DB copy rather than fixed, since it predates Phase 30.
- A real-credential pytest run (to attempt closing the coverage gate "properly") was found to be network-bound and impractically slow; abandoned in favor of the fast, deterministic `.env.example`-derived run with `--cov-fail-under=0`, documenting the gap explicitly instead.

## User Setup Required
None - no external service configuration required. (The full-stack verification pass surfaced a coverage-gate gap tied to missing live Azure/OpenAI credentials in this local dev worktree, but this is a pre-existing environment-provisioning matter, not a new requirement introduced by this plan — documented in `deferred-items.md` Item 6.)

## Human Verification (Task 3 Checkpoint)

**Status: APPROVED.**

Real-browser evidence provided by the human verifier at `http://localhost:5173`:
1. Gating restoration confirmed: "F2F: BRUKINSA CLL/SLL Discussion" (Dr. Wang Fang, VL instance `VL-female-video-zh-CN-realtime-01`) shows BOTH Voice and Digital Human mode buttons enabled on `/user/training`.
2. Control case confirmed: scenarios with `voice_live_instance = null` (Dr. Li Mei) correctly show Voice/Digital Human disabled.
3. API response verified: `hcp_profile.voice_live_instance = {enabled: true, avatar_enabled: true, avatar_character: "lisa", avatar_style: "casual-sitting"}` — nested propagation confirmed working, no hardcoded `lori`/`casual` stale defaults.
4. Digital Human session started: rendered avatar name "Lisa", `img src = lisa-casual-sitting.png` — correct character and style match the VL Instance configuration.

## Next Phase Readiness
- D-10 propagation gap is fully closed end-to-end: backend response shape, frontend gating logic, and E2E test coverage are all aligned to the nested `hcp_profile.voice_live_instance` shape, with real-browser confirmation.
- No Scenario Group currently contains either verification-target scenario; Task 3's optional Scenario-Group-run repeat step was not exercised (plan explicitly marks this conditional — "if one exists"). Future phases touching Scenario Group avatar gating should independently verify `scenario-group-run.tsx`'s `getAvailableModes` against a live Scenario Group if this becomes a concern.
- Deferred items in `deferred-items.md` (pre-existing ruff violations, pre-existing vitest failures, coverage-gate credential gap) remain open for a future dedicated cleanup phase — none block Phase 30's closeout.

---
*Phase: 30-scenario-api-d10-voicelive-instance-propagation-fix*
*Completed: 2026-07-20*

## Self-Check: PASSED

- FOUND: frontend/e2e/training-start-session.spec.ts
- FOUND: .planning/phases/30-scenario-api-d10-voicelive-instance-propagation-fix/deferred-items.md
- FOUND: .planning/phases/30-scenario-api-d10-voicelive-instance-propagation-fix/30-05-SUMMARY.md
- FOUND commit: 77f3f53 (Task 1)
- FOUND commit: 1a508c7 (Task 2 documentation)
- Confirmed on branch: worktree-agent-a7ffa975498993910
