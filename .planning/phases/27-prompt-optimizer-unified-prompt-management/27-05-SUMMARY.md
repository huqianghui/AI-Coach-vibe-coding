---
phase: 27-prompt-optimizer-unified-prompt-management
plan: 05
subsystem: frontend
tags: [prompt-management, admin-ui, i18n, tanstack-query, versioning, optimization]

# Dependency graph
requires:
  - phase: 27-04
    provides: Registry-backed /prompts management REST API (list/detail/versions/runs/PUT/activate/optimize/adopt/delete)
provides:
  - Admin Prompt management data layer (types, axios API module, TanStack Query hooks)
  - Prompt list page (all registered prompts, active version, last-optimized)
  - Prompt editor page (edit content, save versioned edit, AI optimize with diff, adopt, version history + rollback)
  - "Prompt 管理" sidebar nav entry and /admin/prompts routes under AdminRoute
  - prompts + nav i18n namespaces (zh-CN, en-US)
affects: [27-06, admin-prompt-ui]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Domain data layer split: src/types/prompt.ts (interfaces) + src/api/prompts.ts (promptsApi object over apiClient) + src/hooks/use-prompts.ts (query + mutation hooks) — no inline useQuery in components"
    - "Mutation hooks share a private useInvalidatePrompt(key) onSuccess that invalidates the ['prompts'] query tree"
    - "Editor drives optimize via a Dialog: run-optimize mutation onSuccess stores {runId, text}; a two-pane diff renders original (local content) vs optimized (run result); adopt promotes the run"
    - "Prompt text edited/rendered only through a controlled <Textarea> and React-escaped <pre> blocks — no dangerouslySetInnerHTML"

key-files:
  created:
    - frontend/src/types/prompt.ts
    - frontend/src/api/prompts.ts
    - frontend/src/hooks/use-prompts.ts
    - frontend/src/pages/admin/prompts.tsx
    - frontend/src/pages/admin/prompt-editor.tsx
    - frontend/public/locales/zh-CN/prompts.json
    - frontend/public/locales/en-US/prompts.json
    - frontend/src/pages/admin/prompts.test.tsx
    - frontend/src/pages/admin/prompt-editor.test.tsx
    - frontend/e2e/prompt-management.spec.ts
  modified:
    - frontend/src/i18n/index.ts
    - frontend/public/locales/zh-CN/nav.json
    - frontend/public/locales/en-US/nav.json
    - frontend/src/components/layouts/admin-layout.tsx
    - frontend/src/router/index.tsx

key-decisions:
  - "Locale files live in frontend/public/locales/{zh-CN,en-US}/ (HttpBackend loadPath), not the plan's frontend/src/locales/zh|en — adapted to the actual i18n setup; the 'prompts' namespace was appended to the i18n ns array"
  - "Sidebar nav uses the MessageSquare lucide icon for Prompt 管理 (FileText already used by training materials)"
  - "Prompt list rendered as a plain sortable-free table (data-testid rows) — matches existing admin list pages; no pagination since the registry set is small/bounded"

patterns-established:
  - "Admin CRUD-with-AI page pattern: list page navigates by row testid to an editor keyed by :key; editor composes read hooks + save/activate/optimize/adopt mutations with toast feedback"

requirements-completed: [PROMPT-05, PROMPT-04, PROMPT-03]

# Metrics
duration: ~45min
completed: 2026-06-10
---

# Phase 27 Plan 05: Prompt Management Admin UI Summary

**Admins now have a "Prompt 管理" area in the admin console: a list of every registered prompt (with active version and last-optimized timestamp) that opens into an editor where they can edit and save a new prompt version, run the AI optimizer and review an original-vs-optimized diff, adopt the optimized result as a new active version, and browse the full version history with one-click rollback — all fully internationalized (zh-CN + en-US) and backed by dedicated TanStack Query hooks (no inline `useQuery` in components), with prompt text handled only through React-escaped inputs.**

## Performance

- **Duration:** ~45 min
- **Tasks:** 3
- **Files:** 15 (10 created, 5 modified)

## Accomplishments
- Built the data layer: `types/prompt.ts` (Prompt/PromptVersion/PromptSummary/PromptRun + request types), `api/prompts.ts` (`promptsApi` over the shared axios client), and `hooks/use-prompts.ts` (8 hooks: 4 queries + 4 mutations sharing a cache-invalidation `onSuccess`).
- Created the list page (`prompts.tsx`) and editor page (`prompt-editor.tsx`): edit content, save versioned edit, AI-optimize dialog with mode selection, original-vs-optimized diff, adopt, and version history with rollback.
- Added the "Prompt 管理" sidebar entry and `/admin/prompts` + `/admin/prompts/:key` routes under the `AdminRoute` guard, plus the `prompts` and updated `nav` i18n namespaces for both locales.
- **9 vitest unit tests** (4 list + 5 editor) all green, plus a Playwright E2E covering the admin user story (**5 passed, 1 optimizer-leg skipped offline**); `tsc -b` and `npm run build` clean.

## Task Commits

1. **Task 1 + Task 2: Data layer, pages, nav, routes, i18n** - `ad046c9` (feat)
2. **Task 3: Unit + E2E tests** - `acbc9cd` (test)

**Plan metadata:** _(this docs commit)_

## Files Created/Modified
- `frontend/src/types/prompt.ts` *(created)* — TypeScript interfaces mirroring the 27-04 response schemas.
- `frontend/src/api/prompts.ts` *(created)* — `promptsApi`: list, get, versions, runs, saveVersion (PUT), activateVersion, optimize, adoptRun.
- `frontend/src/hooks/use-prompts.ts` *(created)* — query + mutation hooks; `enabled: !!key` guards; shared `useInvalidatePrompt`.
- `frontend/src/pages/admin/prompts.tsx` *(created)* — prompt list table; row click → editor.
- `frontend/src/pages/admin/prompt-editor.tsx` *(created)* — editor with save / optimize-diff-adopt / version-history-rollback.
- `frontend/public/locales/{zh-CN,en-US}/prompts.json` *(created)* — `prompts` namespace strings.
- `frontend/src/pages/admin/prompts.test.tsx`, `prompt-editor.test.tsx` *(created)* — vitest coverage.
- `frontend/e2e/prompt-management.spec.ts` *(created)* — Playwright user-story E2E.
- `frontend/src/i18n/index.ts` *(modified)* — added `prompts` to the `ns` array.
- `frontend/public/locales/{zh-CN,en-US}/nav.json` *(modified)* — added `prompts` label.
- `frontend/src/components/layouts/admin-layout.tsx` *(modified)* — `MessageSquare` nav item.
- `frontend/src/router/index.tsx` *(modified)* — lazy routes for list + editor.

## Deviations from Plan

### Auto-fixed Issues
None affecting behavior.

### Design Decisions

**1. [Rule 1 - Reality alignment] Locale files under `public/locales/{zh-CN,en-US}/`**
- **Reason:** The plan referenced `frontend/src/locales/zh|en/*.json`, but the project's i18n uses `i18next-http-backend` with `loadPath: /locales/{{lng}}/{{ns}}.json`, so translations live in `frontend/public/locales/{zh-CN,en-US}/`. Adapted to the actual setup and registered the `prompts` namespace in the i18n `ns` array.

**2. [Rule 1 - Consistency] `MessageSquare` nav icon**
- **Reason:** The plan didn't specify an icon; `FileText` is already used by Training Materials, so `MessageSquare` (lucide) distinguishes the Prompt 管理 entry.

**3. [Environment] E2E optimizer leg skipped offline**
- **Reason:** Port 8000 on the dev host is held by an unrelated root-owned Docker container, so the E2E was run against our own stack on alternate ports (8100/5273) via a throwaway config (not committed). The optimize→diff→adopt→rollback leg is `test.skip`-guarded when the optimizer adapter has no network — 5 specs pass and that leg skips gracefully. In CI (fresh port 8000, configured adapter) it exercises fully.

## Threat Coverage
- **T-27-14 (routes behind admin guard):** mitigated — `/admin/prompts` and `/admin/prompts/:key` are registered under the `AdminRoute`-guarded `/admin` route subtree in `router/index.tsx`.
- **T-27-15 (no HTML injection from prompt text):** mitigated — prompt content is only ever bound to a controlled `<Textarea>` and rendered in React-escaped `<pre>` diff panes; no `dangerouslySetInnerHTML`. Verified by the `plain text (no HTML injection)` E2E assertion (content element is a `textarea`).

## Self-Check: PASSED
- `frontend/src/types/prompt.ts` — FOUND
- `frontend/src/api/prompts.ts` — FOUND
- `frontend/src/hooks/use-prompts.ts` — FOUND
- `frontend/src/pages/admin/prompts.tsx` — FOUND
- `frontend/src/pages/admin/prompt-editor.tsx` — FOUND
- `frontend/src/pages/admin/prompts.test.tsx` — FOUND (4 tests)
- `frontend/src/pages/admin/prompt-editor.test.tsx` — FOUND (5 tests)
- `frontend/e2e/prompt-management.spec.ts` — FOUND (5 pass, 1 skip)
- Commit `ad046c9` (feat) — FOUND
- Commit `acbc9cd` (test) — FOUND
- `tsc -b` clean, `npm run build` clean, 9/9 unit tests green
