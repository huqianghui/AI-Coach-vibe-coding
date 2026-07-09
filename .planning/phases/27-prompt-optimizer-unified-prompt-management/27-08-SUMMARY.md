---
phase: 27-prompt-optimizer-unified-prompt-management
plan: 08
subsystem: prompt-management
tags: [prompts, admin, versions, i18n, read-only]
requires:
  - "27-07: create-new-prompt feature (list dialog + POST /prompts)"
  - "Prompt registry (Phase 27): GET /prompts/{key}/versions returns content per version"
provides:
  - "Per-version 'View content' action on the prompt detail page"
  - "Read-only version content dialog (does not mutate editor state)"
affects:
  - frontend/src/pages/admin/prompt-editor.tsx
tech-stack:
  added: []
  patterns:
    - "Reuse usePromptVersions data (content already included) — no backend change"
    - "Read-only viewer state (viewVersion) kept separate from editor content state"
key-files:
  created: []
  modified:
    - frontend/src/pages/admin/prompt-editor.tsx
    - frontend/src/pages/admin/prompt-editor.test.tsx
    - frontend/public/locales/en-US/prompts.json
    - frontend/public/locales/zh-CN/prompts.json
    - frontend/e2e/prompt-management.spec.ts
decisions:
  - "Historical content shown in a read-only dialog (pre, whitespace-pre-wrap), not inline expander"
  - "Viewer never calls setContent, so the active version and editor stay untouched"
metrics:
  duration: single session
  completed: 2026-07-01
---

# Phase 27 Plan 08: View Historical Version Content Summary

Admins can now read the full text of any historical prompt version from the detail
page. Each version row in the history list gains an Eye-icon "View content" action
that opens a read-only dialog rendering that version's content plus its source/note,
without touching the editor's active content.

## What Was Built

- `prompt-editor.tsx`: added `viewVersion` state and a per-row "View content" button
  (`data-testid="version-view-${version_no}"`), alongside the existing rollback
  button. A read-only `Dialog` (open when `viewVersion !== null`) renders the
  version's content in a `<pre>` (`data-testid="version-view-content"`,
  whitespace-pre-wrap, scrollable) with source/note in the description and a single
  Close button. The viewer never calls `setContent`.
- i18n: `editor.viewContent`, `editor.versionContentTitle`, `editor.close` added to
  both `en-US` and `zh-CN`.

## Tests

- Unit (vitest): viewing v1 shows "ORIGINAL SEED CONTENT" in the viewer while the
  editable textarea still holds the active v2 content (6/6 pass).
- Typecheck (`tsc -b`) and production build clean.
- E2E: "admin views a historical version's content read-only without altering the
  editor" — saves a v2, opens v1 viewer, asserts content visible/non-empty, closes
  via Escape, and asserts the editor textarea value is unchanged. Full
  prompt-management spec: 7 passed, 2 skipped (optimizer-adapter-gated).

## Deviations from Plan

None — plan executed as written. (E2E dialog close uses `Escape` instead of matching
the localized Close label, since the E2E build renders real i18n strings rather than
raw keys.)

## Commit

- `97eb902`: feat(prompts): view historical version content on detail page

## Self-Check: PASSED

- 27-08-SUMMARY.md exists
- Commit 97eb902 exists in history
