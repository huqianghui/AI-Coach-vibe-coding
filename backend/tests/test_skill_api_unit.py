"""Direct unit tests for api/skills.py router functions.

Bypasses ASGI transport to cover return statement lines that
coverage.py does not track through httpx ASGITransport.
Follows the same pattern as test_material_api_unit.py.
"""

import json
from datetime import UTC
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.skills import (
    RegenerateSopRequest,
    archive_skill,
    convert_skill,
    create_new_version,
    create_skill,
    delete_resource,
    delete_skill,
    download_resource,
    export_skill,
    get_conversion_status,
    get_evaluation_results,
    get_skill,
    import_skill,
    list_published_skills,
    list_resources,
    publish_skill,
    regenerate_sop,
    restore_skill,
    retry_conversion,
    run_quality_evaluation,
    run_structure_check,
    update_skill,
    upload_and_convert,
    upload_resource,
)
from app.models.user import User
from app.schemas.skill import SkillCreate, SkillUpdate
from app.utils.exceptions import NotFoundException, ValidationException

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user() -> User:
    """Create a fake admin user object."""
    user = MagicMock(spec=User)
    user.id = "admin-user-id"
    user.role = "admin"
    return user


def _make_skill(**overrides):
    """Create a mock Skill with sensible defaults."""
    skill = MagicMock()
    skill.id = overrides.get("id", "skill-1")
    skill.name = overrides.get("name", "Test Skill")
    skill.description = overrides.get("description", "desc")
    skill.product = overrides.get("product", "Prod")
    skill.status = overrides.get("status", "draft")
    skill.tags = overrides.get("tags", "")
    skill.content = overrides.get("content", "## Step 1\nContent")
    skill.metadata_json = overrides.get("metadata_json", "{}")
    skill.therapeutic_area = overrides.get("therapeutic_area", "")
    skill.compatibility = overrides.get("compatibility", "")
    skill.current_version = overrides.get("current_version", 1)
    skill.created_by = overrides.get("created_by", "admin-user-id")
    skill.created_at = overrides.get("created_at", "2026-01-01T00:00:00")
    skill.updated_at = overrides.get("updated_at", "2026-01-01T00:00:00")
    skill.conversion_status = overrides.get("conversion_status", None)
    skill.conversion_error = overrides.get("conversion_error", "")
    skill.conversion_job_id = overrides.get("conversion_job_id", None)
    skill.structure_check_passed = overrides.get("structure_check_passed", None)
    skill.structure_check_details = overrides.get("structure_check_details", "{}")
    skill.quality_score = overrides.get("quality_score", None)
    skill.quality_verdict = overrides.get("quality_verdict", None)
    skill.quality_details = overrides.get("quality_details", "{}")
    skill.resources = overrides.get("resources", [])
    skill.versions = overrides.get("versions", [])
    return skill


def _make_upload_file(filename: str = "test.pdf", content: bytes = b"fake-pdf"):
    """Create a mock UploadFile object."""
    mock_file = MagicMock()
    mock_file.filename = filename
    mock_file.content_type = "application/pdf"
    mock_file.read = AsyncMock(return_value=content)
    return mock_file


def _make_db_with_scalars(results=None):
    """Create a mock AsyncSession whose execute returns scalars().all() -> results."""
    if results is None:
        results = []
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = results
    mock_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_result)
    return db


def _make_resource(**overrides):
    """Create a mock SkillResource."""
    r = MagicMock()
    r.id = overrides.get("id", "res-1")
    r.skill_id = overrides.get("skill_id", "skill-1")
    r.version_id = overrides.get("version_id", None)
    r.resource_type = overrides.get("resource_type", "reference")
    r.filename = overrides.get("filename", "doc.pdf")
    r.storage_path = overrides.get("storage_path", "skills/skill-1/references/doc.pdf")
    r.content_type = overrides.get("content_type", "application/pdf")
    r.file_size = overrides.get("file_size", 1024)
    r.extraction_status = overrides.get("extraction_status", None)
    r.created_at = overrides.get("created_at", "2026-01-01T00:00:00")
    r.updated_at = overrides.get("updated_at", "2026-01-01T00:00:00")
    return r


# ===========================================================================
# convert_skill
# ===========================================================================


class TestConvertSkillEndpoint:
    """Tests for POST /{skill_id}/convert."""

    @patch("app.api.skills.asyncio")
    @patch("app.api.skills.skill_service")
    async def test_convert_success(self, mock_svc, mock_asyncio):
        """Successful conversion returns 202 with pending status."""
        skill = _make_skill(conversion_status=None)
        mock_svc.get_skill = AsyncMock(return_value=skill)

        # Mock DB to return at least one reference resource
        db = AsyncMock()
        mock_ref = _make_resource()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_ref]
        db.execute = AsyncMock(return_value=mock_result)

        user = _make_user()
        result = await convert_skill(skill_id="skill-1", db=db, _user=user)

        assert result.status_code == 202
        body = json.loads(result.body)
        assert body["status"] == "processing"
        assert body["method"] == "agent"
        mock_asyncio.create_task.assert_called_once()

    @patch("app.api.skills.skill_service")
    async def test_convert_no_references_raises_422(self, mock_svc):
        """No reference materials triggers bad_request."""
        skill = _make_skill()
        mock_svc.get_skill = AsyncMock(return_value=skill)

        db = _make_db_with_scalars([])
        user = _make_user()

        with pytest.raises(ValidationException):
            await convert_skill(skill_id="skill-1", db=db, _user=user)

    @patch("app.api.skills.skill_service")
    async def test_convert_already_processing_raises_422(self, mock_svc):
        """Conversion in progress triggers bad_request."""
        skill = _make_skill(conversion_status="processing")
        mock_svc.get_skill = AsyncMock(return_value=skill)

        # Mock DB returning at least one reference so we pass the first check
        db = AsyncMock()
        mock_ref = _make_resource()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_ref]
        db.execute = AsyncMock(return_value=mock_result)

        user = _make_user()
        with pytest.raises(ValidationException):
            await convert_skill(skill_id="skill-1", db=db, _user=user)


# ===========================================================================
# retry_conversion
# ===========================================================================


class TestRetryConversionEndpoint:
    """Tests for POST /{skill_id}/retry-conversion."""

    @patch("app.api.skills.asyncio")
    @patch("app.api.skills.skill_service")
    async def test_retry_failed_success(self, mock_svc, mock_asyncio):
        """Retry on failed conversion returns 202."""
        skill = _make_skill(conversion_status="failed")
        mock_svc.get_skill = AsyncMock(return_value=skill)

        db = AsyncMock()
        user = _make_user()
        result = await retry_conversion(skill_id="skill-1", db=db, _user=user)

        assert result.status_code == 202
        body = json.loads(result.body)
        assert body["status"] == "processing"
        assert body["method"] == "agent"
        mock_asyncio.create_task.assert_called_once()

    @patch("app.api.skills.asyncio")
    @patch("app.api.skills.skill_service")
    async def test_retry_none_status_success(self, mock_svc, mock_asyncio):
        """Retry on None conversion status returns 202."""
        skill = _make_skill(conversion_status=None)
        mock_svc.get_skill = AsyncMock(return_value=skill)

        db = AsyncMock()
        user = _make_user()
        result = await retry_conversion(skill_id="skill-1", db=db, _user=user)

        assert result.status_code == 202
        mock_asyncio.create_task.assert_called_once()

    @patch("app.api.skills.skill_service")
    async def test_retry_processing_raises_422(self, mock_svc):
        """Retry when status is processing raises ValidationException."""
        skill = _make_skill(conversion_status="processing")
        mock_svc.get_skill = AsyncMock(return_value=skill)

        db = AsyncMock()
        user = _make_user()
        with pytest.raises(ValidationException):
            await retry_conversion(skill_id="skill-1", db=db, _user=user)

    @patch("app.api.skills.skill_service")
    async def test_retry_completed_raises_422(self, mock_svc):
        """Retry when status is completed raises ValidationException."""
        skill = _make_skill(conversion_status="completed")
        mock_svc.get_skill = AsyncMock(return_value=skill)

        db = AsyncMock()
        user = _make_user()
        with pytest.raises(ValidationException):
            await retry_conversion(skill_id="skill-1", db=db, _user=user)


# ===========================================================================
# get_conversion_status
# ===========================================================================


class TestGetConversionStatusEndpoint:
    """Tests for GET /{skill_id}/conversion-status."""

    @patch("app.api.skills.skill_service")
    async def test_status_returns_fields(self, mock_svc):
        """Returns conversion_status, error, and job_id."""
        skill = _make_skill(
            conversion_status="completed",
            conversion_error="",
            conversion_job_id="job-abc",
        )
        mock_svc.get_skill = AsyncMock(return_value=skill)

        db = AsyncMock()
        user = _make_user()
        result = await get_conversion_status(skill_id="skill-1", db=db, _user=user)

        assert result["conversion_status"] == "completed"
        assert result["conversion_error"] == ""
        assert result["conversion_job_id"] == "job-abc"

    @patch("app.api.skills.skill_service")
    async def test_status_failed_with_error(self, mock_svc):
        """Returns error message when conversion failed."""
        skill = _make_skill(
            conversion_status="failed",
            conversion_error="AI service timeout",
        )
        mock_svc.get_skill = AsyncMock(return_value=skill)

        db = AsyncMock()
        user = _make_user()
        result = await get_conversion_status(skill_id="skill-1", db=db, _user=user)

        assert result["conversion_status"] == "failed"
        assert result["conversion_error"] == "AI service timeout"

    @patch("app.api.skills.skill_service")
    async def test_status_includes_conversion_progress(self, mock_svc):
        """Returns conversion progress from metadata_json if present."""
        progress = {"current_step": 2, "total_steps": 5}
        meta = json.dumps({"conversion_progress": progress})
        skill = _make_skill(
            conversion_status="processing",
            metadata_json=meta,
        )
        mock_svc.get_skill = AsyncMock(return_value=skill)

        db = AsyncMock()
        user = _make_user()
        result = await get_conversion_status(skill_id="skill-1", db=db, _user=user)

        assert result["progress"] == progress

    @patch("app.api.skills.skill_service")
    async def test_status_invalid_metadata_json_ignored(self, mock_svc):
        """Invalid metadata_json does not break the response."""
        skill = _make_skill(
            conversion_status="completed",
            metadata_json="not valid json",
        )
        mock_svc.get_skill = AsyncMock(return_value=skill)

        db = AsyncMock()
        user = _make_user()
        result = await get_conversion_status(skill_id="skill-1", db=db, _user=user)

        assert result["conversion_status"] == "completed"
        assert "progress" not in result


# ===========================================================================
# upload_and_convert
# ===========================================================================


class TestUploadAndConvertEndpoint:
    """Tests for POST /{skill_id}/upload-and-convert."""

    @patch("app.api.skills.asyncio")
    @patch("app.api.skills.get_storage")
    @patch("app.api.skills.skill_service")
    async def test_upload_and_convert_success(self, mock_svc, mock_storage_fn, mock_asyncio):
        """Upload one file and trigger conversion returns 202."""
        skill = _make_skill()
        mock_svc.get_skill = AsyncMock(return_value=skill)

        mock_storage = AsyncMock()
        mock_storage_fn.return_value = mock_storage

        # Existing resources count = 0
        db = _make_db_with_scalars([])
        user = _make_user()

        file = _make_upload_file(filename="doc.pdf", content=b"fake-pdf-content")
        result = await upload_and_convert(skill_id="skill-1", files=[file], db=db, user=user)

        assert result.status_code == 202
        body = json.loads(result.body)
        assert body["files_uploaded"] == 1
        assert body["status"] == "processing"
        assert body["method"] == "agent"
        mock_asyncio.create_task.assert_called_once()

    @patch("app.api.skills.skill_service")
    async def test_upload_too_many_files_raises_422(self, mock_svc):
        """Exceeding MAX_FILES_PER_UPLOAD raises ValidationException."""
        skill = _make_skill()
        mock_svc.get_skill = AsyncMock(return_value=skill)

        db = AsyncMock()
        user = _make_user()

        files = [_make_upload_file(filename=f"doc{i}.pdf") for i in range(11)]
        with pytest.raises(ValidationException):
            await upload_and_convert(skill_id="skill-1", files=files, db=db, user=user)

    @patch("app.api.skills.skill_service")
    async def test_upload_exceeds_resource_limit_raises_422(self, mock_svc):
        """Exceeding MAX_RESOURCES_PER_SKILL raises ValidationException."""
        skill = _make_skill()
        mock_svc.get_skill = AsyncMock(return_value=skill)

        # Simulate 99 existing resources, uploading 2 more exceeds 100
        existing = [MagicMock() for _ in range(99)]
        db = _make_db_with_scalars(existing)
        user = _make_user()

        files = [_make_upload_file(filename="a.pdf"), _make_upload_file(filename="b.pdf")]
        with pytest.raises(ValidationException):
            await upload_and_convert(skill_id="skill-1", files=files, db=db, user=user)

    @patch("app.api.skills.get_storage")
    @patch("app.api.skills.skill_service")
    async def test_upload_no_filename_raises_422(self, mock_svc, mock_storage_fn):
        """File without a filename raises ValidationException."""
        skill = _make_skill()
        mock_svc.get_skill = AsyncMock(return_value=skill)
        mock_storage_fn.return_value = AsyncMock()

        db = _make_db_with_scalars([])
        user = _make_user()

        file = _make_upload_file(filename="")
        file.filename = ""
        with pytest.raises(ValidationException):
            await upload_and_convert(skill_id="skill-1", files=[file], db=db, user=user)


# ===========================================================================
# regenerate_sop
# ===========================================================================


class TestRegenerateSopEndpoint:
    """Tests for POST /{skill_id}/regenerate-sop."""

    @patch("app.services.skill_conversion_service.regenerate_sop_with_feedback")
    async def test_regenerate_success(self, mock_regen):
        """Valid feedback triggers regeneration and returns updated skill."""
        mock_skill = _make_skill()
        mock_regen.return_value = mock_skill

        db = AsyncMock()
        user = _make_user()
        body = RegenerateSopRequest(feedback="Please improve step 2")

        result = await regenerate_sop(skill_id="skill-1", body=body, db=db, _user=user)
        assert result == mock_skill
        mock_regen.assert_awaited_once()

    async def test_regenerate_empty_feedback_raises_422(self):
        """Empty feedback string raises ValidationException."""
        db = AsyncMock()
        user = _make_user()
        body = RegenerateSopRequest(feedback="")

        with pytest.raises(ValidationException):
            await regenerate_sop(skill_id="skill-1", body=body, db=db, _user=user)

    async def test_regenerate_whitespace_feedback_raises_422(self):
        """Whitespace-only feedback raises ValidationException."""
        db = AsyncMock()
        user = _make_user()
        body = RegenerateSopRequest(feedback="   ")

        with pytest.raises(ValidationException):
            await regenerate_sop(skill_id="skill-1", body=body, db=db, _user=user)

    async def test_regenerate_oversized_feedback_raises_422(self):
        """Feedback > 5000 chars raises ValidationException."""
        db = AsyncMock()
        user = _make_user()
        body = RegenerateSopRequest(feedback="x" * 5001)

        with pytest.raises(ValidationException):
            await regenerate_sop(skill_id="skill-1", body=body, db=db, _user=user)


# ===========================================================================
# publish_skill
# ===========================================================================


class TestPublishSkillEndpoint:
    """Tests for POST /{skill_id}/publish."""

    @patch("app.api.skills.skill_service")
    async def test_publish_returns_skill(self, mock_svc):
        """publish_skill returns the published skill from service."""
        mock_skill = _make_skill(status="published")
        mock_svc.publish_skill = AsyncMock(return_value=mock_skill)

        db = AsyncMock()
        user = _make_user()
        result = await publish_skill(skill_id="skill-1", db=db, user=user)

        assert result == mock_skill
        mock_svc.publish_skill.assert_awaited_once_with(db, "skill-1", "admin-user-id")


# ===========================================================================
# archive_skill
# ===========================================================================


class TestArchiveSkillEndpoint:
    """Tests for POST /{skill_id}/archive."""

    @patch("app.api.skills.skill_service")
    async def test_archive_returns_skill(self, mock_svc):
        """archive_skill returns the archived skill from service."""
        mock_skill = _make_skill(status="archived")
        mock_svc.archive_skill = AsyncMock(return_value=mock_skill)

        db = AsyncMock()
        user = _make_user()
        result = await archive_skill(skill_id="skill-1", db=db, user=user)

        assert result == mock_skill
        mock_svc.archive_skill.assert_awaited_once_with(db, "skill-1", "admin-user-id")


# ===========================================================================
# restore_skill
# ===========================================================================


class TestRestoreSkillEndpoint:
    """Tests for POST /{skill_id}/restore."""

    @patch("app.api.skills.skill_service")
    async def test_restore_returns_skill(self, mock_svc):
        """restore_skill returns the restored skill from service."""
        mock_skill = _make_skill(status="draft")
        mock_svc.restore_skill = AsyncMock(return_value=mock_skill)

        db = AsyncMock()
        user = _make_user()
        result = await restore_skill(skill_id="skill-1", db=db, user=user)

        assert result == mock_skill
        mock_svc.restore_skill.assert_awaited_once_with(db, "skill-1", "admin-user-id")


# ===========================================================================
# create_new_version
# ===========================================================================


class TestCreateNewVersionEndpoint:
    """Tests for POST /{skill_id}/new-version."""

    @patch("app.api.skills.skill_service")
    async def test_new_version_returns_skill(self, mock_svc):
        """create_new_version returns the new version skill from service."""
        mock_skill = _make_skill(current_version=2)
        mock_svc.create_new_version = AsyncMock(return_value=mock_skill)

        db = AsyncMock()
        user = _make_user()
        result = await create_new_version(skill_id="skill-1", db=db, user=user)

        assert result == mock_skill
        mock_svc.create_new_version.assert_awaited_once_with(db, "skill-1", "admin-user-id")


# ===========================================================================
# run_structure_check
# ===========================================================================


class TestRunStructureCheckEndpoint:
    """Tests for POST /{skill_id}/check-structure."""

    @patch("app.api.skills.to_dict")
    @patch("app.api.skills.check_skill_structure")
    @patch("app.api.skills.skill_service")
    async def test_structure_check_passed(self, mock_svc, mock_check, mock_to_dict):
        """Structure check passes with score 100 and no issues."""
        skill = _make_skill()
        mock_svc.get_skill = AsyncMock(return_value=skill)

        mock_result = MagicMock()
        mock_result.passed = True
        mock_result.score = 100
        mock_result.issues = []
        mock_check.return_value = mock_result
        mock_to_dict.return_value = {"passed": True, "score": 100, "issues": []}

        db = AsyncMock()
        user = _make_user()
        result = await run_structure_check(skill_id="skill-1", db=db, _user=user)

        assert result.passed is True
        assert result.score == 100
        assert result.issues == []
        # Verify skill attributes were updated
        assert skill.structure_check_passed is True

    @patch("app.api.skills.to_dict")
    @patch("app.api.skills.check_skill_structure")
    @patch("app.api.skills.skill_service")
    async def test_structure_check_with_issues(self, mock_svc, mock_check, mock_to_dict):
        """Structure check with issues returns them properly."""
        skill = _make_skill()
        mock_svc.get_skill = AsyncMock(return_value=skill)

        mock_issue = MagicMock()
        mock_issue.severity = "warning"
        mock_issue.dimension = "sop_steps"
        mock_issue.message = "Too few steps"
        mock_issue.suggestion = "Add more steps"

        mock_result = MagicMock()
        mock_result.passed = False
        mock_result.score = 60
        mock_result.issues = [mock_issue]
        mock_check.return_value = mock_result
        mock_to_dict.return_value = {"passed": False, "score": 60, "issues": []}

        db = AsyncMock()
        user = _make_user()
        result = await run_structure_check(skill_id="skill-1", db=db, _user=user)

        assert result.passed is False
        assert result.score == 60
        assert len(result.issues) == 1
        assert result.issues[0]["severity"] == "warning"


# ===========================================================================
# run_quality_evaluation
# ===========================================================================


class TestRunQualityEvaluationEndpoint:
    """Tests for POST /{skill_id}/evaluate-quality."""

    @patch("app.api.skills.asyncio")
    @patch("app.api.skills.skill_service")
    async def test_evaluate_returns_202(self, mock_svc, mock_asyncio):
        """Triggering evaluation returns 202 and starts background task."""
        mock_svc.get_skill = AsyncMock(return_value=_make_skill())

        db = AsyncMock()
        user = _make_user()
        result = await run_quality_evaluation(skill_id="skill-1", db=db, _user=user)

        assert result.status_code == 202
        body = json.loads(result.body)
        assert body["status"] == "evaluating"
        mock_asyncio.create_task.assert_called_once()


# ===========================================================================
# get_evaluation_results
# ===========================================================================


class TestGetEvaluationResultsEndpoint:
    """Tests for GET /{skill_id}/evaluation."""

    @patch("app.api.skills.skill_evaluation_service")
    @patch("app.api.skills.skill_service")
    async def test_evaluation_results_complete(self, mock_svc, mock_eval_svc):
        """Returns combined L1 + L2 results with staleness indicator."""
        skill = _make_skill(
            structure_check_passed=True,
            structure_check_details='{"passed": true, "score": 100}',
            quality_score=85,
            quality_verdict="good",
            quality_details='{"content_hash": "abc123", "dimensions": []}',
        )
        mock_svc.get_skill = AsyncMock(return_value=skill)
        mock_eval_svc.is_evaluation_stale.return_value = False

        db = AsyncMock()
        user = _make_user()
        result = await get_evaluation_results(skill_id="skill-1", db=db, _user=user)

        assert result["structure_check"]["passed"] is True
        assert result["quality"]["score"] == 85
        assert result["quality"]["verdict"] == "good"
        assert result["quality"]["is_stale"] is False

    @patch("app.api.skills.skill_evaluation_service")
    @patch("app.api.skills.skill_service")
    async def test_evaluation_results_no_data(self, mock_svc, mock_eval_svc):
        """Returns empty details when no evaluation has been run."""
        skill = _make_skill(
            structure_check_passed=None,
            structure_check_details="{}",
            quality_score=None,
            quality_verdict=None,
            quality_details="{}",
        )
        mock_svc.get_skill = AsyncMock(return_value=skill)
        mock_eval_svc.is_evaluation_stale.return_value = True

        db = AsyncMock()
        user = _make_user()
        result = await get_evaluation_results(skill_id="skill-1", db=db, _user=user)

        assert result["structure_check"]["passed"] is None
        assert result["quality"]["score"] is None
        assert result["quality"]["is_stale"] is True

    @patch("app.api.skills.skill_evaluation_service")
    @patch("app.api.skills.skill_service")
    async def test_evaluation_results_invalid_json(self, mock_svc, mock_eval_svc):
        """Handles invalid JSON in stored details gracefully."""
        skill = _make_skill(
            structure_check_details="not valid json",
            quality_details="also invalid",
        )
        mock_svc.get_skill = AsyncMock(return_value=skill)
        mock_eval_svc.is_evaluation_stale.return_value = True

        db = AsyncMock()
        user = _make_user()
        result = await get_evaluation_results(skill_id="skill-1", db=db, _user=user)

        # Falls back to empty dicts
        assert result["structure_check"]["details"] == {}
        assert result["quality"]["details"] == {}


# ===========================================================================
# upload_resource
# ===========================================================================


class TestUploadResourceEndpoint:
    """Tests for POST /{skill_id}/resources."""

    @patch("app.api.skills.get_storage")
    @patch("app.api.skills.skill_service")
    async def test_upload_resource_success(self, mock_svc, mock_storage_fn):
        """Upload a valid reference resource returns 201 with resource data."""
        mock_svc.get_skill = AsyncMock(return_value=_make_skill())

        mock_storage = AsyncMock()
        mock_storage_fn.return_value = mock_storage

        # Existing resources = 0
        db = _make_db_with_scalars([])
        user = _make_user()

        file = _make_upload_file(filename="report.pdf", content=b"pdf-content")
        await upload_resource(
            skill_id="skill-1",
            file=file,
            resource_type="reference",
            db=db,
            user=user,
        )

        # The function returns the SkillResource ORM object (which is the db.add argument)
        # Verify storage was called
        mock_storage.save.assert_awaited_once()
        db.add.assert_called_once()

    @patch("app.api.skills.skill_service")
    async def test_upload_resource_invalid_type_raises_422(self, mock_svc):
        """Invalid resource_type raises ValidationException."""
        mock_svc.get_skill = AsyncMock(return_value=_make_skill())

        db = AsyncMock()
        user = _make_user()
        file = _make_upload_file()

        with pytest.raises(ValidationException):
            await upload_resource(
                skill_id="skill-1",
                file=file,
                resource_type="invalid",
                db=db,
                user=user,
            )

    @patch("app.api.skills.skill_service")
    async def test_upload_resource_no_filename_raises_422(self, mock_svc):
        """File without filename raises ValidationException."""
        mock_svc.get_skill = AsyncMock(return_value=_make_skill())

        db = AsyncMock()
        user = _make_user()
        file = _make_upload_file()
        file.filename = ""

        with pytest.raises(ValidationException):
            await upload_resource(
                skill_id="skill-1",
                file=file,
                resource_type="reference",
                db=db,
                user=user,
            )

    @patch("app.api.skills.get_storage")
    @patch("app.api.skills.skill_service")
    async def test_upload_resource_limit_exceeded_raises_422(self, mock_svc, mock_storage_fn):
        """Exceeding MAX_RESOURCES_PER_SKILL raises ValidationException."""
        mock_svc.get_skill = AsyncMock(return_value=_make_skill())
        mock_storage_fn.return_value = AsyncMock()

        # Simulate 100 existing resources (at the limit)
        existing = [MagicMock() for _ in range(100)]
        db = _make_db_with_scalars(existing)
        user = _make_user()
        file = _make_upload_file(filename="report.pdf", content=b"pdf")

        with pytest.raises(ValidationException):
            await upload_resource(
                skill_id="skill-1",
                file=file,
                resource_type="reference",
                db=db,
                user=user,
            )


# ===========================================================================
# list_resources
# ===========================================================================


class TestListResourcesEndpoint:
    """Tests for GET /{skill_id}/resources."""

    @patch("app.api.skills.skill_service")
    async def test_list_empty(self, mock_svc):
        """Returns empty list when no resources exist."""
        mock_svc.get_skill = AsyncMock(return_value=_make_skill())

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        user = _make_user()
        result = await list_resources(skill_id="skill-1", db=db, _user=user)
        assert result == []

    @patch("app.api.skills.skill_service")
    async def test_list_with_resources(self, mock_svc):
        """Returns list of resources for a skill."""
        mock_svc.get_skill = AsyncMock(return_value=_make_skill())

        resources = [_make_resource(), _make_resource(id="res-2")]
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = resources
        db.execute = AsyncMock(return_value=mock_result)

        user = _make_user()
        result = await list_resources(skill_id="skill-1", db=db, _user=user)
        assert len(result) == 2


# ===========================================================================
# delete_resource
# ===========================================================================


class TestDeleteResourceEndpoint:
    """Tests for DELETE /{skill_id}/resources/{resource_id}."""

    @patch("app.api.skills.get_storage")
    async def test_delete_success(self, mock_storage_fn):
        """Delete existing resource returns 204."""
        resource = _make_resource()
        mock_storage = AsyncMock()
        mock_storage_fn.return_value = mock_storage

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = resource
        db.execute = AsyncMock(return_value=mock_result)

        user = _make_user()
        result = await delete_resource(skill_id="skill-1", resource_id="res-1", db=db, _user=user)

        assert result.status_code == 204
        db.delete.assert_called_once_with(resource)
        mock_storage.delete.assert_awaited_once()

    async def test_delete_not_found_raises_404(self):
        """Non-existent resource raises NotFoundException."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        user = _make_user()
        with pytest.raises(NotFoundException):
            await delete_resource(skill_id="skill-1", resource_id="missing", db=db, _user=user)

    @patch("app.api.skills.get_storage")
    async def test_delete_storage_error_still_succeeds(self, mock_storage_fn):
        """Storage delete failure is swallowed (best-effort cleanup)."""
        resource = _make_resource()
        mock_storage = AsyncMock()
        mock_storage.delete = AsyncMock(side_effect=Exception("storage down"))
        mock_storage_fn.return_value = mock_storage

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = resource
        db.execute = AsyncMock(return_value=mock_result)

        user = _make_user()
        result = await delete_resource(skill_id="skill-1", resource_id="res-1", db=db, _user=user)

        assert result.status_code == 204
        db.delete.assert_called_once_with(resource)


# ===========================================================================
# download_resource
# ===========================================================================


class TestDownloadResourceEndpoint:
    """Tests for GET /{skill_id}/resources/{resource_id}/download."""

    @patch("app.api.skills.get_storage")
    async def test_download_success(self, mock_storage_fn):
        """Download an existing resource returns the file bytes."""
        resource = _make_resource(
            filename="report.pdf",
            content_type="application/pdf",
        )
        mock_storage = AsyncMock()
        mock_storage.exists = AsyncMock(return_value=True)
        mock_storage.read = AsyncMock(return_value=b"pdf-bytes")
        mock_storage_fn.return_value = mock_storage

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = resource
        db.execute = AsyncMock(return_value=mock_result)

        user = _make_user()
        result = await download_resource(skill_id="skill-1", resource_id="res-1", db=db, _user=user)

        assert result.body == b"pdf-bytes"
        assert result.media_type == "application/pdf"
        assert "report.pdf" in result.headers["content-disposition"]

    async def test_download_not_found_raises_404(self):
        """Non-existent resource raises NotFoundException."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        user = _make_user()
        with pytest.raises(NotFoundException):
            await download_resource(skill_id="skill-1", resource_id="missing", db=db, _user=user)

    @patch("app.api.skills.get_storage")
    async def test_download_file_missing_in_storage_raises_404(self, mock_storage_fn):
        """File missing from storage raises NotFoundException."""
        resource = _make_resource()
        mock_storage = AsyncMock()
        mock_storage.exists = AsyncMock(return_value=False)
        mock_storage_fn.return_value = mock_storage

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = resource
        db.execute = AsyncMock(return_value=mock_result)

        user = _make_user()
        with pytest.raises(NotFoundException):
            await download_resource(skill_id="skill-1", resource_id="res-1", db=db, _user=user)


# ===========================================================================
# update_skill
# ===========================================================================


class TestUpdateSkillEndpoint:
    """Tests for PUT /{skill_id}."""

    @patch("app.api.skills.skill_service")
    async def test_update_returns_skill(self, mock_svc):
        """update_skill returns the updated skill from service."""
        mock_skill = _make_skill(name="Updated Skill")
        mock_svc.update_skill = AsyncMock(return_value=mock_skill)

        db = AsyncMock()
        user = _make_user()
        data = SkillUpdate(name="Updated Skill")
        result = await update_skill(skill_id="skill-1", data=data, db=db, user=user)

        assert result == mock_skill
        mock_svc.update_skill.assert_awaited_once_with(db, "skill-1", data, "admin-user-id")


# ===========================================================================
# list_published_skills
# ===========================================================================


class TestListPublishedSkillsEndpoint:
    """Tests for GET /published."""

    @patch("app.api.skills.skill_service")
    async def test_list_published_empty(self, mock_svc):
        """Returns empty paginated response when no published skills."""
        mock_svc.get_published_skills = AsyncMock(return_value=([], 0))

        db = AsyncMock()
        user = _make_user()
        result = await list_published_skills(page=1, page_size=20, search=None, db=db, _user=user)

        assert result.total == 0
        assert result.items == []

    @patch("app.api.skills.skill_service")
    async def test_list_published_with_results(self, mock_svc):
        """Returns paginated published skills."""
        from datetime import datetime

        mock_item = MagicMock()
        mock_item.id = "s1"
        mock_item.name = "Published Skill"
        mock_item.description = "desc"
        mock_item.product = "Prod"
        mock_item.status = "published"
        mock_item.tags = ""
        mock_item.quality_score = 90
        mock_item.quality_verdict = "good"
        mock_item.structure_check_passed = True
        mock_item.conversion_status = "completed"
        mock_item.current_version = 1
        mock_item.created_by = "admin-user-id"
        mock_item.created_at = datetime(2026, 1, 1, tzinfo=UTC)
        mock_item.updated_at = datetime(2026, 1, 1, tzinfo=UTC)
        mock_item.foundry_skill_name = ""
        mock_item.foundry_sync_status = "none"
        mock_item.foundry_cloud_version = ""
        mock_item.foundry_sync_error = ""

        mock_svc.get_published_skills = AsyncMock(return_value=([mock_item], 1))

        db = AsyncMock()
        user = _make_user()
        result = await list_published_skills(page=1, page_size=20, search=None, db=db, _user=user)

        assert result.total == 1
        assert len(result.items) == 1

    @patch("app.api.skills.skill_service")
    async def test_list_published_with_search(self, mock_svc):
        """Search parameter is passed through to the service."""
        mock_svc.get_published_skills = AsyncMock(return_value=([], 0))

        db = AsyncMock()
        user = _make_user()
        await list_published_skills(page=1, page_size=10, search="keyword", db=db, _user=user)

        mock_svc.get_published_skills.assert_awaited_once_with(
            db, page=1, page_size=10, search="keyword"
        )


# ===========================================================================
# create_skill (direct call to cover return line 79)
# ===========================================================================


class TestCreateSkillEndpoint:
    """Tests for POST / (create_skill)."""

    @patch("app.api.skills.skill_service")
    async def test_create_returns_skill(self, mock_svc):
        """create_skill returns the newly created skill."""
        mock_skill = _make_skill()
        mock_svc.create_skill = AsyncMock(return_value=mock_skill)

        db = AsyncMock()
        user = _make_user()
        data = SkillCreate(name="New Skill", product="Prod")

        result = await create_skill(data=data, db=db, user=user)
        assert result == mock_skill
        mock_svc.create_skill.assert_awaited_once_with(db, data, "admin-user-id")


# ===========================================================================
# get_skill (direct call to cover return lines 493-495)
# ===========================================================================


class TestGetSkillEndpoint:
    """Tests for GET /{skill_id}."""

    @patch("app.api.skills._get_source_materials", new_callable=AsyncMock, return_value=[])
    @patch("app.api.skills.skill_service")
    async def test_get_skill_returns_skill_out(self, mock_svc, _mock_src_mats):
        """get_skill returns SkillOut with source_materials."""
        from datetime import datetime

        mock_skill = MagicMock()
        mock_skill.id = "s1"
        mock_skill.name = "Skill One"
        mock_skill.description = "desc"
        mock_skill.product = "Prod"
        mock_skill.status = "draft"
        mock_skill.tags = ""
        mock_skill.quality_score = None
        mock_skill.quality_verdict = None
        mock_skill.structure_check_passed = None
        mock_skill.conversion_status = None
        mock_skill.current_version = 1
        mock_skill.created_by = "admin-user-id"
        mock_skill.created_at = datetime(2026, 1, 1, tzinfo=UTC)
        mock_skill.updated_at = datetime(2026, 1, 1, tzinfo=UTC)
        mock_skill.therapeutic_area = ""
        mock_skill.compatibility = ""
        mock_skill.metadata_json = "{}"
        mock_skill.content = ""
        mock_skill.structure_check_details = "{}"
        mock_skill.quality_details = "{}"
        mock_skill.conversion_error = ""
        mock_skill.resources = []
        mock_skill.versions = []
        mock_skill.foundry_skill_name = ""
        mock_skill.foundry_sync_status = "none"
        mock_skill.foundry_cloud_version = ""
        mock_skill.foundry_sync_error = ""
        mock_svc.get_skill = AsyncMock(return_value=mock_skill)

        db = AsyncMock()
        user = _make_user()
        result = await get_skill(skill_id="s1", db=db, _user=user)

        assert result.id == "s1"
        assert result.source_materials == []


# ===========================================================================
# delete_skill (direct call to cover return line 518)
# ===========================================================================


class TestDeleteSkillEndpoint:
    """Tests for DELETE /{skill_id}."""

    @patch("app.api.skills.skill_service")
    async def test_delete_returns_204(self, mock_svc):
        """delete_skill returns a 204 Response."""
        mock_svc.delete_skill = AsyncMock()

        db = AsyncMock()
        user = _make_user()
        result = await delete_skill(skill_id="skill-1", db=db, _user=user)

        assert result.status_code == 204
        mock_svc.delete_skill.assert_awaited_once_with(db, "skill-1")


# ===========================================================================
# export_skill (direct call to cover return line 478)
# ===========================================================================


class TestExportSkillEndpoint:
    """Tests for GET /{skill_id}/export."""

    @patch("app.api.skills.skill_zip_service")
    async def test_export_returns_zip_response(self, mock_zip_svc):
        """export_skill returns a zip Response."""
        mock_zip_svc.export_skill_zip = AsyncMock(return_value=b"PK-zip-bytes")

        db = AsyncMock()
        user = _make_user()
        result = await export_skill(skill_id="skill-1", db=db, _user=user)

        assert result.body == b"PK-zip-bytes"
        assert result.media_type == "application/zip"


# ===========================================================================
# import_skill (direct call to cover return lines 282, 287-291)
# ===========================================================================


class TestImportSkillEndpoint:
    """Tests for POST /import."""

    @patch("app.api.skills.skill_service")
    @patch("app.api.skills.skill_zip_service")
    async def test_import_returns_skill(self, mock_zip_svc, mock_svc):
        """import_skill returns the imported skill."""
        mock_imported = _make_skill(id="imported-1")
        mock_zip_svc.import_skill_zip = AsyncMock(return_value=mock_imported)
        mock_zip_svc.MAX_ZIP_SIZE_BYTES = 100 * 1024 * 1024
        mock_svc.get_skill = AsyncMock(return_value=mock_imported)

        file = _make_upload_file(filename="skill.zip", content=b"PK-fake-zip")
        db = AsyncMock()
        user = _make_user()

        result = await import_skill(file=file, db=db, user=user)
        assert result == mock_imported
        mock_zip_svc.import_skill_zip.assert_awaited_once()

    async def test_import_non_zip_raises_422(self):
        """Non-zip file extension raises ValidationException."""
        file = _make_upload_file(filename="doc.pdf")
        db = AsyncMock()
        user = _make_user()

        with pytest.raises(ValidationException):
            await import_skill(file=file, db=db, user=user)

    async def test_import_no_filename_raises_422(self):
        """Empty filename raises ValidationException."""
        file = _make_upload_file(filename="")
        db = AsyncMock()
        user = _make_user()

        with pytest.raises(ValidationException):
            await import_skill(file=file, db=db, user=user)

    @patch("app.api.skills.skill_zip_service")
    async def test_import_oversized_raises_422(self, mock_zip_svc):
        """ZIP exceeding MAX_ZIP_SIZE_BYTES raises ValidationException."""
        mock_zip_svc.MAX_ZIP_SIZE_BYTES = 10  # Very small limit for test
        big_content = b"x" * 20
        file = _make_upload_file(filename="skill.zip", content=big_content)
        db = AsyncMock()
        user = _make_user()

        with pytest.raises(ValidationException):
            await import_skill(file=file, db=db, user=user)


# ===========================================================================
# run_quality_evaluation: test the inner _run_evaluation function (lines 615-621)
# ===========================================================================


class TestRunQualityEvaluationInner:
    """Tests that exercise the inner _run_evaluation background task."""

    @patch("app.api.skills.AsyncSessionLocal")
    @patch("app.api.skills.skill_evaluation_service")
    @patch("app.api.skills.skill_service")
    async def test_evaluation_inner_success(self, mock_svc, mock_eval_svc, mock_session_cls):
        """The inner _run_evaluation function succeeds and commits."""
        mock_svc.get_skill = AsyncMock(return_value=_make_skill())
        mock_eval_svc.evaluate_skill_quality = AsyncMock()

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session_cls.return_value = mock_session

        # Capture the coroutine passed to asyncio.create_task
        captured_coro = None

        def capture_task(coro):
            nonlocal captured_coro
            captured_coro = coro
            # Return a mock task
            return MagicMock()

        db = AsyncMock()
        user = _make_user()

        with patch("app.api.skills.asyncio") as mock_asyncio:
            mock_asyncio.create_task.side_effect = capture_task
            await run_quality_evaluation(skill_id="skill-1", db=db, _user=user)

        # Now await the captured coroutine to exercise the inner function
        assert captured_coro is not None
        await captured_coro

        mock_eval_svc.evaluate_skill_quality.assert_awaited_once_with(mock_session, "skill-1")
        mock_session.commit.assert_awaited_once()

    @patch("app.api.skills.AsyncSessionLocal")
    @patch("app.api.skills.skill_evaluation_service")
    @patch("app.api.skills.skill_service")
    async def test_evaluation_inner_failure(self, mock_svc, mock_eval_svc, mock_session_cls):
        """The inner _run_evaluation function handles exceptions gracefully."""
        mock_svc.get_skill = AsyncMock(return_value=_make_skill())
        mock_eval_svc.evaluate_skill_quality = AsyncMock(
            side_effect=RuntimeError("AI service down")
        )

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session_cls.return_value = mock_session

        captured_coro = None

        def capture_task(coro):
            nonlocal captured_coro
            captured_coro = coro
            return MagicMock()

        db = AsyncMock()
        user = _make_user()

        with patch("app.api.skills.asyncio") as mock_asyncio:
            mock_asyncio.create_task.side_effect = capture_task
            await run_quality_evaluation(skill_id="skill-1", db=db, _user=user)

        # Await the captured coroutine - should NOT raise
        assert captured_coro is not None
        await captured_coro

        mock_session.rollback.assert_awaited_once()
