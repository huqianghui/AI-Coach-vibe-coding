"""Foundry Skill sync service: register published Skills as first-class Azure AI
Foundry entities (Phase 28: D-01, D-03, D-06).

Entra-ID-ONLY authentication -- the Skills preview API rejects API keys with a
403 AuthenticationTypeDisabled, so there is NO api_key fallback branch here,
unlike the dual-mode ``agent_sync_service``.

Collision-safe naming (REVIEWS.md HIGH-2): ``_sanitize_skill_name`` alone has no
uniqueness guarantee -- two distinct local skills whose names sanitize to the same
slug would otherwise collide on the same Foundry entity, causing cross-skill cloud
overwrite and, on archive/delete, deletion of the WRONG skill's cloud entity.
``_build_unique_foundry_name`` suffixes the skill's UUID prefix on first sync only;
once ``foundry_skill_name`` is persisted it is reused verbatim on every subsequent
sync/delete call.
"""

import asyncio
import logging
import re

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.skill import Skill
from app.services import agent_sync_service, skill_zip_service

logger = logging.getLogger(__name__)

FOUNDRY_FEATURES_HEADER = {"Foundry-Features": "Skills=V1Preview"}

# ---------------------------------------------------------------------------
# Naming (REVIEWS.md HIGH-2: collision-safe on first sync)
# ---------------------------------------------------------------------------

_NON_ALLOWED_RE = re.compile(r"[^a-z0-9-]+")
_REPEATED_DASH_RE = re.compile(r"-+")


def _sanitize_skill_name(name: str) -> str:
    """Sanitize a skill name into a valid Foundry skill-name slug.

    Lowercase, replace any run of non-``[a-z0-9-]`` with ``-``, collapse
    repeated ``-``, strip leading/trailing ``-``, truncate to 64 chars
    (re-stripping trailing ``-`` after truncation), fallback to ``"skill"``
    if empty. Matches ``^[a-z0-9]([a-z0-9-]*[a-z0-9])?$``.
    """
    sanitized = _NON_ALLOWED_RE.sub("-", name.strip().lower())
    sanitized = _REPEATED_DASH_RE.sub("-", sanitized).strip("-")
    sanitized = sanitized[:64].rstrip("-")
    return sanitized or "skill"


def _build_unique_foundry_name(name: str, skill_id: str) -> str:
    """Build a collision-safe Foundry skill name for a skill's FIRST sync.

    Suffixes the skill's UUID prefix (8 lowercase hex chars, already
    pattern-safe) so two distinct local skills whose names sanitize to the
    same slug can never collide on the same Foundry entity. Only used when
    ``skill.foundry_skill_name`` is empty -- once set, it is reused verbatim
    on every subsequent sync, so this id suffix is generated exactly once
    per skill and never changes even if ``skill.name`` is later edited.
    """
    suffix = "-" + skill_id[:8].lower()
    sanitized_name = _sanitize_skill_name(name)
    max_name_len = 64 - len(suffix)
    name_part = sanitized_name[:max_name_len].rstrip("-")
    if not name_part:
        name_part = "skill"
    return f"{name_part}{suffix}"


# ---------------------------------------------------------------------------
# Entra-ID-only client construction (MEDIUM-6: cached credential)
# ---------------------------------------------------------------------------

_cached_credential = None


def _get_cached_credential():
    """Return the module-level cached DefaultAzureCredential instance.

    DefaultAzureCredential() construction and its first get_token call can
    block for seconds (IMDS probing / interactive fallback); this cache
    avoids reconstructing it on every call.
    """
    global _cached_credential
    if _cached_credential is None:
        _cached_credential = DefaultAzureCredential()
    return _cached_credential


async def get_skills_client(db: AsyncSession):
    """Construct an Entra-ID-ONLY AIProjectClient for the Skills preview surface.

    There is no API-key fallback for this endpoint (T-28-01) -- raises
    RuntimeError with operator guidance if a token cannot be obtained.
    """
    project_endpoint, _api_key = await agent_sync_service.get_project_endpoint(db)

    credential = _get_cached_credential()
    try:
        await asyncio.to_thread(credential.get_token, "https://ai.azure.com/.default")
    except Exception as e:
        raise RuntimeError(
            "No Entra ID credential available for Azure AI Foundry Skills API "
            "(API Key auth is not supported on this preview surface). "
            "Run 'az login' or configure a Managed Identity, then retry. "
            f"Underlying error: {e}"
        ) from e

    return AIProjectClient(endpoint=project_endpoint, credential=credential, allow_preview=True)


# ---------------------------------------------------------------------------
# Sync (D-01, D-03, D-06)
# ---------------------------------------------------------------------------


async def sync_skill_to_foundry(db: AsyncSession, skill: Skill) -> None:
    """Sync a published Skill to Azure AI Foundry as a first-class Skill entity.

    Never raises -- any failure (including a bounded 60s timeout) sets
    foundry_sync_status="failed" and records the error, but the caller's
    local publish/lifecycle operation is never blocked (D-06).
    """
    skill.foundry_sync_status = "pending"
    await db.flush()

    try:
        # HIGH-2 fix: id-suffixed unique name on first sync only. Once set,
        # foundry_skill_name is reused as-is on every future call.
        foundry_name = skill.foundry_skill_name or _build_unique_foundry_name(skill.name, skill.id)

        zip_bytes = await skill_zip_service.export_skill_zip(db, skill.id)

        # T-28-02 defense-in-depth even though the ZIP is server-generated.
        errors = skill_zip_service.validate_zip_security(zip_bytes)
        if errors:
            raise ValueError(f"Skill ZIP failed security validation: {'; '.join(errors)}")

        client = await get_skills_client(db)

        from azure.ai.projects.models import CreateSkillVersionFromFilesBody

        # ASSUMPTION (untested, D-03/WARNING-1): Foundry is assumed to increment
        # result.version when create_from_files is called again with the same
        # skill name. doc 10 Sec 12.4 only invoked this call once -- the confirmed
        # 1->2 increment evidence is from the separate Responses API
        # .versions.create() path, not this surface.
        # See the manual smoke-test note in 28-01-PLAN.md Task 2 <verify>.
        result = await asyncio.wait_for(
            asyncio.to_thread(
                client.beta.skills.create_from_files,
                foundry_name,
                CreateSkillVersionFromFilesBody(
                    files=[(f"{foundry_name}.zip", zip_bytes, "application/zip")]
                ),
                headers=FOUNDRY_FEATURES_HEADER,
            ),
            timeout=60,
        )

        skill.foundry_skill_name = result.name
        skill.foundry_cloud_version = str(getattr(result, "version", "") or "")
        skill.foundry_sync_status = "synced"
        skill.foundry_sync_error = ""
    except Exception as e:
        skill.foundry_sync_status = "failed"
        skill.foundry_sync_error = str(e)[:2000]
        logger.warning("sync_skill_to_foundry failed for skill %s: %s", skill.id, e)
    finally:
        await db.flush()


# ---------------------------------------------------------------------------
# Delete (D-03)
# ---------------------------------------------------------------------------


async def delete_skill_from_foundry(db: AsyncSession, skill: Skill) -> None:
    """Remove a Skill's Foundry cloud entity. Never raises.

    A 404-on-delete is treated as success (already gone / cascade delete),
    mirroring the Toolbox cascade-delete quirk in doc 10 Sec 12.9.
    """
    if not skill.foundry_skill_name:
        return

    try:
        client = await get_skills_client(db)
        await asyncio.to_thread(
            client.beta.skills.delete, skill.foundry_skill_name, headers=FOUNDRY_FEATURES_HEADER
        )
    except Exception as e:
        if getattr(e, "status_code", None) == 404:
            logger.info(
                "delete_skill_from_foundry: skill %s already gone from Foundry (404)", skill.id
            )
        else:
            # WR-03: non-404 failure (network blip, throttling, auth hiccup) means the
            # Foundry-side entity may still exist after this call. The local record is
            # reset below regardless (no retry route exists once a skill is archived --
            # /foundry-sync is restricted to status == "published"), so this MUST be
            # ERROR-level (not WARNING) to be visible in alerting/monitoring: it is the
            # only remaining signal that a cloud entity may now be orphaned with no
            # local reference to it.
            logger.error(
                "delete_skill_from_foundry: non-404 failure for skill %s (foundry_skill_name=%s) "
                "-- local Foundry tracking fields will be reset regardless, cloud entity may be "
                "orphaned: %s",
                skill.id,
                skill.foundry_skill_name,
                e,
            )
    finally:
        skill.foundry_skill_name = ""
        skill.foundry_cloud_version = ""
        skill.foundry_sync_status = "none"
        skill.foundry_sync_error = ""
        await db.flush()


# ---------------------------------------------------------------------------
# Portal URL (D-07 support)
# ---------------------------------------------------------------------------


async def get_skill_portal_url(db: AsyncSession, skill: Skill) -> str:
    """Best-effort Azure AI Foundry Portal deep link for a synced Skill.

    Claude's Discretion per 28-CONTEXT.md: no confirmed Skills-specific
    deep-link path in research; this is the best-effort analog of the
    existing agent portal URL. Falls back to the generic Foundry URL when
    the skill has never synced or portal URL components can't be resolved.
    """
    if not skill.foundry_skill_name:
        return "https://ai.azure.com"

    components = await agent_sync_service.get_portal_url_components(db)
    required_keys = ("subscription_hash", "resource_group", "resource_name", "project_name")
    if components and all(components.get(k) for k in required_keys):
        sub_hash = components["subscription_hash"]
        rg = components["resource_group"]
        resource_name = components["resource_name"]
        project_name = components["project_name"]
        return (
            f"https://ai.azure.com/nextgen/r/{sub_hash},{rg},,{resource_name},{project_name}"
            f"/build/skills/{skill.foundry_skill_name}"
        )

    return "https://ai.azure.com"
