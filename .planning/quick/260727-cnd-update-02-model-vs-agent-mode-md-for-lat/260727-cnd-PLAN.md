---
phase: quick
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - docs/microsoft-agent-framework/02-model-vs-agent-mode.md
  - docs/microsoft-agent-framework/tests/test_agent_foundry_iq_grounding.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "Every connect() code block in doc 02 matches the real installed SDK (1.3.0b1) call shape -- no AgentSessionConfig import or agent_config= kwarg remains in any code example; agent_name/project_name are passed as flattened top-level kwargs exactly as backend/app/services/voice_live_websocket.py:691-697 does"
    - "Doc 02 states the real SDK version chain (1.2.0b5 doc baseline -> 1.2.0 GA 2026-05-22 removed AgentSessionConfig -> 1.3.0b1 currently pinned/installed -> 1.3.0 GA 2026-07-20 changelog-only, NOT on PyPI as of 2026-07-27) instead of the stale 1.2.0b5 framing"
    - "A live, runnable test script exists that connects in agent mode (flattened kwargs) to the already-synced Dr-Wang-Fang agent and asks a question answerable only from its attached Foundry IQ knowledge base (omada-product-parameters-kb), then asks an unrelated control question in the same session"
    - "The script's real, actually-observed event stream (not invented) is captured, specifically whether mcp_list_tools.* / response.mcp_call.* server events fire for the KB question and do not fire for the control question"
    - "Doc 02 gains a new section reporting these real, observed results (event types, real response text excerpts) dated 2026-07-27, clearly distinguished from the historical 2026-04-08 POC section which stays intact as a historical record"
  artifacts:
    - path: "docs/microsoft-agent-framework/02-model-vs-agent-mode.md"
      provides: "Updated SDK-version-accurate code examples plus new real Foundry IQ grounding test-results section"
    - path: "docs/microsoft-agent-framework/tests/test_agent_foundry_iq_grounding.py"
      provides: "New live POC script: agent-mode connect via flattened kwargs, KB-grounded question + control question, mcp_call/mcp_list_tools event detection"
  key_links:
    - from: "docs/microsoft-agent-framework/02-model-vs-agent-mode.md code blocks"
      to: "backend/app/services/voice_live_websocket.py connect() call"
      via: "identical flattened-kwargs connect(endpoint=, credential=, api_version=, agent_name=, project_name=) shape"
      pattern: "agent_name=agent_name"
    - from: "test_agent_foundry_iq_grounding.py"
      to: "Dr-Wang-Fang Foundry Agent (agent_id=Dr-Wang-Fang, agent_sync_status=synced, HcpKnowledgeConfig index_name=omada-product-parameters-kb, is_enabled=1)"
      via: "connect(agent_name='Dr-Wang-Fang', project_name=AZURE_FOUNDRY_DEFAULT_PROJECT) then a KB-specific conversation turn"
      pattern: "response.mcp_call|mcp_list_tools"
---

<objective>
Rewrite `docs/microsoft-agent-framework/02-model-vs-agent-mode.md` so its SDK version references and `connect()` code examples match the SDK actually pinned/installed in this repo (`azure-ai-voicelive==1.3.0b1`, not the doc's stale `1.2.0b5` baseline), and empirically re-verify -- with a real live test run, not assumption -- that Voice Live agent-mode sessions ground answers in a Foundry IQ knowledge base already attached to the `Dr-Wang-Fang` agent, then record the real results in the doc.

Purpose: Research (`260727-cnd-RESEARCH.md`) found doc 02 has been stale since SDK `1.2.0 GA` (2026-05-22) -- `AgentSessionConfig` was removed and `connect()` now takes flattened `agent_name`/`project_name` kwargs, which is what production code (`voice_live_websocket.py`) already uses. Doc 02's own code examples would raise `ImportError` if copy-pasted today. Separately, the doc has never actually demonstrated Foundry IQ grounding firing inside a live Voice Live agent-mode session -- this task closes that gap with a real, observable test against the `Dr-Wang-Fang` agent, which is already `agent_sync_status="synced"` with an enabled `HcpKnowledgeConfig` pointing at `omada-product-parameters-kb`.
Output: Corrected doc 02 (accurate SDK version state + flattened-kwargs code examples), a new reusable live test script, and a new doc section with real observed grounding-test results.
</objective>

<execution_context>
@/Users/huqianghui/Downloads/1.github/AI-Coach-vibe-coding/.claude/get-shit-done/workflows/execute-plan.md
@/Users/huqianghui/Downloads/1.github/AI-Coach-vibe-coding/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@docs/microsoft-agent-framework/02-model-vs-agent-mode.md
@docs/microsoft-agent-framework/06-agent-tools-and-knowledge-grounding.md
@docs/microsoft-agent-framework/tests/test_agent_auth_v2.py
@.planning/quick/260727-cnd-update-02-model-vs-agent-mode-md-for-lat/260727-cnd-RESEARCH.md
@backend/app/services/voice_live_websocket.py
@backend/app/config.py
</context>

<interfaces>
<!-- Verified directly against the installed SDK (backend/.venv, azure-ai-voicelive==1.3.0b1) and
     production code. Use exactly this shape -- do not reintroduce AgentSessionConfig. -->

```python
# inspect.signature(connect) on installed 1.3.0b1
connect(
    *,
    credential: AzureKeyCredential | AsyncTokenCredential,
    endpoint: str,
    api_version: str = "2026-06-01-preview",   # this project always passes "2026-07-15" explicitly
    model: str | None = None,                   # omit in agent mode
    agent_name: str | None = None,               # flattened kwarg (was AgentSessionConfig["agent_name"])
    project_name: str | None = None,              # required together with agent_name
    agent_version: str | None = None,
    conversation_id: str | None = None,
    authentication_identity_client_id: str | None = None,
    foundry_resource_override: str | None = None,
    query=None, headers=None, connection_options=None, credential_scopes=None,
    **kwargs,
) -> AbstractAsyncContextManager["VoiceLiveConnection"]
# from azure.ai.voicelive.aio import AgentSessionConfig  -> ImportError (removed in 1.2.0 GA)

# Production usage (backend/app/services/voice_live_websocket.py:691-697):
# async with connect(
#     endpoint=cfg["endpoint"], credential=credential, api_version=_api_version,
#     agent_name=agent_name, project_name=project_name,
# ) as azure_conn:

# Real MCP-related ServerEventType members confirmed present in installed SDK (grounding signal):
#   mcp_list_tools.in_progress / .completed / .failed
#   response.mcp_call_arguments.delta / .done
#   response.mcp_call.in_progress / .completed / .failed

# Confirmed precondition (queried directly from backend/ai_coach.db, 2026-07-27):
#   hcp_profiles: id=cb6bce84-5cbc-49c5-8624-f5d56fc5255e, name="Dr. Wang Fang",
#                 agent_id="Dr-Wang-Fang", agent_sync_status="synced"
#   hcp_knowledge_configs: hcp_profile_id=<same id>, index_name="omada-product-parameters-kb",
#                          is_enabled=1, server_label="knowledge-base-omada-product-parameters-kb"
# -> No setup task needed: the agent already has a real, enabled Foundry IQ KB attached and synced.

# Settings:
# backend/app/config.py: voice_live_api_version: str = "2026-07-15"
# backend/.env: AZURE_FOUNDRY_ENDPOINT, AZURE_FOUNDRY_API_KEY, AZURE_FOUNDRY_DEFAULT_PROJECT=avarda-demo-prj
```
</interfaces>

<tasks>

<task type="auto">
  <name>Task 1: Correct doc 02's SDK version state and connect() code examples</name>
  <files>docs/microsoft-agent-framework/02-model-vs-agent-mode.md</files>
  <action>
    Edit the doc in place. Do NOT delete the existing section 3 "2026-04-08" historical POC content or its
    auth conclusion (API Key + Agent mode works) -- that conclusion still holds per production code, only
    the code shapes demonstrating it are stale. Keep the doc's existing Chinese-language style. Make these
    edits:

    1. Immediately after the section 1 intro table, insert a new short subsection titled with a SDK version
       state header (dated 2026-07-27) containing a table of the real version chain: 1.2.0b5 (this doc's
       original baseline, superseded) -> 1.2.0 GA 2026-05-22 (AgentSessionConfig removed, connect() switched
       to flattened kwargs) -> 1.3.0b1 (currently pinned in backend/pyproject.toml AND installed in
       backend/.venv, needed because it supports explicitly passing api_version="2026-07-15") -> 1.3.0 GA
       (CHANGELOG dated 2026-07-20 but NOT yet published to PyPI as of 2026-07-27 -- do not upgrade until
       `pip index versions azure-ai-voicelive` confirms it is installable).

    2. In the section 2.2 Agent-mode data-flow diagram, change the `agent_config={agent_name=...,
       project_name=...}` line to the flattened form `agent_name="Dr-Wang", project_name="..."` (two
       independent kwargs, not a nested dict/object).

    3. Directly below the section 3 heading, add a one-line callout: the data in this section was measured
       against SDK 1.2.0b5 (the AgentSessionConfig era); the auth conclusion (API Key works with Agent mode)
       still holds, but the code shapes in section 4 below have been rewritten for the current SDK -- see the
       new section 6 for a fresh, dated re-verification.

    4. In the section 4.1 Model-mode code block, delete the comment about relying on the SDK's 1.2.0b5
       default api_version, and instead explicitly pass `api_version="2026-07-15"` (matching
       `backend/app/config.py`'s `voice_live_api_version` default), with a comment noting this project never
       relies on the SDK's built-in default api_version.

    5. Rewrite the section 4.2 Agent-mode (API Key) code block to:
       ```python
       from azure.core.credentials import AzureKeyCredential
       from azure.ai.voicelive.aio import connect

       credential = AzureKeyCredential(api_key)  # API Key 在 Agent 模式下仍然可用

       async with connect(
           endpoint=endpoint,
           credential=credential,
           api_version="2026-07-15",      # 显式传递，不依赖 SDK 默认值
           agent_name="Dr-Wang-Fang",      # 扁平化 kwarg，取代已移除的 AgentSessionConfig
           project_name="ai-coach-project",
       ) as connection:
           # 不需要发送 instructions -- Agent 自带
           await connection.send({
               "type": "session.update",
               "session": {"modalities": ["text", "audio"]}
           })
       ```
       Add a one-line note directly below stating this matches production code
       `backend/app/services/voice_live_websocket.py:691-697` exactly.

    6. Rewrite section 4.3 (Entra ID version) the same way -- remove the `AgentSessionConfig` import and
       dict, pass `agent_name=`, `project_name=`, and the optional `agent_version=`/`conversation_id=` as
       flattened kwargs directly to `connect()`.

    7. In the section 4.4 comparison table, replace the single `agent_config` row with two rows for
       `agent_name` and `project_name` (both required together -- SDK raises ValueError if only one is
       given), and update the "SDK 最低版本" row's Agent-mode cell to note flattened kwargs available since
       1.2.0 GA (the 1.2.0b3/b4-era AgentSessionConfig has been removed), plus a note that this project
       currently pins 1.3.0b1.

    8. In section 5's Agent-mode advantages list, update the "API Key works (SDK 1.2.0b5+)" bullet to note it
       remains true under the flattened-kwargs form since 1.2.0 GA, with this project pinned at 1.3.0b1.

    After editing, confirm via grep that no `agent_config=` kwarg usage or `AgentSessionConfig` import
    remains inside any python code block (prose sentences explaining the historical removal are fine and
    expected to remain).
  </action>
  <verify>
    <automated>cd /Users/huqianghui/Downloads/1.github/AI-Coach-vibe-coding && ! grep -q 'agent_config=agent_config' docs/microsoft-agent-framework/02-model-vs-agent-mode.md && ! grep -q 'import connect, AgentSessionConfig' docs/microsoft-agent-framework/02-model-vs-agent-mode.md && grep -q 'agent_name="Dr-Wang-Fang"' docs/microsoft-agent-framework/02-model-vs-agent-mode.md && grep -q '1.3.0b1' docs/microsoft-agent-framework/02-model-vs-agent-mode.md</automated>
  </verify>
  <done>
    Doc has a new version-state table near the top, every section-4 code block uses flattened agent_name=/
    project_name= kwargs with no AgentSessionConfig import, and sections 3/4.4/5 text references the real
    1.3.0b1 pin without contradicting the still-valid historical auth conclusions.
  </done>
</task>

<task type="auto">
  <name>Task 2: Write and run a live agent-mode + Foundry IQ grounding test script</name>
  <files>docs/microsoft-agent-framework/tests/test_agent_foundry_iq_grounding.py</files>
  <action>
    Create `docs/microsoft-agent-framework/tests/test_agent_foundry_iq_grounding.py`, following the existing
    style of `test_agent_auth_v2.py` in the same directory (module docstring explaining purpose/run command,
    `print_header`/`print_result`/`print_info`/`print_event` helpers, `load_dotenv(backend_dir / ".env")`,
    hardcoded `AGENT_NAME = "Dr-Wang-Fang"`, `PROJECT_NAME = os.getenv("AZURE_FOUNDRY_DEFAULT_PROJECT", ...)`).

    Requirements:
    1. Import `connect` only (no `AgentSessionConfig` -- removed from the installed SDK). Use
       `AzureKeyCredential(API_KEY)` from `backend/.env`'s `AZURE_FOUNDRY_API_KEY`/`AZURE_FOUNDRY_ENDPOINT`.
    2. Open exactly one connection with the flattened-kwargs shape: `connect(endpoint=ENDPOINT,
       credential=credential, api_version="2026-07-15", agent_name=AGENT_NAME, project_name=PROJECT_NAME)`.
    3. Send `session.update` with `{"modalities": ["text"]}`, wait for `session.created`/`session.updated`,
       same pattern as `test_agent_auth_v2.py`.
    4. Turn 1 (KB-grounded question): send `conversation.item.create` + `response.create` asking a question
       answerable only from the attached `omada-product-parameters-kb`, e.g. asking the agent to look up and
       state Omada's specific product parameters (dosage, storage conditions, approved indication) and
       explicitly say whether the answer came from its knowledge base retrieval. Collect and print EVERY
       received event's `type` into a list, highlighting via `print_event` whenever the type starts with
       `mcp_list_tools.` or `response.mcp_call` (the grounding signal per the installed SDK's
       `ServerEventType` enum). Keep reading until `response.done` or a per-event timeout, same
       loop-with-timeout pattern as `test_agent_auth_v2.py`.
    5. Turn 2 (control question, same connection): after turn 1's `response.done`, send a second
       `conversation.item.create` + `response.create` with an unrelated general-knowledge question (e.g.
       about cross-department communication challenges, explicitly unrelated to the knowledge base) and
       collect its event stream the same way.
    6. After both turns, print a summary: full event-type counts (via `collections.Counter`) per turn,
       whether any `mcp_list_tools.*`/`response.mcp_call*` event fired in turn 1, whether any fired in turn 2
       (expected: no), and the real final text response for both turns.
    7. Wrap the run in try/except printing `type(e).__name__: str(e)[:300]` on failure, matching the
       defensive style of `test_agent_auth_v2.py` -- one turn's failure must not silently swallow the other.
    8. Guard `if not ENDPOINT or not API_KEY: sys.exit(1)` at the top of `main()`.

    Run it for real: `cd backend && .venv/bin/python3 ../docs/microsoft-agent-framework/tests/test_agent_foundry_iq_grounding.py`.
    Read the actual output. If connection/session setup fails for a fixable reason (wrong kwarg, wrong
    event-field access), fix the script and re-run. Do not fabricate results -- if grounding genuinely does
    not fire, record that as the real (negative) finding for Task 3 rather than softening it.
  </action>
  <verify>
    <automated>cd /Users/huqianghui/Downloads/1.github/AI-Coach-vibe-coding/backend && .venv/bin/python3 ../docs/microsoft-agent-framework/tests/test_agent_foundry_iq_grounding.py</automated>
  </verify>
  <done>
    Script exists, imports only `connect` (no AgentSessionConfig), connects once via flattened agent_name=/
    project_name= kwargs, runs both the KB-grounded turn and the control turn in the same session, and its
    real terminal output states explicitly whether mcp_list_tools.*/response.mcp_call* events fired for
    turn 1 and whether they fired (expected not) for turn 2, plus the real response text for both turns.
  </done>
</task>

<task type="auto">
  <name>Task 3: Record the real Foundry IQ grounding test results in doc 02</name>
  <files>docs/microsoft-agent-framework/02-model-vs-agent-mode.md</files>
  <action>
    Using ONLY the actual output captured from Task 2's script run (copy real event-type lists, real
    response text excerpts, and the real conclusion verbatim -- never invent or soften a result, matching
    this project's established empirical-results-only documentation convention already used in docs 06/10),
    append a new dated section (2026-07-27, SDK 1.3.0b1) titled about Agent-mode + Foundry IQ grounding
    testing to the end of the doc. Include:

    1. Precondition confirmed before running, citing the real DB query: the `Dr-Wang-Fang` agent
       (`hcp_profiles.agent_id="Dr-Wang-Fang"`) has `agent_sync_status="synced"` and an enabled
       `HcpKnowledgeConfig` row (`index_name="omada-product-parameters-kb"`, `is_enabled=1`) -- no setup was
       needed, the KB was already attached via the existing admin flow described in doc 06.
    2. Test script reference (`tests/test_agent_foundry_iq_grounding.py`, run command) and the real SDK
       version it ran against (1.3.0b1).
    3. Real event-type summary for both turns, explicitly stating whether mcp_list_tools.*/
       response.mcp_call.* events were observed for turn 1 and whether they were absent for turn 2, taken
       verbatim from Task 2's actual run.
    4. A short excerpt of the real response text for both turns.
    5. A one-paragraph conclusion stating whether this confirms or refutes the research finding that "Voice
       Live agent-mode sessions transparently use whatever Foundry IQ KB tools the target Agent was synced
       with, with no Voice Live-side KB config needed" -- based purely on what was actually observed, with a
       cross-reference to doc 06 for the underlying Agent-side KB attachment mechanism.
    6. A closing note repeating the version caveat: results apply to SDK 1.3.0b1; re-verify if/when 1.3.0 GA
       becomes installable from PyPI.

    Do not modify sections 1-5 further in this task (Task 1 already corrected them) -- only append the new
    section.
  </action>
  <verify>
    <automated>cd /Users/huqianghui/Downloads/1.github/AI-Coach-vibe-coding && grep -qE 'mcp_list_tools|mcp_call' docs/microsoft-agent-framework/02-model-vs-agent-mode.md && grep -q '2026-07-27' docs/microsoft-agent-framework/02-model-vs-agent-mode.md && grep -q 'omada-product-parameters-kb' docs/microsoft-agent-framework/02-model-vs-agent-mode.md</automated>
  </verify>
  <done>
    Doc 02 has a new section reporting real, observed grounding-test results (event types actually seen,
    real response excerpts, real conclusion) dated 2026-07-27 against SDK 1.3.0b1, distinct from and not
    replacing the historical 2026-04-08 section 3.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Test script -> Azure Voice Live / Foundry Agent | Script sends a real API key (from `backend/.env`) over the network to open a live Voice Live session against the `Dr-Wang-Fang` agent and its attached Foundry IQ knowledge base in the shared `avarda-demo-prj` Foundry project |
| Test script output -> doc 02 | Real response text and event logs from a live KB-grounded question are copied into a committed markdown doc |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-quick-01 | Information Disclosure | `test_agent_foundry_iq_grounding.py` printing | mitigate | Never print the raw API key value; only print status/event types and response text, matching the existing pattern in `test_agent_auth_v2.py` |
| T-quick-02 | Information Disclosure | Doc 02's new section quoting agent response text | accept | The KB content (`omada-product-parameters-kb`) is internal training/demo material already referenced by name in doc 06; excerpting a short answer is consistent with existing doc conventions and carries no real customer PII |
| T-quick-03 | Tampering | Live test creates a conversation turn against a shared demo agent | accept | Text-only, ephemeral conversation turns with no persistent state change to the agent definition itself; no cleanup needed |
</threat_model>

<verification>
- `docs/microsoft-agent-framework/02-model-vs-agent-mode.md` contains no `agent_config=` kwarg usage or `AgentSessionConfig` import in any code block, and its `connect()` examples match `backend/app/services/voice_live_websocket.py:691-697`'s flattened-kwargs shape
- `docs/microsoft-agent-framework/tests/test_agent_foundry_iq_grounding.py` exists and was actually executed against the real Azure Foundry resource, producing a real event-type log for both the KB-grounded and control turns
- Doc 02 contains a new, dated (2026-07-27) section with real observed results (not placeholders) referencing `mcp_list_tools`/`response.mcp_call` events and the `omada-product-parameters-kb` KB
</verification>

<success_criteria>
- Doc 02's SDK version references and code examples are corrected to match the actually installed/pinned `azure-ai-voicelive==1.3.0b1`, with no code that would raise `ImportError` if copy-pasted
- A live, reusable test script empirically confirms (or refutes, if that is the real outcome) that Voice Live agent-mode sessions ground answers via the target Agent's attached Foundry IQ knowledge base, using `mcp_list_tools.*`/`response.mcp_call.*` events as the observable signal
- Doc 02 records only real, observed results from that live run, clearly dated and distinguished from the historical 2026-04-08 POC section
</success_criteria>

<output>
After completion, create `.planning/quick/260727-cnd-update-02-model-vs-agent-mode-md-for-lat/260727-cnd-SUMMARY.md`
</output>
