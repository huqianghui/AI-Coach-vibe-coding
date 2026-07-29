# Phase 30 Research — Unified Training Pinned Foundry HCP Agent

**Date:** 2026-07-25
**Discovery level:** Level 2 — cross-transport Azure Agent integration with schema evolution and a real external acceptance boundary.

## Verified Current State

### Branch and repository

- Current branch is `feat/0616_shuning`.
- `HEAD` and `origin/main` are both `3a68cbe22c075d425fa63136e8f929537944b55d`; the branch is already fast-forwarded to `origin/main`.
- Current Alembic head is `z33a_drop_hcp_voice_fields`.
- Unrelated untracked debug documents and `backend/storage/db-backups/` exist and must not be staged or altered.

### Unified Training text path

- `frontend/src/pages/user/training.tsx` creates a `CoachingSession`, then routes to `/user/training/session?id=...`.
- `frontend/src/pages/user/unified-session.tsx` sends text through `POST /sessions/{id}/message` when Voice Live is disconnected.
- `backend/app/api/sessions.py::send_message()` currently resolves the generic LLM adapter, builds local HCP/Skill prompt context, and streams adapter events. It does **not** call the HCP Foundry Prompt Agent.
- `backend/app/services/agent_chat_service.py::chat_with_agent()` already sends `agent_reference = {name, version, type}` through the Foundry Responses API, supports `previous_response_id`, and returns response text/ID, but is synchronous at the SDK boundary and currently returns a completed response rather than stream events.

### Session persistence and pin lifecycle

- `CoachingSession` stores scenario, mode, Skill audit fields, and focus instruction, but no Agent name/version/Responses continuation ID.
- `SessionCreate` contains only scenario/mode. The server can resolve the HCP and authoritative Agent identity from the scenario; the client must not submit Agent identity.
- `HcpProfile.agent_id`, `agent_version`, and `agent_sync_status` are the current authoritative source at session creation.
- `agent_sync_service.sync_agent_for_profile()` creates immutable Foundry Agent versions and updates `profile.agent_version`, so copying both values at session creation creates deterministic historical identity.
- Existing sessions cannot be safely backfilled because the historical version active at their creation is unknown. New nullable DB columns are therefore required, with fail-closed interaction behavior for null legacy rows.

### Voice Live WebSocket/avatar path

- Unified Training calls `useVoiceLive.connect({sessionId})`; the first frame contains only trusted `session_id`.
- `_resolve_training_session_context()` currently forces session-bound training to Model mode and requires `focus_instruction`.
- `handle_voice_live_websocket()` calls `_load_connection_config(..., force_model_mode=True)`, composes Skill focus into instructions, and explicitly rejects Agent mode.
- Non-session HCP voice paths already use hosted `agent_name`, but do not pass `agent_version` to `connect()`.
- Verified SDK fact supplied by the user: pinned `azure-ai-voicelive==1.3.0b1` `connect()` supports `agent_version`. Therefore session-bound Voice Live can call `connect(endpoint, credential, api_version, agent_name, agent_version, project_name)` without mutating Agent instructions.
- Avatar is part of the same Voice Live Agent session modalities; no separate Agent invocation is required for the avatar path.

### WebRTC path

- `useVoiceLiveWebRTC()` obtains config from `POST /voice-live/webrtc/session`, but Unified Training currently instantiates only `useVoiceLive()` (the backend WS proxy). WebRTC is used by the reusable standalone VoiceSession path.
- The broker accepts `hcp_profile_id`/`vl_instance_id`, not `session_id`, and builds an Agent signaling URL without version. To prevent a future transport bypass, the session-bound broker contract needs `session_id`, server ownership checks, and the pinned Agent version.
- Admin/playground paths may continue to use HCP/VL-instance inputs because they are not persisted Unified Training sessions.

### Foundry IQ MCP tools

- `knowledge_base_service.build_search_tools()` builds `MCPTool` with `allowed_tools=MCPToolFilter(tool_names=["knowledge_base_retrieve"])` and a `RemoteTool` connection ID.
- `sync_agent_for_profile()` fails closed if an authenticated RemoteTool cannot be built, then stores the resulting Agent version.
- Existing unit tests verify MCP tool serialization and RemoteTool authentication wiring, but they do not prove the deployed Agent version actually retrieves a KB-exclusive answer.
- Prior debug records show 401 with no auth and 403 with CognitiveSearch credentials; the correct runtime binding is the RemoteTool connection (CustomKeys/managed identity path). The acceptance test must inspect the exact version used by the training session, not merely the latest Agent.

### Frontend contracts and tests

- `CoachingSession.mode` is currently typed as `string`; no Agent pin fields exist in TypeScript.
- Existing frontend data flow is server-owned; no Agent name/version should be accepted from browser input.
- The core Playwright precedent is `frontend/e2e/voice-live-proxy.spec.ts`, which already asserts Unified Training's first WS frame contains only `session_id`.
- Backend test surfaces already exist for sessions, Agent chat, Agent sync, KB tools, Voice Live WS/WebRTC, schema integrity, and migration behavior.

## Recommended Architecture

1. **Snapshot once:** At `create_session()`, eager-load scenario/HCP and validate hosted Agent sync state. Persist `agent_name`, `agent_version`, and null `agent_response_id` on `CoachingSession`.
2. **Resolve from session only:** Add a focused helper returning a pinned Agent reference after ownership/status/integrity checks. Never read `HcpProfile.agent_version` during an interaction.
3. **Text:** Replace generic adapter execution for Unified Training messages with `agent_chat_service` using the session pin. Add a streaming service variant based on Foundry `responses.create(..., stream=True)` or bridge the sync iterator with `asyncio.to_thread` + queue. Preserve SSE `text`, key-message, hint, error, and done semantics. Persist the response ID only after a successful completed response.
4. **WS/avatar:** Remove the session-bound model/focus-instruction branch. Resolve voice/avatar settings from the HCP/VL Instance but identity from the session pin; invoke Voice Live with `agent_name + agent_version + project_name` and no temporary Skill instructions.
5. **WebRTC:** Add `session_id` to request/response contracts. For session-bound calls, resolve identity from the session and include exact Agent name/version in signaling. Keep non-session admin/test calls separate.
6. **Fail closed:** Missing/invalid pins, `asst_*`, non-hosted state, ownership mismatch, closed sessions, version lookup failures, Agent/KB runtime errors, and incomplete streams produce structured errors. Do not use generic LLM/model fallback.
7. **Acceptance evidence:** Unit tests prove deterministic pinning and no latest-version substitution. A real-Azure integration test uses environment-supplied profile/scenario/KB question/expected marker, verifies the pinned Agent version's MCP definition, invokes through the same chat service, and asserts the KB-exclusive marker.

## Streaming Implications

- The existing Responses client call is synchronous. Calling it directly inside FastAPI's async SSE generator would block the event loop.
- Preferred implementation: expose an async iterator that runs the synchronous Foundry stream in a worker thread and forwards text deltas through an `asyncio.Queue` to the SSE generator.
- Accumulate the exact assistant text for persistence; update `agent_response_id` only after the stream emits its terminal completed response.
- On cancellation/error, close the upstream stream if supported, do not persist a partial assistant message or continuation ID, and emit one structured SSE error before termination.
- Suggestions and key-message processing remain post-response operations; requirement 2's `focus_instruction`/SOP update must not be passed to the Prompt Agent.

## Real-Azure Integration Boundary

Required environment inputs should identify **pre-provisioned** resources; the test must not create/delete customer KBs:

- `AZURE_FOUNDRY_ENDPOINT`
- `AZURE_FOUNDRY_DEFAULT_PROJECT`
- Entra credentials or existing configured API-key path
- `UNIFIED_TRAINING_HCP_PROFILE_ID` (profile already synced to a hosted Agent with an enabled KB)
- `UNIFIED_TRAINING_KB_QUESTION` (answer is absent from base HCP instructions and only present in KB)
- `UNIFIED_TRAINING_KB_EXPECTED_MARKER` (stable unique expected substring)

Acceptance evidence must record, without secrets:

- session ID
- pinned Agent name/version
- inspected MCP server label/URL host and allowed tool name
- question identifier/hash rather than sensitive full content if necessary
- response ID
- expected marker matched
- timestamp and test command/result

The test may skip in normal offline runs when these inputs are absent, but the phase release gate requires an explicit execution where it passes and is **not skipped**.

## Threat Analysis Inputs

- **Client → API/WS:** client session IDs and messages are untrusted; Agent identity must never come from client payload.
- **Session DB → Foundry:** stored Agent pins are trusted only after format/non-empty validation; legacy null rows fail closed.
- **Foundry Agent → MCP KB:** tool output is external content; Agent version/tool binding must be verified and errors surfaced rather than replaced by ungrounded answers.
- **Streaming:** partial output/continuation IDs must not be committed as successful state after cancellation or upstream failure.

## Scope Guard

Explicitly excluded: Session Skill temporary context, `focus_instruction` injection, `additional_instructions`, per-session Agent mutation/version creation, requirement 2 tests, and any Skill context frontend contract.
