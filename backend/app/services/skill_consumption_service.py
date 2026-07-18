"""Session-time skill consumption abstraction (Phase 28: D-02, D-04, D-05, D-06).

When a training session starts (or a chat message advances SOP progress) for a
scenario whose Skill is Foundry-synced, this module best-effort mounts the skill
into a Toolbox (D-02), tries the real MCP endpoint (confirmed 405 today per doc
10 Sec 12 -- probed honestly, not hardcoded skipped, so it self-heals if Azure
ever fixes it, per D-04), and falls back to the already-verified
``skills.download()`` + frontmatter extraction path when MCP is unavailable. If
the skill isn't synced, or every cloud path fails, this transparently degrades
to the existing Phase 19/24 local DB injection (``load_skill_for_scenario``,
D-06). The single top-level entry point, :func:`get_skill_content_for_session`,
returns the same :class:`~app.services.skill_manager.SkillContent` abstraction
already consumed identically by text-mode and Voice Live via
``CoachingSession.focus_instruction`` (D-05) -- no separate Voice Live wiring.

HIGH-1 fix (cross-AI review): a process-local TTL cache keyed on
``(skill.id, skill.foundry_cloud_version)`` guards the cloud chain so repeated
calls within a training session (one per chat message) do not re-mount the
Toolbox, re-probe MCP, and re-download the ZIP on every single message.

MEDIUM-4 fix: a scenario with an explicit ``skill_version_id`` pin skips the
cloud path unconditionally (which always serves the latest Foundry version)
and goes straight to the local pinned-version content, so pinned training
content never silently drifts to "latest".
"""

import asyncio
import io
import logging
import time
import zipfile

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scenario import Scenario
from app.models.skill import Skill
from app.services.skill_foundry_service import (
    FOUNDRY_FEATURES_HEADER,
    _sanitize_skill_name,
    get_skills_client,
)
from app.services.skill_manager import SkillContent, load_skill_for_scenario
from app.services.skill_zip_service import parse_skill_frontmatter, validate_zip_security

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HIGH-1 fix -- process-local TTL cache
# ---------------------------------------------------------------------------

_CONTENT_CACHE_TTL_SECONDS = 600  # 10 min: long enough to absorb per-message chat traffic
# within one training conversation, short enough that a re-publish's new foundry_cloud_version
# (which changes the cache key) is picked up well within a single session's lifetime anyway.
_CACHE_MISS = object()  # sentinel distinguishing "no entry" from "cached None"
_content_cache: dict[tuple[str, str], tuple[float, SkillContent | None]] = {}


def _cache_get(key: tuple[str, str]) -> SkillContent | None | object:
    entry = _content_cache.get(key)
    if entry is None:
        return _CACHE_MISS
    cached_at, value = entry
    if time.monotonic() - cached_at > _CONTENT_CACHE_TTL_SECONDS:
        _content_cache.pop(key, None)
        return _CACHE_MISS
    return value


def _cache_set(key: tuple[str, str], value: SkillContent | None) -> None:
    _content_cache[key] = (time.monotonic(), value)


# ---------------------------------------------------------------------------
# MEDIUM-4 fix -- scenario pin staleness check
# ---------------------------------------------------------------------------


def _scenario_pin_is_stale(scenario: Scenario) -> bool:
    """True when the scenario pins an explicit SkillVersion (scenario.skill_version_id is
    set). The Foundry cloud path (Toolbox mount / MCP / skills.download()) has no version-pin
    concept -- it always serves whichever ZIP is currently registered as the skill's latest
    cloud version. If a scenario pins an older version, the cloud path would silently serve
    different (newer) content than the pin intends. Review MEDIUM-4 fix: when a pin exists,
    skip the cloud path unconditionally and let load_skill_for_scenario resolve the exact
    pinned SkillVersion row, guaranteeing content matches the pin."""
    return scenario.skill_version_id is not None


# ---------------------------------------------------------------------------
# Toolbox mount (D-02)
# ---------------------------------------------------------------------------


async def mount_skill_toolbox(db: AsyncSession, skill: Skill) -> str | None:
    """Best-effort mount a synced skill into a Foundry Toolbox via skill_reference.

    Never raises -- any exception on either attempt is logged and returns None
    (D-02: best-effort, never blocks session creation).

    Note (MEDIUM-3): this function itself does not deduplicate Toolbox versions
    server-side -- it is only called at most once per _CONTENT_CACHE_TTL_SECONDS
    window per skill-version (via get_skill_content_for_session's cache check),
    not once per message.
    """
    if skill.foundry_sync_status != "synced" or not skill.foundry_skill_name:
        return None

    toolbox_name = _sanitize_skill_name(f"tb-{skill.foundry_skill_name}")

    try:
        client = await get_skills_client(db)
        toolboxes_op = client.toolboxes if hasattr(client, "toolboxes") else client.beta.toolboxes

        try:
            from azure.ai.projects.models import ToolboxSkillReference

            await asyncio.to_thread(
                toolboxes_op.create_version,
                name=toolbox_name,
                tools=[],
                description=f"Training toolbox for skill {skill.name}",
                skills=[ToolboxSkillReference(name=skill.foundry_skill_name)],
                headers=FOUNDRY_FEATURES_HEADER,
            )
        except Exception:
            await asyncio.to_thread(
                toolboxes_op.create_version,
                name=toolbox_name,
                body={
                    "description": f"Training toolbox for skill {skill.name}",
                    "tools": [],
                    "skills": [{"type": "skill_reference", "name": skill.foundry_skill_name}],
                },
                headers=FOUNDRY_FEATURES_HEADER,
            )

        return toolbox_name
    except Exception as e:
        logger.warning("mount_skill_toolbox failed for skill %s: %s", skill.id, e)
        return None


# ---------------------------------------------------------------------------
# MCP probe (D-04) -- real probe, honest degrade, never raises (LOW-9)
# ---------------------------------------------------------------------------


async def _try_mcp_fetch(db: AsyncSession, toolbox_name: str, skill_name: str) -> str | None:
    """Probe the Toolbox MCP endpoint for skill content.

    Confirmed 405 today per doc 10 Test 7 -- a real, honest probe (not a
    hardcoded stub) so this self-heals if the gap is ever fixed (D-04). Every
    private-attribute access below uses getattr(..., default), never a bare
    attribute dereference, so an SDK minor-version change that renames/removes
    _config degrades to "MCP unavailable" instead of raising an AttributeError
    (LOW-9).
    """
    try:
        client = await get_skills_client(db)
        toolboxes_op = client.toolboxes if hasattr(client, "toolboxes") else client.beta.toolboxes
        config = getattr(client, "_config", None)
        credential = getattr(config, "credential", None)
        endpoint = getattr(config, "endpoint", None)
        if credential is None or endpoint is None:
            logger.debug("MCP probe skipped: client config shape unrecognized")
            return None

        token = (
            await asyncio.to_thread(credential.get_token, "https://ai.azure.com/.default")
        ).token
        toolbox_config = getattr(toolboxes_op, "_config", None)
        api_version = getattr(toolbox_config, "api_version", "v1")

        resp = await asyncio.to_thread(
            httpx.get,
            f"{endpoint}/toolboxes/{toolbox_name}/mcp",
            headers={"Authorization": f"Bearer {token}", **FOUNDRY_FEATURES_HEADER},
            params={"api-version": api_version},
            timeout=30,
        )

        if resp.status_code != 200:
            logger.debug(
                "MCP probe non-200 for toolbox %s / skill %s: %s",
                toolbox_name,
                skill_name,
                resp.status_code,
            )
            return None

        data = resp.json()
        content = data.get("content") or data.get("resources")
        if content:
            return str(content)
        return None
    except Exception as e:
        logger.debug("MCP probe failed for toolbox %s / skill %s: %s", toolbox_name, skill_name, e)
        return None


# ---------------------------------------------------------------------------
# Download fallback (D-04) -- the only end-to-end-verified consumption path
# ---------------------------------------------------------------------------


async def download_and_extract_skill_content(db: AsyncSession, skill: Skill) -> SkillContent | None:
    """Download the skill's cloud ZIP and extract SKILL.md content.

    Returns None (not an exception) if validate_zip_security reports any
    issue, or if download/ZIP/frontmatter parsing raises.
    """
    if not skill.foundry_skill_name:
        return None

    try:
        client = await get_skills_client(db)
        chunks = await asyncio.to_thread(
            lambda: list(
                client.beta.skills.download(
                    skill.foundry_skill_name, headers=FOUNDRY_FEATURES_HEADER
                )
            )
        )
        downloaded_bytes = b"".join(chunks)

        issues = validate_zip_security(downloaded_bytes)
        if issues:
            logger.warning(
                "download_and_extract_skill_content: ZIP failed security validation "
                "for skill %s: %s",
                skill.id,
                "; ".join(issues),
            )
            return None

        with zipfile.ZipFile(io.BytesIO(downloaded_bytes)) as zf:
            raw = zf.read("SKILL.md").decode("utf-8")

        _meta, body = parse_skill_frontmatter(raw)
        content = body.strip()

        return SkillContent(
            name=skill.name,
            description=skill.description or "",
            content=content,
            version_id=skill.foundry_cloud_version or "",
            token_estimate=len(content) // 4,
        )
    except Exception as e:
        logger.warning("download_and_extract_skill_content failed for skill %s: %s", skill.id, e)
        return None


# ---------------------------------------------------------------------------
# Top-level abstraction (D-02, D-04, D-05, D-06) with HIGH-1/MEDIUM-4 fixes
# ---------------------------------------------------------------------------


async def get_skill_content_for_session(db: AsyncSession, scenario_id: str) -> SkillContent | None:
    """Resolve the skill content to inject for a training session/message.

    The single top-level abstraction consumed identically by text and Voice
    Live via the existing focus_instruction channel. Mount-then-MCP-then-
    download-then-local-degrade, with a TTL cache guarding the cloud chain
    and a version-pin bypass preventing pinned scenarios from drifting to the
    cloud's latest version.
    """
    result = await db.execute(select(Scenario).where(Scenario.id == scenario_id))
    scenario = result.scalar_one_or_none()
    if scenario is None or not scenario.skill_id:
        return None

    skill_result = await db.execute(select(Skill).where(Skill.id == scenario.skill_id))
    skill = skill_result.scalar_one_or_none()

    if (
        skill is not None
        and skill.foundry_sync_status == "synced"
        and skill.foundry_skill_name
        and not _scenario_pin_is_stale(scenario)
    ):
        cache_key = (skill.id, skill.foundry_cloud_version or "")
        cached = _cache_get(cache_key)
        if cached is not _CACHE_MISS:
            if cached is not None:
                return cached
            # A cached "cloud failed" result is honored for the rest of the TTL
            # window too, so a flaky/down Foundry endpoint doesn't get hammered
            # every message either -- fall through to the local fallback below.
        else:
            try:
                toolbox_name = await mount_skill_toolbox(db, skill)
                mcp_content = (
                    await _try_mcp_fetch(db, toolbox_name, skill.foundry_skill_name)
                    if toolbox_name
                    else None
                )
                if mcp_content:
                    mcp_result = SkillContent(
                        name=skill.name,
                        description=skill.description or "",
                        content=mcp_content,
                        version_id=skill.foundry_cloud_version or "",
                        token_estimate=len(mcp_content) // 4,
                    )
                    _cache_set(cache_key, mcp_result)
                    return mcp_result

                downloaded = await download_and_extract_skill_content(db, skill)
                _cache_set(cache_key, downloaded)
                if downloaded is not None:
                    return downloaded
            except Exception as e:
                logger.warning(
                    "Cloud skill content unavailable for %s, falling back to local: %s",
                    skill.id,
                    e,
                )
                _cache_set(cache_key, None)

    # Fallback (D-06)
    return await load_skill_for_scenario(db, scenario_id)
