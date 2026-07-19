---
phase: 29-voice-live-api-refactor-adaptation-azure-ai-voicelive-sdk-1-
plan: 01
subsystem: infra
tags: [azure-ai-voicelive, azure-ai-projects, entra-id, voice-live, sdk-upgrade, poc]

# Dependency graph
requires: []
provides:
  - "azure-ai-voicelive pinned to 1.3.0b1 (GA 1.3.0 confirmed unavailable on PyPI at execution time)"
  - "Live-verified Entra-first/API-key-fallback credential resolution against azure.ai.voicelive.aio.connect"
  - "Live-verified Agent connect + session.update round-trip on the pinned SDK, with explicit api_version=\"2026-07-15\" override accepted by the service"
  - "Live-captured AIProjectClient.deployments.list() capabilities dict shape (chat_completion/embeddings/realtime distinction) for D-14"
  - "Reusable POC script (backend/scripts/poc_voice_live_1_3_0.py) for future SDK re-verification"
affects: [29-02, 29-03, 29-06, 29-07, 29-08]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "connect() kwargs shape changed in 1.3.0b1 (breaking vs 1.2.0b5): agent_name/project_name are now flattened top-level kwargs on connect(), not a nested AgentSessionConfig dict"
    - "api_version must be explicitly passed as \"2026-07-15\" at every connect() call site to override the 1.3.0b1 beta SDK's default (2026-06-01-preview)"
    - "AIProjectClient requires a project-scoped endpoint ({base}/api/projects/{project_name}), not the bare account endpoint, for deployments.list() (matches agent_sync_service.get_project_endpoint() precedent)"

key-files:
  created: [backend/scripts/poc_voice_live_1_3_0.py]
  modified: [backend/pyproject.toml]

key-decisions:
  - "Checkpoint decision (user-selected, blocking): pin-beta -- install azure-ai-voicelive[aiohttp]==1.3.0b1 with --pre, explicitly pass api_version=\"2026-07-15\" at every connect() call site, since GA 1.3.0 is confirmed not yet published to PyPI"
  - "Downstream plans (29-02/29-06/29-07) must use the flattened connect(agent_name=, project_name=) kwarg shape, not the old AgentSessionConfig dict, due to a 1.3.0b1 breaking API change"
  - "D-14 filter key resolved from live evidence: capabilities.get(\"chat_completion\") == \"true\" reliably distinguishes chat-capable Foundry deployments from embeddings/realtime-only ones"

patterns-established:
  - "Reusable standalone POC pattern for re-verifying SDK/service compatibility before full migration (mirrors docs/microsoft-agent-framework/tests/test_agent_auth_v2.py)"

requirements-completed: [D-03, D-04, D-14-probe]

# Metrics
duration: ~20min (active work across two sessions, separated by a blocking checkpoint awaiting user decision)
completed: 2026-07-19
---

# Phase 29 Plan 01: Voice Live SDK 1.3.0 POC + Version Pin Summary

**Pinned azure-ai-voicelive to 1.3.0b1 (GA not yet on PyPI) after live-verifying Agent connect via Entra ID with explicit api_version="2026-07-15" override, and captured the Foundry deployments capabilities shape for D-14.**

## Performance

- **Duration:** ~20 min active work (two sessions: pre-checkpoint POC/discovery, post-checkpoint pin + re-verification)
- **Completed:** 2026-07-19
- **Tasks:** 3 (1 auto, 1 checkpoint:decision, 1 auto)
- **Files modified:** 2 (1 created, 1 modified)

## Accomplishments

- Live PyPI re-check (not trusted from research-time) definitively confirmed GA `azure-ai-voicelive>=1.3.0,<2.0` is **not installable** — `pip install --dry-run` fails outright; only `1.2.0` (stable) and `1.3.0b1` (beta) exist on PyPI.
- Checkpoint surfaced to user per plan's blocking gate (skip condition not met: GA range unsatisfiable regardless of connect success). User selected **pin-beta**.
- `azure-ai-voicelive[aiohttp]==1.3.0b1` pinned in `backend/pyproject.toml` with a `TEMPORARY` comment explaining the override and pointing to the plans responsible for the explicit `api_version` pass-through.
- POC script proves the **Entra-first credential path** (D-01) and a real **Agent connect + `session.update` round-trip** succeed against the pinned SDK with `api_version="2026-07-15"` explicitly passed — validating that the live Voice Live service accepts the GA api-version string even from a beta client (RESEARCH.md Assumption A2, now verified).
- Discovered and fixed a **breaking API change** in 1.3.0b1: `connect()` no longer accepts an `agent_config: AgentSessionConfig` dict (present in 1.2.0b5); `agent_name`/`project_name` are now flattened top-level kwargs directly on `connect()`. This is load-bearing information for Plans 29-02/29-06/29-07, which build the production `connect()` call sites.
- Captured the live `ModelDeployment.capabilities` shape from the actual Foundry project, resolving D-14's open question: `capabilities.get("chat_completion") == "true"` distinguishes chat models (`gpt-4o-mini`, `gpt-4.1-mini`, `gpt-5.4-mini`) from embeddings (`capabilities={'embeddings': 'true'}`) and realtime-only models (`capabilities={'chat_completion': 'false', 'completion': 'false'}`).

## Task Commits

1. **Task 1: Live PyPI availability check + POC script for Agent connect and Foundry capabilities probe** - `72d77c4` (feat)
2. **Task 2: Checkpoint decision** - no code commit (decision-only; user selected `pin-beta` between sessions)
3. **Task 3: Finalize dependency pin per resolved version and confirm import** - `6dab8a0` (feat)

**Plan metadata:** (this commit, to follow)

## Files Created/Modified

- `backend/scripts/poc_voice_live_1_3_0.py` — Standalone POC: Entra-first/API-key-fallback credential resolution, live Agent connect + session.update round-trip, Foundry deployments.list() capabilities probe. Never prints raw API keys/tokens (T-29-P1 mitigation).
- `backend/pyproject.toml` — `azure-ai-voicelive[aiohttp]==1.3.0b1` (was `>=1.2.0b5`), with `TEMPORARY` comment documenting the GA-unavailable rationale and the explicit `api_version` override requirement for downstream call sites.

## Verbatim POC Output (final run, against pinned 1.3.0b1)

```
======================================================================
  azure-ai-voicelive POC (Phase 29 Plan 01)
======================================================================
  Installed SDK version: 1.3.0b1
  Target GA api_version: 2026-07-15
  Foundry endpoint configured: yes
  Foundry API key configured: yes
  Project name: avarda-demo-prj
  Agent name (hosted, known-good synced HCP): Dr-Wang-Fang

======================================================================
  Agent connect + session.update probe (D-01)
======================================================================
  [credential] DefaultAzureCredential (Entra ID) token probe: PASS
  [connect] WebSocket established via entra credential path
  [connect] session.update sent
  [event] session.created
  [event] session.updated
  [result] AGENT_CONNECT=PASS (credential_path=entra)

======================================================================
  Foundry deployments.list() capabilities probe (D-14)
======================================================================
  [deployment] name=gpt-4o-mini model_name=gpt-4o-mini model_publisher=OpenAI capabilities={'chat_completion': 'true'}
  [deployment] name=gpt-4.1-mini model_name=gpt-4.1-mini model_publisher=OpenAI capabilities={'chat_completion': 'true'}
  [deployment] name=gpt-5.4-mini model_name=gpt-5.4-mini model_publisher=OpenAI capabilities={'chat_completion': 'true'}
  [deployment] name=gpt-image-2-1 model_name=gpt-image-2 model_publisher=OpenAI capabilities={}
  [deployment] name=text-embedding-3-small model_name=text-embedding-3-small model_publisher=OpenAI capabilities={'embeddings': 'true'}
  [deployment] name=gpt-realtime-2.1 model_name=gpt-realtime-2.1 model_publisher=OpenAI capabilities={'chat_completion': 'false', 'completion': 'false'}
  [deployment] name=gpt-realtime-1.5 model_name=gpt-realtime-1.5 model_publisher=OpenAI capabilities={'chat_completion': 'false', 'completion': 'false'}

POC_RESULT: SDK_VERSION=1.3.0b1 AGENT_CONNECT=PASS ENTRA=PASS API_KEY_FALLBACK=PASS
```

**Earlier run (against pre-pin installed 1.2.0b5, before the checkpoint decision — kept for evidence trail):**
```
POC_RESULT: SDK_VERSION=1.2.0b5 AGENT_CONNECT=PASS ENTRA=PASS API_KEY_FALLBACK=PASS
```

Both runs confirm `AGENT_CONNECT=PASS` via the Entra credential path with `api_version="2026-07-15"` explicitly passed, across two different installed SDK versions — strong evidence the Voice Live service itself accepts the GA api-version string regardless of client SDK version.

## Decisions Made

- **Checkpoint decision (user, blocking):** `pin-beta` — install `1.3.0b1` with `--pre`, explicitly override `api_version` at every `connect()` call site. Chosen over `wait` (would block the whole phase indefinitely) and `github-source` (reproducibility/CI risk); POC evidence (both pre- and post-decision runs) supports this is technically sound.
- **D-14 capabilities filter resolved:** `capabilities.get("chat_completion") == "true"` is the correct filter key (live-verified, not assumed) — Plan 08 should use this directly.
- **connect() kwarg shape for downstream plans:** Use `connect(endpoint=..., credential=..., api_version="2026-07-15", agent_name=..., project_name=...)` — flattened kwargs, not `agent_config={...}`. This differs from the pattern in `docs/microsoft-agent-framework/tests/test_agent_auth_v2.py` (written against 1.2.0b5) and must be updated when that reference doc/pattern is reused in Plans 29-02/29-06/29-07.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed AIProjectClient 404 due to bare account endpoint in Foundry capabilities probe**
- **Found during:** Task 1 (first POC run)
- **Issue:** POC script passed the bare `azure_foundry_endpoint` (account-level) directly to `AIProjectClient`, causing `ResourceNotFoundError: (404)`. `AIProjectClient` requires a project-scoped endpoint (`{base}/api/projects/{project_name}`).
- **Fix:** Mirrored the exact resolution logic from `agent_sync_service.get_project_endpoint()` — build `project_endpoint` from `base` + `project_name` when `/api/projects/` isn't already present in the configured endpoint.
- **Files modified:** `backend/scripts/poc_voice_live_1_3_0.py`
- **Verification:** Re-ran POC; `deployments.list()` returned 7 live deployments with capabilities.
- **Committed in:** `72d77c4` (Task 1 commit)

**2. [Rule 3 - Blocking] Fixed 1.3.0b1 breaking API change in POC's connect() call**
- **Found during:** Task 3 (post-pin re-run)
- **Issue:** After pinning to `1.3.0b1`, the POC's `connect(agent_config=AgentSessionConfig({...}))` call raised a `TypeError`/import error — `AgentSessionConfig` and the `agent_config` kwarg were removed in 1.3.0b1; `connect()`'s signature now exposes `agent_name`/`project_name` as flattened top-level kwargs.
- **Fix:** Updated `agent_connect_probe()` to call `connect(..., agent_name=agent_name, project_name=project_name)` directly, with an inline comment flagging this breaking change for downstream plans.
- **Files modified:** `backend/scripts/poc_voice_live_1_3_0.py`
- **Verification:** Re-ran POC against `1.3.0b1`; `AGENT_CONNECT=PASS`.
- **Committed in:** `6dab8a0` (Task 3 commit)

**3. [Rule 2 - Lint/Format Compliance] Fixed ruff lint/format violations in new POC script**
- **Found during:** Task 1, before commit (CLAUDE.md pre-commit checklist requires `ruff check`/`ruff format --check` to pass)
- **Issue:** Initial script draft had 6 `E501` line-length violations and 1 `UP031` percent-format violation.
- **Fix:** Wrapped long lines, switched to f-string formatting, ran `ruff format`.
- **Files modified:** `backend/scripts/poc_voice_live_1_3_0.py`
- **Verification:** `ruff check` and `ruff format --check` both pass.
- **Committed in:** `72d77c4` (Task 1 commit)

---

**Total deviations:** 3 auto-fixed (1 bug, 1 blocking, 1 lint/format compliance)
**Impact on plan:** All fixes necessary for correctness (the 404 fix and the breaking-change fix both directly affect the plan's load-bearing evidence); no scope creep — all changes confined to the POC script itself.

## Issues Encountered

- The checkpoint at Task 2 was correctly surfaced (not silently resolved) per the plan's blocking gate: `AGENT_CONNECT=PASS` alone was insufficient to skip, since the installed/available SDK version never satisfied the GA range `>=1.3.0,<2.0` at any point during execution — confirmed via `pip install --dry-run`, not just `pip index versions`. Execution paused for one full turn awaiting the user's explicit `wait`/`pin-beta`/`github-source` decision, per the plan's "do NOT decide yourself" instruction.

## User Setup Required

None — no external service configuration required. All credentials (Entra via `az login`, API key) were already configured in `backend/.env` prior to this plan.

## Next Phase Readiness

- `backend/pyproject.toml` now carries a working, live-verified `azure-ai-voicelive==1.3.0b1` pin. Plans 29-02/29-06/29-07 (production `connect()` call sites) must:
  1. Use the flattened `agent_name=`/`project_name=` kwargs on `connect()`, not `AgentSessionConfig`.
  2. Explicitly pass `api_version="2026-07-15"` at every `connect()` call (the beta SDK's default is `2026-06-01-preview`) — per D-02, this should land as a single centralized constant/setting, not scattered literals.
  3. Reference `backend/scripts/poc_voice_live_1_3_0.py` as the working example of both requirements.
- Plan 29-08 (Foundry Agent Foundation Model catalog endpoint) can proceed directly with `capabilities.get("chat_completion") == "true"` as the chat-model filter — no further live-shape verification needed, this plan already captured it from the real project.
- Existing `test_voice_live_websocket.py` / `test_voice_live_webrtc.py` suites (98 tests) still pass against the new pin — no immediate regression, though these tests are unlikely to exercise the real `connect()` kwarg shape directly (they mock the SDK), so Plans 29-02/29-06/29-07 should not assume this is proof the flattened-kwarg migration is already done elsewhere in the codebase.
- No blockers for Wave 2+ plans. The one residual risk carried forward: `1.3.0b1` is a beta package: if the Azure SDK team publishes a further beta or the GA lands on PyPI before this phase completes, `backend/pyproject.toml`'s pin and comment should be revisited (not automatically, but flagged for a human check at the next natural touch point).

---
*Phase: 29-voice-live-api-refactor-adaptation-azure-ai-voicelive-sdk-1-*
*Completed: 2026-07-19*

## Self-Check: PASSED

- FOUND: `backend/scripts/poc_voice_live_1_3_0.py`
- FOUND: `.planning/phases/29-voice-live-api-refactor-adaptation-azure-ai-voicelive-sdk-1-/29-01-SUMMARY.md`
- FOUND commit: `72d77c4`
- FOUND commit: `6dab8a0`
