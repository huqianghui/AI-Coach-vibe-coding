# Deferred Items — Quick Task 260727-cnd

Items discovered during execution that are out of scope for this quick task
(doc 02 SDK-version correction + Foundry IQ grounding test) and are logged
here rather than fixed, per the deviation rules' scope boundary.

## Item 1: AI Search MCP endpoint returns 403 when the Agent enumerates KB tools

**Discovered during:** Task 2 (live test run of `test_agent_foundry_iq_grounding.py`)

**Real observed error** (from `response.done`'s `status_details` on the KB-grounded turn):

```
Foundry agent service API error: Access denied when connecting to the MCP server at
https://ai-search-southeast-asia.search.windows.net:443/knowledgebases/omada-product-parameters-kb/mcp
?api-version=**** while enumerating tools (HTTP 403 Forbidden). Please verify:
(1) your credentials have the necessary permissions to access this server,
(2) any IP allowlists or network policies permit requests from this service, and
(3) the server's access control configuration allows the requested operation.
```

**Why deferred:** This is a failure inside the AI Search `RemoteTool` connection's
`ProjectManagedIdentity` authorization chain (see `docs/microsoft-agent-framework/06-agent-tools-and-knowledge-grounding.md`
§4), not a Voice Live SDK or doc-02 `connect()` call-shape issue -- outside this quick
task's scope (correcting doc 02's SDK version state + code examples). Investigating and
fixing the RemoteTool connection's permissions would require ARM-level changes to the
AI Search resource and/or re-running `agent_sync_service.sync_agent_for_profile()`, which
is a separate, non-trivial piece of work and was explicitly out of scope per this task's
threat model (accepted risk: "no persistent state change to the agent definition itself").

**Recommendation:** File as a follow-up investigation: verify the `ProjectManagedIdentity`
role assignment on the `aisearchsoutheastasia5e88p4` AI Search resource still grants the
Foundry project's managed identity access to the `omada-product-parameters-kb` knowledge
base MCP endpoint. Confirmed still-triggering signal: `mcp_list_tools.in_progress` fires
correctly (the Agent/Voice Live side of the integration works); the 403 happens one layer
deeper, at the AI Search MCP endpoint itself.

## Item 2: API Key authentication now returns 403 for both Model mode and Agent mode

**Discovered during:** Task 2 (live test run)

**Real observed error:**

```
ConnectionError: Failed to establish WebSocket connection: 403, message='Invalid response status',
url='wss://ai-foundary-hu-sweden-central2.services.ai.azure.com/voice-live/realtime?api-version=2026-07-15&agent-name=Dr-Wang-Fang&agent-project-name=avarda-demo-prj'
```

Confirmed via a direct one-off script run that the same 403 occurs for **Model mode**
too (`connect(endpoint=, credential=AzureKeyCredential(key), api_version="2026-07-15",
model="gpt-4o")`), so this is not an Agent-mode-specific regression. The key used is
byte-identical to the one production code resolves via
`config_service.get_effective_key(db, "azure_voice_live")` -- ruled out a stale/wrong key
in `.env` vs the DB config. `DefaultAzureCredential()` (Entra ID) connects successfully
against the same endpoint/API version in the same process.

**Why deferred:** This is a resource-level authentication-policy change on the
`ai-foundary-hu-sweden-central2` Cognitive Services resource, not something this doc-update
quick task can or should fix. It contradicts the 2026-04-08 POC's "API Key + Agent mode
works" finding recorded in doc 02 §3 -- that finding is now stale for the *current* live
environment (2026-07-27), though doc 02 §3 is intentionally left as an unmodified historical
record per the plan's constraints. Doc 02 §6.3 records this new finding transparently and
recommends re-verifying whenever the SDK is next upgraded to `1.3.0` GA.

**Recommendation:** If production code's Entra-first/API-key-fallback logic
(`_resolve_voice_live_credential` in `voice_live_websocket.py`) is currently succeeding in
production, it is very likely succeeding via the Entra-ID path (the Entra probe succeeds
in this environment), not the API-key fallback -- worth confirming with a targeted log
check rather than assuming the API-key path is still exercised in production.
