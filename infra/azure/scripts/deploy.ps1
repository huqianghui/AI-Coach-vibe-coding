[CmdletBinding()]
param(
    [string]$Location = "swedencentral",
    [string]$FoundryLocation = "",
    [string]$EnvironmentName = "public",
    [string]$NamePrefix = "aicoach",
    [string]$ResourceGroupName = "",
    [ValidateSet("foundryOnly", "fullLegacy")]
    [string]$DeploymentMode = "foundryOnly",
    [ValidateSet("publicDemo", "privateBackend")]
    [string]$NetworkProfile = "publicDemo",
    [string]$VnetName = "",
    [string]$VnetAddressPrefix = "10.60.0.0/16",
    [string]$ContainerAppsSubnetPrefix = "10.60.0.0/23",
    [string]$PrivateEndpointsSubnetPrefix = "10.60.2.0/24",
    [ValidateSet("none", "azureAiSearch")]
    [string]$KnowledgeBaseMode = "none",
    [string]$GithubOwner = "huqianghui",
    [string]$GithubRepo = "AI-Coach-vibe-coding",
    [string]$GithubBranch = "main",
    [string]$ChatDeploymentName = "gpt-4o",
    [ValidateSet("Standard", "GlobalStandard", "DataZoneStandard")]
    [string]$ChatDeploymentSkuName = "Standard",
    [int]$ChatDeploymentCapacity = 120,
    [ValidateSet("password", "azureAd")]
    [string]$BackendDatabaseAuthMode = "azureAd",
    [ValidateSet("database", "keyvault")]
    [string]$AzureServiceKeyStorage = "keyvault",
    [string]$PostgresEntraAdminLogin = "",
    [string]$PostgresEntraAdminObjectId = "",
    [ValidateSet("User", "Group", "ServicePrincipal")]
    [string]$PostgresEntraAdminPrincipalType = "User",
    [System.Security.SecureString]$PostgresAdminPassword,
    [System.Security.SecureString]$JwtSecret,
    [System.Security.SecureString]$EncryptionKey,
    [switch]$WhatIf,
    [switch]$DeployApp,
    [switch]$Verify,
    [switch]$SkipImageBuild,
    [switch]$SkipDbBootstrap,
    [switch]$SkipAppBootstrap,
    [switch]$SkipSampleData,
    [switch]$EnableDatabaseAutoCreateTables,
    [string]$PostgresBootstrapClientIp = "",
    [switch]$KeepPostgresBootstrapFirewallRule,
    [switch]$KeepGeneratedParameters
)

$ErrorActionPreference = "Stop"

function Convert-SecureStringToPlainText {
    param([System.Security.SecureString]$Value)

    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

function New-RandomSecret {
    param([int]$ByteCount = 48)

    $bytes = [byte[]]::new($ByteCount)
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    return [Convert]::ToBase64String($bytes)
}

function New-FernetKey {
    $bytes = [byte[]]::new(32)
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    return [Convert]::ToBase64String($bytes).Replace("+", "-").Replace("/", "_")
}

function Test-KeyVaultSecretExists {
    param(
        [Parameter(Mandatory = $false)][AllowEmptyString()][string]$VaultResourceId,
        [Parameter(Mandatory = $true)][string]$SecretName
    )

    if ([string]::IsNullOrWhiteSpace($VaultResourceId)) {
        return $false
    }

    az resource show `
        --ids "$VaultResourceId/secrets/$SecretName" `
        --api-version 2023-07-01 `
        --query "id" `
        --output tsv 1>$null 2>$null

    return $LASTEXITCODE -eq 0
}

function Get-ContainerAppImage {
    param(
        [Parameter(Mandatory = $true)][string]$ResourceGroupName,
        [Parameter(Mandatory = $true)][string]$ContainerAppName,
        [Parameter(Mandatory = $true)][string]$DefaultImage
    )

    $image = az containerapp show `
        --resource-group $ResourceGroupName `
        --name $ContainerAppName `
        --query "properties.template.containers[0].image" `
        --output tsv 2>$null

    if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($image)) {
        return $image
    }

    return $DefaultImage
}

function Invoke-WithTemporaryEnvironment {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Variables,
        [Parameter(Mandatory = $true)][scriptblock]$ScriptBlock
    )

    $previousValues = @{}
    foreach ($key in $Variables.Keys) {
        $previousValues[$key] = [Environment]::GetEnvironmentVariable($key, "Process")
        [Environment]::SetEnvironmentVariable($key, [string]$Variables[$key], "Process")
    }

    try {
        & $ScriptBlock
    }
    finally {
        foreach ($key in $Variables.Keys) {
            [Environment]::SetEnvironmentVariable($key, $previousValues[$key], "Process")
        }
    }

}

function Wait-SubscriptionDeployment {
    param(
        [Parameter(Mandatory = $true)][string]$DeploymentName,
        [int]$TimeoutSeconds = 3600,
        [int]$PollSeconds = 10
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $state = az deployment sub show `
            --name $DeploymentName `
            --query "properties.provisioningState" `
            --output tsv 2>$null

        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($state)) {
            Write-Host "Deployment state: $state"
            if ($state -eq "Succeeded") {
                return
            }
            if ($state -in @("Failed", "Canceled")) {
                throw "Azure infrastructure deployment ended with state '$state'."
            }
        }

        Start-Sleep -Seconds $PollSeconds
    }

    throw "Timed out waiting for Azure infrastructure deployment '$DeploymentName'."
}

function Invoke-ContainerAppBootstrapJob {
    param(
        [Parameter(Mandatory = $true)][string]$ResourceGroupName,
        [Parameter(Mandatory = $true)][string]$JobName,
        [switch]$SkipSampleData
    )

    $startArgs = @(
        "containerapp", "job", "start",
        "--name", $JobName,
        "--resource-group", $ResourceGroupName,
        "--output", "json"
    )
    if ($SkipSampleData) {
        $startArgs += @("--args", "scripts/bootstrap_app.py", "--skip-seed")
    }

    $executionJson = az @startArgs
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($executionJson)) {
        throw "Could not start backend bootstrap Container Apps Job."
    }

    $execution = $executionJson | ConvertFrom-Json
    $executionName = $execution.name
    if ([string]::IsNullOrWhiteSpace($executionName)) {
        throw "Backend bootstrap Container Apps Job did not return an execution name."
    }

    Write-Host "Started backend bootstrap job execution: $executionName" -ForegroundColor Cyan
    for ($attempt = 1; $attempt -le 90; $attempt++) {
        Start-Sleep -Seconds 10
        $statusJson = az containerapp job execution show `
            --name $JobName `
            --resource-group $ResourceGroupName `
            --job-execution-name $executionName `
            --output json
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($statusJson)) {
            throw "Could not read backend bootstrap job execution status."
        }

        $statusObject = $statusJson | ConvertFrom-Json
        $status = $statusObject.properties.status
        if ([string]::IsNullOrWhiteSpace($status)) {
            $status = $statusObject.status
        }

        Write-Host "Backend bootstrap job status: $status"
        if ($status -in @("Succeeded", "Completed")) {
            Write-Host "Backend bootstrap job completed." -ForegroundColor Green
            return
        }
        if ($status -in @("Failed", "Canceled", "Cancelled")) {
            throw "Backend bootstrap job failed with status '$status'. Check Container Apps Job logs for execution '$executionName'."
        }
    }

    throw "Backend bootstrap job did not complete within 15 minutes."
}

function Get-PostgresEntraAccessToken {
    $token = az account get-access-token `
        --resource "https://ossrdbms-aad.database.windows.net" `
        --query "accessToken" `
        --output tsv

    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($token)) {
        throw "Could not get a PostgreSQL Entra access token from Azure CLI."
    }

    return $token
}

function Get-PostgresServerNameFromFqdn {
    param([Parameter(Mandatory = $true)][string]$PostgresHost)

    return ($PostgresHost -split "\.")[0]
}

function Get-CurrentPublicIp {
    if (-not [string]::IsNullOrWhiteSpace($PostgresBootstrapClientIp)) {
        return $PostgresBootstrapClientIp.Trim()
    }

    $ip = Invoke-RestMethod -Uri "https://api.ipify.org" -TimeoutSec 15
    if ([string]::IsNullOrWhiteSpace($ip)) {
        throw "Could not determine current public IP for PostgreSQL bootstrap firewall rule. Pass -PostgresBootstrapClientIp explicitly."
    }

    return ([string]$ip).Trim()
}

function New-PostgresBootstrapFirewallRule {
    param(
        [Parameter(Mandatory = $true)][string]$ResourceGroupName,
        [Parameter(Mandatory = $true)][string]$PostgresHost
    )

    $serverName = Get-PostgresServerNameFromFqdn -PostgresHost $PostgresHost
    $clientIp = Get-CurrentPublicIp
    $ruleName = "AllowBootstrapClient-$(Get-Date -Format yyyyMMddHHmmss)"

    Write-Host "Temporarily allowing PostgreSQL bootstrap client IP $clientIp..." -ForegroundColor Cyan
    az postgres flexible-server firewall-rule create `
        --resource-group $ResourceGroupName `
        --server-name $serverName `
        --name $ruleName `
        --start-ip-address $clientIp `
        --end-ip-address $clientIp `
        --output none
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create PostgreSQL bootstrap firewall rule '$ruleName'."
    }

    return @{
        ResourceGroupName = $ResourceGroupName
        ServerName = $serverName
        RuleName = $ruleName
        ClientIp = $clientIp
    }
}

function Remove-PostgresBootstrapFirewallRule {
    param([Parameter(Mandatory = $true)][hashtable]$Rule)

    Write-Host "Removing temporary PostgreSQL bootstrap firewall rule '$($Rule.RuleName)'..." -ForegroundColor Cyan
    az postgres flexible-server firewall-rule delete `
        --resource-group $Rule.ResourceGroupName `
        --server-name $Rule.ServerName `
        --name $Rule.RuleName `
        --yes `
        --output none
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Could not remove temporary PostgreSQL bootstrap firewall rule '$($Rule.RuleName)'. Remove it manually after deployment."
    }
}

function Invoke-PostgresEntraBootstrapJob {
    param(
        [Parameter(Mandatory = $true)][string]$ResourceGroupName,
        [Parameter(Mandatory = $true)][string]$JobName,
        [Parameter(Mandatory = $true)][string]$PostgresHost,
        [Parameter(Mandatory = $true)][string]$PostgresDatabase,
        [Parameter(Mandatory = $true)][string]$AdminUser,
        [Parameter(Mandatory = $true)][string]$AdminToken,
        [Parameter(Mandatory = $true)][string]$BackendUser,
        [Parameter(Mandatory = $true)][string]$BackendObjectId
    )

    $jobImage = az containerapp job show `
        --name $JobName `
        --resource-group $ResourceGroupName `
        --query "properties.template.containers[0].image" `
        --output tsv
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($jobImage)) {
        throw "Could not resolve backend bootstrap Container Apps Job image."
    }

    $executionJson = az containerapp job start `
        --name $JobName `
        --resource-group $ResourceGroupName `
        --container-name "backend-bootstrap" `
        --image $jobImage `
        --command "python" `
        --args "scripts/bootstrap_postgres_entra.py" `
        --env-vars `
            "DATABASE_HOST=$PostgresHost" `
            "DATABASE_NAME=$PostgresDatabase" `
            "POSTGRES_ENTRA_ADMIN_USER=$AdminUser" `
            "POSTGRES_ENTRA_ADMIN_TOKEN=$AdminToken" `
            "DATABASE_USER=$BackendUser" `
            "DATABASE_USER_OBJECT_ID=$BackendObjectId" `
            "DATABASE_USER_OBJECT_TYPE=service" `
        --output json
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($executionJson)) {
        throw "Could not start PostgreSQL Entra bootstrap Container Apps Job."
    }

    $execution = $executionJson | ConvertFrom-Json
    $executionName = $execution.name
    if ([string]::IsNullOrWhiteSpace($executionName)) {
        throw "PostgreSQL Entra bootstrap Container Apps Job did not return an execution name."
    }

    Write-Host "Started PostgreSQL Entra bootstrap job execution: $executionName" -ForegroundColor Cyan
    for ($attempt = 1; $attempt -le 90; $attempt++) {
        Start-Sleep -Seconds 10
        $statusJson = az containerapp job execution show `
            --name $JobName `
            --resource-group $ResourceGroupName `
            --job-execution-name $executionName `
            --output json
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($statusJson)) {
            throw "Could not read PostgreSQL Entra bootstrap job execution status."
        }

        $statusObject = $statusJson | ConvertFrom-Json
        $status = $statusObject.properties.status
        if ([string]::IsNullOrWhiteSpace($status)) {
            $status = $statusObject.status
        }

        Write-Host "PostgreSQL Entra bootstrap job status: $status"
        if ($status -in @("Succeeded", "Completed")) {
            Write-Host "PostgreSQL Entra bootstrap job completed." -ForegroundColor Green
            return
        }
        if ($status -in @("Failed", "Canceled", "Cancelled")) {
            throw "PostgreSQL Entra bootstrap job failed with status '$status'. Check Container Apps Job logs for execution '$executionName'."
        }
    }

    throw "PostgreSQL Entra bootstrap job did not complete within 15 minutes."
}

function Format-AdminConfigValue {
    param([AllowNull()][object]$Value)

    if ($null -eq $Value) {
        return "(not available)"
    }

    $text = [string]$Value
    if ([string]::IsNullOrWhiteSpace($text)) {
        return "(not available)"
    }

    return $text
}

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$AzureRoot = Split-Path -Parent $ScriptRoot
$RepoRoot = Split-Path -Parent (Split-Path -Parent $AzureRoot)
$TemplateFile = Join-Path $AzureRoot "main.bicep"
$LocalDir = Join-Path $AzureRoot ".local"
New-Item -ItemType Directory -Force -Path $LocalDir | Out-Null

Write-Host "Checking Azure CLI login..." -ForegroundColor Cyan
$account = az account show --output json | ConvertFrom-Json
$subscriptionId = $account.id
$subscriptionSuffix = (($subscriptionId -replace "-", "").Substring(0, 6)).ToLowerInvariant()
$regionToken = ($Location -replace "[^a-zA-Z0-9]", "").ToLowerInvariant()
$effectiveFoundryLocation = if ([string]::IsNullOrWhiteSpace($FoundryLocation)) {
    $Location
}
else {
    $FoundryLocation.Trim()
}

if ($BackendDatabaseAuthMode -eq "azureAd" -and (
        [string]::IsNullOrWhiteSpace($PostgresEntraAdminLogin) -or
        [string]::IsNullOrWhiteSpace($PostgresEntraAdminObjectId)
    )) {
    Write-Host "Resolving PostgreSQL Entra admin from current Azure CLI user..." -ForegroundColor Cyan
    $signedInUserJson = az ad signed-in-user show --output json
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($signedInUserJson)) {
        throw "BackendDatabaseAuthMode=azureAd requires PostgreSQL Entra admin details. Pass -PostgresEntraAdminLogin and -PostgresEntraAdminObjectId, or sign in with a user account that az ad signed-in-user can resolve."
    }
    $signedInUser = $signedInUserJson | ConvertFrom-Json
    if ([string]::IsNullOrWhiteSpace($PostgresEntraAdminLogin)) {
        $PostgresEntraAdminLogin = $signedInUser.userPrincipalName
    }
    if ([string]::IsNullOrWhiteSpace($PostgresEntraAdminObjectId)) {
        $PostgresEntraAdminObjectId = $signedInUser.id
    }
    if ([string]::IsNullOrWhiteSpace($PostgresEntraAdminLogin) -or
        [string]::IsNullOrWhiteSpace($PostgresEntraAdminObjectId)) {
        throw "Could not resolve PostgreSQL Entra admin login/object ID from current Azure CLI user. Pass -PostgresEntraAdminLogin and -PostgresEntraAdminObjectId explicitly."
    }
}

$defaultAcrName = "$($NamePrefix)$($EnvironmentName)$($subscriptionSuffix)$($regionToken)acr".ToLowerInvariant()
if ($defaultAcrName.Length -gt 50) {
    $defaultAcrName = $defaultAcrName.Substring(0, 50)
}

$storageToken = "$($NamePrefix)$($EnvironmentName)$($subscriptionSuffix)$($regionToken)".ToLowerInvariant()
if ($storageToken.Length -gt 22) {
    $storageToken = $storageToken.Substring(0, 22)
}
$defaultStorageName = "${storageToken}st"
$defaultResourceGroupName = "rg-$NamePrefix-$EnvironmentName-$regionToken"
$resourceGroupName = if ([string]::IsNullOrWhiteSpace($ResourceGroupName)) {
    $defaultResourceGroupName
}
else {
    $ResourceGroupName.Trim()
}
$backendContainerAppName = "ca-$NamePrefix-$EnvironmentName-backend"
$frontendContainerAppName = "ca-$NamePrefix-$EnvironmentName-frontend"
$defaultBackendImage = "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest"
$defaultFrontendImage = "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest"

Write-Host "Resolving deployment secrets..." -ForegroundColor Cyan
$resourceGroupExists = az group exists --name $resourceGroupName --output tsv
if ($LASTEXITCODE -ne 0) {
    throw "Failed to check whether resource group '$resourceGroupName' exists."
}

$keyVaultName = ""
$keyVaultResourceId = ""
$postgresServerName = ""
if ($resourceGroupExists -eq "true") {
    $keyVault = az resource list `
        --resource-group $resourceGroupName `
        --resource-type "Microsoft.KeyVault/vaults" `
        --query "[0].{name:name,id:id}" `
        --output json | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to list Key Vault resources in '$resourceGroupName'."
    }
    if ($keyVault) {
        $keyVaultName = $keyVault.name
        $keyVaultResourceId = $keyVault.id
    }

    $postgresServerName = az resource list `
        --resource-group $resourceGroupName `
        --resource-type "Microsoft.DBforPostgreSQL/flexibleServers" `
        --query "[0].name" `
        --output tsv
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to list PostgreSQL Flexible Server resources in '$resourceGroupName'."
    }
}
$managePostgresAdminPassword = [string]::IsNullOrWhiteSpace($postgresServerName) -or $null -ne $PostgresAdminPassword
$jwtSecretExists = Test-KeyVaultSecretExists -VaultResourceId $keyVaultResourceId -SecretName "jwt-secret-key"
$encryptionKeyExists = Test-KeyVaultSecretExists -VaultResourceId $keyVaultResourceId -SecretName "encryption-key"
$postgresPasswordSecretExists = Test-KeyVaultSecretExists -VaultResourceId $keyVaultResourceId -SecretName "postgres-admin-password"
$manageJwtSecret = $null -ne $JwtSecret -or -not $jwtSecretExists
$manageEncryptionKey = $null -ne $EncryptionKey -or -not $encryptionKeyExists
$managePostgresPasswordSecret = $null -ne $PostgresAdminPassword -or -not $postgresPasswordSecretExists
$manageBootstrapSecrets = $manageJwtSecret -or $manageEncryptionKey -or $managePostgresPasswordSecret

if ($keyVaultName) {
    Write-Host "Existing Key Vault '$keyVaultName' found. Existing secrets will not be overwritten unless explicitly supplied or missing." -ForegroundColor Cyan

    if ($BackendDatabaseAuthMode -eq "password") {
        if ($PostgresAdminPassword) {
            $postgresAdminPasswordValue = Convert-SecureStringToPlainText $PostgresAdminPassword
        }
        elseif ($managePostgresAdminPassword -or $managePostgresPasswordSecret) {
            $postgresAdminPasswordValue = Convert-SecureStringToPlainText (Read-Host "PostgreSQL admin password" -AsSecureString)
        }
        else {
            $postgresAdminPasswordValue = Convert-SecureStringToPlainText (Read-Host "Existing PostgreSQL admin password for DATABASE_URL" -AsSecureString)
        }
    }
    else {
        $postgresAdminPasswordValue = if ($PostgresAdminPassword) {
            Convert-SecureStringToPlainText $PostgresAdminPassword
        }
        else {
            New-RandomSecret
        }
    }
    $jwtSecretValue = if ($JwtSecret) {
        Convert-SecureStringToPlainText $JwtSecret
    }
    elseif ($manageJwtSecret) {
        New-RandomSecret
    }
    else {
        "existing-jwt-secret-not-managed"
    }
    $encryptionKeyValue = if ($EncryptionKey) {
        Convert-SecureStringToPlainText $EncryptionKey
    }
    elseif ($manageEncryptionKey) {
        New-FernetKey
    }
    else {
        "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    }
}
else {
    Write-Host "No existing Key Vault found. Generating first-deployment secrets locally..." -ForegroundColor Cyan
    $manageJwtSecret = $true
    $manageEncryptionKey = $true
    $managePostgresPasswordSecret = $true
    $manageBootstrapSecrets = $true
    if ($BackendDatabaseAuthMode -eq "password") {
        $postgresAdminPasswordValue = if ($PostgresAdminPassword) {
            Convert-SecureStringToPlainText $PostgresAdminPassword
        }
        else {
            Convert-SecureStringToPlainText (Read-Host "PostgreSQL admin password" -AsSecureString)
        }
    }
    else {
        $postgresAdminPasswordValue = if ($PostgresAdminPassword) {
            Convert-SecureStringToPlainText $PostgresAdminPassword
        }
        else {
            New-RandomSecret
        }
    }
    $jwtSecretValue = if ($JwtSecret) { Convert-SecureStringToPlainText $JwtSecret } else { New-RandomSecret }
    $encryptionKeyValue = if ($EncryptionKey) { Convert-SecureStringToPlainText $EncryptionKey } else { New-FernetKey }
}

$backendImage = $defaultBackendImage
$frontendImage = $defaultFrontendImage
if ($resourceGroupExists -eq "true") {
    Write-Host "Reusing existing Container App images when present..." -ForegroundColor Cyan
    $backendImage = Get-ContainerAppImage -ResourceGroupName $resourceGroupName -ContainerAppName $backendContainerAppName -DefaultImage $defaultBackendImage
    $frontendImage = Get-ContainerAppImage -ResourceGroupName $resourceGroupName -ContainerAppName $frontendContainerAppName -DefaultImage $defaultFrontendImage
}

$parametersPath = Join-Path $LocalDir "main.parameters.generated.json"
$parameters = [ordered]@{
    "`$schema" = "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#"
    contentVersion = "1.0.0.0"
    parameters = [ordered]@{
        namePrefix = @{ value = $NamePrefix }
        environmentName = @{ value = $EnvironmentName }
        location = @{ value = $Location }
        foundryLocation = @{ value = $effectiveFoundryLocation }
        resourceGroupName = @{ value = $resourceGroupName }
        deploymentMode = @{ value = $DeploymentMode }
        networkProfile = @{ value = $NetworkProfile }
        vnetName = @{ value = $VnetName }
        vnetAddressPrefix = @{ value = $VnetAddressPrefix }
        containerAppsSubnetPrefix = @{ value = $ContainerAppsSubnetPrefix }
        privateEndpointsSubnetPrefix = @{ value = $PrivateEndpointsSubnetPrefix }
        knowledgeBaseMode = @{ value = $KnowledgeBaseMode }
        containerRegistryName = @{ value = $defaultAcrName }
        storageAccountName = @{ value = $defaultStorageName }
        backendImage = @{ value = $backendImage }
        frontendImage = @{ value = $frontendImage }
        postgresAdminPassword = @{ value = $postgresAdminPasswordValue }
        jwtSecret = @{ value = $jwtSecretValue }
        encryptionKey = @{ value = $encryptionKeyValue }
        manageBootstrapSecrets = @{ value = $manageBootstrapSecrets }
        manageJwtSecret = @{ value = $manageJwtSecret }
        manageEncryptionKey = @{ value = $manageEncryptionKey }
        managePostgresPasswordSecret = @{ value = $managePostgresPasswordSecret }
        managePostgresAdminPassword = @{ value = $managePostgresAdminPassword }
        databaseAutoCreateTables = @{ value = [bool]$EnableDatabaseAutoCreateTables }
        backendDatabaseAuthMode = @{ value = $BackendDatabaseAuthMode }
        azureServiceKeyStorage = @{ value = $AzureServiceKeyStorage }
        postgresEntraAdminLogin = @{ value = $PostgresEntraAdminLogin }
        postgresEntraAdminObjectId = @{ value = $PostgresEntraAdminObjectId }
        postgresEntraAdminPrincipalType = @{ value = $PostgresEntraAdminPrincipalType }
        githubOwner = @{ value = $GithubOwner }
        githubRepo = @{ value = $GithubRepo }
        githubBranch = @{ value = $GithubBranch }
        githubEnvironmentName = @{ value = $EnvironmentName }
        chatDeploymentName = @{ value = $ChatDeploymentName }
        chatDeploymentSkuName = @{ value = $ChatDeploymentSkuName }
        chatDeploymentCapacity = @{ value = $ChatDeploymentCapacity }
    }
}
$parameters | ConvertTo-Json -Depth 20 | Set-Content -Path $parametersPath -Encoding utf8NoBOM

Write-Host "Validating Bicep..." -ForegroundColor Cyan
az bicep build --file $TemplateFile | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Bicep build failed."
}

$deploymentName = "deploy-$NamePrefix-$EnvironmentName-$(Get-Date -Format yyyyMMddHHmmss)"
if ($WhatIf) {
    Write-Host "Running subscription what-if..." -ForegroundColor Cyan
    az deployment sub what-if `
        --name $deploymentName `
        --location $Location `
        --template-file $TemplateFile `
        --parameters "@$parametersPath" | Out-Host
    if ($LASTEXITCODE -ne 0) {
        if (-not $KeepGeneratedParameters) {
            Remove-Item -Path $parametersPath -Force
        }
        throw "Azure what-if failed."
    }
    if (-not $KeepGeneratedParameters) {
        Remove-Item -Path $parametersPath -Force
    }
    exit 0
}

Write-Host "Deploying Azure infrastructure..." -ForegroundColor Cyan
az deployment sub create `
    --name $deploymentName `
    --location $Location `
    --template-file $TemplateFile `
    --parameters "@$parametersPath" `
    --no-wait `
    --output none
if ($LASTEXITCODE -ne 0) {
    if (-not $KeepGeneratedParameters) {
        Remove-Item -Path $parametersPath -Force
    }
    throw "Azure infrastructure deployment failed."
}

Wait-SubscriptionDeployment -DeploymentName $deploymentName

$outputsJson = az deployment sub show `
    --name $deploymentName `
    --query "properties.outputs" `
    --output json
if ($LASTEXITCODE -ne 0) {
    if (-not $KeepGeneratedParameters) {
        Remove-Item -Path $parametersPath -Force
    }
    throw "Failed to read Azure infrastructure deployment outputs."
}

$outputs = $outputsJson | ConvertFrom-Json
$outputPath = Join-Path $LocalDir "deployment.outputs.json"
$outputs | ConvertTo-Json -Depth 20 | Set-Content -Path $outputPath -Encoding utf8NoBOM

Write-Host "Infrastructure deployment complete." -ForegroundColor Green
Write-Host "Frontend URL: $($outputs.frontendUrl.value)"
Write-Host "Backend URL:  $($outputs.backendUrl.value)"
Write-Host "ACR:          $($outputs.containerRegistryLoginServer.value)"

if ($DeployApp -and -not $SkipImageBuild) {
    & (Join-Path $ScriptRoot "build-and-push.ps1") `
        -ResourceGroupName $outputs.resourceGroupName.value `
        -ContainerRegistryName $outputs.containerRegistryName.value `
        -BackendContainerAppName $outputs.backendContainerAppName.value `
        -FrontendContainerAppName $outputs.frontendContainerAppName.value `
        -BackendUrl $outputs.backendUrl.value `
        -BackendBootstrapJobName $outputs.backendBootstrapJobName.value
}
elseif (-not $DeployApp) {
    Write-Host "Skipping app image build/update. Pass -DeployApp to build and update Container Apps." -ForegroundColor Yellow
}
else {
    Write-Host "Skipping app image build/update because -SkipImageBuild was specified." -ForegroundColor Yellow
}

if ($BackendDatabaseAuthMode -eq "azureAd" -and -not $SkipDbBootstrap) {
    Write-Host "Bootstrapping PostgreSQL Entra role for backend Managed Identity..." -ForegroundColor Cyan
    if ($NetworkProfile -eq "privateBackend") {
        if ((-not $DeployApp -or $SkipImageBuild) -and $backendImage -eq $defaultBackendImage) {
            throw "privateBackend PostgreSQL Entra bootstrap runs inside the backend Container Apps Job and requires a real backend image. Pass -DeployApp to build one, or pass -SkipDbBootstrap for an infra-only run."
        }

        $adminToken = Get-PostgresEntraAccessToken
        Invoke-PostgresEntraBootstrapJob `
            -ResourceGroupName $outputs.resourceGroupName.value `
            -JobName $outputs.backendBootstrapJobName.value `
            -PostgresHost $outputs.postgresServerFqdn.value `
            -PostgresDatabase $outputs.postgresDatabaseName.value `
            -AdminUser $PostgresEntraAdminLogin `
            -AdminToken $adminToken `
            -BackendUser $outputs.backendIdentityName.value `
            -BackendObjectId $outputs.backendIdentityPrincipalId.value
    }
    else {
        $bootstrapScript = Join-Path $RepoRoot "backend\scripts\bootstrap_postgres_entra.py"
        $bootstrapArgs = @(
            $bootstrapScript,
            "--host", $outputs.postgresServerFqdn.value,
            "--database", $outputs.postgresDatabaseName.value,
            "--admin-user", $PostgresEntraAdminLogin,
            "--backend-user", $outputs.backendIdentityName.value,
            "--backend-object-id", $outputs.backendIdentityPrincipalId.value,
            "--backend-object-type", "service"
        )
        $bootstrapFirewallRule = New-PostgresBootstrapFirewallRule `
            -ResourceGroupName $outputs.resourceGroupName.value `
            -PostgresHost $outputs.postgresServerFqdn.value
        Push-Location (Join-Path $RepoRoot "backend")
        try {
            python @bootstrapArgs
            if ($LASTEXITCODE -ne 0) {
                throw "PostgreSQL Entra bootstrap failed."
            }
        }
        finally {
            Pop-Location
            if ($KeepPostgresBootstrapFirewallRule) {
                Write-Host "Keeping temporary PostgreSQL bootstrap firewall rule '$($bootstrapFirewallRule.RuleName)' for troubleshooting." -ForegroundColor Yellow
            }
            else {
                Remove-PostgresBootstrapFirewallRule -Rule $bootstrapFirewallRule
            }
        }
    }
}
elseif ($BackendDatabaseAuthMode -eq "azureAd") {
    Write-Host "Skipping PostgreSQL Entra DB bootstrap because -SkipDbBootstrap was specified." -ForegroundColor Yellow
}

if ($DeployApp -and -not $SkipAppBootstrap) {
    Write-Host "Running application database migrations and sample data bootstrap in backend Container Apps Job..." -ForegroundColor Cyan
    Invoke-ContainerAppBootstrapJob `
        -ResourceGroupName $outputs.resourceGroupName.value `
        -JobName $outputs.backendBootstrapJobName.value `
        -SkipSampleData:$SkipSampleData
}
elseif ($DeployApp) {
    Write-Host "Skipping application DB/schema/sample bootstrap because -SkipAppBootstrap was specified." -ForegroundColor Yellow
}

if ($Verify) {
    & (Join-Path $ScriptRoot "verify-deployment.ps1") `
        -BackendUrl $outputs.backendUrl.value `
        -FrontendUrl $outputs.frontendUrl.value
}
else {
    Write-Host "Skipping health verification. Pass -Verify to check existing app endpoints." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "GitHub OIDC values:" -ForegroundColor Cyan
Write-Host "AZURE_CLIENT_ID=$($outputs.githubDeploymentClientId.value)"
Write-Host "AZURE_TENANT_ID=$($outputs.tenantId.value)"
Write-Host "AZURE_SUBSCRIPTION_ID=$subscriptionId"
Write-Host "AZURE_RESOURCE_GROUP=$($outputs.resourceGroupName.value)"
Write-Host "ACR_NAME=$($outputs.containerRegistryName.value)"
Write-Host "BACKEND_APP_NAME=$($outputs.backendContainerAppName.value)"
Write-Host "BACKEND_BOOTSTRAP_JOB_NAME=$($outputs.backendBootstrapJobName.value)"
Write-Host "FRONTEND_APP_NAME=$($outputs.frontendContainerAppName.value)"

$deploymentSummary = $outputs.deployment.value
$aiFoundrySummary = if ($deploymentSummary) { $deploymentSummary.aiFoundry } else { $null }
$foundryDeployments = if ($aiFoundrySummary) { $aiFoundrySummary.deployments } else { $null }
$foundryModelOrDeployment = if ($foundryDeployments -is [array] -and $foundryDeployments.Count -gt 0) {
    $foundryDeployments[0]
}
elseif ($null -ne $foundryDeployments -and -not [string]::IsNullOrWhiteSpace([string]$foundryDeployments)) {
    $foundryDeployments
}
else {
    $ChatDeploymentName
}

Write-Host ""
Write-Host "Admin Azure Config values:" -ForegroundColor Cyan
Write-Host "Frontend URL:              $(Format-AdminConfigValue $outputs.frontendUrl.value)"
Write-Host "AI Foundry endpoint:       $(Format-AdminConfigValue $aiFoundrySummary.endpoint)"
Write-Host "AI Foundry project:        $(Format-AdminConfigValue $aiFoundrySummary.projectName)"
Write-Host "Default model/deployment:  $(Format-AdminConfigValue $foundryModelOrDeployment)"
Write-Host "Foundry region:            $(Format-AdminConfigValue $outputs.foundryLocation.value)"

if (-not $KeepGeneratedParameters) {
    Remove-Item -Path $parametersPath -Force
}
