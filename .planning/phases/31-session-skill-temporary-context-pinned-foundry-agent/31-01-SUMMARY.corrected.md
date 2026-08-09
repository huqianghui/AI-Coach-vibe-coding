---
phase: 31-session-skill-temporary-context-pinned-foundry-agent
plan: 01
subsystem: capability-gate
status: proven-text-production-replanning-authorized
tags: [azure-foundry, conversations, developer-item, fail-closed, non-mutating]
provides:
  - PROVEN CONVERSATION_ITEM_DEVELOPER on ai-coach-demo / Dr-Chen-Jun / 5
  - same-Conversation A/B behavioral distinction
  - two independently correlated successful knowledge_base_retrieve lifecycles
  - deterministic Voice/avatar blocked and WebRTC fail-closed verdicts
  - authorization to regenerate production plans only
decisions:
  - Top-level instructions with exact agent_reference is DISPROVEN by HTTP 400 and must not be used.
  - Text production must use a server-owned Foundry Conversation and per-turn developer Conversation item.
  - Voice WS/avatar remain BLOCKED ENDPOINT 404; Session WebRTC remains FAIL-CLOSED; none has fallback.
  - Agent definition/tool and version-inventory fingerprints matched; Agent writes were zero; disposable Conversation cleanup was confirmed.
completed_date: 2026-08-04
---

# Phase 31 Plan 01 Corrected Capability Summary

This corrected summary supersedes the stale blocked frontmatter and historical command-silence sections in `31-01-SUMMARY.md`. Detailed sanitized evidence remains in `31-CAPABILITY-EVIDENCE.md`.

## Authoritative verdict

- Text: **`PROVEN: CONVERSATION_ITEM_DEVELOPER`**.
- Exact target: `ai-coach-demo / Dr-Chen-Jun / version 5`.
- A and B produced distinct required behavior in the same disposable Foundry Conversation.
- A and B each had a separately correlated, successful exact `knowledge_base_retrieve` MCP lifecycle.
- Requests supplied no `tools` or `tool_choice`.
- Top-level `instructions` is **DISPROVEN** (`HTTP 400: Not allowed when agent specified`).
- Agent resource writes: zero; definition/tool and version inventory fingerprints: match.
- Protected hashes: match; database writes: zero; disposable Conversation cleanup: confirmed.
- Voice WS/avatar: **BLOCKED — ENDPOINT 404**.
- Session WebRTC: **FAIL-CLOSED**.

## Authorization boundary

The verdict authorizes the revised production planning set beginning with `31-03-PLAN.revised.md`. It does not itself authorize production edits, schema/database changes, commit, or push. The original 31-02 through 31-07 plans remain withdrawn and non-executable.
