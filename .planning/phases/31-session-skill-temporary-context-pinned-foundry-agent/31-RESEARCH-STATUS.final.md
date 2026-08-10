# Phase 31 Final Research Status

**Authority:** Findings/status only. This file contains no executable top-level instructions and authorizes no implementation, commit, or push.

## Confirmed findings

1. `PROVEN: CONVERSATION_ITEM_DEVELOPER`: Skill-bound text can use a server-owned Foundry Conversation, a developer item before each user item, and the exact Session `agent_reference`.
2. Top-level `instructions` with an Agent is disproven by service rejection. Response-input developer/system candidates are also disproven for this path.
3. Explicit Conversation continuation is the supported Phase 31 design. Compatibility with `previous_response_id` is unproven; simultaneous use is prohibited.
4. Native Foundry IQ remains Agent-owned. Invocation proof requires a successful response-correlated MCP lifecycle named exactly `knowledge_base_retrieve`; answer markers and configured tool inventory are insufficient.
5. Voice Live WS/avatar are blocked by endpoint 404. WebRTC cannot prove exclusive server response authority and remains fail closed.
6. A browser-side cooperative contract cannot establish server authority. Browser requests must be treated as untrusted and stripped of Conversation, context, Agent, Skill, tool, instruction, response-create, continuation, and idempotency authority.
7. `focus_instruction` can contain stale progress. It must remain immutable reference text, while a final current-step developer directive explicitly has highest precedence and supersedes all stale progress references.
8. External create/respond operations do not provide a reliable exactly-once contract across timeout/connection loss. Durable outbox state, provider operation IDs when available, leases, immutable attempts, and reconciliation can guarantee at-most-one committed application result, not exactly one provider side effect.
9. Conversation creation may have an unknown outcome when the provider lacks idempotent creation metadata. Honest behavior is fail closed and reconcile by persisted provider ID/idempotency metadata if available; otherwise quarantine for operator/retention cleanup rather than blind recreation.
10. Coverage.py supports branch data and diff coverage for Python. Vitest V8 LCOV/diff tools do not reliably enforce changed TS/TSX branches; a deterministic source-map-aware verifier is required to compare changed executable statement and branch locations against V8 coverage.
11. SQLite-only migration proof is insufficient. PostgreSQL-specific constraints, locking/CAS behavior, heads, data preservation, and downgrade must run against a real PostgreSQL service.

## Final architecture status

- Text: planned and eligible for implementation only through the final plan chain.
- Voice/avatar/WebRTC: unavailable/fail closed.
- Conversation lifecycle and turn outbox: required durable infrastructure.
- Append-only attempt and context audit: required and separate from mutable aggregates.
- Release: prohibited until all validation gates succeed.

## Supersession

These findings supersede conflicting assumptions in prior Phase 31 research, especially any assumption that top-level instructions, Response-input developer/system, Voice/avatar, WebRTC, browser continuation, or provider exactly-once behavior is available.
