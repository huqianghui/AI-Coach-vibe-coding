# 02 — Model 模式 vs Agent 模式

> Azure AI Voice Live API 支持两种调用模式。理解它们的架构差异是实现双模式切换的基础。

---

## 1. 两种模式的定位

| | Model 模式 | Agent 模式 |
|---|---|---|
| **一句话** | 直接和大语言模型对话 | 调用一个预配置好的 AI Agent |
| **类比** | 打电话给 114 查号台（你问什么它答什么） | 打电话给你的专属医生（他有你的病历、能开处方） |
| **Azure 服务** | Azure OpenAI Realtime | Azure AI Foundry Agent Service |

---

## 1.1 SDK 版本状态（2026-07-27 校正）

> 本文档最初基于 `azure-ai-voicelive==1.2.0b5` 编写。该版本早已被淘汰——`connect()` 的
> Agent 模式调用形态在 `1.2.0 GA` 就已经变化，本项目当前实际安装/锁定的版本又比那更新一个
> 完整的 minor 版本。以下是真实的版本链（校验方式：`backend/.venv` 内 `pip show`
> + `inspect.signature(connect)` 直接内省，非查文档）：

| 版本 | 状态 | 发布日期 | 关键变化 |
|------|------|---------|---------|
| `1.2.0b5` | 已废弃（本文档最初基线） | 2026-04-06 | `AgentSessionConfig` + `connect(agent_config=...)` |
| `1.2.0` GA | 已废弃 | 2026-05-22 | **移除 `AgentSessionConfig`**；`connect()` 改为扁平化 `agent_name`/`project_name` kwargs |
| `1.3.0b1` | **当前锁定版本** — `backend/pyproject.toml` 锁定，`backend/.venv` 实际安装 | 2026-05-28 | 支持显式传递 `api_version="2026-07-15"`（本项目所有 `connect()` 调用点的标准做法） |
| `1.3.0` GA | 仅存在于 CHANGELOG，**尚未发布到 PyPI**（截至 2026-07-27） | CHANGELOG 标注 2026-07-20 | 升级前必须先用 `pip index versions azure-ai-voicelive` 确认 PyPI 已可安装 |

**结论**：本文档下面所有 Python 代码示例均已按 `1.3.0b1` 实际安装的 `connect()` 签名重写，
不再包含任何 `AgentSessionConfig` 导入或 `agent_config=` kwarg。

---

## 2. 数据流对比

### 2.1 Model 模式

```
你的后端                     Azure Voice Live                LLM 模型 (GPT-4o)
   │                              │                              │
   │── connect(                   │                              │
   │     credential=Key,          │                              │
   │     model="gpt-4o"           │                              │
   │   ) ─────────────────────>   │                              │
   │                              │                              │
   │── session.update(            │                              │
   │     instructions="你是王医生...",│                           │
   │     voice="alloy",           │                              │
   │   ) ─────────────────────>   │── 转发到模型 ────────────>   │
   │                              │                              │
   │<── 模型回复（语音+文本） ──  │<── 模型推理结果 ──────────   │
```

**关键特征**：
- **所有上下文由调用方提供**：system prompt、voice 配置、对话历史
- **模型是无状态的**：每次连接都是全新的，不记得上次对话
- **Azure 侧不存储任何业务数据**：知识库内容嵌入在 instructions 中
- **认证**：API Key 足够 — 只是"用算力"

### 2.2 Agent 模式

```
你的后端                     Azure Voice Live           AI Foundry Agent "王医生"
   │                              │                         │
   │── connect(                   │                         │── instructions（预配置）
   │     credential=Key/EntraID,  │                         │── knowledge base（知识库）
   │     agent_name="Dr-Wang",    │                         │── tools（工具集）
   │     project_name="...",      │                         │── conversation history
   │   ) ─────────────────────>   │                         │
   │                              │                         │
   │                              │── 验证调用方权限 ─────>  │
   │                              │── 调用 Agent ────────>  │
   │                              │                         │── 读取知识库
   │                              │                         │── 调用工具
   │                              │                         │── 生成回复
   │                              │                         │
   │<── Agent 回复（语音+文本）── │<── Agent 处理结果 ──── │
```

**关键特征**：
- **上下文来自 Agent 自身配置**：instructions、knowledge、tools 预配置在 AI Foundry
- **Agent 有持久状态**：知识库、工具配置、可能有对话历史
- **Azure 侧存有业务数据**：知识库中可能包含产品资料、临床数据等敏感内容
- **认证**：API Key 和 Entra ID 均可（SDK 1.2.0b5+ 实测确认），多租户场景推荐 Entra ID

---

## 3. Agent 模式的认证：实测结果（2026-04-08）

> **版本说明（2026-07-27）**：本节数据是在 `AgentSessionConfig` 时代的 SDK `1.2.0b5` 上测出的。
> 其认证结论（API Key 可用于 Agent 模式）在当前 `1.3.0b1` 上依然成立，但下面 §4 展示该结论的
> 代码示例已经全部改写为当前 SDK 的扁平化 kwargs 形态——历史 POC 的原始代码形态本身已不可用。
> 关于当前 SDK 上的最新实测（含 Foundry IQ grounding），见文末新增的第 6 节。

> **重要更新**：微软文档声称 "Agent invocation doesn't support key-based authentication"，
> 但 SDK 1.2.0b5 的 POC 实测表明 **API Key + Agent 模式是可行的**。

### 3.1 POC 测试结果

使用 `azure-ai-voicelive==1.2.0b5`，API version `2026-01-01-preview`：

| # | 认证方式 | 模式 | 连接 | 会话 | 对话 | 回复 |
|---|---------|------|------|------|------|------|
| 1 | API Key | Model | ✅ | ✅ | ✅ | 232 字 (完整) |
| 2 | **API Key** | **Agent** | **✅** | **✅** | **✅** | **281 字 (流式)** |
| 3 | Entra ID | Agent | ✅ | ✅ | ✅ | 296 字 (流式) |
| 4 | STS Token | Agent | ❌ 401 | - | - | - |

**测试代码**：[tests/test_agent_auth_v2.py](./tests/test_agent_auth_v2.py)

### 3.2 关键发现

1. **API Key + Agent 可行**：SDK 1.2.0b5 将 Agent 配置通过 WebSocket URL query params 传递
   （`agent-name=xxx&agent-project-name=xxx`），API Key 认证在这种方式下被接受
2. **Agent 回复内容不同**：Model 模式返回 instructions 中定义的"肿瘤科专家"角色，
   Agent 模式返回 AI Foundry 上预配置的"神经内科"角色 — **确认 Agent 配置被正确加载**
3. **STS Token 不可用**：STS Token 被包装为 Bearer Token 后，Azure 用 Entra ID 验证管道检查，
   但 STS Token 不是 Entra ID 签发的 → 签名/签发者不匹配 → 401
4. **SDK 版本决定一切**：1.1.0 没有 `AgentSessionConfig`，无法使用 Agent 模式

### 3.3 理论 vs 实测的差异

微软文档的理论分析（仍然成立，但不是技术强制限制）：

Agent 关联的知识库可能包含：
- 产品临床试验数据（敏感）
- 内部培训资料（保密）
- 客户沟通记录（隐私）

**理论上** API Key 认证的安全风险：
- 一个 Key 对应整个 Cognitive Services 资源
- 持有 Key 的人能调用该资源下**所有** Project 的**所有** Agent
- 能间接访问所有 Agent 关联的知识库数据
- 无法区分调用者，无法审计

**实际情况**：Azure 目前（2026-04-08）并未在技术层面阻止 API Key + Agent，
但在**多租户隔离**场景下，Entra ID 仍是更安全的选择：

```
AI Foundry Hub（一个 Cognitive Services 资源，一个 API Key）
  ├── Project A（百济神州 - 中国区）
  │   ├── Agent "王医生"（知识库：产品A 中国区临床数据）
  │   └── Agent "李医生"（知识库：产品B 中国区安全数据）
  │
  └── Project B（百济神州 - 欧洲区）
      ├── Agent "Dr. Smith"（知识库：EU regulatory data）
      └── Agent "Dr. Mueller"（知识库：DE market data）
```

- API Key 模式：一个 Key 通吃所有 Project（当前可行，但安全粒度粗）
- Entra ID 模式：按身份分配 Project 级别的 RBAC 角色（安全粒度细）

### 3.4 STS Token 为什么不行

```
通道 A — API Key:
  请求头: Ocp-Apim-Subscription-Key: <your-key>
  ──> Azure API Management 网关验证
  ──> 验证: "这个 key 属于这个资源吗？" → 是 → ✅ 放行

通道 B — Bearer Token:
  请求头: Authorization: Bearer <token>
  ──> Entra ID 验证管道
  ──> STS Token: 签发者不是 Entra ID → ❌ 401
  ──> Entra ID Token: 签名/签发者/声明全匹配 → ✅ 放行
```

API Key 和 STS Token 虽然来自同一个密钥，但走的是**完全不同的验证通道**。

### 3.5 与 Model 模式的对比

| 维度 | Model 模式 | Agent 模式 |
|------|-----------|-----------|
| Azure 侧有业务数据？ | 无 — 你自带 instructions | 有 — 知识库、工具配置 |
| API Key 可用？ | ✅ 是 | ✅ 是（SDK 1.2.0b5 实测） |
| Entra ID 可用？ | ✅ 是 | ✅ 是 |
| STS Token 可用？ | 未测试 | ❌ 不可用（401） |
| 推荐认证方式 | API Key（简单够用） | API Key（开发）/ Entra ID（多租户生产） |

---

## 4. 调用方式对比（Python SDK）

### 4.1 Model 模式代码

```python
from azure.core.credentials import AzureKeyCredential
from azure.ai.voicelive.aio import connect

credential = AzureKeyCredential(api_key)

async with connect(
    endpoint=endpoint,
    credential=credential,
    model="gpt-4o",                       # 指定模型
    api_version="2026-07-15",             # 显式传递，本项目从不依赖 SDK 内置默认值
) as connection:
    # 通过 session.update 发送 instructions
    await connection.send({
        "type": "session.update",
        "session": {
            "instructions": "你是王医生...",
            "modalities": ["text", "audio"],
        }
    })
```

### 4.2 Agent 模式代码（API Key — 开发推荐）

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

以上代码与生产代码 `backend/app/services/voice_live_websocket.py:691-697` 的调用形态完全一致。

### 4.3 Agent 模式代码（Entra ID — 多租户生产推荐）

```python
from azure.identity.aio import DefaultAzureCredential
from azure.ai.voicelive.aio import connect

credential = DefaultAzureCredential()     # Entra ID 认证

async with connect(
    endpoint=endpoint,
    credential=credential,
    api_version="2026-07-15",
    agent_name="Dr-Wang-Fang",
    project_name="ai-coach-project",
    # agent_version="v1.0",               # 可选：锁定版本
    # conversation_id="xxx",              # 可选：恢复对话
) as connection:
    # Agent 配置来自 AI Foundry，无需在代码中指定 instructions
    pass
```

### 4.4 关键差异

| 参数 | Model 模式 | Agent 模式 |
|------|-----------|-----------|
| `credential` | `AzureKeyCredential(key)` | `AzureKeyCredential(key)` 或 `DefaultAzureCredential()` |
| `model` | 必填（如 `"gpt-4o"`） | 不填（Agent 自带模型配置） |
| `agent_name` | 不填 | 必填（须与 `project_name` 同时提供，否则 SDK 抛 `ValueError`） |
| `project_name` | 不填 | 必填（须与 `agent_name` 同时提供，否则 SDK 抛 `ValueError`） |
| `session.update` 中的 `instructions` | 必填（调用方提供） | 可选（覆盖 Agent 默认 instructions） |
| SDK 最低版本 | `1.1.0` | 扁平化 kwargs 自 `1.2.0 GA` 起可用（早期 `1.2.0b3`/`b4` 时代的 `AgentSessionConfig` 已被移除）；本项目当前锁定 `1.3.0b1` |

---

## 5. 两种模式的优劣势

### Model 模式

**优势**：
- 配置简单，只需 API Key
- 调用方完全控制对话行为（instructions 由代码管理）
- 无需额外的 Azure 权限配置

**劣势**：
- 知识库内容必须塞进 instructions（token 限制）
- 无法利用 Azure AI Search 等知识检索能力
- 工具调用需要自行实现
- 对话上下文不持久

### Agent 模式

**优势**：
- Agent 自带知识库（RAG — 检索增强生成），不受 token 限制
- Agent 自带工具（Function Calling），由 Azure 托管执行
- 对话能力更强（Agent 有完整的上下文管理）
- 集中管理 — 在 AI Foundry Portal 修改 Agent 配置，无需改代码
- **API Key 认证可行**（自 SDK `1.2.0 GA` 起以扁平化 kwargs 形式延续，不必引入 Entra ID；本项目当前锁定 `1.3.0b1`）

**劣势**：
- 需要 SDK >= 1.2.0b5（当前仍为 beta 版）
- 依赖 Azure AI Foundry Agent Service（额外的服务依赖）
- Agent 配置在 Azure 侧管理，调试链路更长
- 多租户场景仍建议 Entra ID（API Key 安全粒度粗）

---

## 6. Agent 模式 + Foundry IQ 知识库 grounding：真实实测（2026-07-27，SDK 1.3.0b1）

> 本节数据全部来自对 `tests/test_agent_foundry_iq_grounding.py` 的一次真实运行，未加工、未软化。
> 与第 3 节（2026-04-08，SDK `1.2.0b5`）是两次独立的、跨 SDK 版本的实测，互不覆盖。

### 6.1 前置条件（实测前已确认，无需额外配置）

直接查询 `backend/ai_coach.db`（2026-07-27）确认：

```
hcp_profiles: id=cb6bce84-5cbc-49c5-8624-f5d56fc5255e, name="Dr. Wang Fang",
              agent_id="Dr-Wang-Fang", agent_sync_status="synced"
hcp_knowledge_configs: hcp_profile_id=<同上>, index_name="omada-product-parameters-kb",
              is_enabled=1, server_label="knowledge-base-omada-product-parameters-kb"
```

`Dr-Wang-Fang` Agent 已同步、已挂载一个启用的 Foundry IQ 知识库 —— 无需通过管理员 UI 做任何
额外配置（挂载机制见 [doc 06](./06-agent-tools-and-knowledge-grounding.md)）。

### 6.2 测试脚本与运行环境

- 脚本：[`tests/test_agent_foundry_iq_grounding.py`](./tests/test_agent_foundry_iq_grounding.py)
- 运行命令：`cd backend && .venv/bin/python3 ../docs/microsoft-agent-framework/tests/test_agent_foundry_iq_grounding.py`
- 真实运行时的 SDK 版本：`1.3.0b1`（`azure-ai-voicelive.__version__` 直接打印确认）
- `connect()` 调用形态：`connect(endpoint=, credential=, api_version="2026-07-15", agent_name="Dr-Wang-Fang", project_name=<AZURE_FOUNDRY_DEFAULT_PROJECT>)` —— 与第 4.2 节完全一致的扁平化 kwargs

### 6.3 意外的真实发现：API Key 在当前环境下对 Agent 模式返回 403

按第 4.2 节的代码原样发起连接（`AzureKeyCredential` + 扁平化 `agent_name=`/`project_name=`）时，
**握手阶段直接返回 403**，未能建立 WebSocket 连接：

```
ConnectionError: Failed to establish WebSocket connection: 403, message='Invalid response status',
url='wss://.../voice-live/realtime?api-version=2026-07-15&agent-name=Dr-Wang-Fang&agent-project-name=avarda-demo-prj'
```

进一步排查确认：
- 同一个 API Key 用于 **Model 模式**连接同样返回 403（不是 Agent 模式特有问题）
- 该 Key 与生产代码 `config_service.get_effective_key(db, "azure_voice_live")` 实际使用的 Key
  **完全一致**（长度、内容比对相同）——不是 Key 配置错误或过期不同步
- 同一进程内改用 `DefaultAzureCredential()`（Entra ID）连接**立即成功**

**结论**：这与第 3 节（2026-04-08）"API Key + Agent 模式可行"的历史实测结论**不再一致**——
当前（2026-07-27）该 Azure 资源上 API Key 认证对 Voice Live 端点整体（Model 模式和 Agent 模式
均受影响）返回 403。这可能是 Azure 侧后续针对该资源关闭/收紧了 Key 认证通道（与本项目
`260717-x5f`/`260718-cy6` 两次 quick task 中在 Skills/Agents API 上观察到的
`AuthenticationTypeDisabled` 现象方向一致，但本次未拿到明确的错误 code，仅有 403 状态码，
暂不能完全确认根因）。**本次 grounding 实测因此改用 Entra ID 完成**，详见下节。

### 6.4 Turn 1（知识库问题）真实事件与结果

```
事件序列: conversation.item.created ×2, response.created, mcp_list_tools.in_progress,
          conversation.item.done, response.done (status=FAILED)
```

关键信号：**`mcp_list_tools.in_progress` 确实触发** —— 证明 Voice Live Agent 模式会话
在收到知识库相关问题后，自动尝试调用 Agent 已挂载的 MCP 知识库工具，完全不需要在 Voice Live
侧做任何额外的知识库配置。但该次 MCP 调用本身失败，`response.done` 的 `status_details` 给出
了具体错误：

```
Foundry agent service API error: Access denied when connecting to the MCP server at
https://ai-search-southeast-asia.search.windows.net:443/knowledgebases/omada-product-parameters-kb/mcp
?api-version=**** while enumerating tools (HTTP 403 Forbidden). Please verify:
(1) your credentials have the necessary permissions to access this server,
(2) any IP allowlists or network policies permit requests from this service, and
(3) the server's access control configuration allows the requested operation.
```

Turn 1 因此**没有产生任何文本回复**（回复长度 = 0）。这是 AI Search 侧 MCP 端点对 Agent 的
`RemoteTool` 连接返回的 403（`doc 06 §4` 描述的 `project_connection_id`/`ProjectManagedIdentity`
授权链路上的问题），与本 quick task 要修正的 SDK/文档问题是两个独立层面的故障——不在本次任务
范围内修复，已记录为待跟进项（见本 quick task 的 `deferred-items.md`）。

### 6.5 Turn 2（对照问题，同一连接）真实事件与结果

```
事件序列: conversation.item.created ×2, response.created, response.output_item.added,
          response.content_part.added, response.text.delta ×416, response.text.done,
          response.content_part.done, response.output_item.done, response.done (status=COMPLETED)
```

**没有出现任何 `mcp_list_tools.*`/`response.mcp_call*` 事件** —— 与预期一致：无关问题不会
触发知识库检索工具调用。收到完整文本回复（长度 604 字符），节选：

> "从管理学角度看，**跨部门沟通最常见的挑战**通常不是'信息不够'，而是**目标不一致、语言不一致、
> 责任边界不清**。……常见问题主要有几类：1. 部门目标不同……2. 信息传递失真……3. 职责边界模糊……"

### 6.6 结论：确认还是推翻研究假设？

**部分确认**：Voice Live Agent 模式会话确实**透明地**触发了 Agent 已同步挂载的 Foundry IQ
知识库 MCP 工具（`mcp_list_tools.in_progress` 在 KB 相关问题上真实触发、在无关问题上不触发），
证实了研究结论"Voice Live 侧无需任何知识库配置，Agent 挂载什么工具就用什么工具"这一**触发机制**
是真实的，不是假设。

**但未能确认端到端的 grounding 成功**：本次实测中，工具调用本身在 AI Search MCP 端点层面被拒绝
（403），因此无法验证"检索到的知识库内容真的被写进了最终回复文本"这一环节。这个未验证的环节属于
`doc 06 §4` 描述的 RemoteTool 连接授权配置问题，而不是 Voice Live SDK 或本文档 §1-5 涉及的
`connect()` 调用形态问题。

### 6.7 版本适用范围

以上 6.1-6.6 的全部结果均基于 `azure-ai-voicelive==1.3.0b1`（当前锁定/安装版本）实测得出。
若/当 `1.3.0` GA 发布到 PyPI 后升级，应重新运行 `tests/test_agent_foundry_iq_grounding.py`
验证结果是否发生变化 —— 尤其是 API Key 403 这一发现，需要在新版本上确认是否依然存在。
