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
