---
phase: 27-prompt-optimizer-unified-prompt-management
plan: 07
subsystem: prompt-management
tags: [prompts, admin, crud, i18n]
requires:
  - Prompt registry (Phase 27): PromptTemplate/PromptVersion models, prompt_registry service, /prompts API
provides:
  - "POST /prompts create endpoint (admin, 201)"
  - "prompt_registry.create_template service"
  - "PromptCreateRequest schema"
  - "Frontend create dialog on prompt list + useCreatePrompt hook + promptsApi.create"
affects:
  - backend/app/api/prompts.py
  - backend/app/services/prompt_registry.py
  - backend/app/schemas/prompt.py
  - frontend/src/pages/admin/prompts.tsx
tech-stack:
  added: []
  patterns:
    - "Key validation via module-level _KEY_PATTERN regex (lowercase, digits, . _ -)"
    - "create_template creates template (is_system=false) + version_no=1 (source=manual, active) atomically"
    - "409 ConflictException on duplicate key; ValidationException on invalid key"
    - "Create surfaced as a Dialog on the list page (no new route)"
key-files:
  created: []
  modified:
    - backend/app/schemas/prompt.py
    - backend/app/services/prompt_registry.py
    - backend/app/api/prompts.py
    - backend/tests/test_prompt_registry.py
    - backend/tests/test_prompts_management_api.py
    - frontend/src/types/prompt.ts
    - frontend/src/api/prompts.ts
    - frontend/src/hooks/use-prompts.ts
    - frontend/src/pages/admin/prompts.tsx
    - frontend/src/pages/admin/prompts.test.tsx
    - frontend/public/locales/en-US/prompts.json
    - frontend/public/locales/zh-CN/prompts.json
    - frontend/e2e/prompt-management.spec.ts
decisions:
  - "New prompts are non-system (is_system=false) so they remain deletable"
  - "Initial version is source=manual, version_no=1, active"
  - "Create UI is a dialog on the list page rather than a dedicated route"
metrics:
  duration: single session
  completed: 2026-07-01
---

# Phase 27 Plan 07: Create New Prompt Summary

Admins can now create a brand-new custom prompt (key + name + content, plus optional
category/description/variables) directly from the Prompt 管理 list page via a dialog,
backed by a new `POST /prompts` admin endpoint and a `create_template` registry service
that atomically creates the template (non-system) and its active version 1.

## What Was Built

**Backend**
- `PromptCreateRequest` schema (`key`, `name`, `content`, optional `category`,
  `description`, `variables`).
- `prompt_registry.create_template()`: strips/validates the key against
  `_KEY_PATTERN`, rejects duplicates with `ConflictException`, creates a
  `PromptTemplate(is_system=False)` and an active `PromptVersion(version_no=1,
  source="manual")`, wires `active_version_id`, and returns `(template, version)`.
- `POST /prompts` endpoint (admin-gated, 201) returning the full `PromptResponse`.

**Frontend**
- `PromptCreateRequest` type, `promptsApi.create`, `useCreatePrompt` hook.
- "New Prompt" button + create dialog on the list page with field validation,
  409-aware error toast, and navigation to the new prompt's editor on success.
- i18n `create` block + `list.create` added to both `en-US` and `zh-CN`.

## Tests

- Registry unit tests: success, empty-variables default, duplicate-key conflict,
  invalid-key (parametrized), key whitespace stripping.
- API unit tests: 201 detail, duplicate-key conflict, invalid-key, created prompt
  is deletable.
- Backend coverage on changed modules: `prompt_registry.py` 100%, `prompt.py` 100%,
  `prompts.py` 93% (the 7% miss is the pre-existing stateless `/prompts/optimize`
  endpoint, untouched here).
- Frontend vitest: create-and-navigate, submit-disabled-until-required,
  duplicate-key error toast (7/7 pass).
- E2E: "admin creates a brand-new prompt and lands in its editor" (passes).

## Deviations from Plan

None — plan executed as written.

## Deferred Issues

Pre-existing, unrelated backend test failures and formatting drift were discovered
while running the full suite as a pre-commit gate and logged to
`.planning/phases/27-prompt-optimizer-unified-prompt-management/deferred-items.md`
(voice-live/connection-tester tests failing due to an active `az login` in the
environment; docx extractor tests; scenario module formatting). None touch the
prompt modules; all Phase 27 tests pass.

## Commit

- `3705557`: feat(prompts): add create-new-prompt (POST /prompts + list dialog)

## Self-Check: PASSED

- 27-07-SUMMARY.md exists
- Commit 3705557 exists in history
