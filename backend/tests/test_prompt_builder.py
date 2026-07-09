"""Tests for the prompt builder service: HCP system prompts, scoring, key message detection."""

import json

from app.models.hcp_profile import HcpProfile
from app.models.scenario import Scenario


def _make_hcp_profile(**overrides) -> HcpProfile:
    """Create a minimal HcpProfile ORM instance for prompt builder tests."""
    defaults = {
        "name": "Zhang Wei",
        "specialty": "Oncology",
        "hospital": "Beijing Cancer Hospital",
        "title": "Chief Physician",
        "personality_type": "skeptical",
        "emotional_state": 70,
        "communication_style": 40,
        "expertise_areas": json.dumps(["immunotherapy", "lung cancer"]),
        "prescribing_habits": "Conservative, evidence-based",
        "concerns": "Patient safety with novel treatments",
        "objections": json.dumps(["Lack of long-term data", "Cost concerns"]),
        "probe_topics": json.dumps(["survival data", "QoL"]),
        "difficulty": "hard",
        "is_active": True,
        "created_by": "user-1",
    }
    defaults.update(overrides)
    return HcpProfile(**defaults)


def _make_scenario(**overrides) -> Scenario:
    """Create a minimal Scenario ORM instance for prompt builder tests."""
    defaults = {
        "name": "Test Scenario",
        "tags": json.dumps(["product:Brukinsa", "area:Hematology"]),
        "hcp_profile_id": "profile-1",
        "key_messages": json.dumps(["Superior PFS vs ibrutinib", "Better safety profile"]),
        "rubric_id": "test-rubric-id",
        "pass_threshold": 70,
        "created_by": "user-1",
        "mode": "f2f",
        "status": "active",
        "skill_id": "test-skill-id",
    }
    defaults.update(overrides)
    return Scenario(**defaults)


class TestBuildHcpSystemPrompt:
    """Tests for build_hcp_system_prompt."""

    async def test_includes_hcp_identity(self):
        from app.services.prompt_builder import build_hcp_system_prompt

        hcp = _make_hcp_profile()
        scenario = _make_scenario()
        prompt = await build_hcp_system_prompt(hcp, scenario, ["Key msg 1"])

        assert "Dr. Zhang Wei" in prompt
        assert "Oncology" in prompt

    async def test_includes_hospital_and_title(self):
        from app.services.prompt_builder import build_hcp_system_prompt

        hcp = _make_hcp_profile(hospital="Peking Union", title="Associate Professor")
        scenario = _make_scenario()
        prompt = await build_hcp_system_prompt(hcp, scenario, [])

        assert "Peking Union" in prompt
        assert "Associate Professor" in prompt

    async def test_includes_personality_instruction_for_skeptical(self):
        from app.services.prompt_builder import build_hcp_system_prompt

        hcp = _make_hcp_profile(personality_type="skeptical")
        scenario = _make_scenario()
        prompt = await build_hcp_system_prompt(hcp, scenario, [])

        assert "SKEPTICAL" in prompt
        assert "push back on claims" in prompt

    async def test_includes_personality_instruction_for_busy(self):
        from app.services.prompt_builder import build_hcp_system_prompt

        hcp = _make_hcp_profile(personality_type="busy")
        scenario = _make_scenario()
        prompt = await build_hcp_system_prompt(hcp, scenario, [])

        assert "BUSY" in prompt
        assert "SHORT" in prompt

    async def test_unknown_personality_uses_default(self):
        from app.services.prompt_builder import build_hcp_system_prompt

        hcp = _make_hcp_profile(personality_type="unknown_type")
        scenario = _make_scenario()
        prompt = await build_hcp_system_prompt(hcp, scenario, [])

        assert "professional demeanor" in prompt

    async def test_includes_expertise_areas(self):
        from app.services.prompt_builder import build_hcp_system_prompt

        hcp = _make_hcp_profile(expertise_areas=json.dumps(["immunotherapy", "lung cancer"]))
        scenario = _make_scenario()
        prompt = await build_hcp_system_prompt(hcp, scenario, [])

        assert "immunotherapy" in prompt
        assert "lung cancer" in prompt

    async def test_includes_objections(self):
        from app.services.prompt_builder import build_hcp_system_prompt

        hcp = _make_hcp_profile(objections=json.dumps(["Lack of long-term data", "Too expensive"]))
        scenario = _make_scenario()
        prompt = await build_hcp_system_prompt(hcp, scenario, [])

        assert "Lack of long-term data" in prompt
        assert "Too expensive" in prompt

    async def test_includes_scenario_product(self):
        from app.services.prompt_builder import build_hcp_system_prompt

        hcp = _make_hcp_profile()
        scenario = _make_scenario(tags=json.dumps(["product:Tislelizumab"]))
        prompt = await build_hcp_system_prompt(hcp, scenario, [])

        assert "Tislelizumab" in prompt

    async def test_includes_key_messages(self):
        from app.services.prompt_builder import build_hcp_system_prompt

        hcp = _make_hcp_profile()
        scenario = _make_scenario()
        key_msgs = ["Superior PFS data", "Better safety"]
        prompt = await build_hcp_system_prompt(hcp, scenario, key_msgs)

        assert "Superior PFS data" in prompt
        assert "Better safety" in prompt

    async def test_omits_key_messages_section_when_empty(self):
        from app.services.prompt_builder import build_hcp_system_prompt

        hcp = _make_hcp_profile()
        scenario = _make_scenario()
        prompt = await build_hcp_system_prompt(hcp, scenario, [])

        assert "Key Messages (for your awareness)" not in prompt

    async def test_includes_rules_section(self):
        from app.services.prompt_builder import build_hcp_system_prompt

        hcp = _make_hcp_profile()
        scenario = _make_scenario()
        prompt = await build_hcp_system_prompt(hcp, scenario, [])

        assert "Stay STRICTLY in character" in prompt
        assert "Do NOT provide coaching feedback" in prompt


class TestBuildScoringPrompt:
    """Tests for build_scoring_prompt."""

    async def test_includes_scoring_dimensions(self):
        from app.services.prompt_builder import build_scoring_prompt

        scenario = _make_scenario()
        transcript = [
            {"role": "user", "content": "Hello doctor"},
            {"role": "assistant", "content": "Hi, what brings you here?"},
        ]
        prompt = build_scoring_prompt(scenario, transcript, ["Key msg 1"])

        assert "key_message" in prompt
        assert "objection_handling" in prompt
        assert "communication" in prompt
        assert "product_knowledge" in prompt
        assert "scientific_info" in prompt

    async def test_includes_weights_from_rubric_dimensions(self):
        from app.services.prompt_builder import build_scoring_prompt

        scenario = _make_scenario()
        rubric_dims = [
            {"name": "key_message", "weight": 40, "criteria": []},
            {"name": "objection_handling", "weight": 20, "criteria": []},
            {"name": "communication", "weight": 20, "criteria": []},
            {"name": "product_knowledge", "weight": 10, "criteria": []},
            {"name": "scientific_info", "weight": 10, "criteria": []},
        ]
        transcript = [{"role": "user", "content": "Test"}]
        prompt = build_scoring_prompt(scenario, transcript, [], rubric_dimensions=rubric_dims)

        assert "weight: 40" in prompt
        assert "weight: 20" in prompt

    async def test_formats_transcript_with_mr_and_hcp_labels(self):
        from app.services.prompt_builder import build_scoring_prompt

        scenario = _make_scenario()
        transcript = [
            {"role": "user", "content": "I want to discuss Brukinsa"},
            {"role": "assistant", "content": "Go ahead"},
        ]
        prompt = build_scoring_prompt(scenario, transcript, [])

        assert "MR: I want to discuss Brukinsa" in prompt
        assert "HCP: Go ahead" in prompt

    async def test_includes_key_messages_in_scoring_prompt(self):
        from app.services.prompt_builder import build_scoring_prompt

        scenario = _make_scenario()
        key_msgs = ["Superior PFS data", "Favorable safety"]
        prompt = build_scoring_prompt(scenario, [], key_msgs)

        assert "Superior PFS data" in prompt
        assert "Favorable safety" in prompt

    async def test_requires_json_output_format(self):
        from app.services.prompt_builder import build_scoring_prompt

        scenario = _make_scenario()
        prompt = build_scoring_prompt(scenario, [], [])

        assert "Return ONLY valid JSON" in prompt
        assert "overall_feedback" in prompt


class TestBuildKeyMessageDetectionPrompt:
    """Tests for build_key_message_detection_prompt."""

    async def test_includes_key_messages_list(self):
        from app.services.prompt_builder import build_key_message_detection_prompt

        key_msgs = ["Superior PFS", "Better safety profile"]
        prompt = await build_key_message_detection_prompt(key_msgs, "test message", [])

        assert "Superior PFS" in prompt
        assert "Better safety profile" in prompt

    async def test_includes_mr_latest_message(self):
        from app.services.prompt_builder import build_key_message_detection_prompt

        prompt = await build_key_message_detection_prompt(
            ["Key msg"], "Brukinsa shows superior PFS data", []
        )

        assert "Brukinsa shows superior PFS data" in prompt

    async def test_truncates_long_conversation_history(self):
        from app.services.prompt_builder import build_key_message_detection_prompt

        history = [{"role": "user", "content": f"Message {i}"} for i in range(10)]
        prompt = await build_key_message_detection_prompt(["Key msg"], "latest", history)

        # Should only include the last 6 messages
        assert "Message 4" in prompt
        assert "Message 9" in prompt
        # Message 0-3 should not appear (only last 6: 4,5,6,7,8,9)
        assert "Message 3" not in prompt

    async def test_short_history_included_fully(self):
        from app.services.prompt_builder import build_key_message_detection_prompt

        history = [
            {"role": "user", "content": "First message"},
            {"role": "assistant", "content": "Response"},
        ]
        prompt = await build_key_message_detection_prompt(["Key msg"], "latest", history)

        assert "First message" in prompt
        assert "Response" in prompt

    async def test_returns_json_array_example(self):
        from app.services.prompt_builder import build_key_message_detection_prompt

        prompt = await build_key_message_detection_prompt(["Superior PFS", "Safety"], "test", [])

        assert "Return ONLY a JSON array" in prompt
        assert "empty array []" in prompt
