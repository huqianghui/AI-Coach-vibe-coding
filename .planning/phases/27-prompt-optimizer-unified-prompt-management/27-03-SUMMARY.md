---
phase: 27-prompt-optimizer-unified-prompt-management
plan: 03
subsystem: api
tags: [prompt-registry, prompt-builder, scoring, conference, refactor, snapshot-tests]

# Dependency graph
requires:
  - phase: 27-01
    provides: prompt_registry.get_prompt resolver, PROMPT_DEFAULTS catalog, seeded registry (9 keys)
provides:
  - All template-based prompt builders resolve their base template from the registry via get_prompt(key)
  - hcp.system / key_message.detection routed through registry with byte-identical default output
  - scoring.base resolved from registry (per-entity rubric prompt_template still wins)
  - conference.audience resolved from registry; skill.sop_extraction / skill.ai_feedback / dry_run.sop_eval routed too
  - render_double_brace_template safe renderer for admin overrides
  - Snapshot regression + override test suite proving zero behavior drift
affects: [27-04, 27-05, 27-06, prompt-management-api, admin-prompt-ui]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dual-path builder: imperative default path stays byte-identical; registry override hook renders admin template with a flat value dict only when the active version differs from the seeded default"
    - "Lazy function-level import of prompt_registry.get_prompt inside builders to avoid the prompt_defaults circular import"
    - "Graceful registry fallback (try/except) in score_with_llm so mocked/unseeded DBs use the built-in default"

key-files:
  created:
    - backend/tests/test_prompt_builder_registry.py
  modified:
    - backend/app/services/prompt_builder.py
    - backend/app/services/scoring_engine.py
    - backend/app/services/skill_conversion_service.py
    - backend/app/services/dry_run_engine.py
    - backend/app/services/conference_prompt_config.py
    - backend/app/services/conference_service.py
    - backend/app/api/sessions.py
    - backend/tests/test_prompt_builder.py

key-decisions:
  - "Option A dual-path design: keep the imperative HCP/key-message builders producing byte-identical output on the default path, and only render the admin template (via a flat value dict) when the active registry version differs from the seeded default"
  - "Kept build_conference_audience_prompt synchronous and threaded a registry-resolved base_template from the async callers, avoiding async churn across 11 conference tests"
  - "score_with_llm resolves scoring.base with a graceful fallback so unseeded/mocked DBs still work"

patterns-established:
  - "Registry override hook: builder computes legacy output, compares resolved template to PROMPT_DEFAULTS[key]['content'], and only diverges when an admin override is active"
  - "Safe placeholder rendering via render_double_brace_template / render_prompt_template (missing or extra tokens never crash, no eval)"

requirements-completed: [PROMPT-02]

# Metrics
duration: ~55min
completed: 2026-06-10
---

# Phase 27 Plan 03: Route Prompt Builders Through the Registry Summary

**Every template-based prompt builder (HCP system, key-message detection, scoring base, conference audience, skill extraction/feedback, dry-run SOP eval) now sources its base template from the prompt registry via `get_prompt(key)`, with snapshot regression proving byte-identical output when the seeded defaults are active and override tests proving admin edits take effect.**

## Performance

- **Duration:** ~55 min
- **Tasks:** 3
- **Files modified:** 8 (1 created, 7 modified)

## Accomplishments
- Migrated all template-based builders from hardcoded strings to registry-resolved templates without any behavior drift on the default path.
- Added a safe admin-override rendering path (`render_double_brace_template`) that substitutes only known placeholders and never crashes on missing/extra tokens.
- Added `test_prompt_builder_registry.py` (8 tests): 4 snapshot-regression tests (byte-identical defaults for hcp.system, key_message.detection, scoring.base, conference.audience) and 4 override tests (admin versions change output; per-entity rubric prompt_template still wins over the registry base).
- Full backend suite green relative to baseline: 2282 passed (up from 2259), same 9 pre-existing/environmental failures, no new regressions.

## Task Commits

Each task was committed atomically:

1. **Task 2: Route builders through get_prompt** - `2942200` (feat)
2. **Task 1 + Task 3: Snapshot regression & override tests** - `ac965ed` (test)

**Plan metadata:** _(this docs commit)_

_Note: Task 1 (snapshot baselines) and Task 3 (override tests) were delivered in a single `test_prompt_builder_registry.py` file; the migration (Task 2) was committed separately before the test file so the snapshots assert against the migrated builders._

## Files Created/Modified
- `backend/app/services/prompt_builder.py` - `build_hcp_system_prompt` and `build_key_message_detection_prompt` are now async and resolve `hcp.system` / `key_message.detection` from the registry (byte-identical default path, admin override via `render_double_brace_template` + `_hcp_prompt_values`); `build_conference_audience_prompt` accepts a `base_template` arg used when no per-entity override is set.
- `backend/app/services/scoring_engine.py` - `build_scoring_prompt` accepts `base_template`; `score_with_llm` resolves `scoring.base` via `get_prompt` with a graceful fallback to the built-in default.
- `backend/app/services/skill_conversion_service.py` - `_call_sop_extraction` and `regenerate_sop_with_feedback` resolve `skill.sop_extraction` / `skill.ai_feedback` from the registry.
- `backend/app/services/dry_run_engine.py` - `_evaluate_sop_coverage_with_agent` takes a `prompt_template` arg; caller resolves `dry_run.sop_eval` from the registry.
- `backend/app/services/conference_prompt_config.py` - added `render_double_brace_template` for safe `{{token}}` substitution.
- `backend/app/services/conference_service.py` - 3 callers resolve `conference.audience` via `get_prompt` and pass it as `base_template`.
- `backend/app/api/sessions.py` - updated the single `build_hcp_system_prompt` caller to `await ... db=db`.
- `backend/tests/test_prompt_builder.py` - added `await` to existing HCP/key-message builder calls (now async).
- `backend/tests/test_prompt_builder_registry.py` - new snapshot regression + admin override test suite.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Async signature change rippled to non-plan callers**
- **Found during:** Task 2
- **Issue:** Making `build_hcp_system_prompt` / `build_key_message_detection_prompt` async (required to `await get_prompt`) broke their existing callers and tests.
- **Fix:** Updated the sole app caller `backend/app/api/sessions.py` and the existing `backend/tests/test_prompt_builder.py` calls to `await`. These files are outside the plan's `files_modified` list but the change is mechanical and required for the migration to compile.
- **Commit:** `2942200`

**2. [Rule 1 - Bug] Kept conference builder sync to avoid regressing 11 conference tests**
- **Found during:** Task 2
- **Issue:** Initially made `build_conference_audience_prompt` async, which broke 11 sync tests in `test_prompt_builder_conference.py` and required async churn.
- **Fix:** Reverted to a synchronous builder that accepts an optional `base_template`; the 3 async callers in `conference_service.py` resolve `conference.audience` via `get_prompt` and pass it in. Existing conference tests (which pass no `base_template`) stay byte-identical and unmodified.
- **Files modified:** `prompt_builder.py`, `conference_service.py`
- **Commit:** `2942200`

**3. [Rule 2 - Missing critical functionality] Graceful registry fallback in `score_with_llm`**
- **Found during:** Task 2 (regression gate)
- **Issue:** `test_scoring_engine_postvalidation` mocks `db` as `AsyncMock`; the new `get_prompt(db, "scoring.base")` call failed against the mock.
- **Fix:** Wrapped the lookup in `try/except` so an unseeded or mocked DB falls back to the built-in `SCORING_PROMPT_TEMPLATE`. This is also safer in production (registry lookup failure never breaks scoring).
- **Commit:** `2942200`

### Design Decision (Option A, user-approved)

The plan assumed all builders were template-driven, but `hcp.system` and `key_message.detection` were imperative (string-concatenated). Rather than rewrite them, the default path keeps the imperative build (byte-identical), and the registry override hook renders the admin template with a flat value dict **only** when the active version differs from the seeded default. This satisfies both must-have truths (byte-identical default output AND admin-set versions change output) with zero drift risk.

### Note on `scoring.rubric`

The plan references a `scoring.rubric` key; the per-entity override behavior is carried by `build_scoring_prompt(prompt_template=...)`, which still takes precedence over the registry `scoring.base`. This is covered by `test_scoring_per_entity_override_wins_over_registry_base`.

## Threat Model Coverage
- **T-27-08 (Tampering — placeholder rendering):** Mitigated. Admin templates are rendered via `render_double_brace_template` / `render_prompt_template`, which substitute only known tokens and ignore missing/extra tokens (no `eval`, no crash). Verified by `test_hcp_system_override_changes_output` (asserts unresolved `{{name}}` never leaks and unknown tokens don't raise).
- **T-27-09 (Repudiation — behavior change):** Mitigated. Snapshot regression tests assert byte-identical output for all four migrated builders when the seeded default is active.

## Verification
- `ruff check .` — passed.
- `ruff format --check .` — passed (315 files formatted).
- `pytest tests/test_prompt_builder_registry.py -q` — 8 passed.
- `pytest -q` (full suite) — 2282 passed, 149 skipped, 27 deselected, 9 failed (all 9 pre-existing/environmental, documented in `deferred-items.md`: Azure ConnectionTester no-key + python-docx extraction + skill status; none touch the prompt registry).

## Self-Check: PASSED
- FOUND: backend/tests/test_prompt_builder_registry.py
- FOUND commit: 2942200 (feat: route builders through registry)
- FOUND commit: ac965ed (test: registry snapshot + override tests)
