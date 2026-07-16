# 18 - Foundry IQ 权限配置指南（Entra ID / Managed Identity 优先）

本文记录在 AI Coach 项目中配置 Azure AI Foundry IQ / Knowledge Base 时，需要给哪些身份配置哪些权限。目标是让同事后续能按步骤完成 Foundry IQ、Azure AI Search、Blob Storage 和 HCP Agent 的权限配置。

## 目标架构

```text
Blob Storage 文档
  -> Azure AI Search Knowledge Source / Indexer
  -> Foundry IQ Knowledge Base
  -> Foundry Agent Knowledge / MCP Tool
  -> AI Coach HCP Agent / Playground 使用知识库回答问题
```

推荐认证方式：

```text
Entra ID / Managed Identity 优先
API Key 只作为临时兼容方案
```

## 涉及的身份

| 身份 | 在哪里看到 | 用途 |
|---|---|---|
| Search service system-assigned identity | Azure AI Search -> Identity | Search indexer 读取 Blob、调用 Foundry/OpenAI embedding/chat model |
| Foundry project system-assigned identity | Foundry project 子资源 / CLI 查询 | Foundry project 管理 Search index、knowledge base、Agent knowledge |
| Backend user-assigned identity | Container App backend / Managed Identity | AI Coach 后端读取配置、调用 Foundry、Key Vault、Search 等 |
| 当前配置人员账号 | Azure Portal 登录用户 | 在 Portal 上创建资源、添加 role assignment、创建 knowledge source/base |

注意：Foundry account 本体的 Identity 页面可能是 Off；这不代表 Foundry project 没有 identity。Foundry project 是 `Microsoft.CognitiveServices/accounts/projects` 子资源，通常有自己的 system-assigned identity。

## 推荐权限清单

| 授权对象 | Role | Scope | 为什么需要 |
|---|---|---|---|
| Search service system-assigned identity | Cognitive Services User | Foundry / AI Services account，例如 `aicoach-public-foundry-...` | Search 在生成 embedding / 调用模型时访问 Azure AI 模型 |
| Search service system-assigned identity | Storage Blob Data Reader | Storage account 或具体 container，例如 `foundry-iq` | Search indexer 从 Blob 读取知识源文件 |
| Foundry project system-assigned identity | Search Index Data Contributor | Azure AI Search service | Foundry project 读写 Search index 文档/索引数据 |
| Foundry project system-assigned identity | Search Service Contributor | Azure AI Search service | Foundry project 创建/管理 index、indexer、knowledge base 等 Search 资源 |
| Backend user-assigned identity | Search Service Contributor 或 Search Index Data Contributor | Azure AI Search service | AI Coach 后端如需直接列出/read Foundry IQ knowledgebases 或管理连接时使用 |
| 当前配置人员账号 | Contributor / User Access Administrator 或相应资源级角色 | Foundry、Search、Storage | Portal 创建资源和添加 RBAC 时需要 |

最小可先配：

```text
Search identity -> Foundry account: Cognitive Services User
Search identity -> Storage/container: Storage Blob Data Reader
Foundry project identity -> Search: Search Index Data Contributor
Foundry project identity -> Search: Search Service Contributor
```

## Step 1：开启 Azure AI Search 的 system-assigned identity

Portal 路径：

```text
Azure AI Search
  -> 选择 Search service
  -> Identity
  -> System assigned
  -> On
  -> Save
```

保存后记录 Search identity 的 principal id。CLI 查询：

```powershell
az search service show `
  -g <resource-group> `
  -n <search-service-name> `
  --query identity
```

## Step 2：给 Search identity 访问 Foundry 模型的权限

Portal 路径：

```text
Azure AI Foundry / AI Services account
  -> Access control (IAM)
  -> Add role assignment
  -> Role: Cognitive Services User
  -> Members: Managed identity
  -> 选择 Azure AI Search service 的 system-assigned identity
  -> Review + assign
```

Scope 是 Foundry / AI Services account，不是 Foundry project。

用途：

- embedding model：例如 `text-embedding-ada-002`
- chat completion model：例如 `gpt-4o`

如果 embedding 和 chat model 都在同一个 Foundry account 下，一个 `Cognitive Services User` role assignment 就够。

## Step 3：给 Search identity 读取 Blob 的权限

如果 Knowledge Source 使用 Blob Storage：

Portal 路径：

```text
Storage Account
  -> Access control (IAM)
  -> Add role assignment
  -> Role: Storage Blob Data Reader
  -> Members: Managed identity
  -> 选择 Azure AI Search service 的 system-assigned identity
  -> Review + assign
```

Scope 可以是整个 Storage account，也可以缩到具体 container。建议为 Foundry IQ 单独建 container：

```text
foundry-iq
```

不要直接复用 AI Coach 应用的 `materials` 根目录，避免和 Skill/材料上传互相影响。如果必须复用 `materials`，至少使用独立路径前缀：

```text
materials/foundry-iq/
```

## Step 4：给 Foundry project identity 管理 Search 的权限

先找到 Foundry project identity。CLI 示例：

```powershell
az resource list `
  -g <resource-group> `
  --resource-type "Microsoft.CognitiveServices/accounts/projects" `
  --query "[].{name:name,principalId:identity.principalId}"
```

Portal 路径：

```text
Azure AI Search
  -> Access control (IAM)
  -> Add role assignment
  -> Role: Search Index Data Contributor
  -> Members: Managed identity
  -> 选择 Foundry project identity
  -> Review + assign
```

如果 Foundry Portal 要创建/管理 index、indexer、knowledge base，再加：

```text
Role: Search Service Contributor
Scope: Azure AI Search service
Member: Foundry project identity
```

## Step 5：创建 Search connection

推荐使用 Entra ID / Managed Identity connection。

如果 AI Coach 应用当前版本还只支持 API Key connection，则可以临时创建 API Key connection 或打开 Search local auth。但长期方向应改应用支持 AAD connection。

检查 Search local auth：

```powershell
az search service show `
  -g <resource-group> `
  -n <search-service-name> `
  --query "{disableLocalAuth:disableLocalAuth,publicNetworkAccess:publicNetworkAccess,status:status}"
```

如果临时要用 API Key：

```powershell
az search service update `
  -g <resource-group> `
  -n <search-service-name> `
  --disable-local-auth false
```

注意：公司 Policy 可能会重新禁用 local auth。

## Step 6：创建 Knowledge Source / Knowledge Base

在 Foundry Portal 中：

```text
Foundry project
  -> Knowledge
  -> Knowledge sources
  -> Add source
  -> Azure Blob Storage
  -> 选择 storage account/container/path
```

然后创建 Knowledge Base，选择：

- Knowledge source
- Embedding model，例如 `text-embedding-ada-002`
- Chat completion model，例如 `gpt-4o`

为什么需要两个模型：

| 模型 | 作用 |
|---|---|
| Embedding model | 把文档和用户问题转成向量，用于检索 |
| Chat completion model | 对检索到的内容进行推理、组织和生成回答 |

## Step 7：确认索引是否处理文件

Foundry Portal 能看 Knowledge Base 的高层状态，但底层 index / indexer 诊断建议到 Azure AI Search 查看：

```text
Azure AI Search
  -> Search management
  -> Indexes
  -> Indexers
```

CLI 查询 indexer 状态：

```powershell
$token = az account get-access-token --resource "https://search.azure.com" --query accessToken -o tsv
$headers = @{ Authorization = "Bearer $token" }

Invoke-RestMethod `
  -Method Get `
  -Uri "https://<search-name>.search.windows.net/indexers/<indexer-name>/status?api-version=2024-07-01" `
  -Headers $headers
```

如果上传文件后没有立刻生效，可以手动运行 indexer：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "https://<search-name>.search.windows.net/indexers/<indexer-name>/run?api-version=2024-07-01" `
  -Headers $headers
```

## Step 8：把 Knowledge Base 加到 Agent

在 Foundry Portal 中：

```text
Foundry project
  -> Agents
  -> 选择 Agent
  -> Knowledge
  -> Add knowledge
  -> 从 Existing knowledge base 列表选择 KB
  -> Save / Publish new version
```

不要手动粘贴 MCP URL。应从 Knowledge Base 列表选择，让 Portal 自动创建/绑定 RemoteTool connection。

## RemoteTool connection 是什么

Foundry IQ Agent 调用 KB 时，本质上调用的是一个 MCP endpoint：

```text
https://<search>.search.windows.net/knowledgebases/<kb-name>/mcp
```

这个 endpoint 需要认证。RemoteTool connection 就是 Agent runtime 调用 MCP endpoint 时使用的认证配置。

正确的 Agent YAML 应该类似：

```yaml
tools:
  - type: mcp
    server_label: kb-knowledgebase349-xxxxx
    server_url: https://<search>.search.windows.net/knowledgebases/knowledgebase349/mcp?api-version=2026-05-01-preview
    require_approval: never
    project_connection_id: kb-knowledgebase349-xxxxx
```

如果只有 `server_url`，没有 `project_connection_id`，运行时通常会报：

```text
Authentication failed when connecting to the MCP server ... 401 Unauthorized
```

## 验证方式

上传一个只存在于 KB 的测试文件，例如：

```text
唯一验证暗号：BG-HCP-IQ-CHEN-20260716。
```

索引完成并把 KB 加到 Agent 后，问：

```text
请先检索知识库，查询“陈俊医生 Foundry IQ 知识库测试暗号”，然后告诉我唯一验证暗号是什么。
```

预期回答包含：

```text
BG-HCP-IQ-CHEN-20260716
```

如果直接调用 KB MCP endpoint 能检索到，但 Agent 不回答，通常是：

- Agent 没有调用 `knowledge_base_retrieve`
- Agent instructions 没要求先检索知识库
- Agent tool 没绑定 RemoteTool connection
- Playground 没使用最新 Agent version

建议在 Agent instructions 里增加：

```text
知识库使用规则：
- 当用户询问私有笔记、验证暗号、上传资料、培训材料、产品细节，或任何可能存在于知识库中的信息时，必须先调用 knowledge_base_retrieve 工具进行检索，再回答。
- 在检索知识库之前，不要直接回答“我不知道”。
- 如果用户提到“测试暗号”、“Foundry IQ”、“私有知识”、“私有偏好”或“上传资料”，必须优先检索知识库。
```

## 常见问题

### Portal 能看到 KB，但 AI Coach 应用看不到

当前应用后端如果只支持 API Key connection，而 Foundry connection 是 AAD，就可能看不到 KB。长期应让应用支持 AAD/Managed Identity 读取 Search `/knowledgebases` API。

### Portal Playground 调 KB 时报 401

检查 Agent YAML 是否有：

```text
project_connection_id
```

如果没有，从 Agent Knowledge 中移除 KB，再通过 Existing knowledge base 重新添加并发布新版本。

### 上传图片能不能索引

纯图片需要 OCR / image extraction。Foundry IQ 创建的 indexer 可能启用：

```text
imageAction: generateNormalizedImages
```

这会产生额外 image extraction charge。图片里的文字/图表是否能被有效检索，取决于 Search skillset / OCR / image extraction 配置。最稳方式是先把图片内容转成文字、Markdown 或 OCR 结果再入库。

