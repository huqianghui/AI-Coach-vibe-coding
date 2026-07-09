"""Prompt management + optimization API.

Two surfaces share the ``/prompts`` prefix:

* Stateless optimization: ``POST /prompts/optimize`` returns optimized text without
  touching the database (ad-hoc use).
* Management (registry-backed): list/detail, versioned edits, version history,
  activation/rollback, optimization-run recording, and adopt-run-as-new-version.

All write endpoints require the ``admin`` role. Static paths are declared before the
parameterized ``/{key}`` routes so ``/optimize`` stays reachable.
"""

import json

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_role
from app.models.prompt_version import PromptVersion
from app.models.user import User
from app.schemas.prompt import (
    AdoptRunRequest,
    OptimizeRecordRequest,
    OptimizeRunResponse,
    PromptCreateRequest,
    PromptMetaUpdateRequest,
    PromptOptimizationRunResponse,
    PromptResponse,
    PromptSummary,
    PromptUpdateRequest,
    PromptVersionResponse,
)
from app.services import prompt_registry
from app.services.prompt_optimizer_client import PromptOptimizerError, optimize_prompt
from app.utils.exceptions import AppException, bad_request

router = APIRouter(prefix="/prompts", tags=["prompts"])

_VALID_MODES = {"system", "user", "iterate"}
_OPTIMIZER_MODEL = "prompt-optimizer"


class OptimizeRequest(BaseModel):
    prompt: str
    mode: str = "system"
    requirements: str | None = None
    template: str | None = None


class OptimizeResponse(BaseModel):
    optimized_prompt: str


def _validate_mode(mode: str, requirements: str | None) -> None:
    if mode not in _VALID_MODES:
        bad_request(f"Invalid mode: {mode}")
    if mode == "iterate" and not requirements:
        bad_request("mode=iterate requires requirements")


def _version_response(version: PromptVersion) -> PromptVersionResponse:
    return PromptVersionResponse.model_validate(version)


# --- Stateless optimization (no persistence) --------------------------------


@router.post("/optimize", response_model=OptimizeResponse)
async def optimize(
    data: OptimizeRequest,
    _user: User = Depends(require_role("admin")),
) -> OptimizeResponse:
    """Return an optimized prompt without persisting anything. Admin only."""
    _validate_mode(data.mode, data.requirements)

    try:
        optimized = await optimize_prompt(
            data.prompt,
            mode=data.mode,
            requirements=data.requirements,
            template=data.template,
        )
    except PromptOptimizerError as exc:
        raise AppException(
            status_code=502,
            code="PROMPT_OPTIMIZER_ERROR",
            message=str(exc),
        ) from exc

    return OptimizeResponse(optimized_prompt=optimized)


# --- Read endpoints ---------------------------------------------------------


@router.get("", response_model=list[PromptSummary])
async def list_prompts(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
) -> list[PromptSummary]:
    """List every registered prompt with its active version + last optimization time."""
    summaries = await prompt_registry.list_prompt_summaries(db)
    return [PromptSummary(**row) for row in summaries]


@router.get("/{key}", response_model=PromptResponse)
async def get_prompt_detail(
    key: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
) -> PromptResponse:
    """Return a prompt template with its active version content and variables."""
    template, active = await prompt_registry.get_prompt_detail(db, key)
    return PromptResponse(
        key=template.key,
        name=template.name,
        category=template.category,
        description=template.description or "",
        is_system=template.is_system,
        variables=json.loads(template.variables or "[]"),
        active_version=_version_response(active) if active else None,
    )


@router.get("/{key}/versions", response_model=list[PromptVersionResponse])
async def get_prompt_versions(
    key: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
) -> list[PromptVersionResponse]:
    """Return the version chain for a prompt, newest first."""
    versions = await prompt_registry.list_versions(db, key)
    return [_version_response(v) for v in versions]


@router.get("/{key}/runs", response_model=list[PromptOptimizationRunResponse])
async def get_prompt_runs(
    key: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
) -> list[PromptOptimizationRunResponse]:
    """Return optimization runs for a prompt, newest first."""
    runs = await prompt_registry.list_runs(db, key)
    return [PromptOptimizationRunResponse.model_validate(r) for r in runs]


# --- Write endpoints (versioning, activation, optimize-record, adopt) -------


@router.post("", response_model=PromptResponse, status_code=201)
async def create_prompt(
    data: PromptCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
) -> PromptResponse:
    """Create a new non-system prompt with an active version 1. Admin only."""
    template, version = await prompt_registry.create_template(
        db,
        key=data.key,
        name=data.name,
        content=data.content,
        category=data.category,
        description=data.description,
        variables=data.variables,
        is_system=data.is_system,
        created_by=user.id,
    )
    return PromptResponse(
        key=template.key,
        name=template.name,
        category=template.category,
        description=template.description or "",
        is_system=template.is_system,
        variables=data.variables,
        active_version=_version_response(version),
    )


@router.put("/{key}", response_model=PromptVersionResponse, status_code=201)
async def update_prompt(
    key: str,
    data: PromptUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
) -> PromptVersionResponse:
    """Save an edit as a new manual version and activate it."""
    version = await prompt_registry.create_version(
        db, key, content=data.content, note=data.note, created_by=user.id, source="manual"
    )
    return _version_response(version)


@router.patch("/{key}", response_model=PromptResponse)
async def update_prompt_meta(
    key: str,
    data: PromptMetaUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
) -> PromptResponse:
    """Update a prompt's editable metadata (name/category/description/variables). Admin only."""
    template, active = await prompt_registry.update_template_meta(
        db,
        key,
        name=data.name,
        category=data.category,
        description=data.description,
        variables=data.variables,
        is_system=data.is_system,
    )
    return PromptResponse(
        key=template.key,
        name=template.name,
        category=template.category,
        description=template.description or "",
        is_system=template.is_system,
        variables=json.loads(template.variables or "[]"),
        active_version=_version_response(active) if active else None,
    )


@router.post("/{key}/activate/{version_no}", response_model=PromptVersionResponse)
async def activate_prompt_version(
    key: str,
    version_no: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
) -> PromptVersionResponse:
    """Switch the active version (rollback). History is preserved."""
    version = await prompt_registry.activate_version(db, key, version_no)
    return _version_response(version)


@router.post("/{key}/optimize", response_model=OptimizeRunResponse)
async def optimize_and_record(
    key: str,
    data: OptimizeRecordRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
) -> OptimizeRunResponse:
    """Optimize the active version and record a PromptOptimizationRun. No activation."""
    _validate_mode(data.mode, data.requirements)
    # 404 guard for unknown key, then resolve the current active content.
    await prompt_registry.get_prompt_detail(db, key)
    current = await prompt_registry.get_prompt(db, key)

    try:
        optimized = await optimize_prompt(
            current,
            mode=data.mode,
            requirements=data.requirements,
            template=data.template,
        )
    except PromptOptimizerError as exc:
        await prompt_registry.record_optimization_run(
            db,
            key,
            mode=data.mode,
            result_content="",
            model=_OPTIMIZER_MODEL,
            requirements=data.requirements,
            optimizer_template=data.template,
            status="error",
            error_message=str(exc),
            created_by=user.id,
        )
        raise AppException(
            status_code=502,
            code="PROMPT_OPTIMIZER_ERROR",
            message=str(exc),
        ) from exc

    run = await prompt_registry.record_optimization_run(
        db,
        key,
        mode=data.mode,
        result_content=optimized,
        model=_OPTIMIZER_MODEL,
        requirements=data.requirements,
        optimizer_template=data.template,
        status="success",
        created_by=user.id,
    )
    return OptimizeRunResponse(run_id=run.id, optimized_prompt=optimized)


@router.post("/{key}/adopt", response_model=PromptVersionResponse, status_code=201)
async def adopt_optimization_run(
    key: str,
    data: AdoptRunRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
) -> PromptVersionResponse:
    """Adopt a run's result as a new active version linked back to the run."""
    version = await prompt_registry.adopt_run(
        db, key, run_id=data.run_id, note=data.note, created_by=user.id
    )
    return _version_response(version)


@router.delete("/{key}", status_code=204)
async def delete_prompt(
    key: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
) -> Response:
    """Delete a non-system prompt. System prompts are protected (409)."""
    await prompt_registry.delete_template(db, key)
    return Response(status_code=204)
