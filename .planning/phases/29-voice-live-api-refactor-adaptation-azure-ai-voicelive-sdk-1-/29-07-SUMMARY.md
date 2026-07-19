---
phase: 29-voice-live-api-refactor-adaptation-azure-ai-voicelive-sdk-1-
plan: 07
subsystem: ui
tags: [react, react-hook-form, zod, tanstack-query, vitest, typescript, hcp-profile, voice-live]

requires:
  - phase: 29 (plans 02-06)
    provides: Backend VL Instance relationship model, dropped inline voice/avatar columns, safe-defaults fallback pattern
provides:
  - Client-side D-10 enforcement (HCP must be bound to exactly one VL Instance before save, on create AND edit)
  - D-11 read-only VL Instance Summary Card replacing the editable Voice/Avatar tab controls
  - Frontend type contract (hcp.ts) and every consumer fully mirrors the backend's Plan 29-05 column drop — zero remaining reads of the 14 deprecated inline fields off an HcpProfile-typed value
affects: [29-08, 29-09, 29-10]

tech-stack:
  added: []
  patterns:
    - "VL Instance relationship reads: profile.voice_live_instance?.<field> instead of flat profile.<field>, with safe defaults (false / 'lori' / 'casual') matching backend's HcpProfileBrief.from_hcp_profile"
    - "Client-side blocking validation via zod .refine() + form.setError before the mutation call, paired with inline field error + toast"

key-files:
  created: []
  modified:
    - frontend/src/types/hcp.ts
    - frontend/src/pages/admin/hcp-profile-editor.tsx
    - frontend/src/components/admin/agent-config-left-panel.tsx
    - frontend/src/components/admin/voice-avatar-tab.tsx
    - frontend/src/components/admin/hcp-table.tsx
    - frontend/src/pages/user/conference-session.tsx
    - frontend/src/pages/user/scenario-group-run.tsx
    - frontend/src/pages/user/training.tsx
    - frontend/src/pages/user/unified-session.tsx
    - frontend/src/pages/user/voice-session.tsx
    - frontend/public/locales/zh-CN/admin.json
    - frontend/public/locales/en-US/admin.json

key-decisions:
  - "Voice mode availability is now implied solely by having an assigned VL Instance (D-11) — removed the separate voiceModeEnabled useState/Switch entirely rather than migrating it"
  - "avatar_enabled remains a distinct field on HcpProfile (separate from the 14 deprecated fields) — it gates avatar availability independently of the VL Instance's own enabled flag, so it was correctly left untouched throughout"
  - "Task 3 scope expanded beyond the plan's originally-listed 9 files to every file tsc -b organically flagged after the type contract change, per the plan's own broader verification requirement (repo-wide grep, full tsc -b)"

requirements-completed: [D-10, D-11]

duration: ~45min
completed: 2026-07-19
---

# Phase 29 Plan 07: Frontend VL Instance Binding Enforcement + Field Contract Cleanup Summary

**Client-side D-10/D-11 enforcement plus repo-wide removal of the 14 deprecated inline voice/avatar field reads, completing the frontend mirror of backend Plan 29-05's column drop.**

## Performance

- **Tasks:** 3 (all complete)
- **Files modified:** 20 (across all 3 tasks)

## Accomplishments

- **D-10:** HCP create/edit forms block save (inline field error + toast, no API call) when no VL Instance is assigned, via a zod `.refine()` on `voice_live_instance_id`.
- **D-11:** The Voice/Avatar tab's old editable "Model Deployment" selector and "Voice Mode" toggle `Switch` were fully removed (not migrated). `agent-config-left-panel.tsx` now renders exactly three cards, in this order:
  1. **VL Instance Summary Card (D-11)** — read-only summary of the bound instance (voice, avatar character/style, model) with assign/unassign actions and a link to VL Management; empty-state variant with a "Required" badge when unbound.
  2. **Instructions Section** — auto-generated/override agent instructions (unchanged from prior phases).
  3. **Knowledge & Tools** — collapsible skeleton section (unchanged from prior phases).
  Voice mode availability for the Playground preview is now derived purely from `Boolean(vlInstanceId)` — there is no more independent `voiceModeEnabled` state.
- **D-09 (frontend half):** Deleted the 14 deprecated inline fields (`voice_live_enabled`, `voice_live_model`, `voice_name`, `voice_type`, `voice_temperature`, `voice_custom`, `avatar_character`, `avatar_style`, `avatar_customized`, `turn_detection_type`, `noise_suppression`, `echo_cancellation`, `eou_detection`, `recognition_language`) from `hcp.ts`'s `HcpProfile`/`HcpProfileCreate` types and fixed every consumer. **Confirmed fact: `voice_live_model` does NOT exist on `HcpFormValues`** — model selection now lives entirely on `VoiceLiveInstanceSummary` (`profile.voice_live_instance?.voice_live_model`), read-only, surfaced only via the VL Instance Summary Card; there is no Foundation Model dropdown on the HCP editor itself.

## Task Commits

1. **Task 1: Client-side D-10 enforcement (block save without VL Instance)** — `56fb5ee` (feat)
2. **Task 2: Rebuild Voice/Avatar tab as read-only VL Instance Summary Card (D-11)** — `11bdc6e` (feat)
3. **Task 3: Remove remaining consumers of deleted inline voice/avatar fields** — `1ac99da` (fix)

_Note: Task 1 and Task 2 commits were made in a prior session; this session completed and committed Task 3._

## Files Created/Modified

- `frontend/src/types/hcp.ts` — dropped the 14 deprecated fields from `HcpProfile`/`HcpProfileCreate`; `VoiceLiveInstanceSummary` remains the sole owner of `voice_live_model`, `voice_name`, `avatar_character`, `avatar_style`.
- `frontend/src/components/admin/agent-config-left-panel.tsx` + `.test.tsx` — VL Instance Summary Card, validation error display, remove/unassign flow (17 tests).
- `frontend/src/components/admin/voice-avatar-tab.tsx` + `.test.tsx` — removed internal `voiceModeEnabled` state; derives it from `Boolean(vlInstanceId)` for the Playground preview only (9 tests).
- `frontend/src/components/admin/hcp-table.tsx` — badges read `profile.voice_live_instance?.{voice_name,avatar_character,avatar_style,voice_live_model,enabled}`.
- `frontend/src/pages/user/conference-session.tsx`, `scenario-group-run.tsx`, `training.tsx`, `unified-session.tsx`, `voice-session.tsx` — all flat `hcp?.voice_live_enabled` / `profile?.avatar_character` / `.avatar_style` / `.voice_name` reads replaced with `?.voice_live_instance?.<field>` reads, with `"lori"`/`"casual"` safe defaults where the original code had a fallback.
- 12 test files across `src/api`, `src/hooks`, `src/components/admin`, `src/components/coach`, `src/pages/admin`, `src/pages/user` — fixtures updated to drop the flat fields or nest them under `voice_live_instance`.
- `frontend/public/locales/{zh-CN,en-US}/admin.json` — added `vlInstanceRequired`, `vlInstanceEmptyTitle`, `vlInstanceEmptyBody`, `vlInstanceValidationError`, `vlInstanceSaveBlockedToast`, `vlInstanceRequiredBadge`; updated `removeInstanceConfirm` copy.

## Decisions Made

- Voice mode is implied solely by VL Instance assignment (D-11) — no separate toggle state to keep in sync.
- `avatar_enabled` is a legitimately distinct field (gates avatar availability independently of the VL Instance's `enabled` flag) and was correctly excluded from the 14-field cleanup throughout — verified via the plan's own regex grep returning zero matches for it.
- Task 3's file sweep was expanded beyond the plan's originally-listed 9 files to every file `tsc -b` organically surfaced, since the plan's own `<verification>` section requires a clean, repo-wide `tsc -b` and grep — not just the 9 named files.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Expanded Task 3 scope to all tsc-flagged files, not just the plan's 9 named files**
- **Found during:** Task 3
- **Issue:** The plan named 9 files to grep-check, but deleting the 14 fields from `hcp.ts` broke type-checking in additional files not listed in the plan (`api-clients.test.ts`, `agent-status-section.test.tsx`, `hcp-editor.test.tsx`, `hcp-list.test.tsx`, `scenario-table.test.tsx`, `scenario-card.test.tsx`, `scenario-panel.test.tsx`, `use-hcp-profiles.test.tsx`, `vl-instance-editor.test.tsx`, `training.test.tsx`, and production files `unified-session.tsx`, `voice-session.tsx`, `training.tsx`, `scenario-group-run.tsx`, `conference-session.tsx`).
- **Fix:** Fixed every file `tsc -b` flagged, using the same `profile.voice_live_instance?.<field>` replacement pattern.
- **Files modified:** listed above.
- **Verification:** `npx tsc -b` exits clean; repo-wide grep for the 14 fields as `profile.`/`hcp.` reads returns zero matches; full `vitest run` failure count (114) matches pre-existing baseline exactly (verified via `git stash` A/B comparison — no new failures introduced).
- **Committed in:** `1ac99da` (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (Rule 3 - blocking, scope expansion mandated by the plan's own verification requirements)
**Impact on plan:** No scope creep beyond what the plan's `<verification>` section already required. All fixes were mechanical field-access replacements following the established safe-defaults pattern.

## Issues Encountered

Two candidate failures needed investigation before being ruled out-of-scope: `src/pages/user/voice-session.test.tsx` ("back button navigates to /user/scenarios" — actually navigates to `/user/training`) and `src/components/coach/scenario-panel.test.tsx` ("renders scenario product and area when expanded"), plus a large baseline of pre-existing failures in unrelated admin pages (`azure-config`, `dashboard`, `reports`, `settings`, `training-materials`, `users`), `i18n`, `analytics-components`, `voice-test-playground`, `session-history`, and two stale duplicate test files at `src/__tests__/agent-config-left-panel.test.tsx` and `src/__tests__/voice-avatar-tab.test.tsx` (superseded copies of tests that already pass at their correct `src/components/admin/` location, still asserting the old Model Deployment/Switch UI removed in Task 2). A `git stash` A/B comparison confirmed all of these were failing identically before Task 3's changes — none were caused by this plan's work, so none were fixed, per the deviation rule's scope boundary.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The frontend type contract and every consumer now fully match the backend's dropped columns — Plan 29-08 (Foundation Model dropdown work) can rely on the confirmed fact that `voice_live_model` lives only on `VoiceLiveInstanceSummary`, never on `HcpFormValues`, and should wire its model selection UI against the VL Instance, not the HCP form.
- Pre-existing baseline test failures (unrelated admin pages, stale duplicate `src/__tests__/*` files) remain unresolved and should be triaged separately — they are not blockers for this plan but are flagged here for visibility.

---
*Phase: 29-voice-live-api-refactor-adaptation-azure-ai-voicelive-sdk-1-*
*Completed: 2026-07-19*

## Self-Check: PASSED

- Commits found: 56fb5ee, 11bdc6e, 1ac99da
- Files found: frontend/src/types/hcp.ts, frontend/src/components/admin/agent-config-left-panel.tsx, frontend/src/components/admin/voice-avatar-tab.tsx, frontend/src/components/admin/hcp-table.tsx, frontend/src/pages/user/unified-session.tsx, frontend/src/pages/user/voice-session.tsx, frontend/public/locales/zh-CN/admin.json
