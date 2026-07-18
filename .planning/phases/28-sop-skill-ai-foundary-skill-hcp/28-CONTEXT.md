# Phase 28: 资料转 SOP Skill 注册 Foundry 并挂载 HCP 培训对话 - Context

**Gathered:** 2026-07-18
**Status:** Ready for planning

<domain>
## Phase Boundary

上传资料转成的 SOP Skill（Phase 19 产物）注册到 Azure AI Foundry 成为云端一等实体；培训 session 中把 skill 动态挂载到 HCP agent 的 toolbox 供其调用，与用户对话。覆盖文本对话 + Voice Live 两类模式。资料→SOP 转换本身（Phase 19）、会话级 Skill Focus（Phase 24）不在本 phase 重做。

</domain>

<decisions>
## Implementation Decisions

### Foundry 注册机制
- **D-01:** Skill 与 Agent 各自独立注册为 Foundry 一等实体。skill publish 时自动同步：ZIP 打包后经 Agents API `client.beta.skills.create_from_files()` 上传（azure-ai-projects>=2.3.0，Entra ID 认证 + `Foundry-Features: Skills=V1Preview` 头）。不烘焙进 agent 定义。
- **D-02:** 培训 session 创建时才把 skill 经 Toolbox `skill_reference`（`client.toolboxes.create_version(..., skills=[ToolboxSkillReference(name=...)])`）挂载给 HCP agent，目标访问方式为 MCP。agent 定义本身不因 skill 而改变。

### 注册时机与生命周期
- **D-03:** publish → 自动注册/同步到 Foundry；重新发布 → `skills.versions.create()` 版本递增（保留历史版本可回溯）；归档/下架 → 从 Foundry 删除 skill，避免废弃资源残留。

### 训练挂载方式（MCP 缺口兼容层）
- **D-04:** Toolbox 的 MCP 端点发现目前实测 405（doc 10 Test 7 真实缺口）。Phase 28 研究阶段需再探 MCP 端点正确形状；设计上做**消费抽象层**：MCP 可用则走 MCP，不可用则自动降级到已实测验证的 `skills.download()` + 指令注入路径（doc 10 Test 8），对上层透明。
- **D-05:** 模式覆盖：**文本对话 + Voice Live 同时交付**。Voice Live 链路（WS 代理 + AgentSessionConfig）是否支持 Toolbox/skill 挂载未经实测，研究阶段需验证；不支持则该模式用降级注入路径。

### 失败处理
- **D-06:** 发布不阻断 + 培训降级：Foundry 同步失败不阻止 skill 本地发布（页面显示失败状态 + 重试按钮）；培训时若 Foundry 端 skill 不可用，自动降级到 Phase 19 本地 DB 注入路径（`build_skill_augmented_instructions`），培训不中断。

### 管理界面与可观测性
- **D-07:** Skill 管理页显示 Foundry 同步状态、云端版本号等信息，交互模式对齐现有 HCP agent 同步 UI（状态徽章、重试、Foundry 门户跳转链接，参考 `get_portal_url_components`）。

### Claude's Discretion
- 同步状态字段建模（DB 列 vs JSON metadata）、重试的具体 UX、Toolbox 命名规则、ZIP 打包细节复用方式

</decisions>

<specifics>
## Specific Ideas

- 用户核心模型："skill 和 agent 本身就是各自独立的。只有在培训的 session 中才把 skill 添加到 toolbox 中给 agent 调用。"
- "azure ai agent 提供 toolbox 的方式，mcp 来访问" —— MCP 是目标形态，兼容层是落地保障
- `docs/microsoft-agent-framework/` 里的文档和 unit test case 是本 phase 的实测依据，研究/实现直接复用其中已验证的调用代码

**硬性技术约束（doc 10 实测结论）：**
- Skills 端点 **API Key 认证被禁用**（403 AuthenticationTypeDisabled）—— 必须 Entra ID（`DefaultAzureCredential`：本地 az login / 云端 Managed Identity）。现有 agent_sync 走 API Key，skill 同步需要独立的凭据路径，planner 必须处理该差异
- `azure-ai-projects>=2.3.0`（pyproject 已更新）；2.3.0 的 `beta.*` 自动注入 Foundry-Features 头，但 `client.toolboxes` 已移到顶层、需手动附加
- Agents API 路径 ZIP 布局 = SKILL.md 在 ZIP 根目录（无顶层文件夹）—— 与 Responses API 路径（单一顶层文件夹）**相反**，不可混用
- Skill 命名规则 `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`，≤64 字符，不含 `--`
- 删除 Toolbox 唯一版本会级联删除 Toolbox 本身（后续 delete 返回 404 属正常）

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Foundry Skills API 实测（最重要）
- `docs/microsoft-agent-framework/10-agent-skills-foundry-upload-and-toolbox.md` — Skill 上传/版本/Toolbox 挂载/Agent 消费全链路实测结论，含认证、SDK 版本、ZIP 布局、MCP 缺口（§12 为修复后最终结论）
- `docs/microsoft-agent-framework/tests/test_skill_foundry_upload.py` — 可直接改造为生产 service 的已验证调用代码
- `docs/microsoft-agent-framework/tests/test_skill_responses_api.py` — Responses API 第二路径实测（对照参考）

### Skill 规范与工具
- `docs/microsoft-agent-framework/README.md` — 全目录索引 + 核心实测结论速查（**整个目录都是本 phase 的实测依据，文档 + unit test case 均可直接复用**）
- `docs/microsoft-agent-framework/08-agent-skills-specification.md` — SKILL.md 格式规范、命名规则、渐进式加载、AI Coach 实现对照
- `docs/microsoft-agent-framework/07-agent-skill-creation-guide.md` — Agent 命名规则、SDK 创建流程、Meta Skill Agent 架构、常见陷阱
- `docs/microsoft-agent-framework/06-agent-tools-and-knowledge-grounding.md` — 工具与知识挂载
- `docs/microsoft-agent-framework/09-agent-api-version-evolution.md` — API 版本演进、新一代 Agent Service 差异

### 认证与集成策略
- `docs/microsoft-agent-framework/01-azure-authentication-model.md` — API Key vs Entra ID 决策树
- `docs/microsoft-agent-framework/02-model-vs-agent-mode.md` — Model/Agent 双模式架构与认证实测
- `docs/microsoft-agent-framework/03-agent-identity-and-auth-direction.md` — Agent Identity、入站/出站认证
- `docs/microsoft-agent-framework/04-ai-coach-integration-strategy.md` — 平台集成现状与双模式切换设计
- `docs/microsoft-agent-framework/05-agent-api-metadata-constraints.md` — Endpoint 构造、512 字符 metadata 限制
- `docs/microsoft-agent-framework/tests/test_agent_auth_v2.py` — Voice Live 四种认证方式实测（**API Key + Agent 模式可行** —— D-05 Voice Live 挂载研究的起点）

### 上游 phase 决策
- `.planning/phases/19-skill-module/19-CONTEXT.md` — skill 包结构、转换管线、SkillManager 注入（降级路径）
- `.planning/phases/24-session-skill-focus/24-CONTEXT.md` — 会话级 additional_instructions 机制
- `.planning/phases/17-foundry-iq/17-CONTEXT.md` — MCPTool 挂知识库的既有模式

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/app/services/skill_zip_service.py` — 已有 skill ZIP 打包能力（注意 Agents API 要求根目录布局）
- `backend/app/services/agent_sync_service.py` — `_get_project_client()`、重试模式、metadata 分块（512 限制）、`get_portal_url_components()`；skill 同步 service 可对照实现，但凭据需换 Entra ID
- `backend/app/services/skill_service.py` / `skill_manager.py` — skill 生命周期（publish/archive hook 点）与本地注入降级路径
- `backend/app/services/prompt_builder.py:build_skill_augmented_instructions` — D-06 降级路径的现成实现
- `azure_foundary_hosted_agents-main/` — agentskills.io 规范样例（参考，不采用容器化托管方案）

### Established Patterns
- Foundry 同步状态展示：HCP agent 管理页已有同步状态/版本/重试 UI 模式，skill 页对齐复用
- Scenario↔Skill 1:1 关联（Phase 19）：session 创建时经 scenario 找到 skill，是 toolbox 挂载的查找入口

### Integration Points
- skill publish 流程（`skill_service`）→ 新增 Foundry 同步 hook
- session 创建（`session_service` / agent_chat / voice_live）→ 新增 toolbox 挂载/降级逻辑
- Skill 管理前端页 → 新增同步状态区块

</code_context>

<deferred>
## Deferred Ideas

- 会议演讲等其余通信模式的 skill 挂载 — 后续 phase
- 若研究后 MCP 端点仍无法打通，MCP 原生访问整体顺延后续 phase（本 phase 以降级路径交付）
- 容器化托管 skillable agent（`azure_foundary_hosted_agents-main` 样例方案）— 明确不采用，除非未来有按需加载 scripts/references 的强需求

</deferred>

---

*Phase: 28-sop-skill-ai-foundary-skill-hcp*
*Context gathered: 2026-07-18*
