"""Skill Focus Service — dynamic additional_instructions composition and SOP progress tracking.

Provides:
- extract_sop_steps(): Parse SOP content into numbered steps
- compose_focus_instruction(): Build additional_instructions for a focused session run
  (D-01, D-02, D-04, D-05)
- detect_sop_step(): LLM-based SOP step classification (D-06)
"""

import logging
import re

from app.services.skill_manager import SkillContent

logger = logging.getLogger(__name__)


def extract_sop_steps(sop_content: str, *, allow_fallback: bool = True) -> list[str]:
    """Extract numbered SOP steps from content.

    Handles formats:
    - "1. Step description"
    - "Step 1: Description"
    - "## Step 1" (markdown headers)
    - Numbered lines in ordered lists

    Returns list of step descriptions in order.
    """
    steps: list[str] = []

    # Pattern 1: "1. Step text" or "1) Step text"
    numbered_pattern = re.compile(r"^\s*(\d+)[.)]\s+(.+)$", re.MULTILINE)
    matches = numbered_pattern.findall(sop_content)
    if matches:
        # Sort by number to ensure order
        sorted_matches = sorted(matches, key=lambda m: int(m[0]))
        steps = [m[1].strip() for m in sorted_matches]
        if steps:
            return steps

    # Pattern 2: "Step N:" or "步骤 N:"
    step_pattern = re.compile(
        r"^\s*(?:Step|步骤)\s*(\d+)\s*[:：]\s*(.+)$", re.MULTILINE | re.IGNORECASE
    )
    matches = step_pattern.findall(sop_content)
    if matches:
        sorted_matches = sorted(matches, key=lambda m: int(m[0]))
        steps = [m[1].strip() for m in sorted_matches]
        if steps:
            return steps

    # Pattern 3: Markdown headers "## Step N" or "### N."
    header_pattern = re.compile(
        r"^#{2,4}\s*(?:Step\s*)?(\d+)\.?\s*[:：]?\s*(.+)$",
        re.MULTILINE | re.IGNORECASE,
    )
    matches = header_pattern.findall(sop_content)
    if matches:
        sorted_matches = sorted(matches, key=lambda m: int(m[0]))
        steps = [m[1].strip() for m in sorted_matches]
        if steps:
            return steps

    if not allow_fallback:
        return []

    # Fallback: split by double newlines and treat each paragraph as a step
    paragraphs = [p.strip() for p in sop_content.split("\n\n") if p.strip()]
    return paragraphs[:20]  # Cap at 20 steps max


def compose_focus_instruction(
    skill: SkillContent,
    current_step: int,
    sop_steps: list[str],
) -> str:
    """Build the additional_instructions for a focused session run.

    Per D-01: Appended via additional_instructions on each run. Agent definition unchanged.
    Per D-02: Contains full SOP content + focus constraint.
    Per D-04: Graded off-topic handling (gentle redirect vs hard block).
    Per D-05: Dynamic SOP progress awareness.

    Args:
        skill: SkillContent with name, version_id, and SOP content
        current_step: Current SOP step (0 = not started, 1-based index)
        sop_steps: Extracted SOP steps list

    Returns:
        Formatted instruction string for additional_instructions parameter.
    """
    total_steps = len(sop_steps)
    current_topic = (
        sop_steps[current_step - 1] if 0 < current_step <= total_steps else "Not started"
    )
    next_step = min(current_step + 1, total_steps) if current_step > 0 else 1
    next_topic = sop_steps[next_step - 1] if next_step <= total_steps else "All steps completed"

    parts = [
        "== SKILL FOCUS MODE ==",
        f"Skill: {skill.name} (v:{skill.version_id[:8] if skill.version_id else 'latest'})",
        "",
        "## SOP Content (你必须严格围绕以下内容进行讨论 / MUST stay within this scope):",
        skill.content,
        "",
        "## Current Progress:",
        f"当前对话进度: 步骤 {current_step}/{total_steps}",
        f"Current step topic: {current_topic}",
        f"Next expected: Guide user toward step {next_step} — {next_topic}",
        "",
        "## Focus Rules (严格执行):",
        "1. ONLY discuss topics within the SOP content above.",
        "2. 轻微偏离 (仍与产品/治疗领域相关): Gently redirect back to current SOP step.",
        '   Example: "这个问题很好，我们稍后可以讨论。现在让我们继续关注 [current topic]。"',
        "3. 完全无关话题 (闲聊、天气等): Firmly redirect.",
        '   Example: "我们今天专注于 [skill name] 的培训内容，请让我们回到主题。"',
        "4. Track which SOP steps have been covered and guide toward uncovered steps.",
        "5. When all steps are completed, summarize key points and wrap up.",
    ]
    return "\n".join(parts)


async def detect_sop_step(
    conversation_history: list[dict],
    sop_steps: list[str],
    endpoint: str,
    api_key: str,
    deployment: str = "gpt-4o-mini",
) -> int:
    """Determine which SOP step the conversation is currently at.

    Per D-06: Uses LLM to analyze conversation vs SOP steps. Extra LLM call per message.
    Uses gpt-4o-mini (or equivalent fast model) for low latency.

    Args:
        conversation_history: List of {"role": "user"|"assistant", "content": "..."} dicts
        sop_steps: Extracted SOP steps list
        endpoint: Azure OpenAI endpoint
        api_key: Azure OpenAI API key
        deployment: Model deployment name (default: gpt-4o-mini)

    Returns:
        Step number (1-based). 0 if conversation hasn't started SOP yet.
    """
    if not sop_steps:
        return 0

    if not conversation_history:
        return 0

    steps_text = "\n".join(f"{i + 1}. {step}" for i, step in enumerate(sop_steps))

    # Use last 10 messages for efficiency (avoid context overflow)
    recent_messages = conversation_history[-10:]
    transcript = "\n".join(
        f"{'MR' if m.get('role') == 'user' else 'HCP'}: {m.get('content', '')}"
        for m in recent_messages
    )

    prompt = (
        f"SOP Steps:\n{steps_text}\n\n"
        f"Conversation:\n{transcript}\n\n"
        "Based on the conversation content, which SOP step number is the conversation "
        "currently at or has most recently covered? Consider the topics discussed.\n"
        "Rules:\n"
        "- Return 0 if the conversation hasn't started addressing any SOP step yet.\n"
        "- Return the step number (integer) of the most recently addressed step.\n"
        "- If multiple steps were covered, return the highest completed step.\n"
        "Return ONLY the integer, nothing else."
    )

    try:
        from app.services.azure_auth import get_azure_openai_client

        client = await get_azure_openai_client(
            endpoint=endpoint,
            api_key=api_key,
            api_version="2024-06-01",
        )
        response = await client.chat.completions.create(
            model=deployment,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_completion_tokens=10,
        )
        result_text = (response.choices[0].message.content or "").strip()
        step_num = int(result_text)
        # Clamp to valid range
        return max(0, min(step_num, len(sop_steps)))
    except (ImportError, ValueError, AttributeError, TypeError) as e:
        logger.warning("SOP step detection failed: %s — defaulting to 0", e)
        return 0
    except Exception as e:
        logger.error("SOP step detection error: %s", e)
        return 0
