"""Tests for scoring engine post-validation rules and prompt strengthening.

Verifies:
- _enforce_scoring_rules() caps key_message to 30 when all undelivered
- _enforce_scoring_rules() caps all dimensions to 50 when undelivered + short MR content
- build_scoring_prompt() uses strong role labels in transcript
- Critical scoring rules appear near end of prompt
- score_with_llm() applies post-validation before returning
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.scoring_engine import (
    _enforce_scoring_rules,
    build_scoring_prompt,
)

DEFAULT_RUBRIC_DIMENSIONS = [
    {"name": "key_message", "weight": 30, "criteria": [], "max_score": 100.0},
    {"name": "objection_handling", "weight": 25, "criteria": [], "max_score": 100.0},
    {"name": "communication", "weight": 20, "criteria": [], "max_score": 100.0},
    {"name": "product_knowledge", "weight": 15, "criteria": [], "max_score": 100.0},
    {"name": "scientific_info", "weight": 10, "criteria": [], "max_score": 100.0},
]


class TestEnforceScoringRules:
    """Unit tests for _enforce_scoring_rules() post-validation logic."""

    def test_caps_key_message_when_all_undelivered_and_score_above_30(self):
        """When all key_messages have delivered=false, key_message score capped at 30."""
        dimensions = [
            {"dimension": "key_message", "score": 85, "weight": 30},
            {"dimension": "objection_handling", "score": 70, "weight": 25},
            {"dimension": "communication", "score": 75, "weight": 20},
        ]
        key_messages_status = [
            {"message": "PFS data", "delivered": False},
            {"message": "Safety profile", "delivered": False},
        ]
        messages = [
            {
                "role": "user",
                "content": (
                    "I want to discuss the clinical efficacy and tolerability"
                    " data for our product in the context of CLL treatment"
                    " options available today."
                ),
            },
            {"role": "assistant", "content": "Tell me more about that."},
        ]

        result = _enforce_scoring_rules(dimensions, key_messages_status, messages)

        # key_message should be capped to 30
        key_msg_dim = next(d for d in result if d["dimension"] == "key_message")
        assert key_msg_dim["score"] == 30
        # other dimensions should remain untouched (MR content is >100 chars)
        obj_dim = next(d for d in result if d["dimension"] == "objection_handling")
        assert obj_dim["score"] == 70

    def test_no_change_when_key_message_already_below_30(self):
        """When key_message score already below 30 and all undelivered, no change."""
        dimensions = [
            {"dimension": "key_message", "score": 20, "weight": 30},
            {"dimension": "communication", "score": 75, "weight": 20},
        ]
        key_messages_status = [
            {"message": "PFS data", "delivered": False},
        ]
        messages = [
            {
                "role": "user",
                "content": (
                    "I talked about many interesting clinical topics with"
                    " data and evidence from trials and studies."
                ),
            },
        ]

        result = _enforce_scoring_rules(dimensions, key_messages_status, messages)

        key_msg_dim = next(d for d in result if d["dimension"] == "key_message")
        assert key_msg_dim["score"] == 20  # unchanged

    def test_no_capping_when_some_key_messages_delivered(self):
        """When at least one key_message is delivered, no capping is applied."""
        dimensions = [
            {"dimension": "key_message", "score": 85, "weight": 30},
            {"dimension": "communication", "score": 90, "weight": 20},
        ]
        key_messages_status = [
            {"message": "PFS data", "delivered": True},
            {"message": "Safety profile", "delivered": False},
        ]
        messages = [
            {"role": "user", "content": "Hi"},
        ]

        result = _enforce_scoring_rules(dimensions, key_messages_status, messages)

        key_msg_dim = next(d for d in result if d["dimension"] == "key_message")
        assert key_msg_dim["score"] == 85  # no capping
        comm_dim = next(d for d in result if d["dimension"] == "communication")
        assert comm_dim["score"] == 90  # no capping

    def test_caps_all_dimensions_when_undelivered_and_short_mr_content(self):
        """When all undelivered AND MR total < 100 chars, ALL dims capped to 50."""
        dimensions = [
            {"dimension": "key_message", "score": 85, "weight": 30},
            {"dimension": "objection_handling", "score": 70, "weight": 25},
            {"dimension": "communication", "score": 90, "weight": 20},
            {"dimension": "product_knowledge", "score": 80, "weight": 15},
        ]
        key_messages_status = [
            {"message": "PFS data", "delivered": False},
            {"message": "Safety profile", "delivered": False},
        ]
        # Very short MR messages (< 100 chars total)
        messages = [
            {"role": "user", "content": "Hi doctor"},
            {"role": "assistant", "content": "Hello, how can I help?"},
            {"role": "user", "content": "Thanks bye"},
        ]

        result = _enforce_scoring_rules(dimensions, key_messages_status, messages)

        # key_message capped to 30 (specific rule)
        key_msg_dim = next(d for d in result if d["dimension"] == "key_message")
        assert key_msg_dim["score"] == 30
        # ALL other dims capped to 50
        for dim in result:
            if dim["dimension"] != "key_message":
                assert dim["score"] <= 50, f"{dim['dimension']} should be capped to 50"

    def test_only_key_message_capped_when_undelivered_but_substantive(self):
        """When all undelivered but MR > 200 chars, only key_message capped."""
        dimensions = [
            {"dimension": "key_message", "score": 85, "weight": 30},
            {"dimension": "objection_handling", "score": 70, "weight": 25},
            {"dimension": "communication", "score": 90, "weight": 20},
        ]
        key_messages_status = [
            {"message": "PFS data", "delivered": False},
            {"message": "Safety profile", "delivered": False},
        ]
        # Substantive MR messages (> 200 chars total)
        messages = [
            {
                "role": "user",
                "content": (
                    "Doctor, I'd like to discuss some important clinical"
                    " data about treatment options for your patients with"
                    " chronic lymphocytic leukemia. Our recent studies"
                    " show some very interesting findings that I think"
                    " could help your patients significantly."
                ),
            },
            {"role": "assistant", "content": "That sounds interesting."},
        ]

        result = _enforce_scoring_rules(dimensions, key_messages_status, messages)

        # key_message capped to 30
        key_msg_dim = next(d for d in result if d["dimension"] == "key_message")
        assert key_msg_dim["score"] == 30
        # other dims NOT capped
        obj_dim = next(d for d in result if d["dimension"] == "objection_handling")
        assert obj_dim["score"] == 70
        comm_dim = next(d for d in result if d["dimension"] == "communication")
        assert comm_dim["score"] == 90

    def test_no_capping_when_empty_key_messages_status(self):
        """When key_messages_status is empty, no capping (nothing to evaluate)."""
        dimensions = [
            {"dimension": "key_message", "score": 85, "weight": 30},
            {"dimension": "communication", "score": 90, "weight": 20},
        ]
        key_messages_status = []
        messages = [
            {"role": "user", "content": "Hi"},
        ]

        result = _enforce_scoring_rules(dimensions, key_messages_status, messages)

        key_msg_dim = next(d for d in result if d["dimension"] == "key_message")
        assert key_msg_dim["score"] == 85  # unchanged
        comm_dim = next(d for d in result if d["dimension"] == "communication")
        assert comm_dim["score"] == 90  # unchanged


class TestBuildScoringPromptRoleLabels:
    """Tests for strengthened role labels in build_scoring_prompt."""

    def _build_basic_prompt(self, messages=None):
        """Helper to build a prompt with defaults."""
        if messages is None:
            messages = [
                {
                    "role": "user",
                    "content": "Hello doctor, I have data to share.",
                },
                {"role": "assistant", "content": "What data?"},
            ]
        return build_scoring_prompt(
            scenario_data={
                "product": "Brukinsa",
                "therapeutic_area": "Oncology",
                "difficulty": "medium",
                "key_messages": json.dumps(["PFS data", "Safety"]),
                "hcp_profile": {"name": "Dr. Li", "specialty": "Hematology"},
            },
            messages=messages,
            key_messages_status=[
                {"message": "PFS data", "delivered": True},
                {"message": "Safety", "delivered": False},
            ],
            rubric_dimensions=DEFAULT_RUBRIC_DIMENSIONS,
        )

    def test_prompt_contains_strong_mr_role_label(self):
        """Transcript uses '>>> MR (EVALUATE THIS PERSON) <<<' label."""
        prompt = self._build_basic_prompt()
        assert ">>> MR (EVALUATE THIS PERSON) <<<" in prompt

    def test_prompt_contains_strong_hcp_role_label(self):
        """Transcript uses '>>> HCP (DO NOT EVALUATE) <<<' label."""
        prompt = self._build_basic_prompt()
        assert ">>> HCP (DO NOT EVALUATE) <<<" in prompt

    def test_critical_rules_near_end_of_prompt(self):
        """Critical scoring rules appear in the last 40 lines of the prompt."""
        prompt = self._build_basic_prompt()
        lines = prompt.strip().split("\n")
        last_40_lines = "\n".join(lines[-40:])
        # Critical rules section should be near the end
        assert "CRITICAL SCORING RULES" in last_40_lines

    def test_critical_rules_before_json_format(self):
        """Critical scoring rules appear BEFORE the JSON output format."""
        prompt = self._build_basic_prompt()
        critical_pos = prompt.find("CRITICAL SCORING RULES")
        json_pos = prompt.find('"dimensions"')
        assert critical_pos > 0, "CRITICAL SCORING RULES not found"
        assert json_pos > 0, "JSON format section not found"
        assert critical_pos < json_pos, "Critical rules should come before JSON format"

    def test_reminder_line_before_json(self):
        """A reminder about evaluating MR only appears right before JSON."""
        prompt = self._build_basic_prompt()
        assert "REMINDER:" in prompt
        # The reminder should mention MR performance
        reminder_idx = prompt.find("REMINDER:")
        snippet = prompt[reminder_idx : reminder_idx + 200]
        assert "MR" in snippet

    def test_uses_custom_prompt_template_when_provided(self):
        """Rubric prompt_template overrides the built-in prompt body."""
        prompt = build_scoring_prompt(
            scenario_data={
                "product": "Brukinsa",
                "therapeutic_area": "Oncology",
                "difficulty": "medium",
                "key_messages": json.dumps(["PFS data"]),
                "hcp_profile": {"name": "Dr. Li", "specialty": "Hematology"},
            },
            messages=[{"role": "user", "content": "Hello doctor"}],
            key_messages_status=[{"message": "PFS data", "delivered": False}],
            rubric_dimensions=DEFAULT_RUBRIC_DIMENSIONS,
            prompt_template="CUSTOM PROMPT\n{transcript}\n{dimensions_config}",
        )

        assert prompt.startswith("CUSTOM PROMPT")
        assert ">>> MR (EVALUATE THIS PERSON) <<<: Hello doctor" in prompt
        assert "key_message (weight=30%)" in prompt

    def test_custom_prompt_template_allows_json_braces(self):
        """Custom templates can include JSON examples without escaping braces."""
        prompt = build_scoring_prompt(
            scenario_data={"hcp_profile": {"name": "Dr. Li"}},
            messages=[{"role": "user", "content": "I discussed efficacy."}],
            key_messages_status=[],
            rubric_dimensions=DEFAULT_RUBRIC_DIMENSIONS,
            prompt_template='Return JSON: {"summary": "..."}\nTranscript:\n{transcript}',
        )

        assert 'Return JSON: {"summary": "..."}' in prompt
        assert ">>> MR (EVALUATE THIS PERSON) <<<: I discussed efficacy." in prompt

    def test_custom_prompt_template_renders_non_string_values(self):
        """Custom templates render numeric scenario/HCP values safely."""
        prompt = build_scoring_prompt(
            scenario_data={
                "hcp_profile": {
                    "name": "Dr. Li",
                    "communication_style": 50,
                }
            },
            messages=[],
            key_messages_status=[],
            rubric_dimensions=DEFAULT_RUBRIC_DIMENSIONS,
            prompt_template="Communication style: {hcp_comm_style}",
        )

        assert prompt == "Communication style: 50"


class TestScoreWithLlmPostValidation:
    """Tests that score_with_llm() applies post-validation rules."""

    @patch(
        "app.services.azure_auth.get_azure_openai_client",
        new_callable=AsyncMock,
    )
    @patch("app.services.scoring_engine.config_service")
    async def test_score_with_llm_caps_scores_when_all_undelivered(
        self, mock_config, mock_get_client
    ):
        """score_with_llm applies post-validation capping when all undelivered."""
        from app.services.scoring_engine import score_with_llm

        # Setup mocks
        mock_config.get_effective_endpoint = AsyncMock(return_value="https://test.openai.azure.com")
        mock_config.get_effective_key = AsyncMock(return_value="test-key")
        mock_config_obj = MagicMock()
        mock_config_obj.model_or_deployment = "gpt-4o"
        mock_config.get_config = AsyncMock(return_value=mock_config_obj)

        # Mock OpenAI response with high scores
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(
            {
                "dimensions": [
                    {
                        "dimension": "key_message",
                        "score": 85,
                        "weight": 30,
                        "strengths": [],
                        "weaknesses": [],
                        "suggestions": [],
                    },
                    {
                        "dimension": "objection_handling",
                        "score": 70,
                        "weight": 25,
                        "strengths": [],
                        "weaknesses": [],
                        "suggestions": [],
                    },
                    {
                        "dimension": "communication",
                        "score": 75,
                        "weight": 20,
                        "strengths": [],
                        "weaknesses": [],
                        "suggestions": [],
                    },
                    {
                        "dimension": "product_knowledge",
                        "score": 72,
                        "weight": 15,
                        "strengths": [],
                        "weaknesses": [],
                        "suggestions": [],
                    },
                    {
                        "dimension": "scientific_info",
                        "score": 68,
                        "weight": 10,
                        "strengths": [],
                        "weaknesses": [],
                        "suggestions": [],
                    },
                ],
                "feedback_summary": "Good performance overall.",
            }
        )
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        db = AsyncMock()
        scenario_data = {
            "product": "Brukinsa",
            "therapeutic_area": "Oncology",
            "difficulty": "medium",
            "key_messages": json.dumps(["PFS data", "Safety"]),
            "hcp_profile": {"name": "Dr. Li", "specialty": "Hematology"},
        }
        # ALL key messages undelivered
        key_messages_status = [
            {"message": "PFS data", "delivered": False},
            {"message": "Safety", "delivered": False},
        ]
        # Short MR content (< 100 chars)
        messages = [
            {"role": "user", "content": "Hi doctor"},
            {"role": "assistant", "content": "Hello, how can I help?"},
        ]

        result = await score_with_llm(
            db=db,
            scenario_data=scenario_data,
            messages=messages,
            key_messages_status=key_messages_status,
            rubric_dimensions=DEFAULT_RUBRIC_DIMENSIONS,
        )

        # Post-validation should have capped key_message to 30
        dims = result["dimensions"]
        key_msg = next(d for d in dims if d["dimension"] == "key_message")
        assert key_msg["score"] == 30

        # All undelivered + short content -> all dims capped to 50
        for dim in dims:
            if dim["dimension"] == "key_message":
                assert dim["score"] <= 30
            else:
                assert dim["score"] <= 50
