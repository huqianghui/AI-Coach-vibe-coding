"""LLM-based content scoring engine for multi-dimensional coaching evaluation.

Primary content scoring engine using Azure OpenAI (GPT-4o) with structured JSON output.
Produces real scoring based on conversation transcript, HCP profile, scenario objectives,
key message delivery status, and the scenario scoring rubric.

Voice scoring is handled separately by cu_evaluation_service.score_voice_with_cu().
"""

import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import config_service
from app.utils.exceptions import ScoringUnavailableException

logger = logging.getLogger(__name__)

SCORING_PROMPT_TEMPLATE = """You are an expert pharmaceutical sales training evaluator for BeiGene.
You evaluate ONLY the Medical Representative (MR, role="user") performance.
DO NOT evaluate the HCP (role="assistant") performance.
Be strict: vague or off-topic responses deserve low scores.

Analyze the following MR conversation with a
Healthcare Professional (HCP) and provide a detailed multi-dimensional scoring.

## HCP Profile
- Name: {hcp_name}
- Specialty: {hcp_specialty}
- Personality: {hcp_personality}
- Communication Style: {hcp_comm_style}

## Scenario
- Product: {product}
- Therapeutic Area: {therapeutic_area}
- Difficulty: {difficulty}

## Key Messages to Deliver
{key_messages_list}

## Key Message Delivery Status
{key_messages_status}

## Conversation Transcript
{transcript}

## Scoring Dimensions and Weights
{dimensions_config}

## CRITICAL SCORING RULES (MUST FOLLOW)

These rules are MANDATORY and override any other scoring judgment:
1. If key messages are NOT DELIVERED, key_message score MUST be below 30.
2. If MR's messages are unrelated to the product/therapeutic area, ALL scores MUST be below 50.
3. Reference actual MR quotes (from lines marked ">>> MR") in strengths/weaknesses.
4. NEVER reference or evaluate HCP responses. Only evaluate MR performance.
5. Return dimensions ONLY from `## Scoring Dimensions and Weights`. Do not add,
   rename, replace, or infer dimensions from Skill content or any other source.

## Instructions

Score each dimension from 0-100 based on the actual conversation content. Be specific:
- Reference actual quotes from the MR's responses in strengths/weaknesses
- Use the dimension criteria provided above as your scoring guide for each dimension
- Evaluate how well the MR addressed the HCP's concerns and delivered the required information
- "strengths" MUST be genuinely positive observations about the MR's performance. If there
    are no real strengths to report, use an empty array []. NEVER put negative, neutral, or
    absence-of-action observations in the strengths field. Similarly, "weaknesses" MUST be
    genuinely negative observations - never put positive observations there.

REMINDER: Scores MUST reflect MR (role=user) performance ONLY.
Every quote must come from MR messages marked with '>>> MR' above.

Return a JSON object with this exact structure:
{{
  "dimensions": [
    {{
      "dimension": "<dimension_name>",
      "score": <0-100>,
      "weight": <weight_from_config>,
      "strengths": [{{"text": "<observation>", "quote": "<MR quote or null>"}}],
      "weaknesses": [{{"text": "<observation>", "quote": "<MR quote or null>"}}],
      "suggestions": ["<actionable suggestion>"]
    }}
  ],
  "feedback_summary": "<2-3 sentence overall assessment>"
}}"""


def _enforce_scoring_rules(
    dimensions: list[dict],
    key_messages_status: list[dict],
    messages: list[dict],
) -> list[dict]:
    """Post-validation: programmatically enforce critical scoring rules as a safety net.

    Rules enforced:
    1. If ALL key_messages have delivered=false, cap key_message dimension to max 30.
    2. If ALL undelivered AND total MR message content < 100 chars, cap ALL dims to max 50.

    Returns the (possibly mutated) dimensions list.
    """
    # If no key messages to evaluate, skip all rules
    if not key_messages_status:
        return dimensions

    # Check if ALL key messages are undelivered
    all_undelivered = all(not km.get("delivered") for km in key_messages_status)

    if not all_undelivered:
        return dimensions

    # Rule 1: Cap key_message dimension to 30
    for dim in dimensions:
        if dim.get("dimension") == "key_message" and dim.get("score", 0) > 30:
            logger.warning(
                "Post-validation: capping key_message from %d to 30 (all key messages undelivered)",
                dim["score"],
            )
            dim["score"] = 30

    # Rule 2: Check MR message total length for relevance signal
    mr_total_chars = sum(
        len(msg.get("content", "")) for msg in messages if msg.get("role") == "user"
    )

    if mr_total_chars < 100:
        # Very short/irrelevant MR content -> cap ALL dimensions to 50
        for dim in dimensions:
            if dim.get("dimension") == "key_message":
                # Already capped to 30 by Rule 1
                continue
            if dim.get("score", 0) > 50:
                logger.warning(
                    "Post-validation: capping %s from %d to 50 "
                    "(all undelivered + short MR content)",
                    dim.get("dimension"),
                    dim["score"],
                )
                dim["score"] = 50

    return dimensions


def build_dimensions_instructions(rubric_dimensions: list[dict]) -> str:
    """Build dimension config text from rubric dimensions for the scoring prompt."""
    lines = []
    for dim in rubric_dimensions:
        name = dim["name"]
        weight = dim["weight"]
        criteria = dim.get("criteria", [])
        lines.append(f"- {name} (weight={weight}%)")
        if criteria:
            for criterion in criteria:
                lines.append(f"  * {criterion}")
    return "\n".join(lines)


def _normalize_scored_dimensions(
    dimensions: list[dict],
    rubric_dimensions: list[dict],
) -> list[dict]:
    """Keep only dimensions defined by the scenario scoring rubric, in rubric order."""
    scored_by_name = {dim.get("dimension"): dim for dim in dimensions}
    normalized: list[dict] = []
    missing: list[str] = []

    for rubric_dim in rubric_dimensions:
        name = rubric_dim["name"]
        scored_dim = scored_by_name.get(name)
        if scored_dim is None:
            missing.append(name)
            continue
        scored_dim["dimension"] = name
        scored_dim["weight"] = rubric_dim["weight"]
        scored_dim["category"] = "content"
        normalized.append(scored_dim)

    unknown = [
        str(dim.get("dimension"))
        for dim in dimensions
        if dim.get("dimension") not in {rubric_dim["name"] for rubric_dim in rubric_dimensions}
    ]
    if unknown:
        logger.warning("Ignoring non-rubric scoring dimensions returned by LLM: %s", unknown)

    if missing:
        raise ScoringUnavailableException(
            "LLM scoring missing required rubric dimensions: " + ", ".join(missing)
        )

    return normalized


def _render_custom_prompt_template(template: str, values: dict[str, str]) -> str:
    """Render supported placeholders without interpreting other JSON braces."""
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace(f"{{{key}}}", value)
    return rendered.replace("{{", "{").replace("}}", "}")


def build_scoring_prompt(
    scenario_data: dict,
    messages: list[dict],
    key_messages_status: list[dict],
    rubric_dimensions: list[dict],
    prompt_template: str = "",
    base_template: str = "",
) -> str:
    """Build the scoring prompt from session data.

    ``prompt_template`` is a per-entity (rubric) override rendered with the safe
    custom renderer. ``base_template`` is the registry-resolved default base
    (``scoring.base``); when empty the module constant is used. With the seeded
    default the ``str.format`` output is byte-identical to the legacy behavior.
    """
    # Format transcript with strong role labels to prevent LLM role confusion
    transcript_lines = []
    for msg in messages:
        if msg["role"] == "user":
            role_label = ">>> MR (EVALUATE THIS PERSON) <<<"
        else:
            role_label = ">>> HCP (DO NOT EVALUATE) <<<"
        transcript_lines.append(f"{role_label}: {msg['content']}")
    transcript = "\n".join(transcript_lines)

    # Format key messages list
    key_messages = scenario_data.get("key_messages", [])
    if isinstance(key_messages, str):
        key_messages = json.loads(key_messages)
    km_list = "\n".join(f"- {km}" for km in key_messages) if key_messages else "None specified"

    # Format delivery status
    km_status_lines = []
    for km in key_messages_status:
        status = "DELIVERED" if km.get("delivered") else "NOT DELIVERED"
        km_status_lines.append(f"- [{status}] {km.get('message', '')}")
    km_status = "\n".join(km_status_lines) if km_status_lines else "No tracking data"

    # Format dimensions config from rubric dimensions
    dims_config = build_dimensions_instructions(rubric_dimensions)

    hcp = scenario_data.get("hcp_profile", {})

    values = {
        "hcp_name": hcp.get("name", "Unknown"),
        "hcp_specialty": hcp.get("specialty", "Unknown"),
        "hcp_personality": hcp.get("personality_type", "neutral"),
        "hcp_comm_style": hcp.get("communication_style", "50"),
        "product": scenario_data.get("product", "Unknown"),
        "therapeutic_area": scenario_data.get("therapeutic_area", ""),
        "difficulty": scenario_data.get("difficulty", "medium"),
        "key_messages_list": km_list,
        "key_messages_status": km_status,
        "transcript": transcript,
        "dimensions_config": dims_config,
        "skill_criteria_section": "",
    }

    if prompt_template:
        return _render_custom_prompt_template(prompt_template.strip(), values)

    template = base_template or SCORING_PROMPT_TEMPLATE
    return template.format(**values)


async def score_with_llm(
    db: AsyncSession,
    scenario_data: dict,
    messages: list[dict],
    key_messages_status: list[dict],
    rubric_dimensions: list[dict],
    pass_threshold: int = 70,
    prompt_template: str = "",
) -> dict:
    """Score a session using LLM (primary content scoring engine).

    Uses the Azure OpenAI endpoint configured in the admin panel (service_name="azure_openai")
    or falls back to the master AI Foundry endpoint.

    Raises ScoringUnavailableException if LLM is not configured or call fails.
    """
    endpoint = await config_service.get_effective_endpoint(db, "azure_openai")
    api_key = await config_service.get_effective_key(db, "azure_openai")

    if not endpoint:
        raise ScoringUnavailableException(
            "Content scoring unavailable: no Azure OpenAI endpoint configured"
        )

    # Get deployment/model name
    config = await config_service.get_config(db, "azure_openai")
    from app.config import get_settings

    deployment = (
        config.model_or_deployment
        if config and config.model_or_deployment
        else get_settings().voice_live_default_model
    )

    try:
        from app.services.azure_auth import get_azure_openai_client

        client = await get_azure_openai_client(
            endpoint=endpoint,
            api_key=api_key,
            api_version="2024-06-01",
        )
    except ImportError:
        raise ScoringUnavailableException(
            "Content scoring unavailable: openai package not installed"
        )
    except RuntimeError as exc:
        raise ScoringUnavailableException(f"Content scoring unavailable: {exc}")

    from app.services.prompt_registry import get_prompt

    try:
        base_template = await get_prompt(db, "scoring.base")
    except Exception:
        # Registry lookup failed (e.g. unseeded DB) -- fall back to built-in default.
        base_template = ""

    prompt = build_scoring_prompt(
        scenario_data,
        messages,
        key_messages_status,
        rubric_dimensions,
        prompt_template=prompt_template,
        base_template=base_template,
    )

    try:
        response = await client.chat.completions.create(
            model=deployment,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a pharmaceutical sales training evaluator for BeiGene. "
                        "You evaluate ONLY the MR (role=user) performance, NOT the HCP. "
                        "Return ONLY valid JSON, no markdown fences."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_completion_tokens=2048,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        if not content:
            raise ScoringUnavailableException("LLM scoring returned empty content")

        result = json.loads(content)
    except ScoringUnavailableException:
        raise
    except Exception as e:
        logger.error("LLM scoring failed: %s", e, exc_info=True)
        raise ScoringUnavailableException(f"Content scoring failed: {e}") from e

    # Validate and compute overall score
    dimensions = result.get("dimensions", [])
    if not dimensions:
        raise ScoringUnavailableException("LLM scoring returned no dimensions")

    dimensions = _normalize_scored_dimensions(dimensions, rubric_dimensions)

    # Post-validation: enforce critical scoring rules programmatically
    dimensions = _enforce_scoring_rules(dimensions, key_messages_status, messages)

    overall_score = sum(dim["score"] * dim["weight"] / 100 for dim in dimensions)
    overall_score = round(overall_score, 1)
    passed = overall_score >= pass_threshold

    feedback_summary = result.get("feedback_summary", "")
    if not feedback_summary:
        delivered_count = sum(1 for km in key_messages_status if km.get("delivered"))
        total_count = len(key_messages_status)
        feedback_summary = (
            f"Overall score: {overall_score}. "
            f"Delivered {delivered_count}/{total_count} key messages."
        )

    return {
        "overall_score": overall_score,
        "passed": passed,
        "feedback_summary": feedback_summary,
        "dimensions": dimensions,
    }
