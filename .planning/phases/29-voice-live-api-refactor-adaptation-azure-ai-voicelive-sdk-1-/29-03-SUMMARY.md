---
phase: 29-voice-live-api-refactor-adaptation-azure-ai-voicelive-sdk-1-
plan: 03
subsystem: backend
tags: [voice-live, websocket, agent-sync, entra-auth, api-version, mandatory-agent-mode]

# Dependency graph
requires:
  - "29-01: azure-ai-voicelive pinned to 1.3.0b1; api_version must be explicitly passed at every connect() call site"
  - "29-02: settings.voice_live_api_version=\"2026-07-15\" GA constant; agent_sync_service.resync_classic_agent(db, profile), test-proven never to orphan agent_id on failure (T-29-01)"
provides:
  - "AgentSyncRequiredError(ValueError) -- raised when an HCP voice session requires a synced hosted agent but none is available (D-08); caught before any generic ValueError/Exception clause in both _load_connection_config's internal handling and handle_voice_live_websocket's caller-side handling"
  - "_resolve_voice_live_credential(api_key) -- Entra-first (DefaultAzureCredential), API-key-fallback (AzureKeyCredential) credential resolution for Voice Live connect() (D-01), reused for the entire connection lifetime"
  - "Every azure.ai.voicelive.aio.connect() call site (agent mode AND model mode) passes api_version=settings.voice_live_api_version -- single GA source of truth (D-02)"
  - "_load_connection_config auto-resyncs classic asst_* agent_ids via resync_classic_agent() before deciding agent mode (D-05), then hard-rejects any profile that still isn't synced-and-hosted (D-08) -- no silent fallback to Model mode for HCP sessions"
  - "voice_live_hosted_agent_name/project/endpoint settings deleted from config.py (D-07); classic-agent connect branch and _apply_voice_agent_patch() monkey-patch deleted from voice_live_websocket.py (D-06)"
affects: [29-04, 29-06]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "AgentSyncRequiredError subclasses ValueError but is caught in its own except clause BEFORE any generic except ValueError/except Exception -- ordering is load-bearing (Python evaluates except clauses in order); this pattern must be replicated everywhere else this error can surface (e.g. 29-04's webrtc mirror)"
    - "One credential resolved via _resolve_voice_live_credential() per connection, reused across both agent-mode and model-mode connect() branches, explicitly closed in a finally block only when it's the Entra (DefaultAzureCredential) variant"
    - "resync_classic_agent() called only when profile.agent_id starts with 'asst_' -- already-hosted or empty agent_ids skip the resync call entirely and go straight to the synced-and-hosted gate"

key-files:
  created:
    - .planning/phases/29-voice-live-api-refactor-adaptation-azure-ai-voicelive-sdk-1-/deferred-items.md
  modified:
    - backend/app/config.py
    - backend/app/services/voice_live_websocket.py
    - backend/tests/test_voice_live_websocket.py
    - backend/tests/test_voice_live_session_context.py

key-decisions:
  - "Combined Task 1 (D-05/D-07/D-08 in _load_connection_config) and Task 2 (D-01/D-02/D-06 in the connect branch) into a single production-code commit (a631198) rather than two, because both tasks edited the same file (voice_live_websocket.py) interleaved in a prior session without an intermediate commit boundary -- splitting after the fact would have required risky partial-file staging with no functional benefit"
  - "Test suite changes (Task 3, both test files) committed separately (f054ff1) from production code, preserving the feat/test commit-type separation even though the task-level 1:1 commit mapping was collapsed"
  - "resolve_voice_config()'s no-VL-instance fallback branch (voice_live_instance_service.py) crashes with AttributeError for any HcpProfile lacking a linked VoiceLiveInstance, because Plan 29-05 dropped the 14 deprecated inline columns that fallback still reads -- confirmed via 29-05-PLAN.md/29-06-PLAN.md as explicitly out of scope (reserved for Plan 29-06, D-12, wave 3). Worked around in-scope by adding a _link_vl_instance() test helper that links every affected HcpProfile fixture to a VoiceLiveInstance, routing through the working branch instead of touching the out-of-scope file"

patterns-established: []

# Metrics
duration: ~2h (across two sessions, majority in test-suite rewrite + cross-plan schema-collision investigation)
completed: 2026-07-19
---

# Phase 29 Plan 03: Mandatory agent-mode enforcement, Entra auth, GA api-version Summary

Rewrote the Voice Live WebSocket proxy's connection-config and connect-branch logic to converge D-01/D-02/D-05/D-06/D-07/D-08: agent mode is now mandatory (hard rejection via `AgentSyncRequiredError`, no silent Model-mode fallback), credentials resolve Entra-first with API-key fallback, and every `connect()` call carries the single GA `api_version="2026-07-15"`.

## What was done

**Task 1 (D-05/D-07/D-08, `_load_connection_config`):**
- Deleted `voice_live_hosted_agent_name/project/endpoint` from `backend/app/config.py` (D-07); `voice_live_agent_mode_enabled` left untouched (still consumed by `voice_live_service.py`, out of scope).
- Added `AgentSyncRequiredError(ValueError)` in `voice_live_websocket.py`, replacing the deleted `_apply_voice_agent_patch()` monkey-patch at the same location.
- Rewrote the agent-mode decision: classic `asst_*` agent_ids are auto-resynced via `resync_classic_agent()` (D-05) before the gate is evaluated; any profile that isn't `agent_id` truthy + `agent_sync_status == "synced"` afterward raises `AgentSyncRequiredError` (D-08) — unless `force_model_mode=True` (training-session path bypasses the gate entirely, unchanged).
- Deleted the hosted-override read and the "standalone hosted agent mode" block (D-07 cleanup) — inserted an `except AgentSyncRequiredError: raise` clause before the existing broad `except Exception:` so the rejection is never swallowed (T-29-02 mitigation).

**Task 2 (D-01/D-02/D-06, connect branch):**
- `handle_voice_live_websocket()` now catches `AgentSyncRequiredError` before the generic `except ValueError`, sending an `AGENT_SYNC_REQUIRED` error code to the client and returning without ever calling `connect()`.
- Added `_resolve_voice_live_credential(api_key)`: tries `DefaultAzureCredential().get_token(...)` first, falls back to `AzureKeyCredential(api_key)` if the Entra probe fails, raises `RuntimeError` if neither works. One credential is resolved per connection and reused across whichever mode (agent/model) is ultimately used, closed in a `finally` block only if it's the Entra variant.
- Both the agent-mode and model-mode `connect()` calls now pass `api_version=_get_settings().voice_live_api_version` (D-02) — model mode previously passed no api_version at all.
- Deleted the entire classic-agent connect branch (asst_* handling, `agent_access_token` acquisition, `credential_scopes`) — every agent-mode connection reaching `connect()` is now guaranteed hosted, because `_load_connection_config` only sets `use_agent_mode=True` after the D-05/D-08 gate passes.

**Task 3 (test suite):**
- `backend/tests/test_voice_live_websocket.py`: renamed fixtures/inline profiles that used incidental `asst_*` ids for non-agent-mode tests to hosted (`hosted-*`) ids so they clear the new D-08 gate; rewrote the two tests whose entire premise was "unsynced HCP falls back to Model mode" (`test_hcp_profile_not_synced_rejects_connection`, `test_hcp_not_synced_rejects_and_never_calls_connect`) to assert `AgentSyncRequiredError`/`AGENT_SYNC_REQUIRED` instead; added two new D-05 resync tests (`test_load_config_resyncs_classic_agent_before_connect`, `test_load_config_resync_failure_rejects`); replaced the single old credential test with two D-01 tests proving both the Entra-preferred and API-key-fallback paths; updated model-mode `api_version` assertions to `"2026-07-15"` (previously asserted absence).
- `backend/tests/test_voice_live_session_context.py`: simplified the fake settings object in `test_force_model_mode_keeps_model_endpoint_and_avatar_permission` to drop the now-deleted hosted-agent settings fields.
- Added `_link_vl_instance()` test helper and linked every `HcpProfile(...)` fixture that reaches `resolve_voice_config()` to a `VoiceLiveInstance` — an in-scope workaround for an out-of-scope production bug discovered mid-execution (see Deviations).

## Verification

- `pytest tests/test_voice_live_websocket.py -k "AgentSyncRequiredError or resync" -x -q` → 2 passed
- `pytest tests/test_voice_live_websocket.py -k "credential or agent_mode or model_mode" -x -q` → 29 passed
- `pytest tests/test_voice_live_websocket.py tests/test_voice_live_session_context.py -q` → **112 passed**
- `ruff check` + `ruff format --check` on all 4 scoped files → clean
- Acceptance-criteria greps (all pass): `voice_live_hosted_agent` count 0 in both `config.py` and `voice_live_websocket.py`; `class AgentSyncRequiredError` exactly 1 match; `_apply_voice_agent_patch|_VOICE_AGENT_PATCHED` count 0; `_hosted_agent_name|_hosted_agent_project|_hosted_agent_endpoint` count 0; `2025-05-01-preview|2026-01-01-preview` count 0; `agent_access_token|credential_scopes` count 0; `_resolve_voice_live_credential(cfg["api_key"])` exactly 1; `api_version=_api_version` count 2; `agent_id="asst_` in test file exactly 2 (the two dedicated D-05 resync tests); `AGENT_SYNC_REQUIRED` count 2 in test file; `"2026-07-15"` count 3 in test file.
- Full backend suite regression check (`pytest -x -q --deselect tests/test_agent_sync_service.py`): `99 failed, 2426 passed, 15 skipped, 127 deselected` — all 99 failures confirmed outside this plan's 4-file scope, pre-existing fallout from Plan 29-05's column drop (see Deviations and `deferred-items.md`), none caused by this plan's changes.

## Deviations from Plan

### Auto-fixed Issues

None — all edits matched the plan's specified actions exactly (mechanical fixture renames, behavior-reversal rewrites, new test additions, and the two production-code steps), with one in-scope test-only accommodation documented below.

### Out-of-scope discovery (documented, not fixed — see `deferred-items.md`)

**1. `resolve_voice_config()` no-VL-instance fallback crashes (owned by Plan 29-06)**

- **Found during:** Task 3 test execution.
- **Issue:** `voice_live_instance_service.py::resolve_voice_config()`'s fallback branch (for `HcpProfile`s without a linked `VoiceLiveInstance`) still reads 14 deprecated inline voice/avatar columns that Plan 29-05 (commit `333e011`) dropped from `HcpProfile`, causing `AttributeError` on every unlinked-profile call path. Confirmed via direct reading of `29-05-PLAN.md` (line 91, explicit scope reservation) and `29-06-PLAN.md` (D-12, wave 3, `depends_on: [1, 5]`, not yet executed) that this fix is NOT this plan's responsibility.
- **Fix (in-scope, test-only):** Added `_link_vl_instance()` helper in `test_voice_live_websocket.py`; every `HcpProfile(...)` fixture that reaches `resolve_voice_config()` now links a minimal `VoiceLiveInstance`, routing through the working (non-crashing) branch instead. This does not touch `voice_live_instance_service.py` and remains valid after Plan 29-06 lands.
- **Files modified:** `backend/tests/test_voice_live_websocket.py` only.
- **Commit:** `f054ff1`

**2. Full-suite regression: 99 pre-existing failures across 11 files outside scope**

- **Found during:** post-Task-3 full backend suite verification (`pytest -x -q --deselect tests/test_agent_sync_service.py`).
- **Issue:** Same root cause as Item 1 — Plan 29-05's column drop breaks fixtures in files not owned by this plan (`test_api_direct.py`, `test_avatar_data_consistency.py`, `test_conference_api.py`, `test_conference_service.py`, `test_coverage_boost_2.py`, `test_hcp_profile_service.py`, `test_schemas_phase2.py`, `test_voice_live_instance_service.py`, `test_voice_live_model.py`, `test_voice_live_per_hcp.py`, `test_voice_live_service.py`) and `resolve_voice_config()`'s fallback branch fix (Plan 29-06, D-12, not yet run).
- **Action:** Documented in `deferred-items.md` Item 2 for whoever executes Plan 29-06 and any follow-up fixture-repair pass. No files modified.

## Threat Flags

None — both threats this plan mitigates (T-29-01, T-29-02) were already identified in the plan's own threat model and are covered by the verification above (resync failure-path guarantee from Plan 29-02; `AgentSyncRequiredError`-before-`Exception` ordering proven by dedicated rejection tests asserting `connect()` is never called).

## Known Stubs

None.

## Self-Check: PASSED

- `backend/app/config.py` — FOUND
- `backend/app/services/voice_live_websocket.py` — FOUND
- `backend/tests/test_voice_live_websocket.py` — FOUND
- `backend/tests/test_voice_live_session_context.py` — FOUND
- `.planning/phases/29-voice-live-api-refactor-adaptation-azure-ai-voicelive-sdk-1-/deferred-items.md` — FOUND
- Commit `a631198` — FOUND
- Commit `f054ff1` — FOUND
