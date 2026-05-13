---
phase: 24-session-skill-focus-cu-evaluation
plan: 03
subsystem: backend-scoring
tags: [cu-evaluation, azure-content-understanding, scoring-pipeline, dual-mode]
dependency_graph:
  requires: ["24-01"]
  provides: ["cu_evaluation_service", "rubric_cu_sync"]
  affects: ["scoring_service", "session_scoring"]
tech_stack:
  added: []
  patterns: ["submit-poll CU pattern", "layered score merge", "graceful degradation"]
key_files:
  created:
    - backend/app/services/cu_evaluation_service.py
  modified:
    - backend/app/services/rubric_service.py
decisions:
  - "CU analyzer IDs use rubric-content-{id[:8]} / rubric-voice-{id[:8]} format"
  - "Mock fallback when CU not configured preserves dev experience"
  - "Voice scoring failure is non-fatal; degrades to content-only"
  - "Default voice dimensions (fluency/tone/pace/pronunciation) used when rubric lacks voice-specific dims"
metrics:
  duration: 4min
  completed: 2026-05-13
  tasks: 2
  files: 2
---

# Phase 24 Plan 03: CU Evaluation Service Summary

Azure Content Understanding-based scoring pipeline replacing LLM scoring, with analyzer CRUD synced from ScoringRubric and layered content/voice score merging.

## Commits

| # | Hash | Message |
|---|------|---------|
| 1 | 91561bb | feat(24-03): create CU evaluation service with analyzer CRUD and scoring pipeline |
| 2 | 3b8d0a8 | feat(24-03): hook CU analyzer sync into rubric_service on create/update |

## Task Completion

| Task | Name | Status | Commit |
|------|------|--------|--------|
| 1 | Create cu_evaluation_service.py | Done | 91561bb |
| 2 | Hook CU analyzer sync into rubric_service | Done | 3b8d0a8 |

## Implementation Details

### cu_evaluation_service.py (new, ~450 lines)

Provides the full CU-based scoring pipeline:

1. **build_content_analyzer_schema()** - Converts rubric dimensions to CU fieldSchema with per-dimension score/strengths/weaknesses/suggestions objects
2. **build_voice_analyzer_schema()** - Voice-specific schema with fluency/tone/pace/pronunciation dimensions + transcript field
3. **sync_rubric_analyzers()** - PUT CU custom analyzers on rubric save (D-09), stores analyzer IDs back
4. **score_content_with_cu()** - Submit base64-encoded transcript JSON, poll until Succeeded (D-15)
5. **score_voice_with_cu()** - Submit audio URL or base64, poll for voice scoring results (D-14)
6. **merge_scores()** - Layered merge with content_weight/voice_weight (D-11); text-only = 100% content (D-13)
7. **score_session_with_cu()** - Top-level orchestration: load session, determine mode, score, merge

### rubric_service.py (modified)

- Added `from app.services.cu_evaluation_service import sync_rubric_analyzers`
- Called `await sync_rubric_analyzers(db, rubric)` after both `create_rubric` and `update_rubric` flush
- Non-blocking try/except: CU sync failure does not prevent rubric save

## Decisions Made

1. **Analyzer ID format**: `rubric-content-{rubric.id[:8]}` and `rubric-voice-{rubric.id[:8]}` for unique but readable IDs
2. **Mock fallback**: Returns reasonable mock scores (75 overall) when CU endpoint not configured
3. **Voice scoring non-fatal**: If voice scoring fails, session gets content-only scoring rather than failing entirely
4. **Default voice dimensions**: fluency(30%)/tone(25%)/pace(25%)/pronunciation(20%) when rubric lacks voice-specific dimensions
5. **Object type annotation**: Used `object` type for scenario param in _get_session_rubric to avoid circular import

## Deviations from Plan

None - plan executed exactly as written.

## Verification Results

- All 7 functions import correctly
- build_content_analyzer_schema produces correct fieldSchema structure
- merge_scores text-only (D-13): voice_scores=None returns content_total as overall_score
- merge_scores dual-mode (D-11): 80*0.6 + 70*0.4 = 76.0 verified
- ruff check passes on both files
- Both services import together without circular dependency

## Self-Check: PASSED
