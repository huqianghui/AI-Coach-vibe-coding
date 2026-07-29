# Phase 30 Context — Unified Training Pinned Foundry HCP Agent + Foundry IQ Retrieval

## Scope

Plan and execute **requirement 1 only**: every Unified Training interaction must use the session-pinned Microsoft Foundry HCP Prompt Agent identified by both `agent_name` and `agent_version`, and the exact Agent version bound to Foundry IQ MCP must answer a knowledge-base-exclusive question through `knowledge_base_retrieve`.

## Decisions

- **D-01 — One requirement only.** This phase contains only Unified Training Agent pinning and Foundry IQ retrieval acceptance. No requirement 2 work is allowed.
- **D-02 — Pin at session creation.** A new F2F Unified Training session snapshots the HCP profile's hosted `agent_id` as `agent_name` and its authoritative `agent_version`. Later HCP re-sync/version changes affect only new sessions.
- **D-03 — Fail closed.** Session creation and every interaction boundary reject missing, classic `asst_*`, blank-version, non-synced, or unpinned Agent identity. There is no model/adapter/prompt fallback and no substitution with the HCP profile's latest Agent version.
- **D-04 — Text uses the pinned Prompt Agent.** `POST /sessions/{id}/message` invokes the Responses API with `agent_reference.name` and `agent_reference.version` from the session snapshot. Existing SSE text streaming, persistence, key-message status, and coaching-hint behavior remain observable.
- **D-05 — Preserve multi-turn identity.** Store the previous Foundry response ID as internal session state so subsequent text turns continue the same Responses conversation while retaining the same Agent name/version.
- **D-06 — Voice Live WebSocket and avatar use the same pin.** Session-bound Voice Live resolves identity only from the owned session, calls `azure-ai-voicelive==1.3.0b1` `connect()` with `agent_name`, `agent_version`, and `project_name`, and keeps avatar as a modality on that same pinned Agent connection.
- **D-07 — WebRTC boundary is explicit.** Unified Training currently uses the backend WebSocket proxy, not the preview WebRTC hook. The WebRTC broker must nevertheless accept `session_id`, resolve the same pins server-side, include the exact Agent version in signaling, and fail closed. Direct HCP/VL-instance playground calls remain non-session admin/test paths.
- **D-08 — Foundry IQ acceptance is real, not mocked.** A credential-gated integration test must inspect the exact pinned Agent version for an authenticated MCP tool allowing only `knowledge_base_retrieve`, ask a question whose expected answer exists only in the bound KB, and verify an operator-provided expected marker in the answer.
- **D-09 — Evidence and release gate.** Unit tests cover every changed success/failure branch, Playwright covers the core Unified Training user story, the real-Azure test passes without skip, all repository quality/test gates pass, then the requirement is committed and pushed to `feat/0616_shuning`.
- **D-10 — Preserve unrelated work.** Never stage, modify, delete, or clean unrelated untracked debug files or `backend/storage/db-backups/`.

## Claude's Discretion

- Exact helper names and error-code wording, provided errors remain structured and distinguish missing pin, invalid pin, and upstream failure.
- The sync-to-async bridge used to preserve SSE streaming with the synchronous Foundry Responses client.
- The new Alembic revision ID, provided it descends from current head `z33a_drop_hcp_voice_fields` and uses safe nullable columns for existing rows.

## Deferred Ideas — OUT OF SCOPE

- **Requirement 2 / Session Skill temporary context.** Do not add `additional_instructions`, mutate the Prompt Agent for one session, compose `focus_instruction` into Agent/Voice Live requests, or add any session-scoped Skill context transport.
- Skill/SOP lifecycle redesign, scoring changes, KB creation/upload, HCP Knowledge UI changes, and Agent sync UX changes.
- Retrofitting historical sessions with guessed Agent versions. Existing unpinned sessions fail closed when interaction is attempted.

## Branch and Workspace Baseline

- Required branch: `feat/0616_shuning`.
- Verified planning baseline: `HEAD == origin/main == 3a68cbe22c075d425fa63136e8f929537944b55d`.
- Existing unrelated untracked paths must remain untouched:
  - `.planning/debug/ci-backend-skill-injection.md`
  - `.planning/debug/local-scenarios-missing.md`
  - `.planning/debug/skill-sop-runtime-orchestration.md`
  - `backend/storage/db-backups/`
