"""Skill management API endpoints."""

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.dependencies import get_db, require_role
from app.models.material import MaterialVersion, TrainingMaterial
from app.models.skill import Skill, SkillResource, SkillSourceMaterial
from app.models.user import User
from app.schemas.skill import (
    SkillCreate,
    SkillFoundryPortalUrlResponse,
    SkillListOut,
    SkillOut,
    SkillResourceOut,
    SkillUpdate,
    StructureCheckOut,
)
from app.services import (
    skill_evaluation_service,
    skill_foundry_service,
    skill_service,
    skill_zip_service,
)
from app.services.skill_service import (
    MAX_FILES_PER_UPLOAD,
    MAX_RESOURCES_PER_SKILL,
    sanitize_filename,
    validate_file_upload,
)
from app.services.skill_text_extractor import extract_text
from app.services.skill_validation_service import check_skill_structure, to_dict
from app.services.storage import get_storage
from app.utils.exceptions import bad_request, not_found
from app.utils.pagination import PaginatedResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/skills", tags=["skills"])

VALID_RESOURCE_TYPES = {"reference", "script", "asset"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_source_materials(db: AsyncSession, skill_id: str) -> list[dict]:
    """Fetch source material info for a skill (for bidirectional navigation)."""
    result = await db.execute(
        select(TrainingMaterial.id, TrainingMaterial.name, TrainingMaterial.product)
        .join(SkillSourceMaterial, SkillSourceMaterial.material_id == TrainingMaterial.id)
        .where(SkillSourceMaterial.skill_id == skill_id)
    )
    return [{"id": r.id, "name": r.name, "product": r.product} for r in result.all()]


# ---------------------------------------------------------------------------
# Static routes FIRST (before /{skill_id})
# ---------------------------------------------------------------------------


@router.post("", response_model=SkillOut, status_code=201)
async def create_skill(
    data: SkillCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """Create a new skill. Admin only."""
    skill = await skill_service.create_skill(db, data, user.id)
    return skill


@router.get("", response_model=PaginatedResponse[SkillListOut])
async def list_skills(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    product: str | None = Query(None),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
):
    """List skills with optional filters. Admin only."""
    items, total = await skill_service.get_skills(
        db, page=page, page_size=page_size, status=status, product=product, search=search
    )
    return PaginatedResponse.create(
        items=[SkillListOut.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/published", response_model=PaginatedResponse[SkillListOut])
async def list_published_skills(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
):
    """List published skills only. Admin only."""
    items, total = await skill_service.get_published_skills(
        db, page=page, page_size=page_size, search=search
    )
    return PaginatedResponse.create(
        items=[SkillListOut.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


class CreateFromMaterialsRequest(BaseModel):
    """Request body for creating a skill from existing training materials."""

    material_ids: list[str]
    name: str = "New Skill"
    product: str = ""


@router.post("/create-from-agent", status_code=202)
@router.post("/from-materials", status_code=202)
async def create_skill_from_agent(
    body: CreateFromMaterialsRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """Create a skill from materials using the configured creator agent."""
    if not body.material_ids:
        bad_request("At least one material_id is required")

    # Validate materials and collect versions (same logic as from-materials)
    material_versions: list[MaterialVersion] = []
    for mid in body.material_ids:
        result = await db.execute(
            select(TrainingMaterial).where(
                TrainingMaterial.id == mid, TrainingMaterial.is_archived.is_(False)
            )
        )
        material = result.scalar_one_or_none()
        if material is None:
            not_found(f"Material {mid} not found or archived")

        ver_result = await db.execute(
            select(MaterialVersion)
            .where(
                MaterialVersion.material_id == mid,
                MaterialVersion.is_active == True,  # noqa: E712
            )
            .order_by(MaterialVersion.version_number.desc())
            .limit(1)
        )
        version = ver_result.scalar_one_or_none()
        if version is None:
            bad_request(f"Material {mid} has no active version")

        if not body.product and material.product:
            body.product = material.product
        material_versions.append(version)

    # Create the skill record
    skill_data = SkillCreate(name=body.name, product=body.product)
    skill = await skill_service.create_skill(db, skill_data, user.id)
    await db.flush()

    # Persist source material links
    for mid in body.material_ids:
        db.add(SkillSourceMaterial(skill_id=skill.id, material_id=mid))

    # Copy material files into skill resources
    storage = get_storage()
    for version in material_versions:
        file_bytes = await storage.read(version.storage_url)

        storage_path = f"skills/{skill.id}/references/{version.filename}"
        await storage.save(storage_path, file_bytes)

        resource = SkillResource(
            skill_id=skill.id,
            resource_type="reference",
            filename=version.filename,
            storage_path=storage_path,
            content_type=version.content_type,
            file_size=version.file_size,
        )
        db.add(resource)

    skill.conversion_status = "processing"
    await db.flush()
    await db.commit()

    # Run agent-based creation in background
    asyncio.create_task(_run_agent_creation(skill.id))

    return JSONResponse(
        status_code=202,
        content={
            "id": skill.id,
            "status": "processing",
            "method": "agent",
            "materials_copied": len(material_versions),
        },
    )


async def _run_agent_creation(skill_id: str) -> None:
    """Background task for agent-based skill creation."""
    from app.services import skill_creator_service

    async with AsyncSessionLocal() as session:
        try:
            result = await skill_creator_service.create_skill_via_agent(session, skill_id)
            await session.commit()
            logger.info(
                "Agent creation completed for skill %s: status=%s",
                skill_id,
                result.status,
            )
        except Exception as e:
            await session.rollback()
            async with AsyncSessionLocal() as err_session:
                try:
                    skill = await err_session.get(Skill, skill_id)
                    if skill:
                        skill.conversion_status = "failed"
                        skill.conversion_error = str(e)[:2000]
                        await err_session.commit()
                except Exception:
                    logger.error("Failed to record agent creation error for %s", skill_id)
            logger.error("Agent creation failed for %s: %s", skill_id, e)


# ---------------------------------------------------------------------------
# Request schemas for conversion endpoints
# ---------------------------------------------------------------------------


class RegenerateSopRequest(BaseModel):
    """Request body for AI feedback SOP regeneration."""

    feedback: str


# ---------------------------------------------------------------------------
# Conversion and regeneration endpoints (before /{skill_id} per Gotcha #3)
# ---------------------------------------------------------------------------


@router.post("/import", response_model=SkillOut, status_code=201)
async def import_skill(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """Import a Skill from a ZIP archive. Admin only."""
    if not file.filename or not file.filename.endswith(".zip"):
        bad_request("File must be a .zip archive")
    zip_bytes = await file.read()
    if len(zip_bytes) > skill_zip_service.MAX_ZIP_SIZE_BYTES:
        bad_request(
            f"ZIP file exceeds maximum size of "
            f"{skill_zip_service.MAX_ZIP_SIZE_BYTES // (1024 * 1024)}MB"
        )
    skill = await skill_zip_service.import_skill_zip(db, zip_bytes, created_by=user.id)
    await db.commit()

    # Re-query to ensure relationships are loaded for response serialization
    skill = await skill_service.get_skill(db, skill.id)
    return skill


@router.post("/{skill_id}/convert")
async def convert_skill(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
):
    """Start agent-based skill conversion. Admin only. Returns 202 Accepted."""
    skill = await skill_service.get_skill(db, skill_id)

    # Verify at least one reference resource exists
    ref_result = await db.execute(
        select(SkillResource).where(
            SkillResource.skill_id == skill_id,
            SkillResource.resource_type == "reference",
        )
    )
    refs = list(ref_result.scalars().all())
    if not refs:
        bad_request("No reference materials found. Upload at least one reference file first.")

    if skill.conversion_status == "processing":
        bad_request("Conversion already in progress")

    skill.conversion_status = "processing"
    skill.conversion_error = ""
    await db.flush()
    await db.commit()

    asyncio.create_task(_run_agent_creation(skill_id))

    return JSONResponse(
        status_code=202,
        content={"status": "processing", "method": "agent"},
    )


@router.post("/{skill_id}/retry-conversion")
async def retry_conversion(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
):
    """Retry a failed conversion using agent. Admin only."""
    skill = await skill_service.get_skill(db, skill_id)

    if skill.conversion_status not in ("failed", None):
        bad_request(f"Can only retry failed conversions. Current status: {skill.conversion_status}")

    skill.conversion_status = "processing"
    skill.conversion_error = ""
    await db.flush()
    await db.commit()

    asyncio.create_task(_run_agent_creation(skill_id))

    return JSONResponse(
        status_code=202,
        content={"status": "processing", "method": "agent"},
    )


@router.get("/{skill_id}/conversion-status")
async def get_conversion_status(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
):
    """Poll conversion status with step-level progress. Admin only."""
    skill = await skill_service.get_skill(db, skill_id)
    response: dict = {
        "status": skill.conversion_status,
        "error": skill.conversion_error,
        "conversion_status": skill.conversion_status,
        "conversion_error": skill.conversion_error,
        "conversion_job_id": skill.conversion_job_id,
    }
    # Include step-level progress if available
    try:
        meta = json.loads(skill.metadata_json or "{}")
        if "conversion_progress" in meta:
            response["progress"] = meta["conversion_progress"]
    except (json.JSONDecodeError, TypeError):
        pass
    return response


@router.post("/{skill_id}/upload-and-convert")
async def upload_and_convert(
    skill_id: str,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """Upload reference files and trigger conversion. Max 10 files. Admin only."""
    skill = await skill_service.get_skill(db, skill_id)

    if len(files) > MAX_FILES_PER_UPLOAD:
        bad_request(f"Maximum {MAX_FILES_PER_UPLOAD} files per upload")

    # Check existing resource count
    count_result = await db.execute(select(SkillResource).where(SkillResource.skill_id == skill_id))
    existing_count = len(count_result.scalars().all())
    if existing_count + len(files) > MAX_RESOURCES_PER_SKILL:
        bad_request(f"Maximum {MAX_RESOURCES_PER_SKILL} resources per skill")

    storage = get_storage()

    # Upload each file as a reference resource
    for file in files:
        if not file.filename:
            bad_request("File name is required")
        safe_filename = sanitize_filename(file.filename)

        content = await file.read()
        file_size = len(content)
        validate_file_upload(safe_filename, file_size)

        storage_path = f"skills/{skill_id}/references/{safe_filename}"
        await storage.save(storage_path, content)

        ext = safe_filename.rsplit(".", 1)[-1].lower() if "." in safe_filename else ""
        content_type_map = {
            "pdf": "application/pdf",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "txt": "text/plain",
            "md": "text/markdown",
        }
        content_type = content_type_map.get(ext, file.content_type or "application/octet-stream")

        resource = SkillResource(
            skill_id=skill_id,
            resource_type="reference",
            filename=safe_filename,
            storage_path=storage_path,
            content_type=content_type,
            file_size=file_size,
        )
        db.add(resource)

    # Trigger agent-based conversion
    skill.conversion_status = "processing"
    skill.conversion_error = ""
    await db.flush()
    await db.commit()

    asyncio.create_task(_run_agent_creation(skill_id))

    return JSONResponse(
        status_code=202,
        content={"status": "processing", "method": "agent", "files_uploaded": len(files)},
    )


@router.post("/{skill_id}/regenerate-sop", response_model=SkillOut)
async def regenerate_sop(
    skill_id: str,
    body: RegenerateSopRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
):
    """AI feedback SOP regeneration. Admin only."""
    if not body.feedback or not body.feedback.strip():
        bad_request("Feedback is required")
    if len(body.feedback) > 5000:
        bad_request("Feedback must be 5000 characters or less")

    from app.services import skill_conversion_service

    skill = await skill_conversion_service.regenerate_sop_with_feedback(db, skill_id, body.feedback)
    return skill


# ---------------------------------------------------------------------------
# Parameterized routes
# ---------------------------------------------------------------------------


@router.get("/{skill_id}/export")
async def export_skill(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
):
    """Export a Skill as a ZIP archive. Admin only."""
    zip_bytes = await skill_zip_service.export_skill_zip(db, skill_id)
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=skill-{skill_id}.zip"},
    )


@router.get("/{skill_id}", response_model=SkillOut)
async def get_skill(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
):
    """Get a single skill with versions and resources. Admin only."""
    skill = await skill_service.get_skill(db, skill_id)
    result = SkillOut.model_validate(skill)
    result.source_materials = await _get_source_materials(db, skill_id)
    return result


@router.put("/{skill_id}", response_model=SkillOut)
async def update_skill(
    skill_id: str,
    data: SkillUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """Update skill metadata. Admin only."""
    skill = await skill_service.update_skill(db, skill_id, data, user.id)
    return skill


@router.delete("/{skill_id}", status_code=204)
async def delete_skill(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
):
    """Delete a draft or failed skill. Admin only."""
    await skill_service.delete_skill(db, skill_id)
    return Response(status_code=204)


@router.post("/{skill_id}/publish", response_model=SkillOut)
async def publish_skill(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """Publish a skill after quality gate checks. Admin only."""
    skill = await skill_service.publish_skill(db, skill_id, user.id)
    return skill


@router.post("/{skill_id}/archive", response_model=SkillOut)
async def archive_skill(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """Archive a published skill. Admin only."""
    skill = await skill_service.archive_skill(db, skill_id, user.id)
    return skill


@router.post("/{skill_id}/restore", response_model=SkillOut)
async def restore_skill(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """Restore an archived or failed skill to draft. Admin only."""
    skill = await skill_service.restore_skill(db, skill_id, user.id)
    return skill


@router.post("/{skill_id}/new-version", response_model=SkillOut)
async def create_new_version(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """Create a new draft version from a published skill. Admin only."""
    skill = await skill_service.create_new_version(db, skill_id, user.id)
    return skill


@router.post("/{skill_id}/foundry-sync", response_model=SkillOut)
async def retry_foundry_sync(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
):
    """Manually retry Foundry sync for a skill. Admin only. D-06.

    Restricted to skill.status == "published" (MEDIUM-5): an "archived" skill's Foundry
    entity was already deleted by the archive lifecycle hook (Plan 28-01, D-03) -- allowing
    retry here would silently re-create ("resurrect") a cloud entity the user intentionally
    removed. A restored skill lands in "draft" (skill_service.restore_skill) and must go
    through publish_skill() again, which unconditionally re-syncs -- so this guard cannot
    orphan any reachable skill state.
    """
    skill = await skill_service.get_skill(db, skill_id)
    if skill.status != "published":
        bad_request("Foundry sync retry is only available for published skills")
    await skill_foundry_service.sync_skill_to_foundry(db, skill)
    result = SkillOut.model_validate(skill)
    result.source_materials = await _get_source_materials(db, skill_id)
    return result


@router.get("/{skill_id}/foundry-portal-url", response_model=SkillFoundryPortalUrlResponse)
async def get_skill_foundry_portal_url(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
):
    """Get the Azure Portal deep-link for this skill's Foundry entity. Admin only. D-07."""
    skill = await skill_service.get_skill(db, skill_id)
    url = await skill_foundry_service.get_skill_portal_url(db, skill)
    return SkillFoundryPortalUrlResponse(
        url=url,
        skill_name=skill.foundry_skill_name,
        foundry_version=skill.foundry_cloud_version,
    )


# ---------------------------------------------------------------------------
# Quality gate routes (L1 structure check + L2 AI evaluation)
# ---------------------------------------------------------------------------


@router.post("/{skill_id}/check-structure", response_model=StructureCheckOut)
async def run_structure_check(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
):
    """Run L1 structure check on a skill. Instant, rule-based. Admin only."""
    skill = await skill_service.get_skill(db, skill_id)
    result = await check_skill_structure(skill)

    # Update skill with check results
    skill.structure_check_passed = result.passed
    skill.structure_check_details = json.dumps(to_dict(result), ensure_ascii=False)
    await db.flush()

    return StructureCheckOut(
        passed=result.passed,
        score=result.score,
        issues=[
            {
                "severity": issue.severity,
                "dimension": issue.dimension,
                "message": issue.message,
                "suggestion": issue.suggestion,
            }
            for issue in result.issues
        ],
    )


@router.post("/{skill_id}/evaluate-quality")
async def run_quality_evaluation(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
):
    """Trigger L2 AI quality evaluation (async background task). Admin only.

    Returns 202 Accepted immediately. Poll GET /{skill_id}/evaluation for results.
    """
    # Verify skill exists
    await skill_service.get_skill(db, skill_id)

    async def _run_evaluation(sid: str) -> None:
        """Durable background evaluation task with its own DB session."""
        async with AsyncSessionLocal() as session:
            try:
                await skill_evaluation_service.evaluate_skill_quality(session, sid)
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error("L2 evaluation failed for skill %s: %s", sid, e, exc_info=True)
                # Persist error into quality_details so frontend polling can see it
                import json as _json

                async with AsyncSessionLocal() as err_session:
                    from app.models.skill import Skill as _Skill

                    _result = await err_session.execute(select(_Skill).where(_Skill.id == sid))
                    _skill = _result.scalar_one_or_none()
                    if _skill:
                        _skill.quality_score = 0
                        _skill.quality_verdict = "ERROR"
                        _skill.quality_details = _json.dumps(
                            {
                                "evaluation_status": "ai_error",
                                "error_detail": str(e)[:500],
                            },
                            ensure_ascii=False,
                        )
                        await err_session.commit()

    asyncio.create_task(_run_evaluation(skill_id))
    return JSONResponse(status_code=202, content={"status": "evaluating"})


@router.get("/{skill_id}/evaluation")
async def get_evaluation_results(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
):
    """Get combined L1 + L2 evaluation results with staleness indicator. Admin only."""
    skill = await skill_service.get_skill(db, skill_id)

    # Parse stored details
    try:
        structure_details = json.loads(skill.structure_check_details or "{}")
    except (json.JSONDecodeError, TypeError):
        structure_details = {}

    try:
        quality_details = json.loads(skill.quality_details or "{}")
    except (json.JSONDecodeError, TypeError):
        quality_details = {}

    # Staleness check
    is_stale = skill_evaluation_service.is_evaluation_stale(skill)

    # Extract evaluation status and model metadata from stored details
    evaluation_status = quality_details.get("evaluation_status", "ai_success")
    model_used = quality_details.get("model_used", "")
    error_detail = quality_details.get("error_detail", "")

    return {
        "structure_check": {
            "passed": skill.structure_check_passed,
            "details": structure_details,
        },
        "quality": {
            "score": skill.quality_score,
            "verdict": skill.quality_verdict,
            "details": quality_details,
            "is_stale": is_stale,
            "evaluation_status": evaluation_status,
            "model_used": model_used,
            "error_detail": error_detail,
        },
        "evaluation_criteria": [
            {"name": dim_name}
            for dim_name in skill_evaluation_service._load_evaluation_dimensions()
        ],
    }


# ---------------------------------------------------------------------------
# Resource routes with file security
# ---------------------------------------------------------------------------


@router.post("/{skill_id}/resources", response_model=SkillResourceOut, status_code=201)
async def upload_resource(
    skill_id: str,
    file: UploadFile = File(...),
    resource_type: str = Query(..., pattern="^(reference|script|asset)$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """Upload a resource file to a skill. Admin only."""
    # Verify skill exists
    await skill_service.get_skill(db, skill_id)

    # Validate resource_type
    if resource_type not in VALID_RESOURCE_TYPES:
        bad_request(f"Invalid resource_type. Must be one of: {VALID_RESOURCE_TYPES}")

    # Validate filename
    if not file.filename:
        bad_request("File name is required")
    safe_filename = sanitize_filename(file.filename)

    # Read content
    content = await file.read()
    file_size = len(content)

    # Validate extension and size
    validate_file_upload(safe_filename, file_size)

    # Check resource count limit
    count_result = await db.execute(select(SkillResource).where(SkillResource.skill_id == skill_id))
    existing_count = len(count_result.scalars().all())
    if existing_count >= MAX_RESOURCES_PER_SKILL:
        bad_request(f"Maximum {MAX_RESOURCES_PER_SKILL} resources per skill")

    # Store file
    storage_path = f"skills/{skill_id}/{resource_type}s/{safe_filename}"
    storage = get_storage()
    await storage.save(storage_path, content)

    # Determine content type from extension
    ext = safe_filename.rsplit(".", 1)[-1].lower() if "." in safe_filename else ""
    content_type_map = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "txt": "text/plain",
        "md": "text/markdown",
        "py": "text/x-python",
        "json": "application/json",
        "csv": "text/csv",
    }
    content_type = content_type_map.get(ext, file.content_type or "application/octet-stream")

    # WR-01 fix: extract text immediately so ZIP export / Foundry sync doesn't
    # silently ship a placeholder stub for directly-uploaded PDF/DOCX/PPTX/TXT/MD
    # resources (only AI-conversion-pipeline resources previously got real text).
    extracted_text = extract_text(content, safe_filename)
    extraction_status = "completed" if extracted_text else "failed"

    # Create resource record
    resource = SkillResource(
        skill_id=skill_id,
        resource_type=resource_type,
        filename=safe_filename,
        storage_path=storage_path,
        content_type=content_type,
        file_size=file_size,
        text_content=extracted_text,
        extraction_status=extraction_status,
    )
    db.add(resource)
    await db.flush()

    return resource


@router.get("/{skill_id}/resources", response_model=list[SkillResourceOut])
async def list_resources(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
):
    """List all resources for a skill. Admin only."""
    # Verify skill exists
    await skill_service.get_skill(db, skill_id)

    result = await db.execute(
        select(SkillResource)
        .where(SkillResource.skill_id == skill_id)
        .order_by(SkillResource.created_at.desc())
    )
    return list(result.scalars().all())


@router.delete("/{skill_id}/resources/{resource_id}", status_code=204)
async def delete_resource(
    skill_id: str,
    resource_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
):
    """Delete a resource from a skill. Admin only."""
    result = await db.execute(
        select(SkillResource).where(
            SkillResource.id == resource_id,
            SkillResource.skill_id == skill_id,
        )
    )
    resource = result.scalar_one_or_none()
    if resource is None:
        not_found("Resource not found")

    # Delete file from storage
    storage = get_storage()
    try:
        await storage.delete(resource.storage_path)
    except Exception:
        pass  # Best-effort file cleanup

    await db.delete(resource)
    await db.flush()
    return Response(status_code=204)


@router.get(
    "/{skill_id}/resources/{resource_id}/download",
    responses={200: {"content": {"application/octet-stream": {}}}},
)
async def download_resource(
    skill_id: str,
    resource_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
):
    """Download a resource file. Never exposes storage_path. Admin only."""
    result = await db.execute(
        select(SkillResource).where(
            SkillResource.id == resource_id,
            SkillResource.skill_id == skill_id,
        )
    )
    resource = result.scalar_one_or_none()
    if resource is None:
        not_found("Resource not found")

    storage = get_storage()
    if not await storage.exists(resource.storage_path):
        not_found("File not found in storage")

    content = await storage.read(resource.storage_path)
    disposition = f'attachment; filename="{resource.filename}"'

    return Response(
        content=content,
        media_type=resource.content_type or "application/octet-stream",
        headers={"Content-Disposition": disposition},
    )
