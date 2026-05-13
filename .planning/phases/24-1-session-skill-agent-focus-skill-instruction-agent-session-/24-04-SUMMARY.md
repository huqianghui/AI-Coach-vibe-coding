---
phase: 24-session-skill-focus-cu-evaluation
plan: 04
subsystem: backend-services
tags: [session-lifecycle, scoring, cu-evaluation, skill-focus, sop-progress]
dependency_graph:
  requires: [24-01, 24-02]
  provides: [session-focus-runtime, cu-scoring-integration]
  affects: [session_service, scoring_service, voice_scoring_service, sessions-api]
tech_stack:
  added: [cu_evaluation_service]
  patterns: [cu-first-scoring-fallback-chain, sop-progress-per-message, focus-instruction-injection]
key_files:
  created:
    - backend/app/services/cu_evaluation_service.py
  modified:
    - backend/app/services/session_service.py
    - backend/app/api/sessions.py
    - backend/app/services/scoring_service.py
    - backend/app/services/voice_scoring_service.py
    - backend/app/services/scoring_engine.py
decisions:
  - "CU-first scoring fallback chain: CU -> LLM -> mock (graceful degradation)"
  - "cu_evaluation_service returns None when CU not configured (triggers fallback)"
  - "scoring_engine.py kept as deprecated LLM fallback, not deleted"
  - "Focus instruction prepended to scenario_context in text-mode SSE"
  - "Heuristic SOP step increment (1 per 3 messages) when LLM unavailable"
metrics:
  duration: 5min
  completed: "2026-05-13T13:29:03Z"
  tasks_completed: 2
  tasks_total: 2
  files_changed: 6
---

# Phase 24 Plan 04: Service Integration — Focus Runtime + CU Scoring Summary

Wired SkillFocusService into session lifecycle and replaced scoring_engine with CU evaluation as primary scoring path with LLM and mock fallbacks.

## One-liner

Session creation snapshots Skill SOP focus_instruction, per-message SOP progress detection via LLM, scoring uses CU-first fallback chain (CU -> LLM -> mock).

## Tasks Completed

| Task | Name | Commit | Key Changes |
|------|------|--------|-------------|
| 1 | Wire focus_instruction into session creation and message flow | cfa86da | session_service: focus snapshot + update_sop_progress(); sessions.py: SSE focus injection |
| 2 | Replace scoring_engine with CU evaluation in scoring_service | 5bef141 | scoring_service: CU-first chain; voice_scoring_service: CU delegation; cu_evaluation_service created |

## Implementation Details

### Task 1: Focus Instruction Wiring

- `create_session()` now loads Skill content via `load_skill_for_scenario()`, extracts SOP steps, and composes `focus_instruction` which is stored on the session (D-03 snapshot)
- New `update_sop_progress()` function: called on each user message, uses `detect_sop_step()` (LLM-based) or heuristic fallback to track conversation progress through SOP
- SSE chat handler in `sessions.py` calls `update_sop_progress()` before building the CoachRequest, prepends returned focus_instruction to scenario_context for text-mode sessions
- Agent-mode integration point documented via comment (additional_instructions parameter)

### Task 2: CU Evaluation Integration

- Created `cu_evaluation_service.py` with `score_session_with_cu()` interface — returns None when CU not configured (graceful fallback)
- `scoring_service.score_session()` now tries CU first, falls back to LLM `score_with_llm()`, then mock `_generate_mock_scores()`
- `voice_scoring_service.trigger_voice_scoring()` tries CU for voice dimensions first, falls back to mock backend
- `scoring_engine.py` marked DEPRECATED with comments explaining it's kept as LLM fallback

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Created cu_evaluation_service.py stub**
- **Found during:** Task 2
- **Issue:** Plan 03 (parallel wave 2) creates cu_evaluation_service.py, but it doesn't exist in this worktree yet
- **Fix:** Created the service with the expected `score_session_with_cu()` interface that returns None (triggering fallback), matching the contract defined in the plan's interfaces section
- **Files created:** backend/app/services/cu_evaluation_service.py
- **Commit:** 5bef141

**2. [Rule 1 - Bug] Removed unused json import in cu_evaluation_service.py**
- **Found during:** Task 2 verification (ruff check)
- **Issue:** Initial cu_evaluation_service.py had unused `import json`
- **Fix:** Removed the unused import
- **Files modified:** backend/app/services/cu_evaluation_service.py
- **Commit:** 5bef141

## Verification Results

- `ruff check` passes on all 4 modified service files + sessions.py
- `from app.services.session_service import create_session, update_sop_progress` imports cleanly
- `from app.services.scoring_service import score_session` imports cleanly
- `from app.services.cu_evaluation_service import score_session_with_cu` imports cleanly
- scoring_service.py no longer uses score_with_llm as primary path (CU is checked first)

## Known Stubs

| File | Line | Description | Resolution |
|------|------|-------------|------------|
| backend/app/services/cu_evaluation_service.py | 89 | `_call_cu_api()` returns None (CU API integration pending) | Plan 03 or future CU SDK integration will implement actual API call |

## Self-Check: PASSED
