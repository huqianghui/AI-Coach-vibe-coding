---
task: 260727-cnd
subsystem: docs/microsoft-agent-framework
tags: [voice-live-sdk, agent-mode, foundry-iq, grounding, documentation]
dependency-graph:
  requires: []
  provides:
    - "doc 02 corrected to SDK 1.3.0b1 connect() call shape"
    - "real live-tested Foundry IQ grounding trigger evidence for Agent mode"
  affects:
    - docs/microsoft-agent-framework/02-model-vs-agent-mode.md
tech-stack:
  added: []
  patterns:
    - "connect() flattened agent_name=/project_name= kwargs (SDK >=1.2.0 GA)"
    - "Entra-ID fallback when API Key auth returns 403 on Voice Live realtime endpoint"
key-files:
  created:
    - docs/microsoft-agent-framework/tests/test_agent_foundry_iq_grounding.py
  modified:
    - docs/microsoft-agent-framework/02-model-vs-agent-mode.md
key-decisions:
  - "Preserved historical §3 (2026-04-08 POC) as an unmodified record; added a callout pointing to new §6 rather than editing history"
  - "Test script attempts API Key first (to honestly record the 403), then falls back to Entra ID to complete the actual grounding turns -- mirrors production's own Entra-first credential resolution logic"
  - "AI Search MCP 403 and the broader API-Key-403 regression are documented but not fixed -- both are Azure resource-level auth issues outside this doc-correction task's scope"
duration: "~1 session"
completed: "2026-07-27"
---

# Quick Task 260727-cnd: Correct doc 02 SDK version + real Foundry IQ grounding test Summary

Corrected `docs/microsoft-agent-framework/02-model-vs-agent-mode.md`'s stale `1.2.0b5`/`AgentSessionConfig` SDK references to match the actually-installed `azure-ai-voicelive==1.3.0b1` flattened `agent_name=`/`project_name=` `connect()` call shape, then ran a real live Agent-mode + Foundry IQ knowledge-base grounding test against the `Dr-Wang-Fang` agent and recorded the unedited, actually-observed results (including an unexpected API-Key-403 regression and a downstream AI Search MCP 403) in a new dated document section.

## Performance

- Tasks: 3/3 completed
- Commits: 3 (one per task, atomic)
- Files created: 1
- Files modified: 1 (edited twice, across Task 1 and Task 3)

## Accomplishments

**Task 1 — Corrected SDK version state and code examples in doc 02**
- Added new §1.1 "SDK 版本状态（2026-07-27 校正）" documenting the real version chain: `1.2.0b5` (doc's stale baseline, deprecated) → `1.2.0 GA` (2026-05-22, removed `AgentSessionConfig`) → `1.3.0b1` (currently pinned/installed, verified via `pip show` + `inspect.signature(connect)`) → `1.3.0 GA` (changelog-only, not yet on PyPI as of 2026-07-27).
- Rewrote §2.2's ASCII data-flow diagram, §4.2 (API Key + Agent mode code), and §4.3 (Entra ID + Agent mode code) to use the flattened `agent_name="Dr-Wang-Fang", project_name="ai-coach-project"` kwargs, removing all `AgentSessionConfig` imports/usage.
- Added explicit note that §4.2's code shape is identical to production `backend/app/services/voice_live_websocket.py:691-697`.
- Updated §4.4's parameter comparison table (separate `agent_name`/`project_name` rows, `ValueError` if only one provided) and §4.1's `api_version="2026-07-15"` explicit-kwarg convention.
- Preserved §3 (2026-04-08 POC) untouched as a historical record; added a callout directly under its heading clarifying its code shapes are stale but its auth conclusions still hold, pointing readers to new §6 for the current-SDK re-verification.
- Updated §5's Agent-mode advantages bullet to reflect the flattened-kwargs continuation of the "API Key works for Agent mode" finding.

**Task 2 — Wrote and ran a real live Foundry IQ grounding test**
- Created `docs/microsoft-agent-framework/tests/test_agent_foundry_iq_grounding.py`, a live test script (styled after `test_agent_auth_v2.py`) that:
  - Connects in Agent mode to `Dr-Wang-Fang` using SDK 1.3.0b1's flattened `connect(agent_name=, project_name=)` kwargs.
  - Sends a KB-specific question (zanubrutinib dosage/storage/indication, answerable only from the `omada-product-parameters-kb` Foundry IQ knowledge base) as Turn 1, and an unrelated control question (cross-department communication) as Turn 2, on the same connection.
  - Collects and classifies every server event, specifically watching for `mcp_list_tools.*`/`response.mcp_call*` events as the grounding-trigger signal.
- Confirmed DB precondition before running (`hcp_profiles.agent_sync_status="synced"` for Dr-Wang-Fang; `hcp_knowledge_configs.is_enabled=1` for `omada-product-parameters-kb`) — no setup work needed.
- First live run failed at the WebSocket handshake with a 403 using API Key credentials (see Deviations below); debugged and confirmed via a targeted comparison that the `.env` key is byte-identical to what production's `config_service.get_effective_key()` resolves, ruling out key staleness/mismatch, and confirmed the same key also fails for Model mode (not Agent-mode-specific).
- Refactored the script to fall back to `DefaultAzureCredential()` (Entra ID) when API Key fails to establish a usable session, and re-ran — this succeeded and produced the real Turn 1/Turn 2 results below.

**Task 3 — Recorded real results in a new dated doc 02 section**
- Appended §6 "Agent 模式 + Foundry IQ 知识库 grounding：真实实测（2026-07-27，SDK 1.3.0b1）" with subsections covering preconditions, test script/environment, the API-Key-403 finding, Turn 1 and Turn 2 real event sequences and outcomes, a "部分确认" (partially confirmed) conclusion, and a version-applicability caveat.

## Real Test Results (unedited, as observed)

- **API Key auth**: returns 403 on WebSocket handshake for both Model mode and Agent mode on the current `ai-foundary-hu-sweden-central2` resource — contradicts the historical 2026-04-08 POC's "API Key + Agent works" finding for this SDK/environment combination (see doc 02 §6.3).
- **Entra ID auth**: connects successfully in the same process/session immediately after the API Key failure.
- **Turn 1 (KB question)**: `mcp_list_tools.in_progress` fired — proving the Agent's attached Foundry IQ knowledge base MCP tool was transparently invoked with zero Voice Live-side configuration. However, `response.done` reported `status=FAILED` with `status_details` showing the AI Search MCP endpoint (`https://ai-search-southeast-asia.search.windows.net/knowledgebases/omada-product-parameters-kb/mcp`) returned **HTTP 403 Forbidden** while enumerating tools. Turn 1 produced zero text response.
- **Turn 2 (control question)**: No `mcp_list_tools.*`/`response.mcp_call*` events fired (correct — unrelated to KB). `response.done` reported `status=COMPLETED` with a full 604-character text response about cross-department communication challenges.
- **Conclusion (doc 02 §6.6)**: "部分确认" — the *triggering mechanism* (Voice Live Agent mode transparently invokes whatever MCP tools the Agent has mounted, selectively based on question relevance) is proven real. Full end-to-end grounding (retrieved KB content appearing in the final answer) could not be verified because the downstream AI Search MCP endpoint itself rejected the tool-enumeration call.

## Task Commits

| Task | Commit | Message |
|------|--------|---------|
| 1 | `b4e113a` | docs(quick-260727-cnd): correct doc 02 SDK version and connect() code examples |
| 2 | `0fc0316` | test(quick-260727-cnd): add live Agent-mode + Foundry IQ grounding POC script |
| 3 | `e8236d0` | docs(quick-260727-cnd): record real Foundry IQ grounding test results in doc 02 |

## Files Created/Modified

- **Created**: `docs/microsoft-agent-framework/tests/test_agent_foundry_iq_grounding.py`
- **Modified**: `docs/microsoft-agent-framework/02-model-vs-agent-mode.md` (Task 1 edits to §1-5, Task 3 new §6)

## Decisions Made

1. **Preserve historical record**: §3 (2026-04-08 POC) left unmodified; a callout was added rather than editing history, per the plan's constraint that historical findings should remain a transparent record even when current environment behavior has diverged.
2. **Entra-ID fallback in test script**: Rather than stopping at the API-Key 403 (which would have prevented completing the plan's actual grounding-signal test), the script honestly records the 403 first, then falls back to Entra ID — the same credential path production's `_resolve_voice_live_credential()` uses when Entra probing succeeds — to still deliver a real, live grounding-trigger result.
3. **No fix attempted for the two Azure-resource-level 403s** (API Key auth policy change; AI Search MCP endpoint's `ProjectManagedIdentity` authorization): both are infra/permissions issues outside a doc-correction quick task's scope, and the threat model's accepted risk explicitly excluded persistent changes to the agent/resource configuration. Both are logged in `deferred-items.md`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking issue] Test script's `connect()` call needed Entra ID fallback due to real API Key 403**
- **Found during:** Task 2, first live run
- **Issue:** API Key credential (matching production's resolved key byte-for-byte) returned 403 at the WebSocket handshake for both Model and Agent mode — a blocking issue preventing the plan's core deliverable (live grounding-signal capture).
- **Fix:** Refactored `_run_session()`/`main()` to attempt API Key first (recording the 403 honestly), then fall back to `DefaultAzureCredential()` (Entra ID), which connected successfully and allowed both test turns to run for real.
- **Files modified:** `docs/microsoft-agent-framework/tests/test_agent_foundry_iq_grounding.py`
- **Commit:** `0fc0316`

**2. [Rule 1 - Bug] `_run_turn()` did not check `response.status` on `response.done`, silently swallowing the real Turn 1 failure**
- **Found during:** Task 2, debugging Turn 1's "no text response, no visible error" symptom
- **Issue:** The original code treated any `response.done` event as a clean stream-end signal without inspecting `response.status`/`status_details`, so `ResponseStatus.FAILED` (with the AI Search 403 detail) was discarded silently.
- **Fix:** Added a status check that surfaces `status_details` as `error_detail` when status is FAILED, printing the real error instead of a generic "no response" message.
- **Files modified:** `docs/microsoft-agent-framework/tests/test_agent_foundry_iq_grounding.py`
- **Commit:** `0fc0316`

**3. [Rule 1 - Bug] Event-collection loop cap of 200 truncated Turn 2's completion before `response.done` arrived**
- **Found during:** Task 2, observing Turn 2 report "partial response" despite the model clearly finishing
- **Issue:** `for _ in range(200)` was consumed almost entirely by ~195 `response.text.delta` events for a long streamed reply, leaving no iterations for `response.text.done`/`response.done` to be collected.
- **Fix:** Bumped the loop cap to `range(800)`; re-run produced the complete 604-character response and a clean `status=COMPLETED` `response.done`.
- **Files modified:** `docs/microsoft-agent-framework/tests/test_agent_foundry_iq_grounding.py`
- **Commit:** `0fc0316`

### Out-of-scope items (deferred, not fixed)

Logged in `.planning/quick/260727-cnd-update-02-model-vs-agent-mode-md-for-lat/deferred-items.md` (not committed — orchestrator handles docs-artifact commits):

1. **AI Search MCP endpoint 403 while enumerating tools** — the `RemoteTool`/`ProjectManagedIdentity` authorization chain (doc 06 §4) rejects the Agent's KB tool-enumeration call. Requires ARM-level investigation of the AI Search resource's role assignments; out of scope for this SDK/doc-correction task.
2. **API Key authentication now returns 403 broadly** (Model and Agent mode, this resource) — a resource-level auth-policy change contradicting the 2026-04-08 POC. Recommended follow-up: confirm via targeted logging whether production is already relying on the Entra-ID fallback path rather than the (now-broken) API-Key path.

## Verification Performed

All plan verification greps confirmed on the final state of `docs/microsoft-agent-framework/02-model-vs-agent-mode.md`:
- No remaining `agent_config=`/`AgentSessionConfig` references
- `agent_name="Dr-Wang-Fang"` present in the corrected code examples
- `1.3.0b1` present (current pinned version correctly documented)
- `mcp_list_tools`/`mcp_call` event names present in the new §6 real-results section
- `2026-07-27` date present on the new §1.1 and §6 sections
- `omada-product-parameters-kb` present, matching the actual DB-configured knowledge base

## Issues Encountered

None beyond the three auto-fixed deviations above (all resolved within the task; no unresolved blockers for the doc-correction deliverable itself). The two deferred Azure-resource-level 403s are pre-existing environment conditions, not regressions introduced by this task.

## User Setup Required

None. No environment configuration, secrets, or manual steps are needed to consume this doc/test-script update. (The deferred items, if picked up as follow-up work, would require Azure Portal/CLI access to the AI Search and Cognitive Services resources' IAM configuration — not part of this task.)

## Next Phase Readiness

Doc 02 is now consistent with the actually-installed SDK (`1.3.0b1`) and production's real `connect()` call shape, unblocking any future doc-driven onboarding or code review that references it. The two deferred 403 findings are actionable follow-up items for a separate infra/permissions-focused task; §6.7 recommends re-running `test_agent_foundry_iq_grounding.py` once SDK `1.3.0` GA is available on PyPI to confirm whether either 403 has changed.

## Known Stubs

None. No UI/data-flow stubs were introduced — this task only touched documentation and a standalone test script.

## Threat Flags

None. The new test script only performs read-only WebSocket connections/turns against an existing, already-synced agent and does not modify any persistent Azure resource state, matching the plan's threat model's accepted-risk boundary.

## Self-Check: PASSED

- FOUND: docs/microsoft-agent-framework/02-model-vs-agent-mode.md
- FOUND: docs/microsoft-agent-framework/tests/test_agent_foundry_iq_grounding.py
- FOUND: .planning/quick/260727-cnd-update-02-model-vs-agent-mode-md-for-lat/260727-cnd-SUMMARY.md
- FOUND: .planning/quick/260727-cnd-update-02-model-vs-agent-mode-md-for-lat/deferred-items.md
- FOUND: commit b4e113a
- FOUND: commit 0fc0316
- FOUND: commit e8236d0
