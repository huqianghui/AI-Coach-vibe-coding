# Phase 31 Context — Session Skill Temporary Context for the Pinned Foundry Agent

## Scope

Implement **Requirement 2 only**: server-owned Session Skill SOP temporary context must behaviorally guide the exact Session-pinned Foundry Prompt Agent across text Responses, Voice Live WebSocket/Avatar, and WebRTC while preserving the pinned Agent's native Foundry IQ `knowledge_base_retrieve` capability.

## Locked Decisions

- **D-01 — Exact Session pin is immutable authority.** Every response uses only `CoachingSession.agent_name` and `CoachingSession.agent_version`; no HCP-latest lookup, default version, generic adapter, model fallback, or transport-specific substitution.
- **D-02 — Context is server-owned.** The browser may send authenticated `session_id`, user text/media, and documented media-control intents only. It never sends Skill text, SOP state, Agent identity, instructions, tools, or response context.
- **D-03 — Behavioral injection is required.** Audit fields, logs, or post-response processing alone do not satisfy Requirement 2. The temporary context must reach the exact Agent before each response and behaviorally affect it.
- **D-04 — Preserve Agent-native IQ.** Do not send replacement `tools`/`tool_choice`, mutate the Agent, clone it, create/publish a version, or replace Foundry IQ with application retrieval. Exact version `5` must retain authenticated `knowledge_base_retrieve`.
- **D-05 — Current snapshot semantics remain unchanged.** Existing Session `skill_id`, `skill_version_id`, `focus_instruction`, and `sop_current_step` remain authoritative. Do not silently rewrite `focus_instruction`, fetch mutable latest Skill content per turn, or change its creation semantics.
- **D-06 — Response timing.** Freeze the committed SOP step for the current response. Only after successful terminal response persistence may authoritative user input/transcript produce a monotonic next-step decision for the next response. Detector failure/indeterminate state does not heuristic-advance.
- **D-07 — Text contract.** Every initial and continued Responses call sends top-level `instructions` together with the exact `agent_reference` and, when present, `previous_response_id`.
- **D-08 — Voice WS/Avatar authority.** Session-bound VAD auto-response is disabled; the backend creates each response with response-level `additional_instructions`. Browser response/instruction/tool/identity events are rejected by an allowlist. Avatar shares this same authority path.
- **D-09 — WebRTC is gated, not assumed.** Ship server-owned response authority only if the live gate proves behavioral context and that browser/data-channel bypass is enforceably prevented. Otherwise Session-bound WebRTC fails closed with a structured unsupported error; it never falls back.
- **D-10 — Capability-first execution.** Plan 31-01 is non-mutating and runs before production integration against project `ai-coach-demo`, exact `Dr-Chen-Jun` version `5`. Its evidence checkpoint may require later plan revision.
- **D-11 — Audit persistence is evidence-driven.** Decide whether existing durable Session/message state plus structured metadata can meet audit reconstruction before planning a schema change. Add an Alembic migration only if the written audit decision proves a dedicated append-only record is required.
- **D-12 — One Requirement 2 release.** Plans execute strictly in order. No plan commits or pushes before 31-07. After every gate passes, stage an explicit allowlist, create exactly one Requirement 2 commit, and push once.
- **D-13 — Protected work.** Never modify/stage `.planning/debug/*`, `backend/storage/db-backups/`, database files/sidecars, or Phase 30 acceptance/summary files. Never use `git add .`, `git add -A`, clean, reset, or stash.

## Obsolete Assumption

Phase 24 thread/run `additional_instructions` is obsolete for this runtime. Text uses Responses top-level `instructions`; Voice Live uses response-level temporary instructions after live capability proof.

## Deferred / Out of Scope

- Conference flows, scoring, hints/key-message redesign, Skill authoring/lifecycle, Foundry Agent/version writes, IQ replacement, historical-session repair, and any generic/model/latest fallback.
- No migration is presumed. The audit decision in Plan 31-02 determines whether later plans must be revised to add one.

## Acceptance Invariants

1. The same exact `Dr-Chen-Jun` version `5` can obey temporary SOP behavior and retrieve the IQ-only marker in one chain.
2. Initial and continuation text turns receive the current server-rendered context.
3. WS voice and avatar responses are created once by the backend with VAD auto-response disabled.
4. WebRTC either proves exclusive server authority and ships that path, or is explicitly unavailable for Session-bound training.
5. Browser contracts expose no Agent/Skill/SOP/instruction/tool authority.
6. Each implementation plan proves 100% changed-code coverage before the next plan; final gates include full pytest, Ruff check/format, full Vitest coverage, TypeScript, build, Playwright, live acceptance, protected hashes, one allowlisted commit, and one push.
