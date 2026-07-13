targetScope = 'resourceGroup'

@minLength(3)
param namePrefix string
param environmentName string
param location string
param tags object

@secure()
param jwtSecret string

@secure()
param encryptionKey string

@secure()
param postgresAdminPassword string

@secure()
param promptOptimizerProxySecret string

param manageBootstrapSecrets bool = true
param manageJwtSecret bool = true
param manageEncryptionKey bool = true
param managePostgresPasswordSecret bool = true
param managePromptOptimizerProxySecret bool = true

@allowed([
  'publicDemo'
  'privateBackend'
])
param networkProfile string = 'publicDemo'

var vaultName = take(toLower('${namePrefix}-${environmentName}-${uniqueString(resourceGroup().id, location)}'), 24)
var usePrivateBackend = networkProfile == 'privateBackend'

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: vaultName
  location: location
  tags: tags
  properties: {
    tenantId: tenant().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enabledForDeployment: false
    enabledForDiskEncryption: false
    enabledForTemplateDeployment: true
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    publicNetworkAccess: usePrivateBackend ? 'Disabled' : 'Enabled'
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: usePrivateBackend ? 'Deny' : 'Allow'
    }
  }
}

resource jwtSecretResource 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (manageJwtSecret) {
  parent: vault
  name: 'jwt-secret-key'
  properties: {
    value: jwtSecret
  }
}

resource encryptionKeyResource 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (manageEncryptionKey) {
  parent: vault
  name: 'encryption-key'
  properties: {
    value: encryptionKey
  }
}

resource postgresPasswordSecretResource 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (managePostgresPasswordSecret) {
  parent: vault
  name: 'postgres-admin-password'
  properties: {
    value: postgresAdminPassword
  }
}

resource promptOptimizerProxySecretResource 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (managePromptOptimizerProxySecret) {
  parent: vault
  name: 'prompt-optimizer-proxy-secret'
  properties: {
    value: promptOptimizerProxySecret
  }
}

output summary object = {
  module: 'key-vault'
  vaultName: vault.name
  vaultUri: vault.properties.vaultUri
  vaultId: vault.id
  secretNames: [
    'jwt-secret-key'
    'encryption-key'
    'postgres-admin-password'
    'prompt-optimizer-proxy-secret'
  ]
  manageBootstrapSecrets: manageBootstrapSecrets
  managedSecrets: {
    jwtSecret: manageJwtSecret
    encryptionKey: manageEncryptionKey
    postgresAdminPassword: managePostgresPasswordSecret
    promptOptimizerProxySecret: managePromptOptimizerProxySecret
  }
  environmentName: environmentName
  location: location
}
