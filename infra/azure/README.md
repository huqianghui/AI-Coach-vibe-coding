# Azure 一键部署

这个目录包含 AI Coach 平台的 Azure Bicep 部署资产。

当前目标是在不修改应用代码的前提下，提供一套可部署的 Azure 目标环境。基础设施在这里创建；如果某些能力需要应用代码配合，会在文档中明确列为缺口，而不是隐藏在模板里。

## 当前默认值

| 配置 | 默认值 |
|---|---|
| 应用/通用资源区域 | `swedencentral` |
| Foundry/AI Services 区域 | 默认跟随应用区域，可用 `-FoundryLocation` 单独指定 |
| 环境 | `public` |
| 名称前缀 | `aicoach` |
| 部署模式 | `foundryOnly` |
| 网络配置 | `publicDemo` |
| 知识库模式 | `none` |
| 数据库认证 | PostgreSQL Entra / Managed Identity |
| Azure service key 存储 | Key Vault |

## 默认部署范围

默认脚本会部署 Foundry/OpenAI 核心能力和应用运行平台。较重或当前应用未直接使用的服务保留为显式参数开启，方便兼容旧 demo 或完整 demo，但不会默认创建。

默认包含：

- Azure Container Registry
- 后端和前端 Azure Container Apps
- Log Analytics 和 Application Insights
- 用户分配 Managed Identity
- Key Vault
- Azure Database for PostgreSQL Flexible Server
- Storage Account 和 Blob containers
- Azure AI Foundry / Azure AI Services
- Azure OpenAI `gpt-4o` 模型部署，用于 chat/scoring
- GitHub Actions OIDC bootstrap
- RBAC role assignments

可选能力：

- `-DeploymentMode fullLegacy`：兼容之前较完整的部署形态，会启用 Speech/Avatar、Content Understanding 和 Azure AI Search。
- `-NetworkProfile publicDemo`：默认网络配置，frontend 和 backend Container Apps 都对外公开，方便 demo 访问。
- `-NetworkProfile privateBackend`：私有后端网络配置，frontend 保持公网入口，backend 使用 internal ingress，Container Apps Environment 接入 VNet，并为 Storage、Key Vault、PostgreSQL 和 Foundry data-plane 创建 private endpoints。
- `-KnowledgeBaseMode azureAiSearch`：只额外部署 Azure AI Search，不切换到完整 legacy profile。
- `-ResourceGroupName <name>`：指定资源组名称；不传时使用 `rg-{prefix}-{environment}-{location}`。
- `-FoundryLocation <region>`：只将 Azure AI Foundry、legacy Azure OpenAI 和 Content Understanding 资源部署到指定区域；不传时默认使用 `-Location`。

默认不会部署：

- Azure AI Search：因为当前应用代码还没有直接使用 Azure AI Search client。
- Azure Speech / Avatar：只有 `fullLegacy` 时部署。
- Azure Content Understanding：只有 `fullLegacy` 时部署。
- `gpt-realtime-1.5`：Voice Live 的 realtime 模型由应用/Foundry runtime 的白名单选择，不需要 Bicep 创建 realtime model deployment。

## 如何部署

先登录并选择订阅：

```powershell
az login
az account set --subscription "<subscription-id-or-name>"
```

建议先测试区域可用性并执行 what-if：

```powershell
.\infra\azure\scripts\test-region-availability.ps1 -StopOnFirstPass
.\infra\azure\scripts\deploy.ps1 -WhatIf
```

确认 what-if 没问题后部署基础设施：

```powershell
.\infra\azure\scripts\deploy.ps1
```

部署可作为 CD 目标的 public 环境：

```powershell
.\infra\azure\scripts\deploy.ps1 `
  -ResourceGroupName "ai-coach-public-rg" `
  -EnvironmentName "public" `
  -NetworkProfile publicDemo `
  -Location eastasia `
  -FoundryLocation eastus2 `
  -DeployApp
```

脚本会生成本地忽略文件 `infra\azure\.local\main.parameters.generated.json`，然后执行 Bicep 部署并输出 GitHub OIDC 配置值。云端默认使用 PostgreSQL Entra / Managed Identity 和 Key Vault service-key storage。后续重复运行时，如果资源组里已经有 Key Vault，脚本不会读取 Key Vault secret，也不会默认轮换 bootstrap secrets；只有显式切到 legacy password DB 模式且仍需要生成 `DATABASE_URL` 时，脚本才会提示输入当前 PostgreSQL admin password。

脚本支持失败后重跑：Bicep 负责资源增量部署；脚本只按 Key Vault secret 和 PostgreSQL server 的实际存在状态决定是否补写缺失 secret、是否给新建 PostgreSQL 传 administrator password，避免部分失败后重跑时误轮换已有 secret 或漏传首次创建所需密码。

## 常用参数

指定资源组名称：

```powershell
.\infra\azure\scripts\deploy.ps1 -ResourceGroupName "rg-your-name"
```

应用资源靠近用户、Foundry 放到模型可用区域：

```powershell
.\infra\azure\scripts\deploy.ps1 `
  -Location "eastasia" `
  -FoundryLocation "eastus2"
```

部署完整 legacy 资源：

```powershell
.\infra\azure\scripts\deploy.ps1 -DeploymentMode fullLegacy
```

只额外启用 Azure AI Search：

```powershell
.\infra\azure\scripts\deploy.ps1 -KnowledgeBaseMode azureAiSearch
```

部署私有后端网络 profile：

```powershell
.\infra\azure\scripts\deploy.ps1 `
  -ResourceGroupName "ai-coach-private-rg" `
  -EnvironmentName "private" `
  -NetworkProfile privateBackend `
  -Location eastasia `
  -FoundryLocation eastus2 `
  -ChatDeploymentSkuName GlobalStandard `
  -ChatDeploymentCapacity 120
```

如果不传 `-VnetName`，模板会自动创建 VNet，并使用 `-VnetAddressPrefix`、`-ContainerAppsSubnetPrefix`、`-PrivateEndpointsSubnetPrefix` 的 CIDR 默认值。`privateBackend` 会为 PostgreSQL Flexible Server 创建 private endpoint 并关闭 public access；Foundry Tools private endpoint 会同时关联 `privatelink.cognitiveservices.azure.com`、`privatelink.openai.azure.com` 和 `privatelink.services.ai.azure.com`，匹配 Azure Portal 默认 DNS zone 行为。基础设施更新不需要 `-DeployApp`；如果 backend 是 internal ingress，本地机器不能直接验证 backend URL，只有显式传 `-Verify` 才会运行公网 health check。

默认云端安全路径已经启用 PostgreSQL Entra/MI + Admin UI service key 写 Key Vault：

```powershell
.\infra\azure\scripts\deploy.ps1
```

如果不传 PostgreSQL Entra admin 参数，脚本会自动使用当前 `az login` 用户。首次部署后，脚本会自动运行 DB bootstrap，为后端 Managed Identity 创建/授权数据库 role；`publicDemo` 会从本机执行这一步，并临时把当前公网 IP 加入 PostgreSQL firewall，完成后默认删除该临时规则；`privateBackend` 会在后端 Container Apps Job 内执行这一步，避免从本机公网连接已私有化的 PostgreSQL。运行 `-DeployApp` 时还会启动后端 Container Apps Job，在 Azure 环境内执行 Alembic schema migration 并写入幂等 sample 数据（SkillHub、HCP profiles、scenarios、training materials）。如果只想部署 infra 不做 DB role bootstrap，可传 `-SkipDbBootstrap`；如果要完全跳过 schema/sample bootstrap，可传 `-SkipAppBootstrap`。PostgreSQL Entra admin 后续可以在 Azure Portal 中改成 group 或专用 bootstrap identity。生产环境建议显式传 Entra group：

```powershell
.\infra\azure\scripts\deploy.ps1 `
  -PostgresEntraAdminLogin "<admin-group-name>" `
  -PostgresEntraAdminObjectId "<admin-group-object-id>" `
  -PostgresEntraAdminPrincipalType Group
```

这个模式下，后端 Container App 使用 Managed Identity 获取 PostgreSQL token，并通过 `SECRET_STORE=keyvault` 让 Admin UI 更新 Azure service API key 时写入 Key Vault，而不是写入 DB。部署脚本会用 PostgreSQL Entra admin 身份自动运行 `backend\scripts\bootstrap_postgres_entra.py`，通过后端 managed identity 的 object id 创建并授权数据库 role；在 `privateBackend` 下，这一步通过后端 Container Apps Job 运行在 VNet 内。随后后端 Container Apps Job 使用同一个后端镜像和 Managed Identity 在 Azure 网络内运行 `backend\scripts\bootstrap_app.py`，完成 Alembic migration 和 sample data bootstrap。云端后端仍保持 `DATABASE_AUTO_CREATE_TABLES=false`。

如果需要旧兼容模式，显式传：

```powershell
.\infra\azure\scripts\deploy.ps1 `
  -BackendDatabaseAuthMode password `
  -AzureServiceKeyStorage database
```

部署基础设施后，如果还要构建并推送后端/前端镜像，然后更新 Container Apps：

```powershell
.\infra\azure\scripts\deploy.ps1 -DeployApp
```

运行 `-DeployApp` 时，请确认当前本地 branch/worktree 就是你要部署到 Azure 测试的代码。ACR build 使用本地 `backend\` 和 `frontend\` 目录，所以如果要在云上测试 PostgreSQL、Blob Storage、Rubric 或 Voice 相关应用改动，需要先切到包含这些代码的分支再运行命令。

如果只是基础设施改动，应用已经部署过，可以加 `-Verify` 检查后端 `/api/health` 和前端 `/health`：

```powershell
.\infra\azure\scripts\deploy.ps1 -Verify
```

`-DeployApp` 默认会显式运行 schema/sample bootstrap；如只想迁移 schema、不写 sample 数据，可传：

```powershell
.\infra\azure\scripts\deploy.ps1 -DeployApp -SkipSampleData
```

如外部流水线已经负责 migration 和 sample bootstrap，可传：

```powershell
.\infra\azure\scripts\deploy.ps1 -DeployApp -SkipAppBootstrap
```

## 当前云端测试运行方式

- 默认云端模式下，PostgreSQL 使用 `DATABASE_AUTH_MODE=azure_ad`、Managed Identity token 和 DB bootstrap 授权；只有显式传 `-BackendDatabaseAuthMode password` 才使用 legacy `DATABASE_URL`。
- Azure Blob Storage 已经通过 Bicep 注入到后端 Container App：
  - `STORAGE_BACKEND=azure_blob`
  - `AZURE_STORAGE_ACCOUNT_URL=<storage account blob endpoint>`
  - `AZURE_STORAGE_CONTAINER_NAME=materials`
  - 后端 managed identity 拥有 `Storage Blob Data Contributor`。
- 本地开发不受这些云端设置影响；如果没有设置 `STORAGE_BACKEND`，后端仍然默认使用本地存储。
- Sample/demo seed data 默认由部署脚本显式写入，包括 SkillHub、HCP profiles、scenarios、training materials；materials 文件会上传到 Azure Blob，DB 中保存 material metadata/version。
- 后端部署镜像安装 `.[postgresql,voice]`，因此 Azure 镜像包含 PostgreSQL 和 Voice Live runtime 依赖。

## 相关文档

- `docs\architecture.md`：Azure 部署拓扑。
- `docs\parameters.md`：必填和可选参数。
- `docs\operations.md`：部署、镜像更新、验证、GitHub OIDC 和删除资源。
- `docs\deployment-lessons-learned.md`：首次部署遇到的 Azure 问题和修复经验。
- `docs\known-gaps.md`：当前应用/runtime 缺口，说明哪些问题不能只靠基础设施解决。

## 重要限制

这个目录不会合并应用功能分支。基础设施可以提供云端配置，但实际部署出来的应用镜像，只包含运行 `-DeployApp` 时本地 branch/worktree 里的代码。
