---
phase: 28-sop-skill-ai-foundary-skill-hcp
verified: 2026-07-18T11:24:32Z
status: passed
score: 18/18 must-haves verified
overrides_applied: 0
human_verification:
  - test: "D-03 version-increment smoke test against a real, non-mocked Azure AI Foundry project"
    expected: "Calling sync_skill_to_foundry twice in a row for the same skill (same foundry_skill_name) causes Foundry's create_from_files to return an incremented result.version (e.g. '1' -> '2'), which is then persisted to skill.foundry_cloud_version"
    result: "PASSED 2026-07-18 — live smoke test against the project's real Foundry endpoint (az login Entra credentials). Skill a7c5e171 (zanubrutinib-training): sync #1 → version=1, sync #2 → version=2, same entity name zanubrutinib-training-a7c5e171, no duplicate, no error. See 28-HUMAN-UAT.md."
---

# Phase 28: SOP Skill -> Azure AI Foundry Registration + HCP Training Mount Verification Report

**Phase Goal:** Register upload-material-derived SOP Skills (Phase 19 output) as first-class Azure AI Foundry entities on publish, and mount them into the HCP agent's toolbox at training-session time so the agent can consume skill content in dialog with the trainee -- across both text chat and Voice Live, with non-blocking failure degradation at every step.
**Verified:** 2026-07-18T11:24:32Z
**Status:** passed (D-03 confirmed by live smoke test 2026-07-18 — see 28-HUMAN-UAT.md)
**Re-verification:** No -- initial verification

## Goal Achievement

ROADMAP.md contains no explicit `Success Criteria` block for Phase 28 (unlike Phase 27's block immediately above it) -- must-haves were derived from the merged `must_haves` frontmatter of all 4 plans (28-01 through 28-04), per the verification process's Option C fallback within Step 2.

### Observable Truths

| # | Truth | Requirement | Status | Evidence |
|---|-------|-------------|--------|----------|
| 1 | Publishing a skill triggers a Foundry sync via Entra ID credentials, storing cloud skill name/version/status on the Skill row | D-01 | VERIFIED | `skill_service.py:320` calls `skill_foundry_service.sync_skill_to_foundry(db, skill)` inside `publish_skill()`; `skill_foundry_service.py:120-179` implements Entra-ID-only client + `create_from_files` call, sets `foundry_skill_name`/`foundry_cloud_version`/`foundry_sync_status`. 72/72 targeted tests pass. |
| 2 | Foundry sync failure never blocks or rolls back the local skill publish | D-06 | VERIFIED | `sync_skill_to_foundry` wraps the network call in try/except/finally, never re-raises (code inspection lines 120-179); test suite includes a mocked-raise test asserting `publish_skill()` still returns a published Skill. |
| 3 | Re-publishing an already-synced skill re-uploads with the SAME `foundry_skill_name`, causing Foundry to return an incremented version | D-03 | VERIFIED (live smoke test) | Call-pattern (same name, two calls) is unit-tested. Server-side version increment confirmed 2026-07-18 against the real Foundry project: skill a7c5e171 sync #1 → version=1, sync #2 → version=2, same entity, no duplicate. See 28-HUMAN-UAT.md. |
| 4 | Archiving or deleting a skill removes its Foundry entity, treating a 404-on-delete as success | D-03 | VERIFIED | `skill_service.py:232` (archive) and `:371` (delete) both call `delete_skill_from_foundry`; `skill_foundry_service.py:181-213` treats `status_code == 404` as success, resets tracking fields in `finally`. |
| 5 | Two distinct local skills whose names sanitize to the same slug never collide on the same Foundry entity (HIGH-2) | D-01 | VERIFIED | `_build_unique_foundry_name(name, skill_id)` (skill_foundry_service.py:54) suffixes `skill.id[:8]`; dedicated regression test asserts different output for colliding names given different `skill_id`s. |
| 6 | Session creation for a Foundry-synced skill attempts a real MCP probe first, falls back to `skills.download()` + frontmatter extraction, never fails session creation | D-04, D-06 | VERIFIED | `skill_consumption_service.py:150` (`_try_mcp_fetch`, honest 405-aware probe), `:208` (`download_and_extract_skill_content`), `:261` (`get_skill_content_for_session` orchestrates mount->MCP->download->local, all wrapped, never raises). |
| 7 | Session creation makes a best-effort, non-blocking attempt to mount the skill into a Foundry Toolbox via `skill_reference` | D-02 | VERIFIED | `mount_skill_toolbox` (skill_consumption_service.py:96) tries typed `ToolboxSkillReference` kwarg then raw-dict fallback, wrapped in outer try/except returning `None` on any failure. |
| 8 | The same `SkillContent` abstraction feeds the existing Phase 24 `focus_instruction` channel, consumed identically by text-mode and Voice Live | D-05 | VERIFIED | `session_service.py:52,97` both call `get_skill_content_for_session` and feed the result into the unchanged `focus_instruction` composition; `voice_live_websocket.py:361-391` reads `session.focus_instruction` unmodified -- confirmed via grep, no Voice-Live-specific code added. |
| 9 | If a skill is not Foundry-synced, or every cloud path fails, local DB-based injection is used transparently | D-06 | VERIFIED | `get_skill_content_for_session` falls through to `load_skill_for_scenario(db, scenario_id)` on any cloud-path miss/exception (code inspection + tests). |
| 10 | Repeated calls within a TTL window reuse cached cloud content instead of re-mounting/re-probing/re-downloading (HIGH-1) | D-02/D-04 | VERIFIED | `_content_cache`/`_CONTENT_CACHE_TTL_SECONDS` (skill_consumption_service.py:53-72) keyed on `(skill.id, foundry_cloud_version)`; end-to-end test proves cloud mocks fire at most once across two `update_sop_progress()` calls. |
| 11 | A scenario with a pinned `skill_version_id` skips the cloud path entirely (MEDIUM-4) | D-04 | VERIFIED | `_scenario_pin_is_stale` (skill_consumption_service.py:80) short-circuits to local content when a pin exists; dedicated test confirms `mount_skill_toolbox`/`download_and_extract_skill_content` are never called. |
| 12 | Skill list/detail API responses expose `foundry_skill_name`/`foundry_sync_status`/`foundry_cloud_version`/`foundry_sync_error` | D-07 | VERIFIED | `schemas/skill.py:85-88` adds the 4 fields to `SkillListOut` (inherited by `SkillOut`). |
| 13 | Admin can manually retry a failed/pending Foundry sync via `POST /skills/{id}/foundry-sync`, restricted to published skills (MEDIUM-5) | D-06 | VERIFIED (backend); UI gap noted | `api/skills.py:556-578` enforces `if skill.status != "published": bad_request(...)`. Backend enforcement is correct and tested (422 for draft/archived). Frontend gating gap: REVIEW.md WR-02 confirms the Retry button in `skill-foundry-status-section.tsx` is only disabled for `archived`, not for `draft`/`review`/`failed` -- an admin can click retry on a non-published skill and get a generic 422 toast. See Anti-Patterns. |
| 14 | Admin can open the skill's Azure Portal page via a discovered deep link or generic fallback | D-07 | VERIFIED | `GET /skills/{id}/foundry-portal-url` (api/skills.py:580) + `get_skill_portal_url` (skill_foundry_service.py:215) always returns a URL, never 4xx. |
| 15 | Skill editor shows a Foundry sync status badge, error detail, retry button, and portal link, fully i18n'd | D-07 | VERIFIED | `skill-foundry-status-section.tsx` contains 12 occurrences of `t("foundry.` and is wired into `skill-editor.tsx:933`; `foundry` top-level key confirmed present in both `en-US`/`zh-CN` locale JSON. |
| 16 | Playwright E2E coverage exists for the core user story (status visibility, retry, updated status, portal link) | D-06, D-07 | VERIFIED | `frontend/e2e/skill-foundry-sync.spec.ts` exists, contains 4 `test(` blocks; per 28-04-SUMMARY.md all 6 tests (4 spec + 2 auth setup) pass against the real dev stack. |
| 17 | A brand-new, never-synced skill's editor renders the Foundry status section without crashing | D-06 | VERIFIED | Covered by spec's "no-sync regression" test (28-04-SUMMARY.md); confirmed present in spec file. |
| 18 | Route mocks for the Skill detail GET endpoint use a complete, schema-accurate fixture, not a placeholder (LOW-10) | D-06/D-07 | VERIFIED | `buildSkillFixture(` present in spec file; spec does not contain the literal `full Skill shape` placeholder string (grep-confirmed absent). |

**Score:** 18/18 truths verified (#3 D-03 version-increment closed by live smoke test 2026-07-18).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/app/models/skill.py` | 4 Foundry sync columns | VERIFIED | `foundry_skill_name`, `foundry_sync_status`, `foundry_sync_error`, `foundry_cloud_version` all present (lines 54-58) |
| `backend/alembic/versions/y32a_add_skill_foundry_sync.py` | Migration on top of `x31a_merge_heads` | VERIFIED | `alembic heads` reports single head `y32a_skill_foundry_sync (head)` -- applies cleanly, no branching |
| `backend/app/services/skill_foundry_service.py` | Entra-ID-only client + sync/delete/portal-url, collision-safe naming | VERIFIED | All required functions present: `_sanitize_skill_name`, `_build_unique_foundry_name`, `get_skills_client`, `sync_skill_to_foundry`, `delete_skill_from_foundry`, `get_skill_portal_url`. `AzureKeyCredential` grep returns 0 matches (no API-key fallback) |
| `backend/app/services/skill_consumption_service.py` | Toolbox mount + MCP probe + download fallback + local-degrade + TTL cache | VERIFIED | `mount_skill_toolbox`, `_try_mcp_fetch`, `download_and_extract_skill_content`, `get_skill_content_for_session`, `_cache_get`/`_cache_set`, `_scenario_pin_is_stale` all present |
| `backend/app/services/session_service.py` | Wired to consumption abstraction | VERIFIED | 2 call sites of `get_skill_content_for_session`; `load_skill_for_scenario` import removed (grep confirms only referenced via the fallback inside `skill_consumption_service.py`) |
| `backend/app/schemas/skill.py` | Foundry fields + portal-url response schema | VERIFIED | 4 fields in `SkillListOut`, `SkillFoundryPortalUrlResponse` class present |
| `backend/app/api/skills.py` | retry-sync + portal-url routes, admin-gated, published-only guard | VERIFIED | Both routes present; `if skill.status != "published":` guard confirmed (not a blocklist) |
| `frontend/src/components/admin/skill-foundry-status-section.tsx` | i18n'd status/retry/portal-link section | VERIFIED | Component exists, exports `SkillFoundryStatusSection`, 12 `t("foundry.` calls |
| `frontend/src/pages/admin/skill-editor.tsx` | Component wired in | VERIFIED | Import + mutation + render call all present |
| `frontend/public/locales/{en-US,zh-CN}/skill.json` | `foundry.*` i18n keys | VERIFIED | `"foundry"` top-level key present in both files |
| `frontend/e2e/skill-foundry-sync.spec.ts` | E2E coverage of the Foundry sync UI story | VERIFIED | File exists, 4 tests, `buildSkillFixture` present, passes 6/6 against real dev stack per 28-04-SUMMARY.md |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `skill_service.py` | `skill_foundry_service.py` | `publish_skill()`/`archive_skill()`/`delete_skill()` call sync/delete | WIRED | 3 call sites confirmed via grep |
| `skill_foundry_service.py` | `skill_zip_service.py` | `export_skill_zip()` reused as ZIP source | WIRED | Confirmed via code inspection of `sync_skill_to_foundry` |
| `session_service.py` | `skill_consumption_service.py` | `get_skill_content_for_session(db, scenario_id)` | WIRED | 2 call sites confirmed |
| `skill_consumption_service.py` | `skill_foundry_service.py` | reuses `get_skills_client`/`FOUNDRY_FEATURES_HEADER` | WIRED | Confirmed via imports/usage in code |
| `skill_consumption_service.py` | `skill_zip_service.py` | reuses `parse_skill_frontmatter()` | WIRED | Confirmed present in both files (shared helper, no new dependency) |
| `voice_live_websocket.py` | `session.focus_instruction` | unchanged consumption channel | WIRED | Confirmed unmodified, reads the field directly |
| `frontend skill-editor.tsx` | `backend api/skills.py` | retry-sync + portal-url mutations | WIRED | `useRetryFoundrySync` hook + component wired into editor; E2E spec exercises both routes via mocks |
| `skill-foundry-status-section.tsx` | `locales/*/skill.json` | `t("foundry.*")` | WIRED | 12 `t("foundry.` calls resolve against confirmed `foundry` locale keys |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Targeted backend test suite for Phase 28 services | `pytest tests/test_skill_foundry_service.py tests/test_skill_consumption_service.py tests/test_skills_api_foundry.py -q` | 72 passed | PASS |
| Alembic migration head consistency | `alembic heads` | `y32a_skill_foundry_sync (head)` (single head) | PASS |
| No API-key fallback in Skills client | `grep AzureKeyCredential skill_foundry_service.py` | 0 matches | PASS |
| Voice Live reads focus_instruction unmodified | `grep focus_instruction voice_live_websocket.py` | 10 matches, all pre-existing consumption pattern | PASS |
| Playwright E2E for Foundry sync UI | (reported in 28-04-SUMMARY.md; not re-run live in this verification pass) | 6/6 passed against real dev stack | PASS (per SUMMARY evidence + spec file inspection) |

Full backend suite (2624 passed, 14 skipped) reported by the execution context is consistent with the targeted 72-test run observed directly during this verification.

### Requirements Coverage

Requirement IDs (D-01..D-07) are phase-local, defined in `28-CONTEXT.md`, not in the global `.planning/REQUIREMENTS.md`.

| Requirement | Description (28-CONTEXT.md) | Status | Evidence |
|-------------|------------------------------|--------|----------|
| D-01 | Skill registered as independent Foundry entity via `create_from_files`, not baked into agent definition | SATISFIED | `sync_skill_to_foundry` + lifecycle hooks |
| D-02 | Session creation mounts skill into Toolbox via `skill_reference`, targeting MCP access | SATISFIED | `mount_skill_toolbox` called from `get_skill_content_for_session` |
| D-03 | Publish syncs; re-publish increments version; archive/delete removes from Foundry | PARTIAL | Publish-sync and archive/delete-removal fully verified. Version-increment-on-republish is an explicitly flagged untested assumption -- see Human Verification |
| D-04 | Consumption abstraction: MCP probed honestly, degrades to `skills.download()` + instruction injection when unavailable | SATISFIED | `_try_mcp_fetch` (real probe) + `download_and_extract_skill_content` fallback |
| D-05 | Both text chat and Voice Live covered via the same mechanism | SATISFIED | Shared `focus_instruction` channel, confirmed unmodified in `voice_live_websocket.py` |
| D-06 | Publish never blocked by Foundry failure; training degrades to local DB injection on Foundry unavailability | SATISFIED | Non-raising service functions + local fallback chain, tested end-to-end |
| D-07 | Skill management UI shows Foundry sync status/version, retry, portal link, matching HCP agent sync UX | SATISFIED | Schema fields + routes + `SkillFoundryStatusSection`, i18n'd |

No orphaned requirements found -- all 7 phase-local requirement IDs are claimed across the 4 plans' `requirements` frontmatter and each maps to concrete, verified implementation.

### Anti-Patterns Found

Carried forward from `28-REVIEW.md` (independently re-confirmed via grep during this verification pass; none are new findings):

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `backend/app/services/skill_zip_service.py` | 203-207 | `export_skill_zip` silently substitutes a one-line placeholder for any `SkillResource` lacking `text_content` (true for all directly-uploaded binary resources) | Warning (WR-01) | The ZIP shipped to Foundry (and included in local exports) can silently drop real PDF/DOCX/PPTX content with `foundry_sync_status` still reporting "synced" and no admin-visible warning. This is upstream of Phase 28's boundary (resource text extraction is Phase 19 territory) but is newly *exposed* as a Foundry-fidelity risk by this phase's sync feature. Not a Phase 28 must-have failure; flagged for a follow-up fix (extract-at-upload-time or surface-a-warning). |
| `frontend/src/components/admin/skill-foundry-status-section.tsx` | 129-150 | Retry-sync button is only disabled for `archived` status, not `draft`/`review`/`failed`, letting an admin trigger a route that always returns 422 for non-published skills | Warning (WR-02) | Reachable in the real UI (`skill-editor.tsx:931-938` renders the section unconditionally); the resulting error toast is generic (IN-01), not the backend's structured message. Does not break the primary retry-on-published-skill flow (the E2E spec's fixture is always `published`), but is a UX gap versus the plan's own MEDIUM-5-aligned intent to mirror backend semantics in the UI. |
| `backend/app/services/skill_foundry_service.py` | 190-207 | `delete_skill_from_foundry`'s `finally` block unconditionally clears local Foundry tracking fields even when the remote delete failed for a non-404 reason | Warning (WR-03) | Can leave an orphaned cloud entity with no local reference and no retry path once a skill is archived (retry-sync is published-only). Documented as intentional-but-risky in `28-REVIEW.md`; no reconciliation job exists yet. Operational risk, not a functional failure of D-03's happy path. |

No blocker-level (critical) anti-patterns found -- consistent with `28-REVIEW.md`'s `critical: 0` finding.

### Human Verification Required

### 1. D-03 version-increment smoke test against a real Azure AI Foundry project

**Test:** Against a live, non-mocked Azure AI Foundry project with valid Entra ID credentials (`az login` locally, or Managed Identity in Azure Container Apps), publish a skill (first sync, creates the Foundry entity at version 1), then trigger a second sync for the same skill (e.g., via the `POST /skills/{id}/foundry-sync` retry route, or by editing and re-publishing a new skill version) and inspect the resulting `skill.foundry_cloud_version`.

**Expected:** `skill.foundry_cloud_version` changes (e.g. `"1"` -> `"2"`) on the second sync, confirming that Foundry's `create_from_files` increments the version when called again with the same skill name on the Agents API Skills surface.

**Why human:** This requires a real external Azure AI Foundry project and live credentials that cannot be provisioned inside this automated verification pass. The implementing plan (`28-01-PLAN.md` Task 2 `<verify><manual>` block) explicitly labels this an UNTESTED ASSUMPTION: the confirmed 1->2 version-increment evidence in the team's prior research (`docs/microsoft-agent-framework/10-agent-skills-foundry-upload-and-toolbox.md` §12.4) comes from a *different*, unused Responses API `.versions.create()` path -- not the `create_from_files` call this phase actually uses. `28-01-SUMMARY.md` confirms the smoke test has not yet been run ("Not yet confirmed... has NOT been run in this session"). If the version does not increment as expected, `D-03`'s re-publish/version-recovery semantics would need a follow-up plan (e.g., suffix-based naming per publish, or explicit version pinning) before being relied upon in production.

### Gaps Summary

No functional gaps block the phase goal: skills register as first-class Foundry entities on publish (D-01), mount into the HCP agent's toolbox at session time with an honest MCP probe and a verified download fallback (D-02/D-04), feed both text chat and Voice Live through the unchanged `focus_instruction` channel (D-05), degrade non-blockingly to local DB injection at every failure point (D-06), and expose full sync visibility/retry/portal-link UI to admins (D-07) -- all backed by 72 passing targeted unit/integration tests and a 6/6-passing Playwright E2E spec against the real dev stack.

The phase is held at `human_needed` rather than `passed` for exactly one reason: D-03's re-publish version-increment behavior is an explicitly self-flagged, unconfirmed assumption about real Foundry server-side behavior that this environment cannot verify (no live Azure AI Foundry project/credentials available). Three pre-existing warning-level findings from `28-REVIEW.md` (WR-01 binary-resource placeholder fidelity, WR-02 frontend retry-button status gating, WR-03 delete-failure field-reset) are carried forward as anti-patterns for awareness -- none are blocking, and none contradict any must-have truth above.

---

_Verified: 2026-07-18T11:24:32Z_
_Verifier: Claude (gsd-verifier)_
