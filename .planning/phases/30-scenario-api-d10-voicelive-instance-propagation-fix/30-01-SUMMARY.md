---
phase: 30-scenario-api-d10-voicelive-instance-propagation-fix
plan: 01
subsystem: api
tags: [pydantic, fastapi, sqlalchemy, voice-live, scenario, hcp-profile]

# Dependency graph
requires:
  - phase: 29-voice-live-api-refactor-adaptation-azure-ai-voicelive-sdk-1-
    provides: HcpProfileResponse.voice_live_instance nested-field pattern (backend/app/schemas/hcp_profile.py:93-95), VoiceLiveInstanceSummary schema, dropped inline HcpProfile avatar/voice columns
provides:
  - HcpProfileBrief (backend/app/api/scenarios.py) now nests voice_live_instance: VoiceLiveInstanceSummary | None via from_attributes=True, matching HcpProfileResponse
  - Graceful null branch for unbound HCPs (voice_live_instance_id is None) across GET /scenarios/{id}, /scenarios, /scenarios/active
  - hcp_profile.avatar_url and hcp_profile.personality_type restored on every scenario response
  - backend/app/schemas/scenario.py::HcpProfileSummary synced to the same nested shape (dead code, kept consistent)
affects: [scenario-group-run.tsx (frontend consumer via ScenarioOut import chain), 30-02, 30-03, 30-04, 30-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Nested response schema with from_attributes=True auto-resolves SQLAlchemy relationships without manual flattening classmethods or field_validators"

key-files:
  created: []
  modified:
    - backend/app/api/scenarios.py
    - backend/app/schemas/scenario.py
    - backend/tests/test_scenario_avatar_fields.py
    - backend/tests/test_avatar_data_consistency.py

key-decisions:
  - "Deleted HcpProfileBrief.from_hcp_profile() and ScenarioOut.resolve_hcp_avatar validator entirely rather than keeping them as dead code -- grep-confirmed no direct dict-construction call sites, so from_attributes=True on the nested field takes over automatically"
  - "backend/app/schemas/scenario.py::HcpProfileSummary kept in sync with the same nested shape despite being confirmed dead code (never a response_model), for conceptual consistency with the live HcpProfileBrief"

patterns-established:
  - "Rule 1 fix: tests/test_avatar_data_consistency.py also asserted the old flat avatar_character/avatar_style shape and the 'lori'/'casual' fabricated-defaults fallback -- updated to the nested hcp_profile.voice_live_instance path and the correct null-on-unassigned contract, since this file's assumptions were invalidated by the same production change"

requirements-completed: ["D-10 propagation (v1.0 audit integration gap, critical)"]

# Metrics
duration: ~15min
completed: 2026-07-20
---

# Phase 30 Plan 01: Scenario API D-10 VoiceLiveInstance Propagation Fix Summary

**HcpProfileBrief in the real `/api/v1/scenarios*` response_model now nests `voice_live_instance: VoiceLiveInstanceSummary | None` via `from_attributes=True` instead of hardcoding flat `avatar_character="lori"`/`avatar_style="casual"` defaults and manually flattening the relationship.**

## Performance

- **Duration:** ~15 min
- **Completed:** 2026-07-20
- **Tasks:** 2 (TDD RED/GREEN pair)
- **Files modified:** 4

## Accomplishments
- `GET /api/v1/scenarios/{id}`, `GET /api/v1/scenarios`, and `GET /api/v1/scenarios/active` now return `hcp_profile.voice_live_instance` as a true nested object matching `VoiceLiveInstanceSummary`, resolved automatically from the ORM relationship (no more hardcoded `"lori"`/`"casual"`/`False`/`False` defaults baked into every response regardless of the actual assigned VoiceLiveInstance)
- HCPs with no VoiceLiveInstance assigned (`voice_live_instance_id is None`, D-13 unbound/legacy rows) now serialize successfully with `hcp_profile.voice_live_instance == null` instead of silently returning fake defaults or risking a crash
- `hcp_profile.avatar_url` and `hcp_profile.personality_type` restored to every scenario response (previously silently dropped by the old `HcpProfileBrief`)
- Deleted `HcpProfileBrief.from_hcp_profile()` classmethod and `ScenarioOut.resolve_hcp_avatar` field_validator entirely — both were dead-branch code once the nested field takes over relationship resolution
- `backend/app/schemas/scenario.py::HcpProfileSummary` (confirmed dead code, never a `response_model`) synced to the identical nested shape for consistency
- `backend/app/schemas/scenario_group.py` imports `ScenarioOut` directly from `scenarios.py`, so this single fix also covers `scenario-group-run.tsx`'s backend data source with no separate change needed

## Task Commits

1. **Task 1 (RED): Rewrite test_scenario_avatar_fields.py to assert the correct nested shape** - `8634801` (test)
2. **Task 2 (GREEN): Rewrite HcpProfileBrief to nested shape, sync dead schema, pass tests** - `b3eb757` (feat, includes Rule 1 fix to test_avatar_data_consistency.py)

_TDD plan: RED task confirmed 5 failures with `KeyError('voice_live_instance')` against the unfixed `scenarios.py`; GREEN task made all pass._

## Files Created/Modified
- `backend/app/api/scenarios.py` - `HcpProfileBrief` now declares `voice_live_instance: VoiceLiveInstanceSummary | None` with `from_attributes=True`; deleted `from_hcp_profile()` and `resolve_hcp_avatar` validator; `ScenarioOut` unchanged apart from validator removal
- `backend/app/schemas/scenario.py` - `HcpProfileSummary` synced to the same nested shape (dead code, kept consistent)
- `backend/tests/test_scenario_avatar_fields.py` - Rewrote all 4 existing test methods to assert the nested `data["hcp_profile"]["voice_live_instance"][...]` path; added `test_scenario_with_unbound_hcp_returns_null_voice_live_instance` covering the D-13 null-binding regression case
- `backend/tests/test_avatar_data_consistency.py` - Rule 1 fix: updated all avatar-character/style assertions to the nested `voice_live_instance` path and corrected the "no VL Instance assigned" test to assert `null` instead of fabricated `"lori"`/`"casual"` defaults (its docstrings referenced the now-deleted `from_hcp_profile()` resolver and were updated accordingly)

## Decisions Made
- Deleted the manual-flattening classmethod and validator entirely rather than leaving them as unused dead code, per the plan's grep-verified evidence that neither is exercised by any real call site
- Kept `backend/app/schemas/scenario.py::HcpProfileSummary` in sync with the same nested shape even though it is confirmed dead code, since it defines the same conceptual entity as the live `HcpProfileBrief`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] tests/test_avatar_data_consistency.py broke after HcpProfileBrief nesting**
- **Found during:** Task 2 broader verification (`pytest -k scenario -q`)
- **Issue:** This file (not listed in the plan's `files_modified`) asserted the old flat `hcp_profile["avatar_character"]`/`["avatar_style"]` shape in 7 assertions across `TestAvatarSyncOnAssign`, `TestAvatarSyncOnUpdate`, and `TestScenarioApiAvatarResolution`, plus one test (`test_scenario_without_vl_instance_uses_safe_defaults`) that specifically asserted the old fabricated `"lori"`/`"casual"` fallback defaults for unassigned HCPs — a behavior the plan's D-10 fix intentionally replaces with a graceful `null`
- **Fix:** Updated all 7 flat assertions to the nested `hcp_profile["voice_live_instance"][...]` path; rewrote the "no VL Instance" test to assert `hcp_profile["voice_live_instance"] is None` and `voice_live_instance_id is None` instead of fake defaults; updated docstrings referencing the deleted `HcpProfileBrief.from_hcp_profile()` resolver
- **Files modified:** backend/tests/test_avatar_data_consistency.py
- **Verification:** `pytest -k scenario -q` — 173 passed (was 168 passed, 5 failed before this fix)
- **Committed in:** b3eb757 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix, out-of-plan test file directly broken by the in-scope production change)
**Impact on plan:** Necessary correctness fix — the plan's own `<verification>` section required `pytest -k scenario -q` to pass with no other test depending on the flat shape; this file was an unlisted exception. No scope creep beyond making the plan's own success criteria true.

## Issues Encountered
- Broader sanity check `pytest -k "hcp_profile or voice_live"` surfaced 5 pre-existing failures in `tests/test_voice_live_session_context.py` and `tests/test_voice_live_websocket.py` (`TestRealAzureSessionConfig`, `TestRealVoiceLiveIntegration`) that require a live Azure CLI credential / real Voice Live service connection. Confirmed via grep these files have no import or reference to `scenarios.py`, `HcpProfileBrief`, or `VoiceLiveInstanceSummary` — unrelated to this plan's change. Logged to `.planning/phases/30-scenario-api-d10-voicelive-instance-propagation-fix/deferred-items.md` per SCOPE BOUNDARY rather than fixed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- D-10 propagation gap closed at its single fix point; `scenario_group.py`'s `ScenarioOut` import means no separate frontend-data-source backend change is needed for later frontend-facing plans in this phase (30-02 through 30-05)
- Frontend plans in this wave/subsequent waves can now rely on `hcp_profile.voice_live_instance` being present as a nested object (or `null`) on every scenario API response

---
*Phase: 30-scenario-api-d10-voicelive-instance-propagation-fix*
*Completed: 2026-07-20*

## Self-Check: PASSED

All created/modified files confirmed present on disk; both task commits (8634801, b3eb757) confirmed present in git log.
