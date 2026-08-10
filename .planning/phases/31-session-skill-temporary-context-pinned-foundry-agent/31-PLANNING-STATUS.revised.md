# Phase 31 Requirement 2 — Authoritative Production Planning Status

**Effective:** 2026-08-04

This file supersedes stale planning-status and D-08 text in `31-CONTEXT.revised.md` for execution. The capability evidence remains authoritative.

## Capability verdicts

| Surface | Verdict | Executable consequence |
|---|---|---|
| Text Responses | `PROVEN: CONVERSATION_ITEM_DEVELOPER` | Implement only a server-owned Foundry Conversation, a developer message item immediately before each user turn, and Responses with the exact Session `agent_reference` |
| Top-level `instructions` with Agent | `DISPROVEN` — HTTP 400, `Not allowed when agent specified` | Never send it |
| Voice Live WS | `BLOCKED: ENDPOINT 404` | Session Voice and avatar are unavailable and fail closed; no fallback |
| Avatar | `BLOCKED: ENDPOINT 404` | Unavailable and fail closed; no fallback |
| Session WebRTC | `FAIL-CLOSED` | Unavailable; no token/signaling exchange and no fallback |

## Corrected D-08

**D-08 — Text Responses contract.** A Skill-bound application Session maps to one server-owned Foundry Conversation. Before each user turn the backend appends one `developer` Conversation item containing the canonical immutable-focus reference and current-step directive, then appends/sends the user item and creates a Response with the exact `agent_reference`. Do not send top-level `instructions`, `tools`, `tool_choice`, browser-supplied continuation, or `previous_response_id`. Explicit Conversation semantics are the sole continuation mechanism. Preserve public standalone HCP admin `chat_with_agent()` and Phase 30 non-Skill text behavior.

## Production lifecycle decisions

1. Capture immutable structured SOP JSON and digest at application Session creation from its pinned `skill_version_id`; preserve `focus_instruction` byte-for-byte. Historical Skill-bound rows without a valid snapshot fail closed.
2. Lazily provision the Foundry Conversation at the first Skill-bound text turn, under a durable per-Session lease. Persist its ID and lifecycle state before adding items. Never accept the ID from a client.
3. For turn $N$, append exactly one developer item immediately before its user item. The directive has a monotonically increasing context revision and explicitly supersedes earlier Session-context developer items. Earlier items remain immutable history; latest-revision precedence is grounded in the proven same-Conversation A/B behavior.
4. Use the Foundry Conversation ID—not `previous_response_id`—for continuation. Tests must reject requests containing both mechanisms.
5. Serialize turns per Session. A pending server-owned turn record/audit key is reused after disconnect/retry until terminal outcome; a completed identical user message is a new turn. Event duplicates are idempotent.
6. Persist assistant output, Response/correlation metadata, and one immutable audit row before monotonic progression becomes visible to the next turn. Failure or indeterminate detection does not advance.
7. Retain the Foundry Conversation while the application Session is active. On end/delete/expiry, block new turns, request deletion, and mark `closed`; transient deletion failures become `cleanup_pending` and are retried by bounded startup/maintenance cleanup. Never silently create a replacement Conversation for an existing mapped Session.
8. Voice/avatar/WebRTC are unavailable for Requirement 2. Their Session entry points return structured fail-closed errors before external exchange, and Unified Training displays the error without transport/model/text fallback.

## Executable plan set

The old `31-02-PLAN.md`, `31-03-PLAN.md` through `31-07-PLAN.md`, and their conditional Voice/WebRTC branches are **WITHDRAWN / NON-EXECUTABLE**. `31-02-PLAN.revised.md` is completed capability-gate history, not production implementation.

Execute only, in order:

`31-03-PLAN.revised.md` → `31-04-PLAN.revised.md` → `31-05-PLAN.revised.md` → `31-06-PLAN.revised.md` → `31-07-PLAN.revised.md` → `31-08-PLAN.revised.md` → `31-09-PLAN.revised.md`.

No plan before 31-09 may commit or push. Protected paths and Phase 30 acceptance/summary evidence remain read-only.
