targetScope = 'subscription'

@description('Short project/resource prefix. Use lowercase letters and numbers where possible because several Azure resources have strict naming rules.')
@minLength(3)
param namePrefix string = 'aicoach'

@description('Deployment environment name.')
@allowed([
  'dev'
  'demo'
  'public'
  'private'
  'prod'
])
param environmentName string = 'public'

@description('Azure region for resource deployment.')
param location string = 'eastus2'

@description('Optional Azure region for Azure AI Foundry / AI Services resources. Leave empty to use location.')
param foundryLocation string = ''

@description('Optional resource group name. Leave empty to use rg-{namePrefix}-{environmentName}-{location}.')
param resourceGroupName string = ''

@description('High-level deployment profile. foundryOnly keeps the default footprint small; fullLegacy preserves the previous broad deployment shape.')
@allowed([
  'foundryOnly'
  'fullLegacy'
])
param deploymentMode string = 'foundryOnly'

@description('Network exposure profile. publicDemo keeps frontend and backend Container Apps publicly reachable; privateBackend adds an auto-created or user-supplied VNet, private ingress, and private endpoints for the first private backend path.')
@allowed([
  'publicDemo'
  'privateBackend'
])
param networkProfile string = 'publicDemo'

@description('Optional existing VNet name for privateBackend. Leave empty to auto-create a VNet using the supplied CIDR ranges.')
param vnetName string = ''

@description('VNet address prefix used when privateBackend auto-creates the VNet.')
param vnetAddressPrefix string = '10.60.0.0/16'

@description('Container Apps delegated subnet prefix used when privateBackend auto-creates the VNet.')
param containerAppsSubnetPrefix string = '10.60.0.0/23'

@description('Private endpoint subnet prefix used when privateBackend auto-creates the VNet.')
param privateEndpointsSubnetPrefix string = '10.60.2.0/24'

@description('Optional knowledge base capability. Azure AI Search is deployed only when this is azureAiSearch, fullLegacy mode is used, or enableAiSearch is true.')
@allowed([
  'none'
  'azureAiSearch'
])
param knowledgeBaseMode string = 'none'

@description('Optional owner tag.')
param owner string = ''

@description('Optional cost center tag.')
param costCenter string = ''

@description('ACR name. Must be globally unique, lowercase alphanumeric, 5-50 characters.')
@minLength(5)
@maxLength(50)
param containerRegistryName string = 'aicoachdemoacr'

@description('Storage account name. Must be globally unique, lowercase alphanumeric, 3-24 characters.')
@minLength(3)
@maxLength(24)
param storageAccountName string = 'aicoachdemost'

@description('PostgreSQL administrator login name.')
param postgresAdminLogin string = 'aicoachadmin'

@secure()
@description('PostgreSQL administrator password. Do not commit real values in parameter files.')
param postgresAdminPassword string

@secure()
@description('JWT signing secret. Do not commit real values in parameter files.')
param jwtSecret string

@secure()
@description('Stable application encryption key for encrypted service config values. Do not commit real values in parameter files.')
param encryptionKey string

@description('Backend container image. Pass a real ACR image after building and pushing.')
param backendImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('Frontend container image. Pass a real ACR image after building and pushing.')
param frontendImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('Backend CORS origins. Frontend normally calls the backend through nginx /api proxy, so same-origin browser calls do not require CORS.')
param corsOrigins string = 'http://localhost:5173,http://localhost:3000'

@description('Backend database auth mode. password preserves legacy DATABASE_URL auth; azureAd uses backend Managed Identity / Entra token auth.')
@allowed([
  'password'
  'azureAd'
])
param backendDatabaseAuthMode string = 'password'

@description('Service API key storage. database preserves encrypted DB storage; keyvault stores Admin UI service keys in Key Vault.')
@allowed([
  'database'
  'keyvault'
])
param azureServiceKeyStorage string = 'database'

@description('Microsoft Entra admin login/display name for PostgreSQL Flexible Server. Required when backendDatabaseAuthMode=azureAd for initial DB bootstrap.')
param postgresEntraAdminLogin string = ''

@description('Microsoft Entra admin object ID for PostgreSQL Flexible Server. Required when backendDatabaseAuthMode=azureAd for initial DB bootstrap.')
param postgresEntraAdminObjectId string = ''

@description('Microsoft Entra admin principal type for PostgreSQL Flexible Server.')
@allowed([
  'User'
  'Group'
  'ServicePrincipal'
])
param postgresEntraAdminPrincipalType string = 'User'

@description('Manage first-deployment bootstrap secrets in Key Vault and PostgreSQL admin password. Set false for later updates that should not rotate existing secrets.')
param manageBootstrapSecrets bool = true

@description('Whether to create or update the JWT signing secret in Key Vault.')
param manageJwtSecret bool = true

@description('Whether to create or update the application encryption key in Key Vault.')
param manageEncryptionKey bool = true

@description('Whether to create or update the PostgreSQL administrator password secret in Key Vault.')
param managePostgresPasswordSecret bool = true

@description('Whether to set the PostgreSQL administrator password. Required when creating a new PostgreSQL Flexible Server.')
param managePostgresAdminPassword bool = true

@description('Allow backend startup to create missing tables. Keep false for production/migration-governed deployments; use true for first-pass demo initialization.')
param databaseAutoCreateTables bool = false

@description('GitHub repository owner or organization for OIDC federation.')
param githubOwner string = 'huqianghui'

@description('GitHub repository name for OIDC federation.')
param githubRepo string = 'AI-Coach-vibe-coding'

@description('GitHub branch allowed to deploy through OIDC.')
param githubBranch string = 'main'

@description('Optional GitHub Environment allowed to deploy through OIDC. When set, creates an additional federated credential with an environment subject.')
param githubEnvironmentName string = environmentName

@description('Default Azure OpenAI chat/scoring deployment name.')
param chatDeploymentName string = 'gpt-4o'

@description('Default Azure OpenAI chat/scoring model name.')
param chatModelName string = 'gpt-4o'

@description('Default Azure OpenAI chat/scoring model version. Confirm available versions in the target region before deployment.')
param chatModelVersion string = '2024-11-20'

@allowed([
  'Standard'
  'GlobalStandard'
  'DataZoneStandard'
])
@description('Azure OpenAI chat/scoring deployment SKU. Use GlobalStandard when regional Standard quota is constrained.')
param chatDeploymentSkuName string = 'Standard'

@minValue(1)
@description('Default Azure OpenAI chat/scoring deployment capacity. For gpt-4o in Sweden Central, 120 maps to 120,000 TPM.')
param chatDeploymentCapacity int = 120

@description('Whether to include Azure AI / Foundry / OpenAI resources in the deployment.')
param enableAzureAi bool = true

@description('Whether to include Speech / Voice Live / Avatar resources in the deployment plan. fullLegacy also enables this for compatibility.')
param enableVoiceAndAvatar bool = false

@description('Whether to include Content Understanding resources in the deployment plan. fullLegacy also enables this for compatibility.')
param enableContentUnderstanding bool = false

@description('Whether to include Azure AI Search resources in the deployment plan. Prefer knowledgeBaseMode=azureAiSearch for new deployments.')
param enableAiSearch bool = false

var locationToken = replace(toLower(location), ' ', '')
var effectiveFoundryLocation = empty(foundryLocation) ? location : foundryLocation
var effectiveResourceGroupName = empty(resourceGroupName) ? 'rg-${namePrefix}-${environmentName}-${locationToken}' : resourceGroupName
var deploymentName = '${namePrefix}-${environmentName}-${locationToken}'
var isFullLegacyDeployment = deploymentMode == 'fullLegacy'
var deployAzureAi = enableAzureAi || isFullLegacyDeployment
var deployLegacyOpenAi = isFullLegacyDeployment
var deployVoiceAndAvatar = enableVoiceAndAvatar || isFullLegacyDeployment
var deployContentUnderstanding = enableContentUnderstanding || isFullLegacyDeployment
var deployAiSearch = enableAiSearch || knowledgeBaseMode == 'azureAiSearch' || isFullLegacyDeployment
var useAzureAdDatabaseAuth = backendDatabaseAuthMode == 'azureAd'
var commonTags = union({
  project: 'ai-coach'
  environment: environmentName
  managedBy: 'bicep'
}, empty(owner) ? {} : {
  owner: owner
}, empty(costCenter) ? {} : {
  costCenter: costCenter
})

resource deploymentResourceGroup 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: effectiveResourceGroupName
  location: location
  tags: commonTags
}

module monitoring './modules/monitoring.bicep' = {
  name: '${deploymentName}-monitoring'
  scope: deploymentResourceGroup
  params: {
    namePrefix: namePrefix
    environmentName: environmentName
    location: location
    tags: commonTags
  }
}

module managedIdentity './modules/managed-identity.bicep' = {
  name: '${deploymentName}-managed-identity'
  scope: deploymentResourceGroup
  params: {
    namePrefix: namePrefix
    environmentName: environmentName
    location: location
    tags: commonTags
  }
}

module containerRegistry './modules/container-registry.bicep' = {
  name: '${deploymentName}-container-registry'
  scope: deploymentResourceGroup
  params: {
    namePrefix: namePrefix
    environmentName: environmentName
    location: location
    tags: commonTags
    registryName: containerRegistryName
  }
}

module keyVault './modules/key-vault.bicep' = {
  name: '${deploymentName}-key-vault'
  scope: deploymentResourceGroup
  params: {
    namePrefix: namePrefix
    environmentName: environmentName
    location: location
    tags: commonTags
    jwtSecret: jwtSecret
    encryptionKey: encryptionKey
    postgresAdminPassword: postgresAdminPassword
    manageBootstrapSecrets: manageBootstrapSecrets
    manageJwtSecret: manageJwtSecret
    manageEncryptionKey: manageEncryptionKey
    managePostgresPasswordSecret: managePostgresPasswordSecret
    networkProfile: networkProfile
  }
}

module postgresql './modules/postgresql.bicep' = {
  name: '${deploymentName}-postgresql'
  scope: deploymentResourceGroup
  params: {
    namePrefix: namePrefix
    environmentName: environmentName
    location: location
    tags: commonTags
    administratorLogin: postgresAdminLogin
    administratorPassword: postgresAdminPassword
    manageAdministratorPassword: managePostgresAdminPassword
    activeDirectoryAuthEnabled: useAzureAdDatabaseAuth
    networkProfile: networkProfile
  }
}

module postgresqlEntraAdmin './modules/postgresql-entra-admin.bicep' = {
  name: '${deploymentName}-postgresql-entra-admin'
  scope: deploymentResourceGroup
  params: {
    serverName: postgresql.outputs.serverName
    activeDirectoryAuthEnabled: useAzureAdDatabaseAuth
    entraAdminLogin: postgresEntraAdminLogin
    entraAdminSid: postgresEntraAdminObjectId
    entraAdminPrincipalType: postgresEntraAdminPrincipalType
  }
}

module storage './modules/storage.bicep' = {
  name: '${deploymentName}-storage'
  scope: deploymentResourceGroup
  params: {
    namePrefix: namePrefix
    environmentName: environmentName
    location: location
    tags: commonTags
    storageAccountName: storageAccountName
    networkProfile: networkProfile
  }
}

module network './modules/network.bicep' = {
 name: '${deploymentName}-network'
 scope: deploymentResourceGroup
 params: {
   namePrefix: namePrefix
   environmentName: environmentName
   location: location
   tags: commonTags
   networkProfile: networkProfile
   vnetName: vnetName
   vnetAddressPrefix: vnetAddressPrefix
   containerAppsSubnetPrefix: containerAppsSubnetPrefix
   privateEndpointsSubnetPrefix: privateEndpointsSubnetPrefix
  storageAccountId: storage.outputs.summary.storageAccountId
  keyVaultId: keyVault.outputs.summary.vaultId
  postgresqlServerId: postgresql.outputs.summary.serverId
   foundryAccountId: deployAzureAi ? aiFoundry!.outputs.foundryAccountId : ''
 }
}

module containerApps './modules/container-apps.bicep' = {
  name: '${deploymentName}-container-apps'
  scope: deploymentResourceGroup
  dependsOn: [
    roleAssignments
  ]
  params: {
    namePrefix: namePrefix
    environmentName: environmentName
    location: location
    tags: commonTags
    logAnalyticsWorkspaceName: monitoring.outputs.logAnalyticsWorkspaceName
    applicationInsightsConnectionString: monitoring.outputs.applicationInsightsConnectionString
    registryLoginServer: containerRegistry.outputs.registryLoginServer
    backendIdentityId: managedIdentity.outputs.backendIdentityId
    backendIdentityName: managedIdentity.outputs.backendIdentityName
    backendIdentityClientId: managedIdentity.outputs.backendIdentityClientId
    backendImage: backendImage
    frontendImage: frontendImage
    postgresServerFqdn: postgresql.outputs.serverFqdn
    postgresDatabaseName: postgresql.outputs.databaseName
    postgresAdminLogin: postgresql.outputs.administratorLogin
    keyVaultUri: keyVault.outputs.summary.vaultUri
    storageAccountBlobEndpoint: storage.outputs.blobEndpoint
    storageContainerName: 'materials'
    postgresAdminPassword: postgresAdminPassword
    corsOrigins: corsOrigins
    backendDatabaseAuthMode: backendDatabaseAuthMode
    azureServiceKeyStorage: azureServiceKeyStorage
    databaseAutoCreateTables: databaseAutoCreateTables
    networkProfile: networkProfile
    managedEnvironmentInfrastructureSubnetId: network.outputs.infrastructureSubnetId
  }
}

module aiFoundry './modules/ai-foundry.bicep' = if (deployAzureAi) {
  name: '${deploymentName}-ai-foundry'
  scope: deploymentResourceGroup
  params: {
    namePrefix: namePrefix
    environmentName: environmentName
    location: effectiveFoundryLocation
    tags: commonTags
    projectName: '${namePrefix}-${environmentName}'
    chatDeploymentName: chatDeploymentName
    chatModelName: chatModelName
    chatModelVersion: chatModelVersion
    chatDeploymentSkuName: chatDeploymentSkuName
    chatDeploymentCapacity: chatDeploymentCapacity
    networkProfile: networkProfile
  }
}

module aiOpenAi './modules/ai-openai.bicep' = if (deployLegacyOpenAi) {
  name: '${deploymentName}-ai-openai'
  scope: deploymentResourceGroup
  params: {
    namePrefix: namePrefix
    environmentName: environmentName
    location: effectiveFoundryLocation
    tags: commonTags
    chatDeploymentName: chatDeploymentName
    chatModelName: chatModelName
    chatModelVersion: chatModelVersion
    chatDeploymentCapacity: chatDeploymentCapacity
  }
}

module speechAvatar './modules/speech-avatar.bicep' = if (deployVoiceAndAvatar) {
  name: '${deploymentName}-speech-avatar'
  scope: deploymentResourceGroup
  params: {
    namePrefix: namePrefix
    environmentName: environmentName
    location: location
    tags: commonTags
    enableAvatar: deployVoiceAndAvatar
  }
}

module contentUnderstanding './modules/content-understanding.bicep' = if (deployContentUnderstanding) {
  name: '${deploymentName}-content-understanding'
  scope: deploymentResourceGroup
  params: {
    namePrefix: namePrefix
    environmentName: environmentName
    location: effectiveFoundryLocation
    tags: commonTags
  }
}

module aiSearch './modules/ai-search.bicep' = if (deployAiSearch) {
  name: '${deploymentName}-ai-search'
  scope: deploymentResourceGroup
  params: {
    namePrefix: namePrefix
    environmentName: environmentName
    location: location
    tags: commonTags
  }
}

module githubOidc './modules/github-oidc.bicep' = {
  name: '${deploymentName}-github-oidc'
  scope: deploymentResourceGroup
  params: {
    namePrefix: namePrefix
    environmentName: environmentName
    location: location
    tags: commonTags
    githubOwner: githubOwner
    githubRepo: githubRepo
    githubBranch: githubBranch
    githubEnvironmentName: githubEnvironmentName
  }
}

module roleAssignments './modules/role-assignments.bicep' = {
  name: '${deploymentName}-role-assignments'
  scope: deploymentResourceGroup
  params: {
    namePrefix: namePrefix
    environmentName: environmentName
    location: location
    tags: commonTags
    backendIdentityPrincipalId: managedIdentity.outputs.backendIdentityPrincipalId
    enableAzureAi: deployAzureAi
    enableVoiceAndAvatar: deployVoiceAndAvatar
    enableContentUnderstanding: deployContentUnderstanding
    enableAiSearch: deployAiSearch
    githubDeploymentPrincipalId: githubOidc.outputs.githubDeploymentPrincipalId
  }
}

output resourceGroupName string = effectiveResourceGroupName
output location string = location
output foundryLocation string = effectiveFoundryLocation
output tenantId string = tenant().tenantId
output containerRegistryName string = containerRegistry.outputs.summary.registryName
output containerRegistryLoginServer string = containerRegistry.outputs.registryLoginServer
output storageAccountName string = storage.outputs.summary.storageAccountName
output storageBlobEndpoint string = storage.outputs.blobEndpoint
output backendContainerAppName string = containerApps.outputs.backendAppName
output backendBootstrapJobName string = containerApps.outputs.backendBootstrapJobName
output frontendContainerAppName string = containerApps.outputs.frontendAppName
output backendUrl string = containerApps.outputs.backendUrl
output frontendUrl string = containerApps.outputs.frontendUrl
output postgresServerFqdn string = postgresql.outputs.serverFqdn
output postgresDatabaseName string = postgresql.outputs.databaseName
output backendIdentityName string = managedIdentity.outputs.backendIdentityName
output backendIdentityPrincipalId string = managedIdentity.outputs.backendIdentityPrincipalId
output githubDeploymentClientId string = githubOidc.outputs.githubDeploymentClientId
output deployment object = {
  monitoring: monitoring.outputs.summary
  managedIdentity: managedIdentity.outputs.summary
  containerRegistry: containerRegistry.outputs.summary
  keyVault: keyVault.outputs.summary
  postgresql: postgresql.outputs.summary
  storage: storage.outputs.summary
  containerApps: containerApps.outputs.summary
  profile: {
    deploymentMode: deploymentMode
    networkProfile: networkProfile
    knowledgeBaseMode: knowledgeBaseMode
    location: location
    foundryLocation: effectiveFoundryLocation
    enableAzureAi: deployAzureAi
    enableVoiceAndAvatar: deployVoiceAndAvatar
    enableContentUnderstanding: deployContentUnderstanding
    enableAiSearch: deployAiSearch
  }
  aiFoundry: deployAzureAi ? aiFoundry!.outputs.summary : null
  aiOpenAi: deployLegacyOpenAi ? aiOpenAi!.outputs.summary : null
  speechAvatar: deployVoiceAndAvatar ? speechAvatar!.outputs.summary : null
  contentUnderstanding: deployContentUnderstanding ? contentUnderstanding!.outputs.summary : null
  aiSearch: deployAiSearch ? aiSearch!.outputs.summary : null
  githubOidc: githubOidc.outputs.summary
  roleAssignments: roleAssignments.outputs.summary
}

output githubActions object = {
  AZURE_CLIENT_ID: githubOidc.outputs.githubDeploymentClientId
  AZURE_TENANT_ID: tenant().tenantId
  AZURE_SUBSCRIPTION_ID: subscription().subscriptionId
  AZURE_RESOURCE_GROUP: effectiveResourceGroupName
  ACR_NAME: containerRegistry.outputs.summary.registryName
  RESOURCE_GROUP: effectiveResourceGroupName
  BACKEND_APP_NAME: containerApps.outputs.backendAppName
  BACKEND_BOOTSTRAP_JOB_NAME: containerApps.outputs.backendBootstrapJobName
  FRONTEND_APP_NAME: containerApps.outputs.frontendAppName
}
