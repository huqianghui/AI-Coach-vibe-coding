"""Unit tests for the prompt management API (list/detail/versions/runs + writes).

Router coroutines are called directly with a mocked admin user and the real test
``db_session`` so coverage tracks every branch. ``optimize_prompt`` is mocked — no live
sidecar. Targets 100% coverage of app.api.prompts, app.services.prompt_registry, and
app.schemas.prompt.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.prompts import (
    OptimizeRecordRequest,
    activate_prompt_version,
    adopt_optimization_run,
    create_prompt,
    delete_prompt,
    get_prompt_detail,
    get_prompt_runs,
    get_prompt_versions,
    list_prompts,
    optimize_and_record,
    update_prompt,
    update_prompt_meta,
)
from app.models.prompt_template import PromptTemplate
from app.models.prompt_version import PromptVersion
from app.models.user import User
from app.schemas.prompt import (
    AdoptRunRequest,
    PromptCreateRequest,
    PromptMetaUpdateRequest,
    PromptUpdateRequest,
)
from app.services.prompt_optimizer_client import PromptOptimizerError
from app.services.prompt_registry import get_prompt, seed_prompt_registry
from app.utils.exceptions import (
    AppException,
    ConflictException,
    NotFoundException,
    ValidationException,
)

KEY = "hcp.system"


def _admin() -> User:
    user = MagicMock(spec=User)
    user.id = "admin-user-id"
    user.role = "admin"
    return user


async def _add_custom_template(db, key: str = "custom.temp") -> PromptTemplate:
    """Insert a non-system template with one active version for delete tests."""
    template = PromptTemplate(
        key=key,
        name="Custom",
        category="general",
        description="",
        variables="[]",
        is_system=False,
    )
    db.add(template)
    await db.flush()
    version = PromptVersion(
        template_id=template.id,
        version_no=1,
        content="custom body",
        source="manual",
        is_active=True,
    )
    db.add(version)
    await db.flush()
    template.active_version_id = version.id
    await db.commit()
    return template


# --- Read endpoints ---------------------------------------------------------


async def test_list_prompts_returns_seeded_rows(db_session):
    await seed_prompt_registry(db_session)
    rows = await list_prompts(db=db_session, _user=_admin())
    assert len(rows) >= 1
    row = next(r for r in rows if r.key == KEY)
    assert row.active_version_no == 1
    assert row.is_system is True
    assert row.last_optimized_at is None


async def test_get_prompt_detail_returns_active_version(db_session):
    await seed_prompt_registry(db_session)
    detail = await get_prompt_detail(KEY, db=db_session, _user=_admin())
    assert detail.key == KEY
    assert detail.active_version is not None
    assert detail.active_version.version_no == 1
    assert detail.active_version.content


async def test_get_prompt_detail_unknown_key_404(db_session):
    await seed_prompt_registry(db_session)
    with pytest.raises(NotFoundException):
        await get_prompt_detail("does.not.exist", db=db_session, _user=_admin())


async def test_get_prompt_versions_newest_first(db_session):
    await seed_prompt_registry(db_session)
    await update_prompt(KEY, PromptUpdateRequest(content="v2"), db=db_session, user=_admin())
    versions = await get_prompt_versions(KEY, db=db_session, _user=_admin())
    assert [v.version_no for v in versions] == [2, 1]


async def test_get_prompt_versions_unknown_key_404(db_session):
    await seed_prompt_registry(db_session)
    with pytest.raises(NotFoundException):
        await get_prompt_versions("nope", db=db_session, _user=_admin())


async def test_get_prompt_runs_empty_then_populated(db_session):
    await seed_prompt_registry(db_session)
    assert await get_prompt_runs(KEY, db=db_session, _user=_admin()) == []

    data = OptimizeRecordRequest(mode="system")
    with patch("app.api.prompts.optimize_prompt", new=AsyncMock(return_value="OPT")):
        await optimize_and_record(KEY, data, db=db_session, user=_admin())

    runs = await get_prompt_runs(KEY, db=db_session, _user=_admin())
    assert len(runs) == 1
    assert runs[0].result_content == "OPT"
    assert runs[0].model == "prompt-optimizer"


async def test_get_prompt_runs_unknown_key_404(db_session):
    await seed_prompt_registry(db_session)
    with pytest.raises(NotFoundException):
        await get_prompt_runs("nope", db=db_session, _user=_admin())


# --- Create -----------------------------------------------------------------


async def test_create_prompt_returns_201_detail(db_session):
    detail = await create_prompt(
        PromptCreateRequest(
            key="custom.api",
            name="Custom API",
            content="Body {{x}}",
            category="general",
            description="desc",
            variables=["x"],
        ),
        db=db_session,
        user=_admin(),
    )
    assert detail.key == "custom.api"
    assert detail.is_system is False
    assert detail.variables == ["x"]
    assert detail.active_version is not None
    assert detail.active_version.version_no == 1
    assert detail.active_version.content == "Body {{x}}"
    # Resolvable and listed.
    assert await get_prompt(db_session, "custom.api") == "Body {{x}}"
    rows = await list_prompts(db=db_session, _user=_admin())
    assert any(r.key == "custom.api" for r in rows)


async def test_create_prompt_is_system_true(db_session):
    detail = await create_prompt(
        PromptCreateRequest(
            key="custom.sys",
            name="Sys",
            content="body",
            is_system=True,
        ),
        db=db_session,
        user=_admin(),
    )
    assert detail.is_system is True


async def test_create_prompt_duplicate_key_conflict(db_session):
    await seed_prompt_registry(db_session)
    with pytest.raises(ConflictException):
        await create_prompt(
            PromptCreateRequest(key=KEY, name="Dup", content="x"),
            db=db_session,
            user=_admin(),
        )


async def test_create_prompt_invalid_key_raises(db_session):
    with pytest.raises(ValidationException):
        await create_prompt(
            PromptCreateRequest(key="Bad Key", name="X", content="x"),
            db=db_session,
            user=_admin(),
        )


async def test_update_prompt_meta_updates_fields(db_session):
    await create_prompt(
        PromptCreateRequest(key="custom.meta", name="Old", content="body"),
        db=db_session,
        user=_admin(),
    )
    detail = await update_prompt_meta(
        "custom.meta",
        PromptMetaUpdateRequest(
            name="New Name",
            category="skill",
            description="updated",
            variables=["a", "b"],
            is_system=True,
        ),
        db=db_session,
        _user=_admin(),
    )
    assert detail.name == "New Name"
    assert detail.category == "skill"
    assert detail.description == "updated"
    assert detail.variables == ["a", "b"]
    assert detail.is_system is True
    # Content version is untouched.
    assert detail.active_version is not None
    assert detail.active_version.content == "body"


async def test_update_prompt_meta_partial_keeps_other_fields(db_session):
    await create_prompt(
        PromptCreateRequest(key="custom.partial", name="Keep", content="body", category="skill"),
        db=db_session,
        user=_admin(),
    )
    detail = await update_prompt_meta(
        "custom.partial",
        PromptMetaUpdateRequest(description="only desc"),
        db=db_session,
        _user=_admin(),
    )
    assert detail.name == "Keep"
    assert detail.category == "skill"
    assert detail.description == "only desc"


async def test_update_prompt_meta_unknown_key_404(db_session):
    with pytest.raises(NotFoundException):
        await update_prompt_meta(
            "nope",
            PromptMetaUpdateRequest(name="X"),
            db=db_session,
            _user=_admin(),
        )


async def test_created_prompt_is_deletable(db_session):
    await create_prompt(
        PromptCreateRequest(key="custom.del", name="Del", content="x"),
        db=db_session,
        user=_admin(),
    )
    response = await delete_prompt("custom.del", db=db_session, _user=_admin())
    assert response.status_code == 204


# --- Update / activate ------------------------------------------------------


async def test_update_prompt_creates_and_activates_new_version(db_session):
    await seed_prompt_registry(db_session)
    version = await update_prompt(
        KEY, PromptUpdateRequest(content="edited", note="tweak"), db=db_session, user=_admin()
    )
    assert version.version_no == 2
    assert version.source == "manual"
    assert version.is_active is True
    assert version.note == "tweak"
    assert version.created_by == "admin-user-id"
    # New content is now what get_prompt resolves.
    assert await get_prompt(db_session, KEY) == "edited"


async def test_activate_version_rolls_back(db_session):
    await seed_prompt_registry(db_session)
    await update_prompt(KEY, PromptUpdateRequest(content="v2"), db=db_session, user=_admin())
    assert await get_prompt(db_session, KEY) == "v2"

    rolled = await activate_prompt_version(KEY, 1, db=db_session, _user=_admin())
    assert rolled.version_no == 1
    assert rolled.is_active is True
    # History preserved: version 2 still exists.
    versions = await get_prompt_versions(KEY, db=db_session, _user=_admin())
    assert {v.version_no for v in versions} == {1, 2}


async def test_activate_unknown_version_404(db_session):
    await seed_prompt_registry(db_session)
    with pytest.raises(NotFoundException):
        await activate_prompt_version(KEY, 99, db=db_session, _user=_admin())


# --- Optimize + record ------------------------------------------------------


async def test_optimize_records_run_without_activating(db_session):
    await seed_prompt_registry(db_session)
    original = await get_prompt(db_session, KEY)
    data = OptimizeRecordRequest(mode="system")
    with patch("app.api.prompts.optimize_prompt", new=AsyncMock(return_value="BETTER")):
        result = await optimize_and_record(KEY, data, db=db_session, user=_admin())

    assert result.optimized_prompt == "BETTER"
    assert result.run_id
    # Active version is unchanged by an optimize call.
    assert await get_prompt(db_session, KEY) == original


async def test_optimize_iterate_forwards_requirements(db_session):
    await seed_prompt_registry(db_session)
    data = OptimizeRecordRequest(mode="iterate", requirements="be concise")
    with patch("app.api.prompts.optimize_prompt", new=AsyncMock(return_value="X")) as mock_opt:
        await optimize_and_record(KEY, data, db=db_session, user=_admin())
    assert mock_opt.await_args.kwargs["requirements"] == "be concise"


async def test_optimize_invalid_mode_raises(db_session):
    await seed_prompt_registry(db_session)
    with pytest.raises(ValidationException):
        await optimize_and_record(
            KEY, OptimizeRecordRequest(mode="bogus"), db=db_session, user=_admin()
        )


async def test_optimize_iterate_without_requirements_raises(db_session):
    await seed_prompt_registry(db_session)
    with pytest.raises(ValidationException):
        await optimize_and_record(
            KEY, OptimizeRecordRequest(mode="iterate"), db=db_session, user=_admin()
        )


async def test_optimize_unknown_key_404(db_session):
    await seed_prompt_registry(db_session)
    with pytest.raises(NotFoundException):
        await optimize_and_record(
            "nope", OptimizeRecordRequest(mode="system"), db=db_session, user=_admin()
        )


async def test_optimize_error_records_failed_run_and_raises_502(db_session):
    await seed_prompt_registry(db_session)
    data = OptimizeRecordRequest(mode="system")
    with patch(
        "app.api.prompts.optimize_prompt",
        new=AsyncMock(side_effect=PromptOptimizerError("down")),
    ):
        with pytest.raises(AppException) as exc:
            await optimize_and_record(KEY, data, db=db_session, user=_admin())
    assert exc.value.status_code == 502

    runs = await get_prompt_runs(KEY, db=db_session, _user=_admin())
    assert len(runs) == 1
    assert runs[0].status == "error"
    assert runs[0].error_message == "down"


# --- Adopt ------------------------------------------------------------------


async def test_adopt_run_creates_linked_version(db_session):
    await seed_prompt_registry(db_session)
    with patch("app.api.prompts.optimize_prompt", new=AsyncMock(return_value="ADOPTED")):
        run_result = await optimize_and_record(
            KEY, OptimizeRecordRequest(mode="system"), db=db_session, user=_admin()
        )

    version = await adopt_optimization_run(
        KEY, AdoptRunRequest(run_id=run_result.run_id, note="ship"), db=db_session, user=_admin()
    )
    assert version.source == "optimized"
    assert version.content == "ADOPTED"
    assert version.is_active is True

    runs = await get_prompt_runs(KEY, db=db_session, _user=_admin())
    assert runs[0].resulting_version_id == version.id


async def test_adopt_iterate_run_uses_iterate_source(db_session):
    await seed_prompt_registry(db_session)
    with patch("app.api.prompts.optimize_prompt", new=AsyncMock(return_value="ITER")):
        run_result = await optimize_and_record(
            KEY,
            OptimizeRecordRequest(mode="iterate", requirements="x"),
            db=db_session,
            user=_admin(),
        )
    version = await adopt_optimization_run(
        KEY, AdoptRunRequest(run_id=run_result.run_id), db=db_session, user=_admin()
    )
    assert version.source == "iterate"


async def test_adopt_unknown_run_404(db_session):
    await seed_prompt_registry(db_session)
    with pytest.raises(NotFoundException):
        await adopt_optimization_run(
            KEY, AdoptRunRequest(run_id="missing"), db=db_session, user=_admin()
        )


# --- Delete -----------------------------------------------------------------


async def test_delete_system_prompt_conflict(db_session):
    await seed_prompt_registry(db_session)
    with pytest.raises(ConflictException):
        await delete_prompt(KEY, db=db_session, _user=_admin())


async def test_delete_non_system_prompt_returns_204(db_session):
    await _add_custom_template(db_session)
    response = await delete_prompt("custom.temp", db=db_session, _user=_admin())
    assert response.status_code == 204
    with pytest.raises(NotFoundException):
        await get_prompt_detail("custom.temp", db=db_session, _user=_admin())


async def test_delete_unknown_key_404(db_session):
    await seed_prompt_registry(db_session)
    with pytest.raises(NotFoundException):
        await delete_prompt("nope", db=db_session, _user=_admin())


# --- Registry edge cases ----------------------------------------------------


async def test_seed_is_idempotent(db_session):
    first = await seed_prompt_registry(db_session)
    assert first > 0
    second = await seed_prompt_registry(db_session)
    assert second == 0


async def test_template_without_active_version(db_session):
    """A template with no active version reports active_version=None."""
    template = PromptTemplate(
        key="custom.noactive",
        name="No Active",
        category="general",
        description="",
        variables="[]",
        is_system=False,
    )
    db_session.add(template)
    await db_session.commit()

    detail = await get_prompt_detail("custom.noactive", db=db_session, _user=_admin())
    assert detail.active_version is None

    rows = await list_prompts(db=db_session, _user=_admin())
    row = next(r for r in rows if r.key == "custom.noactive")
    assert row.active_version_no is None


async def test_get_prompt_falls_back_to_default(db_session):
    """Without seeding, get_prompt returns the packaged default content."""
    content = await get_prompt(db_session, KEY)
    assert content


async def test_get_prompt_unknown_key_raises_keyerror(db_session):
    with pytest.raises(KeyError):
        await get_prompt(db_session, "totally.unknown")
