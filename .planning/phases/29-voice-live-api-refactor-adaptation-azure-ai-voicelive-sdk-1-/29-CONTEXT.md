# Phase 29: Voice Live API Refactor & Adaptation (azure-ai-voicelive 1.3.0) - Context

**Gathered:** 2026-07-19
**Status:** Ready for planning

<domain>
## Phase Boundary

升级 azure-ai-voicelive SDK 至 1.3.0（GA api-version 2026-07-15），正式化双路径交互架构（文本直连 Agent Responses API，语音走 Voice Live → Agent），删除 voice-agent monkey-patch 与 classic agent 旧路径，移除 HCP 内联 voice/avatar deprecated 字段，拆分 Agent Foundation Model 与 Voice Live 模型目录，更新 docs/voice-live-avatar 文档套件与全部相关测试。

**重要修正（用户决策覆盖 roadmap 表述）：** roadmap 中"VoiceLiveInstance 变为可选"不成立。用户明确：**每个 HCP 必须绑定一个 VL Instance**（VL 不仅有声音也有形象等），落地为保存时校验（见 D-13）。

</domain>

<decisions>
## Implementation Decisions

### SDK 1.3.0 升级与认证策略
- **D-01:** Voice Live WebSocket 认证采用 **Entra 优先 + API Key 回退**——有 Entra 凭据（服务主体/DefaultAzureCredential）时用 Entra，否则回退 API Key。两条认证路径都要有测试覆盖
- **D-02:** api-version **全部统一到 GA `2026-07-15`**，集中到单一常量/配置项（WebSocket + WebRTC 共用），删除所有 preview 版本引用（`2026-01-01-preview`、`2025-05-01-preview`、独立的 `WEBRTC_API_VERSION`）
- **D-03:** SDK 版本 pin 为 `azure-ai-voicelive[aiohttp]>=1.3.0,<2.0`
- **D-04:** 实施顺序：**先独立 POC 脚本验证** 1.3.0 的 Agent 连接/认证/会话配置（照 1.2.0b5 POC 模式），确认可行后再全量迁移主代码

### 旧路径删除与双路径正式化
- **D-05:** 存量 classic agent（`asst_*` ID）数据处理：**自动重同步**——检测到 asst_* 的 HCP 自动重新同步为 hosted agent（启动时或首次连接时触发）
- **D-06:** 双路径正式化范围 = **删旧 + 架构文档化，不引入新共享抽象层**。删除 classic 路径与 `_apply_voice_agent_patch()` monkey-patch，清理 `voice_live_websocket.py` 内部分支，在 docs 中明确双路径架构（文本→Responses API；语音→Voice Live→Agent）
- **D-07:** **删除全局 hosted agent override 配置**（`voice_live_hosted_agent_name/project/endpoint`），只用 per-HCP hosted agent
- **D-08:** **Agent 模式强制**：HCP 语音会话必须有 synced agent_id，未同步时拒绝连接并提示重新同步；Model 模式（`connect(model=...)`）仅保留给 VL Instance Editor 的联通测试功能

### VL Instance 必选化 & HCP 内联字段移除
- **D-09:** HCP 内联字段（`voice_name`、`avatar_character`、`avatar_style`、`avatar_customized`）**直接删列不回填**——Alembic batch 迁移 drop 列，内联值丢弃，model/schema/API/前端全部清除，只保留 `voice_live_instance_id`
- **D-10:** **每个 HCP 必须绑定一个 VL Instance**（覆盖 roadmap 中"变为可选"的表述）。理由：VL Instance 不仅含声音，也含形象（avatar）等完整语音配置
- **D-11:** HCP 编辑器 Voice/Avatar tab 简化为：**只读 VL Instance 引用摘要**（模型/语音/avatar）+ assign/unassign 按钮 + 跳转 VL Management 链接（延续 Phase 14 只读设计）
- **D-12:** Agent sync 的 voice metadata 始终从 VL Instance 生成（`resolve_voice_config()`），HCP 必有 VL 后无需处理"无 VL"分支
- **D-13:** VL 必选的落地方式：**保存时校验（新建 + 编辑都拦截）**——API 层必填校验，DB 列保持 nullable 避免迁移风险；存量无 VL 的 HCP 下次编辑保存时强制选择

### 模型目录拆分
- **D-14:** Agent Foundation Model 目录采用 **Foundry API 动态拉取 + 缓存**——从 AI Foundry 项目拉取已部署的 chat 模型列表作为 foundation model 目录（新增 REST 端点供前端下拉使用）；`VOICE_LIVE_MODELS` 保持为 Voice Live realtime 模型专用目录，两者不再混用

### 文档与测试
- **D-15:** docs/voice-live-avatar **合并两套 README 树为单一树并全面更新**——删除过时内容（classic agent、内联字段、preview api-version），补双路径架构图
- **D-16:** 测试**全量更新 + 新增专项测试**：所有受影响测试适配新架构（删 classic 断言、改 GA api-version、删内联字段）；新增覆盖：Entra/API Key 回退、asst_* 自动重同步、VL 必填校验、foundation model 目录端点；E2E 必须实际运行通过（项目标准：95% 覆盖率）

### Claude's Discretion
- api-version 常量放置位置（config.py 配置项 vs 服务层常量）
- Foundry 模型列表缓存策略（TTL、失败回退行为）
- asst_* 自动重同步的具体触发时机实现（启动 vs 惰性）
- 拒连提示的错误消息文案与前端展示方式
- 文档合并后的章节结构

</decisions>

<specifics>
## Specific Ideas

- POC 先行模式复用既有实践：Phase 16 前的 1.2.0b5 POC（`docs/microsoft-agent-framework/tests/test_agent_auth_v2.py`）验证了 API Key + Agent 模式，本次照此模式验证 1.3.0 GA
- 近期已验证 Entra bearer 认证路径：voice_live 后端测试已改 Entra bearer 且 152/152 通过（quick task 260718-eha）；Skills API 仅支持 Entra（API Key → 403 AuthenticationTypeDisabled）——是 D-01 选择 Entra 优先的直接依据
- HCP/VL 分离设计延续：VL Instance = 模型/Avatar/语音/对话参数（可复用、多 HCP 共享）；HCP Profile = Instructions/Knowledge/Tools + 只读 VL 引用

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Voice Live 架构与实现
- `backend/app/services/voice_live_websocket.py` — WS proxy 主体：monkey-patch（L47-76）、classic/hosted 分支（L701-776）、api-version 引用（L722, L769）、`_load_connection_config`
- `backend/app/services/voice_live_webrtc.py` — WebRTC 信令与 `WEBRTC_API_VERSION`（L116, L123）
- `backend/app/services/agent_chat_service.py` — 文本路径 Responses API 实现（双路径的另一半，保持不动）
- `backend/app/services/agent_sync_service.py` — agent 同步与 voice metadata 构建
- `backend/app/config.py` — `voice_live_agent_mode_enabled`、hosted agent override settings（L105-112，待删）、`default_chat_model`（L97）

### 数据模型与 Schema
- `backend/app/models/hcp_profile.py` — 内联字段（L56, L62-64）与 `voice_live_instance_id`（L45-46）
- `backend/app/models/voice_live_instance.py` — VL Instance 完整配置实体
- `backend/app/schemas/hcp_profile.py` — 内联字段在 create/update/response 三处（L39-45, L81-87, L127-133）
- `backend/app/services/voice_live_models.py` — `VOICE_LIVE_MODELS` 目录（realtime 专用）

### 前端触点
- `frontend/src/components/admin/voice-avatar-tab.tsx` — HCP 编辑器 Voice/Avatar tab（D-11 改造对象）
- `frontend/src/types/hcp.ts`、`frontend/src/types/voice-live.ts` — 内联字段类型定义
- 其他内联字段消费者：`hcp-table.tsx`、`vl-instance-dialog.tsx`、`playground-preview-panel.tsx`、`voice-live-chain-card.tsx`、`conference-stage.tsx`

### 先例与 POC
- `.planning/phases/16-voice-live-refactor-modularize-agent-mode-sync/16-CONTEXT.md` — Agent 模式引入与 SDK 1.2.0b5 升级先例
- `.planning/phases/26-add-voice-live-webrtc-transport-option-as-alternative-to-web/26-CONTEXT.md` — WebRTC transport 决策
- `docs/microsoft-agent-framework/tests/test_agent_auth_v2.py` — API Key + Agent 模式 POC 脚本（D-04 POC 参考模板）
- `voicelive-api-salescoach-main-sample-code/` — Voice Live 参考实现

### 文档套件（D-15 合并对象）
- `docs/voice-live-avatar/README.md` + 两套 `README/` 子树（01-architecture…08-log-monitor 与 01-overview…09-production + appendix）

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `resolve_voice_config()`：VL 配置解析已统一入口，D-12 直接复用
- Entra bearer 认证路径：voice_live 测试已迁移到 Entra bearer（152/152 通过），D-01 的 Entra 分支有现成模式
- `AGENT_FOUNDATION` 目录可参照 `voice_live_models.py` 的目录+REST 端点模式，但数据源改为 Foundry API 动态拉取（D-14）
- Alembic batch 操作模式：项目已有 SQLite batch migration 先例（Gotcha #1）

### Established Patterns
- 双路径已事实存在：文本 `agent_chat_service.py`（`responses.create`）、语音 `voice_live_websocket.py`——Phase 29 是删旧+文档化，不是新建
- `hcp_profiles.voice_live_instance_id` DB 层已 nullable + FK + index，D-13 只需 API 层校验，无 schema 变更
- 前端透明原则：Agent/Model 切换在后端 proxy 完成（Phase 16 决策），拒连行为（D-08）需要新的错误事件传递到前端

### Integration Points
- `voice_live_websocket.py` 连接建立处：D-01 认证选择、D-02 api-version、D-05 asst_* 检测重同步、D-08 拒连校验都汇聚于此
- `backend/app/api/hcp_profiles.py`：D-09 字段删除 + D-13 保存校验
- HCP 编辑器保存流程（前端）：D-13 校验的用户提示
- 测试断言点：`test_voice_live_websocket.py` L786-787/L1326/L1366、`test_voice_live_webrtc.py` L80 有 api-version 硬断言，D-02 后必改

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 29-voice-live-api-refactor-adaptation-azure-ai-voicelive-sdk-1*
*Context gathered: 2026-07-19*
