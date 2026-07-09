---
phase: 27-prompt-optimizer-unified-prompt-management
plan: 04
subsystem: api
tags: [prompt-registry, prompt-management, versioning, optimization-runs, rest-api]

# Dependency graph
requires:
  - phase: 27-01
    provides: PromptTemplate/PromptVersion/PromptOptimizationRun models, prompt_registry.get_prompt + seed_prompt_registry
  - phase: 27-02
    provides: /prompts router registered in main.py, stateless POST /prompts/optimize, prompt_optimizer_client
provides:
  - Registry-backed prompt management REST API (list/detail/versions/runs)
  - Versioned edits (PUT creates source=manual version and activates it)
  - Activation/rollback endpoint preserving append-only history
  - POST /prompts/{key}/optimize records a PromptOptimizationRun without changing the active version
  - POST /prompts/{key}/adopt promotes a run result to a new active version linked back to the run
  - is_system delete protection (409); non-system prompts deletable
  - prompt_registry service functions: list_prompt_summaries, get_prompt_detail, list_versions, list_runs, create_version, activate_version, record_optimization_run, adopt_run, delete_template
affects: [27-05, 27-06, admin-prompt-ui]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Single-active-version invariant enforced transactionally: _deactivate_all_versions clears is_active before setting the new active version and template.active_version_id in one commit"
    - "Append-only version history: create_version increments version_no and sets parent_version_id to the previous active version; activation/rollback never deletes"
    - "Optimize-then-record: /optimize resolves current active content, calls the optimizer, and always persists a PromptOptimizationRun (success or error) without mutating the active version"
    - "Adopt links run to version bidirectionally: create_version then run.resulting_version_id = version.id"
    - "Admin-only writes via Depends(require_role('admin')); reads also admin-gated"

key-files:
  created:
    - backend/app/schemas/prompt.py
    - backend/tests/test_prompts_management_api.py
  modified:
    - backend/app/services/prompt_registry.py
    - backend/app/api/prompts.py

key-decisions:
  - "Return plain newest-first lists for versions/runs/summaries rather than PaginatedResponse — the plan's pagination note was a soft suggestion and these lists are small/bounded; keeps the admin UI contract simple"
  - "optimize_prompt returns text only (no model name), so recorded runs use model='prompt-optimizer' as a non-secret provenance marker (threat T-27-13: model name is non-sensitive)"
  - "Management API tests call router coroutines directly with a mocked admin user + the real test db_session (matching test_prompts_optimize_api.py), giving 100% branch coverage that httpx ASGITransport cannot reach"
  - "Every optimize call records a run — on optimizer failure a status='error' run is persisted before the 502 is raised, satisfying the auditability must-have"

patterns-established:
  - "Registry service functions raise NotFoundException/ConflictException (AppException subclasses) so the global handler produces structured error JSON without router-level try/except"

requirements-completed: [PROMPT-03, PROMPT-04, PROMPT-05]

# Metrics
duration: ~40min
completed: 2026-06-10
---

# Phase 27 Plan 04: Prompt Management REST API Summary

**Admins can now list every registered prompt, read its active version, save versioned edits (source=manual), roll back to any prior version without losing history, run the optimizer against the active version (each call recorded as an auditable `PromptOptimizationRun`), and adopt a run's result as a new active version linked back to the run — all through admin-gated `/prompts` endpoints backed by nine new `prompt_registry` service functions that enforce a single-active-version invariant and protect `is_system` prompts from deletion.**

## Performance

- **Duration:** ~40 min
- **Tasks:** 3
- **Files:** 4 (2 created, 2 modified)

## Accomplishments
- Added `schemas/prompt.py` with the full request/response contract: `PromptSummary`, `PromptResponse`, `PromptVersionResponse`, `PromptOptimizationRunResponse`, `PromptUpdateRequest`, `OptimizeRecordRequest`, `OptimizeRunResponse`, `AdoptRunRequest`.
- Extended `prompt_registry` with nine management service functions plus three private helpers (`_get_template_or_404`, `_deactivate_all_versions`, `_active_version`) enforcing the single-active-version invariant and append-only history.
- Wired ten `/prompts` endpoints (four read, five write, plus the pre-existing stateless `/optimize`), all admin-gated, with static `/optimize` kept ahead of the parameterized `/{key}` routes.
- Achieved **100% coverage** of `app.api.prompts`, `app.services.prompt_registry`, and `app.schemas.prompt` (33 tests across the two prompt-API test files; 62 tests green across all prompt-related suites).

## Task Commits

1. **Task 1 + Task 2: Schemas, registry service functions, and endpoints** - `10b3c2c` (feat)
2. **Task 3: Management API tests (100% coverage)** - `4aa6246` (test)

**Plan metadata:** _(this docs commit)_

_Note: Tasks 1 and 2 (read endpoints, then versioning/activation/adopt/optimize-record) were delivered in one feature commit since the schemas and service layer underpin both; the test suite covering all three tasks was committed separately._

## Files Created/Modified
- `backend/app/schemas/prompt.py` *(created)* - Pydantic v2 schemas for the management API; `from_attributes` on ORM-backed response models.
- `backend/app/services/prompt_registry.py` *(modified)* - Added `list_prompt_summaries`, `get_prompt_detail`, `list_versions`, `list_runs`, `create_version`, `activate_version`, `record_optimization_run`, `adopt_run`, `delete_template` + helpers; imports/`__all__` updated.
- `backend/app/api/prompts.py` *(modified)* - Added list/detail/versions/runs reads and PUT/activate/optimize-record/adopt/delete writes; all `Depends(require_role("admin"))`.
- `backend/tests/test_prompts_management_api.py` *(created)* - 26 tests covering read paths + 404s, versioning, rollback, optimize-records-run (success + error), adopt linkage, is_system 409, non-system 204, and registry edge cases.

## Deviations from Plan

### Auto-fixed Issues

None affecting behavior. Minor design choices below (documented, not behavior bugs).

### Design Decisions

**1. [Rule 1 - Simplification] Plain lists instead of PaginatedResponse for versions/runs/summaries**
- **Reason:** The plan noted pagination "where a list can grow" as a soft suggestion. Version and run histories per prompt are small and bounded; returning newest-first plain lists keeps the admin UI contract straightforward and avoids premature envelope complexity. Can be wrapped later without breaking the service layer.

**2. [Rule 2 - Auditability] `model='prompt-optimizer'` provenance marker**
- **Reason:** `optimize_prompt` returns only text (no model identifier). To keep `PromptOptimizationRun.model` meaningful and satisfy the "records model" must-have, recorded runs store the constant `"prompt-optimizer"` as a non-secret provenance marker (threat T-27-13 accepts model name as non-sensitive).

**3. [Rule 2 - Auditability] Failed optimize calls still record a run**
- **Reason:** The must-have "every optimize call records a PromptOptimizationRun" is enforced even on optimizer failure: a `status='error'` run with the error message is persisted before the 502 is raised.

## Threat Coverage
- **T-27-10 (admin auth on writes):** mitigated — all write endpoints (and reads) require `Depends(require_role("admin"))`.
- **T-27-11 (append-only versions):** mitigated — `create_version` never overwrites; activation toggles `is_active` only; history is preserved on rollback.
- **T-27-12 (created_by on version + run):** mitigated — `create_version`, `record_optimization_run`, and `adopt_run` all persist `created_by` from the authenticated admin.
- **T-27-13 (model name non-secret):** accepted — stored as the constant provenance marker `"prompt-optimizer"`.

## Self-Check: PASSED
- `backend/app/schemas/prompt.py` — FOUND
- `backend/tests/test_prompts_management_api.py` — FOUND
- `backend/app/services/prompt_registry.py` — FOUND (modified)
- `backend/app/api/prompts.py` — FOUND (modified)
- Commit `10b3c2c` (feat) — FOUND
- Commit `4aa6246` (test) — FOUND
- Coverage: app.api.prompts 100%, app.services.prompt_registry 100%, app.schemas.prompt 100%
