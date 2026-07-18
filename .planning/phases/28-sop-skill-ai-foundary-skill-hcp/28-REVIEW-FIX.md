---
phase: 28-sop-skill-ai-foundary-skill-hcp
fixed_at: 2026-07-18T14:08:11Z
review_path: .planning/phases/28-sop-skill-ai-foundary-skill-hcp/28-REVIEW.md
iteration: 1
findings_in_scope: 3
fixed: 3
skipped: 0
status: all_fixed
---

# Phase 28: Code Review Fix Report

**Fixed at:** 2026-07-18T14:08:11Z
**Source review:** .planning/phases/28-sop-skill-ai-foundary-skill-hcp/28-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 3 (WR-01, WR-02, WR-03 — critical_warning scope; IN-01/IN-02 skipped as out of scope)
- Fixed: 3
- Skipped: 0

## Fixed Issues

### WR-01: `export_skill_zip` silently ships placeholder text for directly-uploaded binary resources, undermining Foundry sync fidelity

**Files modified:** `backend/app/api/skills.py`
**Commit:** `040f43c`
**Applied fix:** Chose option (a) from the review's fix guidance (preferable per the reviewer's own note, since it also improves the existing ZIP-export/import feature, not just Foundry sync). `upload_resource` now calls `app.services.skill_text_extractor.extract_text(content, safe_filename)` immediately on upload and persists the result into the new `SkillResource.text_content` / `extraction_status` fields (`"completed"` if text was extracted, `"failed"` otherwise), mirroring the extraction pattern already used by `skill_conversion_service.extract_resource_texts` and `skill_creator_service._collect_material_texts`. This means PDF/DOCX/PPTX/TXT/MD resources uploaded directly via `/resources` now get real extracted text at upload time, so `export_skill_zip` (and therefore `sync_skill_to_foundry`'s ZIP payload) no longer falls back to the `"# {filename}\n# Binary content not included"` placeholder for these files. Verified against `backend/tests/test_skill_api_unit.py::TestUploadResourceEndpoint` (all 4 cases pass, including the PDF-upload success case) and the full `test_skill_api_unit.py` + `test_skill_zip_service.py` suite (72 passed). `ruff check` / `ruff format --check` clean.

### WR-02: Retry-sync button is not gated on `skill.status === "published"`, letting users trigger a route that always 422s otherwise

**Files modified:** `frontend/src/components/admin/skill-foundry-status-section.tsx`, `frontend/public/locales/en-US/skill.json`, `frontend/public/locales/zh-CN/skill.json`, `frontend/e2e/skill-foundry-sync.spec.ts`
**Commit:** `f022dae`
**Applied fix:** Applied the fix exactly as suggested in REVIEW.md — added an `isPublished` branch alongside the existing `isArchived` branch in `SkillFoundryStatusSection`'s Actions block: the retry-sync `<Button>` now renders only when `skill?.status === "published"`; for any other non-archived status (`draft`, `review`, `failed`) a muted note (`t("foundry.notPublishedNote")`) is shown instead, so the button that maps 1:1 onto the backend's `if skill.status != "published": bad_request(...)` 422 gate can no longer be clicked from a state that always fails. Added the `foundry.notPublishedNote` key to both `en-US/skill.json` ("Foundry sync is only available for published skills.") and `zh-CN/skill.json` ("仅已发布的技能支持 Foundry 同步。"). Added a new e2e case in `skill-foundry-sync.spec.ts` — `"retry button is hidden for a never-published (draft) skill (WR-02)"` — that mocks a `status: "draft"` skill fixture and asserts the retry button is absent (`count === 0`) and the not-published note is visible, per the review's explicit suggestion to add a `status: "draft"` e2e case. Verified via `npx tsc -b` (clean) and `npx tsc --noEmit -p e2e/tsconfig.json` (clean) plus manual JSON parse of both locale files. The new e2e test was not executed live (requires a running backend+frontend stack) but is type-checked and structurally consistent with the file's existing passing patterns.

### WR-03: `delete_skill_from_foundry` unconditionally clears local Foundry tracking fields even when the remote delete fails for a non-404 reason, risking an untracked orphaned cloud entity

**Files modified:** `backend/app/services/skill_foundry_service.py`
**Commit:** `5d3df47`
**Applied fix:** Applied the "at minimum" fix explicitly called out in REVIEW.md: the non-404 exception branch in `delete_skill_from_foundry` now logs at `logger.error` (was `logger.warning`) with an expanded message identifying the skill id, the `foundry_skill_name` being cleared, and the underlying error, explicitly stating that the cloud entity may now be orphaned. The reset-to-`"none"` behavior in the `finally` block is intentionally left unchanged — REVIEW.md itself notes this is confirmed-intentional behavior (`test_delete_skill_from_foundry_non_404_error_still_resets_and_does_not_raise`) and that there is currently no reconciliation path that could act on a preserved `"failed"` state anyway (`/foundry-sync` retry is `status == "published"`-only and archived skills can't be re-published without first being restored to draft, which doesn't touch `foundry_*` fields either). Escalating to ERROR-level logging is the change with the highest signal-to-risk ratio: it makes the orphan risk visible in alerting/monitoring without altering functional behavior or requiring a new admin-alert mechanism (out of scope for this review-fix pass). Verified via `python -c "import ast; ast.parse(...)"` (clean) and the full `test_skill_foundry_service.py` suite (31 passed, no regressions — the existing non-404 test still asserts the same reset behavior, only the log level changed). `ruff check` / `ruff format --check` clean.

## Skipped Issues

None — all in-scope findings (WR-01, WR-02, WR-03) were fixed. IN-01 and IN-02 were excluded per `fix_scope: critical_warning` and are documented in 28-REVIEW.md for a future `fix_scope: all` pass if desired.

---

_Fixed: 2026-07-18T14:08:11Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
