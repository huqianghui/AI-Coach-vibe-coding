"""Unit tests for the prompt registry: seed, idempotency, resolver, fallback, snapshots."""

import json

import pytest
from sqlalchemy import func, select

from app.models.prompt_template import PromptTemplate
from app.models.prompt_version import PromptVersion
from app.services.prompt_defaults import PROMPT_DEFAULTS, PROMPT_KEYS
from app.services.prompt_registry import (
    create_template,
    get_prompt,
    seed_prompt_registry,
    update_template_meta,
)
from app.services.scoring_engine import SCORING_PROMPT_TEMPLATE
from app.utils.exceptions import ConflictException, NotFoundException, ValidationException


@pytest.fixture
async def session(db_session):
    return db_session


async def test_seed_creates_all_nine_templates(session):
    created = await seed_prompt_registry(session)
    assert created == 9

    template_count = await session.scalar(select(func.count()).select_from(PromptTemplate))
    assert template_count == 9

    # Every template has exactly one active version_no=1
    for key in PROMPT_KEYS:
        template = (
            await session.execute(select(PromptTemplate).where(PromptTemplate.key == key))
        ).scalar_one()
        assert template.active_version_id is not None
        assert template.is_system is True

        versions = (
            (
                await session.execute(
                    select(PromptVersion).where(PromptVersion.template_id == template.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(versions) == 1
        assert versions[0].version_no == 1
        assert versions[0].source == "seed"
        assert versions[0].is_active is True
        assert versions[0].id == template.active_version_id


async def test_seed_is_idempotent(session):
    first = await seed_prompt_registry(session)
    assert first == 9
    second = await seed_prompt_registry(session)
    assert second == 0

    template_count = await session.scalar(select(func.count()).select_from(PromptTemplate))
    version_count = await session.scalar(select(func.count()).select_from(PromptVersion))
    assert template_count == 9
    assert version_count == 9


async def test_seed_stores_variables_as_json_list(session):
    await seed_prompt_registry(session)
    template = (
        await session.execute(select(PromptTemplate).where(PromptTemplate.key == "scoring.base"))
    ).scalar_one()
    variables = json.loads(template.variables)
    assert isinstance(variables, list)
    assert "transcript" in variables


async def test_get_prompt_returns_default_when_no_db_row(session):
    # No seeding performed: resolver falls back to PROMPT_DEFAULTS
    content = await get_prompt(session, "scoring.base")
    assert content == SCORING_PROMPT_TEMPLATE


async def test_get_prompt_returns_default_after_seed(session):
    await seed_prompt_registry(session)
    content = await get_prompt(session, "hcp.system")
    assert content == PROMPT_DEFAULTS["hcp.system"]["content"]


async def test_get_prompt_returns_active_override_version(session):
    await seed_prompt_registry(session)
    template = (
        await session.execute(select(PromptTemplate).where(PromptTemplate.key == "scoring.base"))
    ).scalar_one()

    # Deactivate the seed version, add an active override version 2
    seed_version = (
        await session.execute(
            select(PromptVersion).where(PromptVersion.id == template.active_version_id)
        )
    ).scalar_one()
    seed_version.is_active = False

    override = PromptVersion(
        template_id=template.id,
        version_no=2,
        content="OVERRIDDEN SCORING PROMPT",
        source="manual",
        is_active=True,
    )
    session.add(override)
    await session.flush()
    template.active_version_id = override.id
    await session.commit()

    content = await get_prompt(session, "scoring.base")
    assert content == "OVERRIDDEN SCORING PROMPT"


async def test_get_prompt_unknown_key_raises(session):
    with pytest.raises(KeyError):
        await get_prompt(session, "does.not.exist")


async def test_default_content_matches_original_hardcoded_strings(session):
    # scoring.base is a real module constant -- snapshot equality guards against drift.
    assert PROMPT_DEFAULTS["scoring.base"]["content"] == SCORING_PROMPT_TEMPLATE

    # hcp.system has no single source constant; assert its stable canonical skeleton.
    hcp_content = PROMPT_DEFAULTS["hcp.system"]["content"]
    assert hcp_content.startswith("# HCP Identity")
    assert "# Personality & Communication" in hcp_content

    # Round-trip: seeded content is byte-identical to the default catalog.
    await seed_prompt_registry(session)
    for key in PROMPT_KEYS:
        assert await get_prompt(session, key) == PROMPT_DEFAULTS[key]["content"]


# --- create_template --------------------------------------------------------


async def test_create_template_success(session):
    template, version = await create_template(
        session,
        key="custom.hello",
        name="Custom Hello",
        content="Hello {{name}}",
        category="general",
        description="a custom prompt",
        variables=["name"],
        created_by="admin-id",
    )
    assert template.key == "custom.hello"
    assert template.name == "Custom Hello"
    assert template.is_system is False
    assert template.active_version_id == version.id
    assert version.version_no == 1
    assert version.is_active is True
    assert version.source == "manual"
    assert json.loads(template.variables) == ["name"]
    # Resolver returns the new content.
    assert await get_prompt(session, "custom.hello") == "Hello {{name}}"


async def test_create_template_defaults_empty_variables(session):
    template, _ = await create_template(session, key="custom.min", name="Min", content="body")
    assert json.loads(template.variables) == []
    assert template.category == "general"


async def test_create_template_is_system_true(session):
    template, _ = await create_template(
        session,
        key="custom.sys",
        name="Sys",
        content="body",
        is_system=True,
    )
    assert template.is_system is True


async def test_create_template_duplicate_key_conflict(session):
    await seed_prompt_registry(session)
    with pytest.raises(ConflictException):
        await create_template(session, key="hcp.system", name="Dup", content="x")


@pytest.mark.parametrize("bad_key", ["", "   ", "Bad Key", "UPPER", ".leading", "has space"])
async def test_create_template_invalid_key_raises(session, bad_key):
    with pytest.raises(ValidationException):
        await create_template(session, key=bad_key, name="X", content="x")


async def test_create_template_strips_key_whitespace(session):
    template, _ = await create_template(session, key="  custom.trim  ", name="Trim", content="x")
    assert template.key == "custom.trim"


# --- update_template_meta ---------------------------------------------------


async def test_update_template_meta_updates_fields(session):
    await create_template(session, key="custom.up", name="Old", content="body")
    template, active = await update_template_meta(
        session,
        "custom.up",
        name="New",
        category="scoring",
        description="d",
        variables=["x"],
        is_system=True,
    )
    assert template.name == "New"
    assert template.category == "scoring"
    assert template.description == "d"
    assert json.loads(template.variables) == ["x"]
    assert template.is_system is True
    assert active is not None and active.content == "body"


async def test_update_template_meta_partial(session):
    await create_template(session, key="custom.up2", name="Keep", content="body", category="skill")
    template, _ = await update_template_meta(session, "custom.up2", description="only")
    assert template.name == "Keep"
    assert template.category == "skill"
    assert template.description == "only"


async def test_update_template_meta_unknown_key_raises(session):
    with pytest.raises(NotFoundException):
        await update_template_meta(session, "missing", name="X")
