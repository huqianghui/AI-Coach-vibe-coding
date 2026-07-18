---
phase: 28-sop-skill-ai-foundary-skill-hcp
plan: 03
subsystem: api
tags: [fastapi, pydantic, react, tanstack-query, i18n, react-i18next, azure-ai-foundry]

# Dependency graph
requires:
  - phase: 28-sop-skill-ai-foundary-skill-hcp (Plan 28-01)
    provides: skill_foundry_service (sync_skill_to_foundry, get_skill_portal_url, delete_skill_from_foundry) and foundry_* columns on the Skill model
provides:
  - foundry_skill_name/foundry_sync_status/foundry_cloud_version/foundry_sync_error fields on SkillListOut/SkillOut (list + detail API responses)
  - POST /skills/{id}/foundry-sync admin-gated manual retry route, restricted to published skills (MEDIUM-5 fix)
  - GET /skills/{id}/foundry-portal-url admin-gated portal deep-link route with generic fallback
  - SkillFoundryStatusSection frontend component fully sourced from i18n (MEDIUM-8 fix)
  - useRetryFoundrySync TanStack Query mutation hook
  - foundry.* i18n keys in en-US/zh-CN skill.json
  - Foundry sync status/retry/portal-link UI wired into the Skill editor Settings tab
affects: [skill-lifecycle, admin-ui, hcp-agent-sync-parity]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Admin-gated manual retry route restricted to a single lifecycle status (published) rather than a status blocklist, to avoid resurrecting cloud entities deleted by other lifecycle transitions (MEDIUM-5)"
    - "New UI components fully sourced from i18n via useTranslation(namespace) from day one, even when mirroring a pre-existing component with hardcoded-English debt (MEDIUM-8)"

key-files:
  created:
    - backend/tests/test_skills_api_foundry.py
    - frontend/src/components/admin/skill-foundry-status-section.tsx
  modified:
    - backend/app/schemas/skill.py
    - backend/app/api/skills.py
    - backend/tests/test_skill_api_unit.py
    - frontend/src/types/skill.ts
    - frontend/src/api/skills.ts
    - frontend/src/hooks/use-skills.ts
    - frontend/public/locales/en-US/skill.json
    - frontend/public/locales/zh-CN/skill.json
    - frontend/src/pages/admin/skill-editor.tsx

key-decisions:
  - "bad_request() in this codebase raises ValidationException -> HTTP 422, not literal 400; tests assert 422 for retry-sync rejections, matching the project-wide convention (test_skill_service.py) rather than the plan's informal '400' wording"
  - "Retry-sync guard uses 'skill.status != \"published\"' (not a blocklist of ('published','archived')) per MEDIUM-5 cross-AI review fix, so archived skills (whose Foundry entity was already deleted by the archive lifecycle hook) can never be retried"
  - "SkillFoundryStatusSection sources 100% of its labels from useTranslation('skill') foundry.* keys, deliberately not replicating AgentStatusSection's pre-existing hardcoded-English debt (MEDIUM-8)"
  - "Foundry status section rendered in the Skill editor's Settings tab (skill has no dedicated agent/status sidebar column unlike the HCP profile editor's 3-column layout), guarded by the same !isNew && skill pattern already used elsewhere in this file"

patterns-established:
  - "useRetryFoundrySync invalidates skillKeys.detail(id) + skillKeys.lists() (not skillKeys.all) to match this file's granular invalidation convention for single-resource mutations"

requirements-completed: [D-06, D-07]

# Metrics
duration: ~40min (across a compacted session; wall-clock from first commit to last is 6min for Tasks 2-3, plus prior Task 1 backend work)
completed: 2026-07-18
---

# Phase 28 Plan 03: Skill Foundry Sync API + Admin UI Summary

**Foundry sync fields on Skill list/detail responses, admin-gated published-only retry-sync + portal-url routes, and a fully i18n'd SkillFoundryStatusSection wired into the Skill editor, closing MEDIUM-5 and MEDIUM-8 cross-AI review findings.**

## Performance

- **Duration:** ~40 min total (backend Task 1, then frontend Tasks 2-3 completed within 6 minutes wall-clock per commit timestamps 18:28-18:34)
- **Completed:** 2026-07-18
- **Tasks:** 3/3 completed
- **Files modified:** 11 (2 created, 9 modified)

## Accomplishments
- `GET /skills` and `GET /skills/{id}` now expose `foundry_skill_name`, `foundry_sync_status`, `foundry_cloud_version`, `foundry_sync_error` on every list/detail item
- `POST /skills/{id}/foundry-sync` lets an admin manually retry a failed/pending Foundry sync without re-publishing, restricted to `published` skills only (MEDIUM-5 regression guard verified by an explicit archived-skill test)
- `GET /skills/{id}/foundry-portal-url` returns a deep link (or generic `https://ai.azure.com` fallback for never-synced skills) without ever 4xx-ing
- New `SkillFoundryStatusSection` frontend component mirrors the existing HCP `AgentStatusSection` UX pattern (status badge, error box, retry button, portal link) but sources every string from `en-US`/`zh-CN` locale files (MEDIUM-8)
- Wired into the Skill editor's Settings tab with a toast-driven retry handler, fully i18n'd (`foundry.retrySuccess`/`foundry.retryError`)

## Task Commits

Each task was committed atomically (`--no-verify`, per parallel-worktree execution convention):

1. **Task 1: Backend — Foundry fields on schemas + retry-sync/portal-url routes** - `5af55d4` (feat, TDD)
2. **Task 2: Frontend — types, API client, hook, i18n'd status section component** - `ec7eb4c` (feat, TDD)
3. **Task 3: Wire SkillFoundryStatusSection into the Skill editor page** - `b6a1495` (feat)

_Note: Task 1 and Task 2 were `tdd="true"` — tests were written and verified passing (168/168 backend, `tsc -b` clean) as part of each task's single commit for this parallel-execution context; test file creation and implementation were validated together before committing._

## Files Created/Modified
- `backend/app/schemas/skill.py` - Added 4 `foundry_*` fields to `SkillListOut` (inherited by `SkillOut`); added `SkillFoundryPortalUrlResponse` schema
- `backend/app/api/skills.py` - Added `POST /{skill_id}/foundry-sync` (published-only guard) and `GET /{skill_id}/foundry-portal-url` routes, both `require_role("admin")`-gated
- `backend/tests/test_skills_api_foundry.py` - 9 new tests covering field exposure, retry-sync (published success, draft/archived 422 rejection, non-admin 403), portal-url (synced deep-link, unsynced graceful fallback, non-admin 403)
- `backend/tests/test_skill_api_unit.py` - Fixed 2 pre-existing tests broken by the new required schema fields (Rule 1 auto-fix)
- `frontend/src/types/skill.ts` - Added 4 `foundry_*` fields to `SkillListItem`; added `SkillFoundryPortalUrlResponse` interface
- `frontend/src/api/skills.ts` - Added `retryFoundrySync()` and `getSkillFoundryPortalUrl()` client functions
- `frontend/src/hooks/use-skills.ts` - Added `useRetryFoundrySync()` mutation (invalidates `skillKeys.detail(id)` + `skillKeys.lists()`)
- `frontend/src/components/admin/skill-foundry-status-section.tsx` - New component, fully i18n'd via `useTranslation("skill")`, archived-skill informational note instead of retry button
- `frontend/public/locales/en-US/skill.json` / `zh-CN/skill.json` - Added `foundry.*` top-level key (14 sub-keys each), validated as valid JSON
- `frontend/src/pages/admin/skill-editor.tsx` - Imported and rendered `SkillFoundryStatusSection` in the Settings tab; added `retryFoundrySyncMutation` + `handleRetryFoundrySync` toast handler

## Decisions Made
- Followed the codebase's actual `bad_request()` → 422 convention over the plan's informal "returns 400" prose (see key-decisions above)
- Placed the new status section in the Settings tab rather than a sidebar column, since the Skill editor uses a tab-based layout (unlike the HCP profile editor's 3-column grid) — this was the most consistent location adjacent to other skill metadata/administrative content
- Chose `skillKeys.detail(id)` + `skillKeys.lists()` invalidation (matching `useRetryConversion`/`useCheckStructure` granularity) over a blanket `skillKeys.all` invalidation, since the plan's suggested `["skills"]` literal did not match this file's established query-key factory convention

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed 2 pre-existing test failures caused by new required schema fields**
- **Found during:** Task 1
- **Issue:** Adding 4 new required `str` fields to `SkillListOut` broke `test_list_published_with_results` and `test_get_skill_returns_skill_out` in `test_skill_api_unit.py` — their `MagicMock()`-based fixtures didn't set the new `foundry_*` attributes, so Pydantic's `model_validate()` rejected the auto-generated `MagicMock` attribute objects as invalid `string_type`
- **Fix:** Added explicit string-valued attribute assignments (`mock_item.foundry_skill_name = ""`, etc.) to both test setups
- **Files modified:** `backend/tests/test_skill_api_unit.py`
- **Verification:** Full backend suite green: `pytest tests/test_skill_api.py tests/test_skill_api_unit.py tests/test_skill_service.py tests/test_skill_foundry_service.py tests/test_skills_api_foundry.py -q` → 168 passed
- **Committed in:** `5af55d4` (Task 1 commit)

**2. [Rule 1 - Convention correction] Test assertions use 422, not the plan's literal "400" wording**
- **Found during:** Task 1
- **Issue:** Plan prose said retry-sync rejection "returns 400"; the codebase's `bad_request()` helper actually raises `ValidationException` → HTTP 422 (confirmed project-wide convention via `test_skill_service.py`)
- **Fix:** Asserted `== 422` in `test_retry_sync_rejected_for_draft_skill` and `test_retry_sync_rejected_for_archived_skill`, with an explanatory code comment
- **Files modified:** `backend/tests/test_skills_api_foundry.py`
- **Verification:** Tests pass; consistent with every other `bad_request()`-guarded route in the codebase
- **Committed in:** `5af55d4` (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (1 bug-fix regression, 1 convention correction — both Rule 1)
**Impact on plan:** Both fixes were necessary for correctness and consistency with established codebase conventions. No scope creep.

## Issues Encountered
- Worktree was initially based on a stale commit (`e43b86c`, an ancestor of the required base `ea70731`) missing all of Plan 28-01's work; resolved with `git reset --hard ea70731370de5a744e0dee565822e7c057165538` before any Plan 28-03 work began. No lasting impact — verified clean state before starting Task 1.

## User Setup Required
None - no external service configuration required. Foundry sync itself (Entra ID auth, Azure AI Foundry endpoint) was already configured in Plan 28-01.

## Next Phase Readiness
- D-06 (manual retry surface) and D-07 (Foundry sync visibility) are fully delivered
- MEDIUM-5 (archived-skill resurrection guard) and MEDIUM-8 (i18n-from-day-1 for new UI) cross-AI review findings are closed
- No blockers for downstream phases; Skill Foundry sync feature (Plans 28-01 through 28-03) is complete pending orchestrator-level Plan 28-02 status (executed in a parallel wave, tracked separately)

---
*Phase: 28-sop-skill-ai-foundary-skill-hcp*
*Completed: 2026-07-18*

## Self-Check: PASSED

All 10 referenced files exist on disk and all 3 task commit hashes (`5af55d4`, `ec7eb4c`, `b6a1495`) are present in `git log`.
