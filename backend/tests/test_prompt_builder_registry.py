"""Registry-integration tests for prompt builders.

Task 1 (snapshot regression): with the seeded default active in the registry,
every builder produces output byte-identical to the legacy imperative/constant
path. This guards against silent drift when routing prompts through the registry.

Task 3 (admin overrides): activating a modified template version changes builder
output, and per-entity overrides still take precedence over the registry base.
"""

import json

import pytest
from sqlalchemy import select

from app.models.hcp_profile import HcpProfile
from app.models.prompt_template import PromptTemplate
from app.models.prompt_version import PromptVersion
from app.models.scenario import Scenario
from app.services.conference_prompt_config import DEFAULT_CONFERENCE_PROMPT_CONFIG
from app.services.prompt_builder import (
    build_conference_audience_prompt,
    build_hcp_system_prompt,
    build_key_message_detection_prompt,
)
from app.services.prompt_registry import get_prompt, seed_prompt_registry
from app.services.scoring_engine import SCORING_PROMPT_TEMPLATE, build_scoring_prompt


@pytest.fixture
async def session(db_session):
    return db_session


def _make_hcp_profile(**overrides) -> HcpProfile:
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


async def _activate_override(session, key: str, content: str) -> None:
    """Deactivate the seeded version and activate a new manual override version."""
    template = (
        await session.execute(select(PromptTemplate).where(PromptTemplate.key == key))
    ).scalar_one()
    seed_version = (
        await session.execute(
            select(PromptVersion).where(PromptVersion.id == template.active_version_id)
        )
    ).scalar_one()
    seed_version.is_active = False

    override = PromptVersion(
        template_id=template.id,
        version_no=2,
        content=content,
        source="manual",
        is_active=True,
    )
    session.add(override)
    await session.flush()
    template.active_version_id = override.id
    await session.commit()


# ---------------------------------------------------------------------------
# Task 1: snapshot regression -- seeded default == legacy output (byte-identical)
# ---------------------------------------------------------------------------


class TestSnapshotRegressionDefaults:
    """With the seeded default active, builders match the legacy path exactly."""

    async def test_hcp_system_default_is_byte_identical(self, session):
        await seed_prompt_registry(session)
        hcp = _make_hcp_profile()
        scenario = _make_scenario()
        key_messages = ["Superior PFS", "Favorable safety profile"]

        legacy = await build_hcp_system_prompt(hcp, scenario, key_messages, db=None)
        via_registry = await build_hcp_system_prompt(hcp, scenario, key_messages, db=session)

        assert via_registry == legacy

    async def test_key_message_detection_default_is_byte_identical(self, session):
        await seed_prompt_registry(session)
        key_messages = ["Superior PFS", "Favorable safety profile"]
        mr_message = "Our drug shows superior progression-free survival."
        history = [
            {"role": "user", "content": "Hello doctor"},
            {"role": "assistant", "content": "What do you have for me?"},
        ]

        legacy = await build_key_message_detection_prompt(
            key_messages, mr_message, history, db=None
        )
        via_registry = await build_key_message_detection_prompt(
            key_messages, mr_message, history, db=session
        )

        assert via_registry == legacy

    async def test_scoring_base_default_is_byte_identical(self, session):
        await seed_prompt_registry(session)
        scenario_data = {
            "key_messages": ["Superior PFS", "Favorable safety profile"],
            "product": "Brukinsa",
            "therapeutic_area": "Hematology",
            "difficulty": "hard",
            "hcp_profile": {
                "name": "Zhang Wei",
                "specialty": "Oncology",
                "personality_type": "skeptical",
                "communication_style": "40",
            },
        }
        messages = [
            {"role": "user", "content": "Our drug shows superior PFS."},
            {"role": "assistant", "content": "Show me the data."},
        ]
        key_messages_status = [
            {"message": "Superior PFS", "delivered": True},
            {"message": "Favorable safety profile", "delivered": False},
        ]
        rubric_dimensions = [
            {"name": "key_message", "weight": 50, "criteria": []},
            {"name": "communication", "weight": 50, "criteria": []},
        ]

        base_template = await get_prompt(session, "scoring.base")
        assert base_template == SCORING_PROMPT_TEMPLATE

        legacy = build_scoring_prompt(
            scenario_data, messages, key_messages_status, rubric_dimensions, base_template=""
        )
        via_registry = build_scoring_prompt(
            scenario_data,
            messages,
            key_messages_status,
            rubric_dimensions,
            base_template=base_template,
        )

        assert via_registry == legacy

    async def test_conference_audience_default_is_byte_identical(self, session):
        await seed_prompt_registry(session)
        hcp_config = {
            "name": "Li Ming",
            "specialty": "Cardiology",
            "personality_type": "analytical",
            "role": "audience",
        }
        scenario = _make_scenario()

        legacy = build_conference_audience_prompt(
            hcp_config=hcp_config,
            scenario=scenario,
            presentation_topic="Brukinsa efficacy",
            conversation_history=[],
            other_hcp_questions=[],
            base_template=None,
        )
        base_template = await get_prompt(session, "conference.audience")
        assert base_template == DEFAULT_CONFERENCE_PROMPT_CONFIG["audience_prompt_template"]

        via_registry = build_conference_audience_prompt(
            hcp_config=hcp_config,
            scenario=scenario,
            presentation_topic="Brukinsa efficacy",
            conversation_history=[],
            other_hcp_questions=[],
            base_template=base_template,
        )

        assert via_registry == legacy


# ---------------------------------------------------------------------------
# Task 3: admin overrides change output; per-entity overrides win
# ---------------------------------------------------------------------------


class TestAdminOverrides:
    """Activating a modified template version changes builder output."""

    async def test_hcp_system_override_changes_output(self, session):
        await seed_prompt_registry(session)
        override_template = (
            "CUSTOM HCP TEMPLATE\n"
            "Doctor: {{name}}\n"
            "Specialty: {{specialty}}\n"
            "Behavior: {{personality_instruction}}\n"
            "Product: {{product}}"
        )
        await _activate_override(session, "hcp.system", override_template)

        hcp = _make_hcp_profile()
        scenario = _make_scenario()
        result = await build_hcp_system_prompt(hcp, scenario, [], db=session)

        legacy = await build_hcp_system_prompt(hcp, scenario, [], db=None)
        assert result != legacy
        assert result.startswith("CUSTOM HCP TEMPLATE")
        assert "Doctor: Zhang Wei" in result
        assert "Specialty: Oncology" in result
        assert "Product: Brukinsa" in result
        # Unknown tokens are not present -- the safe renderer only substitutes known keys.
        assert "{{name}}" not in result

    async def test_key_message_detection_override_changes_output(self, session):
        await seed_prompt_registry(session)
        override_template = (
            "CUSTOM DETECTION\n"
            "Messages:\n{{key_messages_numbered}}\n"
            "Latest: {{mr_message}}\n"
            "Example: {{sample_json}}"
        )
        await _activate_override(session, "key_message.detection", override_template)

        key_messages = ["Superior PFS", "Favorable safety profile"]
        mr_message = "Our drug shows superior PFS."
        result = await build_key_message_detection_prompt(key_messages, mr_message, [], db=session)

        assert result.startswith("CUSTOM DETECTION")
        assert "1. Superior PFS" in result
        assert "Latest: Our drug shows superior PFS." in result

    async def test_conference_audience_override_changes_output(self, session):
        await seed_prompt_registry(session)
        override_template = "OVERRIDE AUDIENCE for {hcp_name} the {specialty} discussing {product}"
        await _activate_override(session, "conference.audience", override_template)

        hcp_config = {
            "name": "Li Ming",
            "specialty": "Cardiology",
            "personality_type": "analytical",
            "role": "audience",
        }
        scenario = _make_scenario()
        base_template = await get_prompt(session, "conference.audience")

        result = build_conference_audience_prompt(
            hcp_config=hcp_config,
            scenario=scenario,
            presentation_topic="",
            conversation_history=[],
            other_hcp_questions=[],
            base_template=base_template,
        )

        assert result.startswith("OVERRIDE AUDIENCE for Li Ming the Cardiology")
        assert "Brukinsa" in result

    async def test_scoring_per_entity_override_wins_over_registry_base(self, session):
        await seed_prompt_registry(session)
        # Activate a registry base override -- it must be ignored when a per-entity
        # (rubric) prompt_template is supplied.
        await _activate_override(session, "scoring.base", "REGISTRY BASE {transcript}")

        scenario_data = {
            "key_messages": ["Superior PFS"],
            "product": "Brukinsa",
            "hcp_profile": {"name": "Zhang Wei", "specialty": "Oncology"},
        }
        messages = [{"role": "user", "content": "Our drug shows superior PFS."}]
        key_messages_status = [{"message": "Superior PFS", "delivered": True}]
        rubric_dimensions = [{"name": "key_message", "weight": 100, "criteria": []}]

        base_template = await get_prompt(session, "scoring.base")
        assert base_template == "REGISTRY BASE {transcript}"

        per_entity = "PER-ENTITY RUBRIC PROMPT: {transcript}"
        result = build_scoring_prompt(
            scenario_data,
            messages,
            key_messages_status,
            rubric_dimensions,
            prompt_template=per_entity,
            base_template=base_template,
        )

        assert result.startswith("PER-ENTITY RUBRIC PROMPT:")
        assert "REGISTRY BASE" not in result
