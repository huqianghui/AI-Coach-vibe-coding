"""Prompt registry resolver + idempotent seed.

``get_prompt`` returns the active DB version content for a key, falling back to the
seeded default from :mod:`app.services.prompt_defaults`. ``seed_prompt_registry``
registers every default key as version 1 exactly once.
"""

import json
import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt_optimization_run import PromptOptimizationRun
from app.models.prompt_template import PromptTemplate
from app.models.prompt_version import PromptVersion
from app.services.prompt_defaults import PROMPT_DEFAULTS
from app.utils.exceptions import ConflictException, NotFoundException, ValidationException

__all__ = [
    "get_prompt",
    "seed_prompt_registry",
    "list_prompt_summaries",
    "get_prompt_detail",
    "list_versions",
    "list_runs",
    "create_template",
    "update_template_meta",
    "create_version",
    "activate_version",
    "record_optimization_run",
    "adopt_run",
    "delete_template",
]

_KEY_PATTERN = re.compile(r"[a-z0-9][a-z0-9_.-]*")


async def get_prompt(db: AsyncSession, key: str) -> str:
    """Return the active version content for ``key``, else the seeded default.

    Raises ``KeyError`` if the key is neither registered nor a known default.
    """
    result = await db.execute(select(PromptTemplate).where(PromptTemplate.key == key))
    template = result.scalar_one_or_none()
    if template is not None and template.active_version_id:
        version_result = await db.execute(
            select(PromptVersion).where(PromptVersion.id == template.active_version_id)
        )
        version = version_result.scalar_one_or_none()
        if version is not None:
            return version.content

    default = PROMPT_DEFAULTS.get(key)
    if default is None:
        raise KeyError(f"Unknown prompt key: {key}")
    return default["content"]


async def seed_prompt_registry(db: AsyncSession) -> int:
    """Idempotently register every default prompt as version 1.

    Creates a :class:`PromptTemplate` plus an active version 1 (``source=seed``) for
    any key not already present. Never modifies existing templates. Returns the number
    of newly created templates.
    """
    created = 0
    for key, spec in PROMPT_DEFAULTS.items():
        existing = await db.execute(select(PromptTemplate).where(PromptTemplate.key == key))
        if existing.scalar_one_or_none() is not None:
            continue

        template = PromptTemplate(
            key=key,
            name=spec.get("name", key),
            category=spec.get("category", "general"),
            description=spec.get("description", ""),
            variables=json.dumps(spec.get("variables", [])),
            is_system=True,
        )
        db.add(template)
        await db.flush()

        version = PromptVersion(
            template_id=template.id,
            version_no=1,
            content=spec["content"],
            source="seed",
            is_active=True,
            created_by=None,
        )
        db.add(version)
        await db.flush()

        template.active_version_id = version.id
        created += 1

    if created:
        await db.commit()
    return created


async def _get_template_or_404(db: AsyncSession, key: str) -> PromptTemplate:
    """Return the :class:`PromptTemplate` for ``key`` or raise ``NotFoundException``."""
    result = await db.execute(select(PromptTemplate).where(PromptTemplate.key == key))
    template = result.scalar_one_or_none()
    if template is None:
        raise NotFoundException(f"Unknown prompt key: {key}")
    return template


async def _deactivate_all_versions(db: AsyncSession, template_id: str) -> None:
    """Clear the active flag on every version of a template (single-active invariant)."""
    active = (
        (
            await db.execute(
                select(PromptVersion).where(
                    PromptVersion.template_id == template_id,
                    PromptVersion.is_active.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    for version in active:
        version.is_active = False


async def _active_version(db: AsyncSession, template: PromptTemplate) -> PromptVersion | None:
    """Return the active :class:`PromptVersion` for a template, if any."""
    if not template.active_version_id:
        return None
    result = await db.execute(
        select(PromptVersion).where(PromptVersion.id == template.active_version_id)
    )
    return result.scalar_one_or_none()


async def list_prompt_summaries(db: AsyncSession) -> list[dict]:
    """Return one summary row per registered prompt (active version_no + last run time)."""
    templates = (
        (await db.execute(select(PromptTemplate).order_by(PromptTemplate.key))).scalars().all()
    )
    summaries: list[dict] = []
    for template in templates:
        active = await _active_version(db, template)
        last_optimized_at = await db.scalar(
            select(func.max(PromptOptimizationRun.created_at)).where(
                PromptOptimizationRun.template_id == template.id
            )
        )
        summaries.append(
            {
                "key": template.key,
                "name": template.name,
                "category": template.category,
                "is_system": template.is_system,
                "active_version_no": active.version_no if active else None,
                "updated_at": template.updated_at,
                "last_optimized_at": last_optimized_at,
            }
        )
    return summaries


async def get_prompt_detail(
    db: AsyncSession, key: str
) -> tuple[PromptTemplate, PromptVersion | None]:
    """Return the template and its active version, raising 404 for an unknown key."""
    template = await _get_template_or_404(db, key)
    active = await _active_version(db, template)
    return template, active


async def list_versions(db: AsyncSession, key: str) -> list[PromptVersion]:
    """Return the version chain for a prompt, newest first."""
    template = await _get_template_or_404(db, key)
    result = await db.execute(
        select(PromptVersion)
        .where(PromptVersion.template_id == template.id)
        .order_by(PromptVersion.version_no.desc())
    )
    return list(result.scalars().all())


async def list_runs(db: AsyncSession, key: str) -> list[PromptOptimizationRun]:
    """Return optimization runs for a prompt, newest first."""
    template = await _get_template_or_404(db, key)
    result = await db.execute(
        select(PromptOptimizationRun)
        .where(PromptOptimizationRun.template_id == template.id)
        .order_by(PromptOptimizationRun.created_at.desc(), PromptOptimizationRun.id.desc())
    )
    return list(result.scalars().all())


async def create_template(
    db: AsyncSession,
    key: str,
    name: str,
    content: str,
    category: str = "general",
    description: str = "",
    variables: list[str] | None = None,
    is_system: bool = False,
    created_by: str | None = None,
) -> tuple[PromptTemplate, PromptVersion]:
    """Register a new prompt with an active version 1.

    Raises ``ValidationException`` for an invalid key and ``ConflictException`` if the key
    already exists. Non-system templates (``is_system=False``) can later be deleted.
    """
    key = (key or "").strip()
    if not _KEY_PATTERN.fullmatch(key):
        raise ValidationException(
            "Invalid prompt key: use lowercase letters, digits, '.', '_' or '-'"
        )

    existing = await db.execute(select(PromptTemplate).where(PromptTemplate.key == key))
    if existing.scalar_one_or_none() is not None:
        raise ConflictException(f"Prompt key already exists: {key}")

    template = PromptTemplate(
        key=key,
        name=name,
        category=category or "general",
        description=description or "",
        variables=json.dumps(variables or []),
        is_system=is_system,
    )
    db.add(template)
    await db.flush()

    version = PromptVersion(
        template_id=template.id,
        version_no=1,
        content=content,
        source="manual",
        is_active=True,
        created_by=created_by,
    )
    db.add(version)
    await db.flush()

    template.active_version_id = version.id
    await db.commit()
    await db.refresh(template)
    await db.refresh(version)
    return template, version


async def update_template_meta(
    db: AsyncSession,
    key: str,
    *,
    name: str | None = None,
    category: str | None = None,
    description: str | None = None,
    variables: list[str] | None = None,
    is_system: bool | None = None,
) -> tuple[PromptTemplate, PromptVersion | None]:
    """Update editable metadata of a prompt template (not its version content).

    Only provided (non-``None``) fields are changed. Returns the template and its active
    version. Raises ``NotFoundException`` for an unknown key.
    """
    template = await _get_template_or_404(db, key)
    if name is not None:
        template.name = name
    if category is not None:
        template.category = category or "general"
    if description is not None:
        template.description = description
    if variables is not None:
        template.variables = json.dumps(variables)
    if is_system is not None:
        template.is_system = is_system
    await db.commit()
    await db.refresh(template)
    active = await _active_version(db, template)
    return template, active


async def create_version(
    db: AsyncSession,
    key: str,
    content: str,
    note: str = "",
    created_by: str | None = None,
    source: str = "manual",
) -> PromptVersion:
    """Append a new version (parent = current active) and make it the active one."""
    template = await _get_template_or_404(db, key)
    max_no = (
        await db.scalar(
            select(func.max(PromptVersion.version_no)).where(
                PromptVersion.template_id == template.id
            )
        )
    ) or 0

    await _deactivate_all_versions(db, template.id)
    version = PromptVersion(
        template_id=template.id,
        version_no=max_no + 1,
        content=content,
        source=source,
        parent_version_id=template.active_version_id,
        note=note,
        created_by=created_by,
        is_active=True,
    )
    db.add(version)
    await db.flush()
    template.active_version_id = version.id
    await db.commit()
    await db.refresh(version)
    return version


async def activate_version(db: AsyncSession, key: str, version_no: int) -> PromptVersion:
    """Switch the active version to ``version_no`` (rollback) without deleting history."""
    template = await _get_template_or_404(db, key)
    result = await db.execute(
        select(PromptVersion).where(
            PromptVersion.template_id == template.id,
            PromptVersion.version_no == version_no,
        )
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise NotFoundException(f"Version {version_no} not found for prompt {key}")

    await _deactivate_all_versions(db, template.id)
    version.is_active = True
    template.active_version_id = version.id
    await db.commit()
    await db.refresh(version)
    return version


async def record_optimization_run(
    db: AsyncSession,
    key: str,
    mode: str,
    result_content: str,
    model: str = "",
    requirements: str | None = None,
    optimizer_template: str | None = None,
    status: str = "success",
    error_message: str | None = None,
    created_by: str | None = None,
) -> PromptOptimizationRun:
    """Persist one optimizer invocation (base = current active version). No activation."""
    template = await _get_template_or_404(db, key)
    run = PromptOptimizationRun(
        template_id=template.id,
        base_version_id=template.active_version_id,
        mode=mode,
        optimizer_template=optimizer_template,
        requirements=requirements,
        result_content=result_content,
        model=model,
        status=status,
        error_message=error_message,
        created_by=created_by,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


async def adopt_run(
    db: AsyncSession,
    key: str,
    run_id: str,
    note: str = "",
    created_by: str | None = None,
) -> PromptVersion:
    """Create a new active version from a run's result and link it back to the run."""
    template = await _get_template_or_404(db, key)
    result = await db.execute(
        select(PromptOptimizationRun).where(
            PromptOptimizationRun.id == run_id,
            PromptOptimizationRun.template_id == template.id,
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise NotFoundException(f"Optimization run not found: {run_id}")

    source = "iterate" if run.mode == "iterate" else "optimized"
    version = await create_version(
        db, key, content=run.result_content, note=note, created_by=created_by, source=source
    )
    run.resulting_version_id = version.id
    await db.commit()
    await db.refresh(version)
    return version


async def delete_template(db: AsyncSession, key: str) -> None:
    """Delete a non-system prompt and its history. System prompts are protected (409)."""
    template = await _get_template_or_404(db, key)
    if template.is_system:
        raise ConflictException("System prompts cannot be deleted")

    for model in (PromptVersion, PromptOptimizationRun):
        rows = (
            (await db.execute(select(model).where(model.template_id == template.id)))
            .scalars()
            .all()
        )
        for row in rows:
            await db.delete(row)
    await db.delete(template)
    await db.commit()
