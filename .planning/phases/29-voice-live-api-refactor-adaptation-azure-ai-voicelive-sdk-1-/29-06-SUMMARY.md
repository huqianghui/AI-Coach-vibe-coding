---
phase: 29-voice-live-api-refactor-adaptation-azure-ai-voicelive-sdk-1-
plan: 06
subsystem: backend
tags: [hcp-profile, voice-live-instance, resolve-voice-config, service-layer, d-12]

# Dependency graph
requires:
  - phase: "29-05"
    provides: "Drops the 14 deprecated inline voice/avatar columns from HcpProfile; skipped test_resolve_voice_config_inline_fallback_real_db pending this plan"
provides:
  - "resolve_voice_config()'s no-VL-instance fallback returns a hardcoded safe-defaults dict (voice_live_enabled=False, avatar_enabled=False) instead of reading the 14 deleted HcpProfile columns"
  - "Dead denormalized avatar-mirror writes removed from update_instance()/assign_to_hcp()"
  - "2 rewritten unit tests proving the new fallback shape, including a MagicMock(spec=...) regression guard against reintroducing deprecated-column reads"
affects: [29-08, 29-09, 29-10]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "MagicMock(spec=[...allowed attrs...]) as a regression guard: constrains a mock to only the attributes a function is supposed to touch, so any accidental read of a removed/deprecated attribute raises AttributeError in the test itself"

key-files:
  created: []
  modified:
    - backend/app/services/voice_live_instance_service.py
    - backend/app/services/agent_sync_service.py
    - backend/tests/test_voice_live_instance_service.py

key-decisions:
  - "resolve_voice_config()'s fallback flips voice_live_enabled/avatar_enabled from True to False (D-10/D-12 alignment): a profile with no assigned VoiceLiveInstance should not silently get voice/avatar capability, matching scenarios.py's HcpProfileBrief.from_hcp_profile() which already defaulted to False"
  - "test_agent_sync_service.py::TestRealAgentSyncOperations (6 failures) NOT fixed -- confirmed via traceback that all 6 fail inside the test's own _create_profile() helper (HcpProfile(**defaults) TypeError on deprecated kwargs), a fixture-construction bug that predates and is unrelated to resolve_voice_config()'s fallback branch this plan fixes. Out of this plan's file-ownership scope (test_agent_sync_service.py owned by Plan 29-02); documented in deferred-items.md Item 3 rather than fixed"

patterns-established:
  - "MagicMock(spec=[allowed_attrs]) regression guard for fallback/defensive code paths that must not read deprecated/removed model attributes"

requirements-completed: [D-12]

# Metrics
duration: ~15min
completed: 2026-07-19
---

# Phase 29 Plan 06: resolve_voice_config safe-defaults fallback (D-12) Summary

Replaced `resolve_voice_config()`'s no-VL-instance fallback with a hardcoded safe-defaults dict (`voice_live_enabled=False`, `avatar_enabled=False`) that reads zero `HcpProfile` columns, deleted the dead denormalized avatar-mirror writes in `update_instance()`/`assign_to_hcp()`, and rewrote the 2 tests exercising that fallback branch.

## Performance

- **Duration:** ~15 min
- **Started:** 2026-07-19T14:33Z (approx, first Edit)
- **Completed:** 2026-07-19T14:48Z
- **Tasks:** 2/2 completed
- **Files modified:** 3

## Accomplishments
- `resolve_voice_config()`'s fallback branch no longer reads any of the 14 `HcpProfile` columns dropped by Plan 29-05's migration -- eliminates a live `AttributeError` for every HCP with no assigned Voice Live Instance
- Deleted dead "denormalized cache" avatar-mirror writes in `update_instance()` and `assign_to_hcp()` (they wrote to columns that no longer exist)
- Unskipped `test_resolve_voice_config_inline_fallback_real_db` (was `pytest.mark.skip` pending this plan since Plan 29-05) and rewrote both fallback-branch tests to assert the new safe-defaults dict
- Added a `MagicMock(spec=["voice_live_instance", "id"])` regression guard in the mock-based test that will raise `AttributeError` if the fallback branch ever reads any attribute beyond those two again

## Task Commits

1. **Task 1: Remove dead avatar-mirror writes; replace resolve_voice_config's fallback with a column-free safe-defaults dict (D-12)** - `2832e67` (fix)
2. **Task 2: Rewrite the 2 resolve_voice_config fallback tests to match the new safe-defaults dict** - `c4feccf` (test)

## Files Created/Modified
- `backend/app/services/voice_live_instance_service.py` - Module docstring updated; `update_instance()`'s `avatar_fields_changed` computation and write block deleted; `assign_to_hcp()`'s 3-line avatar mirror + comment deleted; `resolve_voice_config()`'s fallback docstring and return dict replaced with a hardcoded safe-defaults dict (`voice_live_enabled=False`, `avatar_enabled=False`, all other fields hardcoded matching prior defaults)
- `backend/app/services/agent_sync_service.py` - Stale docstring line in `build_voice_live_metadata()` updated to describe the new safe-defaults behavior instead of the removed "VoiceLiveInstance > inline HcpProfile" priority language; no logic change
- `backend/tests/test_voice_live_instance_service.py` - `test_resolve_voice_config_inline_fallback` rewritten with `MagicMock(spec=["voice_live_instance", "id"])` and new safe-defaults assertions; `test_resolve_voice_config_inline_fallback_real_db` unskipped and its final assertion block updated (`voice_live_enabled is False` instead of `is True`)

## Decisions Made
- `voice_live_enabled`/`avatar_enabled` flip from `True` to `False` in the fallback -- deliberate behavior change per D-10 ("every HCP must have a VL Instance"; unassigned = disabled), now consistent with `scenarios.py`'s existing `HcpProfileBrief` default.
- Did not fix `test_agent_sync_service.py::TestRealAgentSyncOperations` -- see Issues Encountered below.

## Deviations from Plan

None from the plan's own task actions -- both tasks executed exactly as specified in the plan's `<action>` blocks (docstring text, deleted blocks, and dict literal all match verbatim).

## Issues Encountered

**Orchestrator's upstream assumption about `test_agent_sync_service.py::TestRealAgentSyncOperations` did not hold.** The task brief stated these 6 tests "fail via the resolve_voice_config fallback path" and should turn green after this plan's fix. Investigation (full traceback) showed all 6 fail earlier, inside the test file's own `_create_profile()` helper: `HcpProfile(**defaults)` still passes 14 deprecated inline-voice kwargs (`voice_live_enabled`, `avatar_character`, etc.) directly to the ORM constructor, which raises `TypeError: 'voice_live_enabled' is an invalid keyword argument for HcpProfile` before `sync_agent_for_profile()`/`resolve_voice_config()` is ever invoked. This is the same root-cause class as Plan 29-03's `deferred-items.md` Item 2 (fixture never migrated to the "create-a-VoiceLiveInstance-and-link" pattern), not the `AttributeError` fallback-crash bug D-12 fixes.

- Confirmed via `pytest tests/test_agent_sync_service.py -v`: **94 passed, 6 failed** -- all 94 mock-based tests (including the ones exercising `build_voice_live_metadata()`'s `voice_live_enabled=False` mock path) pass with no regression from this plan's `voice_live_enabled: False` fallback change. Only the 6 `TestRealAgentSyncOperations` real-DB integration tests fail, and only via the pre-existing fixture bug above.
- `test_agent_sync_service.py` is outside this plan's file-ownership scope (owned by Plan 29-02's landed work per the orchestrator's stated boundaries) and was not edited.
- Documented in full detail in `.planning/phases/29-voice-live-api-refactor-adaptation-azure-ai-voicelive-sdk-1-/deferred-items.md` (new "From 29-06 execution" Item 3), including the exact fix pattern (link a `VoiceLiveInstance`, drop the 14 kwargs) for whoever picks it up next.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

`resolve_voice_config()` has zero remaining dependencies on the columns Plan 29-05 dropped. `backend/tests/test_voice_live_instance_service.py` is fully green (34 passed, 0 skipped). `backend/tests/test_agent_sync_service.py`'s 94 mock-based tests are green with no regression; its 6 `TestRealAgentSyncOperations` real-DB tests remain broken by a pre-existing, out-of-scope fixture bug (tracked in deferred-items.md, not blocking for this plan's D-12 scope). No blockers for downstream Phase 29 plans.

---
*Phase: 29-voice-live-api-refactor-adaptation-azure-ai-voicelive-sdk-1-*
*Completed: 2026-07-19*

## Self-Check: PASSED

- `backend/app/services/voice_live_instance_service.py` — FOUND
- `backend/app/services/agent_sync_service.py` — FOUND
- `backend/tests/test_voice_live_instance_service.py` — FOUND
- `.planning/phases/29-voice-live-api-refactor-adaptation-azure-ai-voicelive-sdk-1-/29-06-SUMMARY.md` — FOUND
- Commit `2832e67` — FOUND
- Commit `c4feccf` — FOUND
