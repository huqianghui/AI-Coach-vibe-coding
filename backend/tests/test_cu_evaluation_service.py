"""Tests for CU Evaluation Service — voice analyzer schema, auth, merge, and voice parsing."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.cu_evaluation_service import (
    DEFAULT_VOICE_DIMENSIONS,
    _calculate_weighted_total,
    _coerce_score,
    _extract_cu_field_value,
    _get_auth_headers,
    _get_session_rubric,
    _mime_type_for_audio_path,
    _parse_cu_voice_result,
    _poll_analyzer_operation,
    _poll_result,
    _put_analyzer,
    _wait_for_analyzer_ready,
    build_voice_analyzer_schema,
    merge_scores,
    score_voice_with_cu,
    sync_rubric_analyzers,
)


class TestBuildVoiceAnalyzerSchema:
    """Test voice analyzer schema generation."""

    def test_uses_defaults_when_empty(self):
        schema = build_voice_analyzer_schema([])

        assert schema["name"] == "VoiceScoring"
        fields = schema["fields"]
        assert "fluency" in fields
        assert "tone" in fields
        assert "pace" in fields
        assert "pronunciation" in fields
        assert "feedback_summary" in fields
        assert "transcript" in fields

    def test_custom_voice_dimensions(self):
        dims = [
            {"name": "Clarity", "weight": 50, "max_score": 100},
            {"name": "Energy", "weight": 50, "max_score": 100},
        ]
        schema = build_voice_analyzer_schema(dims)

        fields = schema["fields"]
        assert "clarity" in fields
        assert "energy" in fields
        assert "fluency" not in fields

    def test_voice_field_type_is_string(self):
        schema = build_voice_analyzer_schema(DEFAULT_VOICE_DIMENSIONS)

        fluency = schema["fields"]["fluency"]
        assert fluency["type"] == "string"
        assert fluency["method"] == "generate"

    def test_always_includes_transcript(self):
        dims = [{"name": "Test", "weight": 100, "max_score": 100}]
        schema = build_voice_analyzer_schema(dims)
        assert "transcript" in schema["fields"]


class TestGetAuthHeaders:
    """Test authentication header resolution."""

    @pytest.mark.asyncio
    async def test_entra_id_preferred(self):
        mock_credential = AsyncMock()
        mock_token = MagicMock()
        mock_token.token = "fake-bearer-token"
        mock_credential.get_token = AsyncMock(return_value=mock_token)
        mock_credential.close = AsyncMock()

        mock_module = MagicMock()
        mock_module.DefaultAzureCredential = MagicMock(return_value=mock_credential)

        with patch.dict("sys.modules", {"azure.identity.aio": mock_module}):
            headers = await _get_auth_headers("some-api-key")

        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer fake-bearer-token"
        assert "Content-Type" in headers

    @pytest.mark.asyncio
    async def test_api_key_fallback(self):
        mock_module = MagicMock()
        mock_credential = AsyncMock()
        mock_credential.get_token = AsyncMock(side_effect=Exception("Token fetch failed"))
        mock_credential.close = AsyncMock()
        mock_module.DefaultAzureCredential = MagicMock(return_value=mock_credential)

        with patch.dict("sys.modules", {"azure.identity.aio": mock_module}):
            result = await _get_auth_headers("test-key-123")

        assert result["Ocp-Apim-Subscription-Key"] == "test-key-123"
        assert result["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_no_credentials_raises(self):
        with patch.dict("sys.modules", {"azure.identity.aio": None}):
            with pytest.raises((RuntimeError, TypeError, ModuleNotFoundError)):
                await _get_auth_headers("")


class TestPutAnalyzer:
    """Test CU analyzer create/update behavior."""

    @pytest.mark.asyncio
    async def test_create_replace_uses_allow_replace_and_waits_until_ready(self):
        """Deterministic analyzer IDs are replaced and must be ready before reuse."""
        captured = {}
        get_urls = []

        class FakePutResponse:
            status_code = 201
            text = ""
            headers = {"Operation-Location": "https://example.test/operations/create-1"}

        class FakeGetResponse:
            status_code = 200
            text = ""

            def __init__(self, body):
                self.body = body

            def json(self):
                return self.body

        class FakeClient:
            def __init__(self, timeout: float) -> None:
                self.timeout = timeout

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

            async def put(self, url, headers, json):
                captured["url"] = url
                captured["body"] = json
                return FakePutResponse()

            async def get(self, url, headers):
                get_urls.append(url)
                if "operations" in url:
                    return FakeGetResponse({"status": "Succeeded"})
                return FakeGetResponse({"status": "ready"})

        with (
            patch(
                "app.services.cu_evaluation_service._get_auth_headers",
                AsyncMock(return_value={"Content-Type": "application/json"}),
            ),
            patch("app.services.cu_evaluation_service.httpx.AsyncClient", FakeClient),
            patch("app.services.cu_evaluation_service.asyncio.sleep", AsyncMock()),
            patch(
                "app.services.cu_evaluation_service._get_cu_api_version",
                return_value="2025-11-01",
            ),
        ):
            await _put_analyzer(
                "https://example.cognitiveservices.azure.com",
                "",
                "rubricVoice12345678",
                {"name": "VoiceScoring", "fields": {}},
                "voice",
            )

        assert captured["url"].endswith(
            "/contentunderstanding/analyzers/rubricVoice12345678"
            "?api-version=2025-11-01&allowReplace=true"
        )
        assert captured["body"]["baseAnalyzerId"] == "prebuilt-audio"
        assert captured["body"]["fieldSchema"] == {"name": "VoiceScoring", "fields": {}}
        assert get_urls == [
            "https://example.test/operations/create-1",
            "https://example.cognitiveservices.azure.com/contentunderstanding/analyzers/"
            "rubricVoice12345678?api-version=2025-11-01",
        ]

    @pytest.mark.asyncio
    async def test_model_exists_conflict_raises_instead_of_reusing(self):
        """A 409 is not a usable analyzer and must be surfaced to the caller."""

        class FakeResponse:
            status_code = 409
            text = '{"error":{"code":"ModelExists"}}'
            headers = {}

        class FakeClient:
            def __init__(self, timeout: float) -> None:
                self.timeout = timeout

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

            async def put(self, url, headers, json):
                return FakeResponse()

        with (
            patch(
                "app.services.cu_evaluation_service._get_auth_headers",
                AsyncMock(return_value={}),
            ),
            patch("app.services.cu_evaluation_service.httpx.AsyncClient", FakeClient),
            patch(
                "app.services.cu_evaluation_service._get_cu_api_version",
                return_value="2025-11-01",
            ),
        ):
            with pytest.raises(RuntimeError, match="CU analyzer creation failed: HTTP 409"):
                await _put_analyzer(
                    "https://example.cognitiveservices.azure.com",
                    "",
                    "rubricVoice12345678",
                    {"name": "VoiceScoring", "fields": {}},
                    "voice",
                )


class TestCuPollingBranches:
    class Response:
        def __init__(self, status_code=200, body=None, text="error"):
            self.status_code = status_code
            self.body = body or {}
            self.text = text

        def json(self):
            return self.body

    async def test_operation_poll_http_failure_and_terminal_failure(self):
        client = AsyncMock()
        client.get.return_value = self.Response(status_code=500)
        with patch("app.services.cu_evaluation_service.asyncio.sleep", AsyncMock()):
            with pytest.raises(RuntimeError, match="poll failed"):
                await _poll_analyzer_operation(client, "operation", {}, "analyzer")

        client.get.return_value = self.Response(
            body={"status": "Failed", "error": {"message": "bad analyzer"}}
        )
        with patch("app.services.cu_evaluation_service.asyncio.sleep", AsyncMock()):
            with pytest.raises(RuntimeError, match="bad analyzer"):
                await _poll_analyzer_operation(client, "operation", {}, "analyzer")

    async def test_operation_and_result_poll_timeouts(self):
        client = AsyncMock()
        client.get.return_value = self.Response(body={"status": "running"})
        with (
            patch("app.services.cu_evaluation_service.MAX_POLL_ATTEMPTS", 1),
            patch("app.services.cu_evaluation_service.asyncio.sleep", AsyncMock()),
        ):
            with pytest.raises(RuntimeError, match="operation timed out"):
                await _poll_analyzer_operation(client, "operation", {}, "analyzer")
            with pytest.raises(RuntimeError, match="analysis timed out"):
                await _poll_result(client, "operation", {})

    async def test_readiness_not_found_failure_error_and_timeout(self):
        client = AsyncMock()
        with (
            patch("app.services.cu_evaluation_service.MAX_POLL_ATTEMPTS", 1),
            patch("app.services.cu_evaluation_service.asyncio.sleep", AsyncMock()),
        ):
            client.get.return_value = self.Response(status_code=404)
            with pytest.raises(RuntimeError, match="was not ready"):
                await _wait_for_analyzer_ready(client, "url", {}, "analyzer")

            client.get.return_value = self.Response(status_code=500)
            with pytest.raises(RuntimeError, match="readiness check failed"):
                await _wait_for_analyzer_ready(client, "url", {}, "analyzer")

            client.get.return_value = self.Response(body={"status": "failed"})
            with pytest.raises(RuntimeError, match="is failed"):
                await _wait_for_analyzer_ready(client, "url", {}, "analyzer")

            client.get.return_value = self.Response(body={"status": "creating"})
            with pytest.raises(RuntimeError, match="was not ready"):
                await _wait_for_analyzer_ready(client, "url", {}, "analyzer")

    async def test_poll_result_failure_and_fields_without_contents(self):
        client = AsyncMock()
        client.get.return_value = self.Response(
            body={"status": "cancelled", "error": {"message": "cancelled by user"}}
        )
        with patch("app.services.cu_evaluation_service.asyncio.sleep", AsyncMock()):
            with pytest.raises(RuntimeError, match="cancelled by user"):
                await _poll_result(client, "operation", {"Content-Type": "application/json"})

        client.get.return_value = self.Response(
            body={"status": "Succeeded", "result": {"fields": {"score": 9}}}
        )
        with patch("app.services.cu_evaluation_service.asyncio.sleep", AsyncMock()):
            assert await _poll_result(client, "operation", {}) == {"score": 9}


class TestRubricAnalyzerSync:
    async def test_skips_without_endpoint(self):
        db = AsyncMock()
        rubric = SimpleNamespace(id="12345678-rest")
        with (
            patch(
                "app.services.cu_evaluation_service.config_service.get_effective_endpoint",
                AsyncMock(return_value=""),
            ),
            patch(
                "app.services.cu_evaluation_service.config_service.get_effective_key",
                AsyncMock(return_value=""),
            ),
            patch("app.services.cu_evaluation_service._put_analyzer", AsyncMock()) as put,
        ):
            await sync_rubric_analyzers(db, rubric)
        put.assert_not_awaited()
        db.flush.assert_not_awaited()

    async def test_syncs_voice_analyzer_and_flushes(self):
        db = AsyncMock()
        rubric = SimpleNamespace(
            id="12345678-abcd", cu_content_analyzer_id="old", cu_voice_analyzer_id=None
        )
        with (
            patch(
                "app.services.cu_evaluation_service.config_service.get_effective_endpoint",
                AsyncMock(return_value="https://endpoint/"),
            ),
            patch(
                "app.services.cu_evaluation_service.config_service.get_effective_key",
                AsyncMock(return_value="key"),
            ),
            patch("app.services.cu_evaluation_service._put_analyzer", AsyncMock()) as put,
        ):
            await sync_rubric_analyzers(db, rubric)
        put.assert_awaited_once()
        assert put.await_args.args[0] == "https://endpoint"
        assert rubric.cu_content_analyzer_id is None
        assert rubric.cu_voice_analyzer_id == "rubricVoice12345678"
        db.flush.assert_awaited_once()

    async def test_session_rubric_missing_and_found(self):
        db = AsyncMock()
        assert await _get_session_rubric(db, SimpleNamespace(rubric_id=None)) is None
        rubric = object()
        result = MagicMock()
        result.scalar_one_or_none.return_value = rubric
        db.execute.return_value = result
        assert await _get_session_rubric(db, SimpleNamespace(rubric_id="rubric")) is rubric


class TestScoreVoiceWithCu:
    """Test voice scoring submission payloads."""

    @pytest.mark.asyncio
    async def test_audio_data_is_submitted_as_base64(self):
        captured_body = {}

        class FakePostResponse:
            status_code = 202
            headers = {"Operation-Location": "https://example.test/operations/1"}
            text = ""

        class FakeGetResponse:
            def json(self):
                return {
                    "status": "Succeeded",
                    "result": {"contents": [{"fields": {"transcript": {"valueString": "hi"}}}]},
                }

        class FakeClient:
            def __init__(self, timeout: float) -> None:
                self.timeout = timeout

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

            async def post(self, url, headers, json):
                captured_body.update(json)
                return FakePostResponse()

            async def get(self, url, headers):
                return FakeGetResponse()

        with (
            patch(
                "app.services.cu_evaluation_service._get_auth_headers",
                AsyncMock(return_value={}),
            ),
            patch("app.services.cu_evaluation_service.httpx.AsyncClient", FakeClient),
            patch("app.services.cu_evaluation_service.asyncio.sleep", AsyncMock()),
            patch(
                "app.services.cu_evaluation_service._get_cu_api_version",
                return_value="2025-11-01",
            ),
        ):
            result = await score_voice_with_cu(
                "https://example.services.ai.azure.com",
                "",
                "rubricVoice12345678",
                "https://storage.blob.core.windows.net/audio.webm",
                audio_data=b"audio-bytes",
            )

        assert captured_body == {"inputs": [{"data": "YXVkaW8tYnl0ZXM=", "mimeType": "audio/webm"}]}
        assert result == {"transcript": {"valueString": "hi"}}

    @pytest.mark.parametrize(
        ("post_status", "operation_location", "message"),
        [(500, "operation", "submission failed"), (202, "", "No Operation-Location")],
    )
    async def test_submission_response_errors(self, post_status, operation_location, message):
        response = MagicMock(
            status_code=post_status,
            headers={"Operation-Location": operation_location},
            text="failure",
        )
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.return_value = response
        with (
            patch(
                "app.services.cu_evaluation_service._get_auth_headers", AsyncMock(return_value={})
            ),
            patch("app.services.cu_evaluation_service.httpx.AsyncClient", return_value=client),
        ):
            with pytest.raises(RuntimeError, match=message):
                await score_voice_with_cu("https://endpoint/", "", "analyzer", "https://audio")

    async def test_url_and_local_file_inputs(self, tmp_path):
        captured = []
        response = MagicMock(
            status_code=202,
            headers={"Operation-Location": "operation"},
            text="",
        )
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.return_value = response

        async def capture(_client, _operation, _headers):
            captured.append(client.post.await_args.kwargs["json"])
            return {}

        audio = tmp_path / "audio.mp3"
        audio.write_bytes(b"local")
        with (
            patch(
                "app.services.cu_evaluation_service._get_auth_headers", AsyncMock(return_value={})
            ),
            patch("app.services.cu_evaluation_service.httpx.AsyncClient", return_value=client),
            patch("app.services.cu_evaluation_service._poll_result", side_effect=capture),
        ):
            await score_voice_with_cu("https://endpoint", "", "analyzer", "https://audio/file.wav")
            await score_voice_with_cu("https://endpoint", "", "analyzer", str(audio))

            with pytest.raises(RuntimeError, match="Failed to read local"):
                await score_voice_with_cu(
                    "https://endpoint", "", "analyzer", str(tmp_path / "missing")
                )

        assert captured[0] == {"inputs": [{"url": "https://audio/file.wav"}]}
        assert captured[1]["inputs"][0]["mimeType"] == "audio/mpeg"

    @pytest.mark.asyncio
    async def test_audio_data_uses_stable_inputs_shape_when_binary_requested(self):
        captured = {}

        class FakePostResponse:
            status_code = 202
            headers = {"Operation-Location": "https://example.test/operations/1"}
            text = ""

        class FakeGetResponse:
            def json(self):
                return {
                    "status": "Succeeded",
                    "result": {"contents": [{"fields": {"transcript": {"valueString": "hi"}}}]},
                }

        class FakeClient:
            def __init__(self, timeout: float) -> None:
                self.timeout = timeout

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

            async def post(self, url, headers, json):
                captured["url"] = url
                captured["headers"] = headers
                captured["body"] = json
                return FakePostResponse()

            async def get(self, url, headers):
                return FakeGetResponse()

        with (
            patch(
                "app.services.cu_evaluation_service._get_auth_headers",
                AsyncMock(return_value={"Content-Type": "application/json"}),
            ),
            patch("app.services.cu_evaluation_service.httpx.AsyncClient", FakeClient),
            patch("app.services.cu_evaluation_service.asyncio.sleep", AsyncMock()),
        ):
            result = await score_voice_with_cu(
                "https://example.services.ai.azure.com",
                "",
                "rubricVoice12345678",
                "https://storage.blob.core.windows.net/audio.webm",
                audio_data=b"wav-bytes",
                mime_type="audio/wav",
                use_binary_upload=True,
            )

        assert captured["url"].endswith(
            "/contentunderstanding/analyzers/rubricVoice12345678:analyze?api-version=2025-11-01"
        )
        assert captured["headers"]["Content-Type"] == "application/json"
        assert captured["body"] == {"inputs": [{"data": "d2F2LWJ5dGVz", "mimeType": "audio/wav"}]}
        assert result == {"transcript": {"valueString": "hi"}}


class TestMergeScores:
    """Test score merging logic (D-11)."""

    def test_text_only_session(self):
        content_scores = {
            "dimensions": [
                {"name": "Knowledge", "score": 80, "weight": 50},
                {"name": "Communication", "score": 70, "weight": 50},
            ],
            "feedback_summary": "Good performance",
        }
        result = merge_scores(content_scores, None, 60, 40)

        assert result["voice_total"] is None
        assert result["content_total"] == 75.0
        assert result["overall_score"] == 75.0
        assert result["feedback_summary"] == "Good performance"

    def test_voice_session_weighted_merge(self):
        content_scores = {
            "dimensions": [
                {"name": "Knowledge", "score": 80, "weight": 60},
                {"name": "Communication", "score": 60, "weight": 40},
            ],
            "feedback_summary": "Content feedback",
        }
        voice_scores = {
            "dimensions": [
                {"name": "Fluency", "score": 90, "weight": 50},
                {"name": "Tone", "score": 70, "weight": 50},
            ],
            "feedback_summary": "Voice feedback",
        }
        result = merge_scores(content_scores, voice_scores, 60, 40)

        assert result["content_total"] == 72.0
        assert result["voice_total"] == 80.0
        assert result["overall_score"] == 75.2
        assert "Voice: Voice feedback" in result["feedback_summary"]

    def test_zero_weights_fallback(self):
        content_scores = {
            "dimensions": [{"name": "X", "score": 50, "weight": 100}],
            "feedback_summary": "",
        }
        voice_scores = {
            "dimensions": [{"name": "Y", "score": 80, "weight": 100}],
            "feedback_summary": "",
        }
        result = merge_scores(content_scores, voice_scores, 0, 0)
        assert result["overall_score"] == 0.0

    def test_empty_dimensions(self):
        content_scores = {"dimensions": [], "feedback_summary": "No data"}
        result = merge_scores(content_scores, None, 60, 40)
        assert result["content_total"] == 0.0
        assert result["overall_score"] == 0.0

    def test_unweighted_dimensions_use_arithmetic_mean(self):
        assert _calculate_weighted_total([{"score": 50}, {"score": 100}]) == 75


class TestCuValueHelpers:
    def test_mime_type_and_nested_value_variants(self):
        assert _mime_type_for_audio_path("https://host/audio.WAV?token=x") == "audio/wav"
        assert _mime_type_for_audio_path("unknown") == "application/octet-stream"
        assert _extract_cu_field_value("plain") == "plain"
        assert _extract_cu_field_value({"valueArray": [{"valueString": "1"}]}) == [1]
        assert _extract_cu_field_value({"valueString": "not-json"}) == "not-json"
        assert _extract_cu_field_value({"content": "[1, 2]"}) == [1, 2]
        assert _extract_cu_field_value({"content": 3}) == 3

    @pytest.mark.parametrize(
        ("value", "expected"),
        [(True, 0), (None, 0), (5, 5), (2.5, 2.5), ("3.5", 3.5), ("bad", 0), ([], 0)],
    )
    def test_score_coercion(self, value, expected):
        assert _coerce_score(value) == expected


class TestParseCuVoiceResult:
    """Test CU voice result parsing."""

    def test_parse_voice_dimensions(self):
        cu_fields = {
            "fluency": {"valueString": '{"score": 90, "feedback": "Smooth"}'},
            "tone": {"valueString": '{"score": 75, "feedback": "Professional"}'},
            "feedback_summary": {"valueString": "Good voice quality"},
            "transcript": {"valueString": "Hello world"},
        }
        result = _parse_cu_voice_result(cu_fields)

        assert len(result["dimensions"]) == 2
        names = [d["name"] for d in result["dimensions"]]
        assert "fluency" in names
        assert "tone" in names
        assert result["feedback_summary"] == "Good voice quality"

    def test_excludes_non_score_fields(self):
        cu_fields = {
            "feedback_summary": {"valueString": "Summary"},
            "transcript": {"valueString": "Some text"},
            "fluency": {"valueString": '{"score": 80, "feedback": "OK"}'},
        }
        result = _parse_cu_voice_result(cu_fields)
        assert len(result["dimensions"]) == 1

    def test_empty_fields(self):
        result = _parse_cu_voice_result({})
        assert result["dimensions"] == []
        assert result["feedback_summary"] == ""

    def test_parse_voice_dimension_from_value_object(self):
        cu_fields = {
            "fluency": {
                "type": "object",
                "valueObject": {
                    "score": {"type": "string", "valueString": "88"},
                    "feedback": {"type": "string", "valueString": "Clear and smooth"},
                },
            },
            "feedback_summary": {"valueString": "Strong voice delivery"},
        }

        result = _parse_cu_voice_result(cu_fields)

        assert result["dimensions"] == [
            {
                "name": "fluency",
                "score": 88.0,
                "weight": 25,
                "feedback": "Clear and smooth",
            }
        ]
        assert result["feedback_summary"] == "Strong voice delivery"

    def test_parse_voice_dimension_from_content_json(self):
        cu_fields = {
            "tone": {
                "type": "string",
                "content": '{"score": 76, "feedback": "Professional tone"}',
            }
        }

        result = _parse_cu_voice_result(cu_fields)

        assert result["dimensions"] == [
            {
                "name": "tone",
                "score": 76,
                "weight": 25,
                "feedback": "Professional tone",
            }
        ]
