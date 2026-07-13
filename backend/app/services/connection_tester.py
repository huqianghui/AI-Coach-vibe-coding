"""Connection testing for Azure services: real API calls to validate credentials."""

import re
from urllib.parse import urlparse

import httpx

_AI_FOUNDRY_DOMAINS = [
    ".cognitiveservices.azure.com",
    ".services.ai.azure.com",
    ".openai.azure.com",
]


def _derive_endpoint_variants(endpoint: str) -> list[str]:
    """Given an AI Foundry endpoint, return both domain variants.

    AI Foundry resources expose the same key on two domains:
      - https://{name}.cognitiveservices.azure.com
      - https://{name}.services.ai.azure.com
    Some services (OpenAI) only work on one; others (Content Understanding,
    Speech) may only work on the other.  Return both so probes can try each.
    """
    if not endpoint:
        return []
    parsed = urlparse(endpoint.rstrip("/"))
    hostname = parsed.hostname or ""
    for domain in _AI_FOUNDRY_DOMAINS:
        if hostname.endswith(domain.lstrip(".")):
            resource_name = hostname[: -len(domain.lstrip("."))]
            if resource_name.endswith("."):
                resource_name = resource_name[:-1]
            variants = []
            for d in [".cognitiveservices.azure.com", ".services.ai.azure.com"]:
                variant = f"https://{resource_name}{d}"
                variants.append(variant)
            # Put original domain first
            original = f"https://{resource_name}{domain}"
            if original in variants:
                variants.remove(original)
                variants.insert(0, original)
            return variants
    # Not an AI Foundry endpoint — return as-is
    return [endpoint.rstrip("/")]


AZURE_HOST_PATTERN = re.compile(
    r"^https://[\w.-]+\."
    r"(azure\.com|microsoft\.com|azure\.net|windows\.net"
    r"|cognitive\.microsoft\.com|cognitiveservices\.azure\.com"
    r"|services\.ai\.azure\.com|openai\.azure\.com"
    r"|tts\.speech\.microsoft\.com)(/.*)?$",
    re.IGNORECASE,
)


def validate_endpoint_url(endpoint: str) -> tuple[bool, str]:
    """Validate endpoint URL: must be HTTPS and match Azure host patterns."""
    if not endpoint:
        return (False, "Endpoint is required")
    if not endpoint.startswith("https://"):
        return (False, "Endpoint must use HTTPS")
    if not AZURE_HOST_PATTERN.match(endpoint):
        return (
            False,
            "Endpoint must be an Azure service URL (*.azure.com, *.microsoft.com, *.azure.net)",
        )
    return (True, "")


async def detect_region_from_endpoint(endpoint: str, api_key: str) -> str:
    """Detect the Azure region from an AI Foundry endpoint.

    Tries the response header x-ms-region first, then falls back to parsing
    the resource name from the endpoint URL (e.g. 'xxx-eastus2' → 'eastus2').
    """
    try:
        base = endpoint.rstrip("/")
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Any request will return x-ms-region in headers
            url = f"{base}/openai/deployments?api-version=2024-10-21"
            response = await client.get(url, headers={"api-key": api_key})
            region = response.headers.get("x-ms-region", "")
            if region:
                return region.lower().replace(" ", "")
    except Exception:
        pass

    # Fallback: parse from hostname (e.g. ai-foundary-qiah-east-us2.cognitiveservices.azure.com)
    try:
        hostname = urlparse(endpoint).hostname or ""
        resource_name = hostname.split(".")[0]
        # Common Azure region suffixes
        known_regions = [
            "eastus",
            "eastus2",
            "westus",
            "westus2",
            "westus3",
            "centralus",
            "northcentralus",
            "southcentralus",
            "westcentralus",
            "canadacentral",
            "canadaeast",
            "northeurope",
            "westeurope",
            "uksouth",
            "ukwest",
            "francecentral",
            "germanywestcentral",
            "switzerlandnorth",
            "swedencentral",
            "norwayeast",
            "polandcentral",
            "eastasia",
            "southeastasia",
            "japaneast",
            "japanwest",
            "koreacentral",
            "koreasouth",
            "australiaeast",
            "australiasoutheast",
            "australiacentral",
            "centralindia",
            "southindia",
            "westindia",
            "brazilsouth",
            "southafricanorth",
            "uaenorth",
        ]
        name_lower = resource_name.lower().replace("-", "")
        for r in known_regions:
            if name_lower.endswith(r):
                return r
    except Exception:
        pass

    return ""


async def _get_bearer_token() -> str | None:
    """Get a bearer token via DefaultAzureCredential for keyless auth."""
    try:
        from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential

        async with AsyncDefaultAzureCredential() as cred:
            token = await cred.get_token("https://cognitiveservices.azure.com/.default")
            return token.token
    except Exception:
        return None


async def test_ai_foundry_endpoint(
    endpoint: str, api_key: str, model: str = ""
) -> tuple[bool, str]:
    """Test AI Foundry master config.

    If a model/deployment is configured, validates via a real chat completion call.
    Otherwise falls back to listing deployments (tries multiple API versions).
    Supports DefaultAzureCredential when API key is empty (disableLocalAuth).
    """
    valid, msg = validate_endpoint_url(endpoint)
    if not valid:
        return (False, msg)

    # If a model is configured, do a real chat completion test (most reliable)
    if model:
        return await test_azure_openai(endpoint, api_key, model)

    if not api_key:
        # Try DefaultAzureCredential (keyless / Entra ID auth)
        token = await _get_bearer_token()
        if not token:
            return (False, "API key is required (DefaultAzureCredential also failed)")
        headers = {"Authorization": f"Bearer {token}"}
    else:
        headers = {"api-key": api_key}

    # No model configured — try listing deployments with multiple API versions
    base = endpoint.rstrip("/")
    api_versions = ["2024-10-21", "2024-06-01", "2025-01-01-preview"]
    last_status = 0
    last_body = ""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            for api_ver in api_versions:
                url = f"{base}/openai/deployments?api-version={api_ver}"
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    count = len(data.get("data", []))
                    auth_mode = "Entra ID" if not api_key else "API key"
                    return (
                        True,
                        f"Connection successful ({count} deployment(s) found, auth: {auth_mode})",
                    )
                elif response.status_code in (401, 403):
                    return (False, f"Authentication failed: HTTP {response.status_code}")
                last_status = response.status_code
                last_body = response.text[:200]
            return (False, f"HTTP {last_status}: {last_body}")
    except Exception as e:
        return (False, f"Connection failed: {e!s}")


async def test_azure_openai(endpoint: str, api_key: str, deployment: str) -> tuple[bool, str]:
    """Test Azure OpenAI connection by making a minimal chat completion call.

    Supports DefaultAzureCredential when api_key is empty.
    """
    valid, msg = validate_endpoint_url(endpoint)
    if not valid:
        return (False, msg)
    try:
        from openai import AsyncAzureOpenAI

        if api_key:
            client = AsyncAzureOpenAI(
                azure_endpoint=endpoint,
                api_key=api_key,
                api_version="2024-06-01",
                timeout=10.0,
            )
        else:
            # Keyless auth via DefaultAzureCredential
            from azure.identity.aio import (
                DefaultAzureCredential as AsyncDefaultAzureCredential,
            )
            from azure.identity.aio import (
                get_bearer_token_provider as async_get_bearer_token_provider,
            )

            credential = AsyncDefaultAzureCredential()
            token_provider = async_get_bearer_token_provider(
                credential,
                "https://cognitiveservices.azure.com/.default",
            )
            client = AsyncAzureOpenAI(
                azure_endpoint=endpoint,
                azure_ad_token_provider=token_provider,
                api_version="2024-06-01",
                timeout=10.0,
            )
        # Try max_completion_tokens first (newer models like gpt-4o, gpt-5.4-mini, o1, o3),
        # fall back to max_tokens for older models (gpt-4, gpt-35-turbo)
        try:
            await client.chat.completions.create(
                model=deployment,
                messages=[{"role": "user", "content": "Hi"}],
                max_completion_tokens=10,
            )
        except Exception as first_err:
            if "max_completion_tokens" in str(first_err):
                await client.chat.completions.create(
                    model=deployment,
                    messages=[{"role": "user", "content": "Hi"}],
                    max_tokens=10,
                )
            else:
                raise
        return (True, "Connection successful")
    except ImportError:
        return (False, "Connection failed: openai package not installed")
    except Exception as e:
        return (False, f"Connection failed: {e!s}")


async def test_azure_speech(key: str, region: str, endpoint: str = "") -> tuple[bool, str]:
    """Test Azure Speech connectivity.

    In AI Foundry, all services (Speech, OpenAI, Content Understanding…) share
    the same endpoint and API key.

    Strategy — try multiple paths/headers/endpoints in order, succeed on first 200:
    1. AI Foundry custom domain with multiple auth headers and API paths
    2. STS token endpoint (POST /sts/v1.0/issueToken) to prove Speech key validity
    3. Regional Speech endpoint as fallback
    4. DefaultAzureCredential bearer token when no key is provided
    """
    if not key and not endpoint:
        return (False, "API key is required")
    if not region and not endpoint:
        return (False, "Region or endpoint is required")

    # Build list of probes: (method, url, headers)
    # method is "GET" or "POST"
    probes: list[tuple[str, str, dict[str, str]]] = []

    if key:
        headers_ocp = {"Ocp-Apim-Subscription-Key": key}
        headers_apikey = {"api-key": key}
    else:
        # Keyless auth via DefaultAzureCredential
        token = await _get_bearer_token()
        if not token:
            return (False, "API key is required (DefaultAzureCredential also failed)")
        headers_ocp = {"Authorization": f"Bearer {token}"}
        headers_apikey = headers_ocp

    if endpoint:
        # AI Foundry has two domains for same resource — try both
        bases = _derive_endpoint_variants(endpoint)
        speech_paths = [
            "/speechtotext/v3.2/models/base",
            "/cognitiveservices/voices/list",
        ]
        for base in bases:
            for path in speech_paths:
                url = f"{base}{path}"
                probes.append(("GET", url, headers_ocp))
                probes.append(("GET", url, headers_apikey))
            # STS token endpoint on each domain
            probes.append(
                (
                    "POST",
                    f"{base}/sts/v1.0/issueToken",
                    headers_ocp,
                )
            )

    if region:
        # Regional TTS endpoint
        probes.append(
            (
                "GET",
                f"https://{region}.tts.speech.microsoft.com/cognitiveservices/voices/list",
                headers_ocp,
            )
        )
        # Regional STS token endpoint
        probes.append(
            (
                "POST",
                f"https://{region}.api.cognitive.microsoft.com/sts/v1.0/issueToken",
                headers_ocp,
            )
        )

    if not probes:
        return (False, "No testable endpoint available")

    last_status = 0
    tried_details: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            for method, url, hdrs in probes:
                try:
                    if method == "POST":
                        response = await client.post(url, headers=hdrs, content=b"")
                    else:
                        response = await client.get(url, headers=hdrs)
                    status = response.status_code
                    if status == 200:
                        return (True, "Connection successful")
                    header_name = next(iter(hdrs))
                    tried_details.append(f"{method} ...{url[-40:]} [{header_name}]→{status}")
                    if status != 404:
                        last_status = status
                except Exception as exc:
                    header_name = next(iter(hdrs))
                    tried_details.append(f"{method} {url[-30:]}→ERR:{type(exc).__name__}")
                    continue
    except Exception as e:
        return (False, f"Connection failed: {e!s}")

    detail = "; ".join(tried_details[-6:]) if tried_details else "(no probes)"
    if last_status in (401, 403):
        return (
            False,
            f"Authentication failed (HTTP {last_status}). "
            f"Tried: {detail}. "
            "Check that Speech is enabled on your Azure AI Services resource.",
        )
    if last_status == 0:
        return (False, f"All Speech endpoints unreachable. Tried: {detail}")
    return (False, f"HTTP {last_status}. Tried: {detail}")


async def test_azure_avatar(api_key: str, region: str, endpoint: str = "") -> tuple[bool, str]:
    """Test Avatar by fetching ICE relay token.

    Tries AI Foundry custom domain first, then regional endpoint.
    Avatar uses the same Speech service credentials.
    """
    if not api_key and not endpoint:
        return (False, "API key is required for Avatar service")
    if not endpoint and not region:
        return (False, "Region or endpoint is required for Avatar service")

    probes: list[tuple[str, str, dict[str, str]]] = []
    if api_key:
        headers_ocp = {"Ocp-Apim-Subscription-Key": api_key}
        headers_apikey = {"api-key": api_key}
    else:
        token = await _get_bearer_token()
        if not token:
            return (False, "API key is required (DefaultAzureCredential also failed)")
        headers_ocp = {"Authorization": f"Bearer {token}"}
        headers_apikey = headers_ocp

    if endpoint:
        bases = _derive_endpoint_variants(endpoint)
        for base in bases:
            probes.append(
                (
                    "GET",
                    f"{base}/cognitiveservices/avatar/relay/token/v1",
                    headers_ocp,
                )
            )
            probes.append(
                (
                    "GET",
                    f"{base}/cognitiveservices/avatar/relay/token/v1",
                    headers_apikey,
                )
            )

    if region:
        probes.append(
            (
                "GET",
                f"https://{region}.tts.speech.microsoft.com/cognitiveservices/avatar/relay/token/v1",
                headers_ocp,
            )
        )

    if not probes:
        return (False, "No testable endpoint available")

    last_status = 0
    tried_details: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            for method, url, hdrs in probes:
                try:
                    if method == "POST":
                        response = await client.post(url, headers=hdrs, content=b"")
                    else:
                        response = await client.get(url, headers=hdrs)
                    if response.status_code == 200:
                        return (True, "Avatar service reachable (ICE token retrieved)")
                    header_name = next(iter(hdrs))
                    tried_details.append(
                        f"{method} ...{url[-40:]} [{header_name}]→{response.status_code}"
                    )
                    if response.status_code != 404:
                        last_status = response.status_code
                except Exception as exc:
                    header_name = next(iter(hdrs))
                    tried_details.append(f"{method} {url[-30:]}→ERR:{type(exc).__name__}")
                    continue
    except Exception as e:
        return (False, f"Avatar connection failed: {e!s}")

    detail = "; ".join(tried_details[-6:]) if tried_details else "(no probes)"
    if last_status in (401, 403):
        return (
            False,
            f"Authentication failed (HTTP {last_status}). "
            f"Tried: {detail}. "
            "Check that Avatar is enabled on your Azure AI Services resource.",
        )
    if last_status == 0:
        return (False, f"All Avatar endpoints unreachable. Tried: {detail}")
    return (False, f"Avatar test failed: HTTP {last_status}. Tried: {detail}")


async def test_azure_content_understanding(
    endpoint: str,
    api_key: str,
) -> tuple[bool, str]:
    """Test Content Understanding by listing analyzers.

    Content Understanding ONLY works on *.services.ai.azure.com (not
    *.cognitiveservices.azure.com).  The SDK uses AzureKeyCredential which
    sends the Ocp-Apim-Subscription-Key header.

    If the user provides a *.cognitiveservices.azure.com endpoint (e.g. the
    AI Foundry master endpoint), we auto-derive the *.services.ai.azure.com
    variant and try that first.
    """
    valid, msg = validate_endpoint_url(endpoint)
    if not valid:
        return (False, msg)

    # Derive both domain variants; prioritise .services.ai.azure.com for CU
    bases = _derive_endpoint_variants(endpoint)
    # Move .services.ai.azure.com to front (CU only works on that domain)
    bases_sorted = sorted(
        bases,
        key=lambda b: 0 if ".services.ai.azure.com" in b else 1,
    )

    path = "/contentunderstanding/analyzers?api-version=2025-11-01"
    if api_key:
        # AzureKeyCredential sends Ocp-Apim-Subscription-Key; also try api-key
        headers_list = [
            {"Ocp-Apim-Subscription-Key": api_key},
            {"api-key": api_key},
        ]
    else:
        token = await _get_bearer_token()
        if not token:
            return (False, "API key is required (DefaultAzureCredential also failed)")
        headers_list = [{"Authorization": f"Bearer {token}"}]

    last_status = 0
    tried: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            for base in bases_sorted:
                url = f"{base}{path}"
                for hdrs in headers_list:
                    try:
                        response = await client.get(url, headers=hdrs)
                        hdr_name = next(iter(hdrs))
                        status = response.status_code
                        if status == 200:
                            return (
                                True,
                                "Content Understanding service connected. Analyzers accessible.",
                            )
                        short_base = base.split("//")[-1].split(".")[0]
                        tried.append(f"{short_base}[{hdr_name}]→{status}")
                        if status != 404:
                            last_status = status
                    except Exception as exc:
                        hdr_name = next(iter(hdrs))
                        short_base = base.split("//")[-1].split(".")[0]
                        tried.append(f"{short_base}[{hdr_name}]→ERR:{type(exc).__name__}")
    except Exception as e:
        return (False, f"Content Understanding connection failed: {e!s}")

    detail = "; ".join(tried) if tried else "(no probes)"
    if last_status in (401, 403):
        return (
            False,
            f"Authentication failed (HTTP {last_status}). Tried: {detail}",
        )
    return (
        False,
        f"Content Understanding test failed: HTTP {last_status}. Tried: {detail}",
    )


async def test_azure_realtime(
    endpoint: str,
    api_key: str,
    deployment: str,
) -> tuple[bool, str]:
    """Test Realtime API by verifying deployment exists via REST."""
    valid, msg = validate_endpoint_url(endpoint)
    if not valid:
        return (False, msg)
    if api_key:
        headers = {"api-key": api_key}
    else:
        token = await _get_bearer_token()
        if not token:
            return (False, "API key is required (DefaultAzureCredential also failed)")
        headers = {"Authorization": f"Bearer {token}"}
    try:
        base = endpoint.rstrip("/")
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = f"{base}/openai/deployments/{deployment}?api-version=2024-06-01"
            response = await client.get(
                url,
                headers=headers,
            )
            if response.status_code == 200:
                return (True, "Realtime API deployment verified.")
            elif response.status_code in (401, 403):
                return (False, f"Authentication failed: HTTP {response.status_code}")
            elif response.status_code == 404:
                return (False, f"Deployment '{deployment}' not found")
            return (False, f"HTTP {response.status_code}: {response.text[:200]}")
    except Exception as e:
        return (False, f"Realtime connection failed: {e!s}")


async def test_azure_voice_live(endpoint: str, api_key: str, region: str) -> tuple[bool, str]:
    """Test Azure Voice Live API configuration by validating region and endpoint format."""
    from app.services.voice_live_service import SUPPORTED_REGIONS

    valid, msg = validate_endpoint_url(endpoint)
    if not valid:
        return (False, msg)
    if not api_key:
        # Try DefaultAzureCredential
        token = await _get_bearer_token()
        if not token:
            return (False, "API key is required (DefaultAzureCredential also failed)")
        auth_headers = {"Authorization": f"Bearer {token}"}
    else:
        auth_headers = {"api-key": api_key}
    if region.lower() not in SUPPORTED_REGIONS:
        return (
            False,
            f"Unsupported region: {region}. Voice Live API is only available in: "
            f"{', '.join(sorted(SUPPORTED_REGIONS))}",
        )
    # Attempt a lightweight HTTP probe to the endpoint
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = f"{endpoint.rstrip('/')}/openai/realtime"
            response = await client.get(
                url,
                headers=auth_headers,
                params={"api-version": "2025-04-01-preview"},
            )
            if response.status_code in (404, 405, 426):
                return (True, "Connection successful (endpoint reachable)")
            elif response.status_code in (401, 403):
                return (False, f"Authentication failed: HTTP {response.status_code}")
            else:
                return (True, f"Endpoint reachable (HTTP {response.status_code})")
    except Exception as e:
        return (
            True,
            f"Configuration valid (endpoint format correct, connectivity check skipped: {e})",
        )


async def test_service_connection(
    service_name: str,
    endpoint: str,
    api_key: str,
    deployment: str,
    region: str,
    master_endpoint: str = "",
    master_key: str = "",
    master_region: str = "",
    master_model: str = "",
) -> tuple[bool, str]:
    """Route connection test to the correct service-specific tester.

    When a per-service config has empty endpoint/key/model, falls back to master
    AI Foundry values and derives service-specific URLs.
    """
    # Apply master fallbacks
    effective_key = api_key or master_key
    effective_region = region or master_region
    effective_deployment = deployment or master_model

    if service_name == "ai_foundry":
        effective_endpoint = endpoint or master_endpoint
        return await test_ai_foundry_endpoint(
            effective_endpoint, effective_key, effective_deployment
        )
    elif service_name in ("azure_openai", "prompt_optimizer"):
        effective_endpoint = endpoint or (
            f"{master_endpoint.rstrip('/')}/" if master_endpoint else ""
        )
        return await test_azure_openai(effective_endpoint, effective_key, effective_deployment)
    elif service_name in ("azure_speech_stt", "azure_speech_tts"):
        effective_endpoint = endpoint or master_endpoint
        return await test_azure_speech(
            key=effective_key, region=effective_region, endpoint=effective_endpoint
        )
    elif service_name == "azure_avatar":
        effective_endpoint = endpoint or master_endpoint
        return await test_azure_avatar(
            api_key=effective_key, region=effective_region, endpoint=effective_endpoint
        )
    elif service_name == "azure_voice_live":
        effective_endpoint = endpoint or master_endpoint
        return await test_azure_voice_live(effective_endpoint, effective_key, effective_region)
    elif service_name == "azure_content":
        effective_endpoint = endpoint or master_endpoint
        return await test_azure_content_understanding(effective_endpoint, effective_key)
    elif service_name == "azure_openai_realtime":
        effective_endpoint = endpoint or master_endpoint
        return await test_azure_realtime(effective_endpoint, effective_key, effective_deployment)
    else:
        return (False, f"Unknown service: {service_name}")
