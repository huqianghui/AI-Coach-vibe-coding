---
phase: 28-sop-skill-ai-foundary-skill-hcp
reviewed: 2026-07-18T11:06:35Z
depth: standard
files_reviewed: 20
files_reviewed_list:
  - backend/alembic/versions/y32a_add_skill_foundry_sync.py
  - backend/app/api/skills.py
  - backend/app/models/skill.py
  - backend/app/schemas/skill.py
  - backend/app/services/session_service.py
  - backend/app/services/skill_consumption_service.py
  - backend/app/services/skill_foundry_service.py
  - backend/app/services/skill_service.py
  - backend/app/services/skill_zip_service.py
  - backend/tests/test_skill_api_unit.py
  - backend/tests/test_skill_consumption_service.py
  - backend/tests/test_skill_foundry_service.py
  - backend/tests/test_skills_api_foundry.py
  - frontend/e2e/skill-foundry-sync.spec.ts
  - frontend/public/locales/en-US/skill.json
  - frontend/public/locales/zh-CN/skill.json
  - frontend/src/api/skills.ts
  - frontend/src/components/admin/skill-foundry-status-section.tsx
  - frontend/src/hooks/use-skills.ts
  - frontend/src/pages/admin/skill-editor.tsx
  - frontend/src/types/skill.ts
findings:
  critical: 0
  warning: 3
  info: 2
  total: 5
status: issues_found
---

# Phase 28: Code Review Report

**Reviewed:** 2026-07-18T11:06:35Z
**Depth:** standard
**Files Reviewed:** 20
**Status:** issues_found

## Summary

Phase 28 wires a new "Skill Foundry Sync" feature: publishing a Skill now best-effort syncs it as a
first-class entity to Azure AI Foundry, archiving/deleting a skill best-effort deletes the cloud
entity, and a training session prefers cloud content (Toolbox mount -> MCP probe -> ZIP download)
before falling back to the existing local DB injection. The "never raises" contract for
`sync_skill_to_foundry` / `delete_skill_from_foundry` is implemented correctly and is well covered by
unit tests (`test_skill_foundry_service.py`, `test_skills_api_foundry.py`,
`test_skill_consumption_service.py`). The Entra-ID-only credential path (no API-key fallback),
collision-safe naming, ZIP-security reuse for both import and Foundry sync/download, the HIGH-1 TTL
cache, and the MEDIUM-4 version-pin bypass are all implemented as documented and are backed by
targeted tests. The alembic migration chain is a clean single-head append onto `x31a_merge_heads`.

No critical (security/crash/data-loss) issues were found. Three warning-level issues were found: a
frontend UI gap that lets users trigger an operation the backend will reject 422 for non-published
skills, an intentional-but-risky field-reset-on-error path in `delete_skill_from_foundry` that can
orphan a cloud entity with no retry route once a skill is archived, and — the most consequential
finding — `sync_skill_to_foundry`'s ZIP payload (via `export_skill_zip`) silently substitutes a
placeholder stub for any resource lacking `text_content`, which is true for every resource uploaded
through the direct `/resources` upload endpoint (only AI-conversion-pipeline-created resources get
real extracted text). This means binary reference materials (PDF/DOCX/PPTX) uploaded directly and
then published will sync to Foundry as placeholder text with no error surfaced to the admin. Two
info-level items (generic error toast on retry failure, a naming nit) round out the findings.

## Warnings

### WR-01: `export_skill_zip` silently ships placeholder text for directly-uploaded binary resources, undermining Foundry sync fidelity

**File:** `backend/app/services/skill_zip_service.py:198-207`
**Issue:** `sync_skill_to_foundry` (`backend/app/services/skill_foundry_service.py:133-160`) builds its
Foundry payload by calling `export_skill_zip`, which for each `SkillResource` does:
```python
if resource.text_content:
    zf.writestr(file_path, resource.text_content)
else:
    # Placeholder for binary resources
    zf.writestr(file_path, f"# {resource.filename}\n# Binary content not included")
```
`text_content` is only populated by the AI-conversion pipeline
(`backend/app/services/skill_conversion_service.py:482`, `backend/app/services/skill_creator_service.py:560`).
The direct upload route `upload_resource` (`backend/app/api/skills.py:732-762`) creates a
`SkillResource` from raw uploaded bytes and never sets `text_content`. Consequently, any admin who
uploads a PDF/DOCX/PPTX reference directly (rather than going through the AI-conversion flow) and then
publishes the skill will have that resource silently replaced by a one-line placeholder string in both
the exported ZIP *and* the ZIP synced to Foundry — with `foundry_sync_status` reporting "synced" and no
warning that content was dropped. This is a correctness/data-fidelity gap that is easy to hit in normal
admin usage and hard to detect after the fact (the sync "succeeds").
**Fix:** Either (a) extract text from binary resources at upload time in `upload_resource` (reusing the
extraction logic already in `skill_creator_service.py:86-110`), or (b) have `export_skill_zip` fail loud
/ surface a warning (e.g. append to `foundry_sync_error` or a new `sync_warnings` field) when it has to
substitute a placeholder for a resource going into a Foundry sync ZIP, so admins are not silently misled
about what was actually shipped to Foundry. Option (a) is preferable since it also improves the
existing ZIP-export/import feature (D-27), not just Foundry sync.

### WR-02: Retry-sync button is not gated on `skill.status === "published"`, letting users trigger a route that always 422s otherwise

**File:** `frontend/src/components/admin/skill-foundry-status-section.tsx:129-150`
**Issue:** The backend route `retry_foundry_sync` (`backend/app/api/skills.py:556-578`) enforces
`if skill.status != "published": bad_request(...)` (422), restricting retry-sync to published skills
only (MEDIUM-5). The component only branches on `isArchived` (`skill?.status === "archived"`, line 37)
to decide whether to render the retry button — for `draft`, `review`, and `failed` statuses the button
renders fully enabled (`disabled={retrySyncPending || foundryStatus === "pending"}`, line 138), so an
admin viewing a never-published skill's Settings tab can click "Retry Sync" and get a 422 with only the
generic error toast (see IN-01). This is reachable in the real UI:
`frontend/src/pages/admin/skill-editor.tsx:931-938` renders `SkillFoundryStatusSection` unconditionally
for any existing skill, regardless of status. It is also not caught by the existing e2e suite —
every `page.route()` mock in `frontend/e2e/skill-foundry-sync.spec.ts` sets `status: "published"`
(e.g. `buildSkillFixture({..., status: "published", ...})` at lines 127-133, 174-180), so the
draft/review/failed path is never exercised end-to-end.
**Fix:** Gate the button on published status as well, mirroring the backend contract:
```tsx
const isArchived = skill?.status === "archived";
const isPublished = skill?.status === "published";
...
{isArchived ? (
  <p>...</p>
) : isPublished ? (
  <Button ...>...</Button>
) : (
  <p className="text-xs text-muted-foreground">{t("foundry.notPublishedNote")}</p>
)}
```
Add a corresponding e2e case with `status: "draft"` (or `"review"`) asserting the button is disabled/hidden.

### WR-03: `delete_skill_from_foundry` unconditionally clears local Foundry tracking fields even when the remote delete fails for a non-404 reason, risking an untracked orphaned cloud entity

**File:** `backend/app/services/skill_foundry_service.py:190-207`
**Issue:** The `finally` block resets `foundry_skill_name`, `foundry_cloud_version`,
`foundry_sync_status`, and `foundry_sync_error` to empty/`"none"` unconditionally — including on the
`else` branch of a non-404 exception (line 200-201, which only logs a warning and falls through to
`finally`). Once `archive_skill()` (which calls this at `backend/app/services/skill_service.py:232`)
completes, the local Skill record has lost all record of the Foundry entity's name, so there is no
retry path: `/foundry-sync` (the only route that can re-sync) is restricted to `status == "published"`
skills, and an archived skill cannot be re-published without first being restored to draft
(`restore_skill`, which per the review notes does not touch foundry_* fields either). If the delete
call failed for a transient reason (network blip, throttling, auth hiccup) rather than because the
entity was already gone, the Foundry-side entity is left running with no local reference to it and no
UI signal that cleanup didn't actually happen. This behavior is intentional per
`test_skill_foundry_service.py`'s delete-non-404 test (confirms the reset happens either way), but it
is worth flagging as an operational risk since there is currently no cleanup/reconciliation path (e.g.
a periodic job that lists Foundry skills and reconciles against local `foundry_skill_name` values).
**Fix:** At minimum, log at `ERROR` (not `WARNING`) for the non-404 case so it's visible in
alerting/monitoring, and consider preserving `foundry_sync_status="failed"` (with the error message)
instead of resetting to `"none"` when the remote call raised a non-404 error, so the local record still
reflects "there may be an orphaned cloud entity" rather than looking like clean deletion succeeded.
If the local record must be cleared regardless (e.g. because `Skill.status` is now `archived` and the
UI hides Foundry state for archived skills anyway per WR-02's `isArchived` branch), consider emitting a
structured log event or admin-visible alert instead of silently downgrading to `"none"`.

## Info

### IN-01: Foundry retry-sync error toast shows generic axios message instead of backend's structured error detail

**File:** `frontend/src/pages/admin/skill-editor.tsx:299-300`
**Issue:** `onError: (err) => toast.error(t("foundry.retryError", { error: (err as Error).message }))`
surfaces whatever `Error.message` axios produces (typically `"Request failed with status code 422"`)
rather than the backend's structured `{"code": "...", "message": "Foundry sync retry is only available
for published skills", ...}` body. Confirmed via `frontend/src/api/client.ts`: the response interceptor
only special-cases 401 (clears auth, redirects to `/login`) and otherwise does a bare
`Promise.reject(error)` — it never extracts `error.response.data.message` into the propagated error.
This means once WR-02 is fixed the toast for any *other* failure mode (e.g. a genuine Foundry outage)
will still be an unhelpful generic message.
**Fix:** In the axios response interceptor (or in the mutation's `onError`), prefer
`err.response?.data?.message ?? err.message` when building the toast string, so backend-provided detail
reaches the admin.

### IN-02: `_scenario_pin_is_stale` name doesn't match what it checks

**File:** `backend/app/services/skill_consumption_service.py:80-88`
**Issue:** The function only checks `scenario.skill_version_id is not None` — i.e. whether a pin
*exists* — not whether the pinned version is stale relative to the current Foundry cloud version. The
docstring explains the real intent correctly ("skip the cloud path unconditionally... when a pin
exists"), so this is a naming clarity nit only, not a logic bug — but a future reader skimming call
sites (`get_skill_content_for_session`, line 282) could reasonably misread the name as "returns True
only if the pin is outdated."
**Fix:** Rename to `_scenario_has_version_pin` (or similar) to match the actual check, or update the
name to `_scenario_should_skip_cloud_path` to describe its role at the call site.

---

_Reviewed: 2026-07-18T11:06:35Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
