---
phase: 29-voice-live-api-refactor-adaptation-azure-ai-voicelive-sdk-1-
plan: 08
subsystem: api
tags: [fastapi, pydantic, ai-foundry, azure-ai-projects, tanstack-query, react, typescript, vitest]

requires:
  - phase: 29 (plan 01)
    provides: Live-verified capabilities.get("chat_completion") filter key and AIProjectClient project-scoped endpoint contract from the Foundry POC
  - phase: 29 (plan 07)
    provides: Confirmed post-D-11 agent-config-left-panel.tsx card layout and the fact that voice_live_model does not exist on HcpFormValues
provides:
  - "D-14: Agent Foundation Model catalog — admin-scoped GET /api/v1/agent-foundation-models, live-pulled from AIProjectClient.deployments.list(), cached 300s, defensively filtered against VOICE_LIVE_MODELS"
  - "Minimal id/label response schema (no connection_name/sku leak)"
  - "Frontend AgentFoundationModelSelect dropdown (loading/error/empty/populated states) wired into the HCP editor's agent panel"
affects: [29-09, 29-10]

tech-stack:
  added: []
  patterns:
    - "Backend: module-level in-process TTL cache dict ({data, fetched_at}) for a cheap, dependency-free 300s cache without Redis"
    - "Backend: _get_project_client Entra-first/API-key-fallback credential resolution, mirrored (not imported) from agent_sync_service.py to keep this service dependency-free of the agent-sync module's DB-coupled flow"
    - "Frontend: local useState fallback binding for a new dropdown when the underlying form schema has no corresponding field (used here because voice_live_model was removed from HcpFormValues in Plan 07)"

key-files:
  created:
    - backend/app/services/agent_foundation_models.py
    - backend/app/schemas/agent_foundation_model.py
    - backend/app/api/agent_foundation_models.py
    - backend/tests/test_agent_foundation_models.py
    - frontend/src/types/agent-foundation-model.ts
    - frontend/src/api/agent-foundation-models.ts
    - frontend/src/hooks/use-agent-foundation-models.ts
    - frontend/src/components/admin/agent-foundation-model-select.tsx
    - frontend/src/components/admin/agent-foundation-model-select.test.tsx
  modified:
    - backend/app/api/__init__.py
    - backend/app/main.py
    - frontend/src/components/admin/agent-config-left-panel.tsx
    - frontend/src/components/admin/agent-config-left-panel.test.tsx
    - frontend/public/locales/zh-CN/admin.json
    - frontend/public/locales/en-US/admin.json

key-decisions:
  - "Used the fallback wiring path (local useState in AgentConfigLeftPanel), not the form-bound primary path, because 29-07-SUMMARY.md confirmed voice_live_model was removed from HcpFormValues by Plan 07 — no field was added to HcpFormValues, hcpSchema, or any backend schema/model"
  - "Composed the AIProjectClient project-scoped endpoint ({base}/api/projects/{project_name}) from Settings fields only (azure_foundry_endpoint + azure_foundry_default_project), rather than agent_sync_service.get_project_endpoint()'s DB-backed resolution, since this service is synchronous and has no DB session"
  - "Renamed the plan's suggested _resolve_credential helper into a single _get_project_client function (mirroring agent_sync_service._get_project_client's exact shape) to avoid duplicating credential-then-client construction logic across two functions"

requirements-completed: [D-14]

duration: 9min
completed: 2026-07-19
---

# Phase 29 Plan 08: Agent Foundation Model Catalog (D-14) Summary

**New admin-scoped, 300s-cached REST endpoint live-pulling chat-capable Foundry deployments via AIProjectClient.deployments.list(), plus a frontend dropdown wired into the HCP editor via a local-state fallback (voice_live_model has no HcpFormValues field to bind to).**

## Performance

- **Duration:** 9 min
- **Tasks:** 2 (both complete)
- **Files modified:** 15 (9 created, 6 modified)

## Accomplishments

- **D-14 backend:** `list_agent_foundation_models()` live-pulls deployments, excludes anything matching `VOICE_LIVE_MODELS` (case-insensitive), applies positive/negative capability-key signals with a defensive include-when-unknown default, and caches results in-process for 300s with stale-on-failure / empty-on-failure-with-no-cache behavior.
- **D-14 endpoint:** `GET /api/v1/agent-foundation-models` gated by `require_role("admin")`; response schema exposes only `id`/`label` (T-29-08-01 mitigation verified by a raw-response-text assertion in tests).
- **D-14 frontend:** `AgentFoundationModelSelect` renders all 4 UI-SPEC states (loading, error+retry, empty, populated) plus a 5th covered case (fetch-succeeded-but-`data.error`-set), wired into `agent-config-left-panel.tsx` as a new card immediately below the VL Instance Summary Card, reusing the `admin:hcp.modelDeployment` i18n label per the plan's explicit instruction.
- Confirmed and executed the **fallback wiring path**: since `voice_live_model` does not exist on `HcpFormValues` (per 29-07-SUMMARY.md), the dropdown's selection is tracked via a local `useState<string>("")` inside `AgentConfigLeftPanel`, not persisted to any form field, schema, or backend model.

## Task Commits

1. **Task 1: Backend Foundry deployments catalog service + admin-scoped endpoint** — `fb43883` (feat)
2. **Task 2: Frontend Foundation Model dropdown + wiring into HCP editor** — `cee1621` (feat)

## Files Created/Modified

- `backend/app/services/agent_foundation_models.py` — cache, `_is_chat_capable` filter, `_get_project_client`, `_build_project_endpoint`, `list_agent_foundation_models`.
- `backend/app/schemas/agent_foundation_model.py` — `AgentFoundationModelInfo` (id/label only), `AgentFoundationModelsResponse`.
- `backend/app/api/agent_foundation_models.py` — admin-gated `GET /agent-foundation-models` router.
- `backend/app/api/__init__.py`, `backend/app/main.py` — router registration.
- `backend/tests/test_agent_foundation_models.py` — 9/9 behaviors: filter exclusion/inclusion (4), cache reuse/stale/empty (3), admin-403/admin-200-minimal-fields (2).
- `frontend/src/types/agent-foundation-model.ts`, `frontend/src/api/agent-foundation-models.ts`, `frontend/src/hooks/use-agent-foundation-models.ts` — type/api/hook layer mirroring the voice-live-instances pattern.
- `frontend/src/components/admin/agent-foundation-model-select.tsx` + `.test.tsx` — dropdown component, 5 test behaviors.
- `frontend/src/components/admin/agent-config-left-panel.tsx` — new card wiring `AgentFoundationModelSelect` via local state; comment numbering updated (now 4 cards).
- `frontend/src/components/admin/agent-config-left-panel.test.tsx` — added a mock for the new child component (required since it now calls a real TanStack Query hook) and updated the pre-Plan-07 "does not render VoiceLiveModelSelect" assertion to reflect the intentional `modelDeployment` label reuse.
- `frontend/public/locales/{zh-CN,en-US}/admin.json` — `foundationModelLoading`/`foundationModelError`/`foundationModelEmpty` keys, validated as parseable JSON.

## Decisions Made

- Fallback wiring path confirmed and used (see key-decisions above) — no new field added anywhere in the HCP form/schema/model chain.
- Project-scoped endpoint composed from Settings fields directly (`_build_project_endpoint`), matching the 29-01 POC's live-verified contract that `AIProjectClient` requires `{base}/api/projects/{project_name}`, not the bare account endpoint — the plan's literal action pseudocode used the bare endpoint, which was corrected here for correctness (Rule 2).
- Single `_get_project_client` function (not a separate `_resolve_credential` + client-builder pair) to avoid duplicated Entra/API-key branching logic, mirroring `agent_sync_service._get_project_client`'s exact shape as instructed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Compose project-scoped endpoint instead of using the bare account endpoint**
- **Found during:** Task 1
- **Issue:** The plan's action pseudocode built `AIProjectClient(endpoint=get_settings().azure_foundry_endpoint, ...)` directly, but the cross-plan contract restated from 29-01's live POC states `AIProjectClient` requires a project-scoped endpoint (`{base}/api/projects/{project_name}`), not the bare account endpoint — using the bare endpoint would 404 against the real Foundry API.
- **Fix:** Added `_build_project_endpoint(base_endpoint, project_name)` composing the endpoint from `settings.azure_foundry_endpoint` + `settings.azure_foundry_default_project`, mirroring `agent_sync_service.get_project_endpoint()`'s composition logic but operating on Settings fields only (no DB session available in this synchronous service).
- **Files modified:** `backend/app/services/agent_foundation_models.py`
- **Verification:** Unit-testable in isolation; mocked-client tests unaffected since `_get_project_client` is patched directly in tests.
- **Committed in:** `fb43883` (Task 1 commit)

**2. [Rule 3 - Blocking] Existing agent-config-left-panel.test.tsx broke on the new hook-backed child component**
- **Found during:** Task 2
- **Issue:** `AgentFoundationModelSelect` internally calls the real `useAgentFoundationModels()` TanStack Query hook, which requires a `QueryClientProvider` not present in the existing test's `TestWrapper` — all 17 pre-existing tests failed with "No QueryClient set".
- **Fix:** Added `vi.mock("@/components/admin/agent-foundation-model-select", ...)` stubbing the component (matching the existing pattern for `ConnectKbDialog`/`InstructionsSection`), and updated the one assertion that checked for the *absence* of the `modelDeployment` label (now intentionally reused per this plan) to instead assert the new stub is present.
- **Files modified:** `frontend/src/components/admin/agent-config-left-panel.test.tsx`
- **Verification:** `npx vitest run src/components/admin/agent-config-left-panel.test.tsx src/components/admin/agent-foundation-model-select.test.tsx` — 22/22 passing.
- **Committed in:** `cee1621` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 missing-critical endpoint-correctness fix, 1 blocking test-infrastructure fix)
**Impact on plan:** Both fixes were necessary for correctness (Foundry endpoint shape) and for not regressing pre-existing test coverage. No scope creep — no new features beyond the plan's `<action>` blocks.

## Issues Encountered

None beyond the two deviations above.

## User Setup Required

None - no external service configuration required. The endpoint relies on the already-configured `azure_foundry_endpoint`/`azure_foundry_api_key`/`azure_foundry_default_project` settings used elsewhere in the codebase (e.g., `agent_sync_service.py`).

## Next Phase Readiness

- The Agent Foundation Model catalog is fully decoupled from `VOICE_LIVE_MODELS` and ready for any future plan that wants to persist a selected foundation model — that would require a new backend field/migration (out of scope here, correctly left as local UI state per the fallback path).
- Plans 29-09/29-10 can rely on `GET /api/v1/agent-foundation-models` being live and admin-gated.

---
*Phase: 29-voice-live-api-refactor-adaptation-azure-ai-voicelive-sdk-1-*
*Completed: 2026-07-19*

## Self-Check: PASSED

- Commits found: fb43883, cee1621
- Files found: backend/app/services/agent_foundation_models.py, backend/app/schemas/agent_foundation_model.py, backend/app/api/agent_foundation_models.py, backend/tests/test_agent_foundation_models.py, frontend/src/types/agent-foundation-model.ts, frontend/src/api/agent-foundation-models.ts, frontend/src/hooks/use-agent-foundation-models.ts, frontend/src/components/admin/agent-foundation-model-select.tsx, frontend/src/components/admin/agent-foundation-model-select.test.tsx
