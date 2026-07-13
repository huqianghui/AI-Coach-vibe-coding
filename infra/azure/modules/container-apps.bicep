targetScope = 'resourceGroup'

param namePrefix string
param environmentName string
param location string
param tags object

param logAnalyticsWorkspaceName string
param applicationInsightsConnectionString string
param registryLoginServer string
param backendIdentityId string
param backendIdentityName string
param backendIdentityClientId string
param backendImage string
param frontendImage string
param promptOptimizerImage string = 'linshen/prompt-optimizer:2.11.7'
param postgresServerFqdn string
param postgresDatabaseName string
param postgresAdminLogin string
param storageAccountBlobEndpoint string
param storageContainerName string = 'materials'
param keyVaultUri string

@secure()
param postgresAdminPassword string

param corsOrigins string
@allowed([
  'password'
  'azureAd'
])
param backendDatabaseAuthMode string = 'password'

@allowed([
  'database'
  'keyvault'
])
param azureServiceKeyStorage string = 'database'

param databaseAutoCreateTables bool = true

@allowed([
  'publicDemo'
  'privateBackend'
])
param networkProfile string = 'publicDemo'

param managedEnvironmentInfrastructureSubnetId string = ''

var environmentResourceName = 'cae-${namePrefix}-${environmentName}'
var backendAppName = 'ca-${namePrefix}-${environmentName}-backend'
var frontendAppName = 'ca-${namePrefix}-${environmentName}-frontend'
var promptOptimizerAppName = 'ca-${namePrefix}-${environmentName}-po'
var backendBootstrapJobName = 'job-${namePrefix}-${environmentName}-bootstrap'
var backendIngressExternal = networkProfile == 'publicDemo'
var usePrivateVNet = networkProfile == 'privateBackend' && !empty(managedEnvironmentInfrastructureSubnetId)
var useAzureAdDatabaseAuth = backendDatabaseAuthMode == 'azureAd'
var backendFqdn = '${backendAppName}.${managedEnvironment.properties.defaultDomain}'
var promptOptimizerProxyBaseUrl = 'https://${backendFqdn}/api/v1/internal/openai/v1'

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: logAnalyticsWorkspaceName
}

resource managedEnvironment 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: environmentResourceName
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: workspace.properties.customerId
        sharedKey: workspace.listKeys().primarySharedKey
      }
    }
    vnetConfiguration: usePrivateVNet ? {
      infrastructureSubnetId: managedEnvironmentInfrastructureSubnetId
    } : null
  }
}

resource backendApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: backendAppName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${backendIdentityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: managedEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: backendIngressExternal
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        {
          server: registryLoginServer
          identity: backendIdentityId
        }
      ]
      secrets: [
        {
          name: 'database-url'
          #disable-next-line use-secure-value-for-secure-inputs
          value: 'postgresql+asyncpg://${postgresAdminLogin}:${postgresAdminPassword}@${postgresServerFqdn}:5432/${postgresDatabaseName}?ssl=require'
        }
        {
          name: 'secret-key'
          keyVaultUrl: '${keyVaultUri}secrets/jwt-secret-key'
          identity: backendIdentityId
        }
        {
          name: 'encryption-key'
          keyVaultUrl: '${keyVaultUri}secrets/encryption-key'
          identity: backendIdentityId
        }
        {
          name: 'prompt-optimizer-proxy-secret'
          keyVaultUrl: '${keyVaultUri}secrets/prompt-optimizer-proxy-secret'
          identity: backendIdentityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'backend'
          image: backendImage
          env: [
            {
              name: 'DATABASE_URL'
              secretRef: 'database-url'
            }
            {
              name: 'DATABASE_AUTH_MODE'
              value: useAzureAdDatabaseAuth ? 'azure_ad' : 'password'
            }
            {
              name: 'DATABASE_HOST'
              value: postgresServerFqdn
            }
            {
              name: 'DATABASE_NAME'
              value: postgresDatabaseName
            }
            {
              name: 'DATABASE_USER'
              value: backendIdentityName
            }
            {
              name: 'DATABASE_AUTO_CREATE_TABLES'
              value: databaseAutoCreateTables ? 'true' : 'false'
            }
            {
              name: 'SECRET_KEY'
              secretRef: 'secret-key'
            }
            {
              name: 'ENCRYPTION_KEY'
              secretRef: 'encryption-key'
            }
            {
              name: 'DEBUG'
              value: 'false'
            }
            {
              name: 'REGION'
              value: 'global'
            }
            {
              name: 'CORS_ORIGINS'
              value: corsOrigins
            }
            {
              name: 'STORAGE_BACKEND'
              value: 'azure_blob'
            }
            {
              name: 'AZURE_STORAGE_ACCOUNT_URL'
              value: storageAccountBlobEndpoint
            }
            {
              name: 'AZURE_STORAGE_CONTAINER_NAME'
              value: storageContainerName
            }
            {
              name: 'SECRET_STORE'
              value: azureServiceKeyStorage
            }
            {
              name: 'AZURE_KEY_VAULT_URL'
              value: keyVaultUri
            }
            {
              name: 'DEFAULT_LLM_PROVIDER'
              value: 'mock'
            }
            {
              name: 'DEFAULT_STT_PROVIDER'
              value: 'mock'
            }
            {
              name: 'DEFAULT_TTS_PROVIDER'
              value: 'mock'
            }
            {
              name: 'DEFAULT_AVATAR_PROVIDER'
              value: 'mock'
            }
            {
              name: 'AZURE_CLIENT_ID'
              value: backendIdentityClientId
            }
            {
              name: 'VOICE_SCORING_TRANSCODE_ENABLED'
              value: 'true'
            }
            {
              name: 'VOICE_SCORING_TRANSCODE_TIMEOUT_SECONDS'
              value: '120'
            }
            {
              name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
              value: applicationInsightsConnectionString
            }
            {
              name: 'PROMPT_OPTIMIZER_MCP_URL'
              value: 'https://${promptOptimizerApp.properties.configuration.ingress.fqdn}/mcp'
            }
            {
              name: 'PROMPT_OPTIMIZER_PROXY_SECRET'
              secretRef: 'prompt-optimizer-proxy-secret'
            }
            {
              name: 'PROMPT_OPTIMIZER_PROXY_SECRET_SOURCE'
              value: 'keyvault'
            }
          ]
          resources: {
            cpu: json('1.0')
            memory: '2Gi'
          }
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 2
      }
    }
  }
}

resource promptOptimizerApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: promptOptimizerAppName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${backendIdentityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: managedEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: false
        targetPort: 80
        transport: 'auto'
        allowInsecure: false
      }
      secrets: [
        {
          name: 'prompt-optimizer-proxy-secret'
          keyVaultUrl: '${keyVaultUri}secrets/prompt-optimizer-proxy-secret'
          identity: backendIdentityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'prompt-optimizer'
          image: promptOptimizerImage
          env: [
            {
              name: 'MCP_DEFAULT_MODEL_PROVIDER'
              value: 'custom'
            }
            {
              name: 'MCP_DEFAULT_LANGUAGE'
              value: 'zh'
            }
            {
              name: 'VITE_CUSTOM_API_BASE_URL'
              value: promptOptimizerProxyBaseUrl
            }
            {
              name: 'VITE_CUSTOM_API_KEY'
              secretRef: 'prompt-optimizer-proxy-secret'
            }
            {
              name: 'VITE_CUSTOM_API_MODEL'
              value: 'prompt-optimizer'
            }
            {
              name: 'MCP_DEFAULT_MODEL_BASE_URL'
              value: promptOptimizerProxyBaseUrl
            }
            {
              name: 'MCP_DEFAULT_MODEL_API_KEY'
              secretRef: 'prompt-optimizer-proxy-secret'
            }
            {
              name: 'MCP_DEFAULT_MODEL_NAME'
              value: 'prompt-optimizer'
            }
            {
              name: 'PROMPT_OPTIMIZER_PROXY_SECRET_SOURCE'
              value: 'keyvault'
            }
          ]
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 2
      }
    }
  }
}

resource frontendApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: frontendAppName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${backendIdentityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: managedEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 80
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        {
          server: registryLoginServer
          identity: backendIdentityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'frontend'
          image: frontendImage
          env: [
            {
              name: 'BACKEND_URL'
              value: 'https://${backendApp.properties.configuration.ingress.fqdn}'
            }
          ]
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 2
      }
    }
  }
}

resource backendBootstrapJob 'Microsoft.App/jobs@2023-05-01' = {
  name: backendBootstrapJobName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${backendIdentityId}': {}
    }
  }
  properties: {
    environmentId: managedEnvironment.id
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 1800
      replicaRetryLimit: 0
      manualTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: [
        {
          server: registryLoginServer
          identity: backendIdentityId
        }
      ]
      secrets: [
        {
          name: 'database-url'
          #disable-next-line use-secure-value-for-secure-inputs
          value: 'postgresql+asyncpg://${postgresAdminLogin}:${postgresAdminPassword}@${postgresServerFqdn}:5432/${postgresDatabaseName}?ssl=require'
        }
        {
          name: 'secret-key'
          keyVaultUrl: '${keyVaultUri}secrets/jwt-secret-key'
          identity: backendIdentityId
        }
        {
          name: 'encryption-key'
          keyVaultUrl: '${keyVaultUri}secrets/encryption-key'
          identity: backendIdentityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'backend-bootstrap'
          image: backendImage
          command: [
            'python'
          ]
          args: [
            'scripts/bootstrap_app.py'
          ]
          env: [
            {
              name: 'DATABASE_URL'
              secretRef: 'database-url'
            }
            {
              name: 'DATABASE_AUTH_MODE'
              value: useAzureAdDatabaseAuth ? 'azure_ad' : 'password'
            }
            {
              name: 'DATABASE_HOST'
              value: postgresServerFqdn
            }
            {
              name: 'DATABASE_NAME'
              value: postgresDatabaseName
            }
            {
              name: 'DATABASE_USER'
              value: backendIdentityName
            }
            {
              name: 'DATABASE_AUTO_CREATE_TABLES'
              value: 'false'
            }
            {
              name: 'SECRET_KEY'
              secretRef: 'secret-key'
            }
            {
              name: 'ENCRYPTION_KEY'
              secretRef: 'encryption-key'
            }
            {
              name: 'DEBUG'
              value: 'false'
            }
            {
              name: 'STORAGE_BACKEND'
              value: 'azure_blob'
            }
            {
              name: 'AZURE_STORAGE_ACCOUNT_URL'
              value: storageAccountBlobEndpoint
            }
            {
              name: 'AZURE_STORAGE_CONTAINER_NAME'
              value: storageContainerName
            }
            {
              name: 'SECRET_STORE'
              value: azureServiceKeyStorage
            }
            {
              name: 'AZURE_KEY_VAULT_URL'
              value: keyVaultUri
            }
            {
              name: 'SEED_DATA_IGNORE'
              value: 'false'
            }
            {
              name: 'AZURE_CLIENT_ID'
              value: backendIdentityClientId
            }
            {
              name: 'VOICE_SCORING_TRANSCODE_ENABLED'
              value: 'true'
            }
            {
              name: 'VOICE_SCORING_TRANSCODE_TIMEOUT_SECONDS'
              value: '120'
            }
            {
              name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
              value: applicationInsightsConnectionString
            }
          ]
          resources: {
            cpu: json('1.0')
            memory: '2Gi'
          }
        }
      ]
    }
  }
}

output summary object = {
  module: 'container-apps'
  environmentName: environmentName
  managedEnvironmentName: managedEnvironment.name
  backendAppName: backendApp.name
  backendBootstrapJobName: backendBootstrapJob.name
  backendUrl: 'https://${backendApp.properties.configuration.ingress.fqdn}'
  promptOptimizerAppName: promptOptimizerApp.name
  promptOptimizerMcpUrl: 'https://${promptOptimizerApp.properties.configuration.ingress.fqdn}/mcp'
  promptOptimizerProxyBaseUrl: promptOptimizerProxyBaseUrl
  frontendAppName: frontendApp.name
  frontendUrl: 'https://${frontendApp.properties.configuration.ingress.fqdn}'
  registryLoginServer: registryLoginServer
  location: location
  networkProfile: networkProfile
}

output backendUrl string = 'https://${backendApp.properties.configuration.ingress.fqdn}'
output frontendUrl string = 'https://${frontendApp.properties.configuration.ingress.fqdn}'
output backendAppName string = backendApp.name
output backendBootstrapJobName string = backendBootstrapJob.name
output promptOptimizerAppName string = promptOptimizerApp.name
output promptOptimizerMcpUrl string = 'https://${promptOptimizerApp.properties.configuration.ingress.fqdn}/mcp'
output frontendAppName string = frontendApp.name
