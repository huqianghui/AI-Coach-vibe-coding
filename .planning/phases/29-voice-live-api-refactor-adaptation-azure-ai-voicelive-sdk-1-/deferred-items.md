# Deferred Items — Phase 29

Out-of-scope issues discovered during plan execution but NOT fixed (per GSD deviation
scope-boundary rules: only auto-fix issues directly caused by the current plan's changes).

## From 29-03 execution

### 1. `resolve_voice_config()` no-VL-instance fallback crashes (owned by Plan 29-06)

- **File:** `backend/app/services/voice_live_instance_service.py`, function `resolve_voice_config()`
  (lines ~310-338, the "deprecated inline fields" fallback branch).
- **Symptom:** `AttributeError: 'HcpProfile' object has no attribute 'voice_live_enabled'`
  (and similarly for `voice_name`, `voice_type`, `avatar_character`, etc.) whenever
  `resolve_voice_config(profile)` is called for an `HcpProfile` that has no linked
  `VoiceLiveInstance` (`profile.voice_live_instance_id is None`).
- **Root cause:** Plan 29-05 (commit `333e011`) dropped the 14 deprecated inline
  voice/avatar columns from `HcpProfile`, but `resolve_voice_config()`'s fallback branch
  (for profiles without a linked `VoiceLiveInstance`) still reads those now-nonexistent
  columns. `29-05-PLAN.md` line 91 explicitly reserves this file for **Plan 29-06**
  ("do not edit that file here even though it also reads/writes these columns"), and
  `29-06-PLAN.md`'s `must_haves.truths` confirms: "resolve_voice_config() never reads a
  deprecated inline HcpProfile column ... its no-VL-instance fallback returns a
  hardcoded safe-defaults dict instead" (D-12, wave 3, depends_on [1, 5] -- i.e. runs
  after both 29-01 and 29-05).
- **Impact observed in 29-03:** Any test/call path that invokes `_load_connection_config()`
  or `handle_voice_live_websocket()`'s `voice_live_enabled` pre-check with an
  `hcp_profile_id` for a profile lacking a `VoiceLiveInstance` link crashes inside
  `resolve_voice_config()`. In `_load_connection_config()` this is swallowed by a broad
  `except Exception` (line ~243 of `voice_live_websocket.py`) and silently falls back to
  defaults -- which also means the D-08 agent-sync-required rejection is skipped for such
  profiles until Plan 29-06 lands the safe-defaults fix.
- **29-03 workaround (in-scope, test-only):** Every `HcpProfile(...)` fixture in
  `backend/tests/test_voice_live_websocket.py` that reaches `resolve_voice_config()` now
  links a minimal `VoiceLiveInstance` via a new `_link_vl_instance()` helper, routing
  through the working (non-crashing) `VoiceLiveInstance` branch. This is a temporary
  test-fixture accommodation, not a production fix.
- **Action needed:** No action from 29-03. Plan 29-06 (D-12) already covers fixing the
  actual `resolve_voice_config()` fallback branch. Once 29-06 lands, the
  `_link_vl_instance()` workaround in the 29-03 test file remains valid (it doesn't rely
  on the fallback crashing) and does not need to be reverted.

### 2. Full-suite regression confirms 99 pre-existing failures outside 29-03 scope (owned by Plans 29-05/29-06)

- **Verification run:** `pytest -x -q --deselect tests/test_agent_sync_service.py` executed
  from a clean 29-03-complete tree (config.py + voice_live_websocket.py + both scoped test
  files finalized, commit `333e011` for Plan 29-05 already landed). Result:
  `99 failed, 2426 passed, 15 skipped, 127 deselected, 16 warnings in 509.30s (0:08:29)`.
- **Root cause (same as Item 1):** Plan 29-05 (commit `333e011`) dropped 14 deprecated
  inline voice/avatar columns from `HcpProfile`. Every failure below is either (a) a test
  fixture that still constructs `HcpProfile(**kwargs)` with one of those dropped columns
  (`TypeError: '<column>' is an invalid keyword argument for HcpProfile`), or (b) a call
  path that reaches `resolve_voice_config()`'s no-VL-instance fallback branch, which still
  reads those now-nonexistent columns (`AttributeError`) -- the fix for that fallback is
  explicitly reserved for Plan 29-06 (D-12, wave 3, `depends_on: [1, 5]`, not yet executed).
- **Affected files (none owned by 29-03; all pre-existing, not caused by 29-03's changes):**
  - `tests/test_api_direct.py` (4 failures) -- `TestHcpProfilesDirect` CRUD fixtures
  - `tests/test_avatar_data_consistency.py` (7 failures) -- avatar sync/resolution fixtures
  - `tests/test_conference_api.py` (12 failures) -- conference session endpoint fixtures
  - `tests/test_conference_service.py` (24 failures) -- conference service fixtures
  - `tests/test_coverage_boost_2.py` (1 failure) -- `test_hcp_profile_with_override_instructions`
  - `tests/test_hcp_profile_service.py` (16 failures) -- HCP profile CRUD/agent-sync service
    fixtures
  - `tests/test_schemas_phase2.py` (2 failures) -- `TestHcpProfileSchemas` create-with-defaults
  - `tests/test_voice_live_instance_service.py` (1 failure) --
    `test_resolve_voice_config_inline_fallback_real_db` (directly exercises the Item 1
    fallback branch; expected to fail until Plan 29-06 lands)
  - `tests/test_voice_live_model.py` (8 failures) -- `TestHcpProfileOrm`/`TestHcpProfileSchemas`
    voice-live-model column/schema fixtures
  - `tests/test_voice_live_per_hcp.py` (4 failures) -- per-HCP token broker real-data fixtures
  - `tests/test_voice_live_service.py` (4 failures) -- `TestAgentModeAvailability` fixtures
  - `tests/test_agent_sync_service.py::TestRealAgentSyncOperations` (deselected from this run,
    but confirmed broken by the same root cause via `_create_profile()` helper using dropped
    inline fields)
- **Status:** A parallel background agent executing Plan 29-05 was observed actively fixing
  analogous fixture breakages in other test files (`test_sessions_api.py`,
  `test_hcp_agent_sync_integration.py`, etc.) concurrently with this run; none of the files
  listed above were touched by that agent as of this writing.
- **Action needed:** No action from 29-03 (none of these files are in 29-03's
  `files_modified` list; none of these failures are caused by 29-03's changes). Whoever
  executes Plan 29-06 (D-12, the `resolve_voice_config()` safe-defaults fix) and any
  follow-up fixture-repair pass should re-run this full-suite command and apply the same
  create-a-`VoiceLiveInstance`-and-link (or drop-invalid-kwarg) fix pattern established in
  29-03's `_link_vl_instance()` helper to each remaining broken fixture above.
