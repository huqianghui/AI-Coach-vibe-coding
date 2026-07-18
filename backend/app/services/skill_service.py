"""Skill service: CRUD, lifecycle management, and file security."""

import pathlib
import re

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.skill import VALID_TRANSITIONS, Skill, SkillVersion
from app.schemas.skill import SkillCreate, SkillUpdate
from app.services import skill_foundry_service
from app.utils.exceptions import bad_request, not_found

# ---------------------------------------------------------------------------
# File security constants
# ---------------------------------------------------------------------------

ALLOWED_RESOURCE_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".pptx",
    ".txt",
    ".md",
    ".py",
    ".json",
    ".csv",
    ".xlsx",
}
MAX_FILE_SIZE = 4 * 1024 * 1024  # 4MB per file, constrained by Container Apps ingress
MAX_FILES_PER_UPLOAD = 10
MAX_RESOURCES_PER_SKILL = 100

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

# Control character pattern (C0 + C1 minus common whitespace)
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def validate_status_transition(current: str, target: str) -> None:
    """Enforce strict state machine transitions.

    This is the SOLE transition enforcement point.
    """
    allowed = VALID_TRANSITIONS.get(current, set())
    if target not in allowed:
        bad_request(f"Invalid status transition from '{current}' to '{target}'. Allowed: {allowed}")


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename for safe storage.

    - Strip directory separators
    - Reject path traversal (..)
    - Reject absolute paths
    - Reject control characters
    - Return base filename only
    """
    if not filename:
        bad_request("Filename is required")

    # Reject path traversal
    if ".." in filename:
        bad_request("Filename must not contain '..'")

    # Reject absolute paths
    if filename.startswith("/") or filename.startswith("\\"):
        bad_request("Filename must not be an absolute path")

    # Extract base filename using PurePosixPath
    safe_name = pathlib.PurePosixPath(filename).name

    if not safe_name:
        bad_request("Filename is empty after sanitization")

    # Reject control characters
    if _CONTROL_CHARS_RE.search(safe_name):
        bad_request("Filename must not contain control characters")

    return safe_name


def validate_file_upload(filename: str, file_size: int) -> None:
    """Validate file extension and size for upload security."""
    ext = pathlib.PurePosixPath(filename).suffix.lower()
    if ext not in ALLOWED_RESOURCE_EXTENSIONS:
        bad_request(
            f"File type '{ext}' not allowed. "
            f"Allowed: {', '.join(sorted(ALLOWED_RESOURCE_EXTENSIONS))}"
        )
    if file_size > MAX_FILE_SIZE:
        bad_request(f"File size exceeds maximum of {MAX_FILE_SIZE // (1024 * 1024)}MB")


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------


async def create_skill(db: AsyncSession, data: SkillCreate, user_id: str) -> Skill:
    """Create a new skill with initial draft version."""
    skill = Skill(
        name=data.name,
        description=data.description,
        product=data.product,
        therapeutic_area=data.therapeutic_area,
        compatibility=data.compatibility,
        tags=data.tags,
        content=data.content,
        metadata_json=data.metadata_json,
        created_by=user_id,
        updated_by=user_id,
        status="draft",
        current_version=1,
    )
    db.add(skill)
    await db.flush()

    # Create initial version snapshot
    version = SkillVersion(
        skill_id=skill.id,
        version_number=1,
        content=data.content,
        metadata_json=data.metadata_json,
        is_published=False,
        created_by=user_id,
    )
    db.add(version)
    await db.flush()

    # Re-query with relationships loaded
    result = await db.execute(
        select(Skill)
        .options(selectinload(Skill.versions), selectinload(Skill.resources))
        .where(Skill.id == skill.id)
    )
    return result.scalar_one()


async def get_skills(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    product: str | None = None,
    search: str | None = None,
) -> tuple[list[Skill], int]:
    """List skills with optional filters and pagination."""
    query = select(Skill)

    if status:
        query = query.where(Skill.status == status)
    if product:
        query = query.where(Skill.product == product)
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            (Skill.name.ilike(search_pattern)) | (Skill.description.ilike(search_pattern))
        )

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    query = query.order_by(Skill.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return items, total


async def get_published_skills(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
) -> tuple[list[Skill], int]:
    """List published skills only."""
    return await get_skills(db, page=page, page_size=page_size, status="published", search=search)


async def get_skill(db: AsyncSession, skill_id: str) -> Skill:
    """Get a single skill with versions and resources. Raises 404 if not found."""
    result = await db.execute(
        select(Skill)
        .options(selectinload(Skill.versions), selectinload(Skill.resources))
        .where(Skill.id == skill_id)
    )
    skill = result.scalar_one_or_none()
    if skill is None:
        not_found("Skill not found")
    return skill


async def update_skill(db: AsyncSession, skill_id: str, data: SkillUpdate, user_id: str) -> Skill:
    """Update skill metadata and/or trigger status transition."""
    skill = await get_skill(db, skill_id)

    update_data = data.model_dump(exclude_unset=True)

    # Validate status transition if status is being changed
    if "status" in update_data and update_data["status"] != skill.status:
        validate_status_transition(skill.status, update_data["status"])

    for field, value in update_data.items():
        setattr(skill, field, value)

    skill.updated_by = user_id
    await db.flush()

    # Re-query with relationships
    result = await db.execute(
        select(Skill)
        .options(selectinload(Skill.versions), selectinload(Skill.resources))
        .where(Skill.id == skill_id)
    )
    return result.scalar_one()


async def delete_skill(db: AsyncSession, skill_id: str) -> None:
    """Delete a skill. Only draft/failed skills can be deleted."""
    skill = await get_skill(db, skill_id)
    if skill.status not in {"draft", "failed"}:
        bad_request("Cannot delete a skill that is under review, published, or archived")

    # Defensive: covers a skill that was synced then reverted to draft/failed.
    await skill_foundry_service.delete_skill_from_foundry(db, skill)

    # Delete associated resource files from storage
    from app.services.storage import get_storage

    storage = get_storage()
    for resource in skill.resources:
        try:
            await storage.delete(resource.storage_path)
        except Exception:
            pass  # Best-effort file cleanup

    await db.delete(skill)
    await db.flush()


# ---------------------------------------------------------------------------
# Lifecycle operations
# ---------------------------------------------------------------------------


async def publish_skill(db: AsyncSession, skill_id: str, user_id: str) -> Skill:
    """Publish a skill: enforce quality gates, create published version snapshot."""
    skill = await get_skill(db, skill_id)

    # Deliberate (WARNING-2): idempotent re-publish does not re-trigger
    # Foundry sync. Retry a failed/pending sync via POST /{id}/foundry-sync (Plan 28-03,
    # restricted to published-status skills only per MEDIUM-5).
    # Idempotent: if already published, return as-is
    if skill.status == "published":
        return skill

    # The UI publish action is the review gate: generated skills remain draft
    # after quality evaluation, then publish directly from the confirmation dialog.
    if skill.status == "draft":
        validate_status_transition(skill.status, "review")
        skill.status = "review"

    validate_status_transition(skill.status, "published")

    # Quality gates
    if not skill.structure_check_passed:
        bad_request("L1 structure check must pass before publishing")

    if skill.quality_score is None or skill.quality_score < 50:
        bad_request("Quality score must be at least 50 to publish")

    # Transactional staleness check (T-19-13: prevent publish with stale evaluation)
    from app.services.skill_evaluation_service import is_evaluation_stale

    if is_evaluation_stale(skill):
        bad_request(
            "Quality evaluation is stale -- content has changed since last evaluation. "
            "Please re-run quality assessment."
        )

    # Invariant: single published version
    # Mark all existing versions as not published
    await db.execute(
        update(SkillVersion).where(SkillVersion.skill_id == skill_id).values(is_published=False)
    )

    # Create new published version snapshot
    version = SkillVersion(
        skill_id=skill.id,
        version_number=skill.current_version,
        content=skill.content,
        metadata_json=skill.metadata_json,
        is_published=True,
        created_by=user_id,
    )
    db.add(version)

    skill.status = "published"
    skill.updated_by = user_id
    await db.flush()

    # Re-query with relationships
    result = await db.execute(
        select(Skill)
        .options(selectinload(Skill.versions), selectinload(Skill.resources))
        .where(Skill.id == skill_id)
    )
    skill = result.scalar_one()

    # D-01: register the newly-published skill as a first-class Foundry entity.
    # Never blocks/fails the local publish (D-06) -- sync_skill_to_foundry has
    # its own internal try/except and never raises.
    await skill_foundry_service.sync_skill_to_foundry(db, skill)

    # Re-query once more so the returned object reflects the updated foundry_* columns.
    result = await db.execute(
        select(Skill)
        .options(selectinload(Skill.versions), selectinload(Skill.resources))
        .where(Skill.id == skill_id)
    )
    return result.scalar_one()


async def create_new_version(db: AsyncSession, skill_id: str, user_id: str) -> Skill:
    """Create a new draft version from a published skill."""
    skill = await get_skill(db, skill_id)

    if skill.status != "published":
        bad_request("Can only create new version from a published skill")

    # Increment version and reset to draft
    skill.current_version += 1
    skill.status = "draft"
    skill.updated_by = user_id

    # Reset quality fields
    skill.structure_check_passed = None
    skill.structure_check_details = "{}"
    skill.quality_score = None
    skill.quality_verdict = None
    skill.quality_details = "{}"

    await db.flush()

    # Re-query with relationships
    result = await db.execute(
        select(Skill)
        .options(selectinload(Skill.versions), selectinload(Skill.resources))
        .where(Skill.id == skill_id)
    )
    return result.scalar_one()


async def archive_skill(db: AsyncSession, skill_id: str, user_id: str) -> Skill:
    """Archive a published skill."""
    skill = await get_skill(db, skill_id)
    validate_status_transition(skill.status, "archived")

    skill.status = "archived"
    skill.updated_by = user_id
    await db.flush()

    # D-03: remove the Foundry cloud entity when a skill is archived.
    await skill_foundry_service.delete_skill_from_foundry(db, skill)

    # Re-query with relationships
    result = await db.execute(
        select(Skill)
        .options(selectinload(Skill.versions), selectinload(Skill.resources))
        .where(Skill.id == skill_id)
    )
    return result.scalar_one()


async def restore_skill(db: AsyncSession, skill_id: str, user_id: str) -> Skill:
    """Restore an archived or failed skill to draft."""
    skill = await get_skill(db, skill_id)
    validate_status_transition(skill.status, "draft")

    skill.status = "draft"
    skill.updated_by = user_id
    await db.flush()

    # Re-query with relationships
    result = await db.execute(
        select(Skill)
        .options(selectinload(Skill.versions), selectinload(Skill.resources))
        .where(Skill.id == skill_id)
    )
    return result.scalar_one()
