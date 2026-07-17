"""Unit tests for agent_sync_service: instruction builder + AI Foundry SDK wrapper."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# --- Test 1: build_agent_instructions with complete profile data ---
def test_build_agent_instructions_complete_profile():
    """build_agent_instructions returns formatted string with profile fields."""
    from app.services.agent_sync_service import build_agent_instructions

    profile_data = {
        "name": "Dr. Chen Wei",
        "specialty": "Oncology",
        "hospital": "Beijing Hospital",
        "title": "Chief Physician",
        "personality_type": "analytical",
        "emotional_state": 50,
        "communication_style": 30,
        "expertise_areas": ["lung cancer", "immunotherapy"],
        "prescribing_habits": "Evidence-based, prefers clinical trials",
        "concerns": "Drug efficacy and safety data",
        "objections": ["cost concerns", "limited data"],
        "probe_topics": ["clinical trial results", "mechanism of action"],
        "difficulty": "hard",
    }

    result = build_agent_instructions(profile_data)

    assert "Dr. Chen Wei" in result
    assert "Oncology" in result
    assert "analytical" in result
    assert "Beijing Hospital" in result
    assert "Chief Physician" in result


# --- Test 2: build_agent_instructions joins list fields ---
def test_build_agent_instructions_joins_list_fields():
    """build_agent_instructions converts lists to comma-separated strings."""
    from app.services.agent_sync_service import build_agent_instructions

    profile_data = {
        "name": "Dr. Li",
        "specialty": "Cardiology",
        "hospital": "",
        "title": "",
        "personality_type": "friendly",
        "emotional_state": 20,
        "communication_style": 80,
        "expertise_areas": ["heart failure", "arrhythmia", "valvular disease"],
        "prescribing_habits": "",
        "concerns": "",
        "objections": ["price", "side effects"],
        "probe_topics": ["dosing", "interactions"],
        "difficulty": "medium",
    }

    result = build_agent_instructions(profile_data)

    assert "heart failure, arrhythmia, valvular disease" in result
    assert "price, side effects" in result
    assert "dosing, interactions" in result


# --- Test 3: build_agent_instructions with custom template ---
def test_build_agent_instructions_custom_template():
    """build_agent_instructions uses provided custom template."""
    from app.services.agent_sync_service import build_agent_instructions

    custom_template = "Hello, I am {name} from {specialty}. Style: {communication_style_desc}."
    profile_data = {
        "name": "Dr. Wang",
        "specialty": "Neurology",
        "communication_style": 30,
        "emotional_state": 50,
    }

    result = build_agent_instructions(profile_data, template=custom_template)

    assert "Dr. Wang" in result
    assert "Neurology" in result
    assert "direct" in result


# --- Test 4: build_agent_instructions with missing optional fields ---
def test_build_agent_instructions_missing_fields():
    """build_agent_instructions uses safe defaults for missing fields."""
    from app.services.agent_sync_service import build_agent_instructions

    profile_data = {
        "name": "Dr. Minimal",
        "specialty": "General",
    }

    result = build_agent_instructions(profile_data)

    assert "Dr. Minimal" in result
    assert "General" in result


def test_build_agent_instructions_defaults_to_chinese():
    """Default HCP agent instructions prefer Simplified Chinese responses."""
    from app.services.agent_sync_service import build_agent_instructions

    result = build_agent_instructions({"name": "Dr. Li", "specialty": "Oncology"})

    assert "Language rules" in result
    assert "Default to Simplified Chinese" in result
    assert "Only switch to English" in result


# --- Test 5: build_agent_instructions emotional state descriptors ---
def test_build_agent_instructions_emotional_descriptors():
    """build_agent_instructions sets correct emotional descriptors."""
    from app.services.agent_sync_service import build_agent_instructions

    # Calm
    r1 = build_agent_instructions({"name": "A", "specialty": "B", "emotional_state": 10})
    assert "calm and open" in r1

    # Neutral
    r2 = build_agent_instructions({"name": "A", "specialty": "B", "emotional_state": 50})
    assert "neutral" in r2

    # Resistant
    r3 = build_agent_instructions({"name": "A", "specialty": "B", "emotional_state": 80})
    assert "resistant" in r3

    # Non-numeric
    r4 = build_agent_instructions({"name": "A", "specialty": "B", "emotional_state": "high"})
    assert "neutral" in r4

    # Non-numeric comm style
    r5 = build_agent_instructions({"name": "A", "specialty": "B", "communication_style": "auto"})
    assert "moderate" in r5


# --- Test 6: get_project_endpoint derives correct URL ---
@pytest.mark.asyncio
async def test_get_project_endpoint():
    """get_project_endpoint derives URL from master config default_project."""
    from app.services.agent_sync_service import get_project_endpoint

    mock_db = AsyncMock()

    mock_master = MagicMock()
    mock_master.default_project = "my-project"

    with (
        patch(
            "app.services.agent_sync_service.config_service.get_effective_endpoint",
            new_callable=AsyncMock,
            return_value="https://my-foundry.services.ai.azure.com",
        ),
        patch(
            "app.services.agent_sync_service.config_service.get_effective_key",
            new_callable=AsyncMock,
            return_value="test-api-key-123",
        ),
        patch(
            "app.services.agent_sync_service.config_service.get_master_config",
            new_callable=AsyncMock,
            return_value=mock_master,
        ),
    ):
        endpoint, key = await get_project_endpoint(mock_db)

    assert "my-project" in endpoint
    assert "api/projects" in endpoint
    assert key == "test-api-key-123"


# --- Test 7: get_project_endpoint with existing project path ---
@pytest.mark.asyncio
async def test_get_project_endpoint_existing_path():
    """get_project_endpoint preserves existing /api/projects/ path."""
    from app.services.agent_sync_service import get_project_endpoint

    mock_db = AsyncMock()
    mock_master = MagicMock()
    mock_master.default_project = ""

    with (
        patch(
            "app.services.agent_sync_service.config_service.get_effective_endpoint",
            new_callable=AsyncMock,
            return_value="https://foundry.azure.com/api/projects/existing-proj",
        ),
        patch(
            "app.services.agent_sync_service.config_service.get_effective_key",
            new_callable=AsyncMock,
            return_value="key",
        ),
        patch(
            "app.services.agent_sync_service.config_service.get_master_config",
            new_callable=AsyncMock,
            return_value=mock_master,
        ),
        patch(
            "app.services.agent_sync_service.config_service.get_config",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        endpoint, _ = await get_project_endpoint(mock_db)

    assert endpoint == "https://foundry.azure.com/api/projects/existing-proj"


# --- Test 8: get_project_endpoint env var fallback ---
@pytest.mark.asyncio
async def test_get_project_endpoint_env_var_fallback():
    """get_project_endpoint uses AZURE_FOUNDRY_DEFAULT_PROJECT env var as fallback."""
    from app.services.agent_sync_service import get_project_endpoint

    mock_db = AsyncMock()
    mock_master = MagicMock()
    mock_master.default_project = ""  # no DB project → fall through to voice_live then env

    mock_config = MagicMock()
    mock_config.model_or_deployment = "gpt-4o-realtime"  # model mode, no project

    mock_settings = MagicMock()
    mock_settings.azure_foundry_default_project = "avarda-demo-prj"

    with (
        patch(
            "app.services.agent_sync_service.config_service.get_effective_endpoint",
            new_callable=AsyncMock,
            return_value="https://foundry.azure.com",
        ),
        patch(
            "app.services.agent_sync_service.config_service.get_effective_key",
            new_callable=AsyncMock,
            return_value="key",
        ),
        patch(
            "app.services.agent_sync_service.config_service.get_master_config",
            new_callable=AsyncMock,
            return_value=mock_master,
        ),
        patch(
            "app.services.agent_sync_service.config_service.get_config",
            new_callable=AsyncMock,
            return_value=mock_config,
        ),
        patch(
            "app.config.get_settings",
            return_value=mock_settings,
        ),
    ):
        endpoint, _ = await get_project_endpoint(mock_db)

    assert endpoint == "https://foundry.azure.com/api/projects/avarda-demo-prj"


# --- Test 8b: get_project_endpoint bare fallback when no env var ---
@pytest.mark.asyncio
async def test_get_project_endpoint_no_project_no_env():
    """get_project_endpoint falls back to bare endpoint when no project at all."""
    from app.services.agent_sync_service import get_project_endpoint

    mock_db = AsyncMock()
    mock_master = MagicMock()
    mock_master.default_project = ""

    mock_config = MagicMock()
    mock_config.model_or_deployment = "gpt-4o-realtime"

    mock_settings = MagicMock()
    mock_settings.azure_foundry_default_project = ""

    with (
        patch(
            "app.services.agent_sync_service.config_service.get_effective_endpoint",
            new_callable=AsyncMock,
            return_value="https://foundry.azure.com",
        ),
        patch(
            "app.services.agent_sync_service.config_service.get_effective_key",
            new_callable=AsyncMock,
            return_value="key",
        ),
        patch(
            "app.services.agent_sync_service.config_service.get_master_config",
            new_callable=AsyncMock,
            return_value=mock_master,
        ),
        patch(
            "app.services.agent_sync_service.config_service.get_config",
            new_callable=AsyncMock,
            return_value=mock_config,
        ),
        patch(
            "app.config.get_settings",
            return_value=mock_settings,
        ),
    ):
        endpoint, _ = await get_project_endpoint(mock_db)

    assert endpoint == "https://foundry.azure.com"


# --- Test 9: create_agent calls SDK create_version and returns agent name ---
@pytest.mark.asyncio
async def test_create_agent():
    """create_agent calls SDK agents.create_version and returns agent name as id."""
    from app.services.agent_sync_service import create_agent

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.name = "Test-Agent"
    mock_result.version = "1"

    mock_client = MagicMock()
    mock_client.agents.create_version.return_value = mock_result

    with (
        patch(
            "app.services.agent_sync_service.get_project_endpoint",
            new_callable=AsyncMock,
            return_value=("https://foundry/api/projects/proj", "key"),
        ),
        patch(
            "app.services.agent_sync_service._get_project_client",
            return_value=mock_client,
        ),
    ):
        result = await create_agent(mock_db, "Test Agent", "Instructions", "gpt-4o")

    assert result["id"] == "Test-Agent"
    assert result["name"] == "Test-Agent"
    assert result["version"] == "1"
    mock_client.agents.create_version.assert_called_once()


# --- Test 10: update_agent calls SDK create_version (new version) ---
@pytest.mark.asyncio
async def test_update_agent():
    """update_agent calls SDK agents.create_version with existing agent_name."""
    from app.services.agent_sync_service import update_agent

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.name = "existing-agent"
    mock_result.version = "2"

    mock_client = MagicMock()
    mock_client.agents.create_version.return_value = mock_result

    with (
        patch(
            "app.services.agent_sync_service.get_project_endpoint",
            new_callable=AsyncMock,
            return_value=("https://foundry/api/projects/proj", "key"),
        ),
        patch(
            "app.services.agent_sync_service._get_project_client",
            return_value=mock_client,
        ),
    ):
        result = await update_agent(mock_db, "existing-agent", "Updated", "New instructions")

    assert result["id"] == "existing-agent"
    assert result["version"] == "2"
    mock_client.agents.create_version.assert_called_once()
    call_kwargs = mock_client.agents.create_version.call_args
    assert call_kwargs[1]["agent_name"] == "existing-agent"


# --- Test 11: delete_agent calls SDK agents.delete and returns True ---
@pytest.mark.asyncio
async def test_delete_agent():
    """delete_agent calls SDK agents.delete and returns True."""
    from app.services.agent_sync_service import delete_agent

    mock_db = AsyncMock()
    mock_client = MagicMock()
    mock_client.agents.delete.return_value = None  # success

    with (
        patch(
            "app.services.agent_sync_service.get_project_endpoint",
            new_callable=AsyncMock,
            return_value=("https://foundry/api/projects/proj", "key"),
        ),
        patch(
            "app.services.agent_sync_service._get_project_client",
            return_value=mock_client,
        ),
    ):
        result = await delete_agent(mock_db, "agent-to-delete")

    assert result is True
    mock_client.agents.delete.assert_called_once_with(agent_name="agent-to-delete")


# --- Test 12: delete_agent returns False on error ---
@pytest.mark.asyncio
async def test_delete_agent_returns_false_on_error():
    """delete_agent returns False when SDK raises exception."""
    from app.services.agent_sync_service import delete_agent

    mock_db = AsyncMock()
    mock_client = MagicMock()
    mock_client.agents.delete.side_effect = Exception("Not found")

    with (
        patch(
            "app.services.agent_sync_service.get_project_endpoint",
            new_callable=AsyncMock,
            return_value=("https://foundry/api/projects/proj", "key"),
        ),
        patch(
            "app.services.agent_sync_service._get_project_client",
            return_value=mock_client,
        ),
    ):
        result = await delete_agent(mock_db, "nonexistent-agent")

    assert result is False


# --- Test 13: sync_agent_for_profile creates when no agent_id ---
@pytest.mark.asyncio
async def test_sync_agent_for_profile_creates_when_no_agent_id():
    """sync_agent_for_profile creates agent when agent_id is empty."""
    from app.services.agent_sync_service import sync_agent_for_profile

    mock_db = AsyncMock()
    mock_profile = MagicMock()
    mock_profile.agent_id = ""
    mock_profile.name = "Dr. New"
    mock_profile.voice_live_enabled = False
    mock_profile.voice_live_instance = None  # no VL instance
    mock_profile.voice_live_model = "gpt-4o"
    mock_profile.voice_name = "en-US-AvaNeural"
    mock_profile.voice_type = "azure-standard"
    mock_profile.voice_temperature = 0.9
    mock_profile.voice_custom = False
    mock_profile.avatar_character = "lori"
    mock_profile.avatar_style = "casual"
    mock_profile.avatar_customized = False
    mock_profile.turn_detection_type = "server_vad"
    mock_profile.noise_suppression = False
    mock_profile.echo_cancellation = False
    mock_profile.eou_detection = False
    mock_profile.recognition_language = "auto"
    mock_profile.to_prompt_dict.return_value = {
        "name": "Dr. New",
        "specialty": "Oncology",
    }

    mock_master = MagicMock()
    mock_master.model_or_deployment = "gpt-4o"

    with (
        patch(
            "app.services.agent_sync_service.config_service.get_master_config",
            new_callable=AsyncMock,
            return_value=mock_master,
        ),
        patch(
            "app.services.agent_sync_service.create_agent",
            new_callable=AsyncMock,
            return_value={
                "id": "asst_created",
                "name": "Dr. New",
                "version": "1",
                "model": "gpt-4o",
            },
        ) as mock_create,
        patch(
            "app.services.agent_sync_service.update_agent",
            new_callable=AsyncMock,
        ) as mock_update,
        patch(
            "app.services.knowledge_base_service.get_knowledge_configs",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        result = await sync_agent_for_profile(mock_db, mock_profile)

    assert result["id"] == "asst_created"
    mock_create.assert_called_once()
    mock_update.assert_not_called()


# --- Test 14: sync_agent_for_profile updates when agent_id exists ---
@pytest.mark.asyncio
async def test_sync_agent_for_profile_updates_when_agent_id_exists():
    """sync_agent_for_profile updates agent when agent_id is set."""
    from app.services.agent_sync_service import sync_agent_for_profile

    mock_db = AsyncMock()
    mock_profile = MagicMock()
    mock_profile.agent_id = "asst_existing"
    mock_profile.name = "Dr. Existing"
    mock_profile.voice_live_enabled = False
    mock_profile.voice_live_instance = None
    mock_profile.voice_live_model = "gpt-4o"
    mock_profile.voice_name = "en-US-AvaNeural"
    mock_profile.voice_type = "azure-standard"
    mock_profile.voice_temperature = 0.9
    mock_profile.voice_custom = False
    mock_profile.avatar_character = "lori"
    mock_profile.avatar_style = "casual"
    mock_profile.avatar_customized = False
    mock_profile.turn_detection_type = "server_vad"
    mock_profile.noise_suppression = False
    mock_profile.echo_cancellation = False
    mock_profile.eou_detection = False
    mock_profile.recognition_language = "auto"
    mock_profile.to_prompt_dict.return_value = {
        "name": "Dr. Existing",
        "specialty": "Cardiology",
    }

    mock_master = MagicMock()
    mock_master.model_or_deployment = "gpt-4o"

    with (
        patch(
            "app.services.agent_sync_service.config_service.get_master_config",
            new_callable=AsyncMock,
            return_value=mock_master,
        ),
        patch(
            "app.services.agent_sync_service.create_agent",
            new_callable=AsyncMock,
        ) as mock_create,
        patch(
            "app.services.agent_sync_service.update_agent",
            new_callable=AsyncMock,
            return_value={
                "id": "asst_existing",
                "name": "Dr. Existing",
                "version": "2",
                "model": "gpt-4o",
            },
        ) as mock_update,
        patch(
            "app.services.knowledge_base_service.get_knowledge_configs",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        result = await sync_agent_for_profile(mock_db, mock_profile)

    assert result["id"] == "asst_existing"
    mock_update.assert_called_once()
    mock_create.assert_not_called()


# --- Test 15: sync_agent_for_profile with no master config ---
@pytest.mark.asyncio
async def test_sync_agent_for_profile_no_master_config():
    """sync_agent_for_profile defaults to voice_live_default_model with no master config."""
    from app.config import get_settings
    from app.services.agent_sync_service import sync_agent_for_profile

    default_model = get_settings().voice_live_default_model

    mock_db = AsyncMock()
    mock_profile = MagicMock()
    mock_profile.agent_id = ""
    mock_profile.name = "Dr. Default"
    mock_profile.voice_live_enabled = False
    mock_profile.voice_live_instance = None
    mock_profile.voice_live_model = "gpt-4o"
    mock_profile.voice_name = "en-US-AvaNeural"
    mock_profile.voice_type = "azure-standard"
    mock_profile.voice_temperature = 0.9
    mock_profile.voice_custom = False
    mock_profile.avatar_character = "lori"
    mock_profile.avatar_style = "casual"
    mock_profile.avatar_customized = False
    mock_profile.turn_detection_type = "server_vad"
    mock_profile.noise_suppression = False
    mock_profile.echo_cancellation = False
    mock_profile.eou_detection = False
    mock_profile.recognition_language = "auto"
    mock_profile.to_prompt_dict.return_value = {"name": "Dr. Default", "specialty": "GP"}

    with (
        patch(
            "app.services.agent_sync_service.config_service.get_master_config",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.services.agent_sync_service.create_agent",
            new_callable=AsyncMock,
            return_value={
                "id": "asst_default",
                "name": "Dr. Default",
                "version": "1",
                "model": default_model,
            },
        ) as mock_create,
        patch(
            "app.services.knowledge_base_service.get_knowledge_configs",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        result = await sync_agent_for_profile(mock_db, mock_profile)

    assert result["id"] == "asst_default"
    # Verify model defaults to settings value (not hardcoded)
    call_args = mock_create.call_args
    actual_model = call_args[1].get("model", call_args[0][3] if len(call_args[0]) > 3 else None)
    assert actual_model == default_model


# --- Test 16: three HCP profiles sync to agents end-to-end ---
@pytest.mark.asyncio
async def test_three_profiles_sync_to_agents():
    """Three HCP profiles each create an agent via sync_agent_for_profile.

    This is the critical end-to-end scenario: every HCP profile must have
    a corresponding AI Foundry agent after sync.
    """
    from app.services.agent_sync_service import sync_agent_for_profile

    hcp_profiles = [
        {
            "agent_id": "",
            "name": "Dr. Chen Wei",
            "prompt_data": {
                "name": "Dr. Chen Wei",
                "specialty": "Oncology",
                "hospital": "Beijing Hospital",
                "title": "Chief Physician",
                "personality_type": "analytical",
                "emotional_state": 50,
                "communication_style": 30,
                "expertise_areas": ["lung cancer", "immunotherapy"],
                "prescribing_habits": "Evidence-based",
                "concerns": "Drug efficacy",
                "objections": ["cost concerns"],
                "probe_topics": ["clinical trial results"],
            },
        },
        {
            "agent_id": "",
            "name": "Dr. Li Ming",
            "prompt_data": {
                "name": "Dr. Li Ming",
                "specialty": "Cardiology",
                "hospital": "Shanghai Heart Center",
                "title": "Senior Physician",
                "personality_type": "friendly",
                "emotional_state": 20,
                "communication_style": 80,
                "expertise_areas": ["heart failure", "arrhythmia"],
                "prescribing_habits": "Conservative",
                "concerns": "Patient safety",
                "objections": ["side effects"],
                "probe_topics": ["dosing"],
            },
        },
        {
            "agent_id": "",
            "name": "Dr. Wang Fang",
            "prompt_data": {
                "name": "Dr. Wang Fang",
                "specialty": "Neurology",
                "hospital": "Guangzhou Medical",
                "title": "Attending Physician",
                "personality_type": "skeptical",
                "emotional_state": 80,
                "communication_style": 40,
                "expertise_areas": ["stroke", "epilepsy"],
                "prescribing_habits": "Guideline-based",
                "concerns": "Long-term outcomes",
                "objections": ["limited data", "compliance"],
                "probe_topics": ["mechanism of action", "safety profile"],
            },
        },
    ]

    agent_counter = 0

    def make_create_agent_side_effect():
        nonlocal agent_counter

        async def _create(*args, **kwargs):
            nonlocal agent_counter
            agent_counter += 1
            name = args[1] if len(args) > 1 else kwargs.get("name", "agent")
            return {
                "id": f"agent-{agent_counter}",
                "name": name,
                "version": "1",
                "model": "gpt-4o",
            }

        return _create

    results = []
    mock_db = AsyncMock()

    for profile_data in hcp_profiles:
        mock_profile = MagicMock()
        mock_profile.agent_id = profile_data["agent_id"]
        mock_profile.name = profile_data["name"]
        mock_profile.voice_live_enabled = False  # skip VL metadata in sync test
        mock_profile.voice_live_instance = None
        mock_profile.voice_live_model = "gpt-4o"
        mock_profile.voice_name = "en-US-AvaNeural"
        mock_profile.voice_type = "azure-standard"
        mock_profile.voice_temperature = 0.9
        mock_profile.voice_custom = False
        mock_profile.avatar_character = "lori"
        mock_profile.avatar_style = "casual"
        mock_profile.avatar_customized = False
        mock_profile.turn_detection_type = "server_vad"
        mock_profile.noise_suppression = False
        mock_profile.echo_cancellation = False
        mock_profile.eou_detection = False
        mock_profile.recognition_language = "auto"
        mock_profile.to_prompt_dict.return_value = profile_data["prompt_data"]

        with (
            patch(
                "app.services.agent_sync_service.create_agent",
                new_callable=AsyncMock,
                side_effect=make_create_agent_side_effect(),
            ),
            patch(
                "app.services.knowledge_base_service.get_knowledge_configs",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = await sync_agent_for_profile(
                mock_db,
                mock_profile,
                prefetched_model="gpt-4o",
            )
            results.append(result)

    # All three must have unique agent IDs
    assert len(results) == 3
    agent_ids = [r["id"] for r in results]
    assert len(set(agent_ids)) == 3, f"Expected 3 unique agent IDs, got: {agent_ids}"
    for r in results:
        assert r["id"], f"Agent ID must not be empty: {r}"
        assert r["model"] == "gpt-4o"


# --- Test 17: three profiles batch sync (create + update + retry) ---
@pytest.mark.asyncio
async def test_three_profiles_mixed_sync_scenarios():
    """Three profiles: one new (create), one existing (update), one failed (retry).

    Verifies that sync_agent_for_profile correctly routes to create vs update
    based on agent_id presence, and all three succeed.
    """
    from app.services.agent_sync_service import sync_agent_for_profile

    mock_db = AsyncMock()

    def _set_inline_voice_fields(mock):
        """Set all inline voice fields on a MagicMock so resolve_voice_config works."""
        mock.voice_live_instance = None
        mock.voice_live_model = "gpt-4o"
        mock.voice_name = "en-US-AvaNeural"
        mock.voice_type = "azure-standard"
        mock.voice_temperature = 0.9
        mock.voice_custom = False
        mock.avatar_character = "lori"
        mock.avatar_style = "casual"
        mock.avatar_customized = False
        mock.turn_detection_type = "server_vad"
        mock.noise_suppression = False
        mock.echo_cancellation = False
        mock.eou_detection = False
        mock.recognition_language = "auto"

    # Profile 1: new (no agent_id)
    p1 = MagicMock()
    p1.agent_id = ""
    p1.name = "Dr. New"
    p1.voice_live_enabled = False
    _set_inline_voice_fields(p1)
    p1.to_prompt_dict.return_value = {"name": "Dr. New", "specialty": "GP"}

    # Profile 2: existing (has agent_id, should update)
    p2 = MagicMock()
    p2.agent_id = "existing-agent-002"
    p2.name = "Dr. Update"
    p2.voice_live_enabled = False
    _set_inline_voice_fields(p2)
    p2.to_prompt_dict.return_value = {"name": "Dr. Update", "specialty": "Dermatology"}

    # Profile 3: retry (had agent_id but sync_status was failed, treat as update)
    p3 = MagicMock()
    p3.agent_id = "failed-agent-003"
    p3.name = "Dr. Retry"
    p3.voice_live_enabled = False
    _set_inline_voice_fields(p3)
    p3.to_prompt_dict.return_value = {"name": "Dr. Retry", "specialty": "Pediatrics"}

    with (
        patch(
            "app.services.agent_sync_service.create_agent",
            new_callable=AsyncMock,
            return_value={
                "id": "new-agent-001",
                "name": "Dr-New",
                "version": "1",
                "model": "gpt-4o",
            },
        ) as mock_create,
        patch(
            "app.services.agent_sync_service.update_agent",
            new_callable=AsyncMock,
            side_effect=[
                {
                    "id": "existing-agent-002",
                    "name": "Dr-Update",
                    "version": "3",
                    "model": "gpt-4o",
                },
                {
                    "id": "failed-agent-003",
                    "name": "Dr-Retry",
                    "version": "2",
                    "model": "gpt-4o",
                },
            ],
        ) as mock_update,
        patch(
            "app.services.knowledge_base_service.get_knowledge_configs",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        r1 = await sync_agent_for_profile(mock_db, p1, prefetched_model="gpt-4o")
        r2 = await sync_agent_for_profile(mock_db, p2, prefetched_model="gpt-4o")
        r3 = await sync_agent_for_profile(mock_db, p3, prefetched_model="gpt-4o")

    # Verify create called once for new profile
    mock_create.assert_called_once()
    assert r1["id"] == "new-agent-001"

    # Verify update called twice (existing + retry)
    assert mock_update.call_count == 2
    assert r2["id"] == "existing-agent-002"
    assert r3["id"] == "failed-agent-003"

    # All three synced successfully
    all_ids = {r1["id"], r2["id"], r3["id"]}
    assert len(all_ids) == 3


# --- Test 18: create_agent builds correct endpoint with env var project ---
@pytest.mark.asyncio
async def test_create_agent_uses_project_endpoint():
    """create_agent uses full project endpoint including /api/projects/."""
    from app.services.agent_sync_service import create_agent

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.name = "Dr-Chen-Wei"
    mock_result.version = "1"

    mock_client = MagicMock()
    mock_client.agents.create_version.return_value = mock_result

    with (
        patch(
            "app.services.agent_sync_service.get_project_endpoint",
            new_callable=AsyncMock,
            return_value=(
                "https://foundry.azure.com/api/projects/avarda-demo-prj",
                "test-key",
            ),
        ),
        patch(
            "app.services.agent_sync_service._get_project_client",
            return_value=mock_client,
        ) as mock_get_client,
    ):
        result = await create_agent(mock_db, "Dr. Chen Wei", "Instructions", "gpt-4o")

    assert result["id"] == "Dr-Chen-Wei"
    # Verify _get_project_client received the full project endpoint and key
    mock_get_client.assert_called_once_with(
        "https://foundry.azure.com/api/projects/avarda-demo-prj",
        "test-key",
    )


# ===========================================================================
# Real-data integration tests — real DB + real Azure SDK (no mocking)
# Covers get_project_endpoint with seeded ServiceConfig,
# sync_agent_for_profile with real HcpProfile objects and real Azure agents.
# ===========================================================================


def _get_real_azure_config() -> tuple[str, str, str]:
    """Read Azure AI Foundry config from .env. Returns (endpoint, api_key, project)."""
    import os

    from dotenv import load_dotenv

    load_dotenv()
    endpoint = os.getenv("AZURE_FOUNDRY_ENDPOINT", "").rstrip("/")
    api_key = os.getenv("AZURE_FOUNDRY_API_KEY", "")
    project = os.getenv("AZURE_FOUNDRY_DEFAULT_PROJECT", "")
    return endpoint, api_key, project


def _has_real_azure_config() -> bool:
    """Check if real Azure credentials are configured in .env."""
    endpoint, api_key, project = _get_real_azure_config()
    return bool(endpoint and api_key and project)


_skip_no_creds_integration = pytest.mark.skipif(
    not _has_real_azure_config(),
    reason="No Azure AI Foundry credentials in .env",
)

# Agents created by TestRealAgentSyncOperations, for cleanup
_integration_agents: list[str] = []


class TestRealGetProjectEndpoint:
    """Real-data tests for get_project_endpoint using seeded ServiceConfig in the test DB.

    These replace mock-based tests #1-4 with real database operations.
    The test DB is in-memory SQLite (created by conftest.py fixtures).
    """

    @pytest.mark.asyncio
    async def test_get_project_endpoint_from_master_config(self, db_session):
        """get_project_endpoint resolves project from master config default_project (real DB)."""
        from app.models.service_config import ServiceConfig
        from app.services.agent_sync_service import get_project_endpoint
        from app.utils.encryption import encrypt_value

        # Seed a master AI Foundry config row
        master = ServiceConfig(
            service_name="ai_foundry",
            display_name="Azure AI Foundry",
            endpoint="https://my-foundry.services.ai.azure.com",
            api_key_encrypted=encrypt_value("test-api-key-123"),
            default_project="my-project",
            is_master=True,
            is_active=True,
            updated_by="test",
        )
        db_session.add(master)
        await db_session.flush()

        endpoint, key = await get_project_endpoint(db_session)

        assert "my-project" in endpoint
        assert "api/projects" in endpoint
        assert key == "test-api-key-123"

    @pytest.mark.asyncio
    async def test_get_project_endpoint_existing_path_in_endpoint(self, db_session):
        """get_project_endpoint preserves existing /api/projects/ path from per-service config."""
        from app.models.service_config import ServiceConfig
        from app.services.agent_sync_service import get_project_endpoint
        from app.utils.encryption import encrypt_value

        # Seed a per-service config with endpoint that already has /api/projects/
        per_service = ServiceConfig(
            service_name="azure_voice_live",
            display_name="Voice Live",
            endpoint="https://foundry.azure.com/api/projects/existing-proj",
            api_key_encrypted=encrypt_value("key-for-vl"),
            is_master=False,
            is_active=True,
            updated_by="test",
        )
        db_session.add(per_service)
        await db_session.flush()

        endpoint, key = await get_project_endpoint(db_session)

        # The endpoint already has /api/projects/ so it should be returned as-is
        assert endpoint == "https://foundry.azure.com/api/projects/existing-proj"
        assert key == "key-for-vl"

    @pytest.mark.asyncio
    async def test_get_project_endpoint_env_var_fallback(self, db_session):
        """get_project_endpoint falls back to AZURE_FOUNDRY_DEFAULT_PROJECT env var."""
        from unittest.mock import patch

        from app.models.service_config import ServiceConfig
        from app.services.agent_sync_service import get_project_endpoint
        from app.utils.encryption import encrypt_value

        # Seed master config with NO default_project
        master = ServiceConfig(
            service_name="ai_foundry",
            display_name="Azure AI Foundry",
            endpoint="https://foundry.azure.com",
            api_key_encrypted=encrypt_value("key"),
            default_project="",
            is_master=True,
            is_active=True,
            updated_by="test",
        )
        db_session.add(master)
        await db_session.flush()

        # Patch settings to provide env var project
        mock_settings = MagicMock()
        mock_settings.azure_foundry_default_project = "env-var-project"
        with patch("app.config.get_settings", return_value=mock_settings):
            endpoint, _ = await get_project_endpoint(db_session)

        assert endpoint == "https://foundry.azure.com/api/projects/env-var-project"

    @pytest.mark.asyncio
    async def test_get_project_endpoint_no_project_no_env(self, db_session):
        """get_project_endpoint falls back to bare endpoint when no project configured."""
        from unittest.mock import patch

        from app.models.service_config import ServiceConfig
        from app.services.agent_sync_service import get_project_endpoint
        from app.utils.encryption import encrypt_value

        # Seed master config with NO default_project
        master = ServiceConfig(
            service_name="ai_foundry",
            display_name="Azure AI Foundry",
            endpoint="https://foundry.azure.com",
            api_key_encrypted=encrypt_value("key"),
            default_project="",
            is_master=True,
            is_active=True,
            updated_by="test",
        )
        db_session.add(master)
        await db_session.flush()

        # Patch settings to provide empty env var project
        mock_settings = MagicMock()
        mock_settings.azure_foundry_default_project = ""
        with patch("app.config.get_settings", return_value=mock_settings):
            endpoint, _ = await get_project_endpoint(db_session)

        assert endpoint == "https://foundry.azure.com"


@_skip_no_creds_integration
class TestRealAgentSyncOperations:
    """Real Azure integration tests for sync_agent_for_profile using real DB + real SDK.

    Uses real Azure AI Foundry credentials from .env.
    Creates real HcpProfile objects in the test DB and syncs them to real agents.
    Cleans up created agents after tests.
    """

    @staticmethod
    async def _seed_user(db_session) -> str:
        """Create a test user in the DB and return its id."""
        from app.models.user import User

        user = User(
            username="test-agent-sync-user",
            email="agent-sync@test.com",
            hashed_password="not-real",
            full_name="Test User",
            role="admin",
        )
        db_session.add(user)
        await db_session.flush()
        return user.id

    @staticmethod
    async def _seed_master_config(db_session):
        """Seed the master AI Foundry config row from real .env credentials."""
        from app.models.service_config import ServiceConfig
        from app.utils.encryption import encrypt_value

        endpoint, api_key, project = _get_real_azure_config()
        master = ServiceConfig(
            service_name="ai_foundry",
            display_name="Azure AI Foundry",
            endpoint=endpoint,
            api_key_encrypted=encrypt_value(api_key),
            default_project=project,
            is_master=True,
            is_active=True,
            updated_by="test",
        )
        db_session.add(master)
        await db_session.flush()

    @staticmethod
    async def _create_profile(db_session, user_id: str, **overrides):
        """Create an HcpProfile in the DB with defaults + overrides."""
        import json

        from app.models.hcp_profile import HcpProfile

        defaults = {
            "name": "Dr. Test",
            "specialty": "Oncology",
            "hospital": "Test Hospital",
            "title": "Physician",
            "personality_type": "analytical",
            "emotional_state": 50,
            "communication_style": 30,
            "expertise_areas": json.dumps(["testing"]),
            "prescribing_habits": "Evidence-based",
            "concerns": "Drug efficacy",
            "objections": json.dumps(["cost concerns"]),
            "probe_topics": json.dumps(["clinical trials"]),
            "difficulty": "medium",
            "agent_id": "",
            "voice_live_enabled": True,
            "voice_live_model": "gpt-4o",
            "voice_name": "en-US-AvaNeural",
            "voice_type": "azure-standard",
            "voice_temperature": 0.9,
            "voice_custom": False,
            "avatar_character": "lori",
            "avatar_style": "casual",
            "avatar_customized": False,
            "turn_detection_type": "server_vad",
            "noise_suppression": False,
            "echo_cancellation": False,
            "eou_detection": False,
            "recognition_language": "auto",
            "created_by": user_id,
        }
        defaults.update(overrides)
        profile = HcpProfile(**defaults)
        db_session.add(profile)
        await db_session.flush()
        return profile

    @pytest.mark.asyncio
    async def test_sync_creates_agent_for_new_profile(self, db_session):
        """[REAL DB+SDK] sync_agent_for_profile creates agent when profile has no agent_id."""
        from app.services.agent_sync_service import sync_agent_for_profile

        await self._seed_master_config(db_session)
        user_id = await self._seed_user(db_session)
        profile = await self._create_profile(
            db_session,
            user_id,
            name="UT-Real-Dr-Create",
            specialty="Oncology",
        )

        result = await sync_agent_for_profile(db_session, profile)

        assert result["id"], "Agent ID must not be empty"
        assert result["name"], "Agent name must not be empty"
        assert result["version"], "Agent version must not be empty"
        _integration_agents.append(result["id"])

    @pytest.mark.asyncio
    async def test_sync_updates_agent_when_agent_id_exists(self, db_session):
        """[REAL DB+SDK] sync_agent_for_profile updates when profile has existing agent_id."""
        from app.services.agent_sync_service import sync_agent_for_profile

        await self._seed_master_config(db_session)
        user_id = await self._seed_user(db_session)

        # First: create an agent via sync
        profile = await self._create_profile(
            db_session,
            user_id,
            name="UT-Real-Dr-Update",
            specialty="Cardiology",
        )
        result1 = await sync_agent_for_profile(db_session, profile)
        _integration_agents.append(result1["id"])

        # Set the agent_id on the profile (as would happen in the real app)
        profile.agent_id = result1["id"]
        await db_session.flush()

        # Second: update via sync (should create new version, not new agent)
        result2 = await sync_agent_for_profile(db_session, profile)

        assert result2["id"] == result1["id"], "Agent ID should not change on update"
        # Version should be non-empty (Azure may or may not increment version numbers)
        assert result2["version"], "Updated agent must have a version"

    @pytest.mark.asyncio
    async def test_sync_no_master_config_uses_default_model(self, db_session):
        """[REAL DB+SDK] sync_agent_for_profile uses default model when no master config."""
        # Do NOT seed master config — but we still need real endpoint/key
        endpoint, api_key, project = _get_real_azure_config()
        project_endpoint = f"{endpoint}/api/projects/{project}"

        user_id = await self._seed_user(db_session)
        profile = await self._create_profile(
            db_session,
            user_id,
            name="UT-Real-Dr-NoMaster",
            specialty="GP",
        )

        # Use prefetched values to bypass DB config lookup
        from app.config import get_settings
        from app.services.agent_sync_service import sync_agent_for_profile

        default_model = get_settings().voice_live_default_model

        result = await sync_agent_for_profile(
            db_session,
            profile,
            prefetched_endpoint=project_endpoint,
            prefetched_key=api_key,
            prefetched_model=default_model,
        )

        assert result["id"], "Agent ID must not be empty"
        assert result["model"] == default_model
        _integration_agents.append(result["id"])

    @pytest.mark.asyncio
    async def test_three_profiles_sync_create_agents(self, db_session):
        """[REAL DB+SDK] Three HCP profiles create three separate agents via sync."""
        from app.services.agent_sync_service import sync_agent_for_profile

        await self._seed_master_config(db_session)
        user_id = await self._seed_user(db_session)

        profiles_data = [
            {"name": "UT-Real-Dr-Chen", "specialty": "Oncology"},
            {"name": "UT-Real-Dr-Li", "specialty": "Cardiology"},
            {"name": "UT-Real-Dr-Wang", "specialty": "Neurology"},
        ]

        results = []
        for pd in profiles_data:
            profile = await self._create_profile(db_session, user_id, **pd)
            result = await sync_agent_for_profile(db_session, profile)
            results.append(result)
            _integration_agents.append(result["id"])

        assert len(results) == 3
        agent_ids = [r["id"] for r in results]
        assert len(set(agent_ids)) == 3, f"Expected 3 unique agent IDs, got: {agent_ids}"
        for r in results:
            assert r["id"], f"Agent ID must not be empty: {r}"
            assert r["version"], f"Agent version must not be empty: {r}"

    @pytest.mark.asyncio
    async def test_three_profiles_mixed_create_and_update(self, db_session):
        """[REAL DB+SDK] Three profiles: one new (create), one existing (update), one new again."""
        from app.services.agent_sync_service import sync_agent_for_profile

        await self._seed_master_config(db_session)
        user_id = await self._seed_user(db_session)

        # Profile 1: new — will create an agent
        p1 = await self._create_profile(
            db_session, user_id, name="UT-Real-Mixed-New", specialty="GP"
        )
        r1 = await sync_agent_for_profile(db_session, p1)
        _integration_agents.append(r1["id"])
        assert r1["id"]

        # Profile 2: existing — create first, then update
        p2 = await self._create_profile(
            db_session, user_id, name="UT-Real-Mixed-Update", specialty="Dermatology"
        )
        r2_create = await sync_agent_for_profile(db_session, p2)
        _integration_agents.append(r2_create["id"])

        p2.agent_id = r2_create["id"]
        await db_session.flush()
        r2_update = await sync_agent_for_profile(db_session, p2)
        assert r2_update["id"] == r2_create["id"], "Update should keep same agent ID"
        assert r2_update["version"], "Updated agent must have a version"

        # Profile 3: another new — third distinct agent
        p3 = await self._create_profile(
            db_session, user_id, name="UT-Real-Mixed-New2", specialty="Pediatrics"
        )
        r3 = await sync_agent_for_profile(db_session, p3)
        _integration_agents.append(r3["id"])

        all_ids = {r1["id"], r2_create["id"], r3["id"]}
        assert len(all_ids) == 3, f"Expected 3 unique agent IDs, got: {all_ids}"

    @pytest.mark.asyncio
    async def test_sync_stores_agent_version_on_profile(self, db_session):
        """[REAL DB+SDK] sync_agent_for_profile stores agent_version on profile object."""
        from app.services.agent_sync_service import sync_agent_for_profile

        await self._seed_master_config(db_session)
        user_id = await self._seed_user(db_session)
        profile = await self._create_profile(
            db_session, user_id, name="UT-Real-Dr-Version", specialty="Hematology"
        )

        result = await sync_agent_for_profile(db_session, profile)

        assert profile.agent_version, "agent_version should be set after sync"
        assert profile.agent_version == str(result["version"])
        _integration_agents.append(result["id"])


@_skip_no_creds_integration
@pytest.mark.asyncio
async def test_real_integration_cleanup():
    """[REAL] Cleanup: delete agents created by TestRealAgentSyncOperations."""
    from app.services.agent_sync_service import _get_project_client

    endpoint, api_key, project = _get_real_azure_config()
    project_endpoint = f"{endpoint}/api/projects/{project}"
    client = _get_project_client(project_endpoint, api_key)

    deleted = 0
    for agent_name in _integration_agents:
        try:
            client.agents.delete(agent_name=agent_name)
            deleted += 1
        except Exception as e:
            print(f"  Integration cleanup: could not delete {agent_name}: {e}")

    print(f"  Integration cleanup: deleted {deleted}/{len(_integration_agents)} test agents")
    _integration_agents.clear()


# ===========================================================================
# Original real Azure integration tests (standalone, non-class)
# ===========================================================================

_skip_no_creds = _skip_no_creds_integration

# Agent names created during tests, for cleanup
_created_agents: list[str] = []


@_skip_no_creds
@pytest.mark.asyncio
async def test_real_create_agent():
    """[REAL] Create a single agent on Azure AI Foundry using .env credentials."""
    from app.services.agent_sync_service import (
        _get_project_client,
        _sanitize_agent_name,
        build_agent_instructions,
    )

    endpoint, api_key, project = _get_real_azure_config()
    project_endpoint = f"{endpoint}/api/projects/{project}"
    client = _get_project_client(project_endpoint, api_key)

    from azure.ai.projects.models import PromptAgentDefinition

    instructions = build_agent_instructions(
        {
            "name": "Dr. Test-Chen",
            "specialty": "Oncology",
            "hospital": "Test Hospital",
            "title": "Physician",
            "personality_type": "analytical",
            "emotional_state": 50,
            "communication_style": 30,
            "expertise_areas": ["testing"],
            "prescribing_habits": "N/A",
            "concerns": "test",
            "objections": ["none"],
            "probe_topics": ["test"],
        }
    )

    agent_name = _sanitize_agent_name("Test-Dr-Chen-UT")
    definition = PromptAgentDefinition(model="gpt-4o", instructions=instructions)

    result = client.agents.create_version(
        agent_name=agent_name,
        definition=definition,
        description="Unit test agent — safe to delete",
    )

    _created_agents.append(result.name)

    assert result.name == agent_name
    assert result.version
    print(f"  Created real agent: name={result.name}, version={result.version}")


@_skip_no_creds
@pytest.mark.asyncio
async def test_real_three_profiles_sync():
    """[REAL] Three HCP profiles create three agents on Azure AI Foundry.

    This is the primary acceptance test: 3 HCPs → 3 real agents.
    """
    from app.services.agent_sync_service import (
        _get_project_client,
        _sanitize_agent_name,
        build_agent_instructions,
    )

    endpoint, api_key, project = _get_real_azure_config()
    project_endpoint = f"{endpoint}/api/projects/{project}"
    client = _get_project_client(project_endpoint, api_key)

    from azure.ai.projects.models import PromptAgentDefinition

    profiles = [
        {
            "name": "UT-Dr-Chen-Wei",
            "specialty": "Oncology",
            "hospital": "Beijing Hospital",
            "title": "Chief Physician",
            "personality_type": "analytical",
            "emotional_state": 50,
            "communication_style": 30,
            "expertise_areas": ["lung cancer", "immunotherapy"],
            "prescribing_habits": "Evidence-based",
            "concerns": "Drug efficacy",
            "objections": ["cost concerns"],
            "probe_topics": ["clinical trial results"],
        },
        {
            "name": "UT-Dr-Li-Ming",
            "specialty": "Cardiology",
            "hospital": "Shanghai Heart Center",
            "title": "Senior Physician",
            "personality_type": "friendly",
            "emotional_state": 20,
            "communication_style": 80,
            "expertise_areas": ["heart failure", "arrhythmia"],
            "prescribing_habits": "Conservative",
            "concerns": "Patient safety",
            "objections": ["side effects"],
            "probe_topics": ["dosing"],
        },
        {
            "name": "UT-Dr-Wang-Fang",
            "specialty": "Neurology",
            "hospital": "Guangzhou Medical",
            "title": "Attending Physician",
            "personality_type": "skeptical",
            "emotional_state": 80,
            "communication_style": 40,
            "expertise_areas": ["stroke", "epilepsy"],
            "prescribing_habits": "Guideline-based",
            "concerns": "Long-term outcomes",
            "objections": ["limited data"],
            "probe_topics": ["mechanism of action"],
        },
    ]

    results = []
    for profile_data in profiles:
        instructions = build_agent_instructions(profile_data)
        agent_name = _sanitize_agent_name(profile_data["name"])
        definition = PromptAgentDefinition(model="gpt-4o", instructions=instructions)

        result = client.agents.create_version(
            agent_name=agent_name,
            definition=definition,
            description="Unit test agent — safe to delete",
        )
        _created_agents.append(result.name)
        results.append({"name": result.name, "version": result.version})

    # All 3 must succeed
    assert len(results) == 3
    agent_names = [r["name"] for r in results]
    assert len(set(agent_names)) == 3, f"Expected 3 unique agents, got: {agent_names}"

    for r in results:
        assert r["name"], f"Agent name must not be empty: {r}"
        assert r["version"], f"Agent version must not be empty: {r}"
        print(f"  Created real agent: name={r['name']}, version={r['version']}")


@_skip_no_creds
@pytest.mark.asyncio
async def test_real_cleanup_test_agents():
    """[REAL] Cleanup: delete any agents created by tests."""
    from app.services.agent_sync_service import _get_project_client

    endpoint, api_key, project = _get_real_azure_config()
    project_endpoint = f"{endpoint}/api/projects/{project}"
    client = _get_project_client(project_endpoint, api_key)

    deleted = 0
    for agent_name in _created_agents:
        try:
            client.agents.delete(agent_name=agent_name)
            deleted += 1
        except Exception as e:
            print(f"  Cleanup: could not delete {agent_name}: {e}")

    print(f"  Cleanup: deleted {deleted}/{len(_created_agents)} test agents")
    _created_agents.clear()


# ===========================================================================
# Phase 12: Agent instruction override tests (D-02)
# ===========================================================================


def test_build_agent_instructions_with_override():
    """build_agent_instructions returns override when non-empty (D-02)."""
    from app.services.agent_sync_service import build_agent_instructions

    data = {
        "name": "Dr. Zhang",
        "specialty": "Oncology",
        "agent_instructions_override": "Custom override instructions for Dr. Zhang",
    }
    result = build_agent_instructions(data)
    assert result == "Custom override instructions for Dr. Zhang"


def test_build_agent_instructions_empty_override():
    """build_agent_instructions returns template when override is empty string."""
    from app.services.agent_sync_service import build_agent_instructions

    data = {
        "name": "Dr. Zhang",
        "specialty": "Oncology",
        "agent_instructions_override": "",
    }
    result = build_agent_instructions(data)
    assert "Dr. Zhang" in result
    assert "Oncology" in result


def test_build_agent_instructions_whitespace_override():
    """build_agent_instructions returns template when override is whitespace-only."""
    from app.services.agent_sync_service import build_agent_instructions

    data = {
        "name": "Dr. Li",
        "specialty": "Hematology",
        "agent_instructions_override": "   ",
    }
    result = build_agent_instructions(data)
    assert "Dr. Li" in result
    assert "Hematology" in result


def test_build_agent_instructions_no_override_key():
    """build_agent_instructions returns template when no override key present."""
    from app.services.agent_sync_service import build_agent_instructions

    data = {
        "name": "Dr. Wang",
        "specialty": "Cardiology",
    }
    result = build_agent_instructions(data)
    assert "Dr. Wang" in result
    assert "Cardiology" in result


def test_build_agent_instructions_override_with_whitespace_stripped():
    """build_agent_instructions strips leading/trailing whitespace from override."""
    from app.services.agent_sync_service import build_agent_instructions

    data = {
        "name": "Dr. Pad",
        "specialty": "GP",
        "agent_instructions_override": "  Custom padded instructions  ",
    }
    result = build_agent_instructions(data)
    assert result == "Custom padded instructions"


# ===========================================================================
# Phase 16: build_voice_live_metadata with resolve_voice_config + avatar/instance fields
# ===========================================================================


def test_build_voice_live_metadata_uses_resolve_voice_config():
    """build_voice_live_metadata uses resolve_voice_config and includes avatar/instance fields."""
    import json

    from app.services.agent_sync_service import (
        VOICE_LIVE_CONFIG_KEY,
        VOICE_LIVE_ENABLED_KEY,
        build_voice_live_metadata,
    )

    mock_profile = MagicMock()
    # Simulate a profile with a VoiceLiveInstance attached
    mock_instance = MagicMock()
    mock_instance.enabled = True
    mock_instance.voice_live_model = "gpt-4o"
    mock_instance.voice_name = "zh-CN-XiaoxiaoMultilingualNeural"
    mock_instance.voice_type = "azure-standard"
    mock_instance.voice_temperature = 0.7
    mock_instance.voice_custom = False
    mock_instance.avatar_character = "lisa"
    mock_instance.avatar_style = "formal"
    mock_instance.avatar_customized = False
    mock_instance.turn_detection_type = "server_vad"
    mock_instance.noise_suppression = True
    mock_instance.echo_cancellation = True
    mock_instance.eou_detection = True
    mock_instance.recognition_language = "zh-CN"
    mock_instance.model_instruction = ""
    mock_instance.response_temperature = 0.6
    mock_instance.proactive_engagement = False
    mock_instance.auto_detect_language = False
    mock_instance.playback_speed = 1.2
    mock_instance.custom_lexicon_enabled = True
    mock_instance.custom_lexicon_url = "https://example.com/lexicon.xml"
    mock_instance.avatar_enabled = True

    mock_profile.voice_live_instance = mock_instance

    result = build_voice_live_metadata(mock_profile)
    assert result is not None
    assert result[VOICE_LIVE_ENABLED_KEY] == "true"

    # Parse config JSON (single value, no chunking)
    config_json = result[VOICE_LIVE_CONFIG_KEY]
    config = json.loads(config_json)

    # Azure metadata 512-char limit: verify JSON fits
    assert len(config_json) <= 512, f"config_json is {len(config_json)} chars, exceeds 512 limit"

    # Foundry Portal format: config wrapped in {"session": {...}} with camelCase keys
    assert "session" in config
    session = config["session"]

    # Voice settings — name always present; defaults omitted to save space
    assert session["voice"]["name"] == "zh-CN-XiaoxiaoMultilingualNeural"
    # "type" omitted when "azure-standard" (default)
    assert "type" not in session["voice"]
    # Non-default values ARE present
    assert session["voice"]["temperature"] == 0.7
    assert session["voice"]["rate"] == "1.2"

    # Input audio transcription — only present when language is non-default
    # zh-CN is not the default "auto-detect", so it should be present
    assert session["inputAudioTranscription"]["language"] == "zh-CN"
    # "model" key omitted to save space (always "azure-speech")
    assert "model" not in session["inputAudioTranscription"]

    # Turn detection with EOU (camelCase)
    assert session["turnDetection"]["type"] == "server_vad"
    assert session["turnDetection"]["endOfUtteranceDetection"] == {"model": "semantic_detection_v1"}
    # removeFillerWords omitted (Foundry default is true)
    assert "removeFillerWords" not in session["turnDetection"]

    # Noise/echo — present when enabled (omitted when disabled instead of null)
    assert session["inputAudioNoiseReduction"] is not None
    assert session["inputAudioEchoCancellation"] is not None

    # Avatar settings — only non-default fields
    assert session["avatar"]["character"] == "lisa"
    assert session["avatar"]["style"] == "formal"
    # "customized" omitted when False (default)
    assert "customized" not in session["avatar"]

    # proactiveEngagement omitted when False (default)
    assert "proactiveEngagement" not in session


def test_build_voice_live_metadata_fits_512_char_limit_worst_case():
    """Azure metadata values must be ≤512 chars per key.

    This test exercises the WORST-CASE scenario: a long avatar style
    (casual-sitting), long voice name (XiaoxiaoMultilingualNeural),
    all optional features enabled (noise, echo, EOU, proactive, customized,
    non-default temperature/rate).  If this passes, all real configurations
    will fit within the 512-char Azure metadata limit.

    Rule: We omit null fields and default-value fields from the JSON.
    The Azure Foundry Portal fills in defaults server-side.
    See agent_sync_service.build_voice_live_metadata() for details.
    """
    import json

    from app.services.agent_sync_service import (
        VOICE_LIVE_CONFIG_KEY,
        build_voice_live_metadata,
    )

    mock_profile = MagicMock()
    mock_instance = MagicMock()
    # Worst-case long values
    mock_instance.enabled = True
    mock_instance.voice_live_model = "gpt-4o-realtime-preview"
    mock_instance.voice_name = "zh-CN-XiaoxiaoMultilingualNeural"
    mock_instance.voice_type = "azure-standard"
    mock_instance.voice_temperature = 0.65
    mock_instance.voice_custom = False
    mock_instance.avatar_character = "lisa"
    mock_instance.avatar_style = "casual-sitting"
    mock_instance.avatar_customized = True
    mock_instance.turn_detection_type = "azure_semantic_vad"
    mock_instance.noise_suppression = True
    mock_instance.echo_cancellation = True
    mock_instance.eou_detection = True
    mock_instance.recognition_language = "auto-detect"
    mock_instance.model_instruction = ""
    mock_instance.response_temperature = 0.9
    mock_instance.proactive_engagement = True
    mock_instance.auto_detect_language = True
    mock_instance.playback_speed = 1.5
    mock_instance.custom_lexicon_enabled = True
    mock_instance.custom_lexicon_url = "https://example.com/custom-lexicon.xml"
    mock_instance.avatar_enabled = True

    mock_profile.voice_live_instance = mock_instance

    result = build_voice_live_metadata(mock_profile)
    assert result is not None

    config_json = result[VOICE_LIVE_CONFIG_KEY]
    config = json.loads(config_json)

    # THE critical assertion: must fit within Azure's 512-char per-value limit
    assert len(config_json) <= 512, (
        f"Voice config JSON is {len(config_json)} chars, exceeds Azure 512-char "
        f"metadata limit.  Compact the JSON by omitting null/default fields.\n"
        f"JSON: {config_json}"
    )

    # Verify essential fields are still present
    session = config["session"]
    assert session["voice"]["name"] == "zh-CN-XiaoxiaoMultilingualNeural"
    assert session["avatar"]["character"] == "lisa"
    assert session["avatar"]["style"] == "casual-sitting"
    assert "inputAudioNoiseReduction" in session
    assert "inputAudioEchoCancellation" in session


def test_build_cleared_voice_metadata_returns_disabled_state():
    """build_cleared_voice_metadata returns disabled VL metadata (RD-4)."""
    from app.services.agent_sync_service import (
        VOICE_LIVE_CONFIG_KEY,
        VOICE_LIVE_ENABLED_KEY,
        build_cleared_voice_metadata,
    )

    result = build_cleared_voice_metadata()
    assert result[VOICE_LIVE_ENABLED_KEY] == "false"
    assert result[VOICE_LIVE_CONFIG_KEY] == "{}"


def test_build_voice_live_metadata_returns_none_when_disabled():
    """build_voice_live_metadata returns None when voice_live_enabled is False."""
    from app.services.agent_sync_service import build_voice_live_metadata

    mock_profile = MagicMock()
    mock_profile.voice_live_instance = None
    mock_profile.voice_live_enabled = False
    # Inline fallback fields
    mock_profile.voice_live_model = "gpt-4o"
    mock_profile.voice_name = "en-US-AvaNeural"
    mock_profile.voice_type = "azure-standard"
    mock_profile.voice_temperature = 0.9
    mock_profile.voice_custom = False
    mock_profile.avatar_character = "lori"
    mock_profile.avatar_style = "casual"
    mock_profile.avatar_customized = False
    mock_profile.turn_detection_type = "server_vad"
    mock_profile.noise_suppression = False
    mock_profile.echo_cancellation = False
    mock_profile.eou_detection = False
    mock_profile.recognition_language = "auto"

    result = build_voice_live_metadata(mock_profile)
    assert result is None


# ===========================================================================
# Phase 16: sync_agent_for_profile stores agent_version (RD-7)
# ===========================================================================


@pytest.mark.asyncio
async def test_sync_agent_for_profile_stores_agent_version():
    """sync_agent_for_profile stores agent version on profile after sync (RD-7)."""
    from app.services.agent_sync_service import sync_agent_for_profile

    mock_db = AsyncMock()
    mock_profile = MagicMock()
    mock_profile.agent_id = ""
    mock_profile.name = "Dr. Version"
    mock_profile.voice_live_enabled = False
    mock_profile.voice_live_instance = None
    # Add all inline fallback fields needed by resolve_voice_config
    mock_profile.voice_live_model = "gpt-4o"
    mock_profile.voice_name = "en-US-AvaNeural"
    mock_profile.voice_type = "azure-standard"
    mock_profile.voice_temperature = 0.9
    mock_profile.voice_custom = False
    mock_profile.avatar_character = "lori"
    mock_profile.avatar_style = "casual"
    mock_profile.avatar_customized = False
    mock_profile.turn_detection_type = "server_vad"
    mock_profile.noise_suppression = False
    mock_profile.echo_cancellation = False
    mock_profile.eou_detection = False
    mock_profile.recognition_language = "auto"
    mock_profile.to_prompt_dict.return_value = {"name": "Dr. Version", "specialty": "GP"}

    with (
        patch(
            "app.services.agent_sync_service.create_agent",
            new_callable=AsyncMock,
            return_value={
                "id": "agent-v-001",
                "name": "Dr-Version",
                "version": "3",
                "model": "gpt-4o",
            },
        ),
        patch(
            "app.services.agent_sync_service.get_agent_latest_version",
            new_callable=AsyncMock,
            return_value="3",
        ),
        patch(
            "app.services.knowledge_base_service.get_knowledge_configs",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        result = await sync_agent_for_profile(mock_db, mock_profile, prefetched_model="gpt-4o")

    assert result["version"] == "3"
    # Verify version from Foundry stored on profile object
    assert mock_profile.agent_version == "3"


# ===========================================================================
# Phase 16 coverage boost: update_agent_metadata_only, _ApiKeyTokenCredential,
# _get_project_client DefaultAzureCredential, create/update_agent exception paths,
# prefetch_sync_config, get_portal_url_components, get_agent_latest_version
# ===========================================================================


@pytest.mark.asyncio
async def test_update_agent_metadata_only_success():
    """update_agent_metadata_only merges VL metadata, preserves instructions, returns version."""
    from app.services.agent_sync_service import update_agent_metadata_only

    mock_db = AsyncMock()

    # Simulate existing agent with old VL metadata and full instructions
    full_instructions = (
        "You are Dr. Wang Fang, a Neurology specialist.\n\n"
        "Background:\n- Hospital: Shanghai Huashan Hospital\n- Title: Chief Physician"
    )
    mock_agent = MagicMock()
    mock_agent.metadata = {
        "microsoft.voice-live.enabled": "true",
        "microsoft.voice-live.configuration": '{"old":"data"}',
        "custom-key": "keep-this",
    }
    mock_agent.versions = {
        "latest": {
            "version": "3",
            "definition": {
                "instructions": full_instructions,
                "model": "gpt-4o",
            },
        }
    }

    mock_create_result = MagicMock()
    mock_create_result.version = "4"

    mock_client = MagicMock()
    mock_client.agents.get.return_value = mock_agent
    mock_client.agents.create_version.return_value = mock_create_result

    new_metadata = {
        "microsoft.voice-live.enabled": "true",
        "microsoft.voice-live.configuration": '{"new":"config"}',
    }

    with (
        patch(
            "app.services.agent_sync_service.get_project_endpoint",
            new_callable=AsyncMock,
            return_value=("https://foundry/api/projects/proj", "key"),
        ),
        patch(
            "app.services.agent_sync_service._get_project_client",
            return_value=mock_client,
        ),
    ):
        result = await update_agent_metadata_only(mock_db, "agent-001", new_metadata)

    # Returns new version string (not bool)
    assert result == "4"
    mock_client.agents.create_version.assert_called_once()
    call_kwargs = mock_client.agents.create_version.call_args[1]
    # Old VL keys removed, new VL keys added, custom-key preserved
    merged = call_kwargs["metadata"]
    assert merged["microsoft.voice-live.enabled"] == "true"
    assert merged["microsoft.voice-live.configuration"] == '{"new":"config"}'
    assert merged["custom-key"] == "keep-this"
    # Instructions MUST be preserved through metadata-only update
    sent_definition = call_kwargs["definition"]
    assert sent_definition.instructions == full_instructions
    assert "Background:" in sent_definition.instructions
    assert "Shanghai Huashan Hospital" in sent_definition.instructions


@pytest.mark.asyncio
async def test_update_agent_metadata_only_with_endpoint_override():
    """update_agent_metadata_only uses endpoint_override when provided."""
    from app.services.agent_sync_service import update_agent_metadata_only

    mock_db = AsyncMock()
    mock_agent = MagicMock()
    mock_agent.metadata = {}
    mock_agent.versions = {
        "latest": {
            "definition": {"instructions": "test", "model": "gpt-4o"},
        }
    }

    mock_create_result = MagicMock()
    mock_create_result.version = "5"

    mock_client = MagicMock()
    mock_client.agents.get.return_value = mock_agent
    mock_client.agents.create_version.return_value = mock_create_result

    with patch(
        "app.services.agent_sync_service._get_project_client",
        return_value=mock_client,
    ) as mock_get_client:
        result = await update_agent_metadata_only(
            mock_db,
            "agent-002",
            {"key": "val"},
            endpoint_override="https://custom-endpoint",
            key_override="custom-key",
        )

    assert result == "5"
    mock_get_client.assert_called_once_with("https://custom-endpoint", "custom-key")


@pytest.mark.asyncio
async def test_update_agent_metadata_only_api_failure():
    """update_agent_metadata_only returns None when SDK raises exception."""
    from app.services.agent_sync_service import update_agent_metadata_only

    mock_db = AsyncMock()
    mock_client = MagicMock()
    mock_client.agents.get.side_effect = Exception("API error")

    with (
        patch(
            "app.services.agent_sync_service.get_project_endpoint",
            new_callable=AsyncMock,
            return_value=("https://foundry/api/projects/proj", "key"),
        ),
        patch(
            "app.services.agent_sync_service._get_project_client",
            return_value=mock_client,
        ),
    ):
        result = await update_agent_metadata_only(mock_db, "agent-fail", {"k": "v"})

    assert result is None


@pytest.mark.asyncio
async def test_update_agent_metadata_only_no_existing_metadata():
    """update_agent_metadata_only handles agent with no existing metadata."""
    from app.services.agent_sync_service import update_agent_metadata_only

    mock_db = AsyncMock()
    mock_agent = MagicMock()
    mock_agent.metadata = None  # no metadata at all
    mock_agent.versions = {
        "latest": {
            "definition": {"instructions": "instruct", "model": "gpt-4o"},
        }
    }

    mock_create_result = MagicMock()
    mock_create_result.version = "2"

    mock_client = MagicMock()
    mock_client.agents.get.return_value = mock_agent
    mock_client.agents.create_version.return_value = mock_create_result

    with (
        patch(
            "app.services.agent_sync_service.get_project_endpoint",
            new_callable=AsyncMock,
            return_value=("https://foundry/api/projects/proj", "key"),
        ),
        patch(
            "app.services.agent_sync_service._get_project_client",
            return_value=mock_client,
        ),
    ):
        result = await update_agent_metadata_only(mock_db, "agent-no-meta", {"new-key": "val"})

    assert result == "2"
    call_kwargs = mock_client.agents.create_version.call_args[1]
    assert call_kwargs["metadata"]["new-key"] == "val"
    # Instructions preserved even with no existing metadata
    assert call_kwargs["definition"].instructions == "instruct"


def test_api_key_token_credential_get_token():
    """_ApiKeyTokenCredential.get_token returns AccessToken with key."""
    from app.services.agent_sync_service import _ApiKeyTokenCredential

    cred = _ApiKeyTokenCredential("test-api-key")
    token = cred.get_token("https://scope")
    assert token.token == "test-api-key"
    assert token.expires_on > 0


def test_get_project_client_with_default_azure_credential():
    """_get_project_client uses DefaultAzureCredential when no api_key."""
    from app.services.agent_sync_service import _get_project_client

    mock_dac = MagicMock()
    mock_client_cls = MagicMock()

    with (
        patch("azure.identity.DefaultAzureCredential", mock_dac),
        patch("azure.ai.projects.AIProjectClient", mock_client_cls),
    ):
        _get_project_client("https://endpoint.azure.com", "")

    mock_dac.assert_called_once()
    mock_client_cls.assert_called_once()
    call_kwargs = mock_client_cls.call_args[1]
    assert call_kwargs["endpoint"] == "https://endpoint.azure.com"


def test_get_project_client_prefers_entra_id_over_api_key():
    """_get_project_client prefers DefaultAzureCredential even when api_key is provided."""
    from app.services.agent_sync_service import _get_project_client

    mock_dac = MagicMock()
    mock_client_cls = MagicMock()

    with (
        patch("azure.identity.DefaultAzureCredential", mock_dac),
        patch("azure.ai.projects.AIProjectClient", mock_client_cls),
    ):
        _get_project_client("https://endpoint.azure.com", "my-api-key")

    # Should use DefaultAzureCredential, not API Key
    mock_dac.assert_called_once()
    call_kwargs = mock_client_cls.call_args[1]
    assert call_kwargs["endpoint"] == "https://endpoint.azure.com"
    # credential should be the DAC instance, not _ApiKeyTokenCredential
    assert call_kwargs["credential"] == mock_dac.return_value
    # No authentication_policy override (Entra ID doesn't need it)
    assert "authentication_policy" not in call_kwargs


def test_get_project_client_falls_back_to_api_key():
    """_get_project_client falls back to API Key when DefaultAzureCredential fails."""
    from app.services.agent_sync_service import _get_project_client

    mock_dac = MagicMock()
    mock_dac.return_value.get_token.side_effect = Exception("No credential available")
    mock_client_cls = MagicMock()

    with (
        patch("azure.identity.DefaultAzureCredential", mock_dac),
        patch("azure.ai.projects.AIProjectClient", mock_client_cls),
    ):
        _get_project_client("https://endpoint.azure.com", "my-api-key")

    mock_client_cls.assert_called_once()
    call_kwargs = mock_client_cls.call_args[1]
    assert call_kwargs["endpoint"] == "https://endpoint.azure.com"
    # Should have authentication_policy (API Key mode)
    assert "authentication_policy" in call_kwargs


def test_get_project_client_no_credential_raises():
    """_get_project_client raises ValueError when no credential is available."""
    from app.services.agent_sync_service import _get_project_client

    mock_dac = MagicMock()
    mock_dac.return_value.get_token.side_effect = Exception("No credential")

    with patch("azure.identity.DefaultAzureCredential", mock_dac):
        with pytest.raises(ValueError, match="No valid credential available"):
            _get_project_client("https://endpoint.azure.com", "")


@pytest.mark.asyncio
async def test_create_agent_exception_path():
    """create_agent raises RuntimeError when SDK raises."""
    from app.services.agent_sync_service import create_agent

    mock_db = AsyncMock()
    mock_client = MagicMock()
    mock_client.agents.create_version.side_effect = Exception("SDK error")

    with (
        patch(
            "app.services.agent_sync_service.get_project_endpoint",
            new_callable=AsyncMock,
            return_value=("https://foundry/api/projects/proj", "key"),
        ),
        patch(
            "app.services.agent_sync_service._get_project_client",
            return_value=mock_client,
        ),
    ):
        with pytest.raises(RuntimeError, match="Agent creation failed"):
            await create_agent(mock_db, "Fail Agent", "Instructions", "gpt-4o")


@pytest.mark.asyncio
async def test_create_agent_no_model_uses_default():
    """create_agent uses default model from settings when model is None."""
    from app.services.agent_sync_service import create_agent

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.name = "Test-Agent"
    mock_result.version = "1"

    mock_client = MagicMock()
    mock_client.agents.create_version.return_value = mock_result

    with (
        patch(
            "app.services.agent_sync_service.get_project_endpoint",
            new_callable=AsyncMock,
            return_value=("https://foundry/api/projects/proj", "key"),
        ),
        patch(
            "app.services.agent_sync_service._get_project_client",
            return_value=mock_client,
        ),
    ):
        result = await create_agent(mock_db, "Test Agent", "Instructions", None)

    assert result["name"] == "Test-Agent"


@pytest.mark.asyncio
async def test_create_agent_with_endpoint_override():
    """create_agent uses endpoint_override instead of DB lookup."""
    from app.services.agent_sync_service import create_agent

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.name = "Override-Agent"
    mock_result.version = "1"

    mock_client = MagicMock()
    mock_client.agents.create_version.return_value = mock_result

    with patch(
        "app.services.agent_sync_service._get_project_client",
        return_value=mock_client,
    ) as mock_get_client:
        result = await create_agent(
            mock_db,
            "Override Agent",
            "Instructions",
            "gpt-4o",
            endpoint_override="https://custom-ep",
            key_override="custom-k",
        )

    assert result["name"] == "Override-Agent"
    mock_get_client.assert_called_once_with("https://custom-ep", "custom-k")


@pytest.mark.asyncio
async def test_update_agent_exception_path():
    """update_agent raises RuntimeError when SDK raises."""
    from app.services.agent_sync_service import update_agent

    mock_db = AsyncMock()
    mock_client = MagicMock()
    mock_client.agents.create_version.side_effect = Exception("SDK update error")

    with (
        patch(
            "app.services.agent_sync_service.get_project_endpoint",
            new_callable=AsyncMock,
            return_value=("https://foundry/api/projects/proj", "key"),
        ),
        patch(
            "app.services.agent_sync_service._get_project_client",
            return_value=mock_client,
        ),
    ):
        with pytest.raises(RuntimeError, match="Agent update failed"):
            await update_agent(mock_db, "existing-agent", "Updated Name", "New instructions")


@pytest.mark.asyncio
async def test_update_agent_with_endpoint_override():
    """update_agent uses endpoint_override instead of DB lookup."""
    from app.services.agent_sync_service import update_agent

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.name = "Override-Update"
    mock_result.version = "2"

    mock_client = MagicMock()
    mock_client.agents.create_version.return_value = mock_result

    with patch(
        "app.services.agent_sync_service._get_project_client",
        return_value=mock_client,
    ) as mock_get_client:
        result = await update_agent(
            mock_db,
            "existing",
            "Name",
            "Instructions",
            "gpt-4o",
            endpoint_override="https://custom-ep",
            key_override="custom-k",
        )

    assert result["name"] == "Override-Update"
    mock_get_client.assert_called_once_with("https://custom-ep", "custom-k")


@pytest.mark.asyncio
async def test_prefetch_sync_config():
    """prefetch_sync_config returns endpoint, api_key, model from master config."""
    from app.services.agent_sync_service import prefetch_sync_config

    mock_db = AsyncMock()
    mock_master = MagicMock()
    mock_master.model_or_deployment = "gpt-4o-realtime"

    with (
        patch(
            "app.services.agent_sync_service.get_project_endpoint",
            new_callable=AsyncMock,
            return_value=("https://foundry/api/projects/proj", "the-key"),
        ),
        patch(
            "app.services.agent_sync_service.config_service.get_master_config",
            new_callable=AsyncMock,
            return_value=mock_master,
        ),
    ):
        endpoint, api_key, model = await prefetch_sync_config(mock_db)

    assert endpoint == "https://foundry/api/projects/proj"
    assert api_key == "the-key"
    assert model == "gpt-4o-realtime"


@pytest.mark.asyncio
async def test_prefetch_sync_config_no_master():
    """prefetch_sync_config falls back to settings default model when no master."""
    from app.config import get_settings
    from app.services.agent_sync_service import prefetch_sync_config

    mock_db = AsyncMock()

    with (
        patch(
            "app.services.agent_sync_service.get_project_endpoint",
            new_callable=AsyncMock,
            return_value=("https://foundry/api/projects/proj", "key"),
        ),
        patch(
            "app.services.agent_sync_service.config_service.get_master_config",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        endpoint, api_key, model = await prefetch_sync_config(mock_db)

    assert model == get_settings().voice_live_default_model


@pytest.mark.asyncio
async def test_get_portal_url_components_success():
    """get_portal_url_components extracts subscription, RG, resource, project from ARM ID."""
    import app.services.agent_sync_service as mod

    # Clear cache
    mod._portal_url_cache = None

    mock_db = AsyncMock()
    mock_client = MagicMock()

    # Simulate a connection with ARM resource ID
    conn = {
        "id": (
            "/subscriptions/12345678-1234-1234-1234-123456789abc"
            "/resourceGroups/my-rg/providers/Microsoft.MachineLearningServices"
            "/accounts/my-resource/projects/my-project/connections/conn1"
        ),
    }
    mock_client.connections.list.return_value = [conn]

    with (
        patch(
            "app.services.agent_sync_service.get_project_endpoint",
            new_callable=AsyncMock,
            return_value=("https://foundry", "key"),
        ),
        patch(
            "app.services.agent_sync_service._get_project_client",
            return_value=mock_client,
        ),
    ):
        result = await mod.get_portal_url_components(mock_db)

    assert result["resource_group"] == "my-rg"
    assert result["resource_name"] == "my-resource"
    assert result["project_name"] == "my-project"
    assert "subscription_hash" in result

    # Clean up cache for other tests
    mod._portal_url_cache = None


@pytest.mark.asyncio
async def test_get_portal_url_components_no_connections():
    """get_portal_url_components returns empty dict when no connections with ARM ID."""
    import app.services.agent_sync_service as mod

    mod._portal_url_cache = None

    mock_db = AsyncMock()
    mock_client = MagicMock()
    # No connections matching the ARM pattern
    mock_client.connections.list.return_value = [{"id": "no-match"}]

    with (
        patch(
            "app.services.agent_sync_service.get_project_endpoint",
            new_callable=AsyncMock,
            return_value=("https://foundry", "key"),
        ),
        patch(
            "app.services.agent_sync_service._get_project_client",
            return_value=mock_client,
        ),
    ):
        result = await mod.get_portal_url_components(mock_db)

    assert result == {}
    mod._portal_url_cache = None


@pytest.mark.asyncio
async def test_get_portal_url_components_exception():
    """get_portal_url_components returns empty dict when SDK raises exception."""
    import app.services.agent_sync_service as mod

    mod._portal_url_cache = None

    mock_db = AsyncMock()

    with patch(
        "app.services.agent_sync_service.get_project_endpoint",
        new_callable=AsyncMock,
        side_effect=Exception("connection error"),
    ):
        result = await mod.get_portal_url_components(mock_db)

    assert result == {}
    mod._portal_url_cache = None


@pytest.mark.asyncio
async def test_get_portal_url_components_cached():
    """get_portal_url_components uses cache on second call."""
    import app.services.agent_sync_service as mod

    mod._portal_url_cache = {"subscription_hash": "cached", "resource_group": "rg"}

    mock_db = AsyncMock()
    result = await mod.get_portal_url_components(mock_db)

    assert result["subscription_hash"] == "cached"
    mod._portal_url_cache = None


@pytest.mark.asyncio
async def test_get_agent_latest_version_success():
    """get_agent_latest_version returns latest version string from Azure."""
    from app.services.agent_sync_service import get_agent_latest_version

    mock_db = AsyncMock()
    mock_agent = MagicMock()
    mock_agent.versions = {"latest": {"version": "5"}}

    mock_client = MagicMock()
    mock_client.agents.get.return_value = mock_agent

    with (
        patch(
            "app.services.agent_sync_service.get_project_endpoint",
            new_callable=AsyncMock,
            return_value=("https://foundry", "key"),
        ),
        patch(
            "app.services.agent_sync_service._get_project_client",
            return_value=mock_client,
        ),
    ):
        version = await get_agent_latest_version(mock_db, "test-agent")

    assert version == "5"


@pytest.mark.asyncio
async def test_get_agent_latest_version_exception_returns_fallback():
    """get_agent_latest_version returns '1' on exception."""
    from app.services.agent_sync_service import get_agent_latest_version

    mock_db = AsyncMock()
    mock_client = MagicMock()
    mock_client.agents.get.side_effect = Exception("not found")

    with (
        patch(
            "app.services.agent_sync_service.get_project_endpoint",
            new_callable=AsyncMock,
            return_value=("https://foundry", "key"),
        ),
        patch(
            "app.services.agent_sync_service._get_project_client",
            return_value=mock_client,
        ),
    ):
        version = await get_agent_latest_version(mock_db, "unknown-agent")

    assert version == "1"


def test_build_voice_live_metadata_semantic_vad():
    """build_voice_live_metadata correctly sets semantic_vad turn_detection_type."""
    import json

    from app.services.agent_sync_service import (
        VOICE_LIVE_CONFIG_KEY,
        build_voice_live_metadata,
    )

    mock_profile = MagicMock()
    mock_instance = MagicMock()
    mock_instance.enabled = True
    mock_instance.voice_live_model = "gpt-4o"
    mock_instance.voice_name = "en-US-AvaNeural"
    mock_instance.voice_type = "azure-standard"
    mock_instance.voice_temperature = 0.9
    mock_instance.voice_custom = False
    mock_instance.avatar_character = "lori"
    mock_instance.avatar_style = "casual"
    mock_instance.avatar_customized = False
    mock_instance.turn_detection_type = "semantic_vad"
    mock_instance.noise_suppression = False
    mock_instance.echo_cancellation = False
    mock_instance.eou_detection = False
    mock_instance.recognition_language = "auto"
    mock_instance.model_instruction = ""
    mock_instance.response_temperature = 0.8
    mock_instance.proactive_engagement = True
    mock_instance.auto_detect_language = True
    mock_instance.playback_speed = 1.0
    mock_instance.custom_lexicon_enabled = False
    mock_instance.custom_lexicon_url = ""
    mock_instance.avatar_enabled = True

    mock_profile.voice_live_instance = mock_instance

    result = build_voice_live_metadata(mock_profile)
    assert result is not None

    # Parse config JSON (single value, no chunking)
    config = json.loads(result[VOICE_LIVE_CONFIG_KEY])

    # Foundry format: config["session"]["turnDetection"]
    session = config["session"]
    assert session["turnDetection"]["type"] == "semantic_vad"
    # No EOU since eou_detection=False — key omitted (not null) to save space
    assert "endOfUtteranceDetection" not in session["turnDetection"]


def test_build_voice_live_metadata_non_azure_standard_voice():
    """build_voice_live_metadata omits temperature for non-azure-standard voice types."""
    import json

    from app.services.agent_sync_service import (
        VOICE_LIVE_CONFIG_KEY,
        build_voice_live_metadata,
    )

    mock_profile = MagicMock()
    mock_instance = MagicMock()
    mock_instance.enabled = True
    mock_instance.voice_live_model = "gpt-4o"
    mock_instance.voice_name = "custom-voice"
    mock_instance.voice_type = "custom"
    mock_instance.voice_temperature = 0.9
    mock_instance.voice_custom = True
    mock_instance.avatar_character = "lori"
    mock_instance.avatar_style = "casual"
    mock_instance.avatar_customized = False
    mock_instance.turn_detection_type = "server_vad"
    mock_instance.noise_suppression = False
    mock_instance.echo_cancellation = False
    mock_instance.eou_detection = False
    mock_instance.recognition_language = "auto"
    mock_instance.model_instruction = ""
    mock_instance.response_temperature = 0.8
    mock_instance.proactive_engagement = True
    mock_instance.auto_detect_language = True
    mock_instance.playback_speed = 1.0
    mock_instance.custom_lexicon_enabled = False
    mock_instance.custom_lexicon_url = ""
    mock_instance.avatar_enabled = True

    mock_profile.voice_live_instance = mock_instance

    result = build_voice_live_metadata(mock_profile)
    assert result is not None
    config = json.loads(result[VOICE_LIVE_CONFIG_KEY])

    # Foundry format: config["session"]["voice"]
    session = config["session"]
    # All voice types include temperature in Foundry format
    assert session["voice"]["type"] == "custom"
    assert session["voice"]["name"] == "custom-voice"


def test_build_voice_live_metadata_custom_lexicon_disabled():
    """build_voice_live_metadata omits custom_lexicon when disabled."""
    import json

    from app.services.agent_sync_service import (
        VOICE_LIVE_CONFIG_KEY,
        build_voice_live_metadata,
    )

    mock_profile = MagicMock()
    mock_instance = MagicMock()
    mock_instance.enabled = True
    mock_instance.voice_live_model = "gpt-4o"
    mock_instance.voice_name = "en-US-AvaNeural"
    mock_instance.voice_type = "azure-standard"
    mock_instance.voice_temperature = 0.9
    mock_instance.voice_custom = False
    mock_instance.avatar_character = "lori"
    mock_instance.avatar_style = "casual"
    mock_instance.avatar_customized = False
    mock_instance.turn_detection_type = "server_vad"
    mock_instance.noise_suppression = False
    mock_instance.echo_cancellation = False
    mock_instance.eou_detection = False
    mock_instance.recognition_language = "auto"
    mock_instance.model_instruction = ""
    mock_instance.response_temperature = 0.8
    mock_instance.proactive_engagement = True
    mock_instance.auto_detect_language = True
    mock_instance.playback_speed = 1.0
    mock_instance.custom_lexicon_enabled = False
    mock_instance.custom_lexicon_url = ""
    mock_instance.avatar_enabled = True

    mock_profile.voice_live_instance = mock_instance

    result = build_voice_live_metadata(mock_profile)
    assert result is not None
    config = json.loads(result[VOICE_LIVE_CONFIG_KEY])

    assert "custom_lexicon" not in config


# =============================================================================
# Agent Name Sanitization Tests (Azure AI Foundry naming rules)
#
# Azure 命名规则（实测 2026-04）：
# - 仅允许字母数字 (a-z, A-Z, 0-9) 和连字符 (-)
# - 必须以字母数字开头和结尾
# - 不允许下划线、空格、点、中文等
# - 最大 63 字符（不是 64）
# - 违反时报错: (invalid_parameters) Must start and end with alphanumeric
#   characters, can contain hyphens in the middle, and must not exceed 63 characters.
#
# 参考文档: docs/microsoft-agent-framework/07-agent-skill-creation-guide.md
# =============================================================================


class TestSanitizeAgentName:
    """Tests for _sanitize_agent_name — Azure AI Foundry naming rule enforcement."""

    def _sanitize(self, name: str) -> str:
        from app.services.agent_sync_service import _sanitize_agent_name

        return _sanitize_agent_name(name)

    # --- Basic valid names pass through ---

    def test_valid_lowercase_hyphen(self):
        """Valid name with lowercase and hyphens passes through unchanged."""
        assert self._sanitize("skill-creator") == "skill-creator"

    def test_valid_mixed_case(self):
        """Valid name with mixed case passes through unchanged."""
        assert self._sanitize("Dr-Wang-Fang") == "Dr-Wang-Fang"

    def test_valid_alphanumeric_only(self):
        """Pure alphanumeric name passes through unchanged."""
        assert self._sanitize("agent123") == "agent123"

    def test_single_character(self):
        """Single alphanumeric character is valid."""
        assert self._sanitize("a") == "a"

    # --- Underscores must be replaced with hyphens ---

    def test_underscores_replaced_with_hyphens(self):
        """Underscores are NOT valid in Azure agent names — must become hyphens.

        This is the root cause of the Skill Creator bug:
        "skill_creator" was passed to Azure API which only allows hyphens.
        """
        assert self._sanitize("skill_creator") == "skill-creator"

    def test_multiple_underscores(self):
        """Multiple underscores each become a hyphen (then collapsed)."""
        assert self._sanitize("a__b___c") == "a-b-c"

    def test_mixed_underscores_and_hyphens(self):
        """Mix of underscores and hyphens normalizes to single hyphens."""
        assert self._sanitize("a_-_b") == "a-b"

    # --- Spaces must be replaced ---

    def test_spaces_replaced(self):
        """Spaces become hyphens."""
        assert self._sanitize("Skill Creator") == "Skill-Creator"

    def test_multiple_spaces(self):
        """Multiple spaces collapse to single hyphen."""
        assert self._sanitize("Skill   Creator") == "Skill-Creator"

    # --- Special characters ---

    def test_dots_replaced(self):
        """Dots become hyphens."""
        assert self._sanitize("Dr.Wang") == "Dr-Wang"

    def test_chinese_characters_replaced(self):
        """Chinese characters become hyphens."""
        assert self._sanitize("王医生") == "agent"  # all chars replaced → empty → fallback

    def test_mixed_chinese_and_ascii(self):
        """Mixed Chinese/ASCII: Chinese chars become hyphens, ASCII preserved."""
        result = self._sanitize("Dr-王医生-Chen")
        assert result == "Dr-Chen"

    def test_at_hash_dollar(self):
        """Special symbols become hyphens."""
        assert self._sanitize("a@b#c$d") == "a-b-c-d"

    # --- Leading/trailing hyphens stripped ---

    def test_leading_hyphens_stripped(self):
        """Leading hyphens are stripped (Azure requires alphanumeric start)."""
        assert self._sanitize("---test") == "test"

    def test_trailing_hyphens_stripped(self):
        """Trailing hyphens are stripped (Azure requires alphanumeric end)."""
        assert self._sanitize("test---") == "test"

    def test_both_ends_hyphens_stripped(self):
        """Both leading and trailing hyphens stripped."""
        assert self._sanitize("---test---") == "test"

    # --- Consecutive hyphens collapsed ---

    def test_consecutive_hyphens_collapsed(self):
        """Consecutive hyphens collapse to single hyphen."""
        assert self._sanitize("a--b---c") == "a-b-c"

    # --- Length limit ---

    def test_max_63_chars(self):
        """Output must not exceed 63 characters (Azure hard limit)."""
        long_name = "a" * 100
        result = self._sanitize(long_name)
        assert len(result) <= 63

    def test_exactly_63_chars_passes(self):
        """63-character name is within limit."""
        name = "a" * 63
        result = self._sanitize(name)
        assert len(result) == 63

    def test_64_chars_truncated(self):
        """64-character name is truncated to 63."""
        name = "a" * 64
        result = self._sanitize(name)
        assert len(result) == 63

    # --- Empty / whitespace fallback ---

    def test_empty_string_fallback(self):
        """Empty string falls back to default name."""
        result = self._sanitize("")
        assert result  # must not be empty
        assert result.isalnum()  # fallback must be valid

    def test_whitespace_only_fallback(self):
        """Whitespace-only string falls back to default name."""
        result = self._sanitize("   ")
        assert result
        assert result.isalnum()

    def test_all_special_chars_fallback(self):
        """All-special-char string falls back to default name."""
        result = self._sanitize("@#$%^&*()")
        assert result
        assert result.isalnum()

    # --- Azure format validation (regex) ---

    def test_result_matches_azure_pattern(self):
        """All sanitized results must match Azure's naming pattern."""
        import re

        pattern = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?$")
        test_inputs = [
            "skill_creator",
            "Skill Creator",
            "Dr. Wang Fang",
            "---invalid---",
            "a@b#c",
            "test",
            "a" * 100,
            "a_b_c",
        ]
        for name in test_inputs:
            result = self._sanitize(name)
            assert pattern.match(result), (
                f"Sanitized name '{result}' (from '{name}') doesn't match Azure pattern"
            )
            assert len(result) <= 63, f"Sanitized name '{result}' exceeds 63 chars"

    # --- Meta Skill default names ---

    def test_meta_skill_creator_name(self):
        """Default meta skill creator name must be valid after sanitization."""
        result = self._sanitize("skill-creator")
        assert result == "skill-creator"

    def test_meta_skill_evaluator_name(self):
        """Default meta skill evaluator name must be valid after sanitization."""
        result = self._sanitize("skill-evaluator")
        assert result == "skill-evaluator"

    def test_legacy_underscore_names_fixed(self):
        """Legacy underscore names (pre-fix) are properly converted."""
        assert self._sanitize("skill_creator") == "skill-creator"
        assert self._sanitize("skill_evaluator") == "skill-evaluator"
