// Internal Container App for the prompt-optimizer sidecar + backend proxy secret.
//
// Deploys the open-source linshen/prompt-optimizer MCP service as a standalone
// Azure Container App with INTERNAL ingress only (no public FQDN — T-27-16). The
// backend reaches it over the managed-environment private DNS via
// PROMPT_OPTIMIZER_MCP_URL. The optimizer does not receive Azure credentials; it
// calls the backend internal OpenAI-compatible proxy with a shared internal secret.
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

@description('Resource ID of the user-assigned managed identity assigned to the Container App.')
param managedIdentityId string

@description('Backend internal OpenAI-compatible proxy base URL, e.g. https://backend/api/v1/internal/openai/v1.')
param backendProxyBaseUrl string

@secure()
@description('Internal shared secret accepted by the backend prompt optimizer proxy.')
param promptOptimizerProxySecret string

@description('Container image for the prompt-optimizer sidecar (deployed unmodified).')
param image string = 'linshen/prompt-optimizer:2.11.7'

@description('Default UI/optimization language for the optimizer.')
@allowed([
  'zh'
  'en'
])
param defaultLanguage string = 'zh'

var appName = 'ca-${namePrefix}-${environmentName}-po'
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
          name: 'prompt-optimizer-proxy-secret'
          value: promptOptimizerProxySecret
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
              value: backendProxyBaseUrl
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
              value: backendProxyBaseUrl
            }
            {
              name: 'MCP_DEFAULT_MODEL_API_KEY'
              secretRef: 'prompt-optimizer-proxy-secret'
            }
            {
              name: 'MCP_DEFAULT_MODEL_NAME'
              value: 'prompt-optimizer'
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
output mcpUrl string = 'https://${promptOptimizerApp.properties.configuration.ingress.fqdn}/mcp'
