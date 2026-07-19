---
phase: 29-voice-live-api-refactor-adaptation-azure-ai-voicelive-sdk-1-
plan: 04
subsystem: backend
tags: [voice-live, webrtc, agent-sync, api-version, mandatory-agent-mode]

# Dependency graph
requires:
  - phase: "29-01"
    provides: "azure-ai-voicelive pinned to 1.3.0b1; settings.voice_live_api_version=\"2026-07-15\" GA constant"
  - phase: "29-03"
    provides: "AgentSyncRequiredError / except-AppException-before-except-Exception ordering pattern established on the WS side (T-29-02); resync_classic_agent(db, profile) call convention"
provides:
  - "create_webrtc_session_config() reads settings.voice_live_api_version for the WebRTC signaling URL's api-version query param -- WEBRTC_API_VERSION preview literal deleted (D-02)"
  - "D-05: classic (asst_*) HCP agent_ids are auto-resynced to hosted agents via resync_classic_agent() before the per-HCP branch decides agent mode, mirroring the WS-side wiring"
  - "D-08: WebRTC session requests for HCP profiles without a synced hosted agent_id are rejected with 409 AGENT_SYNC_REQUIRED before any signaling URL or bearer token is built -- closes the WebRTC enforcement gap flagged in 29-VALIDATION.md"
  - "except AppException: raise placed before the broad except Exception in the per-HCP try block, so the 409 rejection can never be silently swallowed into a model-mode fallback"
affects: [29-06]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "except AppException: raise before except Exception: (fall back to defaults) -- same ordering hazard fix as WS-side AgentSyncRequiredError in Plan 29-03, now proven on the WebRTC transport too"
    - "resync_classic_agent() called only when profile.agent_id starts with 'asst_'; the D-08 gate re-checks agent_id + agent_sync_status=='synced' unconditionally afterward, so a no-op resync (empty/never-synced agent_id) still gets caught by the gate"

key-files:
  created: []
  modified:
    - backend/app/services/voice_live_webrtc.py
    - backend/tests/test_voice_live_webrtc.py

key-decisions:
  - "Genuine profile-load failures (DB error, profile not found) still fall back to config-level defaults unchanged (Scenario 5) -- only rejects when the profile loads successfully but isn't synced-and-hosted, since AGENT_SYNC_REQUIRED requires having actually evaluated the sync status"
  - "D-07 verification (grep voice_live_hosted_agent in config.py and voice_live_webrtc.py) confirmed 0 matches in both files -- Plan 29-03's deletion already covers this file; no code change needed here"

patterns-established: []

requirements-completed: [D-02, D-05, D-07, D-08]

# Metrics
duration: ~25min
completed: 2026-07-19
---

# Phase 29 Plan 04: WebRTC GA api-version + D-05/D-08 agent-sync gate Summary

Mirrored the WS-side D-02/D-05/D-08 rewiring from Plan 29-03 onto `create_webrtc_session_config()`: deleted the standalone `WEBRTC_API_VERSION` preview literal in favor of `settings.voice_live_api_version`, wired auto-resync of classic (`asst_*`) agents, and closed the previously-unenforced "WebRTC gap" by rejecting unsynced-HCP sessions with 409 `AGENT_SYNC_REQUIRED` before any signaling URL or bearer token is built.

## Performance

- **Duration:** ~25 min
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- WebRTC and WebSocket transports now share one GA api-version source (`settings.voice_live_api_version = "2026-07-15"`)
- D-05: classic `asst_*` HCP agents auto-resync to hosted agents on first WebRTC connection
- D-08: unsynced HCP profiles can no longer start a WebRTC voice session (previously zero enforcement existed here, unlike the WS side)
- Confirmed (verification-only) that D-07 hosted-override settings remain fully deleted with zero references in this file

## Task Commits

1. **Task 1: GA api-version + D-05 resync + D-08 rejection gate in create_webrtc_session_config** - `3be361f` (feat)
2. **Task 2: Update and extend test_voice_live_webrtc.py** - `a624d64` (test)

**Plan metadata:** (this commit)

## Files Created/Modified
- `backend/app/services/voice_live_webrtc.py` - Deleted `WEBRTC_API_VERSION` constant; reads `settings.voice_live_api_version`; per-HCP branch now auto-resyncs classic agents and rejects unsynced profiles with `AppException(409, "AGENT_SYNC_REQUIRED", ...)` before the broad `except Exception` fallback
- `backend/tests/test_voice_live_webrtc.py` - Updated GA api-version assertion; added `_mock_hcp_profile` fixture helper; added `TestWebRTCSessionAgentSyncGate` with `test_unsynced_hcp_rejects_with_409` and `test_classic_agent_auto_resyncs_then_succeeds`

## Decisions Made
- Followed the plan's exact edit steps (A-D) with no structural deviation
- D-07 verification grep confirmed 0 matches for `voice_live_hosted_agent` in both `config.py` and `voice_live_webrtc.py` -- no action needed, Plan 29-03 already owns and completed that deletion

## Deviations from Plan

None -- plan executed exactly as written. One minor mechanical adjustment: `ruff format` reformatted a single `with patch(...)` line in the new test (collapsed a multi-line call onto one line to satisfy the 100-char line-length rule); no behavioral change, re-verified with a full test re-run after formatting.

## Issues Encountered

None specific to this plan's scope. Confirmed pre-existing, out-of-scope failures in `tests/test_agent_sync_service.py::TestRealAgentSyncOperations` (6 failures) during the cross-file regression check specified in Task 2's acceptance criteria -- these are the same root cause already documented in `deferred-items.md` Item 2 (Plan 29-05's column drop on `HcpProfile`, owned by Plan 29-06/D-12), confirmed via `git stash` to pre-exist independent of this plan's changes (identical failures reproduce against the pre-Task-2 tree). `tests/test_voice_live_websocket.py` (95 tests) and `tests/test_voice_live_webrtc.py` (8 tests) both pass cleanly in isolation.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Both Voice Live transports (WS from Plan 29-03, WebRTC from this plan) now share one GA api-version source and enforce the identical "synced hosted agent or reject" contract for HCP profiles
- Plan 29-06 (D-12) remains responsible for fixing `resolve_voice_config()`'s no-VL-instance fallback branch, which is unrelated to this plan's files and unaffected by these changes

---
*Phase: 29-voice-live-api-refactor-adaptation-azure-ai-voicelive-sdk-1-*
*Completed: 2026-07-19*

## Self-Check: PASSED

- `backend/app/services/voice_live_webrtc.py` — FOUND
- `backend/tests/test_voice_live_webrtc.py` — FOUND
- `.planning/phases/29-voice-live-api-refactor-adaptation-azure-ai-voicelive-sdk-1-/29-04-SUMMARY.md` — FOUND
- Commit `3be361f` — FOUND
- Commit `a624d64` — FOUND
