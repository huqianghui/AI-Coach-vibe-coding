#!/usr/bin/env bash
# Grant the RBAC chain required for Foundry IQ knowledge bases (agentic
# retrieval / KB MCP) to work end-to-end with an Azure AI Foundry Agent:
#
#   Layer 1  Foundry project MI  --roles-->  AI Search resource
#   Layer 3  AI Search MI        --role--->  Azure OpenAI resource (KB models[])
#
# Why this script exists:
#   Binding a knowledge base to an Agent is a data-plane operation — it only
#   writes an MCP endpoint URL into the Agent definition. It does NOT grant
#   the Foundry project's managed identity any permission on the AI Search
#   resource, does NOT enable Entra ID auth on the Search service, and does
#   NOT authorize the Search service to call the Azure OpenAI model that the
#   knowledge base uses for agentic retrieval. Without all of these, KB
#   retrieval fails with 403/401 somewhere along the chain
#   (observed 2026-07-27, see docs/microsoft-agent-framework/02-model-vs-agent-mode.md §7).
#
# NOT covered by this script (see doc 02 §7 for both):
#   - Layer 2: the Foundry project also needs a RemoteTool connection with
#     authType=ProjectManagedIdentity. Created by the backend's agent sync —
#     re-run agent_sync_service.sync_agent_for_profile() if the agent predates
#     that logic (a plain CognitiveSearch/ApiKey connection causes 403).
#   - KB definition: if the AOAI resource has disableLocalAuth=true, the KB's
#     models[].azureOpenAIParameters must use apiKey=null + authIdentity=null
#     (= Search system MI) instead of an API key. Data-plane PUT on
#     /knowledgebases/{name} — see doc 02 §7.3.
#
# This script is idempotent — safe to re-run.
#
# Prerequisites:
#   - az login --tenant fdpo.onmicrosoft.com   (Microsoft Non-Production tenant)
#   - Caller needs Owner or User Access Administrator on the Search and AOAI resources.
#
# Usage:
#   ./grant-search-rbac.sh [subscription_id] [foundry_rg] [foundry_account] [project_name] [search_rg] [search_name] [aoai_rg] [aoai_name]

set -euo pipefail

SUBSCRIPTION_ID="${1:-7a03e9b8-18d6-48e7-b186-0ec68da9e86f}"
FOUNDRY_RG="${2:-ai-foundary-rg}"
FOUNDRY_ACCOUNT="${3:-ai-foundary-hu-sweden-central2}"
PROJECT_NAME="${4:-avarda-demo-prj}"
SEARCH_RG="${5:-ai-search-rg}"
SEARCH_NAME="${6:-ai-search-southeast-asia}"
AOAI_RG="${7:-openai-rg}"
AOAI_NAME="${8:-openai-hu-test-sweden-central3}"

SEARCH_SCOPE="/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${SEARCH_RG}/providers/Microsoft.Search/searchServices/${SEARCH_NAME}"

echo "==> Resolving managed identity of Foundry project '${PROJECT_NAME}'..."
PRINCIPAL_ID=$(az rest --method get \
  --url "https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${FOUNDRY_RG}/providers/Microsoft.CognitiveServices/accounts/${FOUNDRY_ACCOUNT}/projects/${PROJECT_NAME}?api-version=2025-06-01" \
  --query "identity.principalId" -o tsv)

if [[ -z "${PRINCIPAL_ID}" || "${PRINCIPAL_ID}" == "null" ]]; then
  echo "ERROR: project '${PROJECT_NAME}' has no system-assigned managed identity." >&2
  exit 1
fi
echo "    principalId: ${PRINCIPAL_ID}"

echo "==> Enabling Entra ID (RBAC) data-plane auth on Search service '${SEARCH_NAME}' (aadOrApiKey keeps API keys working)..."
az search service update -n "${SEARCH_NAME}" -g "${SEARCH_RG}" \
  --subscription "${SUBSCRIPTION_ID}" \
  --auth-options aadOrApiKey \
  --aad-auth-failure-mode http401WithBearerChallenge \
  --query "authOptions" -o json

# Search Index Data Reader  : read documents during retrieval
# Search Service Contributor: enumerate/execute knowledge base (agentic retrieval) MCP tools
for ROLE in "Search Index Data Reader" "Search Service Contributor"; do
  echo "==> Ensuring role '${ROLE}' for ${PRINCIPAL_ID} on ${SEARCH_NAME}..."
  EXISTING=$(az role assignment list --scope "${SEARCH_SCOPE}" \
    --query "[?principalId=='${PRINCIPAL_ID}' && roleDefinitionName=='${ROLE}'] | length(@)" -o tsv)
  if [[ "${EXISTING}" != "0" ]]; then
    echo "    already assigned — skipping"
  else
    az role assignment create \
      --assignee-object-id "${PRINCIPAL_ID}" \
      --assignee-principal-type ServicePrincipal \
      --role "${ROLE}" \
      --scope "${SEARCH_SCOPE}" \
      --query "id" -o tsv
    echo "    created"
  fi
done

# Layer 3: the KB's models[] entry calls an Azure OpenAI deployment during
# agentic retrieval. When that AOAI resource has disableLocalAuth=true, the KB
# must authenticate with the Search service's system-assigned MI, which needs
# this role on the AOAI resource.
AOAI_SCOPE="/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${AOAI_RG}/providers/Microsoft.CognitiveServices/accounts/${AOAI_NAME}"

echo "==> Resolving system-assigned managed identity of Search service '${SEARCH_NAME}'..."
SEARCH_PRINCIPAL_ID=$(az search service show -n "${SEARCH_NAME}" -g "${SEARCH_RG}" \
  --subscription "${SUBSCRIPTION_ID}" --query "identity.principalId" -o tsv)

if [[ -z "${SEARCH_PRINCIPAL_ID}" || "${SEARCH_PRINCIPAL_ID}" == "null" ]]; then
  echo "ERROR: Search service '${SEARCH_NAME}' has no system-assigned managed identity." >&2
  echo "       Enable it with: az search service update -n ${SEARCH_NAME} -g ${SEARCH_RG} --identity-type SystemAssigned" >&2
  exit 1
fi
echo "    principalId: ${SEARCH_PRINCIPAL_ID}"

ROLE="Cognitive Services OpenAI User"
echo "==> Ensuring role '${ROLE}' for ${SEARCH_PRINCIPAL_ID} on ${AOAI_NAME}..."
EXISTING=$(az role assignment list --scope "${AOAI_SCOPE}" \
  --query "[?principalId=='${SEARCH_PRINCIPAL_ID}' && roleDefinitionName=='${ROLE}'] | length(@)" -o tsv)
if [[ "${EXISTING}" != "0" ]]; then
  echo "    already assigned — skipping"
else
  az role assignment create \
    --assignee-object-id "${SEARCH_PRINCIPAL_ID}" \
    --assignee-principal-type ServicePrincipal \
    --role "${ROLE}" \
    --scope "${AOAI_SCOPE}" \
    --query "id" -o tsv
  echo "    created"
fi

echo ""
echo "Done. Note: RBAC propagation can take 5-10 minutes before KB retrieval succeeds."
echo "Verify with: cd backend && .venv/bin/python3 ../docs/microsoft-agent-framework/tests/test_agent_foundry_iq_grounding.py"
