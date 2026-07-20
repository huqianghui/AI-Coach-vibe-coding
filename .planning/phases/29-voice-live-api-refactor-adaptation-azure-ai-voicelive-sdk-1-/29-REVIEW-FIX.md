---
phase: 29-voice-live-api-refactor-adaptation-azure-ai-voicelive-sdk-1-
fixed_at: 2026-07-20T00:00:00Z
review_path: .planning/phases/29-voice-live-api-refactor-adaptation-azure-ai-voicelive-sdk-1-/29-REVIEW.md
iteration: 1
findings_in_scope: 3
fixed: 3
skipped: 0
status: all_fixed
---

# Phase 29: Code Review Fix Report

**Fixed at:** 2026-07-20T00:00:00Z
**Source review:** .planning/phases/29-voice-live-api-refactor-adaptation-azure-ai-voicelive-sdk-1-/29-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 3 (0 critical, 3 warning — per fix_scope=critical_warning)
- Fixed: 3
- Skipped: 0

## Fixed Issues

### WR-01: Stale foundation-model cache is discarded on any transient Foundry error

**Files modified:** `frontend/src/components/admin/agent-foundation-model-select.tsx`, `frontend/public/locales/en-US/admin.json`, `frontend/public/locales/zh-CN/admin.json`
**Commit:** f01e515
**Applied fix:** Changed the blocking-error condition from `isError || data?.error` to
`isError || (data?.error && models.length === 0)`, so a transient Foundry error no
longer discards a still-usable stale cached model list. When `data.stale` is `true`
and models are present, the dropdown now renders normally with a new non-blocking
amber warning banner (`hcp.foundationModelStale`, added to both `en-US` and `zh-CN`
locale files) instead of the blocking destructive-error UI. Verified via `npx tsc -b`
(no errors) and `npx vitest run src/components/admin/agent-foundation-model-select.test.tsx`
(5/5 passed, including the existing `data.error` + empty-`models` regression test which
still correctly renders the blocking error state).

### WR-02: Documentation contradicts the implemented (and tested) `resolve_voice_config()` fallback behavior

**Files modified:** `docs/voice-live-avatar/02-database-schema.md`
**Commit:** 37d1fba
**Applied fix:** Replaced the doc's `resolve_voice_config()` code snippet (which
incorrectly showed `raise ConfigurationError(...)` on a missing `VoiceLiveInstance`)
with a version matching the real implementation in
`backend/app/services/voice_live_instance_service.py`: it returns VoiceLiveInstance
fields when assigned, otherwise returns a hardcoded safe-defaults dict with
`voice_live_enabled=False`, and never raises. Updated the docstring to explicitly
state this behavior and reference D-10/D-09/D-12. Documentation-only change, no tests
required per task scope.

### WR-03: `voice-live-integration.test.ts` uses a pre-Phase-29 `HcpProfile` shape, silently losing coverage instead of failing

**Files modified:** `frontend/src/hooks/voice-live-integration.test.ts`
**Commit:** e6db016
**Applied fix:** Replaced the stale local `HcpProfile` interface (which declared
`avatar_character`, `avatar_style`, `voice_name`, `voice_type` as direct fields no
longer present on the Phase 29 API response) with the correct shape matching the
sibling e2e file `frontend/e2e/voice-avatar-real.spec.ts`: added a
`VoiceLiveInstanceSummary` interface and nested `voice_live_instance?:
VoiceLiveInstanceSummary | null` field on `HcpProfile`. Updated the one predicate that
read the removed direct field (`p.avatar_character`) to read
`p.voice_live_instance?.avatar_character` instead, restoring the intended avatar-HCP
coverage path. Verified via `npx tsc -b` (no errors) and
`npx vitest run src/hooks/voice-live-integration.test.ts` (9/9 passed; backend not
available locally so real-API assertions were gated as expected, consistent with
pre-existing test design).

---

_Fixed: 2026-07-20T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
