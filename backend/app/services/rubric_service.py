"""Rubric CRUD service: manage scoring rubrics with dimension configurations."""

import json
import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scoring_rubric import ScoringRubric
from app.schemas.scoring_rubric import RubricCreate, RubricUpdate
from app.services.cu_evaluation_service import sync_rubric_analyzers
from app.utils.exceptions import NotFoundException

logger = logging.getLogger(__name__)


async def create_rubric(db: AsyncSession, data: RubricCreate, user_id: str) -> ScoringRubric:
    """Create a new scoring rubric with JSON-serialized dimensions.

    If is_default=True, unsets other defaults for the same scenario_type first.
    """
    if data.is_default:
        await _unset_defaults(db, data.scenario_type)

    rubric = ScoringRubric(
        name=data.name,
        description=data.description,
        scenario_type=data.scenario_type,
        dimensions=json.dumps([d.model_dump() for d in data.dimensions]),
        is_default=data.is_default,
        created_by=user_id,
    )
    db.add(rubric)
    await db.flush()

    # D-09: Pre-create CU analyzers for this rubric
    try:
        await sync_rubric_analyzers(db, rubric)
    except Exception as e:
        logger.warning("CU analyzer sync failed on create (non-blocking): %s", e)

    return rubric


async def get_rubric(db: AsyncSession, rubric_id: str) -> ScoringRubric:
    """Fetch a rubric by ID. Raises NotFoundException if not found."""
    result = await db.execute(select(ScoringRubric).where(ScoringRubric.id == rubric_id))
    rubric = result.scalar_one_or_none()
    if rubric is None:
        raise NotFoundException("Rubric not found")
    return rubric


async def list_rubrics(db: AsyncSession, scenario_type: str | None = None) -> list[ScoringRubric]:
    """List all rubrics, optionally filtered by scenario_type."""
    query = select(ScoringRubric)
    if scenario_type is not None:
        query = query.where(ScoringRubric.scenario_type == scenario_type)
    result = await db.execute(query)
    return list(result.scalars().all())


async def update_rubric(db: AsyncSession, rubric_id: str, data: RubricUpdate) -> ScoringRubric:
    """Update rubric fields. Only non-None fields are modified.

    If dimensions are provided, they are re-serialized to JSON.
    If is_default is set to True, unsets other defaults for the same scenario_type.
    """
    rubric = await get_rubric(db, rubric_id)

    if data.name is not None:
        rubric.name = data.name
    if data.description is not None:
        rubric.description = data.description
    if data.scenario_type is not None:
        rubric.scenario_type = data.scenario_type
    if data.dimensions is not None:
        rubric.dimensions = json.dumps([d.model_dump() for d in data.dimensions])
    if data.is_default is not None:
        if data.is_default:
            await _unset_defaults(db, rubric.scenario_type)
        rubric.is_default = data.is_default

    await db.flush()
    await db.refresh(rubric)

    # D-09: Update CU analyzers when rubric changes
    try:
        await sync_rubric_analyzers(db, rubric)
    except Exception as e:
        logger.warning("CU analyzer sync failed on update (non-blocking): %s", e)

    return rubric


async def delete_rubric(db: AsyncSession, rubric_id: str) -> None:
    """Delete a rubric by ID. Raises NotFoundException if not found."""
    rubric = await get_rubric(db, rubric_id)
    await db.delete(rubric)
    await db.flush()


async def get_default_rubric(db: AsyncSession, scenario_type: str) -> ScoringRubric | None:
    """Return the default rubric for a given scenario_type, or None."""
    result = await db.execute(
        select(ScoringRubric).where(
            ScoringRubric.is_default == True,  # noqa: E712
            ScoringRubric.scenario_type == scenario_type,
        )
    )
    return result.scalar_one_or_none()


async def _unset_defaults(db: AsyncSession, scenario_type: str) -> None:
    """Unset is_default for all rubrics with the given scenario_type."""
    await db.execute(
        update(ScoringRubric)
        .where(
            ScoringRubric.scenario_type == scenario_type,
            ScoringRubric.is_default == True,  # noqa: E712
        )
        .values(is_default=False)
    )
