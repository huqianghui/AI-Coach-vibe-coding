---
phase: 30-unified-training-pinned-foundry-hcp-agent-kb-retrieval
plan: 06
subsystem: acceptance-release
tags: [foundry-agent, foundry-iq, playwright, release-gates]
requires:
  - phase: 30-01
    provides: Session Agent pin migration
  - phase: 30-05
    provides: Exact Agent WebRTC boundary
provides:
  - Cross-transport Requirement 1 acceptance evidence
  - Real Foundry IQ knowledge_base_retrieve proof
  - Protected-path and release-gate audit
affects: []
requirements-completed: [R1]
completed: 2026-07-28
status: implementation-verified-release-approved
---

# Phase 30 Plan 06: Acceptance and Release Summary

**Requirement 1 is implemented and verified across all intended transports. The stale frontend
test failures are fixed. The user explicitly waived the unrelated global branch coverage gate for
this release without changing its configured threshold.**

## Delivered architecture

- Added a reversible nullable Session migration for `agent_name`, `agent_version`, and internal
  Responses continuation state `agent_response_id`.
- Session creation snapshots the exact synced Microsoft Foundry HCP Prompt Agent identity once.
- Every later interaction resolves Agent identity only from the owned Session and fails closed for
  missing, blank, classic-assistant, unauthorized, or invalid pins.
- Text training uses the Responses API with exact `agent_reference` and persists continuation only
  after terminal completion.
- Voice Live and avatar use exact Session Agent name/version/project. Session instructions are
  empty, with no model fallback or temporary Skill context.
- WebRTC accepts trusted `session_id`, validates authorization before STS exchange, and derives the
  URL-encoded Agent name/version/project server-side.
- Browser requests never choose Agent identity and send no `focus_instruction`,
  `additional_instructions`, or temporary Skill content.

## Verification evidence

The authoritative evidence is in [30-ACCEPTANCE.md](30-ACCEPTANCE.md).

| Area | Result |
|---|---|
| Alembic round trip | passed |
| Backend complete assertions | 2554 passed, 153 skipped, 28 deselected, 0 failed |
| Completed full global coverage artifact | 88.95% |
| Focused seven-line closure | 5 passed; audio transcoding service 100%; estimated global 89.01% |
| Python changed-code coverage | 187/187, 100% |
| Ruff lint / format | passed; 340 files formatted |
| Requirement 1 frontend API suite | 20 passed |
| Unified Session focused suite | 21 passed |
| Complete frontend Vitest | 2422 passed, 0 failed |
| Global frontend coverage | statements 91.04%, branches 77.62%, functions 82.65%, lines 91.04% |
| Changed TypeScript line coverage | 2/2, 100% |
| TypeScript / production build | passed / passed |
| Playwright | 4 passed, 0 failed, 0 skipped using system Edge |
| Real Azure Foundry IQ | 1 passed, 0 skipped |
| Protected paths | 6/6 post-run hashes equal |

Real Azure acceptance created a rollback-only production Session pinned to `Dr-Chen-Jun` version
`5`, inspected that exact version's authenticated MCP RemoteTool, required allowed tools exactly
`knowledge_base_retrieve`, and received KB-exclusive marker `UNIFIED-IQ-MARKER-7F3C9A` from Search
`aicoach-demo-srch-iq`. Latest response ID:
`resp_00b5d61f36d80b8a006a68814df7048196868834bd3568fb72`.

## Scope and security audit

- Requirement 2 was not started.
- Session text and Voice Live paths contain no Skill focus/additional instruction injection.
- The legacy `_compose_session_instructions()` helper is standalone/non-session only.
- Browser E2E proves identity-minimal Session and Voice Live request bodies.
- Protected debug documents and database backups were unchanged byte-for-byte and remain excluded
  from staging.

## Release blockers and Git state

- The 108 stale frontend failures were repaired. Full Vitest is green, but global branch coverage
  is 77.62% against the configured 82% threshold. This is approximately 183 additional covered
  branches short; the threshold was not lowered, and the user explicitly waived this unrelated
  global gate for the Requirement 1 release. See [deferred-items.md](deferred-items.md).
- The user waived another 22-minute complete backend run after focused tests covered the final seven
  lines, so the estimated 89.01% global coverage is not backed by a new complete-run artifact.
- Root tracked database sidecars were restored and are excluded from staging.
- Branch is `feat/0616_shuning`; local HEAD remains baseline
  `3a68cbe22c075d425fa63136e8f929537944b55d` with zero staged files.
- Final commit SHA: not available. Remote SHA verification: not performed. No Phase 30 commit or
  push occurred.

## Final disposition

Status is **implementation verified and release approved by explicit gate waiver**. Proceed with
allowlist staging, the single required commit, and the single push. Requirement 2 remains untouched.