# Quick Task Research: Update doc 02 for latest azure-ai-voicelive SDK + Foundry IQ testing

**Researched:** 2026-07-27
**Domain:** azure-ai-voicelive SDK / Azure AI Foundry Agent Service / Foundry IQ knowledge bases
**Confidence:** HIGH (SDK facts verified via installed package introspection + official CHANGELOG; Foundry IQ facts MEDIUM via official Microsoft devblog)

## Summary

The task framing ("1.2.0b5 currently installed, 1.2.0 GA released") is **stale relative to this repo's actual state**. `backend/pyproject.toml` already pins `azure-ai-voicelive[aiohttp]==1.3.0b1` (Phase 29 decision), and `backend/.venv` has `1.3.0b1` installed — one full minor version ahead of the `1.2.0` GA the task description references. Doc `02-model-vs-agent-mode.md` was written against `1.2.0b5` and is now **two SDK releases behind production code**. The most important finding: `connect(agent_config=AgentSessionConfig({...}))` — the pattern documented in doc 02 §3–4 — **no longer exists in the installed SDK**. `AgentSessionConfig` was removed; `connect()` now takes flattened keyword arguments (`agent_name`, `project_name`, `agent_version`, `conversation_id`, `authentication_identity_client_id`, `foundry_resource_override`) directly. Production code (`backend/app/services/voice_live_websocket.py:691-697`) already uses the new flattened form — doc 02's code examples do not match the code that actually ships.

Separately, a `1.3.0` **GA** changelog entry (dated 2026-07-20, one week before this research) exists in the `azure-sdk-for-python` GitHub repo's `main` branch CHANGELOG.md, but **is not yet published to PyPI** as of 2026-07-27 (PyPI simple index still lists `1.3.0b1` as the newest release). This is a "documented but not yet shippable" state the planner should be aware of — do not upgrade to a package that doesn't exist on PyPI yet; keep the `1.3.0b1` pin until `1.3.0` actually appears.

Foundry IQ is Microsoft's enterprise knowledge platform (announced at Build 2026, June 2026), built on Azure AI Search's agentic retrieval engine, exposed to agents via an MCP endpoint. This matches exactly what doc 06 already implements (`MCPTool` + `/knowledgebases/{name}/mcp` endpoint) — the project's existing Knowledge Base feature (`knowledge_base_service.py`) **is** a Foundry IQ integration, just built before the "Foundry IQ" brand name existed. A Voice Live agent-mode session does not need any special Voice Live–side config to use Foundry IQ: the KB tools live on the Agent (server-side), and Voice Live's `agent_name`/`project_name` kwargs simply route the session to that pre-configured Agent. Grounding can be verified by watching for `response.mcp_call.*` / `mcp_list_tools.*` server events during the session (confirmed to exist in the installed SDK's `ServerEventType` enum).

**Primary recommendation:** Rewrite doc 02 §3–4 code examples around the flattened `connect(agent_name=..., project_name=...)` kwargs (drop all `AgentSessionConfig` references), correct the SDK version references (1.2.0b5 → 1.3.0b1), and add a new §6 "Agent + Foundry IQ" section describing the test procedure below using `response.mcp_call.*` events as the grounding-verification signal.

## User Constraints

No CONTEXT.md exists for this quick task — no locked decisions to honor beyond the task's own focus questions. Project-wide constraint from CLAUDE.md: multi-requirement work must be done one at a time with full test coverage before commit — not directly applicable to a doc-update-only task, but any code changes to test files should still follow the pytest conventions in `backend/tests/`.

## Project Constraints (from CLAUDE.md)

- English for commit messages, code comments, docstrings; Chinese for user-facing UI text (docs in this directory are Chinese by established convention — preserve that).
- Conventional commits (`docs:`, `fix:`, etc.)
- No raw SQL, async-everywhere — not directly relevant to this doc-only task.
- GSD workflow enforcement: file edits should happen through a `/gsd:*` command context (this research is being produced for exactly that purpose).

## Findings

### 1. SDK version state: 1.2.0b5 (doc) → 1.3.0b1 (installed/pinned) → 1.3.0 GA (changelog-only, not on PyPI)

**[VERIFIED: pip show / PyPI JSON API / PyPI simple index, checked 2026-07-27]**

| Version | Status | Release date | On PyPI? |
|---------|--------|---------------|----------|
| 1.2.0b5 | superseded (doc 02's baseline) | 2026-04-06 | yes |
| 1.2.0 | GA | 2026-05-22 | yes |
| 1.3.0b1 | **currently pinned in `backend/pyproject.toml`, installed in `.venv`** | 2026-05-28 | yes |
| 1.3.0 | GA per CHANGELOG.md on `main` branch | 2026-07-20 | **no** — not in `pypi.org/simple/azure-ai-voicelive/` as of 2026-07-27 |

`backend/pyproject.toml:56`: `"azure-ai-voicelive[aiohttp]==1.3.0b1"`. Confirmed installed: `pip show azure-ai-voicelive` → `Version: 1.3.0b1`.

Per `.planning/STATE.md` Phase 29 decisions: pin-beta was deliberately chosen over the `1.2.0` GA because `1.2.0` GA does not support `api_version="2026-07-15"` (the GA API version the project standardized on) — `1.3.0b1`'s default was `2026-06-01-preview`, and the project explicitly overrides `api_version` at every `connect()` call site to `2026-07-15` regardless of SDK default.

**Action for planner:** Do NOT bump to `1.3.0` yet — it isn't installable via pip. Track it as a follow-up once published. Doc 02 should state the current pin explicitly (`1.3.0b1`) rather than `1.2.0b5`.

### 2. BREAKING CHANGE: `AgentSessionConfig` removed, `connect()` uses flattened kwargs

**[VERIFIED: installed SDK introspection + official CHANGELOG.md]**

```python
>>> from azure.ai.voicelive.aio import AgentSessionConfig
ImportError: cannot import name 'AgentSessionConfig' from 'azure.ai.voicelive.aio'
```

Actual `connect()` signature in installed `1.3.0b1` (via `inspect.signature`):

```python
connect(
    *,
    credential: AzureKeyCredential | AsyncTokenCredential,
    endpoint: str,
    api_version: str = "2026-06-01-preview",
    model: str | None = None,
    agent_name: str | None = None,
    project_name: str | None = None,
    agent_version: str | None = None,
    conversation_id: str | None = None,
    authentication_identity_client_id: str | None = None,
    foundry_resource_override: str | None = None,
    query: Mapping[str, Any] | None = None,
    headers: Mapping[str, Any] | None = None,
    connection_options: WebsocketConnectionOptions | None = None,
    credential_scopes: str | Sequence[str] | None = None,
    **kwargs,
) -> AbstractAsyncContextManager["VoiceLiveConnection"]
```

Docstring confirms: `model` "may be omitted only when connecting through an Agent scenario" and "`agent_name`: ... When set, `project_name` is also required." Raises `ValueError` if only one of `agent_name`/`project_name` is given.

Per CHANGELOG.md, this flattening happened in the **1.2.0 GA** release (2026-05-22): *"Agent Session Configuration: Added flattened `connect()` keyword arguments for configuring Azure AI Foundry agents at connection time with `agent_name`, `project_name`, `agent_version`, `conversation_id`, and more"* — paired with a breaking change: *"Removed Foundry Agent Tool classes (`FoundryAgentTool`, `ResponseFoundryAgentCallItem`, etc.) — use flattened Azure AI Foundry keyword arguments with `connect()` instead."*

Note: doc 02's existing `AgentSessionConfig` dict pattern (`agent_config: AgentSessionConfig = {"agent_name": ..., "project_name": ...}`, passed as `connect(agent_config=agent_config)`) was itself only ever a `1.2.0b3`/`b4` shape (`FoundryAgentTool`-era) — it was already obsolete by `1.2.0` GA, well before `1.3.0b1`. Doc 02 has been stale since **1.2.0 GA (2026-05-22)**, not just since `1.3.0b1`.

**Confirmed matching production code** (`backend/app/services/voice_live_websocket.py:691-697`):
```python
async with connect(
    endpoint=cfg["endpoint"],
    credential=credential,
    api_version=_api_version,
    agent_name=agent_name,
    project_name=project_name,
) as azure_conn:
```
No `agent_config=` or `AgentSessionConfig` anywhere in `backend/app/` — `grep` confirms zero matches. Doc 02 needs its §3–4 code blocks rewritten to this exact shape.

### 3. Other changes between 1.2.0b5 → 1.2.0 → 1.3.0b1 relevant to this project

**[VERIFIED: official CHANGELOG.md, `azure-sdk-for-python` repo, `main` branch]**

- **Default `api_version` bumped twice**: `2026-01-01-preview` (1.2.0b5) → `2026-04-10` (1.2.0 GA) → `2026-06-01-preview` (1.3.0b1) → `2026-07-15` GA (1.3.0, not yet on PyPI). Irrelevant to this project in practice since `api_version` is always passed explicitly (D-02 decision), but doc 02 currently states "SDK 默认值 1.2.0b5 默认 2026-01-01-preview" — this line is stale and should be updated or removed since the project no longer relies on SDK defaults.
- **`OutputAudioFormat` enum values** changed from hyphenated (`pcm16-8000hz`) to underscore (`pcm16_8000hz`) in 1.2.0 GA — legacy values still deserialize for backward compat.
- **`AvatarConfig.type` renamed to `avatar_type`** in 1.2.0 GA (Python `type` builtin collision) — check if `backend/app/services/voice_live_websocket.py` or avatar config code references `.type` on an `AvatarConfig` instance; if so this is a live breaking-change risk, not just docs.
- **MCP (Model Context Protocol) support added in 1.2.0 GA** at the Voice Live SDK level (`MCPServer`, `MCPTool`, `MCPApprovalType` in `azure-ai-voicelive`, distinct from the `azure.ai.projects.models.MCPTool` used server-side in doc 06's Agent-Foundry-IQ flow) — new server events `mcp_list_tools.*`, `response.mcp_call.*` were added. These are the events needed to verify Foundry IQ grounding in a Voice Live session (see Finding 5).
- **1.3.0b1 added**: `agent_name`/`project_name` flattening was already in 1.2.0 GA; 1.3.0b1's own additions are OpenTelemetry-adjacent (Agent v2 telemetry fields), `AzureRealtimeNativeVoice`, input text streaming (`ClientEventInputTextDelta`), image content support, `parallel_tool_calls`. None of these are breaking for agent-mode connect() shape.
- **1.3.0 GA (changelog-only, not released)** would additionally remove three 1.3.0b1-preview-only features if/when it ships: WebRTC call SDP negotiation events, audio playback lifecycle events, and `SmartEndOfTurnDetection` — worth flagging as a future-breaking-change watch item, not an action now.

### 4. API Key + Agent mode: still supported, unchanged

**[VERIFIED: code path unchanged]** `credential: AzureKeyCredential | AsyncTokenCredential` remains a valid type for `connect()` in 1.3.0b1 regardless of whether `agent_name`/`project_name` are set — nothing in the signature or docstring restricts `AzureKeyCredential` to model-mode-only. Combined with `.planning/STATE.md` Phase 29 confirmation that production code uses this successfully, doc 02's core claim ("API Key + Agent mode 可行, 推翻微软文档声明") **remains valid** and doesn't need re-testing for this doc update — only the code examples demonstrating it need to be rewritten to the flattened-kwargs shape. `[ASSUMED]`: the exact behavioral nuances found in the original 2026-04-08 POC (STS token 401, etc.) likely still hold since nothing in the changelog mentions authentication-channel changes, but this has not been re-run against 1.3.0b1 in this research session.

### 5. Foundry IQ: what it is, and how Voice Live agent mode uses it

**[CITED: https://devblogs.microsoft.com/foundry/build-smarter-agents-faster-with-foundry-iq/, announced Build 2026 / June 2026]**

- **Foundry IQ** = Microsoft's enterprise knowledge platform: a **knowledge base** (unified container) aggregates data from multiple **knowledge sources** (Work IQ / emails+Teams, Fabric IQ, File Search, Azure SQL, MCP servers, Web IQ, Blob Storage, OneLake). It sits on top of **Azure AI Search's agentic retrieval engine** (the blog claims up to 20% answer-quality improvement from recent retrieval enhancements).
- **Agent attachment mechanism**: Foundry IQ exposes each knowledge base via an **MCP server endpoint**, consumable "from any MCP-compatible host or client." This is exactly the `{search_endpoint}/knowledgebases/{kb_name}/mcp?api-version=...` pattern already implemented in this repo's `knowledge_base_service.py` and documented in doc 06 §2 — i.e., **doc 06's existing implementation already is a Foundry IQ integration**, just predating the public "Foundry IQ" brand.
- **Pricing/tier (Public Preview, Developer/Serverless tier)**: $0.24/Compute-Unit-hour, up to $0.29/GB-month storage, 1GB per index, 30 indexes/service, 5 services/subscription/region. Billing starts late 2026 with 30-day notice. `[CITED]` — no exact region list surfaced by the blog; regions/prerequisites beyond "Azure AI Search resource + Foundry project" are `[ASSUMED]` to match the existing Azure AI Search / RemoteTool-connection prerequisites already documented in doc 06 §4 (ARM-based RemoteTool connection, `ProjectManagedIdentity` auth) — this should be flagged as an open question, not treated as settled.
- **Does Voice Live agent mode "see" Foundry IQ automatically?** Yes, architecturally: knowledge/tool configuration lives on the **Agent** (server-side, in AI Foundry), not in the Voice Live session config. Voice Live's `agent_name`/`project_name` kwargs just route the session to a pre-existing Agent; whatever `tools=[MCPTool(...)]` that Agent was created/updated with (via `agent_sync_service.py` → `knowledge_base_service.build_search_tools()`) is used transparently during the session. No Voice Live–specific KB wiring is needed beyond having a **synced Agent whose HcpProfile has an enabled `HcpKnowledgeConfig`** pointing at a real Foundry IQ knowledge base.

### 6. How to test "agent mode + Foundry IQ" from this repo

**[VERIFIED: SDK event introspection]** — Query of the installed SDK's `ServerEventType` enum confirms these MCP-related server events exist and are the mechanism to detect grounding:
```
mcp_list_tools.in_progress
mcp_list_tools.completed
mcp_list_tools.failed
response.mcp_call_arguments.delta
response.mcp_call_arguments.done
response.mcp_call.in_progress
response.mcp_call.completed
response.mcp_call.failed
```

**Minimal test procedure (adapting `test_agent_auth_v2.py`):**

1. **Prerequisite (one-time, via existing admin flow, not new code):** Ensure the target agent (e.g., `Dr-Wang-Fang`) has at least one enabled `HcpKnowledgeConfig` row pointing at a real Foundry IQ knowledge base, and that `agent_sync_service.sync_agent_for_profile()` has run successfully (`agent_sync_status == "synced"`, not `"failed"`). Without this, the Agent has no `MCPTool` attached and there is nothing to ground against.
2. **Update the connect() call** in a copy of `test_agent_auth_v2.py` to the flattened-kwargs form matching production code:
   ```python
   async with connect(
       endpoint=ENDPOINT,
       credential=credential,
       api_version="2026-07-15",   # match settings.voice_live_api_version, not SDK default
       agent_name=AGENT_NAME,
       project_name=PROJECT_NAME,
   ) as connection:
   ```
   (Remove the `agent_config: AgentSessionConfig = {...}` block entirely — that type no longer imports.)
3. **Ask a question that can only be answered from the indexed knowledge base**, not general LLM knowledge — e.g., a specific numeric product parameter or clinical-trial detail that exists only in the material uploaded to that KB (per doc 06's example KB `omada-product-parameters-kb`).
4. **Capture and log every received event's `type`.** Assert that the event stream includes at least one `response.mcp_call.completed` (or `in_progress`) event before the final `response.done` — this is positive proof the Agent actually invoked `knowledge_base_retrieve` against the Foundry IQ KB, rather than just hallucinating a plausible-sounding answer. Absence of any `mcp_call.*` event despite a KB-specific question is a strong signal the KB isn't actually attached/synced (agent_sync_status check in step 1 should have caught this, but the live event stream is the ground truth).
5. **Compare against a control**: ask the same agent (same `agent_name`) an unrelated general-knowledge question and confirm no `mcp_call.*` event fires — proves the KB tool is being invoked selectively, not on every turn (expected `require_approval="never"` + `allowed_tools=["knowledge_base_retrieve"]` behavior per doc 06 §2.4).

**Env vars available in `backend/.env` for this test (names only, no values printed):** `AZURE_FOUNDRY_ENDPOINT`, `AZURE_FOUNDRY_API_KEY`, `AZURE_FOUNDRY_DEFAULT_PROJECT`. No dedicated `AGENT_NAME` env var exists — all existing test files hardcode `AGENT_NAME = "Dr-Wang-Fang"` as a literal. `AZURE_TENANT_ID` also exists in `.env` (used for `DefaultAzureCredential`/Entra ID paths, not required for the API-Key test path).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|--------------|-----|
| Attaching a knowledge base to a Foundry Agent | Custom RAG pipeline calling Azure AI Search directly from the Voice Live proxy | Existing `knowledge_base_service.py` (`resolve_kb_remote_tool_connections` + `build_search_tools` + `MCPTool`) | Already implements the exact Foundry IQ MCP pattern; duplicating it in the voice path would create two divergent KB-attachment code paths |
| Detecting whether an Agent's reply used retrieved knowledge | String-matching the reply text for KB content | Watch `response.mcp_call.*` server events during the session | Deterministic, SDK-native signal; text-matching is fragile and language-dependent (agent may paraphrase) |

## Common Pitfalls

### Pitfall 1: Copying doc 02's current code examples verbatim
**What goes wrong:** `ImportError: cannot import name 'AgentSessionConfig'` — the type was removed in 1.2.0 GA.
**Why it happens:** Doc 02 was written against 1.2.0b5/b4-era `FoundryAgentTool` classes, which were replaced by flattened kwargs before 1.3.0b1 even existed.
**How to avoid:** Always cross-check doc code examples against `backend/app/services/voice_live_websocket.py` (production usage) before trusting a docs snippet in this repo — the docs have lagged the code by at least one SDK GA cycle before.
**Warning signs:** Any doc referencing `agent_config=` or `AgentSessionConfig`.

### Pitfall 2: Assuming `1.3.0` GA is installable because the CHANGELOG says it exists
**What goes wrong:** `pip install azure-ai-voicelive==1.3.0` fails — the GitHub CHANGELOG.md on `main` is ahead of the actual PyPI publish.
**Why it happens:** Azure SDK release process merges the CHANGELOG entry before/during the release pipeline; there can be a lag (observed: at least 7 days as of this research) between changelog merge and PyPI availability.
**How to avoid:** Always verify with `pip index versions azure-ai-voicelive` or the PyPI JSON API, not just the GitHub changelog, before recommending a version bump.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|----------------|
| A1 | STS-token-401 and Entra-ID-agent-mode behavior from the original 2026-04-08 POC still holds unchanged on 1.3.0b1 | Finding 4 | If auth behavior changed silently between SDK versions, doc 02's auth table would need re-verification via a fresh POC run, not just a code-example rewrite |
| A2 | Foundry IQ region/prerequisite list matches the existing Azure AI Search + RemoteTool-connection prerequisites already in doc 06 | Finding 5 | If Foundry IQ (the newly-branded product) has its own separate region rollout or preview enrollment step beyond "have an AI Search resource," the test procedure in Finding 6 could fail with an unexpected 403/404 not covered by doc 06's pitfall table |

**If this table is empty:** N/A — see above, two items need confirmation before being treated as locked fact.

## Open Questions

1. **Is `1.3.0` GA available on PyPI yet at execution time?**
   - What we know: not published as of 2026-07-27 research date; changelog entry exists on `main` branch dated 2026-07-20.
   - What's unclear: exact PyPI publish date (could be days away).
   - Recommendation: re-check `pip index versions azure-ai-voicelive` immediately before doc update execution; if now available, document both `1.3.0b1` (current pin) and `1.3.0` (available upgrade, not yet adopted) rather than silently upgrading the pin as part of a docs-only task.

2. **Does the currently-synced `Dr-Wang-Fang` agent already have a Foundry IQ KB attached, or does the test procedure require first creating one via the admin UI?**
   - What we know: doc 06 describes the full KB-attach flow and references example KBs (`omada-product-parameters-kb`, `product-kb`, `clinical-trials-kb`) as illustrative names, not confirmed-live resources.
   - What's unclear: whether any `HcpKnowledgeConfig` row currently exists with `is_enabled=True` for a real Foundry IQ KB in this environment.
   - Recommendation: query `hcp_knowledge_configs` table (or the admin UI) before attempting the live test in Finding 6 — if none exists, step 1 of the test procedure must be executed first as a setup precondition, not assumed.

## Sources

### Primary (HIGH confidence)
- Installed package introspection (`backend/.venv`, `azure-ai-voicelive==1.3.0b1`): `inspect.signature(connect)`, `inspect.getsource(connect)`, `ServerEventType` enum enumeration, `AgentSessionConfig` import failure — all run directly against the project's own virtualenv.
- `backend/pyproject.toml:56`, `backend/app/services/voice_live_websocket.py:660-759` — production code, read directly.
- `backend/.env` (names only), `.planning/STATE.md` (Phase 29 decisions D-02/D-14).
- PyPI JSON API (`https://pypi.org/pypi/azure-ai-voicelive/json`) and PyPI simple index (`https://pypi.org/simple/azure-ai-voicelive/`) — queried 2026-07-27.

### Secondary (MEDIUM confidence)
- [azure-ai-voicelive CHANGELOG.md](https://raw.githubusercontent.com/Azure/azure-sdk-for-python/main/sdk/voicelive/azure-ai-voicelive/CHANGELOG.md) — official Azure SDK repo, `main` branch, fetched 2026-07-27. Contains the not-yet-released `1.3.0 (2026-07-20)` entry — treat with the caveat in Open Question 1.
- [Foundry IQ: Build smarter agents faster with unified knowledge and serverless retrieval](https://devblogs.microsoft.com/foundry/build-smarter-agents-faster-with-foundry-iq/) — official Microsoft Foundry devblog, June 2026.

### Tertiary (LOW confidence)
- None used directly in final claims (WebSearch tool was non-functional this session — all findings sourced from WebFetch against official/authoritative URLs or direct code/package introspection instead).

## Metadata

**Confidence breakdown:**
- SDK version/API facts: HIGH — verified directly against installed package and production code, not just docs
- Foundry IQ conceptual facts: MEDIUM — single official source (devblog), no second independent source cross-checked (WebSearch was unavailable this session)
- Test procedure: HIGH for the event-detection mechanism (verified via enum introspection), MEDIUM for the "agent already has a KB attached" precondition (unverified — see Open Question 2)

**Research date:** 2026-07-27
**Valid until:** ~14 days (fast-moving: SDK 1.3.0 GA PyPI publish is imminent and would immediately date this doc further)
