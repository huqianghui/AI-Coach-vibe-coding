// Internal Container App for the prompt-optimizer sidecar + Key Vault secret reference.
//
// Deploys the open-source linshen/prompt-optimizer MCP service as a standalone
// Azure Container App with INTERNAL ingress only (no public FQDN — T-27-16). The
// backend reaches it over the managed-environment private DNS via
// PROMPT_OPTIMIZER_MCP_URL. The Azure OpenAI API key is never stored in plaintext;
// it is pulled from Key Vault through a user-assigned managed identity (T-27-17).
// The AGPL image is deployed unmodified as a separate service (T-27-18).
targetScope = 'resourceGroup'

@description('Short prefix used to name resources.')
param namePrefix string

@description('Environment discriminator (e.g. dev, prod).')
param environmentName string

param location string
param tags object

@description('Resource ID of the shared Container Apps managed environment.')
param managedEnvironmentId string

@description('Resource ID of the user-assigned managed identity used to read Key Vault secrets.')
param managedIdentityId string

@description('Base URI of the Key Vault holding the Azure OpenAI API key (e.g. https://kv.vault.azure.net/).')
param keyVaultUri string

@description('Name of the Key Vault secret that holds the Azure OpenAI API key.')
param azureOpenAiApiKeySecretName string = 'azure-openai-api-key'

@description('Azure OpenAI OpenAI-compatible base URL, e.g. https://<resource>.openai.azure.com/openai/v1.')
param azureOpenAiApiBaseUrl string

@description('Azure OpenAI deployment / model name the optimizer should call.')
param azureOpenAiModel string

@description('Container image for the prompt-optimizer sidecar (deployed unmodified).')
param image string = 'linshen/prompt-optimizer:2.11.7'

@description('Default UI/optimization language for the optimizer.')
@allowed([
  'zh'
  'en'
])
param defaultLanguage string = 'zh'

var appName = 'ca-${namePrefix}-${environmentName}-prompt-optimizer'
var targetPort = 80

resource promptOptimizerApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: appName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: managedEnvironmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        // Internal ingress only — the sidecar is never exposed publicly (T-27-16).
        external: false
        targetPort: targetPort
        transport: 'auto'
        allowInsecure: false
      }
      secrets: [
        {
          // Azure OpenAI API key sourced from Key Vault via managed identity (T-27-17).
          name: 'azure-openai-api-key'
          keyVaultUrl: '${keyVaultUri}secrets/${azureOpenAiApiKeySecretName}'
          identity: managedIdentityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'prompt-optimizer'
          image: image
          env: [
            {
              name: 'MCP_DEFAULT_MODEL_PROVIDER'
              value: 'custom'
            }
            {
              name: 'MCP_DEFAULT_LANGUAGE'
              value: defaultLanguage
            }
            {
              name: 'VITE_CUSTOM_API_BASE_URL'
              value: azureOpenAiApiBaseUrl
            }
            {
              name: 'VITE_CUSTOM_API_KEY'
              secretRef: 'azure-openai-api-key'
            }
            {
              name: 'VITE_CUSTOM_API_MODEL'
              value: azureOpenAiModel
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

@description('Internal FQDN of the prompt-optimizer Container App (reachable only inside the environment).')
output internalFqdn string = promptOptimizerApp.properties.configuration.ingress.fqdn

@description('Value to set as PROMPT_OPTIMIZER_MCP_URL on the backend.')
output mcpUrl string = 'http://${promptOptimizerApp.properties.configuration.ingress.fqdn}/mcp'
