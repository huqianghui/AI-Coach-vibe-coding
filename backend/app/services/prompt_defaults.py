"""Canonical default content + metadata for every registered project prompt.

For prompts that already exist as module-level constants, the default content is
imported directly from the source module so the registry default stays byte-identical
to the original hardcoded prompt (single source of truth, no transcription drift).

Dynamically-composed prompts (``hcp.system``, ``key_message.detection``) have no single
source constant, so a canonical ``{{placeholder}}`` template skeleton is defined here.
"""

import json
from typing import Any

from app.services.conference_prompt_config import DEFAULT_CONFERENCE_PROMPT_CONFIG
from app.services.dry_run_engine import _SOP_EVAL_PROMPT
from app.services.scoring_engine import SCORING_PROMPT_TEMPLATE
from app.services.skill_conversion_service import AI_FEEDBACK_PROMPT, SOP_EXTRACTION_PROMPT

# --- Canonical templates for dynamically-composed prompts -------------------

HCP_SYSTEM_DEFAULT = """# HCP Identity
You are Dr. {{name}}, a {{specialty}} specialist.
{{identity_extras}}

# Personality & Communication
Personality type: {{personality_type}}
Emotional state: {{emotional_state}}/100 (0=calm/neutral, 100=resistant/hostile)
Communication style: {{communication_style}}/100 (0=very direct, 100=very indirect)

{{personality_instruction}}

# Knowledge & Expertise
{{knowledge_section}}

# Scenario Context
Product under discussion: {{product}}
{{scenario_extras}}

# Key Messages (for your awareness)
{{key_messages_section}}"""

KEY_MESSAGE_DETECTION_DEFAULT = """# Key Message Detection Task

Analyze the MR's latest message in the context of the conversation to determine
which key messages have been delivered.

## Key Messages to Detect
{{key_messages_numbered}}

## Recent Conversation Context
{{history_text}}

## MR's Latest Message
{{mr_message}}

## Instructions
- A key message is considered "delivered" if the MR has communicated its core meaning,
  even if not word-for-word.
- Consider the context of the full conversation, not just the latest message.
- Only mark messages as delivered if the MR genuinely conveyed the information.

## Required Output
Return ONLY a JSON array of the key messages that were detected as delivered in this
latest message:

{{sample_json}}

Return an empty array [] if no key messages were detected in this message."""


# --- The unified catalog ----------------------------------------------------

PROMPT_DEFAULTS: dict[str, dict[str, Any]] = {
    "hcp.system": {
        "name": "HCP System Prompt",
        "category": "conversation",
        "description": "System prompt enforcing the digital HCP persona during F2F coaching.",
        "variables": [
            "name",
            "specialty",
            "identity_extras",
            "personality_type",
            "emotional_state",
            "communication_style",
            "personality_instruction",
            "knowledge_section",
            "product",
            "scenario_extras",
            "key_messages_section",
        ],
        "content": HCP_SYSTEM_DEFAULT,
    },
    "key_message.detection": {
        "name": "Key Message Detection",
        "category": "conversation",
        "description": "Detects which key messages the MR has delivered in the latest turn.",
        "variables": ["key_messages_numbered", "history_text", "mr_message", "sample_json"],
        "content": KEY_MESSAGE_DETECTION_DEFAULT,
    },
    "scoring.base": {
        "name": "Base Scoring Prompt",
        "category": "scoring",
        "description": "Default multi-dimensional content scoring prompt template.",
        "variables": [
            "hcp_name",
            "hcp_specialty",
            "hcp_personality",
            "hcp_comm_style",
            "product",
            "therapeutic_area",
            "difficulty",
            "key_messages_list",
            "key_messages_status",
            "skill_criteria_section",
            "transcript",
            "dimensions_config",
        ],
        "content": SCORING_PROMPT_TEMPLATE,
    },
    "scoring.rubric": {
        "name": "Rubric Scoring Prompt (global default)",
        "category": "scoring",
        "description": (
            "Global default rubric scoring template; per-rubric overrides live on ScoringRubric."
        ),
        "variables": [
            "hcp_name",
            "hcp_specialty",
            "hcp_personality",
            "hcp_comm_style",
            "product",
            "therapeutic_area",
            "difficulty",
            "key_messages_list",
            "key_messages_status",
            "skill_criteria_section",
            "transcript",
            "dimensions_config",
        ],
        "content": SCORING_PROMPT_TEMPLATE,
    },
    "conference.audience": {
        "name": "Conference Audience Prompt",
        "category": "conference",
        "description": "System prompt for a digital HCP in the conference audience.",
        "variables": [
            "hcp_name",
            "specialty",
            "role",
            "speaker_order",
            "speaker_priority",
            "speaker_order_policy",
        ],
        "content": DEFAULT_CONFERENCE_PROMPT_CONFIG["audience_prompt_template"],
    },
    "conference.moderator": {
        "name": "Conference Moderator Remarks",
        "category": "conference",
        "description": "Localized moderator remarks (invite/opening/handoff/closing) as JSON.",
        "variables": [],
        "content": json.dumps(
            DEFAULT_CONFERENCE_PROMPT_CONFIG["moderator_remarks"],
            ensure_ascii=False,
            indent=2,
        ),
    },
    "skill.sop_extraction": {
        "name": "Skill SOP Extraction",
        "category": "skill",
        "description": "Extracts a structured SOP from training material.",
        "variables": ["language_instruction"],
        "content": SOP_EXTRACTION_PROMPT,
    },
    "skill.ai_feedback": {
        "name": "Skill AI Feedback",
        "category": "skill",
        "description": "Applies requested modifications to an existing SOP.",
        "variables": ["current_content", "feedback", "language_instruction"],
        "content": AI_FEEDBACK_PROMPT,
    },
    "dry_run.sop_eval": {
        "name": "Dry Run SOP Evaluation",
        "category": "dry_run",
        "description": "Evaluates SOP coverage across a dry-run simulation transcript.",
        "variables": ["sop_steps_text", "transcript_text"],
        "content": _SOP_EVAL_PROMPT,
    },
}

# Convenience set of all registered keys.
PROMPT_KEYS: tuple[str, ...] = tuple(PROMPT_DEFAULTS.keys())
