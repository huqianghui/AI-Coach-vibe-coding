---
phase: 30-unified-training-pinned-foundry-hcp-agent-kb-retrieval
plan: 04
subsystem: voice-live-websocket
tags: [voice-live, websocket, avatar, exact-agent-version]
requires:
  - phase: 30-02
    provides: Session-only pinned-Agent resolver
provides:
  - Owned-session exact Agent identity for Voice Live WebSocket
  - Exact agent_name, agent_version, and project_name SDK connect kwargs
  - Agent-only session branch with avatar as a modality
  - Client identity/prompt override resistance and no session Skill focus transport
affects: [30-05, 30-06]
tech-stack:
  added: []
  patterns: [session identity override after voice-config resolution, agent-only training connection]
key-files:
  created: []
  modified:
    - backend/app/services/voice_live_websocket.py
    - backend/tests/test_voice_live_session_context.py
key-decisions:
  - "Legacy model/agent mode labels are transport choices; identity always comes from the session pin."
  - "HCP/VL configuration contributes voice and avatar settings but cannot contribute training Agent identity."
  - "Session-bound RequestSession carries no focus or temporary instructions."
requirements-completed: [R1]
duration: 13min
completed: 2026-07-26
---

# Phase 30 Plan 04: Pinned Voice Live WebSocket Summary

**Voice and avatar now connect to the exact owned session Agent version with no model fallback or Skill focus transport**

## Accomplishments

- Replaced session model/focus gating with support for all six Unified Training voice/avatar mode labels.
- Resolved Agent name/version exclusively through `resolve_pinned_agent()` after ownership and lifecycle checks.
- Loaded HCP configuration for voice/avatar only, then explicitly overrode connection identity from the session and server-side project configuration.
- Passed exact `agent_name`, `agent_version`, `project_name`, and configured API version to Voice Live `connect()` with no model kwarg.
- Kept avatar on the same Agent connection and ignored browser HCP, prompt, instance, and avatar identity overrides.

## Verification Results

- Session-bound focused suite: **18 passed**.
- Combined WebSocket suites: **18 passed, 95 credential-gated existing tests skipped** because `AZURE_FOUNDRY_ENDPOINT` / API key configuration was absent from the test process.
- Ruff check and format: **passed**.

## Task Commits

None. Plan 30-06 remains the sole commit/push owner.

## Deviations from Plan

None.

## Known Stubs

None.

## Threat Flags

None beyond the declared Voice Live network and browser WebSocket boundaries.

## Next Phase Readiness

The neutral session context now exposes exact pins and HCP configuration identity needed by the future WebRTC broker path.

## Self-Check: PASSED

- Implementation and tests exist.
- Focused exact-pin tests pass.
- No commit, push, staging, or protected-path operation occurred.

---
*Phase: 30-unified-training-pinned-foundry-hcp-agent-kb-retrieval*
*Completed: 2026-07-26*
