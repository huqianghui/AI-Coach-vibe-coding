# Phase 30: Scenario API D-10 VoiceLiveInstance Propagation Fix - Research

**Researched:** 2026-07-20
**Domain:** FastAPI/Pydantic response-schema serialization + React/TypeScript type-narrowing (internal bug fix, no new external dependencies)
**Confidence:** HIGH (all findings verified directly against current repo code, not training-data assumptions)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**HcpProfileSummary target shape (backend)**
- **D-01:** Delete ALL four hardcoded flat fields (`avatar_character`, `avatar_style`, `voice_live_enabled`, `avatar_enabled`) from `HcpProfileSummary`. No derived compatibility fields — front-end already reads nested paths.
- **D-02:** Reuse `VoiceLiveInstanceSummary` imported from `backend/app/schemas/voice_live_instance.py` (same pattern as `hcp_profile.py:94-95`) — single source of truth, no local duplicate.
- **D-03:** Summary also gains `avatar_url` and `personality_type` — these are real model columns (hcp_profile.py:20-21) that the summary schema omitted, silently breaking scenario card avatars and personality badges. User confirmed this is a bug ("有但没返回就是错误"). Final shape: `id, name, specialty, avatar_url, personality_type, voice_live_instance_id, voice_live_instance`.

**Frontend types**
- **D-04:** Create a frontend `HcpProfileSummary` type matching the backend response exactly; `Scenario.hcp_profile` (frontend/src/types/scenario.ts:26) switches from full `HcpProfile` to it — type honesty so tsc catches misuse of non-returned fields.
- **D-05:** Remove the stray flat `avatar_enabled?: boolean` from `HcpProfile` (frontend/src/types/hcp.ts:28). `avatar_enabled` lives only on `VoiceLiveInstanceSummary`.

**Avatar/voice gating semantics**
- **D-06:** Digital-human availability = `features.avatar_enabled && vl.enabled && vl.avatar_enabled`. Frontend gating replaces dead `hcp?.avatar_enabled` reads with `hcp?.voice_live_instance?.avatar_enabled`. Voice availability stays `features.voice_live_enabled && vl.enabled`. Consistent with Phase 29 D-12 (all voice config resolves from VL Instance); both `enabled` and `avatar_enabled` are real columns on the VL model (default True).

**Regression scope**
- **D-07:** Re-verify ALL SIX scenario `hcp_profile` consumers, not just the three roadmap-named pages:
  - Pages (mode gating + avatar resolution): `frontend/src/pages/user/training.tsx`, `frontend/src/pages/user/unified-session.tsx`, `frontend/src/pages/user/scenario-group-run.tsx`
  - Components (display fields): `frontend/src/components/admin/scenario-table.tsx`, `frontend/src/components/coach/scenario-card.tsx`, `frontend/src/components/coach/scenario-panel.tsx`
  - Type narrowing (D-04) will force all touchpoints through tsc.

**Test strategy**
- **D-08:** Backend unit tests: scenario API serialization returns nested VL object + display fields, including the null branch (HCP without VL binding). Frontend unit tests: `getScenarioModes`/`getConferenceModes` gating matrix + affected component render tests. Project standard: 95% coverage.
- **D-09:** E2E: new gating-restoration story (scenario bound to enabled VL shows voice/digital-human mode options on selection/session pages; avatar character/style propagate correctly) PLUS actually re-run existing `voice-avatar-real.spec.ts` real-connection spec as regression. E2E must actually pass (project standard).

### Claude's Discretion
- Whether frontend `HcpProfileSummary` lives in `hcp.ts` or `scenario.ts`
- Whether `VoiceLiveInstanceSummary.avatar_enabled` in frontend types stays optional or becomes required (backend always returns it, default True)
- Exact test file organization and fixture setup

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| D-10 propagation (v1.0 audit integration gap, critical) | Scenario API must return nested `voice_live_instance` so scenario-driven voice/avatar training modes resolve again | See "CRITICAL CORRECTION" below for the actual fix location; see "Standard Stack" / "Architecture Patterns" for the exact schema-only change; see "Common Pitfalls" for the six-consumer + test-fixture blast radius |
</phase_requirements>

## Summary

This phase is a pure serialization/type-narrowing fix — no new libraries, no DB migration (Phase 29 already dropped the inline HCP voice/avatar columns and the ORM eager-load is already in place). The fix is entirely: (1) change what shape a Pydantic response schema exposes, and (2) narrow a TypeScript type + fix two `hcp?.avatar_enabled` reads to `hcp?.voice_live_instance?.avatar_enabled`.

**CRITICAL CORRECTION to CONTEXT.md's canonical_refs — read this before planning:** CONTEXT.md names `backend/app/schemas/scenario.py:55-67` (`HcpProfileSummary`) and `ScenarioResponse` as "the fix target." Verified by grep across the entire `backend/app` tree: **neither class is used anywhere as a FastAPI `response_model` or instantiated by any router/service.** They are re-exported in `app/schemas/__init__.py.__all__` and exercised only by `backend/tests/test_scenario_schemas.py` (which tests them as bare Pydantic classes, never through an HTTP call) — otherwise dead code.

The class that **actually serializes every `/api/v1/scenarios*` HTTP response** is a **locally-defined** `HcpProfileBrief` + `ScenarioOut` pair inside `backend/app/api/scenarios.py` (lines 22–123), used via `response_model=ScenarioOut` on every route (lines 126, 137, 160, 176, 188, 199, 262) and `ScenarioOut.model_validate(item)` in list/active endpoints. `backend/app/schemas/scenario_group.py` imports this *same* `ScenarioOut` (`from app.api.scenarios import ScenarioOut`, line 7) for scenario-group-run responses — so fixing `HcpProfileBrief` in `api/scenarios.py` is the **single fix point** that also automatically fixes `scenario-group-run.tsx`'s data source. `backend/tests/test_scenario_avatar_fields.py` (the file that currently proves the bug exists) asserts against `HcpProfileBrief`'s flat fields exactly — confirming this is the real target.

**Practical implication for the planner:** the D-01/D-02/D-03 shape changes must be applied to `HcpProfileBrief` (and `ScenarioOut.resolve_hcp_avatar`) in `backend/app/api/scenarios.py`, not (only) to `backend/app/schemas/scenario.py`. Whether `backend/app/schemas/scenario.py`'s duplicate, unused `HcpProfileSummary`/`ScenarioResponse` should also be updated for consistency, deleted as dead code, or left alone is a planning decision — but leaving it untouched will NOT fix the bug; only `api/scenarios.py` matters for HTTP behavior. Recommendation: update the dead code to match (cheap, keeps `app/schemas/__init__.py` exports honest) OR delete it and its `__all__` entries if no other phase/doc depends on it — either is safe since nothing imports it.

A second, genuinely good-news finding: `HcpProfileBrief.from_hcp_profile()` **already resolves** `avatar_character`/`avatar_style`/`voice_live_enabled`/`avatar_enabled` from the eager-loaded `profile.voice_live_instance` relationship (lines 41–66) — the resolution logic is correct today, it is only exposed in the wrong (flat) shape. The fix is a reshape, not new resolution logic, and can likely be *simpler* than the current code (see Architecture Patterns).

**Primary recommendation:** Rewrite `HcpProfileBrief` in `backend/app/api/scenarios.py` to the D-03 shape (`id, name, specialty, avatar_url, personality_type, voice_live_instance_id, voice_live_instance: VoiceLiveInstanceSummary | None`), importing `VoiceLiveInstanceSummary` from `app.schemas.voice_live_instance`, and let Pydantic v2 `from_attributes=True` resolve the nested object directly from the ORM relationship exactly as `HcpProfileResponse.voice_live_instance` already does in `hcp_profile.py:94-95` — no manual `getattr`/flattening needed. Then fix the two dead `hcp?.avatar_enabled` reads in `training.tsx` and `scenario-group-run.tsx` to `hcp?.voice_live_instance?.avatar_enabled`, narrow `Scenario.hcp_profile`'s type, and update the ~5 test fixtures identified below.

## Standard Stack

No new libraries. This phase uses only what's already in the project.

### Core (already in use, no version changes needed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Pydantic | v2 (per project stack) | `HcpProfileBrief`/`ScenarioOut` response schemas, nested `from_attributes` resolution | Already the project's schema layer; `hcp_profile.py:94-95` is the proven working pattern for this exact nested-summary problem |
| SQLAlchemy 2.0 async | per project stack | `selectinload(Scenario.hcp_profile).selectinload(HcpProfile.voice_live_instance)` — already present in `scenario_service.py:82/133/176` | Eager-load chain requires no changes; this is a serialization-only fix |
| TypeScript strict mode | per `tsconfig.json` | `HcpProfileSummary` type narrowing on `Scenario.hcp_profile` | `noUncheckedIndexedAccess` + strict excess-property checks on object literals will surface every consumer/fixture mismatch automatically (see Common Pitfalls) |

### Alternatives Considered
None — CONTEXT.md already locked the approach (D-01 through D-09); no architecture alternatives are in scope.

**Version verification:** Not applicable — no package.json/pyproject.toml dependency changes in this phase.

## Architecture Patterns

### Pattern 1: Nested-summary-via-from_attributes (the D-02 template)
**What:** Declare a Pydantic field typed as another `BaseModel` with `ConfigDict(from_attributes=True)`; when the source ORM object has an attribute of the same name pointing to a related ORM row (or `None`), Pydantic v2 resolves it automatically — no manual extraction required.
**When to use:** Exactly the HCP → VoiceLiveInstance summary case.
**Example (already working in production today):**
```python
# Source: backend/app/schemas/hcp_profile.py:93-95 (verified in this session)
class HcpProfileResponse(BaseModel):
    ...
    voice_live_instance_id: str | None = None
    voice_live_instance: VoiceLiveInstanceSummary | None = None
    model_config = ConfigDict(from_attributes=True)
```
Apply the identical pattern to `HcpProfileBrief` in `backend/app/api/scenarios.py`:
```python
# Target shape per D-01/D-02/D-03 — verified fix location: backend/app/api/scenarios.py
from app.schemas.voice_live_instance import VoiceLiveInstanceSummary

class HcpProfileBrief(BaseModel):
    id: str
    name: str
    specialty: str = ""
    avatar_url: str = ""
    personality_type: str = "friendly"
    voice_live_instance_id: str | None = None
    voice_live_instance: VoiceLiveInstanceSummary | None = None

    model_config = ConfigDict(from_attributes=True)
```
This lets you **delete** the current `from_hcp_profile()` classmethod's manual `getattr(vl_inst, ...)` flattening (lines 51-66) — Pydantic does it for you once the field is declared, exactly as it already does for `HcpProfileResponse`. Keep (or simplify) the `resolve_hcp_avatar` `field_validator` on `ScenarioOut` only if something in the codebase still constructs `ScenarioOut(hcp_profile=<dict>)` directly (the validator's `isinstance(v, dict)` passthrough branch suggests a caller or test may do this — grep for `ScenarioOut(` / `HcpProfileBrief(` constructor calls before deleting the validator to confirm nothing relies on dict-passthrough).

### Pattern 2: Single fix point fans out through re-exported schema
**What:** `backend/app/schemas/scenario_group.py:7` does `from app.api.scenarios import ScenarioOut` and embeds it directly (`scenario: ScenarioOut | None = None`, lines 66 and 116).
**When to use:** Confirms `scenario-group-run.tsx`'s backend data source is the *same* `ScenarioOut`/`HcpProfileBrief` — fixing `api/scenarios.py` alone covers both the scenario-selection flow and the scenario-group-run flow. No separate backend change needed for group-run.

### Recommended narrow-type addition (frontend, D-04)
```typescript
// New type — location per Claude's Discretion (hcp.ts or scenario.ts)
export interface HcpProfileSummary {
  id: string;
  name: string;
  specialty: string;
  avatar_url: string;
  personality_type: string;
  voice_live_instance_id: string | null;
  voice_live_instance?: VoiceLiveInstanceSummary | null;
}

// frontend/src/types/scenario.ts:26
export interface Scenario {
  ...
  hcp_profile?: HcpProfileSummary;   // was: HcpProfile
  ...
}
```

### Anti-Patterns to Avoid
- **Editing `backend/app/schemas/scenario.py` alone and assuming the bug is fixed:** verified dead code (see Summary) — will not change any HTTP response. Must edit `backend/app/api/scenarios.py::HcpProfileBrief`.
- **Manually flattening/re-deriving VL fields with `getattr` chains:** the whole point of D-02 is to stop doing this; nested `from_attributes` resolution (Pattern 1) is less code and is already proven elsewhere in this codebase.
- **Leaving frontend `HcpProfile` (full type) on `Scenario.hcp_profile`:** defeats D-04's purpose — tsc won't catch a single one of the stale flat-field reads if the wide type stays.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Nested HCP→VL summary serialization | Custom `getattr`/dict-flattening resolver | Pydantic v2 `ConfigDict(from_attributes=True)` + typed nested field | Already the proven pattern at `hcp_profile.py:94-95`; hand-rolled version is what created this bug's flat-shape blind spot in the first place |
| Frontend type safety for the new shape | Ad-hoc `as any` casts at call sites | A dedicated `HcpProfileSummary` interface (D-04) | tsc excess-property + strict-null checks are the actual verification mechanism D-04 relies on |

**Key insight:** The original bug exists precisely *because* someone hand-rolled a flat summary schema instead of reusing the nested `VoiceLiveInstanceSummary` that already existed for the full `HcpProfileResponse`. Don't repeat that mistake in the fix.

## Runtime State Inventory

Not a rename/migration phase — Phase 29 already performed the DB column drop and data migration (D-09 in that phase: "Dropped 14 deprecated inline voice/avatar columns from hcp_profiles, no backfill"). This phase makes no schema/data changes; it only changes what an existing, unmodified set of columns/relationships is serialized as.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — no new columns, no data migration. `voice_live_instance_id` FK and `VoiceLiveInstance` rows are unchanged from Phase 29. | None |
| Live service config | None — no n8n/external service config involved | None |
| OS-registered state | None | None |
| Secrets/env vars | None | None |
| Build artifacts | None — no package/dependency changes | None |

**Nothing found in any category** — verified by reading `backend/app/models/hcp_profile.py` and `backend/app/models/voice_live_instance.py` in this session; both match the post-Phase-29 schema with no pending migration debt relevant to this phase.

## Common Pitfalls

### Pitfall 1: Fixing the wrong (dead) schema file
**What goes wrong:** Editing `backend/app/schemas/scenario.py::HcpProfileSummary`/`ScenarioResponse` per CONTEXT.md's literal canonical_refs, verifying it looks correct, and shipping — with zero effect on the actual API response.
**Why it happens:** CONTEXT.md's canonical_refs cite this file by line number as "the fix target," and the file *looks* plausible (has a `HcpProfileSummary` class matching the bug description almost exactly).
**How to avoid:** Confirmed by grep in this session — `response_model=ScenarioOut` (defined in `backend/app/api/scenarios.py`) is what every scenario route actually returns. Fix `HcpProfileBrief` there. Optionally sync the dead schema file for consistency, but that alone does not close D-10.
**Warning signs:** If `test_scenario_avatar_fields.py` (which hits real HTTP endpoints) still shows flat `avatar_character`/`avatar_style`/`voice_live_enabled`/`avatar_enabled` at the top level of `hcp_profile` after your change, you edited the wrong file.

### Pitfall 2: `test_scenario_avatar_fields.py` currently *asserts the bug's shape as correct*
**What goes wrong:** This existing regression test (`backend/tests/test_scenario_avatar_fields.py`, all 4 test methods) asserts `data["hcp_profile"]["avatar_character"]`, `["voice_live_enabled"]`, `["avatar_enabled"]` as flat top-level keys — i.e., it currently *passes* against the buggy flat shape and *would fail* once D-01 removes those flat fields.
**Why it happens:** It was written to lock in the flat `HcpProfileBrief` shape from an earlier phase, before the nested nested nested requirement existed.
**How to avoid:** This file must be rewritten (not just supplemented) as part of this phase's backend test work — assert `data["hcp_profile"]["voice_live_instance"]["avatar_character"]` etc., add the D-08 null-VL-binding case, and add `avatar_url`/`personality_type` assertions. Treat it as a Wave 0 gap even though the file already exists — its assertions are stale, not just incomplete.

### Pitfall 3: Frontend test fixtures encode the old flat shape and will fail tsc/vitest after D-04
**What goes wrong:** Four test files build `hcp_profile` fixtures matching the OLD full `HcpProfile` type (with flat `avatar_character`/`avatar_style`/`voice_live_enabled`/`avatar_enabled` and/or excess fields like `hospital`, `title`, `emotional_state` that don't exist on the new narrow `HcpProfileSummary`):
- `frontend/src/pages/user/training.test.tsx` — 6 occurrences of literal `hcp_profile: { voice_live_instance: {...}, avatar_enabled: ... }` mixing a partially-nested + partially-flat shape (lines ~217-455)
- `frontend/src/components/coach/scenario-card.test.tsx` — full flat `HcpProfile` literal (lines 24-51) assigned to a typed `const mockScenario: Scenario`
- `frontend/src/components/coach/scenario-panel.test.tsx` — same pattern
- `frontend/src/components/admin/scenario-table.test.tsx` — same pattern
- `frontend/src/pages/user/unified-session.test.tsx` — untyped `mockScenario` object (not type-annotated, so tsc excess-property check won't fire, but its `hcp_profile` fixture is semantically stale: flat `avatar_character`/`avatar_style`/`voice_live_enabled`/`avatar_enabled` at lines 27-36 and 253-254, while the *production* code under test already reads `scenario?.hcp_profile?.voice_live_instance?.avatar_character` — meaning this test currently cannot be verifying real avatar propagation at all)

**Why it happens:** These fixtures were written against `HcpProfile` (the full HCP profile type) before D-04 narrows `Scenario.hcp_profile` to a dedicated summary type; they predate Phase 29's nested VL restructuring for this particular embedding point.
**How to avoid:** Update all 5 fixtures to the new `HcpProfileSummary` shape as part of this phase's frontend test work (not optional — `training.test.tsx`, `scenario-card.test.tsx`, `scenario-panel.test.tsx`, `scenario-table.test.tsx` will fail `tsc -b` immediately once D-04 lands if left as-is; `unified-session.test.tsx` won't fail tsc but is testing dead assertions and should be corrected to actually validate the propagation fix per D-09's intent).
**Warning signs:** `npx tsc -b` errors of the form "Object literal may only specify known properties, and 'hospital' does not exist in type 'HcpProfileSummary'" pinpoint every fixture that needs updating — run this early as a discovery step, don't guess the list by inspection alone.

### Pitfall 4: Coverage threshold is NOT actually 95% today
**What goes wrong:** D-08 states "Project standard: 95% coverage," but the enforced gates are currently lower:
- `backend/pyproject.toml:71` — `--cov-fail-under=89` (with a TODO comment: "raise to 95 per project testing standard once coverage improves")
- `frontend/vitest.config.ts:42-47` — thresholds are `statements: 71, branches: 82, functions: 70, lines: 71` (with an identical TODO comment referencing a Phase 29 baseline)

**Why it happens:** The 95% target is the aspirational project-wide standard (CLAUDE.md / feedback memory), but actual CI-enforced gates were intentionally lowered during Phase 29 pending broader coverage improvement work — this is a known, documented gap, not an oversight.
**How to avoid:** New/changed code in this phase should still be tested to as close to 100% as practical (it's a small, well-isolated surface), but do not assume the phase will fail CI if the *global* percentage doesn't hit exactly 95% — the enforced thresholds are 89% (backend) and 71/82/70/71% (frontend). Do not lower these further; if this phase's changes measurably improve the numbers, consider (as a stretch, not required) nudging the thresholds up to lock in the gain.
**Warning signs:** None — this is informational so the planner doesn't set an incorrect, unenforceable acceptance criterion.

### Pitfall 5: D-13's "voice_live_instance_id required" doesn't guarantee every existing row has one
**What goes wrong:** Assuming the D-08 "null branch" test (HCP without VL binding) is a purely hypothetical/future case and skipping it.
**Why it happens:** Phase 29 D-13 made `voice_live_instance_id` required going forward on create, and Phase 29 D-09 explicitly did NOT backfill when dropping the old inline columns — so pre-existing rows created before D-13's enforcement, or rows whose FK gets manually nulled at the DB level, can still have `voice_live_instance_id = None` / `voice_live_instance = None` today.
**How to avoid:** Keep the D-08-mandated null-VL-binding test case; `HcpProfileBrief.voice_live_instance` must degrade to `None` (not raise) when the relationship is unset — this already works correctly today via the existing `from_hcp_profile`/`getattr(profile, "voice_live_instance", None)` pattern and must continue to work identically after the reshape.

## Code Examples

### Nested resolution — full before/after for the real fix point
```python
# BEFORE (backend/app/api/scenarios.py:22-66, verified current state — flat shape, the bug)
class HcpProfileBrief(BaseModel):
    id: str
    name: str
    specialty: str = ""
    avatar_url: str = ""
    avatar_character: str = "lori"
    avatar_style: str = "casual"
    voice_live_enabled: bool = False
    voice_live_instance_id: str | None = None
    avatar_enabled: bool = False

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_hcp_profile(cls, profile: Any) -> "HcpProfileBrief":
        vl_inst = getattr(profile, "voice_live_instance", None)
        avatar_character = vl_inst.avatar_character if vl_inst else "lori"
        avatar_style = vl_inst.avatar_style if vl_inst else "casual"
        voice_live_enabled = bool(vl_inst.enabled) if vl_inst else False
        avatar_enabled = bool(vl_inst.avatar_enabled) if vl_inst else False
        return cls(
            id=profile.id, name=profile.name, specialty=profile.specialty or "",
            avatar_url=getattr(profile, "avatar_url", "") or "",
            avatar_character=avatar_character, avatar_style=avatar_style,
            voice_live_enabled=voice_live_enabled,
            voice_live_instance_id=getattr(profile, "voice_live_instance_id", None),
            avatar_enabled=avatar_enabled,
        )

# AFTER (D-01/D-02/D-03 target shape — reuses VoiceLiveInstanceSummary, no manual flattening)
from app.schemas.voice_live_instance import VoiceLiveInstanceSummary

class HcpProfileBrief(BaseModel):
    """Lightweight HCP profile embedded in scenario response.

    Voice/avatar config resolves entirely from the linked VoiceLiveInstance
    (Phase 29 D-09/D-10/D-12); Pydantic from_attributes resolves the nested
    relationship automatically, same pattern as HcpProfileResponse
    (app/schemas/hcp_profile.py:94-95).
    """
    id: str
    name: str
    specialty: str = ""
    avatar_url: str = ""
    personality_type: str = "friendly"
    voice_live_instance_id: str | None = None
    voice_live_instance: VoiceLiveInstanceSummary | None = None

    model_config = ConfigDict(from_attributes=True)
```

The `ScenarioOut.resolve_hcp_avatar` field_validator (lines 94-101) can then either be deleted (if nothing constructs `ScenarioOut`/`HcpProfileBrief` from a raw dict — verify via grep before removing) or simplified to just `HcpProfileBrief.model_validate(v)` for the ORM-object branch, since Pydantic now does all the nested resolution.

### Frontend gating fix — the two dead reads (D-06)
```typescript
// frontend/src/pages/user/training.tsx:38-40 (verified current state)
// BEFORE:
const avatarAvailable = Boolean(
  voiceAvailable && features?.avatar_enabled && hcp?.avatar_enabled,
);
// AFTER:
const avatarAvailable = Boolean(
  voiceAvailable && features?.avatar_enabled && hcp?.voice_live_instance?.avatar_enabled,
);

// Same fix applies to the conference-mode branch (training.tsx:70-75) and to
// frontend/src/pages/user/scenario-group-run.tsx:37-44 (both the f2f and
// conference branches of getAvailableModes there read the same dead `hcp?.avatar_enabled`)
```
`frontend/src/pages/user/unified-session.tsx:526-533` requires **no code change** — it already reads `scenario?.hcp_profile?.voice_live_instance?.avatar_character` / `.avatar_style`; it was silently getting `undefined` because the backend never sent `voice_live_instance` at all. Verification-only for that file, per CONTEXT.md's "specifics" note.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Inline flat voice/avatar columns directly on `HcpProfile` | Voice/avatar config lives exclusively on `VoiceLiveInstance`, referenced via FK | Phase 29 (D-09, this session's STATE.md) | This phase is the final propagation step of that Phase 29 migration — `scenario.py`'s response schemas were the one serialization surface left behind |
| `HcpProfileBrief` manually flattening VL fields via `getattr` | Direct nested `VoiceLiveInstanceSummary` via Pydantic `from_attributes` | This phase (proposed) | Matches the pattern already used successfully for the full `HcpProfileResponse` (Phase 29) |

**Deprecated/outdated:** The flat `avatar_character`/`avatar_style`/`voice_live_enabled`/`avatar_enabled` fields on any HCP-related response schema — Phase 29 already established the nested-only convention; this phase closes the one remaining holdout.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Nothing in the codebase constructs `ScenarioOut`/`HcpProfileBrief` with `hcp_profile` as a raw dict (so the `resolve_hcp_avatar` validator's dict-passthrough branch could be simplified/removed) | Code Examples | If something does (e.g., a currently-untested code path), removing the dict branch could break silently; mitigate by grepping for `HcpProfileBrief(` / `ScenarioOut(hcp_profile=` constructor calls before deleting, or simply keep the validator and just change what it constructs |

**Only one assumption** — everything else in this research (the dead-schema-file finding, the actual `response_model` wiring, the eager-load presence, the exact frontend gating reads, the test-fixture blast radius, the real coverage thresholds) was verified directly by reading the current repository state in this session, not inferred from training knowledge.

## Open Questions

1. **Should `backend/app/schemas/scenario.py`'s unused `HcpProfileSummary`/`ScenarioResponse` be updated to match, or deleted?**
   - What we know: Confirmed dead code — not used as any `response_model`, not imported by any router/service, only referenced in `app/schemas/__init__.py.__all__` and tested in isolation by `test_scenario_schemas.py`.
   - What's unclear: Whether a future phase or external doc expects these names to exist/match reality.
   - Recommendation: Cheapest safe option is to update it to mirror the new `api/scenarios.py` shape (consistency, ~2 min of work) rather than delete — avoids any risk of breaking an unseen import, and keeps `app/schemas/__init__.py`'s public API honest. Flag as a discretionary call for the plan, not a blocker.

2. **Should the `resolve_hcp_avatar` field_validator's dict-passthrough branch be removed?**
   - What we know: It exists today (`isinstance(v, dict)` early-return) and its presence implies some caller may pass a plain dict for `hcp_profile` rather than an ORM object.
   - What's unclear: Which caller, if any — not found via search in this session's scope.
   - Recommendation: Grep for direct `ScenarioOut(` / `HcpProfileBrief(` constructor invocations as a first task action before touching the validator; keep the passthrough if any hit is found, otherwise simplify per Code Examples.

## Environment Availability

Skipped — this phase has no external tool/service/runtime dependencies beyond the project's existing Python/Node toolchain (no new packages, no Azure services touched).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Backend framework | pytest + pytest-asyncio, httpx `AsyncClient` against the FastAPI app (see `backend/tests/conftest.py`, `test_scenario_avatar_fields.py`) |
| Backend config file | `backend/pyproject.toml` (`[tool.pytest.ini_options]`) |
| Frontend framework | Vitest 3.x + @testing-library/react |
| Frontend config file | `frontend/vitest.config.ts` |
| E2E framework | Playwright, config `frontend/e2e/playwright.config.ts` |
| Quick backend run | `cd backend && pytest tests/test_scenario_avatar_fields.py tests/test_scenario_schemas.py tests/test_hcp_profiles_api.py -v` |
| Quick frontend run | `cd frontend && npx vitest run src/pages/user/training.test.tsx src/components/coach/scenario-card.test.tsx src/components/coach/scenario-panel.test.tsx src/components/admin/scenario-table.test.tsx src/pages/user/unified-session.test.tsx` |
| Full backend suite | `cd backend && pytest -v` (enforces `--cov-fail-under=89`) |
| Full frontend suite | `cd frontend && npm run test:coverage && npx tsc -b` |
| Full E2E (this phase's scope) | `cd frontend && npx playwright test --config=e2e/playwright.config.ts scenario-selection.spec.ts voice-avatar-real.spec.ts` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| D-10 (backend shape) | `GET /api/v1/scenarios/{id}` returns nested `hcp_profile.voice_live_instance` object (not flat fields), plus `avatar_url`/`personality_type` | unit/integration | `pytest tests/test_scenario_avatar_fields.py -x` | ✅ exists, needs rewrite (Pitfall 2) |
| D-10 (backend null branch) | HCP with `voice_live_instance_id=None` serializes `hcp_profile.voice_live_instance: null` without error | unit/integration | `pytest tests/test_scenario_avatar_fields.py::TestScenarioAvatarFields -x` (new test method) | ❌ Wave 0 — add new test method |
| D-06 (frontend gating: training.tsx) | `getScenarioModes`/`getConferenceModes` return correct mode list when `hcp.voice_live_instance.avatar_enabled` is true/false/undefined | unit | `npx vitest run src/pages/user/training.test.tsx` | ✅ exists, fixtures need update (Pitfall 3) |
| D-06 (frontend gating: scenario-group-run.tsx) | `getAvailableModes` same matrix for f2f + conference branches | unit | No dedicated test file today | ❌ Wave 0 — create `scenario-group-run.test.tsx` or extend existing hook tests |
| D-03 (display fields propagate) | `scenario-card.tsx`/`scenario-panel.tsx`/`scenario-table.tsx` render `avatar_url`/`personality_type`/`specialty` from the narrowed type | unit | `npx vitest run src/components/coach/scenario-card.test.tsx src/components/coach/scenario-panel.test.tsx src/components/admin/scenario-table.test.tsx` | ✅ exist, fixtures need update (Pitfall 3) |
| D-04 (type honesty) | `Scenario.hcp_profile` narrowed; `tsc -b` passes with zero suppressions | type-check | `cd frontend && npx tsc -b` | N/A — compiler check, not a test file |
| D-09 (avatar propagation E2E) | Digital-human mode selection propagates `avatar_character`/`avatar_style` end-to-end via unified-session | e2e | New scenario in `scenario-selection.spec.ts` or new spec file | ❌ Wave 0 — new E2E story |
| D-09 (regression) | Existing real-connection voice+avatar flow still works | e2e (integration-marked, requires real Azure creds) | `npx playwright test --config=e2e/playwright.config.ts voice-avatar-real.spec.ts` | ✅ exists — re-run, no changes expected needed (uses HCP-direct endpoint, already nested) |

### Sampling Rate
- **Per task commit:** targeted quick backend/frontend commands above for the file(s) touched
- **Per wave merge:** `pytest -v` (backend) + `npm run test:coverage && npx tsc -b` (frontend)
- **Phase gate:** Full backend + frontend suites green, `tsc -b` clean, `voice-avatar-real.spec.ts` + new gating-restoration E2E spec both passing before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] Rewrite `backend/tests/test_scenario_avatar_fields.py` assertions to the nested shape (currently asserts the buggy flat shape — see Pitfall 2)
- [ ] Add backend test method for the null-VL-binding branch (D-08)
- [ ] Update fixtures in `frontend/src/pages/user/training.test.tsx`, `frontend/src/components/coach/scenario-card.test.tsx`, `frontend/src/components/coach/scenario-panel.test.tsx`, `frontend/src/components/admin/scenario-table.test.tsx`, `frontend/src/pages/user/unified-session.test.tsx` to the new `HcpProfileSummary` shape (see Pitfall 3)
- [ ] New/extended test coverage for `scenario-group-run.tsx`'s `getAvailableModes` gating (no dedicated test file exists today)
- [ ] New E2E "gating-restoration" spec per D-09 (scenario bound to enabled VL → voice/digital-human options appear; avatar character/style propagate)

## Security Domain

security_enforcement not explicitly disabled in `.planning/config.json` — treated as enabled. This phase's surface is narrow: no new input-validation boundary (no new user-supplied fields; `HcpProfileBrief`/`HcpProfileSummary` are output-only response fields resolved server-side from already-trusted DB relationships), no new auth boundary (existing `get_current_user`/`require_role("admin")` dependencies on the scenario routes are unchanged).

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | No change | Existing JWT bearer auth (`get_current_user`) on scenario routes, untouched |
| V4 Access Control | No change | Existing `require_role("admin")` on create/update/delete/list/clone; `get_current_user` on read/active — untouched by this phase |
| V5 Input Validation | N/A | No new request-body fields; this phase only changes *response* shape |
| V6 Cryptography | N/A | Not touched |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| Over-exposure of internal fields via response schema | Information Disclosure | `HcpProfileSummary`/`HcpProfileBrief` remains an explicit allow-list schema (Pydantic `BaseModel` with named fields) rather than dumping the full ORM object — this phase's D-03 additions (`avatar_url`, `personality_type`) are already-public display fields shown in the UI today via the full `HcpProfile` type, so no new disclosure risk |

## Sources

### Primary (HIGH confidence — verified by direct code inspection in this session)
- `backend/app/api/scenarios.py` (full file read) — actual `HcpProfileBrief`/`ScenarioOut` response model, the real fix location
- `backend/app/schemas/scenario.py`, `backend/app/schemas/hcp_profile.py`, `backend/app/schemas/voice_live_instance.py` (full files read) — confirmed dead-code schema vs. reusable `VoiceLiveInstanceSummary` pattern
- `backend/app/models/hcp_profile.py`, `backend/app/models/voice_live_instance.py` (full files read) — confirmed real columns (`avatar_url`, `personality_type`) and FK/relationship wiring
- `backend/app/services/scenario_service.py`, `backend/app/services/scenario_group_service.py` (full/grep read) — confirmed eager-load already present; confirmed `ScenarioOut` re-import in `scenario_group.py`
- `backend/tests/test_scenario_avatar_fields.py`, `backend/tests/test_scenario_schemas.py` (full files read) — confirmed which test proves the bug and which tests dead code
- `frontend/src/types/hcp.ts`, `frontend/src/types/scenario.ts` (full files read) — confirmed stray `avatar_enabled` and current wide `hcp_profile?: HcpProfile` typing
- `frontend/src/pages/user/training.tsx`, `frontend/src/pages/user/scenario-group-run.tsx`, `frontend/src/pages/user/unified-session.tsx` (relevant sections read) — confirmed exact gating reads and line numbers
- `frontend/src/components/admin/scenario-table.tsx`, `frontend/src/components/coach/scenario-card.tsx`, `frontend/src/components/coach/scenario-panel.tsx` (grep-confirmed) — confirmed which display fields each reads
- `frontend/src/pages/user/training.test.tsx`, `frontend/src/components/coach/scenario-card.test.tsx`, `frontend/src/components/coach/scenario-panel.test.tsx`, `frontend/src/components/admin/scenario-table.test.tsx`, `frontend/src/pages/user/unified-session.test.tsx` (grep + partial read) — confirmed stale fixture shapes
- `frontend/e2e/voice-avatar-real.spec.ts`, `frontend/e2e/scenario-selection.spec.ts` (partial read) — confirmed existing E2E baseline and that the real-connection spec already models the nested type correctly (it queries HCP profiles directly, not through scenarios)
- `backend/pyproject.toml`, `frontend/vitest.config.ts` (grep-confirmed) — actual enforced coverage thresholds (89% backend; 71/82/70/71% frontend), correcting the "95%" figure in D-08
- `.planning/config.json` — `workflow.nyquist_validation: true` (Validation Architecture section required), no `security_enforcement: false` override

### Secondary / Tertiary
None used — this phase required no web search or Context7 lookups; it is a fully internal, codebase-verifiable fix with no external library or API surface.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new libraries; existing patterns verified directly in repo
- Architecture: HIGH — the `from_attributes` nested-resolution pattern is copied from working production code (`hcp_profile.py:94-95`), not a novel design
- Pitfalls: HIGH — every pitfall (dead schema file, stale test assertions, stale fixtures, actual coverage thresholds) was discovered by direct grep/read in this session, not inferred

**Research date:** 2026-07-20
**Valid until:** Until the next change to `backend/app/api/scenarios.py`, `backend/app/schemas/scenario.py`, or the six named frontend consumers — this research is tied to exact current line numbers/content, not a time-based staleness window.
