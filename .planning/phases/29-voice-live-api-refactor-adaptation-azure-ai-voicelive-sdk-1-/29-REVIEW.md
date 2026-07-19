---
phase: 29-voice-live-api-refactor-adaptation-azure-ai-voicelive-sdk-1-
reviewed: 2026-07-20T00:00:00Z
depth: standard
files_reviewed: 74
files_reviewed_list:
  - backend/alembic/versions/z33a_drop_hcp_inline_voice_fields.py
  - backend/app/api/__init__.py
  - backend/app/main.py
  - backend/app/api/agent_foundation_models.py
  - backend/app/api/hcp_profiles.py
  - backend/app/api/scenarios.py
  - backend/app/config.py
  - backend/app/models/hcp_profile.py
  - backend/app/schemas/agent_foundation_model.py
  - backend/app/schemas/hcp_profile.py
  - backend/app/services/agent_foundation_models.py
  - backend/app/services/agent_sync_service.py
  - backend/app/services/hcp_profile_service.py
  - backend/app/services/voice_live_instance_service.py
  - backend/app/services/voice_live_webrtc.py
  - backend/app/services/voice_live_websocket.py
  - backend/pyproject.toml
  - backend/tests/test_agent_foundation_models.py
  - backend/tests/test_agent_sync_service.py
  - backend/tests/test_coverage_gaps.py
  - backend/tests/test_hcp_agent_sync_integration.py
  - backend/tests/test_hcp_profiles_api.py
  - backend/tests/test_hcp_test_chat.py
  - backend/tests/test_knowledge_base.py
  - backend/tests/test_no_trailing_slash_redirect.py
  - backend/tests/test_scenario_avatar_fields.py
  - backend/tests/test_scenarios_api.py
  - backend/tests/test_schemas_phase2.py
  - backend/tests/test_sessions_api.py
  - backend/tests/test_voice_live_instance.py
  - backend/tests/test_voice_live_instance_service.py
  - backend/tests/test_voice_live_management.py
  - backend/tests/test_voice_live_model.py
  - backend/tests/test_voice_live_per_hcp.py
  - backend/tests/test_voice_live_service.py
  - backend/tests/test_voice_live_session_context.py
  - backend/tests/test_voice_live_webrtc.py
  - backend/tests/test_voice_live_websocket.py
  - frontend/e2e/hcp-editor-voice-tab.spec.ts
  - frontend/e2e/voice-avatar-real.spec.ts
  - frontend/public/locales/en-US/admin.json
  - frontend/public/locales/zh-CN/admin.json
  - frontend/src/api/agent-foundation-models.ts
  - frontend/src/components/admin/agent-config-left-panel.tsx
  - frontend/src/components/admin/agent-config-left-panel.test.tsx
  - frontend/src/components/admin/agent-foundation-model-select.tsx
  - frontend/src/components/admin/agent-foundation-model-select.test.tsx
  - frontend/src/components/admin/hcp-table.tsx
  - frontend/src/components/admin/voice-avatar-tab.tsx
  - frontend/src/hooks/use-agent-foundation-models.ts
  - frontend/src/hooks/voice-live-integration.test.ts
  - frontend/src/pages/admin/hcp-profile-editor.tsx
  - frontend/src/pages/user/conference-session.tsx
  - frontend/src/pages/user/scenario-group-run.tsx
  - frontend/src/pages/user/training.tsx
  - frontend/src/pages/user/unified-session.tsx
  - frontend/src/pages/user/voice-session.tsx
  - frontend/src/router/index.tsx
  - frontend/src/types/agent-foundation-model.ts
  - frontend/src/types/hcp.ts
  - frontend/vite.config.ts
  - frontend/vitest.config.ts
  - docs/voice-live-avatar/00-index.md
  - docs/voice-live-avatar/01-architecture.md
  - docs/voice-live-avatar/02-database-schema.md
  - docs/voice-live-avatar/03-api-design.md
  - docs/voice-live-avatar/04-backend-websocket.md
  - docs/voice-live-avatar/09-websocket-webrtc-protocol.md
  - docs/voice-live-avatar/10-nat-traversal.md
  - docs/voice-live-avatar/11-azure-voice-live-reference.md
  - docs/voice-live-avatar/12-frontend-deep-dive.md
  - docs/voice-live-avatar/13-backend-deep-dive.md
  - docs/voice-live-avatar/14-production-operations.md
  - docs/voice-live-avatar/appendix-glossary.md
findings:
  critical: 0
  warning: 3
  info: 3
  total: 6
status: issues_found
---

# Phase 29: Code Review Report

**Reviewed:** 2026-07-20T00:00:00Z
**Depth:** standard
**Files Reviewed:** 74
**Status:** issues_found

## Summary

Phase 29 migrates Voice Live integration to `azure-ai-voicelive==1.3.0b1` with the GA
`api_version="2026-07-15"` sourced exclusively from `settings.voice_live_api_version`,
removes the classic `asst_*` agent branch in favor of hosted (name-based) Foundry
agents only, drops the 14 inline voice/avatar columns from `HcpProfile` in favor of a
mandatory `VoiceLiveInstance` FK, and adds an Agent Foundation Model catalog
endpoint + frontend dropdown. The implementation is solid and internally consistent:

- The GA api-version single-source-of-truth rule is honored at every voice-live
  `connect()` call site (`voice_live_websocket.py`, `voice_live_webrtc.py`); no stray
  api-version literals were found for voice-live specifically.
- The classic `asst_*` branch has been fully removed from the runtime connect path;
  remaining `asst_*` references are exclusively in the auto-migration
  (`resync_classic_agent`) and are correctly load-bearing.
- `resolve_voice_config()` correctly never reads the deleted inline `HcpProfile`
  columns and returns safe, `voice_live_enabled=False` defaults when no
  `VoiceLiveInstance` is linked — this is the cornerstone of D-09/D-12 and is
  implemented and tested correctly across both mocked and real-DB test suites.
- The mandatory-VL-instance invariant (D-13) is enforced consistently at the DB
  migration, ORM, Pydantic schema, service layer ("cannot clear"), API (422 on empty/
  missing), and frontend Zod-schema layers.
- The Agent Foundation Model catalog endpoint is admin-gated, returns a minimal
  DTO (no connection_name/sku leakage), and has well-designed stale-cache-on-failure
  semantics with solid test coverage.
- i18n locale files (`en-US`/`zh-CN` `admin.json`) are valid JSON with no missing
  keys for any string referenced by the reviewed components.

Three issues are worth addressing before or shortly after merge: a frontend UI bug
that discards a still-usable stale foundation-model cache on transient Foundry
errors, a documentation page that describes `resolve_voice_config()` as
exception-raising when the implemented (and tested) behavior is a silent
safe-defaults fallback, and a stale integration test file whose type shape predates
the Phase 29 schema change and silently loses coverage rather than failing loudly.

## Warnings

### WR-01: Stale foundation-model cache is discarded on any transient Foundry error

**File:** `frontend/src/components/admin/agent-foundation-model-select.tsx:38-55`
**Issue:** The backend's `list_agent_foundation_models()` is explicitly designed to
serve a stale cached model list plus `stale=true` and a non-fatal `error` message
when a fresh Foundry API call fails (see `backend/app/services/agent_foundation_models.py`).
The frontend component, however, treats *any* truthy `data?.error` as a full failure
state and renders the blocking error UI instead of the dropdown — even when
`data.models` is non-empty and perfectly usable:
```tsx
if (isError || data?.error) {
  return (
    <div className="flex items-center gap-2">
      <p className="text-xs text-destructive flex-1">{t("hcp.foundationModelError")}</p>
      <Button onClick={() => refetch()}>...</Button>
    </div>
  );
}
const models = data?.models ?? [];
```
This defeats the backend's stale-cache-fallback design: during any transient Foundry
outage, admins lose the ability to pick a foundation model from the (still valid)
cached list, even though the backend intentionally kept serving it. The existing test
suite (`agent-foundation-model-select.test.tsx`) only exercises `stale: true` combined
with an *empty* `models: []` list, so this gap has no regression coverage today.
**Fix:** Only treat the response as blocking-error when there is no usable data,
e.g.:
```tsx
if (isError || (data?.error && (data?.models?.length ?? 0) === 0)) {
  // blocking error UI
}
// otherwise render the Select using data.models, optionally with a
// non-blocking warning banner when data.stale is true
```

### WR-02: Documentation contradicts the implemented (and tested) `resolve_voice_config()` fallback behavior

**File:** `docs/voice-live-avatar/02-database-schema.md:93-116`
**Issue:** The doc states:
```python
def resolve_voice_config(profile: HcpProfile) -> dict:
    """
    强制要求: profile.voice_live_instance 必须存在（D-09/D-10，无内联字段回退）
    未分配 VoiceLiveInstance 的 HCP 视为配置错误，而非静默降级
    ...
    """
    if not profile.voice_live_instance:
        raise ConfigurationError(f"HCP {profile.id} 未分配 VoiceLiveInstance")
```
This describes `resolve_voice_config()` as *raising* on a missing `VoiceLiveInstance`.
The actual implementation in `backend/app/services/voice_live_instance_service.py`
does the opposite — it returns a hardcoded safe-defaults dict with
`voice_live_enabled=False` and never raises. This is corroborated by
`backend/tests/test_voice_live_instance_service.py::test_resolve_voice_config_inline_fallback`
and `::test_resolve_voice_config_inline_fallback_real_db`, both of which assert the
safe-defaults dict (`voice_name == "en-US-AvaNeural"`, `voice_live_enabled is False`,
etc.) rather than an exception. A future engineer relying on this doc page would
implement error-handling around a `ConfigurationError` that is never actually thrown.
**Fix:** Update the doc snippet to match the real implementation:
```python
def resolve_voice_config(profile: HcpProfile) -> dict:
    """
    未分配 VoiceLiveInstance 的 HCP 返回安全默认值（voice_live_enabled=False），
    而非抛出异常或读取已删除的内联字段（D-09/D-12）。
    """
    inst = profile.voice_live_instance
    if inst:
        return {...}
    return {"voice_live_enabled": False, ...}  # safe defaults
```

### WR-03: `voice-live-integration.test.ts` uses a pre-Phase-29 `HcpProfile` shape, silently losing coverage instead of failing

**File:** `frontend/src/hooks/voice-live-integration.test.ts:22-32`
**Issue:** This real-backend integration test suite declares:
```ts
interface HcpProfile {
  id: string;
  name: string;
  avatar_character: string;
  avatar_style: string;
  voice_name: string;
  voice_type: string;
  agent_id?: string;
  agent_sync_status?: string;
  is_active: boolean;
}
```
These four `avatar_*`/`voice_*` fields no longer exist directly on the `HcpProfile`
API response after Phase 29 (they were dropped in migration `z33a` and now live under
`hcp_profile.voice_live_instance.*`, as correctly modeled in the sibling e2e file
`frontend/e2e/voice-avatar-real.spec.ts`). Because every test in this file is gated by
`if (!backendAvailable) return;` and then does `profiles.items.find((p) => p.avatar_character && ...)`,
against the real (Phase-29) API these predicates will now always evaluate to
`undefined`/falsy, so the "no matching profile" branch (`console.warn(...); return;`)
is silently taken every time the backend actually is available — the avatar/agent
coverage this file was written for no longer executes, but no test fails or is
marked skipped, so the coverage loss is invisible in CI output.
**Fix:** Update the local `HcpProfile` interface (and the predicates that use it) to
read `p.voice_live_instance?.avatar_character` / `p.voice_live_instance?.voice_name`,
matching the shape already used correctly in `voice-avatar-real.spec.ts`.

## Info

### IN-01: Dead constant `AGENT_REGISTRY_API_VERSION`

**File:** `backend/app/services/agent_sync_service.py:23`
**Issue:** `AGENT_REGISTRY_API_VERSION = "2025-01-01-preview"` is defined but never
referenced anywhere else in the codebase (confirmed via repo-wide grep). It reads as
a second, unused api-version literal sitting right next to the single-source-of-truth
`settings.voice_live_api_version`, which is confusing given D-02's explicit "do not
hardcode any older preview-dated api-version literal anywhere else" rule.
**Fix:** Remove the constant, or if it is intentionally reserved for a future Agent
Registry REST call, add a comment clarifying it is unrelated to the voice-live
connect() api-version and is not yet wired up.

### IN-02: Stale, permanently-skipped test should be deleted rather than left skipped

**File:** `backend/tests/test_voice_live_instance.py:233-260`
**Issue:** `test_resolve_config_fallback_to_inline` is `@pytest.mark.skip`ped with a
reason describing work ("Plan 29-06 must update the fallback to return safe defaults
instead of reading deleted columns") that has since been completed — the skip reason
itself is now describing history, not a current blocker. Equivalent, currently-passing
coverage for the corrected behavior already exists in
`test_voice_live_instance_service.py::test_resolve_voice_config_inline_fallback` and
`::test_resolve_voice_config_inline_fallback_real_db`, so there is no coverage gap,
but the stale skipped test adds noise and could mislead a future reader into thinking
the fallback is still broken.
**Fix:** Delete the skipped test (coverage is already provided elsewhere) rather than
leaving it permanently skipped.

### IN-03: Vacuous "Voice Mode" toggle tests reference a UI control removed by D-11

**File:** `frontend/e2e/hcp-editor-voice-tab.spec.ts:117-166, 434-489`
**Issue:** Several tests (e.g. "text chat mode shows when Voice Mode is OFF", "VL
Instance selector appears when Voice Mode is toggled ON", "Playground panel shows
voice-related UI when voice mode is ON") gate their logic on `page.getByRole("switch")`,
a per-HCP on/off "Voice Mode" toggle that D-11/D-13 explicitly removed (voice
configuration is now a mandatory VL Instance assignment, not an optional switch — see
the `agent-config-left-panel.test.tsx` regression test "does not render a voice mode
Switch toggle"). Because these e2e tests guard every switch interaction with
`if (switchCount > 0)`, they silently skip all toggle-dependent assertions
(`switchCount` will be `0`) and fall through to weaker assertions that are always true
regardless of the actual VL Instance state, so they no longer exercise the scenario
their titles describe.
**Fix:** Remove or rewrite these tests to reflect the current mandatory-VL-instance
UI (no toggle), consistent with the already-updated "Voice Live Instance selector is
present" test earlier in the same file.

---

_Reviewed: 2026-07-20T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
