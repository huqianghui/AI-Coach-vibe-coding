---
phase: 30-scenario-api-d10-voicelive-instance-propagation-fix
reviewed: 2026-07-20T00:00:00Z
depth: standard
files_reviewed: 15
files_reviewed_list:
  - backend/app/api/scenarios.py
  - backend/app/schemas/scenario.py
  - backend/tests/test_avatar_data_consistency.py
  - backend/tests/test_scenario_avatar_fields.py
  - frontend/e2e/training-start-session.spec.ts
  - frontend/src/components/admin/scenario-table.test.tsx
  - frontend/src/components/coach/scenario-card.test.tsx
  - frontend/src/components/coach/scenario-panel.test.tsx
  - frontend/src/pages/user/scenario-group-run.test.tsx
  - frontend/src/pages/user/scenario-group-run.tsx
  - frontend/src/pages/user/training.test.tsx
  - frontend/src/pages/user/training.tsx
  - frontend/src/pages/user/unified-session.test.tsx
  - frontend/src/types/hcp.ts
  - frontend/src/types/scenario.ts
findings:
  critical: 0
  warning: 3
  info: 2
  total: 5
status: issues_found
---

# Phase 30: Code Review Report

**Reviewed:** 2026-07-20T00:00:00Z
**Depth:** standard
**Files Reviewed:** 15
**Status:** issues_found

## Summary

Reviewed the D-10 fix that nests `voice_live_instance: VoiceLiveInstanceSummary | None` on the
scenario API's `hcp_profile` (backend `HcpProfileBrief` / `HcpProfileSummary`) and on the
frontend's `HcpProfileSummary`/`HcpProfile` types, replacing the old hardcoded flat
`avatar_character`/`avatar_style` defaults.

The core propagation fix is correct and well-tested:
- `scenario_service.py` consistently applies
  `selectinload(Scenario.hcp_profile).selectinload(HcpProfile.voice_live_instance)` on every code
  path that returns a `ScenarioOut` (`create_scenario`, `get_scenarios`, `get_scenario`,
  `transition_scenario_status`, `update_scenario`, `clone_scenario` via `_reload_with_hcp`), so
  there is no async lazy-load ("MissingGreenlet") risk and no missing-eager-load regression.
- The unbound/legacy-HCP case (`voice_live_instance_id is None`) is handled gracefully — nested
  field resolves to `null`, not a crash — and is covered by both `test_avatar_data_consistency.py`
  and `test_scenario_avatar_fields.py`.
- Frontend gating in `training.tsx` and `scenario-group-run.tsx` correctly reads
  `hcp?.voice_live_instance?.enabled` / `avatar_enabled` (no more flattened top-level reads), and
  `unified-session.tsx` correctly reads `scenario?.hcp_profile?.voice_live_instance?.avatar_character/avatar_style`.

Three maintainability/correctness concerns worth fixing are documented below (no critical
security or crash-level issues found).

## Warnings

### WR-01: `VoiceLiveInstanceSummary.hcp_count` silently resolves to `0` when nested under scenario responses

**File:** `backend/app/schemas/voice_live_instance.py:131` (field definition), consumed via
`backend/app/api/scenarios.py:36` and `backend/app/schemas/scenario.py:71`

**Issue:** `VoiceLiveInstanceSummary` declares `hcp_count: int = 0`. In `backend/app/api/voice_live.py`
(lines 158-239) this field is populated correctly by explicitly computing
`len(instance.hcp_profiles)` before constructing the response object. However, when the *same*
`VoiceLiveInstanceSummary` schema is reused to validate the nested `hcp_profile.voice_live_instance`
object in the scenario API (`HcpProfileBrief.voice_live_instance` / `HcpProfileSummary.voice_live_instance`,
both `model_config = ConfigDict(from_attributes=True)`), it is populated directly from the raw
`VoiceLiveInstance` ORM object via attribute lookup — and `VoiceLiveInstance` has no `hcp_count`
attribute/property. Pydantic silently falls back to the field default (`0`) instead of erroring,
so every scenario API response will report `hcp_count: 0` for the embedded instance regardless of
how many HCPs are actually assigned to it. This is not currently consumed by the frontend
(`frontend/src/types/hcp.ts::VoiceLiveInstanceSummary` correctly omits `hcp_count`), but it is a
latent data-correctness bug in the API contract that could mislead any future consumer (or a
person debugging via `curl`/API docs) into thinking the value is meaningful.

**Fix:** Either drop `hcp_count` from the schema used for embedding, or introduce a separate lean
schema (e.g. `VoiceLiveInstanceEmbed`) without the aggregate field:
```python
class VoiceLiveInstanceEmbed(BaseModel):
    """Compact VL Instance view for embedding — no aggregate fields that require a query."""
    id: str
    name: str
    voice_live_model: str
    enabled: bool
    voice_name: str
    avatar_character: str
    avatar_style: str
    avatar_enabled: bool = True

    model_config = ConfigDict(from_attributes=True)
```
and use it in `HcpProfileBrief.voice_live_instance` / `HcpProfileSummary.voice_live_instance`
instead of the full `VoiceLiveInstanceSummary`.

### WR-02: Mode-gating logic duplicated across two frontend files, risking future drift

**File:** `frontend/src/pages/user/training.tsx:29-92` (`getScenarioModes`, `getConferenceModes`)
and `frontend/src/pages/user/scenario-group-run.tsx:22-62` (`getAvailableModes`)

**Issue:** The voice/avatar availability rules that this phase depends on
(`features.voice_live_enabled && hcp?.voice_live_instance?.enabled`, and
`... && features.avatar_enabled && hcp?.voice_live_instance?.avatar_enabled`) are implemented
independently in both files. They currently agree, but this is exactly the class of bug D-10
was fixing (avatar gating silently diverging from the actual VL Instance data) — a future change
to one copy (e.g. adding a new feature flag, or changing conference-mode rules) can easily be
applied to only one file and reintroduce a propagation bug that looks identical to the one this
phase fixed.

**Fix:** Extract a single shared utility, e.g. `frontend/src/lib/scenario-modes.ts`:
```typescript
export function getAvailableTrainingModes(
  scenario: Pick<Scenario, "mode" | "hcp_profile"> | null | undefined,
  features: { voice_enabled?: boolean; voice_live_enabled?: boolean; avatar_enabled?: boolean } | undefined,
) { /* single implementation, imported by training.tsx and scenario-group-run.tsx */ }
```
and have both `training.tsx` and `scenario-group-run.tsx` import it instead of maintaining
parallel implementations.

### WR-03: Dead, manually-synced duplicate schemas in `backend/app/schemas/scenario.py`

**File:** `backend/app/schemas/scenario.py:57-99` (`HcpProfileSummary`, `ScenarioResponse`)

**Issue:** `HcpProfileSummary` and `ScenarioResponse` are not used as a `response_model` anywhere
(confirmed: only re-exported via `app/schemas/__init__.py`, never imported/used in
`app/api/scenarios.py` or any router). They duplicate the live `HcpProfileBrief` / `ScenarioOut`
definitions that actually back the API (in `backend/app/api/scenarios.py`). The docstring on
`HcpProfileSummary` even acknowledges this ("NOTE: not used as any router response_model ... Kept
in sync for consistency") — i.e. the codebase already relies on a human remembering to update two
places whenever the nested `voice_live_instance` contract changes. This is precisely the kind of
manual-sync requirement that produced the original D-10 bug (hardcoded flat avatar defaults that
fell out of sync with the real VL Instance data model).

**Fix:** Remove the dead schemas, or make `backend/app/api/scenarios.py::HcpProfileBrief` /
`ScenarioOut` import and reuse the schema types from `app/schemas/scenario.py` (single source of
truth) rather than maintaining two parallel definitions.

## Info

### IN-01: Frontend `Scenario.hcp_profile` type does not account for backend `null`

**File:** `frontend/src/types/scenario.ts:36`

**Issue:** `hcp_profile?: HcpProfileSummary;` only types the field as possibly `undefined`, but
the backend's `ScenarioOut.hcp_profile: HcpProfileBrief | None = None`
(`backend/app/api/scenarios.py:52`) can serialize to JSON `null`. Currently this is benign at
runtime (optional chaining `scenario.hcp_profile?.x` handles both `null` and `undefined`
identically, and `Scenario.hcp_profile_id` is a required, non-nullable column so the field is
effectively always populated in practice), but the type does not accurately reflect the wire
contract.

**Fix:**
```typescript
hcp_profile?: HcpProfileSummary | null;
```

### IN-02: `personality_type` typing is inconsistent between the two frontend HCP types

**File:** `frontend/src/types/scenario.ts:13` vs `frontend/src/types/hcp.ts:8`

**Issue:** `HcpProfileSummary.personality_type` (scenario.ts) is a loose `string`, while
`HcpProfile.personality_type` (hcp.ts) is a literal union
`"friendly" | "skeptical" | "busy" | "analytical" | "cautious"`. Both ultimately describe the same
backend field. Not a bug, but a small drift that weakens type safety on the summary type used
throughout the training/session UI reviewed in this phase.

**Fix:** Reuse `HcpProfile["personality_type"]` in `HcpProfileSummary` for consistency, matching
the pattern already used elsewhere in the codebase (e.g. `HcpProfileCreate["personality_type"]`).

---

_Reviewed: 2026-07-20T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
