---
phase: 27-prompt-optimizer-unified-prompt-management
plan: 06
subsystem: fullstack
tags: [prompt-optimization, rubric, conference, versioning, bicep, container-apps, key-vault]

# Dependency graph
requires:
  - phase: 27-04
    provides: Stateless POST /prompts/optimize endpoint + registry management API
  - phase: 27-05
    provides: Admin prompt optimize dialog UX pattern (mode/diff/adopt)
provides:
  - Shared PromptOptimizeDialog reused by every per-entity prompt editor
  - AI optimize wired into scoring rubric and conference audience prompt templates
  - optimizeText API + useOptimizeText hook + OptimizeText request/response types
  - conference_prompt_version column on scenarios (bumped on config change) exposed via ScenarioOut
  - infra/azure/prompt-optimizer.bicep — internal-ingress Container App + Key Vault secretRef
affects: [admin-prompt-ui, scenario-editor, rubric-editor, azure-infra]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Shared per-entity optimize: PromptOptimizeDialog uses the stateless POST /prompts/optimize endpoint (no registry mutation); parent supplies content and an onAdopt(text) callback that sets its own form field via react-hook-form setValue(..., {shouldDirty:true})"
    - "One reusable dialog (data-testid optimize-mode / optimize-diff / optimized-text / run-optimize / adopt-run) drives the global registry editor, the scoring rubric editor, and the conference audience prompt — no duplicated optimize/diff logic"
    - "Per-entity prompt versioning mirrors rubric_service: bump conference_prompt_version only when the normalized conference_prompt_config actually changes"
    - "Standalone sidecar Bicep: internal ingress (external:false), AGPL image deployed unmodified, secret pulled from Key Vault via user-assigned managed identity (never plaintext)"

key-files:
  created:
    - frontend/src/components/admin/prompt-optimize-dialog.tsx
    - backend/alembic/versions/a7f3c1d92b04_add_conference_prompt_version.py
    - infra/azure/prompt-optimizer.bicep
  modified:
    - frontend/src/types/prompt.ts
    - frontend/src/api/prompts.ts
    - frontend/src/hooks/use-prompts.ts
    - frontend/src/pages/admin/rubric-editor.tsx
    - frontend/src/pages/admin/scenario-editor.tsx
    - backend/app/models/scenario.py
    - backend/app/services/scenario_service.py
    - backend/app/schemas/scenario.py
    - backend/app/api/scenarios.py
    - backend/tests/test_scenarios_api.py
    - frontend/src/pages/admin/rubric-editor.test.tsx
    - frontend/e2e/prompt-management.spec.ts

key-decisions:
  - "The audience prompt template textarea lives in scenario-editor.tsx (conference_prompt_config.audience_prompt_template), NOT conference-audience-config.tsx (which is HCP-member selection only) — the plan's file target was corrected"
  - "The shared dialog uses the stateless /prompts/optimize endpoint rather than the registry optimize/adopt flow: per-entity prompts are not registry templates, so they just receive optimized text and set their own field"
  - "alembic/env.py already imports Scenario and all models — no change needed (plan listed it defensively)"
  - "conference_prompt_version added to ScenarioOut (the actual API response model in app/api/scenarios.py) as well as the ScenarioResponse schema mirror"
  - "prompt-optimizer.bicep is authored as a standalone module (own params for managed environment id, identity, Key Vault uri) so it can be wired into the main deployment without editing container-apps.bicep in this plan"

patterns-established:
  - "Reusable optimize dialog component in components/admin shared across all admin prompt-bearing editors; each editor owns a boolean open-state and an onAdopt that writes to its own form field"

requirements-completed: [PROMPT-05, PROMPT-01]

# Metrics
duration: ~50min
completed: 2026-07-01
---

# Phase 27 Plan 06: Per-Entity Prompt Optimize & Azure Sidecar Summary

**Every admin prompt-bearing editor now shares one AI optimize experience: a reusable `PromptOptimizeDialog` (mode → original-vs-optimized diff → adopt) is wired into the scoring rubric prompt template and the conference audience prompt template, both reusing the stateless `/prompts/optimize` endpoint and the same management UX with no duplicated logic. Scenarios gained a `conference_prompt_version` that bumps only when the conference prompt config actually changes (mirroring rubric versioning), and the open-source prompt-optimizer sidecar is deployable to Azure as an INTERNAL-ingress Container App whose Azure OpenAI key is referenced from Key Vault via managed identity — never plaintext.**

## Performance

- **Duration:** ~50 min
- **Tasks:** 2 (+ blocking human-verify checkpoint)
- **Files:** 15 (3 created, 12 modified)

## Accomplishments
- Created `PromptOptimizeDialog` (`components/admin/prompt-optimize-dialog.tsx`): mode select, iterate-requirements input, two-pane diff, and adopt — driven by the new `useOptimizeText` hook over stateless `POST /prompts/optimize`.
- Added the data layer: `OptimizeTextRequest`/`OptimizeTextResponse` types, `promptsApi.optimizeText`, and the `useOptimizeText` mutation hook.
- Wired an "AI 优化" button + shared dialog into the scoring rubric editor (`prompt_template`) and the scenario/conference audience editor (`conference_prompt_config.audience_prompt_template`); adopt writes the optimized text back into each form field.
- Backend: added `conference_prompt_version` to the Scenario model (+ Alembic migration `a7f3c1d92b04`), bumped it in `scenario_service.update_scenario` only when the normalized config changes, and exposed it on `ScenarioOut` / `ScenarioResponse`.
- Authored `infra/azure/prompt-optimizer.bicep`: internal-ingress Container App running `linshen/prompt-optimizer` unmodified, with `VITE_CUSTOM_API_KEY` as a Key Vault `secretRef` resolved through a user-assigned managed identity.
- **Tests:** backend version-bump test (bumps on change, stable on identical config); frontend rubric-editor optimize tests (opens dialog, adopts optimized text); E2E rubric-optimize story (guarded/skipped offline). All green: 34 frontend unit tests, backend scenario/prompt suites pass, `tsc -b` + `npm run build` clean, E2E 5 passed / 2 optimizer-legs skipped offline.

## Task Commits

1. **Task 1: shared dialog + per-entity integration + scenario version** — `d241688` (feat)
2. **Task 2: Azure sidecar Bicep + optimize tests + E2E** — `77c39be` (test)
3. **Docs: summary + state** — (this docs commit)

## Files

**Created (3):** `frontend/src/components/admin/prompt-optimize-dialog.tsx`, `backend/alembic/versions/a7f3c1d92b04_add_conference_prompt_version.py`, `infra/azure/prompt-optimizer.bicep`

**Modified (12):** prompt types/api/hooks, rubric-editor (+test), scenario-editor, scenario model/service/schema/api, test_scenarios_api, prompt-management E2E.

## Deviations
- **Audience prompt location:** wired the optimize button in `scenario-editor.tsx` (where the `audience_prompt_template` textarea actually lives) instead of the plan's `conference-audience-config.tsx` (which only handles HCP audience-member selection).
- **Stateless endpoint:** the shared dialog uses `POST /prompts/optimize` (no persistence) rather than the registry optimize/adopt flow — per-entity prompts are not registry templates.
- **alembic/env.py:** already imports `Scenario`; no edit required.

## Threat Coverage
- **T-27-16 (no public FQDN):** `prompt-optimizer.bicep` sets `ingress.external: false` — the sidecar is reachable only inside the managed environment.
- **T-27-17 (no plaintext key):** the Azure OpenAI key is a Key Vault `secretRef` resolved via user-assigned managed identity; no key value is embedded.
- **T-27-18 (AGPL unmodified):** the image `linshen/prompt-optimizer` is deployed as-is as a standalone service.

## Self-Check: PASSED
