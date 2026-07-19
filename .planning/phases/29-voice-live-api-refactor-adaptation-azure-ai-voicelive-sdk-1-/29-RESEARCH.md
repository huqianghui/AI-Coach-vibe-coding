# Phase 29: Voice Live API Refactor & Adaptation (azure-ai-voicelive 1.3.0) - Research

**Researched:** 2026-07-19
**Domain:** Azure AI Voice Live SDK upgrade, dual-path agent architecture, HCP data model cleanup, AI Foundry model catalog
**Confidence:** MEDIUM-HIGH (SDK version/timeline finding is HIGH confidence but surfaces a blocking risk; codebase findings are HIGH; D-14 Foundry API approach is HIGH; a few CONTEXT.md decision-scope ambiguities are flagged as Open Questions)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**SDK 1.3.0 升级与认证策略**
- **D-01:** Voice Live WebSocket 认证采用 **Entra 优先 + API Key 回退**——有 Entra 凭据（服务主体/DefaultAzureCredential）时用 Entra，否则回退 API Key。两条认证路径都要有测试覆盖
- **D-02:** api-version **全部统一到 GA `2026-07-15`**，集中到单一常量/配置项（WebSocket + WebRTC 共用），删除所有 preview 版本引用（`2026-01-01-preview`、`2025-05-01-preview`、独立的 `WEBRTC_API_VERSION`）
- **D-03:** SDK 版本 pin 为 `azure-ai-voicelive[aiohttp]>=1.3.0,<2.0`
- **D-04:** 实施顺序：**先独立 POC 脚本验证** 1.3.0 的 Agent 连接/认证/会话配置（照 1.2.0b5 POC 模式），确认可行后再全量迁移主代码

**旧路径删除与双路径正式化**
- **D-05:** 存量 classic agent（`asst_*` ID）数据处理：**自动重同步**——检测到 asst_* 的 HCP 自动重新同步为 hosted agent（启动时或首次连接时触发）
- **D-06:** 双路径正式化范围 = **删旧 + 架构文档化，不引入新共享抽象层**。删除 classic 路径与 `_apply_voice_agent_patch()` monkey-patch，清理 `voice_live_websocket.py` 内部分支，在 docs 中明确双路径架构（文本→Responses API；语音→Voice Live→Agent）
- **D-07:** **删除全局 hosted agent override 配置**（`voice_live_hosted_agent_name/project/endpoint`），只用 per-HCP hosted agent
- **D-08:** **Agent 模式强制**：HCP 语音会话必须有 synced agent_id，未同步时拒绝连接并提示重新同步；Model 模式（`connect(model=...)`）仅保留给 VL Instance Editor 的联通测试功能

**VL Instance 必选化 & HCP 内联字段移除**
- **D-09:** HCP 内联字段（`voice_name`、`avatar_character`、`avatar_style`、`avatar_customized`）**直接删列不回填**——Alembic batch 迁移 drop 列，内联值丢弃，model/schema/API/前端全部清除，只保留 `voice_live_instance_id`
- **D-10:** **每个 HCP 必须绑定一个 VL Instance**（覆盖 roadmap 中"变为可选"的表述）。理由：VL Instance 不仅含声音，也含形象（avatar）等完整语音配置
- **D-11:** HCP 编辑器 Voice/Avatar tab 简化为：**只读 VL Instance 引用摘要**（模型/语音/avatar）+ assign/unassign 按钮 + 跳转 VL Management 链接（延续 Phase 14 只读设计）
- **D-12:** Agent sync 的 voice metadata 始终从 VL Instance 生成（`resolve_voice_config()`），HCP 必有 VL 后无需处理"无 VL"分支
- **D-13:** VL 必选的落地方式：**保存时校验（新建 + 编辑都拦截）**——API 层必填校验，DB 列保持 nullable 避免迁移风险；存量无 VL 的 HCP 下次编辑保存时强制选择

**模型目录拆分**
- **D-14:** Agent Foundation Model 目录采用 **Foundry API 动态拉取 + 缓存**——从 AI Foundry 项目拉取已部署的 chat 模型列表作为 foundation model 目录（新增 REST 端点供前端下拉使用）；`VOICE_LIVE_MODELS` 保持为 Voice Live realtime 模型专用目录，两者不再混用

**文档与测试**
- **D-15:** docs/voice-live-avatar **合并两套 README 树为单一树并全面更新**——删除过时内容（classic agent、内联字段、preview api-version），补双路径架构图
- **D-16:** 测试**全量更新 + 新增专项测试**：所有受影响测试适配新架构（删 classic 断言、改 GA api-version、删内联字段）；新增覆盖：Entra/API Key 回退、asst_* 自动重同步、VL 必填校验、foundation model 目录端点；E2E 必须实际运行通过（项目标准：95% 覆盖率）

**重要修正：** roadmap 中"VoiceLiveInstance 变为可选"不成立。用户明确：**每个 HCP 必须绑定一个 VL Instance**（VL 不仅有声音也有形象等），落地为保存时校验（见 D-13），DB 列保持 nullable。

### Claude's Discretion
- api-version 常量放置位置（config.py 配置项 vs 服务层常量）
- Foundry 模型列表缓存策略（TTL、失败回退行为）
- asst_* 自动重同步的具体触发时机实现（启动 vs 惰性）
- 拒连提示的错误消息文案与前端展示方式
- 文档合并后的章节结构

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

No phase requirement IDs were provided for this phase (ROADMAP traceability table has no row for Phase 29 — it is a post-v1 technical refactor/adaptation phase, not tied to a v1/v2 REQUIREMENTS.md entry). The closest related v1 requirement is **PLAT-05** (voice interaction mode configurable per deployment/session) and **PLAT-03** (Azure service connections configurable), both already "Complete" from earlier phases — Phase 29 does not reopen their acceptance criteria, it refactors the underlying SDK/architecture that implements them.
</phase_requirements>

## Summary

Phase 29 is a **deep refactor of already-working code**, not new-feature research. The codebase already has: a dual-path architecture (text via `agent_chat_service.py` Responses API, voice via `voice_live_websocket.py` proxy), an Entra-preferred/API-Key-fallback credential pattern (`agent_sync_service._get_project_client`), a VoiceLiveInstance/HcpProfile separation with a `resolve_voice_config()` priority resolver, and Alembic batch-migration precedent for SQLite. The work is concentrated in five areas: (1) SDK version bump + api-version consolidation, (2) deleting the classic-agent branch and monkey-patch, (3) making VL Instance mandatory and removing 4 (or more — see Open Questions) deprecated inline HCP columns, (4) building a genuinely new capability — a Foundry-API-backed Agent Foundation Model catalog endpoint, and (5) merging two documentation trees (~11,500 lines total) and updating 29 backend test files + 44 frontend files that reference the fields being removed.

**Critical, HIGH-confidence finding that must be surfaced to the user before/during planning:** `azure-ai-voicelive` **1.3.0 GA is not yet published to PyPI** as of this research date (2026-07-19), even though the GitHub source (`main` branch `_version.py` = `"1.3.0"`, `CHANGELOG.md` dated 2026-07-13) confirms the GA release exists and does use api-version `2026-07-15` exactly as CONTEXT.md's D-02 assumes. PyPI's registry (`pip index versions`, `pypi.org/pypi/.../json`, `pip install --dry-run`) shows the latest installable version is `1.3.0b1` (beta, released 2026-05-28, default api-version `2026-06-01-preview`). The currently installed version in `backend/.venv` is `1.2.0b5`. **This is a 6-day-old GA release that has a publish lag** — Azure SDK repos routinely merge CHANGELOG entries with the release PR before the PyPI artifact actually appears (typically hours to a few days, but can stretch to weeks). The plan MUST include a first-task PyPI availability check and an explicit fallback strategy (see Common Pitfalls #1 and Environment Availability).

**Primary recommendation:** Structure Phase 29 as: (0) verify current PyPI availability of `azure-ai-voicelive==1.3.0` at execution start; (1) POC script per D-04 confirming Agent connect/auth/session-config against whichever version is actually installable; (2) SDK bump + api-version consolidation; (3) delete classic/monkey-patch code; (4) VL-mandatory + column drop (get exact field-list ambiguity in D-09 resolved — see Open Questions); (5) new Foundry deployments-list endpoint (data-plane, no ARM/subscription-ID needed — confirmed feasible with the already-installed `azure-ai-projects==2.3.0` SDK); (6) docs merge; (7) full test-suite update. Given the volume (29 backend test files, 44 frontend files, ~11.5k doc lines), this phase needs multiple waves, not a single pass.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `azure-ai-voicelive[aiohttp]` | **See risk above** — GitHub source is 1.3.0 GA (2026-07-13); PyPI latest is `1.3.0b1` (2026-05-28) as of research date | Voice Live realtime WebSocket client | Official Microsoft SDK; already the project's chosen client [VERIFIED: pypi.org JSON API + GitHub raw CHANGELOG.md, cross-checked 2026-07-19] |
| `azure-ai-projects` | **2.3.0** (installed, matches latest PyPI) | AI Foundry Agent creation/sync + (new) deployments listing for D-14 | Already used throughout `agent_sync_service.py`, `skill_foundry_service.py`, `knowledge_base_service.py` [VERIFIED: `pip show`, PyPI JSON] |
| `azure-identity` | 1.25.3 (installed) | `DefaultAzureCredential` for Entra auth | Already the project's Entra pattern [VERIFIED: `pip show`] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `azure-core` | already a transitive dep of voicelive/projects | `AzureKeyCredential`, `AzureKeyCredentialPolicy` | API-key fallback path (D-01) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `AIProjectClient.deployments.list()` (data-plane) for D-14 | ARM `Microsoft.CognitiveServices/accounts/deployments` REST API (management-plane, `azure-mgmt-cognitiveservices`) | ARM approach needs `subscription_id` + `resource_group` + ARM RBAC, **none of which the app currently stores anywhere** (config.py only has `azure_foundry_endpoint/api_key/default_project`). Data-plane `.deployments` is a straight drop-in using the exact credential pattern already in `agent_sync_service.py` — strongly preferred. |
| Pin to `1.3.0` exactly (`==1.3.0`) | D-03's locked range `>=1.3.0,<2.0` | Range is correct per D-03; just flag that at plan-execution time the range may currently resolve to nothing installable (1.3.0b1 is `<1.3.0` per PEP 440 and won't satisfy `>=1.3.0`) |

**Installation:**
```bash
# Verify current availability BEFORE writing the pin (see Common Pitfalls #1)
backend/.venv/bin/pip index versions azure-ai-voicelive

# If 1.3.0 GA is on PyPI:
backend/.venv/bin/pip install "azure-ai-voicelive[aiohttp]>=1.3.0,<2.0"

# If GA still not published (fallback — requires explicit user sign-off, see Pitfall #1):
backend/.venv/bin/pip install --pre "azure-ai-voicelive[aiohttp]==1.3.0b1"
```

**Version verification (re-run at plan-execution time, not just at research time):**
```bash
backend/.venv/bin/pip index versions azure-ai-voicelive
curl -s https://pypi.org/pypi/azure-ai-voicelive/json | python3 -c "import json,sys; print(json.load(sys.stdin)['info']['version'])"
```

## Architecture Patterns

### Recommended Project Structure (no new top-level dirs — refactor in place)
```
backend/app/
├── services/
│   ├── voice_live_websocket.py       # D-01/D-02/D-05/D-06/D-08 changes concentrate here
│   ├── voice_live_webrtc.py          # D-02: replace WEBRTC_API_VERSION constant with shared one
│   ├── voice_live_instance_service.py # D-12/D-13: resolve_voice_config() fallback branch becomes dead code
│   ├── voice_live_models.py          # D-14: stays realtime-only; do NOT add foundation models here
│   ├── agent_foundation_models.py    # NEW (D-14): Foundry deployments-list + cache + REST endpoint backing
│   └── agent_sync_service.py         # D-05: asst_* auto-resync logic goes here (reuses create_agent/sync helpers)
├── config.py                          # D-02: single API_VERSION constant/setting; D-07: remove 3 hosted-agent-override settings
├── models/hcp_profile.py              # D-09: Alembic batch drop columns (scope TBD — see Open Questions)
└── alembic/versions/                  # new batch migration, follow u24a_*/y32a_* precedent

docs/voice-live-avatar/
└── README/                            # D-15: single merged tree (currently 2 trees, ~11.5k lines total)
```

### Pattern 1: Entra-preferred / API-Key-fallback credential resolution (D-01)
**What:** Try `DefaultAzureCredential()` first (probe with `get_token`), fall back to `AzureKeyCredential` if Entra unavailable or key configured explicitly.
**When to use:** Every Voice Live / Foundry connection point (WS proxy connect, WebRTC token exchange, new Foundry deployments client).
**Example — exact reusable pattern already in the codebase (`backend/app/services/agent_sync_service.py`):**
```python
# Source: backend/app/services/agent_sync_service.py (lines ~350-390), already Entra-first + API-key-fallback
def _get_project_client(endpoint: str, api_key: str = ""):
    """Create an AIProjectClient -- prefers Entra ID, falls back to API Key."""
    try:
        from azure.identity import DefaultAzureCredential
        credential = DefaultAzureCredential()
        credential.get_token("https://cognitiveservices.azure.com/.default")
        logger.info("_get_project_client: using DefaultAzureCredential (Entra ID)")
        return AIProjectClient(endpoint=endpoint, credential=credential)
    except Exception as exc:
        logger.debug("_get_project_client: DefaultAzureCredential unavailable: %s", exc)
    if api_key:
        from azure.core.credentials import AzureKeyCredential
        from azure.core.pipeline.policies import AzureKeyCredentialPolicy
        return AIProjectClient(
            endpoint=endpoint,
            credential=_ApiKeyTokenCredential(api_key),
            authentication_policy=AzureKeyCredentialPolicy(credential=AzureKeyCredential(api_key)),
        )
    raise RuntimeError("No valid credential available...")
```
D-01 asks for the *same shape* applied to the Voice Live WS `connect()` call in `voice_live_websocket.py`, which today only branches on hosted-vs-classic agent (using Entra unconditionally for hosted, API key OR Entra ambiguously for model mode) — this needs to become a single, explicit Entra-first/API-key-fallback helper shared by both call sites, per D-06's "no new shared abstraction layer beyond what's needed" guidance (a small local helper function is fine; a new package/module hierarchy is not what D-06 intends).

### Pattern 2: AI Foundry deployments enumeration for Agent Foundation Model catalog (D-14)
**What:** `AIProjectClient(endpoint, credential).deployments.list(deployment_type=...)` returns `ItemPaged[ModelDeployment]` with `model_name`, `model_publisher`, `model_version`, `capabilities: dict[str,str]`, `sku`. This is a **data-plane** call using the same endpoint/credential the app already stores (`azure_foundry_endpoint`) — no ARM subscription ID or resource group needed.
**When to use:** New `GET /api/v1/agent-foundation-models` endpoint (or similar) backing the HCP agent-model dropdown, distinct from `VOICE_LIVE_MODELS` (realtime-only, static dict).
**Example (verified against installed SDK source, not docs):**
```python
# Source: backend/.venv/lib/python3.11/site-packages/azure/ai/projects/operations/_operations.py
# class DeploymentsOperations.list() -- verified by reading installed SDK source, 2.3.0
from azure.ai.projects import AIProjectClient

client = AIProjectClient(endpoint=foundry_endpoint, credential=credential)
for deployment in client.deployments.list():  # ItemPaged[Deployment], subtype ModelDeployment
    # deployment.model_name, deployment.model_publisher, deployment.capabilities (dict[str,str])
    # Filter here for chat-capable models (capabilities keys vary by publisher; verify with a
    # live project during POC -- e.g. capabilities.get("chat_completion") is the likely signal,
    # but this was NOT verified against a live Foundry project in this research pass).
    ...
```
**Caveat [ASSUMED]:** The exact `capabilities` dict keys that distinguish "chat" models from "realtime-only" or "embedding" models were not verified against a live Foundry project response in this research session — only the SDK's type definitions were inspected. The POC step (D-04, extend to also cover D-14) should print a real `capabilities` payload from the project's actual deployments before writing the filter logic.

### Pattern 3: Alembic batch column drop for SQLite (D-09)
**What:** `with op.batch_alter_table("hcp_profiles") as batch_op: batch_op.drop_column(...)` — SQLite has no native `ALTER TABLE DROP COLUMN` (project CLAUDE.md Gotcha #1); batch mode rebuilds the table.
**When to use:** D-09's column drop migration.
**Example — exact precedent already in the repo:**
```python
# Source: backend/alembic/versions/u24a_add_focus_and_cu_fields.py (add-column precedent; drop is the mirror image)
with op.batch_alter_table("scoring_rubrics") as batch_op:
    batch_op.add_column(sa.Column(...))
# For DROP, same batch_alter_table wrapper, batch_op.drop_column("voice_name") etc.
```

### Anti-Patterns to Avoid
- **Re-introducing a shared "voice config resolver" abstraction beyond `resolve_voice_config()`:** D-06 explicitly says no new shared abstraction layer. `resolve_voice_config()` already exists and, once VL is mandatory, simply loses its inline-fallback branch — don't refactor it into something bigger.
- **Filtering Foundry deployments client-side by hardcoded model-name string list:** defeats the purpose of D-14's "dynamic pull" — the whole point is to avoid another static `VOICE_LIVE_MODELS`-style dict for foundation models. Filter by `capabilities`/`deployment_type`, not model name.
- **Assuming `1.3.0` GA is on PyPI without checking:** see Common Pitfalls #1.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Entra token acquisition + refresh | Custom token cache/refresh loop | `azure.identity.DefaultAzureCredential` / `azure.identity.aio.DefaultAzureCredential` | Already the project standard (`agent_sync_service.py`, recent quick-task 260718-eha migrated 152 voice_live tests to Entra bearer) |
| Foundation model catalog | Static hardcoded model-name dict (like the old `VOICE_LIVE_MODELS` pattern, but for chat models) | `AIProjectClient.deployments.list()` (D-14) | Deployed models change per-project/per-region; a hardcoded list goes stale immediately, which is exactly the problem D-14 is fixing |
| SQLite column removal | Raw `ALTER TABLE ... DROP COLUMN` or manual table rebuild | `alembic.op.batch_alter_table(...).drop_column(...)` | SQLite limitation (CLAUDE.md Gotcha #1); batch mode is the only safe path and has 2+ precedents in this repo |
| Voice/Avatar config precedence | New ad-hoc conditional logic scattered across call sites | Keep using `resolve_voice_config()` as the single source of truth, just delete its now-dead inline-fallback branch | D-12 explicitly says this |

**Key insight:** Almost everything Phase 29 needs (Entra-first credential resolution, batch Alembic migrations, VL/HCP separation, a config-resolution single point of truth) **already exists in this codebase from prior phases** (11, 14, 16, quick-task 260718-eha). This phase is subtraction and consolidation more than invention — the one genuinely new capability is the Foundry deployments-list endpoint for D-14.

## Common Pitfalls

### Pitfall 1: SDK 1.3.0 GA may not be installable at the moment the plan executes
**What goes wrong:** A plan task does `pip install "azure-ai-voicelive[aiohttp]>=1.3.0,<2.0"` and it fails or silently resolves to nothing (constraint unsatisfiable), or CI breaks because the PyPI publish still hasn't landed.
**Why it happens:** GitHub `main`'s CHANGELOG.md and `_version.py` are updated as part of the release PR, which can merge *before* the PyPI artifact is actually uploaded. Verified gap here: GitHub confirms 1.3.0 GA dated 2026-07-13 (6 days before this research), but PyPI (`pip index versions`, JSON API, `pip install --dry-run`) shows only `1.3.0b1` as of 2026-07-19.
**How to avoid:** Make the very first task of the phase a live `pip index versions azure-ai-voicelive` check. If 1.3.0 GA is available, proceed as planned. If not, the plan needs an explicit fallback decision point for the user: (a) wait and re-check daily, (b) install `1.3.0b1` with `--pre` and explicitly pass `api_version="2026-07-15"` to `connect()` (untested — the beta SDK's *default* is `2026-06-01-preview`, but the `connect()` signature accepts an arbitrary `api_version: str`, so passing the GA string is possible in principle; not verified against a live service in this research), or (c) install directly from the GitHub source tree via `pip install git+https://github.com/Azure/azure-sdk-for-python.git#subdirectory=sdk/voicelive/azure-ai-voicelive` as an interim measure. Do not silently substitute one of these without flagging it back to the user — D-02/D-03 are locked decisions premised on GA being available.
**Warning signs:** `pip install` reports "No matching distribution found for azure-ai-voicelive==1.3.0"; CI failing on dependency resolution.

### Pitfall 2: D-09's named-field list is narrower than the actual "deprecated inline" field set on `HcpProfile`
**What goes wrong:** A plan/migration drops exactly the 4 named columns (`voice_name`, `avatar_character`, `avatar_style`, `avatar_customized`) but leaves 10 more inline fields (`voice_live_enabled`, `voice_live_model`, `voice_type`, `voice_temperature`, `voice_custom`, `turn_detection_type`, `noise_suppression`, `echo_cancellation`, `eou_detection`, `recognition_language`) in place, half-cleaning the model and leaving `resolve_voice_config()`'s now-unreachable inline-fallback branch partially referencing dead columns.
**Why it happens:** `backend/app/models/hcp_profile.py` has a comment block literally titled `# --- Deprecated inline voice fields (kept for backward compat, prefer VoiceLiveInstance) ---` covering 14 fields total, but CONTEXT.md's D-09 names only 4. See Open Questions #1 for the exact recommendation.
**How to avoid:** Planner should explicitly re-confirm scope with the user before writing the migration task (D-09 is locked, but its literal field list may be incomplete rather than intentionally narrow — this needs a yes/no, not an assumption either way).
**Warning signs:** After the migration, `resolve_voice_config()`'s inline branch still references live columns that are individually meaningless without the ones that got dropped (e.g., `voice_type` without `voice_name`).

### Pitfall 3: `agent-name=`/`agent_id=` query-param shape drift between SDK versions
**What goes wrong:** The monkey-patch in `_apply_voice_agent_patch()` rewrites the SDK's URL builder to swap `/voice-live/realtime`→`/voice-agent/realtime` and `agent-name=`→`agent_id=` for classic (`asst_*`) agents. Deleting the monkey-patch (D-06) without also fully removing the classic-agent connect branch (D-08 forces hosted-agent-only) could leave dead imports/dangling references, or — if D-05's auto-resync doesn't run before the classic branch is deleted — orphan any HCP still holding an `asst_*` ID with no code path to reach it.
**Why it happens:** D-05 (auto-resync) and D-06 (delete classic path) are two separate decisions that must land in the right order: resync-capable code needs to exist and run (at least once, for every `asst_*` HCP) before the classic connect branch is safe to delete outright, or every remaining `asst_*` HCP becomes permanently unreachable via voice.
**How to avoid:** Sequence tasks so D-05's auto-resync trigger is implemented and exercised (or confirmed there are zero `asst_*` HCPs in the target DB) before deleting the classic-agent `connect()` branch in `voice_live_websocket.py`.
**Warning signs:** A production HCP profile with `agent_id` starting `asst_` and `agent_sync_status="synced"` failing to connect after the classic branch is removed.

### Pitfall 4: WebRTC path currently has no `use_agent_mode` gate mirroring D-08
**What goes wrong:** `voice_live_webrtc.py`'s `create_webrtc_session_config()` determines agent mode purely from `profile.agent_id and profile.agent_sync_status == "synced"` with no D-08-style "reject if not synced" enforcement, and still supports model-mode as a normal (not test-only) path. If D-08 ("Agent 模式强制") is applied to the WebSocket path but not mirrored in the WebRTC path (Phase 26 alternative transport), the two transports diverge in security/behavior semantics.
**Why it happens:** WebRTC was added in Phase 26 as a preview alternative and wasn't updated when the agent-mode-forcing decisions were made for the WS proxy.
**How to avoid:** Explicitly decide (with the user, since CONTEXT.md doesn't mention WebRTC) whether D-08's "Agent mode forced, Model mode test-only" rule extends to the WebRTC transport too, or whether WebRTC is out of scope for this pass (Phase 26 already marked it "preview"). Flagged as Open Question #3.
**Warning signs:** WebRTC sessions still succeeding in Model mode for HCPs that the WS proxy would now reject.

## Code Examples

### Reading a `ModelDeployment`'s capabilities (D-14 POC starting point)
```python
# Source: verified by reading azure-ai-projects 2.3.0 installed source
# (backend/.venv/lib/python3.11/site-packages/azure/ai/projects/models/_models.py, class ModelDeployment)
from azure.ai.projects import AIProjectClient

client = AIProjectClient(endpoint=foundry_endpoint, credential=credential)
for d in client.deployments.list():
    print(d.name, d.model_name, d.model_publisher, d.model_version, d.capabilities, d.sku)
    # capabilities: dict[str, str] -- exact keys NOT verified against a live project in this
    # research pass; confirm during POC before writing the chat-model filter.
```

### Existing Entra-first credential helper to mirror in Voice Live WS connect (D-01)
```python
# Source: backend/app/services/agent_sync_service.py lines ~332-391 (already in repo)
# See "Pattern 1" above for the full listing.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Classic agent (`asst_*` ID) + `/voice-agent/realtime` URL monkey-patch | Hosted agent (name-based) + native `/voice-live/realtime` + `agent-name=` | Introduced SDK ≥1.2.0b5 (Phase 16) | D-06 removes the now-legacy classic path entirely in Phase 29 |
| `api_version="2025-05-01-preview"` (classic), `"2026-01-01-preview"` (hosted, WS), `"2026-01-01-preview"` (WebRTC const) | Single GA `api_version="2026-07-15"` | SDK 1.3.0 GA, GitHub CHANGELOG dated 2026-07-13 [VERIFIED: GitHub raw CHANGELOG.md] | D-02; must land as one config value, not 3 scattered literals |
| SDK default api-version progression: `2026-01-01-preview` (1.2.0b5) → `2026-04-10` (1.2.0 stable) → `2026-06-01-preview` (1.3.0b1) → `2026-07-15` GA (1.3.0) | — | Each `Other Changes`/`Breaking Changes` entry in CHANGELOG.md [VERIFIED] | Confirms the app's 3 hardcoded api-version strings are already stale relative to even the 1.2.0 *stable* default (`2026-04-10`), independent of the 1.3.0 question |
| Foundry Agent Tool classes (`FoundryAgentTool`, etc.) | Removed in SDK 1.2.0 GA, replaced by flattened `connect(agent_name=..., project_name=...)` kwargs | 1.2.0 (2026-05-22) [VERIFIED: CHANGELOG] | Already reflected in current codebase; no further action needed for this specific item in Phase 29 |
| `RequestImageContentPart.url` | Renamed to `image_url` | 1.3.0b1 breaking change, carried into 1.3.0 GA [VERIFIED: CHANGELOG] | Not used in this codebase today (grep found no `RequestImageContentPart` usage) — no impact, but flag if image input is ever added |

**Deprecated/outdated:**
- Classic agent mode (`asst_*` + monkey-patch): being deleted this phase (D-06/D-08).
- Global hosted-agent-override config (`voice_live_hosted_agent_name/project/endpoint`): being deleted this phase (D-07).
- HCP inline voice/avatar fields: being deleted this phase, scope TBD (D-09, see Open Questions).
- Preview api-versions (`2026-01-01-preview`, `2025-05-01-preview`): being deleted this phase (D-02).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The `ModelDeployment.capabilities` dict contains a key that reliably distinguishes chat-capable models from realtime/embedding-only models (exact key name not verified against a live Foundry project response) | Architecture Patterns #2, Code Examples | D-14's filter logic (excluding non-chat models from the Agent Foundation Model dropdown) may need rework after a real POC call; low risk, contained to one filter function |
| A2 | Passing `api_version="2026-07-15"` explicitly to `connect()` on the 1.3.0b1 *beta* SDK (if GA isn't installable at execution time) would be accepted by the Azure Voice Live *service* even though the beta SDK's default is `2026-06-01-preview` | Common Pitfalls #1 | If wrong, the interim fallback (installing 1.3.0b1 + explicit api_version override) doesn't work, and the team must wait for GA PyPI publish or install from GitHub source instead |
| A3 | The WebRTC transport (`voice_live_webrtc.py`) is out of scope for D-08's "Agent mode forced" rule, since CONTEXT.md's canonical refs only call out this file for its own `WEBRTC_API_VERSION` constant (D-02), not for agent-mode enforcement | Common Pitfalls #4 | If wrong, WebRTC sessions could bypass the new agent-mode-forced security/UX invariant that the WS proxy enforces, creating an inconsistent voice-session security posture between the two transports |

## Open Questions

1. **Does D-09's column-drop scope cover only the 4 named fields, or the full 14-field "deprecated inline" block on `HcpProfile`?**
   - What we know: CONTEXT.md D-09 names exactly `voice_name`, `avatar_character`, `avatar_style`, `avatar_customized`. The actual model (`backend/app/models/hcp_profile.py` lines 49-74) has a comment-delimited block of 14 fields under "Deprecated inline voice fields", including `voice_live_enabled`, `voice_live_model`, `voice_type`, `voice_temperature`, `voice_custom`, `turn_detection_type`, `noise_suppression`, `echo_cancellation`, `eou_detection`, `recognition_language` in addition to the 4 named ones. `resolve_voice_config()`'s inline-fallback branch (which D-12 says becomes unreachable once VL is mandatory) reads **all 14**, not just the 4 named ones. The same 3-way split (create/update/response schemas) exists in `backend/app/schemas/hcp_profile.py` for all 14 fields, and D-11's "read-only VL summary" tab redesign implies the whole tab (not 4 fields) collapses.
   - What's unclear: Whether the user intentionally scoped D-09 narrowly (e.g., planning a separate future cleanup for the other 10) or simply named the most UI-visible 4 as shorthand for "the deprecated inline block."
   - Recommendation: Planner should ask/confirm before writing the migration task. Given D-10 (VL mandatory) + D-12 (no-VL branch unreachable) + D-13 (nullable-but-required-at-API-layer), the *logically consistent* outcome is dropping all 14 columns together in one migration — a partial drop leaves half a dead abstraction. Default to proposing "drop all 14, confirm with user" rather than mechanically implementing only the 4 named ones.

2. **Is `1.3.0` actually installable via `pip` by the time this phase executes?**
   - What we know: As of 2026-07-19, GitHub `main` has `_version.py = "1.3.0"` and a CHANGELOG.md entry dated 2026-07-13 documenting the GA release and its `2026-07-15` default api-version — exactly matching D-02/D-03's premise. PyPI (`pip index versions`, JSON API) shows only `1.3.0b1` (2026-05-28) as the newest available install.
   - What's unclear: Publish timing is entirely up to the Azure SDK release pipeline; there's no way to predict from this research whether it lands in 1 day or 3 weeks.
   - Recommendation: First plan task = live re-check (`pip index versions azure-ai-voicelive`). Branch the plan explicitly on the result rather than assuming GA availability.

3. **Should D-08's "Agent mode forced, Model mode test-only" rule extend to the WebRTC transport (`voice_live_webrtc.py`)?**
   - What we know: CONTEXT.md's canonical refs call out `voice_live_webrtc.py` only for `WEBRTC_API_VERSION` (D-02 scope). D-08's language is specific to "HCP 语音会话" without naming a transport, and the WebRTC session-config builder currently has no agent-mode-forcing/rejection logic at all — it silently falls back to model mode.
   - What's unclear: Whether this is an intentional scope boundary (WebRTC is still "preview" per Phase 26) or an oversight in CONTEXT.md's phase-boundary framing.
   - Recommendation: Surface explicitly at plan-check; do not silently extend or silently ignore.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `azure-ai-voicelive[aiohttp]>=1.3.0` (GA) | D-02, D-03 | ✗ (not on PyPI as of 2026-07-19; GitHub source confirms it exists) | Latest PyPI: `1.3.0b1` (beta); installed: `1.2.0b5` | Install `1.3.0b1` with `--pre` + explicit `api_version` override (unverified — A2), or install from GitHub source subdirectory, or wait for PyPI publish and re-check |
| `azure-ai-projects` | D-14 (deployments.list), existing agent sync | ✓ | 2.3.0 (matches latest PyPI) | — |
| `azure-identity` | D-01 Entra path | ✓ | 1.25.3 | — |
| Live AI Foundry project with ≥1 deployed chat model | D-14 POC (verifying `capabilities` dict shape) | Not verified in this research session (no live Azure credentials probed) | — | POC step must run against the actual project before finalizing the model-catalog filter |
| Backend Python venv | All backend tasks | ✓ | Python 3.11, `backend/.venv` | — |

**Missing dependencies with no fallback:**
- None — the SDK gap has a fallback (see above), just an unverified one requiring a POC/decision checkpoint.

**Missing dependencies with fallback:**
- `azure-ai-voicelive>=1.3.0` GA — see table above.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Backend framework | pytest ≥8.3.0 + pytest-asyncio ≥0.24.0 [VERIFIED: `backend/pyproject.toml`] |
| Backend config | `backend/pyproject.toml` `[tool.pytest.ini_options]`, `testpaths = ["tests"]` |
| Frontend framework | vitest ^3.2.4 [VERIFIED: `frontend/package.json`] |
| E2E framework | Playwright ≥1.48.0, config at `frontend/playwright.config.ts` (per CLAUDE.md Gotcha #5, must pass `--config=e2e/playwright.config.ts` explicitly) |
| Quick run command (backend) | `cd backend && .venv/bin/pytest tests/test_voice_live_websocket.py tests/test_voice_live_webrtc.py -x` |
| Quick run command (frontend) | `cd frontend && npm run test -- voice-avatar-tab` (or relevant spec) |
| Full suite command (backend) | `cd backend && .venv/bin/pytest -v` |
| Full suite command (frontend) | `cd frontend && npm run test && npx playwright test` |

### Phase Requirements → Test Map
No formal REQ-IDs are mapped to this phase (see `<phase_requirements>`). Test mapping instead follows the 16 locked decisions:

| Decision | Behavior | Test Type | Automated Command | File Exists? |
|----------|----------|-----------|-------------------|-------------|
| D-01 | Entra-first connect succeeds; API-key fallback succeeds when Entra unavailable | unit | `pytest tests/test_voice_live_websocket.py -k entra_or_api_key -x` | ❌ Wave 0 — new test cases needed |
| D-02 | Single api-version constant used by both WS and WebRTC paths; no preview-version literals remain | unit | `pytest tests/test_voice_live_websocket.py tests/test_voice_live_webrtc.py -k api_version -x` | ✅ Existing assertions at `test_voice_live_websocket.py:786-787,1326,1366` and `test_voice_live_webrtc.py:80` need updating, not creating from scratch |
| D-05 | `asst_*` HCP auto-resyncs to hosted agent | unit + integration | `pytest tests/test_agent_sync_service.py -k asst_resync -x` (file name assumed; confirm exact test file) | ❌ Wave 0 |
| D-06/D-08 | Classic branch removed; unsynced HCP voice session rejected with clear error | unit | `pytest tests/test_voice_live_websocket.py -k agent_forced_reject -x` | ❌ Wave 0 |
| D-09/D-13 | Save (create/update) HCP without `voice_live_instance_id` is rejected by API | unit | `pytest tests/test_hcp_profile_api.py -k vl_required -x` (file name assumed) | ❌ Wave 0 |
| D-14 | Foundation model catalog endpoint returns cached, filtered chat-model list | unit + manual POC verification of live capabilities shape | `pytest tests/test_agent_foundation_models.py -x` (new file) | ❌ Wave 0 |
| D-16 (E2E) | Full HCP voice training session still works end-to-end post-refactor | e2e | `npx playwright test e2e/voice-live-training.spec.ts` (name assumed — confirm exact existing spec) | Existing E2E specs must be located and re-run, not assumed passing |

### Sampling Rate
- **Per task commit:** targeted quick-run command for the file(s) touched
- **Per wave merge:** full backend + frontend + Playwright suite green
- **Phase gate:** Full suite green before `/gsd-verify-work`, consistent with CLAUDE.md's 95% coverage + "E2E must actually run" standard

### Wave 0 Gaps
- [ ] Confirm exact existing test file names for HCP profile API tests, agent sync tests, and the F2F voice-live E2E spec (this research did not exhaustively enumerate all 29 backend + 44 frontend affected files — see `Common Pitfalls`/scale note in Summary)
- [ ] New test file: `backend/tests/test_agent_foundation_models.py` for D-14's new endpoint
- [ ] New test cases in `test_voice_live_websocket.py` for D-01's Entra/API-key dual-path coverage (per D-16's explicit requirement)
- [ ] New test cases for D-05's asst_* auto-resync trigger
- [ ] New test cases for D-13's VL-required save-time validation (create + update)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | Yes | D-01's Entra-first pattern via `DefaultAzureCredential` — already the established, correct pattern in `agent_sync_service.py`; extend, don't reinvent |
| V3 Session Management | Partial | Voice Live WS/WebRTC session tokens (bearer exchange in `voice_live_webrtc.py._exchange_api_key_for_bearer_token`) — unaffected by this phase's scope but adjacent; no new risk introduced |
| V4 Access Control | Yes | D-08's "Agent mode forced, reject unsynced" is itself an access-control invariant — must be enforced server-side (already is, in the WS path) and the WebRTC gap (Open Question #3) is the actual access-control risk surface for this phase |
| V5 Input Validation | Yes | D-13's save-time VL-required validation is standard Pydantic-schema-level input validation, matching existing `model_validator` patterns in the codebase (e.g., scoring-weight validation from Phase 02) |
| V6 Cryptography | No | No new crypto in this phase; existing API-key encryption (`backend/app/config.py` `encryption_key`) is untouched |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Stale/orphaned `asst_*` classic-agent HCP silently losing voice capability after classic path removal (Pitfall #3) | Denial of Service (unintentional, but treat as availability risk) | D-05's auto-resync must run and be verified (or DB confirmed clean of `asst_*`) before D-06 deletes the classic connect branch |
| WebRTC transport bypassing D-08's agent-mode-forced invariant that WS enforces (Pitfall #4 / Open Question #3) | Elevation of Privilege / inconsistent authorization surface | Explicit decision needed: either mirror D-08 in `voice_live_webrtc.py` or document the WebRTC transport as explicitly out of scope (still "preview") |
| Foundry deployments-list endpoint (new, D-14) exposing more than intended (e.g., all deployment metadata including connection names) to a non-admin-scoped frontend caller | Information Disclosure | New REST endpoint should apply the same `require_role("admin")` pattern already used for other admin-config endpoints (CLAUDE.md convention), and should return only the fields the dropdown needs (name/label), not full `ModelDeployment` objects with `connection_name`/`sku` internals |

## Sources

### Primary (HIGH confidence)
- `https://pypi.org/pypi/azure-ai-voicelive/json` and `.../1.3.0b1/json` — PyPI registry JSON API, queried live 2026-07-19, confirms latest installable version and full embedded CHANGELOG text for 1.0.0 through 1.3.0b1
- `https://raw.githubusercontent.com/Azure/azure-sdk-for-python/main/sdk/voicelive/azure-ai-voicelive/CHANGELOG.md` — fetched live, contains the `## 1.3.0 (2026-07-13)` GA entry with the exact `2026-07-15` api-version breaking-change note
- `https://raw.githubusercontent.com/Azure/azure-sdk-for-python/main/sdk/voicelive/azure-ai-voicelive/azure/ai/voicelive/_version.py` — confirms `VERSION = "1.3.0"` on `main`
- `backend/.venv/lib/python3.11/site-packages/azure/ai/projects/` (installed 2.3.0 source, `_client.py`, `_patch.py`, `operations/_operations.py`, `models/_models.py`) — read directly to confirm `AIProjectClient.deployments.list()`/`.get()` and `ModelDeployment` schema
- `backend/app/services/voice_live_websocket.py`, `voice_live_webrtc.py`, `agent_sync_service.py`, `voice_live_instance_service.py`, `voice_live_models.py`, `models/hcp_profile.py`, `models/voice_live_instance.py`, `schemas/hcp_profile.py`, `config.py` — read directly for current-state architecture
- `docs/microsoft-agent-framework/tests/test_agent_auth_v2.py` — read directly, confirms the exact POC pattern D-04 references
- `backend/tests/test_voice_live_websocket.py` (lines 786-787, 1326, 1366), `test_voice_live_webrtc.py` (line 80) — grepped directly, confirms the exact hardcoded api-version assertions D-02 will invalidate

### Secondary (MEDIUM confidence)
- `https://learn.microsoft.com/en-us/rest/api/microsoftfoundry/accountmanagement/deployments/list` — fetched, confirms the ARM/management-plane alternative exists but requires subscription_id/resource_group (ruled out in favor of the data-plane SDK approach)

### Tertiary (LOW confidence)
- None retained — WebSearch tool returned repeated API errors (400) during this session; all findings were cross-verified via direct PyPI/GitHub/installed-package inspection instead, so no unverified web claims are carried into this document.

## Metadata

**Confidence breakdown:**
- SDK version/timeline: HIGH — cross-verified via three independent sources (PyPI JSON API, GitHub raw CHANGELOG, GitHub raw `_version.py`) that agree with each other and reveal a real, actionable gap
- D-14 Foundry API approach: HIGH for feasibility (verified against installed SDK source), MEDIUM for the exact `capabilities` filter logic (untested against a live project — A1)
- Codebase current-state findings (D-01, D-02, D-05 through D-13 touchpoints): HIGH — all read directly from the actual files
- D-09 scope ambiguity: this is a genuine open question surfaced by evidence, not a confidence gap — flagged for explicit resolution, not guessed at
- Security domain: MEDIUM — mapped from ASVS categories to this phase's specific decisions using established codebase patterns, not a fresh threat-model exercise

**Research date:** 2026-07-19
**Valid until:** The SDK-availability finding (Pitfall #1 / Open Question #2) should be **re-verified immediately before plan execution**, not just trusted from this document — PyPI publish status can change within days. Everything else (codebase architecture, D-14 approach feasibility) is stable for the standard 30-day window.
