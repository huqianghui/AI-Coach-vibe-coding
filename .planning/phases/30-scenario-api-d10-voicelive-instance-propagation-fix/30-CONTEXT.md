# Phase 30: Scenario API D-10 VoiceLiveInstance Propagation Fix - Context

**Gathered:** 2026-07-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Propagate the Phase 29 D-10 nested structure to the scenario API: replace `HcpProfileSummary` (backend/app/schemas/scenario.py:55-67) hardcoded flat defaults with nested `voice_live_instance: VoiceLiveInstanceSummary | None`, remove the stray flat `avatar_enabled` from frontend/src/types/hcp.ts, and re-verify all scenario `hcp_profile` consumers so scenario-driven voice/digital-human training modes are offered again and avatar character/style resolve correctly.

**Root cause (verified during discussion):** Backend ORM already eager-loads `Scenario.hcp_profile → HcpProfile.voice_live_instance` (scenario_service.py:82/133/176) — the data is fetched but the response schema drops it. Frontend gating already reads the nested path (`hcp?.voice_live_instance?.enabled`) which is always undefined, so voice/avatar modes never appear from the scenario flow. This is a serialization-schema fix, not an architecture change.

</domain>

<decisions>
## Implementation Decisions

### HcpProfileSummary target shape (backend)
- **D-01:** Delete ALL four hardcoded flat fields (`avatar_character`, `avatar_style`, `voice_live_enabled`, `avatar_enabled`) from `HcpProfileSummary`. No derived compatibility fields — front-end already reads nested paths.
- **D-02:** Reuse `VoiceLiveInstanceSummary` imported from `backend/app/schemas/voice_live_instance.py` (same pattern as `hcp_profile.py:94-95`) — single source of truth, no local duplicate.
- **D-03:** Summary also gains `avatar_url` and `personality_type` — these are real model columns (hcp_profile.py:20-21) that the summary schema omitted, silently breaking scenario card avatars and personality badges. User confirmed this is a bug ("有但没返回就是错误"). Final shape: `id, name, specialty, avatar_url, personality_type, voice_live_instance_id, voice_live_instance`.

### Frontend types
- **D-04:** Create a frontend `HcpProfileSummary` type matching the backend response exactly; `Scenario.hcp_profile` (frontend/src/types/scenario.ts:26) switches from full `HcpProfile` to it — type honesty so tsc catches misuse of non-returned fields.
- **D-05:** Remove the stray flat `avatar_enabled?: boolean` from `HcpProfile` (frontend/src/types/hcp.ts:28). `avatar_enabled` lives only on `VoiceLiveInstanceSummary`.

### Avatar/voice gating semantics
- **D-06:** Digital-human availability = `features.avatar_enabled && vl.enabled && vl.avatar_enabled`. Frontend gating replaces dead `hcp?.avatar_enabled` reads with `hcp?.voice_live_instance?.avatar_enabled`. Voice availability stays `features.voice_live_enabled && vl.enabled`. Consistent with Phase 29 D-12 (all voice config resolves from VL Instance); both `enabled` and `avatar_enabled` are real columns on the VL model (default True).

### Regression scope
- **D-07:** Re-verify ALL SIX scenario `hcp_profile` consumers, not just the three roadmap-named pages:
  - Pages (mode gating + avatar resolution): `frontend/src/pages/user/training.tsx`, `frontend/src/pages/user/unified-session.tsx`, `frontend/src/pages/user/scenario-group-run.tsx`
  - Components (display fields): `frontend/src/components/admin/scenario-table.tsx`, `frontend/src/components/coach/scenario-card.tsx`, `frontend/src/components/coach/scenario-panel.tsx`
  Type narrowing (D-04) will force all touchpoints through tsc.

### Test strategy
- **D-08:** Backend unit tests: scenario API serialization returns nested VL object + display fields, including the null branch (HCP without VL binding). Frontend unit tests: `getScenarioModes`/`getConferenceModes` gating matrix + affected component render tests. Project standard: 95% coverage.
- **D-09:** E2E: new gating-restoration story (scenario bound to enabled VL shows voice/digital-human mode options on selection/session pages; avatar character/style propagate correctly) PLUS actually re-run existing `voice-avatar-real.spec.ts` real-connection spec as regression. E2E must actually pass (project standard).

### Claude's Discretion
- Whether frontend `HcpProfileSummary` lives in `hcp.ts` or `scenario.ts`
- Whether `VoiceLiveInstanceSummary.avatar_enabled` in frontend types stays optional or becomes required (backend always returns it, default True)
- Exact test file organization and fixture setup

</decisions>

<specifics>
## Specific Ideas

- Target pattern is already established — copy the `hcp_profile.py:94-95` approach (`voice_live_instance_id: str | None` + `voice_live_instance: VoiceLiveInstanceSummary | None` with `from_attributes=True`); the ORM eager-load is already in place, so the backend change is schema-only.
- unified-session.tsx:528/533 already reads `scenario?.hcp_profile?.voice_live_instance?.avatar_character/style` — no frontend change needed there, only verification that values now flow through.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Backend schema & service
- `backend/app/schemas/scenario.py` — `HcpProfileSummary` (L55-67, the fix target) and `ScenarioResponse.hcp_profile` (L81)
- `backend/app/schemas/hcp_profile.py` §L94-95 — Phase 29 target pattern to replicate (`voice_live_instance_id` + nested `voice_live_instance`)
- `backend/app/schemas/voice_live_instance.py` §L120-133 — `VoiceLiveInstanceSummary` to reuse (D-02)
- `backend/app/services/scenario_service.py` §L82/L133/L176 — eager-load already in place (`selectinload(Scenario.hcp_profile).selectinload(HcpProfile.voice_live_instance)`)
- `backend/app/models/hcp_profile.py` §L20-21, L45-46, L58 — `avatar_url`/`personality_type` columns, `voice_live_instance_id` FK, relationship
- `backend/app/models/voice_live_instance.py` §L24, L57 — `enabled` and `avatar_enabled` columns (both default True)

### Frontend types & consumers
- `frontend/src/types/hcp.ts` — stray `avatar_enabled` (L28, delete per D-05), `VoiceLiveInstanceSummary` (L35-44)
- `frontend/src/types/scenario.ts` §L26 — `hcp_profile?: HcpProfile` to narrow (D-04)
- `frontend/src/pages/user/training.tsx` §L25-92 — `getScenarioModes`/`getConferenceModes` gating (D-06 fix target)
- `frontend/src/pages/user/scenario-group-run.tsx` §L27-53 — group-run gating (D-06 fix target)
- `frontend/src/pages/user/unified-session.tsx` §L526-533 — avatar character/style nested reads (verify only)
- `frontend/src/components/admin/scenario-table.tsx` §L164-175, `frontend/src/components/coach/scenario-card.tsx` §L67-115, `frontend/src/components/coach/scenario-panel.tsx` §L39+ — display-field consumers (D-03/D-07)

### Prior decisions & audit
- `.planning/phases/29-voice-live-api-refactor-adaptation-azure-ai-voicelive-sdk-1-/29-CONTEXT.md` — D-09/D-10/D-12 locked decisions this phase propagates
- `.planning/v1.0-MILESTONE-AUDIT.md` — gap definition (scenario API → frontend voice/avatar mode gating; flow F2)

### Existing E2E
- `frontend/e2e/voice-avatar-real.spec.ts` — real-connection regression spec to re-run (D-09)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `VoiceLiveInstanceSummary` (voice_live_instance.py:120-133) — ready to import into scenario.py
- Eager-load chain in scenario_service.py — no query changes needed, serialization-only fix
- Existing E2E voice specs (`voice-avatar-real.spec.ts`, `voice-live-proxy.spec.ts`) — regression baseline

### Established Patterns
- Phase 29 nested-summary pattern (hcp_profile.py:94-95) — exact template for this fix
- Pydantic `ConfigDict(from_attributes=True)` on summaries — ORM relationship serializes automatically once field declared
- Frontend gating already written against nested paths — backend catches up, minimal frontend logic change (only `hcp?.avatar_enabled` → `hcp?.voice_live_instance?.avatar_enabled`)

### Integration Points
- `backend/app/schemas/scenario.py` HcpProfileSummary — single backend change point
- `frontend/src/types/scenario.ts` + `hcp.ts` — type narrowing ripples to all 6 consumers via tsc
- training.tsx / scenario-group-run.tsx gating helpers — the only frontend logic edits

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 30-scenario-api-d10-voicelive-instance-propagation-fix*
*Context gathered: 2026-07-20*
