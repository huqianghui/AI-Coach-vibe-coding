# Phase 31 Context — Capability-First Session Skill Context for the Pinned Foundry Agent

## Planning Status

Phase 31 is **capability-first**. Only [31-01-PLAN.md](31-01-PLAN.md) is executable. All production integration plans were withdrawn after checker failure and **must be regenerated from the recorded 31-01 verdict**. No production code, production test, schema, migration, frontend, release, commit, or push work may begin from the withdrawn plans.

The default Session-bound WebRTC verdict is **FAIL-CLOSED**. It may become **PROVEN** only when a separate live Playwright/browser probe on the actual Unified Training route demonstrates exclusive backend response authority against a hostile browser data-channel `response.create`. A cooperative-client or backend-pytest-only result cannot change that default.

## Scope

Implement **Requirement 2 only** after capability proof: server-owned Session Skill SOP temporary context behaviorally guides the exact Session-pinned Foundry Prompt Agent across text Responses and Voice Live WebSocket/avatar while preserving native Foundry IQ. Session-bound WebRTC remains unavailable unless the live browser gate proves exclusive authority and the phase is replanned for the proven endpoint/lifecycle.

## Locked Decisions

- **D-01 — Exact Session pin is immutable authority.** Every response uses only `CoachingSession.agent_name` and `CoachingSession.agent_version`; no HCP-latest lookup, default version, generic adapter, model fallback, or transport substitution.
- **D-02 — Context is server-owned.** The browser may send authenticated `session_id`, user text/media, and documented media-control intents only. It never sends Skill text, SOP state, Agent identity, instructions, tools, or response context.
- **D-03 — Behavioral injection is required.** Audit fields, logs, or post-response processing alone do not satisfy Requirement 2. Temporary context must reach the exact Agent before each response and behaviorally affect it.
- **D-04 — Preserve Agent-native IQ and prohibit Agent mutation.** Do not send replacement `tools`/`tool_choice`, mutate/clone the Agent, or create/publish a version. Capability evidence must include an exact before/after canonical Agent-definition/tool hash, a sorted Agent-version inventory fingerprint, and a static/runtime write guard.
- **D-05 — Immutable snapshots are references, not current progress.** Preserve `focus_instruction` byte-for-byte as the Session creation reference. Because it can contain stale progress, never treat it as the authoritative current-step directive and never rewrite it per turn.
- **D-06 — Stable structured SOP authority.** A migration must add an immutable structured SOP snapshot captured at Session creation from the pinned Skill version. Each turn deterministically derives a separate authoritative current-step directive from that snapshot and `sop_current_step`, appending it after the immutable focus reference. Never fetch mutable latest Skill content per turn. Historical Skill-bound rows missing a valid structured snapshot fail closed; no guessed repair.
- **D-07 — Response timing.** Freeze the committed SOP step for the current response. Only after successful terminal response and durable turn persistence may authoritative user input/transcript produce a monotonic decision for the next response. Failure/indeterminate does not advance.
- **D-08 — Text Responses contract.** Every Session initial/continued call sends top-level `instructions`, exact `agent_reference`, and `previous_response_id` when present. Preserve public `chat_with_agent()` semantics for HCP playground/Phase 30; add a separate Session-specific wrapper or required typed Session context API rather than globally requiring instructions.
- **D-09 — Detector compatibility.** Do not break `detect_sop_step()` callers. Add a new typed Session progression API (preferred), or update every caller and its tests atomically in one regenerated plan while keeping the repository green.
- **D-10 — Voice WS/avatar authority and contract.** Session VAD auto-response is disabled. Text-over-WS `conversation.item.create` is an allowed user intent; audio final transcript is the authoritative audio input. Browser callbacks are display-only for Session flows. Backend creates exactly one response with response-level temporary instructions and persists user transcript, assistant output, context audit, and progression. `unified-session.tsx`, hook tests, page tests, and Playwright must exercise this contract.
- **D-11 — WebRTC is fail-closed unless live-browser proven.** Backend pytest cannot prove hostile browser data-channel exclusion. A separate live Playwright probe must use the actual Unified Training path and attempt bypass. Missing browser/harness, successful bypass, ambiguous routing, duplicate response, or cooperative-only evidence yields `FAIL-CLOSED`. A `PROVEN` result requires regeneration of later plans with the exact endpoint, signaling/control ownership, data-channel policy, event routing, cleanup, and lifecycle observed.
- **D-12 — Append-only per-turn audit is mandatory.** Existing Session/SessionMessage state cannot reconstruct applied context. Regenerated plans must add an ORM model and Alembic migration for immutable per-turn context audit, with unique idempotency key, transport, exact pin, Skill/version IDs, structured snapshot/context digests, applied step, response ID, progression result, timestamps, and sanitized correlation metadata. Rows are append-only, exported through explicit model/package exports, retained at least as long as the parent Session, cascade/restrict semantics documented, and covered by migration upgrade/downgrade plus DB round-trip/idempotency tests.
- **D-13 — Actual IQ invocation evidence.** Success requires correlated MCP call lifecycle evidence naming exactly `knowledge_base_retrieve`; marker text or Agent tool configuration alone is insufficient. Parse accepted exact `response.mcp_call.*` stream events and, only when exposed by the SDK, final Responses output items of type `mcp_call`. Correlate call ID to the same response ID/chain, require a successful terminal call event, reject failed/uncorrelated/other-name calls, and record which surface supplied proof.
- **D-14 — Blocking preflight, no hidden assumptions.** Before any live call, resolve and sanitize: HCP/scenario/session IDs, Foundry endpoint/project, IQ question/expected marker, Voice Live endpoint/credential source/API version, avatar config, exact Agent pin, Python/SDK versions, frontend/base URL, Chromium/Playwright availability, and media permissions/device capability. Existing DB config services and `DefaultAzureCredential`/Azure CLI are allowed; raw secrets must never be written to files/output. Any missing prerequisite blocks the applicable probe and produces a deterministic verdict, not a successful skip.
- **D-15 — Capability-first regeneration.** Plan 31-01 is standalone and non-mutating. Plans 31-02+ do not exist as executable plans and must be regenerated after `31-CAPABILITY-EVIDENCE.md` and `31-01-SUMMARY.md` record the approved verdicts.
- **D-16 — One Requirement 2 release.** After regenerated implementation plans and all gates pass, use one explicit allowlisted commit and one push. Record the baseline commit count before release, pre-release evidence before commit, and post-push receipt/remote SHA after push; do not claim the post-push receipt is inside the already-pushed commit.
- **D-17 — Protected work.** Never modify/stage `.planning/debug/*`, `backend/storage/db-backups/`, database files/sidecars, or Phase 30 acceptance/summary. Never use broad add, clean, reset, or stash.
- **D-18 — Coverage thresholds are immutable.** Known frontend branch coverage is 77.62% versus required 82%. Regenerated plans must include explicit uncovered-branch closure or a blocking user decision checkpoint; the threshold may not be lowered. All changed executable Python/TS/TSX requires executable changed-code coverage, not typecheck-only substitution.

## Capability Verdict Rules

| Surface | Required proof | Failure verdict |
|---|---|---|
| Text Responses | Initial and continuation obey distinct temporary directives on exact pin; same chain contains successful correlated `knowledge_base_retrieve`; no tools override | Block text integration planning |
| Voice WS | Typed SDK response creation timeline, VAD no-auto-response, exactly one backend response, behavior proof, successful correlated MCP call | Block WS/avatar integration planning |
| Avatar | Same authority path plus configured avatar lifecycle and events | Block avatar integration planning |
| WebRTC | Separate live Playwright on actual Unified Training route; hostile data-channel create rejected/prevented and no extra response | `FAIL-CLOSED` |

A 2xx, generated marker text, configured tool inventory, or a mocked/browser-cooperative flow is not capability proof.

## Post-Gate Architecture Commitments for Regenerated Plans

1. Add immutable structured SOP snapshot columns at Session creation and fail closed for historical rows without them.
2. Add append-only per-turn audit model, Alembic migration, package exports, retention/foreign-key semantics, uniqueness/idempotency, and migration/round-trip tests.
3. Build one canonical envelope containing immutable focus reference plus a separately rendered authoritative current-step directive.
4. Preserve `chat_with_agent()` standalone callers; add a Session-specific wrapper/typed required context.
5. Preserve `detect_sop_step()` compatibility; add a typed Session progression API.
6. Resolve text and WS flows as backend-owned persistence/progression; browser callbacks remain display-only.
7. Generate exactly one WebRTC implementation plan matching the gate verdict. `FAIL-CLOSED` is the default; do not retain conditional executable branches.
8. Include `unified-session.tsx` and its tests, actual Unified Training Playwright path, strict live no-skip, protected hash/forbidden sweep, coverage closure, and release receipt semantics.

## Deferred / Out of Scope

Conference flows, scoring, hints/key-message redesign, Skill authoring/lifecycle, Foundry Agent/version writes, IQ replacement, mutable-latest lookups, historical snapshot backfill by guesswork, threshold reduction, and generic/model/transport fallback.

## Decision Coverage Matrix

| Decision | Current executable plan | Coverage |
|---|---|---|
| D-01–D-04, D-13–D-15, D-17 | 31-01 | Full capability-gate coverage |
| D-05–D-12, D-16, D-18 | Regenerated plans required after 31-01 | Locked architecture/validation input; not executable yet |

No locked decision is partially implemented by the current plan set: implementation decisions are intentionally blocked until capability evidence exists.
