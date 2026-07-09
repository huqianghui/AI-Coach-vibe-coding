"""Dry Run simulation engine — orchestrates AI MR/HCP conversation for SOP coverage testing.

Uses two MetaSkill agents (dry-run-mr, dry-run-hcp) via Azure AI Foundry
Responses API with agent_reference + previous_response_id for server-side
multi-turn state. SOP coverage is evaluated semantically via the
skill-evaluator agent (replacing keyword matching).

Runs as a durable background task with its own DB session (not tied to the
HTTP request lifecycle).

Launched via ``asyncio.create_task(run_dry_run_simulation(dry_run_id))``
from the POST create endpoint.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import UTC, datetime

from app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_TURNS = 20

# Fallback marker — if an agent response contains this, the AI service is down
_FALLBACK_MARKER = "unavailable -- simulation continues"

# Abort simulation if this many consecutive turns return fallback text
_MAX_CONSECUTIVE_FAILURES = 2

# Retry transient Responses API failures before returning fallback text.
_AGENT_CALL_MAX_ATTEMPTS = 3
_AGENT_CALL_RETRY_BASE_SECONDS = 0.5

# Phrases that signal the end of a conversation (case-insensitive)
_ENDING_PHRASES = [
    "thank you for your time",
    "thanks for your time",
    "i'll let you go",
    "goodbye",
    "see you next time",
    "have a good day",
    "i should let you get back",
    "it was nice talking",
    "take care",
    "until next time",
]


# ---------------------------------------------------------------------------
# SOP extraction
# ---------------------------------------------------------------------------


def _extract_sop_steps(content: str) -> list[dict]:
    """Extract SOP steps from skill markdown content.

    Recognises:
      - ``## Step N:`` or ``### N.`` style headers
      - Numbered list items ``1. ...``, ``2. ...``

    Returns list of dicts with keys: step_id, step_name, step_content.
    If no steps are found, wraps the entire content as a single step.
    """
    if not content or not content.strip():
        return [{"step_id": "step_1", "step_name": "Full Content", "step_content": content or ""}]

    steps: list[dict] = []

    # Pattern 1: markdown headers like "## Step 1: Introduction" or "### 1. Opening"
    header_pattern = re.compile(
        r"^(?:#{2,3})\s*(?:Step\s+)?(\d+)[.:\s]+(.+?)$",
        re.MULTILINE | re.IGNORECASE,
    )
    headers = list(header_pattern.finditer(content))

    if headers:
        for i, match in enumerate(headers):
            step_num = match.group(1)
            step_name = match.group(2).strip()
            start = match.end()
            end = headers[i + 1].start() if i + 1 < len(headers) else len(content)
            step_content = content[start:end].strip()
            steps.append(
                {
                    "step_id": f"step_{step_num}",
                    "step_name": step_name,
                    "step_content": step_content,
                }
            )
        return steps

    # Pattern 2: numbered list items "1. ...", "2. ..."
    list_pattern = re.compile(r"^(\d+)\.\s+(.+?)$", re.MULTILINE)
    items = list(list_pattern.finditer(content))

    if len(items) >= 2:
        for i, match in enumerate(items):
            step_num = match.group(1)
            step_name = match.group(2).strip()
            start = match.end()
            end = items[i + 1].start() if i + 1 < len(items) else len(content)
            step_content = content[start:end].strip()
            steps.append(
                {
                    "step_id": f"step_{step_num}",
                    "step_name": step_name,
                    "step_content": step_content,
                }
            )
        return steps

    # Fallback: treat whole content as one step
    return [{"step_id": "step_1", "step_name": "Full Content", "step_content": content}]


# ---------------------------------------------------------------------------
# Conversation ending detection
# ---------------------------------------------------------------------------


def _is_conversation_ending(message: str, turn_number: int) -> bool:
    """Detect if the conversation should end.

    Returns True when:
      - Turn number is >= 18 (approaching MAX_TURNS)
      - Message contains common ending phrases
    """
    if turn_number >= 18:
        return True
    lower = message.lower()
    return any(phrase in lower for phrase in _ENDING_PHRASES)


def _sanitize_agent_error(error: Exception, api_key: str = "") -> str:
    """Return a short, admin-safe error summary for dry-run diagnostics."""
    error_type = type(error).__name__
    status_code = getattr(error, "status_code", None)
    request_id = getattr(error, "request_id", None)
    message = str(error)

    if api_key:
        message = message.replace(api_key, "[redacted]")

    message = re.sub(
        r"(?i)(api[-_ ]?key|authorization|bearer)\s*[:=]\s*[^,\s]+",
        r"\1=[redacted]",
        message,
    )
    message = re.sub(r"sk-[A-Za-z0-9_-]+", "sk-[redacted]", message)
    message = re.sub(r"\s+", " ", message).strip()
    message = message[:220]

    parts = [error_type]
    if status_code:
        parts.append(f"status={status_code}")
    if request_id:
        parts.append(f"request_id={request_id}")
    if message:
        parts.append(message)
    return ": ".join(parts)


def _set_failed_dry_run(
    dry_run,
    *,
    message: str,
    start_time: datetime | None = None,
    suggestion: str = "Check Azure AI Foundry agent availability and retry the dry run.",
) -> None:
    """Persist a failed dry run with structured issue data for API/UI consumers."""
    dry_run.status = "failed"
    dry_run.error_message = message
    if start_time and dry_run.duration_seconds is None:
        dry_run.duration_seconds = int((datetime.now(tz=UTC) - start_time).total_seconds())
    dry_run.issues_json = json.dumps(
        [
            {
                "severity": "error",
                "step_id": None,
                "description": message[:500],
                "suggestion": suggestion,
            }
        ]
    )
    dry_run.issues_count = 1


# ---------------------------------------------------------------------------
# Agent call helper (replaces _call_llm)
# ---------------------------------------------------------------------------


async def _call_dry_run_agent(
    message: str,
    agent_id: str,
    agent_version: str,
    model: str,
    previous_response_id: str | None,
    *,
    project_endpoint: str,
    api_key: str,
) -> tuple[str, str]:
    """Call a dry-run agent via Responses API with agent_reference.

    Uses the same pattern as chat_with_agent() and
    skill_evaluation_service._call_agent_for_evaluation():
    - agent_reference in extra_body for Azure AI Foundry agent routing
    - previous_response_id for server-side multi-turn conversation state

    Returns (response_text, response_id) for chaining multi-turn.
    On failure returns (fallback_text, "").
    """
    from app.services.agent_sync_service import _get_project_client

    agent_label = agent_id or "unknown-agent"
    last_error = ""

    for attempt in range(1, _AGENT_CALL_MAX_ATTEMPTS + 1):
        try:
            client = _get_project_client(project_endpoint, api_key)
            openai_client = client.get_openai_client()

            input_messages = [{"role": "user", "content": message}]

            extra_body = {
                "agent_reference": {
                    "name": agent_id,
                    "version": agent_version or "1",
                    "type": "agent_reference",
                }
            }

            kwargs: dict = {
                "model": model,
                "input": input_messages,
                "extra_body": extra_body,
            }

            if previous_response_id:
                kwargs["previous_response_id"] = previous_response_id

            response = openai_client.responses.create(**kwargs)
            content = (response.output_text or "")[:500]
            return content, response.id

        except Exception as e:
            last_error = _sanitize_agent_error(e, api_key)
            logger.warning(
                "_call_dry_run_agent failed for %s on attempt %d/%d: %s",
                agent_label,
                attempt,
                _AGENT_CALL_MAX_ATTEMPTS,
                last_error,
            )
            if attempt < _AGENT_CALL_MAX_ATTEMPTS:
                await asyncio.sleep(_AGENT_CALL_RETRY_BASE_SECONDS * attempt)

    return f"[{agent_label} {_FALLBACK_MARKER}. Last error: {last_error}]", ""


# ---------------------------------------------------------------------------
# Semantic SOP coverage evaluation via skill-evaluator agent
# ---------------------------------------------------------------------------

# Prompt template for SOP coverage evaluation
_SOP_EVAL_PROMPT = """\
You are evaluating a dry run simulation conversation for SOP coverage.

## SOP Steps
{sop_steps_text}

## Conversation Transcript
{transcript_text}

## Task

Analyze the conversation and determine which SOP steps were covered by the MR's messages.

Return a JSON object with this exact structure:
{{
  "steps": [
    {{
      "step_id": "step_1",
      "step_name": "Opening Greeting",
      "status": "covered",
      "details": "MR greeted the doctor in message #0",
      "matched_message_indices": [0]
    }}
  ],
  "issues": [
    {{
      "severity": "error",
      "step_id": "step_3",
      "description": "SOP step 'Closing' was not covered during the simulation",
      "suggestion": "Consider simplifying the step or adding clearer guidance"
    }}
  ],
  "executability_score": 75,
  "summary": "Brief assessment of overall SOP executability"
}}

Rules:
- status must be one of: "covered", "partial", "not_covered"
- severity must be one of: "error" (not_covered steps), "warning" (partial steps)
- executability_score: 0-100 based on how well the SOP was executed
- Only MR messages can cover SOP steps (HCP messages do not count)
- Return ONLY the JSON object, no other text"""


async def _evaluate_sop_coverage_with_agent(
    sop_steps: list[dict],
    conversation: list[dict],
    evaluator_agent_id: str,
    evaluator_agent_version: str,
    evaluator_model: str,
    *,
    project_endpoint: str,
    api_key: str,
    prompt_template: str = _SOP_EVAL_PROMPT,
) -> tuple[list[dict], list[dict], int]:
    """Evaluate SOP coverage using the skill-evaluator MetaSkill agent.

    Returns (coverage_map, issues, executability_score).
    Falls back to basic coverage on evaluator failure.
    """
    # Format SOP steps for the prompt
    sop_lines = []
    for step in sop_steps:
        sop_lines.append(f"### {step['step_id']}: {step['step_name']}")
        if step.get("step_content"):
            sop_lines.append(step["step_content"][:300])
        sop_lines.append("")
    sop_steps_text = "\n".join(sop_lines)

    # Format conversation transcript
    transcript_lines = []
    for i, msg in enumerate(conversation):
        role_label = "MR" if msg["role"] == "mr" else "HCP"
        transcript_lines.append(f"[#{i}] {role_label}: {msg['content']}")
    transcript_text = "\n".join(transcript_lines)

    prompt = prompt_template.format(
        sop_steps_text=sop_steps_text,
        transcript_text=transcript_text,
    )

    try:
        from app.services.agent_sync_service import _get_project_client

        client = _get_project_client(project_endpoint, api_key)
        openai_client = client.get_openai_client()

        extra_body = {
            "agent_reference": {
                "name": evaluator_agent_id,
                "version": evaluator_agent_version or "1",
                "type": "agent_reference",
            }
        }

        response = openai_client.responses.create(
            model=evaluator_model,
            input=[{"role": "user", "content": prompt}],
            extra_body=extra_body,
        )

        raw = response.output_text or ""
        # Strip markdown code fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)

        result = json.loads(raw)

        # Extract coverage map
        coverage_map = []
        for step_result in result.get("steps", []):
            coverage_map.append(
                {
                    "step_id": step_result.get("step_id", ""),
                    "step_name": step_result.get("step_name", ""),
                    "status": step_result.get("status", "not_covered"),
                    "matched_message_ids": step_result.get("matched_message_indices", []),
                    "details": step_result.get("details", ""),
                }
            )

        # Ensure all SOP steps are in coverage map
        covered_ids = {c["step_id"] for c in coverage_map}
        for step in sop_steps:
            if step["step_id"] not in covered_ids:
                coverage_map.append(
                    {
                        "step_id": step["step_id"],
                        "step_name": step["step_name"],
                        "status": "not_covered",
                        "matched_message_ids": [],
                        "details": "Not evaluated",
                    }
                )

        issues = result.get("issues", [])
        score = result.get("executability_score", 0)
        return coverage_map, issues, int(score)

    except Exception as e:
        logger.warning("SOP coverage evaluation via agent failed: %s", e)
        # Fallback: mark all steps as not evaluated
        coverage_map = [
            {
                "step_id": s["step_id"],
                "step_name": s["step_name"],
                "status": "not_covered",
                "matched_message_ids": [],
                "details": f"Evaluation failed: {str(e)[:100]}",
            }
            for s in sop_steps
        ]
        issues = [
            {
                "severity": "error",
                "step_id": None,
                "description": f"SOP coverage evaluation failed: {str(e)[:200]}",
                "suggestion": "Check evaluator agent configuration and try again.",
            }
        ]
        return coverage_map, issues, 0


# ---------------------------------------------------------------------------
# Main simulation orchestrator
# ---------------------------------------------------------------------------


async def run_dry_run_simulation(dry_run_id: str) -> None:
    """Run a full dry-run simulation as a durable background task.

    Uses two MetaSkill agents (dry-run-mr, dry-run-hcp) for the conversation
    and the skill-evaluator agent for semantic SOP coverage evaluation.

    Creates its own DB session via AsyncSessionLocal (not tied to the
    HTTP request that spawned it). Updates the DryRun record with
    results or error state on completion.
    """
    from app.models.dry_run import DryRun, DryRunMessage
    from app.models.skill import Skill
    from app.services import meta_skill_service
    from app.services.agent_sync_service import get_project_endpoint

    start_time: datetime | None = None
    async with AsyncSessionLocal() as db:
        try:
            # 1. Load DryRun and Skill
            dry_run = await db.get(DryRun, dry_run_id)
            if not dry_run:
                logger.error("run_dry_run_simulation: DryRun %s not found", dry_run_id)
                return

            skill = await db.get(Skill, dry_run.skill_id)
            if not skill:
                _set_failed_dry_run(
                    dry_run,
                    message="Associated skill not found",
                    suggestion="Delete this dry run and create a new one from an existing skill.",
                )
                await db.commit()
                return

            # 2. Load MetaSkill agents
            mr_meta = await meta_skill_service.get_meta_skill(db, "dry-run-mr")
            hcp_meta = await meta_skill_service.get_meta_skill(db, "dry-run-hcp")
            eval_meta = await meta_skill_service.get_meta_skill(db, "evaluator")

            if not mr_meta or not mr_meta.agent_id:
                _set_failed_dry_run(
                    dry_run,
                    message=(
                        "Dry Run MR agent not synced to Azure AI Foundry. "
                        "Go to Admin > Meta Skills and sync the 'dry-run-mr' agent."
                    ),
                    suggestion="Sync the dry-run-mr Meta Skill in Admin > Meta Skills.",
                )
                await db.commit()
                return

            if not hcp_meta or not hcp_meta.agent_id:
                _set_failed_dry_run(
                    dry_run,
                    message=(
                        "Dry Run HCP agent not synced to Azure AI Foundry. "
                        "Go to Admin > Meta Skills and sync the 'dry-run-hcp' agent."
                    ),
                    suggestion="Sync the dry-run-hcp Meta Skill in Admin > Meta Skills.",
                )
                await db.commit()
                return

            # 3. Set status to running and record agent audit info
            dry_run.status = "running"
            dry_run.mr_agent_id = mr_meta.agent_id
            dry_run.mr_agent_version = mr_meta.agent_version
            dry_run.hcp_agent_id = hcp_meta.agent_id
            dry_run.hcp_agent_version = hcp_meta.agent_version
            if eval_meta and eval_meta.agent_id:
                dry_run.evaluator_agent_id = eval_meta.agent_id
                dry_run.evaluator_agent_version = eval_meta.agent_version
            start_time = datetime.now(tz=UTC)
            await db.flush()

            # 4. Extract SOP steps
            sop_steps = _extract_sop_steps(skill.content or "")
            dry_run.total_sop_steps = len(sop_steps)
            await db.flush()

            # 5. Pre-fetch AI endpoint
            project_endpoint, api_key_val = await get_project_endpoint(db)

            # 6. Compose initial messages for session-level skill binding (DR-01.3)
            # MR gets the full skill content (SOP + script + references)
            formatted_steps = "\n".join(
                f"  {s['step_id']}: {s['step_name']}\n    {s['step_content'][:200]}"
                for s in sop_steps
            )
            mr_first_message = (
                "You are starting a dry run simulation. Here is the Skill content "
                "you must follow during this conversation:\n\n"
                f"## Skill: {skill.name or 'Unnamed Skill'}\n"
                f"{skill.description or ''}\n\n"
                f"## SOP Steps\n{formatted_steps}\n\n"
                f"## Full Content\n{(skill.content or '')[:3000]}\n\n"
                "Begin the conversation by greeting the HCP."
            )

            # HCP gets brief product context
            hcp_first_message = (
                f"A Medical Representative is visiting to discuss: "
                f"{skill.name or 'a pharmaceutical product'}. "
                f"{skill.description or ''}\n\n"
                "The MR will start the conversation. Respond as a busy doctor would."
            )

            # 7. Simulation loop with agent_reference + previous_response_id
            conversation: list[dict] = []
            sequence = 0
            mr_prev_response_id: str | None = None
            hcp_prev_response_id: str | None = None
            consecutive_failures = 0

            for turn in range(MAX_TURNS):
                current_role = "mr" if turn % 2 == 0 else "hcp"

                if current_role == "mr":
                    if turn == 0:
                        # First MR turn: send skill content as initial message
                        message = mr_first_message
                    else:
                        # Relay HCP's last response to MR
                        message = conversation[-1]["content"]

                    response_text, response_id = await _call_dry_run_agent(
                        message=message,
                        agent_id=mr_meta.agent_id,
                        agent_version=mr_meta.agent_version,
                        model=mr_meta.model,
                        previous_response_id=mr_prev_response_id,
                        project_endpoint=project_endpoint,
                        api_key=api_key_val,
                    )
                    mr_prev_response_id = response_id or mr_prev_response_id
                else:
                    if turn == 1:
                        # First HCP turn: send product context + MR's greeting
                        message = (
                            f"{hcp_first_message}\n\nThe MR said: {conversation[-1]['content']}"
                        )
                    else:
                        # Relay MR's last response to HCP
                        message = conversation[-1]["content"]

                    response_text, response_id = await _call_dry_run_agent(
                        message=message,
                        agent_id=hcp_meta.agent_id,
                        agent_version=hcp_meta.agent_version,
                        model=hcp_meta.model,
                        previous_response_id=hcp_prev_response_id,
                        project_endpoint=project_endpoint,
                        api_key=api_key_val,
                    )
                    hcp_prev_response_id = response_id or hcp_prev_response_id

                # Track consecutive failures for mid-simulation abort
                is_fallback = _FALLBACK_MARKER in response_text
                if is_fallback:
                    consecutive_failures += 1
                else:
                    consecutive_failures = 0

                # Early abort: if first MR turn fails, AI service is unavailable
                if turn == 0 and is_fallback:
                    _set_failed_dry_run(
                        dry_run,
                        message=(
                            "AI service unavailable — check Azure AI Foundry configuration "
                            "and ensure dry-run agents are synced. "
                            f"First response: {response_text[:300]}"
                        ),
                        start_time=start_time,
                    )
                    await db.commit()
                    logger.error(
                        "Dry run %s aborted: AI service unavailable on first turn",
                        dry_run_id,
                    )
                    return

                # Mid-simulation abort: consecutive failures indicate persistent issue
                if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                    _set_failed_dry_run(
                        dry_run,
                        message=(
                            f"AI service became unavailable during simulation "
                            f"({consecutive_failures} consecutive failures at turn {turn}). "
                            f"Last response: {response_text[:300]}"
                        ),
                        start_time=start_time,
                    )
                    await db.commit()
                    logger.error(
                        "Dry run %s aborted: %d consecutive agent failures at turn %d",
                        dry_run_id,
                        consecutive_failures,
                        turn,
                    )
                    return

                # Skip empty responses — treat as conversation end
                if not response_text.strip():
                    break

                conversation.append({"role": current_role, "content": response_text})

                # Save message to DB (no keyword SOP matching — done by evaluator later)
                msg = DryRunMessage(
                    dry_run_id=dry_run_id,
                    sequence_number=sequence,
                    role=current_role,
                    content=response_text,
                )
                db.add(msg)
                sequence += 1
                await db.flush()

                # Check for natural conversation end
                if _is_conversation_ending(response_text, turn):
                    break

            # 8. Evaluate SOP coverage via skill-evaluator agent
            if eval_meta and eval_meta.agent_id:
                from app.services.prompt_registry import get_prompt

                sop_eval_template = await get_prompt(db, "dry_run.sop_eval")
                coverage_map, issues, score = await _evaluate_sop_coverage_with_agent(
                    sop_steps=sop_steps,
                    conversation=conversation,
                    evaluator_agent_id=eval_meta.agent_id,
                    evaluator_agent_version=eval_meta.agent_version,
                    evaluator_model=eval_meta.model,
                    project_endpoint=project_endpoint,
                    api_key=api_key_val,
                    prompt_template=sop_eval_template,
                )
            else:
                # No evaluator synced — produce empty coverage
                logger.warning(
                    "Dry run %s: evaluator agent not synced, skipping SOP evaluation",
                    dry_run_id,
                )
                coverage_map = [
                    {
                        "step_id": s["step_id"],
                        "step_name": s["step_name"],
                        "status": "not_covered",
                        "matched_message_ids": [],
                        "details": "Evaluator agent not synced",
                    }
                    for s in sop_steps
                ]
                issues = [
                    {
                        "severity": "warning",
                        "step_id": None,
                        "description": "SOP coverage not evaluated — evaluator agent not synced",
                        "suggestion": "Sync the skill-evaluator agent in Admin > Meta Skills.",
                    }
                ]
                score = 0

            # Update message SOP annotations from evaluator results
            # Use explicit query to avoid lazy-loading issues in async context
            from sqlalchemy import select as sa_select

            coverage_by_step = {c["step_id"]: c for c in coverage_map}
            msg_result = await db.execute(
                sa_select(DryRunMessage)
                .where(DryRunMessage.dry_run_id == dry_run_id)
                .where(DryRunMessage.role == "mr")
            )
            for msg_obj in msg_result.scalars():
                for step_id, cov in coverage_by_step.items():
                    if msg_obj.sequence_number in cov.get("matched_message_ids", []):
                        msg_obj.sop_step_id = step_id
                        msg_obj.sop_step_name = cov.get("step_name", "")
                        break

            # 9. Update DryRun with results
            covered_count = sum(1 for c in coverage_map if c["status"] == "covered")
            partial_count = sum(1 for c in coverage_map if c["status"] == "partial")
            total_steps = len(sop_steps)

            dry_run.status = "completed"
            dry_run.executability_score = score
            dry_run.coverage_percent = (
                round(covered_count * 100 / total_steps) if total_steps else 0
            )
            dry_run.total_sop_steps = total_steps
            dry_run.covered_sop_steps = covered_count
            dry_run.partial_sop_steps = partial_count
            dry_run.issues_count = len(issues)
            dry_run.issues_json = json.dumps(issues, ensure_ascii=False)
            dry_run.sop_coverage_json = json.dumps(coverage_map, ensure_ascii=False)
            dry_run.duration_seconds = int((datetime.now(tz=UTC) - start_time).total_seconds())
            await db.commit()

            logger.info(
                "Dry run %s completed: score=%d, coverage=%d%%, issues=%d, turns=%d",
                dry_run_id,
                score,
                dry_run.coverage_percent,
                len(issues),
                len(conversation),
            )

        except Exception as e:
            logger.exception("Dry run simulation failed for %s", dry_run_id)
            try:
                dry_run = await db.get(DryRun, dry_run_id)
                if dry_run:
                    _set_failed_dry_run(
                        dry_run,
                        message=str(e)[:500],
                        start_time=start_time,
                        suggestion=(
                            "Review backend logs for the dry-run simulation failure and retry."
                        ),
                    )
                    await db.commit()
            except Exception:
                logger.exception("Failed to update dry run %s error state", dry_run_id)
