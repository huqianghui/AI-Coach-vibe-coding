---
phase: 29-voice-live-api-refactor-adaptation-azure-ai-voicelive-sdk-1-
plan: 02
subsystem: backend
tags: [voice-live, api-version, agent-sync, resync, foundry-agents]

# Dependency graph
requires:
  - "29-01: azure-ai-voicelive pinned to 1.3.0b1; api_version=\"2026-07-15\" must be explicitly passed at every connect() call site"
provides:
  - "settings.voice_live_api_version = \"2026-07-15\" -- single GA api-version source of truth (D-02) for all Voice Live connect() call sites"
  - "agent_sync_service.resync_classic_agent(db, profile) -- tested migration of classic asst_* agent_id to a hosted (name-based) agent (D-05)"
  - "Failure-path guarantee: a profile can never end resync with a blank agent_id it didn't already have (T-29-01 mitigation, precondition for 29-03's classic-branch deletion D-06)"
affects: [29-03, 29-04, 29-06]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "resync_classic_agent temporarily clears profile.agent_id in memory to force sync_agent_for_profile's create_agent (hosted) branch, restoring the original id on failure"
    - "Read settings.voice_live_api_version instead of hardcoding any api-version literal (D-02)"

key-files:
  created: []
  modified:
    - backend/app/config.py
    - backend/app/services/agent_sync_service.py
    - backend/tests/test_agent_sync_service.py

key-decisions:
  - "Purely additive plan: classic connect branch NOT deleted here (29-03 owns D-06); no voice_live_hosted_* settings touched (29-03 owns D-07)"
  - "resync failure returns False and records agent_sync_status=failed instead of raising -- callers (29-03/29-04 gates) treat False as 'not synced' and reject per D-08"

patterns-established: []

# Metrics
duration: ~10min (executor interrupted by provider 403 mid-run; Task 2 work verified green and committed by orchestrator)
completed: 2026-07-19
---

# Phase 29 Plan 02: GA api-version setting + resync_classic_agent

## What was done

**Task 1 (commit 5a769d8):** Added `voice_live_api_version: str = "2026-07-15"` to `backend/app/config.py` directly below `voice_live_default_model`, with the D-02 comment forbidding any other api-version literal in the codebase. No other voice_live settings modified.

**Task 2 (commit 4e2c341, TDD):** Implemented `resync_classic_agent(db, profile)` in `backend/app/services/agent_sync_service.py` (placed after `sync_agent_for_profile`) plus 4 tests in `backend/tests/test_agent_sync_service.py` under `# --- D-05: resync_classic_agent ---`:
- success: `asst_legacy_123` → hosted id, `agent_sync_status="synced"`, returns True
- failure/no-orphan: RuntimeError from sync → original `asst_*` id restored, `status="failed"`, error recorded, returns False
- no-op guards: empty `agent_id` and already-hosted id both return False without calling `sync_agent_for_profile`

## Verification

- `pytest tests/test_agent_sync_service.py -k resync_classic_agent -x` → 4 passed
- `pytest tests/test_agent_sync_service.py` (full file) → **100 passed, 0 failed** (no regression)
- `python -c "from app.config import get_settings; ..."` → prints `2026-07-15`

## Deviations

- Executor agent was interrupted by a transient provider 403 after completing Task 2's code; orchestrator verified tests green and created the Task 2 commit + this SUMMARY directly. No scope deviation.
