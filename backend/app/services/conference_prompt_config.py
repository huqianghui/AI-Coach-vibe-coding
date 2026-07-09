"""Default conference prompt configuration and safe template rendering."""

import copy
import json
from typing import Any

DEFAULT_CONFERENCE_PROMPT_CONFIG: dict[str, Any] = {
    "speaker_order_policy": (
        "Use the configured audience order as the speaking order. The first non-moderator "
        "HCP is the primary questioner and should ask the most strategically important "
        "question. Later HCPs are secondary questioners and should cover different angles."
    ),
    "moderator_remarks": {
        "invite": {
            "zh": "欢迎参加本次会议。请先进行你的主题演讲，演讲结束后我会组织各位专家依次提问。",
            "en": (
                "Welcome to the meeting. Please begin your presentation first; "
                "afterward, I will invite each expert to ask questions in turn."
            ),
        },
        "opening": {
            "zh": "感谢刚才的精彩演讲。下面进入问答环节，有请在座的各位专家依次提问。",
            "en": (
                "Thank you for the presentation. Let us now open the floor for "
                "questions from our panel."
            ),
        },
        "handoff": {
            "zh": "感谢刚才的交流。下面有请下一位专家继续提问。",
            "en": (
                "Thank you for that exchange. I will now invite the next expert to ask a question."
            ),
        },
        "closing": {
            "zh": "感谢各位专家的提问与精彩讨论，本次问答环节到此结束，谢谢大家。",
            "en": (
                "Thank you all for your questions and the insightful discussion. "
                "This concludes our Q&A session."
            ),
        },
    },
    "audience_prompt_template": """# Conference Audience Role
You are Dr. {hcp_name}, a {specialty} specialist attending a medical conference.
You are a {role} member in the audience.
Audience order: {speaker_order}. Speaker priority: {speaker_priority}.

# Speaking Policy
{speaker_order_policy}

# Personality
{personality_instruction}

# Presentation Context
The Medical Representative is presenting about: {product}
Therapeutic area: {therapeutic_area}
Presentation topic: {presentation_topic}

# Conversation So Far
{conversation_history}

# Questions Already Asked by Other Audience Members
{other_hcp_questions}

# Grounding Rules
- Never claim the MR mentioned clinical trials, data, efficacy, safety, sample size, or
    any specific topic unless it appears in the conversation so far.
- If the MR only greets you or gives a vague answer, ask them to clarify or provide
    details instead of inventing missing content.
- Keep following up on the current thread until the point is reasonably clear.

# Instructions
Respond as this HCP in a natural conference conversation with the MR.
- React directly to the MR's latest input and the conversation so far.
- If you are taking the floor for the first time, ask one relevant question.
- If the MR has just answered you, acknowledge the answer and ask at most one contextual
    follow-up if needed.
- Do not ignore the MR's answer and jump to an unrelated topic.
- Do not repeat questions already asked by other HCPs.
- Respond in the same language the MR uses (Chinese or English).
- Keep your response concise (1-3 sentences).
- Do NOT provide coaching feedback. You ARE a conference attendee.""",
}


def default_conference_prompt_config() -> dict[str, Any]:
    """Return a deep copy of the default conference prompt config."""
    return copy.deepcopy(DEFAULT_CONFERENCE_PROMPT_CONFIG)


def normalize_conference_prompt_config(raw_config: str | dict[str, Any] | None) -> dict[str, Any]:
    """Merge stored config over defaults, tolerating malformed/partial JSON."""
    merged = default_conference_prompt_config()
    if not raw_config:
        return merged

    try:
        parsed = json.loads(raw_config) if isinstance(raw_config, str) else raw_config
    except (TypeError, json.JSONDecodeError):
        return merged

    if not isinstance(parsed, dict):
        return merged

    if isinstance(parsed.get("speaker_order_policy"), str):
        merged["speaker_order_policy"] = parsed["speaker_order_policy"]
    if isinstance(parsed.get("audience_prompt_template"), str):
        merged["audience_prompt_template"] = parsed["audience_prompt_template"]

    moderator_remarks = parsed.get("moderator_remarks")
    if isinstance(moderator_remarks, dict):
        for phase, langs in moderator_remarks.items():
            if phase not in merged["moderator_remarks"] or not isinstance(langs, dict):
                continue
            for lang, text in langs.items():
                if lang in ("zh", "en") and isinstance(text, str):
                    merged["moderator_remarks"][phase][lang] = text

    return merged


def render_prompt_template(template: str, values: dict[str, Any]) -> str:
    """Render known placeholders without interpreting unrelated braces."""
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", str(value or ""))
    return rendered


def render_double_brace_template(template: str, values: dict[str, Any]) -> str:
    """Render ``{{placeholder}}`` tokens safely (missing/extra tokens do not crash)."""
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", str(value if value is not None else ""))
    return rendered
