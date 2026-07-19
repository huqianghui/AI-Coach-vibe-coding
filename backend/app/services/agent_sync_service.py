"""Agent sync service: bidirectional sync between HCP profiles and AI Foundry Agents.

Creates, updates, and deletes AI Foundry Agents (via azure-ai-projects SDK)
when HCP profiles change.  Uses the Agent Registry API
(``client.agents.create_version()``) which stores agents as
``name:version`` pairs (e.g. ``Dr-Li-Mei:2``).

Authentication: DefaultAzureCredential (Entra ID) preferred, API Key fallback.
"""

import asyncio
import json
import logging
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import config_service
from app.services.agents.adapters.azure_voice_live import parse_voice_live_mode

logger = logging.getLogger(__name__)

AGENT_REGISTRY_API_VERSION = "2025-01-01-preview"

DEFAULT_AGENT_TEMPLATE = """You are {name}, a {specialty} specialist.

Personality: {personality_type}
Communication Style: {communication_style_desc} (level: {communication_style}/100)
Emotional State: {emotional_state_desc} (level: {emotional_state}/100)

Background:
- Hospital: {hospital}
- Title: {title}
- Expertise: {expertise_areas}
- Prescribing Habits: {prescribing_habits}
- Key Concerns: {concerns}

Common Objections:
{objections}

Topics You Probe About:
{probe_topics}

Stay in character throughout the conversation. \
Respond as this HCP would in a real face-to-face interaction with a Medical Representative.

Language rules:
- Default to Simplified Chinese in all responses.
- Keep medical abbreviations, drug names, study names, and technical terms in English when
    appropriate.
- Only switch to English if the Medical Representative explicitly asks in English or requests
    English."""


def build_agent_instructions(profile_data: dict, template: str | None = None) -> str:
    """Build agent instructions from HCP profile data.

    If agent_instructions_override is non-empty, use it instead of auto-generated text (D-02).

    Converts list fields to comma-separated strings, adds computed descriptor
    fields (communication_style_desc, emotional_state_desc), and formats
    using the provided template or DEFAULT_AGENT_TEMPLATE.

    Uses str.format_map with defaultdict for safe missing-key handling.
    """
    # Check for override first (D-02)
    override = profile_data.get("agent_instructions_override", "")
    if override and override.strip():
        return override.strip()

    data = dict(profile_data)

    # Convert list fields to comma-separated strings
    for field in ("expertise_areas", "objections", "probe_topics"):
        value = data.get(field)
        if isinstance(value, list):
            data[field] = ", ".join(str(item) for item in value)

    # Add computed descriptor fields
    comm_style = data.get("communication_style", 50)
    if isinstance(comm_style, (int, float)):
        data["communication_style_desc"] = "direct" if comm_style < 50 else "indirect"
    else:
        data["communication_style_desc"] = "moderate"

    emotional = data.get("emotional_state", 50)
    if isinstance(emotional, (int, float)):
        if emotional < 30:
            data["emotional_state_desc"] = "calm and open"
        elif emotional < 70:
            data["emotional_state_desc"] = "neutral"
        else:
            data["emotional_state_desc"] = "resistant"
    else:
        data["emotional_state_desc"] = "neutral"

    safe_data = defaultdict(lambda: "", data)
    use_template = template or DEFAULT_AGENT_TEMPLATE
    return use_template.format_map(safe_data)


VOICE_LIVE_ENABLED_KEY = "microsoft.voice-live.enabled"
VOICE_LIVE_CONFIG_KEY = "microsoft.voice-live.configuration"


def _chunk_metadata_value(key: str, value: str, max_len: int = 512) -> dict[str, str]:
    """Split a long metadata value into 512-char chunks.

    Azure agent metadata values are limited to 512 characters.
    Base key stores the first chunk; continuations use key.1, key.2, etc.
    """
    if len(value) <= max_len:
        return {key: value}
    result: dict[str, str] = {}
    idx = 0
    chunk_num = 0
    while idx < len(value):
        chunk = value[idx : idx + max_len]
        chunk_key = key if chunk_num == 0 else f"{key}.{chunk_num}"
        result[chunk_key] = chunk
        idx += max_len
        chunk_num += 1
    return result


def build_voice_live_metadata(profile: object) -> dict[str, str] | None:
    """Build microsoft.voice-live.configuration metadata from HCP profile voice fields.

    Uses resolve_voice_config() to get the effective voice/avatar settings --
    VoiceLiveInstance fields when assigned, or safe defaults (voice disabled)
    when not (D-12).

    The output format matches Azure AI Foundry Portal's own save format:
    ``{"session": {camelCase keys for voice, avatar, turnDetection, etc.}}``

    IMPORTANT: Azure Agent metadata values are limited to 512 characters per key.
    The Portal likely uses an internal API without this limit.  We stay under 512
    by omitting null fields and false-valued defaults — Foundry fills them in.

    Returns dict[str, str] suitable for agent metadata, or None if voice_live_enabled is False.
    Includes ``description`` and ``modified_at`` keys to match Foundry Portal format.
    """
    from app.services.voice_live_instance_service import resolve_voice_config

    vc = resolve_voice_config(profile)

    if not vc.get("voice_live_enabled", True):
        return None

    # --- Build session config in Foundry Portal's camelCase format ---
    # Only include non-null, non-default fields to stay within 512-char limit.
    session: dict = {}

    # Voice settings (always required)
    voice_name = vc.get("voice_name", "en-US-AvaNeural")
    voice: dict = {"name": voice_name}
    voice_type = vc.get("voice_type", "azure-standard")
    if voice_type and voice_type != "azure-standard":
        voice["type"] = voice_type
    voice_temp = vc.get("voice_temperature", 0.8)
    if voice_temp != 0.8:
        voice["temperature"] = voice_temp
    playback_speed = vc.get("playback_speed", 1.0)
    if playback_speed != 1.0:
        voice["rate"] = str(playback_speed)
    is_hd = ":DragonHDLatestNeural" in voice_name or "HD" in voice_name
    if is_hd:
        voice["isHdVoice"] = True
    session["voice"] = voice

    # Input audio transcription — omit "model" (always "azure-speech") to save chars.
    # Only include when language is non-default.
    recognition_lang = vc.get("recognition_language", "auto")
    transcription_lang = (
        "auto-detect" if recognition_lang in ("auto", "auto-detect") else recognition_lang
    )
    if transcription_lang != "auto-detect":
        session["inputAudioTranscription"] = {"language": transcription_lang}

    # Turn detection — only include non-null, non-default sub-fields
    turn_detection_type = vc.get("turn_detection_type", "azure_semantic_vad")
    turn_detection: dict = {"type": turn_detection_type}
    if vc.get("eou_detection", False):
        turn_detection["endOfUtteranceDetection"] = {"model": "semantic_detection_v1"}
    # Omit removeFillerWords:true — Foundry default is true
    session["turnDetection"] = turn_detection

    # Noise suppression — only include when enabled (omit null)
    if vc.get("noise_suppression", False):
        session["inputAudioNoiseReduction"] = {"type": "azure_deep_noise_suppression"}

    # Echo cancellation — only include when enabled (omit null)
    if vc.get("echo_cancellation", False):
        session["inputAudioEchoCancellation"] = {"type": "server_echo_cancellation"}

    # fillerResponse — omit null (Foundry default is null)

    # Avatar settings — only include when avatar is enabled
    avatar_enabled = vc.get("avatar_enabled", True)
    avatar_char = vc.get("avatar_character", "")
    if avatar_enabled and avatar_char:
        avatar: dict = {"character": avatar_char}
        avatar_style = vc.get("avatar_style", "")
        if avatar_style:
            avatar["style"] = avatar_style
        if vc.get("avatar_customized", False):
            avatar["customized"] = True
        session["avatar"] = avatar

    # Proactive engagement — only include when True (default is False)
    if vc.get("proactive_engagement", False):
        session["proactiveEngagement"] = True

    # Wrap in {"session": {...}} to match Foundry Portal format
    config = {"session": session}

    config_json = json.dumps(config, separators=(",", ":"))

    # Safety check: if still >512, log warning (should not happen with defaults omitted)
    if len(config_json) > 512:
        logger.warning(
            "build_voice_live_metadata: config_json=%d chars (>512 limit), "
            "agent metadata update may fail. Profile=%s",
            len(config_json),
            getattr(profile, "id", "?"),
        )

    result = {VOICE_LIVE_ENABLED_KEY: "true"}
    result[VOICE_LIVE_CONFIG_KEY] = config_json

    # Add Portal-compatible metadata keys (matches Foundry Portal save format)
    import time

    name = getattr(profile, "name", "")
    result["description"] = f"HCP Agent: {name}" if name else "HCP Agent"
    result["modified_at"] = str(int(time.time()))

    return result


def build_cleared_voice_metadata() -> dict[str, str]:
    """Return metadata dict that clears Voice Live configuration on an agent (RD-4).

    Used when unassigning a VoiceLiveInstance from an HCP profile to disable
    voice live on the agent without deleting the agent itself.
    """
    return {VOICE_LIVE_ENABLED_KEY: "false", VOICE_LIVE_CONFIG_KEY: "{}"}


async def update_agent_metadata_only(
    db: AsyncSession,
    agent_id: str,
    new_metadata: dict[str, str],
    *,
    endpoint_override: str = "",
    key_override: str = "",
) -> str | None:
    """Update only voice-live metadata keys on an existing agent without touching instructions.

    Fetches current agent metadata, removes old microsoft.voice-live.* keys,
    merges in new_metadata, and updates via create_version.

    Returns the new agent version string on success, or None on failure.
    Callers should update profile.agent_version with the returned value
    to keep the platform version in sync with Foundry.
    """
    if endpoint_override:
        project_endpoint, api_key = endpoint_override, key_override
    else:
        project_endpoint, api_key = await get_project_endpoint(db)

    client = _get_project_client(project_endpoint, api_key)

    try:
        # Get current agent to read existing metadata and instructions
        agent = await asyncio.to_thread(client.agents.get, agent_name=agent_id)

        # Build merged metadata: remove old VL keys, add new ones
        current_metadata: dict[str, str] = {}
        if hasattr(agent, "metadata") and agent.metadata:
            current_metadata = dict(agent.metadata)

        # Remove all microsoft.voice-live.* keys (including chunk keys like .configuration.1)
        keys_to_remove = [k for k in current_metadata if k.startswith("microsoft.voice-live.")]
        for k in keys_to_remove:
            del current_metadata[k]

        # Merge in new metadata
        current_metadata.update(new_metadata)

        # Get instructions and model from current agent
        latest = getattr(agent, "versions", {}).get("latest", {})
        definition = latest.get("definition", {})
        instructions = definition.get("instructions", "")
        model = definition.get("model", "gpt-4o")

        if not instructions:
            logger.warning(
                "update_agent_metadata_only: read-back instructions empty for agent %s "
                "(Foundry may have returned unexpected format). "
                "Proceeding but instructions may be lost.",
                agent_id,
            )

        # Preserve existing tools from the current agent definition (Phase 17)
        existing_tools = definition.get("tools", [])

        from azure.ai.projects.models import PromptAgentDefinition

        new_definition = PromptAgentDefinition(
            model=model, instructions=instructions, tools=existing_tools or []
        )

        result = await asyncio.to_thread(
            client.agents.create_version,
            agent_name=agent_id,
            definition=new_definition,
            metadata=current_metadata,
        )
        new_version = str(result.version) if hasattr(result, "version") else None
        logger.info(
            "update_agent_metadata_only: updated metadata for agent %s, new version=%s",
            agent_id,
            new_version,
        )
        return new_version
    except Exception as e:
        logger.warning("update_agent_metadata_only failed for agent %s: %s", agent_id, e)
        return None


class _ApiKeyTokenCredential:
    """Minimal TokenCredential stub so AIProjectClient constructor doesn't fail.

    The actual authentication is handled by AzureKeyCredentialPolicy which
    sends the key as the 'api-key' HTTP header. This stub is only needed
    because the SDK constructor type-checks for TokenCredential.
    """

    def __init__(self, api_key: str):
        self._key = api_key

    def get_token(self, *scopes, **kwargs):
        import time

        from azure.core.credentials import AccessToken

        return AccessToken(self._key, int(time.time()) + 86400)


def _get_project_client(endpoint: str, api_key: str = ""):
    """Create an AIProjectClient — prefers Entra ID, falls back to API Key.

    Authentication priority:
      1. DefaultAzureCredential (Managed Identity / az login / Service Principal)
         — required for creating new agents (API Key returns 500 on creation).
      2. API Key via ``api-key`` header — works for read/update/delete only.

    See docs/microsoft-agent-framework/09-agent-api-version-evolution.md
    """
    from azure.ai.projects import AIProjectClient

    # 1. Try Entra ID (DefaultAzureCredential)
    try:
        from azure.identity import DefaultAzureCredential

        credential = DefaultAzureCredential()
        # Probe: verify a token can actually be obtained (az login / MI / SP)
        credential.get_token("https://ai.azure.com/.default")
        logger.info("_get_project_client: using DefaultAzureCredential (Entra ID)")
        return AIProjectClient(endpoint=endpoint, credential=credential)
    except Exception as exc:
        logger.debug("_get_project_client: DefaultAzureCredential unavailable: %s", exc)

    # 2. Fallback to API Key (cannot create new agents, but can read/update/delete)
    if api_key:
        from azure.core.credentials import AzureKeyCredential
        from azure.core.pipeline.policies import AzureKeyCredentialPolicy

        logger.info("_get_project_client: using API Key authentication")
        return AIProjectClient(
            endpoint=endpoint,
            credential=_ApiKeyTokenCredential(api_key),
            authentication_policy=AzureKeyCredentialPolicy(
                credential=AzureKeyCredential(api_key),
                name="api-key",
            ),
        )

    raise ValueError(
        "No valid credential available. Either run 'az login' for Entra ID or provide an API key."
    )


async def get_project_endpoint(db: AsyncSession) -> tuple[str, str]:
    """Derive AI Foundry project endpoint and API key from config.

    Resolution order for project_name:
      1. Master AI Foundry config default_project field (DB)
      2. voice_live config model_or_deployment (agent mode JSON with project_name)
      3. AZURE_FOUNDRY_DEFAULT_PROJECT env var (Settings)
      4. Bare endpoint (no /api/projects/ suffix — will likely 404)

    Returns:
        Tuple of (project_endpoint, api_key).
    """
    from app.config import get_settings

    base_endpoint = await config_service.get_effective_endpoint(db, "azure_voice_live")
    api_key = await config_service.get_effective_key(db, "azure_voice_live")

    # 1. Master config default_project (most authoritative, set via admin UI)
    master = await config_service.get_master_config(db)
    project_name = master.default_project if master else ""

    # 2. voice_live config agent mode JSON
    if not project_name:
        voice_config = await config_service.get_config(db, "azure_voice_live")
        if voice_config and voice_config.model_or_deployment:
            mode_info = parse_voice_live_mode(voice_config.model_or_deployment)
            project_name = mode_info.get("project_name", "")

    # 3. Fallback: env var AZURE_FOUNDRY_DEFAULT_PROJECT
    if not project_name:
        settings = get_settings()
        project_name = settings.azure_foundry_default_project

    base = base_endpoint.rstrip("/")
    if "/api/projects/" in base:
        project_endpoint = base
    elif project_name:
        project_endpoint = f"{base}/api/projects/{project_name}"
    else:
        logger.warning(
            "No project name configured for AI Foundry agent sync. "
            "Set default_project in AI Foundry config or "
            "AZURE_FOUNDRY_DEFAULT_PROJECT env var."
        )
        project_endpoint = base

    logger.info(
        "get_project_endpoint: base=%s, project=%s, final=%s",
        base_endpoint,
        project_name,
        project_endpoint,
    )
    return (project_endpoint, api_key)


def _sanitize_agent_name(name: str) -> str:
    """Sanitize name into a valid Azure AI Foundry agent name.

    Azure rules: alphanumeric + hyphens only, start/end with alphanumeric, max 63 chars.
    Underscores, spaces, dots, Chinese characters etc. are all replaced with hyphens.
    """
    import re

    sanitized = re.sub(r"[^a-zA-Z0-9-]", "-", name.strip())
    sanitized = re.sub(r"-+", "-", sanitized).strip("-")
    return sanitized[:63] or "agent"


async def create_agent(
    db: AsyncSession,
    name: str,
    instructions: str,
    model: str | None = None,
    *,
    metadata: dict[str, str] | None = None,
    tools: list | None = None,
    endpoint_override: str = "",
    key_override: str = "",
) -> dict:
    """Create an AI Foundry Agent via azure-ai-projects SDK (Agent v2 API).

    Uses the Agent Registry API (client.agents.create_version) with
    PromptAgentDefinition. Returns dict with agent name, version, and id.

    Authentication via API Key (``api-key`` header).

    Azure AI Foundry limitation: API Key auth can update existing agents but
    may fail (HTTP 500) when creating brand-new agent registrations.  When
    creation fails with 500, this function checks whether the agent was
    pre-created in Foundry Portal and, if so, falls back to an update.

    Pass metadata to attach Voice Live configuration or other key-value pairs.
    Pass endpoint_override/key_override to skip DB+env lookup (used by batch sync).
    """
    from azure.ai.projects.models import PromptAgentDefinition
    from azure.core.exceptions import HttpResponseError

    if not model:
        from app.config import get_settings

        model = get_settings().voice_live_default_model

    if endpoint_override:
        project_endpoint, api_key = endpoint_override, key_override
    else:
        project_endpoint, api_key = await get_project_endpoint(db)
    logger.info("create_agent: endpoint=%s, has_key=%s", project_endpoint, bool(api_key))

    agent_name = _sanitize_agent_name(name)
    definition = PromptAgentDefinition(model=model, instructions=instructions, tools=tools or [])
    client = _get_project_client(project_endpoint, api_key)

    max_retries = 3
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            result = await asyncio.to_thread(
                client.agents.create_version,
                agent_name=agent_name,
                definition=definition,
                description=f"HCP Agent: {name}",
                metadata=metadata,
            )
            return {
                "id": result.name,
                "name": result.name,
                "version": result.version,
                "model": model,
            }
        except Exception as e:
            last_error = e
            err_str = str(e)
            is_transient = (
                "RemoteDisconnected" in err_str
                or "Connection aborted" in err_str
                or "ConnectionError" in err_str
                or "ConnectionResetError" in err_str
            )
            if is_transient and attempt < max_retries:
                wait = 2**attempt  # 2s, 4s
                logger.warning(
                    "create_agent: transient error on attempt %d/%d for '%s': %s. "
                    "Retrying in %ds...",
                    attempt,
                    max_retries,
                    agent_name,
                    e,
                    wait,
                )
                await asyncio.sleep(wait)
                continue

            # On server_error (500), check if agent was pre-created in Portal.
            # API Key auth can update existing agents but cannot create new ones.
            is_server_500 = (
                isinstance(e, HttpResponseError) and e.status_code == 500
            ) or "server_error" in err_str
            if is_server_500:
                logger.warning(
                    "create_agent: server 500 for new agent '%s'. "
                    "Checking if agent was pre-created in Foundry Portal...",
                    agent_name,
                )
                try:
                    existing = await asyncio.to_thread(client.agents.get, agent_name=agent_name)
                    if existing:
                        logger.info(
                            "create_agent: agent '%s' exists in Foundry (pre-created). "
                            "Updating with new version...",
                            agent_name,
                        )
                        result = await asyncio.to_thread(
                            client.agents.create_version,
                            agent_name=agent_name,
                            definition=definition,
                            description=f"HCP Agent: {name}",
                            metadata=metadata,
                        )
                        return {
                            "id": result.name,
                            "name": result.name,
                            "version": result.version,
                            "model": model,
                        }
                except Exception:
                    pass  # Agent doesn't exist — fall through to error

                logger.error(
                    "create_agent: cannot create new agent '%s' with API Key auth. "
                    "Azure AI Foundry requires agents to be pre-created in Portal "
                    "before they can be updated via API Key. "
                    "Please create agent '%s' in Azure AI Foundry Portal first, "
                    "then retry sync.",
                    agent_name,
                    agent_name,
                )
                raise RuntimeError(
                    f"Agent creation failed: Azure AI Foundry does not support "
                    f"creating new agents via API Key. Please create agent "
                    f"'{agent_name}' in Azure AI Foundry Portal first, then "
                    f"retry the sync operation."
                ) from e

            logger.error(
                "create_agent failed: endpoint=%s, agent_name=%s, attempt=%d, error=%s",
                project_endpoint,
                agent_name,
                attempt,
                e,
            )
            raise RuntimeError(f"Agent creation failed (endpoint: {project_endpoint}): {e}") from e

    raise RuntimeError(
        f"Agent creation failed after {max_retries} attempts "
        f"(endpoint: {project_endpoint}): {last_error}"
    ) from last_error


async def update_agent(
    db: AsyncSession,
    agent_id: str,
    name: str,
    instructions: str,
    model: str | None = None,
    *,
    metadata: dict[str, str] | None = None,
    tools: list | None = None,
    endpoint_override: str = "",
    key_override: str = "",
) -> dict:
    """Update an existing AI Foundry Agent by creating a new version.

    AI Foundry agents are immutable — updates create new versions.
    Returns dict with updated agent metadata.

    Pass metadata to attach Voice Live configuration or other key-value pairs.
    Pass endpoint_override/key_override to skip DB+env lookup (used by batch sync).
    """
    from azure.ai.projects.models import PromptAgentDefinition

    if not model:
        from app.config import get_settings

        model = get_settings().voice_live_default_model

    if endpoint_override:
        project_endpoint, api_key = endpoint_override, key_override
    else:
        project_endpoint, api_key = await get_project_endpoint(db)
    logger.info("update_agent: endpoint=%s, agent_id=%s", project_endpoint, agent_id)
    client = _get_project_client(project_endpoint, api_key)

    definition = PromptAgentDefinition(model=model, instructions=instructions, tools=tools or [])

    try:
        result = await asyncio.to_thread(
            client.agents.create_version,
            agent_name=agent_id,
            definition=definition,
            description=f"HCP Agent: {name}",
            metadata=metadata,
        )
    except Exception as e:
        logger.error(
            "update_agent failed: endpoint=%s, agent_id=%s, error=%s",
            project_endpoint,
            agent_id,
            e,
        )
        raise RuntimeError(f"Agent update failed (endpoint: {project_endpoint}): {e}") from e
    return {
        "id": result.name,
        "name": result.name,
        "version": result.version,
        "model": model,
    }


async def delete_agent(db: AsyncSession, agent_id: str) -> bool:
    """Delete an AI Foundry Agent via azure-ai-projects SDK.

    Returns True if deletion was successful.
    """
    project_endpoint, api_key = await get_project_endpoint(db)
    client = _get_project_client(project_endpoint, api_key)

    try:
        await asyncio.to_thread(client.agents.delete, agent_name=agent_id)
        return True
    except Exception as e:
        logger.warning("Failed to delete agent %s: %s", agent_id, e)
        return False


async def prefetch_sync_config(db: AsyncSession) -> tuple[str, str, str]:
    """Pre-fetch config values needed for agent sync (endpoint, api_key, model).

    Call this BEFORE flushing DB writes so the config reads happen before
    any write locks are held (avoids SQLite "database is locked" errors).

    Returns:
        Tuple of (project_endpoint, api_key, model).
    """
    endpoint, api_key = await get_project_endpoint(db)
    master = await config_service.get_master_config(db)
    from app.config import get_settings

    default_model = get_settings().voice_live_default_model
    model = master.model_or_deployment if master else default_model
    return endpoint, api_key, model


async def sync_agent_for_profile(
    db: AsyncSession,
    profile: object,
    template: str | None = None,
    *,
    scenario_id: str | None = None,
    prefetched_endpoint: str | None = None,
    prefetched_key: str | None = None,
    prefetched_model: str | None = None,
) -> dict:
    """High-level helper: create or update an AI Foundry agent for an HCP profile.

    If profile.agent_id is truthy, updates the existing agent (creates new version).
    Otherwise, creates a new agent.

    When scenario_id is provided and the Scenario has an associated Skill,
    the Skill's SOP content is injected into the agent instructions via
    build_skill_augmented_instructions (D-22).

    Pass prefetched_endpoint/prefetched_key/prefetched_model (from prefetch_sync_config)
    to avoid DB reads during an active write transaction (prevents SQLite locking).
    """
    profile_data = profile.to_prompt_dict()

    # Use skill-augmented instructions when scenario_id is available
    if scenario_id:
        try:
            from app.services.prompt_builder import build_skill_augmented_instructions

            instructions = await build_skill_augmented_instructions(
                db, profile_data, scenario_id=scenario_id, template=template
            )
        except Exception as e:
            logger.warning("Skill-augmented instructions failed, using base: %s", e)
            instructions = build_agent_instructions(profile_data, template)
    else:
        instructions = build_agent_instructions(profile_data, template)

    # Use prefetched values or fetch now (fallback for backward compat)
    if prefetched_model is None:
        from app.config import get_settings

        master = await config_service.get_master_config(db)
        prefetched_model = (
            master.model_or_deployment if master else get_settings().voice_live_default_model
        )

    # Build Voice Live metadata if enabled on the profile
    vl_metadata = build_voice_live_metadata(profile)

    # Build knowledge base tools from KB configs (Phase 17).
    # resolve_kb_remote_tool_connections() finds-or-creates the RemoteTool
    # connection required for MCP auth (403 fix: must use RemoteTool
    # connection, not CognitiveSearch connection, for correct credentials type).
    # IMPORTANT: this is intentionally NOT wrapped in a broad try/except.
    # A KB that fails to get an authenticated connection must fail the whole
    # sync (propagating up to hcp_profile_service / _trigger_agent_resync,
    # which set agent_sync_status="failed") rather than silently producing an
    # unauthenticated MCPTool that gets reported as a "synced" agent.
    kb_tools: list = []
    from app.services import knowledge_base_service

    kb_configs = await knowledge_base_service.get_knowledge_configs(db, profile.id)
    if kb_configs:
        rt_map = await knowledge_base_service.resolve_kb_remote_tool_connections(db, kb_configs)
        kb_tools = knowledge_base_service.build_search_tools(kb_configs, rt_map)
        enabled_count = sum(1 for cfg in kb_configs if cfg.is_enabled)
        if len(kb_tools) != enabled_count:
            raise RuntimeError(
                f"Failed to build authenticated MCP tools for all Knowledge Bases "
                f"({len(kb_tools)}/{enabled_count})."
            )

    if profile.agent_id:
        result = await update_agent(
            db,
            profile.agent_id,
            profile.name,
            instructions,
            prefetched_model,
            metadata=vl_metadata,
            tools=kb_tools or None,
            endpoint_override=prefetched_endpoint or "",
            key_override=prefetched_key or "",
        )
    else:
        result = await create_agent(
            db,
            profile.name,
            instructions,
            prefetched_model,
            metadata=vl_metadata,
            tools=kb_tools or None,
            endpoint_override=prefetched_endpoint or "",
            key_override=prefetched_key or "",
        )

    # Store authoritative version from Foundry (RD-7).
    # We use the version returned by create_version, then verify with
    # get_agent_latest_version to handle edge cases (concurrent portal
    # edits, other API callers incrementing version after us).
    agent_name = result.get("id") or result.get("name", "")
    api_version = result.get("version")
    if agent_name:
        try:
            latest_version = await get_agent_latest_version(
                db,
                agent_name,
                endpoint_override=prefetched_endpoint or "",
                key_override=prefetched_key or "",
            )
            profile.agent_version = latest_version
        except Exception:
            # Fallback: use version from create_version response
            profile.agent_version = str(api_version) if api_version else None
    else:
        profile.agent_version = str(api_version) if api_version else None

    return result


async def resync_classic_agent(db: AsyncSession, profile: object) -> bool:
    """Migrate a classic Foundry Agent (asst_* id) to a hosted agent (D-05).

    No-op (returns False immediately, no network call) if profile.agent_id
    does not start with "asst_" -- covers both "never synced" (empty id)
    and "already hosted" profiles.

    On success: profile.agent_id/agent_version/agent_sync_status/agent_sync_error
    are updated in place and flushed; returns True.
    On failure: the original asst_* agent_id is restored (never left blank/
    orphaned), agent_sync_status is set to "failed" with the error recorded,
    flushed, and the function returns False (does not raise -- callers decide
    how to react, e.g. Plan 29-03's voice_live_websocket.py treats a False
    return the same as "not synced" and rejects the connection per D-08).
    """
    old_agent_id = getattr(profile, "agent_id", "") or ""
    if not old_agent_id.startswith("asst_"):
        return False

    profile.agent_id = ""  # forces sync_agent_for_profile's create_agent (hosted) branch
    profile.agent_sync_status = "pending"
    await db.flush()

    try:
        endpoint, api_key, model = await prefetch_sync_config(db)
        result = await sync_agent_for_profile(
            db,
            profile,
            prefetched_endpoint=endpoint,
            prefetched_key=api_key,
            prefetched_model=model,
        )
        profile.agent_id = result.get("id", "")
        profile.agent_version = str(result.get("version", ""))
        profile.agent_sync_status = "synced"
        profile.agent_sync_error = ""
        await db.flush()
        logger.info(
            "resync_classic_agent: migrated classic agent %s -> hosted agent %s (profile %s)",
            old_agent_id,
            profile.agent_id,
            getattr(profile, "id", "?"),
        )
        return True
    except Exception as e:
        profile.agent_id = old_agent_id
        profile.agent_sync_status = "failed"
        profile.agent_sync_error = str(e)[:500]
        await db.flush()
        logger.error(
            "resync_classic_agent: failed to migrate classic agent %s (profile %s): %s",
            old_agent_id,
            getattr(profile, "id", "?"),
            e,
        )
        return False


# ---------------------------------------------------------------------------
# Portal URL discovery — derive from connections API, no extra env vars needed
# ---------------------------------------------------------------------------

_portal_url_cache: dict | None = None


async def get_portal_url_components(db: AsyncSession) -> dict:
    """Discover Azure Portal URL components from the connections API.

    Parses the ARM resource ID from any connection to extract:
    - subscription_hash (base64url of subscription UUID bytes)
    - resource_group
    - resource_name
    - project_name

    Results are cached for the lifetime of the process.
    """
    import base64
    import re
    import uuid

    global _portal_url_cache
    if _portal_url_cache is not None:
        return _portal_url_cache

    try:
        project_endpoint, api_key = await get_project_endpoint(db)
        client = _get_project_client(project_endpoint, api_key)

        # List connections — we only need one to extract the ARM resource ID
        connections = await asyncio.to_thread(client.connections.list)
        for conn in connections:
            conn_id = conn.get("id", "")
            # ARM ID format:
            # /subscriptions/{sub}/resourceGroups/{rg}/providers/
            # .../accounts/{name}/projects/{proj}/...
            match = re.search(
                r"/subscriptions/([^/]+)/resourceGroups/([^/]+)"
                r"/providers/[^/]+/[^/]+/([^/]+)/projects/([^/]+)",
                conn_id,
            )
            if match:
                sub_id, rg, resource_name, project_name = match.groups()
                # Convert subscription UUID to base64url hash (no padding)
                sub_uuid = uuid.UUID(sub_id)
                sub_hash = base64.urlsafe_b64encode(sub_uuid.bytes).rstrip(b"=").decode()

                _portal_url_cache = {
                    "subscription_id": sub_id,
                    "subscription_hash": sub_hash,
                    "resource_group": rg,
                    "resource_name": resource_name,
                    "project_name": project_name,
                }
                logger.info("Portal URL components discovered from connections API")
                return _portal_url_cache

        logger.warning("No connection with ARM resource ID found")
    except Exception as e:
        logger.warning("Failed to discover portal URL components: %s", e)

    _portal_url_cache = {}
    return _portal_url_cache


async def get_agent_latest_version(
    db: AsyncSession,
    agent_name: str,
    *,
    endpoint_override: str = "",
    key_override: str = "",
) -> str:
    """Query Azure for the latest version of an agent.

    Returns the latest version string, or "1" as fallback.
    Pass endpoint_override/key_override to skip DB lookup (avoids SQLite locking).
    """
    try:
        if endpoint_override:
            project_endpoint, api_key = endpoint_override, key_override
        else:
            project_endpoint, api_key = await get_project_endpoint(db)
        client = _get_project_client(project_endpoint, api_key)

        agent = await asyncio.to_thread(client.agents.get, agent_name=agent_name)
        latest = agent.versions.get("latest", {})
        version = str(latest.get("version", "1"))
        logger.info("Agent %s latest version: %s", agent_name, version)
        return version
    except Exception as e:
        logger.warning("Failed to get latest version for agent %s: %s", agent_name, e)
        return "1"
