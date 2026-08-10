# Phase 31 Research Addendum — Checker-Driven Capability Gate

**Date:** 2026-07-28
**Status:** Authoritative over conflicting assumptions in 31-RESEARCH.md

## Corrected Findings

1. Backend pytest can validate SDK calls and server event handling, but cannot prove that a hostile browser is unable to issue `response.create` over a negotiated WebRTC data channel. Session-bound WebRTC therefore defaults to **FAIL-CLOSED**.
2. A WebRTC `PROVEN` verdict requires a separate live Playwright test using the actual Unified Training route, a real browser `RTCPeerConnection`/data channel, and an active hostile bypass attempt. If a test-only harness cannot reproduce the production endpoint/lifecycle without production edits, the capability plan records `FAIL-CLOSED`; it does not skip or infer safety.
3. Environment availability is not presumed from Phase 30. The capability plan performs a blocking, sanitized preflight for application IDs, Foundry/IQ inputs, Voice Live/API/avatar settings, credentials source, and browser/media capability before network calls.
4. Read-only intent is insufficient mutation evidence. Before and after probes, canonical JSON hashes of the exact Agent definition and tools plus a sorted Agent-version inventory fingerprint must match. Static forbidden-write scanning and runtime client write traps are both required.
5. Foundry IQ proof requires an actual successful MCP invocation named exactly `knowledge_base_retrieve`, correlated to the tested response. Accepted stream event family is `response.mcp_call.*`; the probe must enumerate the concrete SDK event types it observes/accepts. Final Responses output may expose items with `type == "mcp_call"`; this is parsed only when present and must include the exact name/call correlation. Marker output and configured tools are supporting evidence, never invocation proof.
6. Existing `SessionMessage` records cannot reconstruct the exact per-turn context, applied SOP step, response correlation, and progression decision. An append-only audit model and Alembic migration are mandatory in regenerated implementation plans.
7. Existing `focus_instruction` may embed stale progress. Preserve it as immutable reference text and append a separately rendered authoritative current-step directive from a new immutable structured SOP snapshot. The snapshot is created once from the pinned Skill version; historical missing/invalid snapshots fail closed.
8. Public `chat_with_agent()` serves standalone HCP playground and Phase 30 acceptance. A Session-specific wrapper/typed context must carry required instructions without globally changing standalone semantics.
9. `detect_sop_step()` has existing callers. Add a new typed Session progression function, or atomically update all callers/tests in one plan; no temporary red state is acceptable.
10. Session WS text intent may use `conversation.item.create`. Audio final transcript is authoritative. Browser callbacks display lifecycle only; backend persists user/assistant/audit/progression. Future plans must include `frontend/src/pages/user/unified-session.tsx` and corresponding unit/E2E tests.

## Live Probe Event Parsing Contract

### Responses text

Collect all streaming event type strings and response IDs. Invocation succeeds only when:

- an accepted successful terminal event in the `response.mcp_call.*` family is present for a call whose name is exactly `knowledge_base_retrieve`; and
- its call/response correlation belongs to the same initial/continuation chain under test; and
- no `response.mcp_call.failed` exists for that call.

Because preview SDKs can represent MCP output differently, the probe must print a sanitized inventory of observed event type names and explicitly list accepted concrete types in evidence. If the final response exposes `output` items, parse only items with `type == "mcp_call"`, exact `name`, call ID, and successful status. If final output does not expose MCP calls, state that explicitly and rely on correlated stream lifecycle events. Never infer invocation from answer text.

### Voice Live

Use typed SDK event creation rather than raw unvalidated dictionaries. Evidence records a timeline containing: session configuration with `create_response=False`; committed text item or authoritative final audio transcript; backend response create with the SDK's response-level temporary-instruction field; response created; MCP lifecycle; assistant transcript/output; terminal response. Each event must carry or map to one server turn correlation key.

## WebRTC Feasibility Rule

The separate live browser probe is technically feasible only when preflight confirms all of the following without changing production code:

- an actual Unified Training Skill-bound Session/HCP/scenario is available;
- frontend and backend live base URLs are reachable;
- installed Chromium supports the required fake/real media setup and exposes the active data channel for a hostile injected event;
- the target endpoint/lifecycle under test is the same one that a future production plan would rely on; and
- server/service event telemetry can distinguish the authorized response from the injected attempt.

If any condition fails, record `FAIL-CLOSED: PROOF HARNESS UNAVAILABLE`. If the injected event creates or can ambiguously create another response, record `FAIL-CLOSED: BYPASS POSSIBLE`. Only service rejection/prevention plus exactly one authorized response can yield `PROVEN`, after which plans must be regenerated with the observed endpoint/lifecycle design.

## Audit Schema Requirements for Regenerated Plans

The append-only record must include at least:

- UUID primary key and parent Session foreign key;
- unique `(session_id, turn_key)` idempotency constraint;
- transport and authoritative user message/transcript correlation;
- exact Agent name/version and Skill/version IDs;
- structured SOP snapshot digest, immutable focus digest, rendered context digest/schema version, applied step;
- provider response ID and successful terminal state;
- typed progression outcome and from/to step;
- sanitized MCP call correlation metadata;
- created timestamp with no update/delete service path.

Define ORM/package exports, Alembic upgrade/downgrade, SQLite/PostgreSQL-compatible constraints, retention at least equal to parent Session, explicit parent-delete behavior, duplicate replay handling, and ORM/API round-trip tests.

## Validation/Release Correction

Known frontend branch coverage is 77.62% against an 82% gate. Future implementation plans must inspect uncovered branches and close the deficit, or stop at a blocking user decision checkpoint. Lowering/excluding the threshold is forbidden. Final commands must preserve pytest's exit code when teeing output (PowerShell `$PSNativeCommandUseErrorActionPreference=$true` and immediate `$LASTEXITCODE` capture, or an equivalent wrapper), require zero live skips, compute changed-code coverage for executable Python/TS/TSX, rerun protected hashes/forbidden sweeps, prove one commit from the recorded baseline, and separate pre-release evidence from the post-push receipt.
