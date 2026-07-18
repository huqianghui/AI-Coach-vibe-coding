# Microsoft Agent Framework — 使用前置说明书

> 本目录包含 Azure AI Foundry Agent Service 和 Voice Live API 的架构理解、认证模型、以及与 AI Coach 平台集成的关键设计决策。
>
> **阅读顺序**：按编号从 01 到 04 依次阅读，每层知识建立在前一层之上。

## 文档索引

| 编号 | 文档 | 内容 | 适用人群 |
|------|------|------|---------|
| 01 | [Azure 服务认证模型](./01-azure-authentication-model.md) | API Key vs Entra ID 的本质区别、适用场景、决策树 | 全体开发 |
| 02 | [Model 模式 vs Agent 模式](./02-model-vs-agent-mode.md) | 两种调用模式的架构差异、数据流、认证方式实测结果 | 后端开发 |
| 03 | [Agent Identity 与认证方向](./03-agent-identity-and-auth-direction.md) | Agent 内部 Identity 的作用、入站/出站认证的区别、常见误解澄清 | 架构师 |
| 04 | [AI Coach 平台集成策略](./04-ai-coach-integration-strategy.md) | 当前实现现状、双模式切换设计、集成方案 | 项目开发 |
| 05 | [Agent API Metadata 约束](./05-agent-api-metadata-constraints.md) | Endpoint 构造、512 字符限制、metadata 格式、默认值省略策略、重构指南 | 后端开发 / Agent |
| 06 | [POC 验证测试代码](./tests/test_agent_auth_v2.py) | SDK 1.2.0b5 四种认证方式实测代码（**唯一有效测试**） | 开发/验证 |
| 07 | [Agent Metadata API 探测测试](./tests/test_agent_metadata_api.py) | 真实 API 连接测试：metadata 读写、512 限制验证、版本追踪 | 开发/验证 |
| 08 | [REST Client 测试](./tests/agent-metadata-api.http) | VS Code 点击运行：6 组 API 测试（metadata、512 限制、VL 格式、版本、错误、合并） | 开发/验证 |
| 09 | [Postman 测试集合](./tests/agent-metadata-api.postman_collection.json) | Postman Collection JSON：5 组测试含自动验证脚本 | 开发/验证 |
| 09 | [Agent API 版本演进](./09-agent-api-version-evolution.md) | API 版本变迁时间线、`2025-05-01` 废弃原因、新一代 Agent Service (1.0/preview) 差异、metadata 支持现状 | 全体开发 |
| 07 | [Azure Agent API 操作指南](./07-agent-skill-creation-guide.md) | Agent 命名规则（63字符/字母数字+连字符）、SDK 创建流程、Meta Skill Agent 架构与同步、常见陷阱 | 后端开发 / Agent |
| 08 | [Agent Skills 规范与平台实现](./08-agent-skills-specification.md) | SKILL.md 完整格式、目录结构、渐进式加载、Python SDK 用法、AI Coach 实现对照（含 name vs display_name）、命名规则与 sanitize 函数、安全实践 | 全体开发 |
| 10 | [Agent Skills Foundry 上传与 Toolbox 挂载](./10-agent-skills-foundry-upload-and-toolbox.md) | Skills API 上传（inline/ZIP）、版本管理、Toolbox skill_reference 挂载、Agent 消费模式实测；以及 Responses API 路径（openai/v1, client.skills, shell 工具挂载）对比实测 | 后端开发 / Agent |

> **注意**：`tests/` 目录下的 `test_voice_live_auth_modes.py` 和 `test_agent_conversation.py`
> 是 SDK 1.1.0 时期的早期探索代码，使用了 `session.agent` 字段（服务端不接受）和错误的 API 版本。
> 这两个文件已标记为废弃，仅供历史参考。**所有结论以 `test_agent_auth_v2.py` 为准**。

## 核心结论速查（2026-04-08 实测验证）

> 以下结论基于 `azure-ai-voicelive==1.2.0b5`（API version `2026-01-01-preview`）POC 实测。

1. **API Key + Agent 模式 = 可行** — SDK 1.2.0b5 通过 `AgentSessionConfig` + URL query params 支持 API Key 调用 Agent（推翻了微软文档中的声明）
2. **Entra ID + Agent 模式 = 可行** — 标准方式，同样正常
3. **STS Token + Agent 模式 = 不可行** — STS Token 不是 Entra ID 签发的，无法通过 Bearer Token 验证通道（401）
4. **SDK 版本是关键** — 1.1.0 没有 `AgentSessionConfig`，只有 1.2.0b5 才支持 Agent 连接
5. **Agent 回复内容与 Model 不同** — 实测确认 Agent 模式加载了 AI Foundry 上预配置的 instructions，而非代码中的
6. **对 AI Coach 平台的重大利好** — 可以继续使用 API Key 认证，不需要改认证架构即可支持 Agent 模式
