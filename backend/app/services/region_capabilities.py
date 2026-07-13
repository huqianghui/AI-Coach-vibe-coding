"""Region capability lookup for Azure AI services.

Hardcoded map maintained from Azure docs. Last verified: 2026-03-27.
"""

# Update frequency: re-verify monthly from Azure docs.
# Sources:
#   Avatar: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/regions
#   Voice Live: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/voice-live
#   General: https://learn.microsoft.com/en-us/azure/ai-services/openai/concepts/models
LAST_VERIFIED = "2026-03-27"

AVATAR_REGIONS: set[str] = {
    "eastus2",
    "northeurope",
    "southcentralus",
    "southeastasia",
    "swedencentral",
    "westeurope",
    "westus2",
}

VOICE_LIVE_REGIONS: set[str] = {
    "australiaeast",
    "brazilsouth",
    "canadaeast",
    "eastus",
    "eastus2",
    "francecentral",
    "germanywestcentral",
    "italynorth",
    "japaneast",
    "norwayeast",
    "southafricanorth",
    "southcentralus",
    "southeastasia",
    "swedencentral",
    "switzerlandnorth",
    "uksouth",
    "westeurope",
    "westus",
    "westus2",
    "westus3",
}

VOICE_LIVE_AGENT_REGIONS: set[str] = {
    "australiaeast",
    "brazilsouth",
    "canadaeast",
    "eastus",
    "eastus2",
    "francecentral",
    "germanywestcentral",
    "italynorth",
    "japaneast",
    "norwayeast",
    "southafricanorth",
    "southcentralus",
    "southeastasia",
    "swedencentral",
    "switzerlandnorth",
    "uksouth",
    "westeurope",
    "westus",
    "westus2",
    "westus3",
}

UNRESTRICTED_SERVICES: set[str] = {
    "azure_openai",
    "azure_speech_stt",
    "azure_speech_tts",
    "azure_content",
    "azure_openai_realtime",
    "prompt_optimizer",
}

ALL_SERVICE_NAMES: list[str] = [
    "azure_openai",
    "azure_speech_stt",
    "azure_speech_tts",
    "azure_avatar",
    "azure_content",
    "azure_openai_realtime",
    "azure_voice_live",
    "prompt_optimizer",
]

_AVATAR_REGIONS_DISPLAY = ", ".join(sorted(AVATAR_REGIONS))


def get_region_capabilities(region: str) -> dict:
    """Return per-service availability for a given Azure region.

    Args:
        region: Azure region identifier (case-insensitive), e.g. "eastus2", "WestEurope".

    Returns:
        Dict with 'region' (original input) and 'services' mapping each service name
        to {"available": bool, "note": str}.
    """
    region_lower = region.lower().strip()

    services: dict[str, dict] = {}

    for service_name in ALL_SERVICE_NAMES:
        if service_name in UNRESTRICTED_SERVICES:
            services[service_name] = {"available": True, "note": ""}

        elif service_name == "azure_avatar":
            available = region_lower in AVATAR_REGIONS
            note = "" if available else f"Available in: {_AVATAR_REGIONS_DISPLAY}"
            services[service_name] = {"available": available, "note": note}

        elif service_name == "azure_voice_live":
            available = region_lower in VOICE_LIVE_REGIONS
            if available and region_lower in VOICE_LIVE_AGENT_REGIONS:
                note = "Agent and Model modes available"
            elif available:
                note = "Model mode only; Agent mode not available in this region"
            else:
                note = "Not available in this region"
            services[service_name] = {"available": available, "note": note}

        else:
            # Unknown service -- mark as unavailable
            services[service_name] = {"available": False, "note": "Unknown service"}

    return {"region": region, "services": services}
