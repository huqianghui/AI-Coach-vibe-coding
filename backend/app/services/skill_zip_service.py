"""ZIP export/import service for Skill packages with security hardening.

Addresses D-27: Skill sharing across environments via ZIP format.
Security: zip bomb protection, path traversal rejection, symlink rejection,
extension whitelist, directory whitelist, entry count limits, nesting depth limits.
"""

import io
import logging
import os
import zipfile
from pathlib import PurePosixPath

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.skill import Skill, SkillResource
from app.schemas.skill import SkillCreate
from app.services import skill_service
from app.utils.exceptions import ConflictException, bad_request, not_found

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hard limits for ZIP import security
# ---------------------------------------------------------------------------

MAX_ZIP_SIZE_BYTES = 100 * 1024 * 1024  # 100MB compressed
MAX_UNCOMPRESSED_SIZE_BYTES = 100 * 1024 * 1024  # 100MB uncompressed total
MAX_ZIP_ENTRIES = 500  # Max files in archive
MAX_PATH_DEPTH = 5  # Max directory nesting
MAX_SINGLE_FILE_SIZE = 50 * 1024 * 1024  # 50MB per file

ALLOWED_IMPORT_EXTENSIONS = {
    ".md",
    ".txt",
    ".pdf",
    ".docx",
    ".pptx",
    ".py",
    ".json",
    ".yaml",
    ".yml",
    ".csv",
    ".png",
    ".jpg",
    ".jpeg",
    ".svg",
    ".gif",
}

ALLOWED_DIRECTORIES = {"references", "scripts", "assets"}


# ---------------------------------------------------------------------------
# Security validation
# ---------------------------------------------------------------------------


def validate_zip_security(zip_bytes: bytes) -> list[str]:
    """Validate ZIP archive for security threats.

    Returns list of error strings (empty = valid).
    Checks: size, entry count, path traversal, symlinks, depth, extensions, zip bomb.
    """
    errors: list[str] = []

    # Check compressed size
    if len(zip_bytes) > MAX_ZIP_SIZE_BYTES:
        errors.append(
            f"ZIP file size ({len(zip_bytes)} bytes) exceeds maximum of {MAX_ZIP_SIZE_BYTES} bytes"
        )
        return errors  # Don't even try to open if too large

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        errors.append("Invalid ZIP file format")
        return errors

    entries = zf.infolist()

    # Check entry count
    if len(entries) > MAX_ZIP_ENTRIES:
        errors.append(f"ZIP contains {len(entries)} entries, maximum is {MAX_ZIP_ENTRIES}")

    total_uncompressed = 0

    for entry in entries:
        name = entry.filename

        # Skip directory entries
        if name.endswith("/"):
            continue

        # Path traversal check
        if ".." in name:
            errors.append(f"Path traversal detected: '{name}' contains '..'")

        if name.startswith("/"):
            errors.append(f"Absolute path detected: '{name}'")

        # Symlink check (external_attr upper nibble 0xA = symlink)
        if (entry.external_attr >> 28) == 0xA:
            errors.append(f"Symlink detected: '{name}'")

        # Path depth check
        parts = PurePosixPath(name).parts
        if len(parts) > MAX_PATH_DEPTH:
            errors.append(
                f"Path too deep ({len(parts)} levels): '{name}', maximum is {MAX_PATH_DEPTH}"
            )

        # File size check
        if entry.file_size > MAX_SINGLE_FILE_SIZE:
            errors.append(
                f"File too large: '{name}' ({entry.file_size} bytes), "
                f"maximum is {MAX_SINGLE_FILE_SIZE} bytes"
            )

        # Extension check
        ext = PurePosixPath(name).suffix.lower()
        if ext and ext not in ALLOWED_IMPORT_EXTENSIONS:
            errors.append(
                f"Disallowed file extension '{ext}' in '{name}'. "
                f"Allowed: {sorted(ALLOWED_IMPORT_EXTENSIONS)}"
            )

        # Directory whitelist check (for non-root files)
        if len(parts) > 1:
            top_dir = parts[0]
            if top_dir not in ALLOWED_DIRECTORIES:
                # Allow SKILL.md at root
                if name != "SKILL.md":
                    errors.append(
                        f"File '{name}' is in disallowed directory '{top_dir}'. "
                        f"Allowed directories: {sorted(ALLOWED_DIRECTORIES)}"
                    )

        total_uncompressed += entry.file_size

    # Zip bomb check (total uncompressed size)
    if total_uncompressed > MAX_UNCOMPRESSED_SIZE_BYTES:
        errors.append(
            f"Total uncompressed size ({total_uncompressed} bytes) exceeds maximum "
            f"of {MAX_UNCOMPRESSED_SIZE_BYTES} bytes (zip bomb protection)"
        )

    zf.close()
    return errors


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


async def export_skill_zip(db: AsyncSession, skill_id: str) -> bytes:
    """Export a Skill as a ZIP archive containing SKILL.md + resources.

    ZIP structure:
    - SKILL.md (YAML frontmatter + Markdown body)
    - references/<filename>
    - scripts/<filename>
    - assets/<filename>
    """
    # populate_existing ensures fresh load even if Skill is already in identity map
    result = await db.execute(
        select(Skill)
        .options(selectinload(Skill.resources), selectinload(Skill.versions))
        .where(Skill.id == skill_id)
        .execution_options(populate_existing=True)
    )
    skill = result.scalar_one_or_none()
    if skill is None:
        not_found("Skill not found")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        # Build SKILL.md with YAML frontmatter
        frontmatter = {
            "name": skill.name,
            "description": skill.description,
            "version": skill.current_version,
            "product": skill.product,
            "therapeutic_area": skill.therapeutic_area,
            "compatibility": skill.compatibility,
            "tags": skill.tags,
            "status": skill.status,
        }
        yaml_str = yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False)
        skill_md = f"---\n{yaml_str}---\n\n{skill.content or ''}"
        zf.writestr("SKILL.md", skill_md)

        # Bundle resources by type
        for resource in skill.resources:
            # Map resource_type to directory name (reference -> references/)
            dir_name = f"{resource.resource_type}s"
            file_path = f"{dir_name}/{resource.filename}"

            if resource.text_content:
                zf.writestr(file_path, resource.text_content)
            else:
                # Placeholder for binary resources
                zf.writestr(file_path, f"# {resource.filename}\n# Binary content not included")

    logger.info("Exported skill %s as ZIP (%d bytes)", skill_id, buf.tell())
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


async def import_skill_zip(db: AsyncSession, zip_bytes: bytes, created_by: str = "admin") -> Skill:
    """Import a Skill from a ZIP archive.

    Validates security, parses SKILL.md frontmatter, creates Skill + resources.
    Scripts are stored as inert text (never auto-executed).
    Rejects duplicate skill names.
    """
    # Security validation
    errors = validate_zip_security(zip_bytes)
    if errors:
        bad_request(f"ZIP security validation failed: {'; '.join(errors)}")

    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))

    # Find SKILL.md
    if "SKILL.md" not in zf.namelist():
        bad_request("ZIP must contain a SKILL.md file at root")

    skill_md_content = zf.read("SKILL.md").decode("utf-8")

    # Parse YAML frontmatter
    name, description, product, therapeutic_area, compatibility, tags, content = _parse_skill_md(
        skill_md_content
    )

    # Conflict check: reject duplicate names
    existing = await db.execute(select(Skill).where(Skill.name == name))
    if existing.scalar_one_or_none() is not None:
        raise ConflictException(
            f"A skill with name '{name}' already exists. "
            "Rename or delete the existing skill before importing."
        )

    # Create Skill
    skill_data = SkillCreate(
        name=name,
        description=description,
        product=product,
        therapeutic_area=therapeutic_area,
        compatibility=compatibility,
        tags=tags,
        content=content,
    )
    skill = await skill_service.create_skill(db, skill_data, created_by)

    # Import resources
    for entry in zf.infolist():
        fname = entry.filename
        if fname == "SKILL.md" or fname.endswith("/"):
            continue

        parts = PurePosixPath(fname).parts
        if len(parts) < 2:
            continue

        # Determine resource_type from directory
        top_dir = parts[0]
        resource_type_map = {
            "references": "reference",
            "scripts": "script",
            "assets": "asset",
        }
        resource_type = resource_type_map.get(top_dir)
        if resource_type is None:
            continue

        # Read content as text (UTF-8 with fallback)
        raw = zf.read(fname)
        try:
            text_content = raw.decode("utf-8")
        except UnicodeDecodeError:
            text_content = raw.decode("latin-1")

        filename = os.path.basename(fname)

        resource = SkillResource(
            skill_id=skill.id,
            resource_type=resource_type,
            filename=filename,
            storage_path=f"skills/{skill.id}/{top_dir}/{filename}",
            content_type="text/plain",
            file_size=len(raw),
            text_content=text_content,
        )
        db.add(resource)
        logger.info("Imported resource: %s (%s)", filename, resource_type)

    await db.flush()
    zf.close()

    # Re-query with relationships (populate_existing for fresh load)
    result = await db.execute(
        select(Skill)
        .options(selectinload(Skill.resources), selectinload(Skill.versions))
        .where(Skill.id == skill.id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


def parse_skill_frontmatter(content: str) -> tuple[dict, str]:
    """Parse SKILL.md content into (frontmatter metadata dict, markdown body).

    Shared by skill ZIP import (_parse_skill_md) and Foundry download-fallback
    consumption (skill_consumption_service.download_and_extract_skill_content) --
    do not introduce a second YAML-frontmatter parsing library (see Phase 28 BLOCKER-1).
    """
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            yaml_str, body = parts[1], parts[2].strip()
        else:
            yaml_str, body = "", content
    else:
        yaml_str, body = "", content
    meta = yaml.safe_load(yaml_str) or {} if yaml_str.strip() else {}
    return meta, body


def _parse_skill_md(content: str) -> tuple[str, str, str, str, str, str, str]:
    """Parse SKILL.md content: extract YAML frontmatter + Markdown body.

    Returns (name, description, product, therapeutic_area, compatibility, tags, markdown_body).
    """
    meta, body = parse_skill_frontmatter(content)
    return (
        meta.get("name", "Imported Skill"),
        meta.get("description", ""),
        meta.get("product", ""),
        meta.get("therapeutic_area", ""),
        meta.get("compatibility", ""),
        meta.get("tags", ""),
        body,
    )
