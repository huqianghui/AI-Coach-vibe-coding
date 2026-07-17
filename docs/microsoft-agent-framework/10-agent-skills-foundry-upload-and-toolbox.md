# Agent Skills Foundry 上传与 Toolbox 挂载实测

> 本文档基于 `docs/microsoft-agent-framework/tests/test_skill_foundry_upload.py` 的真实运行结果编写。
> 运行环境：`azure-ai-projects==2.1.0`，Foundry 项目 `avarda-demo-prj`（`sweden central` 区域）。
> 运行命令：`cd backend && .venv/bin/python3 ../docs/microsoft-agent-framework/tests/test_skill_foundry_upload.py`
> 遵循本项目"结论以实测为准"的文档传统（见 doc 01/02），本文档记录的每一条"实测结果"均为脚本实际输出，无任何假设或推测。

## 结论速查

1. **Skills inline 上传 (`skills.create()`) = 不可行（当前认证方式下）** — API Key 认证被 403 `AuthenticationTypeDisabled` 拒绝；Entra ID (`DefaultAzureCredential`) 兜底认证被 405 `Method Not Allowed` 拒绝
2. **ZIP 包上传 (`skills.create_from_package()`) = 不可行（当前认证方式下）** — 同样 403 `AuthenticationTypeDisabled`（API Key）
3. **Toolbox `skill_reference` 挂载 = 未验证（被上游 Skill 上传失败阻塞，SKIP）**
4. **Agent 消费 Toolbox 内 Skill = 未验证（被上游 Toolbox 挂载阻塞，SKIP）**
5. **本地校验（frontmatter 规则、ZIP 打包结构）= 100% 通过** — SKILL.md 命名规则、长度限制、ZIP 根目录布局均符合 doc 08 §3.3 规范
6. **清理 = 无需清理** — 由于没有任何云端资源被成功创建，`cleanup()` 空跑（no-op），未在 Foundry 项目留下任何遗留资源

## 1. 概述

本文档覆盖 Azure AI Foundry 的 **Skills REST/SDK API**（`project.beta.skills` / `project.beta.toolboxes`，云端 Skill 注册与 Toolbox 挂载）实测结果。

**本文档不重复 doc 08 的 SKILL.md 格式规范和渐进式加载章节**，doc 08 讲的是 SKILL.md 文件格式本身以及 `agent_framework` 库的本地 `SkillsProvider`（本地加载 Skill 内容，不涉及云端上传）。本文档只讲：把一个符合 doc 08 格式的 Skill **上传到 Azure AI Foundry 云端**、把它**版本化管理**、把它**挂载到 Toolbox**、以及 **Agent 如何消费挂载了 Skill 的 Toolbox** —— 这是一条与 doc 08 完全不同、此前项目内从未实测过的 API 路径。

## 2. 前置条件与环境

- SDK 版本：`azure-ai-projects==2.1.0`（`backend/.venv` 已安装）
- 环境变量（来自 `backend/.env`）：`AZURE_FOUNDRY_ENDPOINT`、`AZURE_FOUNDRY_API_KEY`、`AZURE_FOUNDRY_DEFAULT_PROJECT`（`avarda-demo-prj`）、`AZURE_FOUNDRY_MODEL`
- 客户端构造（API Key 模式，`allow_preview=True` 用于开启 `beta.*` 预览面）：

```python
from azure.ai.projects import AIProjectClient
from azure.core.credentials import AccessToken, AzureKeyCredential
from azure.core.pipeline.policies import AzureKeyCredentialPolicy

class _StubTokenCredential:
    def get_token(self, *_scopes, **_kwargs):
        return AccessToken(token="stub", expires_on=0)

client = AIProjectClient(
    endpoint=f"{ENDPOINT}/api/projects/{PROJECT_NAME}",
    credential=_StubTokenCredential(),
    authentication_policy=AzureKeyCredentialPolicy(
        credential=AzureKeyCredential(API_KEY), name="api-key",
    ),
    allow_preview=True,
)
```

- 运行命令：

```bash
cd backend
.venv/bin/python3 ../docs/microsoft-agent-framework/tests/test_skill_foundry_upload.py
```

## 3. Inline 上传（`skills.create()`）实测结果

| 操作 | 预期 | 实测结果 | 说明 |
|------|------|----------|------|
| `client.beta.skills.create(name="mr-training-creator-inline-poc", ...)`（API Key 认证） | 创建成功，返回 `SkillObject`（`name`/`skill_id`） | **FAIL** — `403 AuthenticationTypeDisabled` | 服务端返回：`(AuthenticationTypeDisabled) Key based authentication is disabled for this resource.` |
| 同一调用，改用 `DefaultAzureCredential`（Entra ID，本机 `az login` 会话） | 若 API Key 被拒绝，Entra ID 应可作为标准认证方式生效 | **FAIL** — `405 Method Not Allowed` | 服务端未返回 JSON 错误体（SDK 触发 "failsafe deserialization" 告警），仅报 `Operation returned an invalid status 'Method Not Allowed'` |

两种认证方式均未能创建 Skill，因此 `INLINE_SKILL_NAME`（`mr-training-creator-inline-poc`）**未被创建**，无需清理。

## 4. ZIP 包上传（`skills.create_from_package()`）实测结果

ZIP 打包逻辑（`SKILL.md` 位于 ZIP 根目录，`references/`、`scripts/` 保留相对子路径，不嵌套在额外的顶层文件夹下）：

```python
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    for file_path in sorted(SKILL_DIR.rglob("*")):
        if file_path.is_file():
            arcname = str(file_path.relative_to(SKILL_DIR))
            zf.write(file_path, arcname=arcname)
zip_bytes = buf.getvalue()
```

本地校验该 ZIP：`namelist()` 确认包含根级 `"SKILL.md"`（`['SKILL.md', 'references/hcp-objections.md', 'references/product-zanubrutinib.md', 'scripts/validate_skill_output.py']`），重新打开并解析 frontmatter，`name` 字段与原始文件一致 —— **PASS**。

| 操作 | 预期 | 实测结果 | 说明 |
|------|------|----------|------|
| ZIP 打包（`namelist()` 含根级 `SKILL.md`） | 打包成功，结构正确 | **PASS** | 4473 字节，4 个条目 |
| 重新打开 ZIP 校验 frontmatter `name` | 与原始 SKILL.md 一致 | **PASS** | `mr-training-creator` == `mr-training-creator` |
| `client.beta.skills.create_from_package(body=zip_bytes)`（API Key 认证，沿用 Test 3 的认证方式，因未探测到可用兜底模式） | 创建成功，`result.name == "mr-training-creator"` | **FAIL** — `403 AuthenticationTypeDisabled` | 与 inline 上传完全相同的错误：`Key based authentication is disabled for this resource.` |

## 5. Get / List / Download 往返实测

**SKIP** — 因为 Test 3、Test 4 均未能成功创建任何 Skill（`_created_skills` 列表为空），本轮无可供 get/list/download 验证的 Skill 名称，脚本按设计打印 `Skipped: no skills were created in Test 3/4` 并返回 `None`。此项待 Skill 上传认证问题解决后重新运行验证。

## 6. Toolbox Version + `skill_reference` 挂载实测

**SKIP** — Toolbox 挂载依赖 Test 4 成功创建 `mr-training-creator` Skill（脚本显式检查 `"mr-training-creator" not in _created_skills`），由于上游上传失败，Test 6 未执行，打印 `Skipped: 'mr-training-creator' skill was not created successfully in Test 4`。

已确认的 SDK 层面事实（本项目代码检查得出，未被本次运行推翻）：`project.beta.toolboxes.create_version()` **没有** typed 的 `skills` kwarg，REST API 接受顶层 `skills` 数组需通过 raw dict `body` 传入：

```python
body = {
    "description": "POC toolbox mounting the mr-training-creator skill",
    "tools": [],
    "skills": [{"type": "skill_reference", "name": "mr-training-creator"}],
}
client.beta.toolboxes.create_version(name=TOOLBOX_NAME, body=body)
```

`get_version()` 的 `as_dict()` 中是否会回显 `skills` 字段 —— **本次运行未能验证**（被上游阻塞），留待认证问题解决后补测。

## 7. Agent 消费 Toolbox 实测

**SKIP** — Test 7 依赖 Test 6 成功创建 Toolbox 版本，由于 Test 6 被跳过，Test 7 打印 `Skipped: Toolbox version was not created successfully in Test 6` 并返回 `None`。

已确认的 SDK 层面事实（代码检查，未被本次运行推翻）：该 SDK 版本中**不存在**用于"从 Agent 的 tools 列表引用 Toolbox"的 typed `Tool` 子类（已检查 `AzureAISearchTool`、`BingGroundingTool`、`FileSearchTool`、`MCPTool` 等，均无 `ToolboxTool`）。脚本设计了两级尝试：先尝试 raw dict tool `{"type": "toolbox", "name": ..., "version": ...}`，若被 SDK/API 拒绝则降级为 `metadata`-only fallback（仅在 Agent 的 `metadata` 中记录 `toolbox.name`/`toolbox.version`，**不是真正的 tool 绑定**）。这两级尝试均**未能实际执行**，因为上游 Toolbox 创建本身就未成功。

**"Agent 消费 Toolbox 内 Skill" 在本次实测中未能得出任何结论**（既未证实可行，也未证实不可行）——这是因为认证层面的阻塞发生在更早的 Skill 上传步骤，尚未触及 Agent-Toolbox 绑定这一层。

## 8. 认证模式对照

| 认证模式 | 端点 | 实测结果 | 状态码 | 说明 |
|----------|------|----------|--------|------|
| API Key（`AzureKeyCredentialPolicy`） | `beta.skills.create()` | **不生效** | 403 | `AuthenticationTypeDisabled` — 资源侧已禁用基于 Key 的认证 |
| API Key | `beta.skills.create_from_package()` | **不生效** | 403 | 同上，错误信息完全一致 |
| Entra ID（`DefaultAzureCredential`，本机 `az login`） | `beta.skills.create()` | **不生效** | 405 | `Method Not Allowed` —— 错误性质与 API Key 的 403 不同，未进一步排查是权限/RBAC 缺失还是该预览端点在 Entra ID 模式下的请求路径/方法不匹配 |

这与本项目此前 doc 01/02/README 中"API Key + Agent 模式 = 可行"的结论**并不矛盾**：那个结论针对的是 Voice Live API 的 `AgentSessionConfig` 连接路径（`azure-ai-voicelive` SDK），与本文档测试的 `azure-ai-projects` 的 `beta.skills`/`beta.toolboxes` 预览端点是完全不同的服务面。本次实测表明，至少在 `avarda-demo-prj` 这个 Foundry 资源上，**Skills 预览端点已被配置为禁用 Key 认证**，且本机的 Entra ID 身份也未能满足该端点的认证/方法要求。

## 9. 命名规则提醒

Skill 命名规则沿用 doc 08 §3.3：`^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`，最长 64 字符，不含 `--`。本次测试使用了与生产 Skill 名称区分的 POC 专用命名，避免污染真实资源：

- `mr-training-creator-inline-poc`（仅用于 inline `create()` 测试，避免与 ZIP 上传产生的 `mr-training-creator` 冲突）
- `mr-training-toolbox-poc`（Toolbox 名称）

真实 Skill `mr-training-creator` 本身满足该命名规则（已通过 Test 1 校验）。

## 10. 清理与建议顺序

脚本设计的删除顺序（依赖方向：先删除依赖资源，再删除被依赖资源）：

```
Agent（client.agents.delete）
  → Toolbox Version（project.beta.toolboxes.delete_version）
    → Toolbox（project.beta.toolboxes.delete）
      → Skill（project.beta.skills.delete）
```

每一步删除都包裹在独立的 `try/except` 中，单个删除失败不会阻塞后续删除。

**本次实测的实际清理结果**：由于 Test 3-7 均未成功创建任何云端资源（`_created_skills`、`_created_toolboxes`、`_created_agents` 三个列表均为空），`cleanup()` 在入口处的空检查（`if not (_created_agents or _created_toolboxes or _created_skills): return`）直接返回，**未打印任何清理日志，也未产生任何 API 调用** —— 这是符合预期的空跑（no-op），Foundry 项目中没有任何本次运行遗留的资源。

**生产环境建议**：Skill/Toolbox 生命周期管理应遵循同样的依赖方向进行清理；在自动化脚本或 CI 中操作 Skills/Toolbox 资源前，应先确认目标 Foundry 资源的认证策略（是否禁用 Key 认证），避免因认证配置差异导致脚本静默失败或产生误导性的清理跳过。

## 附：本次运行的完整终端输出摘要

```
Test 1: Validate Skill Frontmatter        [PASS]
Test 2: Package Skill as ZIP              [PASS]
Test 3: Create Skill Inline               [FAIL]  403 AuthenticationTypeDisabled (api-key) / 405 Method Not Allowed (entra-id fallback)
Test 4: Create Skill From Package         [FAIL]  403 AuthenticationTypeDisabled (api-key)
Test 5: Get/List/Download Roundtrip       [SKIP]  no skills created upstream
Test 6: Toolbox Version + skill_reference [SKIP]  no skill to reference upstream
Test 7: Agent Uses Toolbox                [SKIP]  no toolbox version upstream

Total: 2 passed, 2 failed, 3 skipped
Exit code: 1
```

无任何测试资源遗留在 Foundry 项目中（`_created_skills`/`_created_toolboxes`/`_created_agents` 均为空，`cleanup()` 空跑）。
