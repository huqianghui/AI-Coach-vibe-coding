---
phase: 30-scenario-api-d10-voicelive-instance-propagation-fix
fixed_at: 2026-07-20T16:10:00Z
review_path: .planning/phases/30-scenario-api-d10-voicelive-instance-propagation-fix/30-REVIEW.md
iteration: 1
findings_in_scope: 3
fixed: 3
skipped: 0
status: all_fixed
---

# Phase 30: Code Review Fix Report

**Fixed at:** 2026-07-20T16:10:00Z
**Source review:** .planning/phases/30-scenario-api-d10-voicelive-instance-propagation-fix/30-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 3 (fix_scope = critical_warning; REVIEW.md reported 0 Critical, 3 Warning, 2 Info -- the 2 Info findings, IN-01 and IN-02, were out of scope and left untouched)
- Fixed: 3
- Skipped: 0

## Fixed Issues

### WR-01: `VoiceLiveInstanceSummary.hcp_count` silently resolves to `0` when nested under scenario responses

**Files modified:** `backend/app/schemas/voice_live_instance.py`
**Commit:** `6acc1fb`
**Applied fix:** Removed the `hcp_count: int = 0` field from `VoiceLiveInstanceSummary` (the schema
used exclusively for embedding under `hcp_profile.voice_live_instance` in the scenario and HCP
profile APIs, validated directly from the raw ORM object via `from_attributes`). Confirmed via
grep that `VoiceLiveInstanceSummary` is never used as a list-view/aggregate response anywhere in
the backend (list views actually use `VoiceLiveInstanceResponse`, which correctly computes
`hcp_count` explicitly in `app/api/voice_live.py`), so dropping the field is a clean fix rather
than introducing a second lean schema. Updated the class docstring to explain why aggregate
fields must not be added back. Verified no test asserts on a nested `hcp_count` value and no code
constructs `VoiceLiveInstanceSummary(...)` with an explicit `hcp_count` kwarg.
**Verification:** `ruff check`/`ruff format --check` pass; targeted pytest run (`test_avatar_data_consistency.py`,
`test_scenario_avatar_fields.py`, `test_voice_live_instance.py`, `test_hcp_profiles_api.py`,
`test_scenarios_api.py`) — 85 passed, 1 skipped.

### WR-02: Mode-gating logic duplicated across two frontend files, risking future drift

**Files modified:** `frontend/src/lib/scenario-modes.ts` (new), `frontend/src/pages/user/training.tsx`,
`frontend/src/pages/user/scenario-group-run.tsx`, `frontend/src/pages/user/training.test.tsx`
**Commit:** `8f92c8c`
**Applied fix:** Extracted the single canonical `getAvailableModes(scenario, features)` implementation
(previously only in `scenario-group-run.tsx`, which already handled both f2f and conference mode
branches) into a new `frontend/src/lib/scenario-modes.ts` module. Removed `training.tsx`'s two
duplicate implementations (`getScenarioModes`, `getConferenceModes`) and had it import the shared
function instead. `scenario-group-run.tsx` now imports from the shared module and re-exports
`getAvailableModes` for backward compatibility with its existing test import path
(`import { getAvailableModes } from "./scenario-group-run"`).

**Behavior change surfaced during unification (flagging for human review):** the two prior
implementations had already silently diverged on `defaultMode` ordering for the *conference*
scenario case when both voice and digital-human modes are available: `training.tsx`'s
`getConferenceModes` defaulted to `voice_realtime_model` (voice-first), while
`scenario-group-run.tsx`'s `getAvailableModes` defaulted to `digital_human_realtime_model`
(avatar-first) -- this is exactly the drift risk the finding warned about, now confirmed to have
already occurred. The unified implementation keeps the avatar-first behavior (consistent with the
f2f case and with `scenario-group-run.tsx`'s existing, tested behavior). Updated the one
`training.test.tsx` assertion that encoded the old voice-first conference default
(`"allows digital human mode on avatar-capable conference scenario cards"`) to match the unified
avatar-first behavior, with an inline comment explaining the change.
**Verification:** `npx tsc -b` — no errors. `npx vitest run src/pages/user/training.test.tsx
src/pages/user/scenario-group-run.test.tsx` — 28/28 passed.
**Status: fixed: requires human verification** — the `defaultMode` ordering choice for
conference mode (avatar-first vs. voice-first) is a product/UX decision, not purely mechanical
deduplication. Please confirm avatar-first is the intended default for conference scenarios with
both voice and digital-human available.

### WR-03: Dead, manually-synced duplicate schemas in `backend/app/schemas/scenario.py`

**Files modified:** `backend/app/schemas/scenario.py`, `backend/app/schemas/__init__.py`,
`backend/tests/test_scenario_schemas.py`, `backend/tests/test_schemas_phase2.py`
**Commit:** `1205ff9`
**Applied fix:** Removed the unused `HcpProfileSummary` and `ScenarioResponse` classes from
`backend/app/schemas/scenario.py` (confirmed via grep: never used as a `response_model`, never
imported outside `app/schemas/__init__.py` re-export and two schema-only unit test files) along
with their now-unneeded `VoiceLiveInstanceSummary`/`ConfigDict`/`datetime` imports. Removed the
`ScenarioResponse` import/export from `app/schemas/__init__.py`. Removed the corresponding
`TestScenarioResponse` class in `test_scenario_schemas.py` and `TestScenarioResponseSchema` class
in `test_schemas_phase2.py` that directly exercised the deleted dead schema, replacing each with a
short comment pointing to where the *live* `ScenarioOut`/`HcpProfileBrief` contract (in
`app/api/scenarios.py`) is actually covered (`test_scenarios_api.py`, `test_scenario_avatar_fields.py`).
Grep-confirmed no remaining references to `ScenarioResponse` or the removed `HcpProfileSummary` in
the backend.
**Verification:** `ruff check`/`ruff format --check` pass; targeted pytest run (schema tests +
scenarios/HCP-profile/avatar-consistency API tests) — 97 passed, 2 warnings (pre-existing pydantic
deprecation, unrelated). Two independent full-backend-suite runs during this session showed no
failures attributable to these files (one run showed a single flaky failure in
`test_agent_chat_service.py`, a real-API test with no import of any touched schema, not reproduced
on rerun).

## Skipped Issues

None — all in-scope findings were fixed.

---

_Fixed: 2026-07-20T16:10:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
