"""Unit tests for conference_service: session creation, questions, respond, end."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.models.conference import ConferenceAudienceHcp
from app.models.hcp_profile import HcpProfile
from app.models.message import SessionMessage
from app.models.scenario import Scenario
from app.models.user import User
from app.models.voice_live_instance import VoiceLiveInstance
from app.services.agents.base import CoachEvent, CoachEventType
from app.services.auth import get_password_hash
from app.services.conference_service import (
    _compute_relevance_score,
    _serialize_queue,
    _strip_speaker_prefix,
    create_conference_session,
    end_conference_session,
    generate_hcp_questions,
    score_conference_session_background,
    transition_sub_state,
)
from app.services.turn_manager import QueuedQuestion, TurnManager
from app.utils.exceptions import AppException, NotFoundException
from tests.conftest import TestSessionLocal


@pytest.mark.parametrize(
    ("text", "speaker_name", "expected"),
    [
        (
            "张维：谢谢您的回答。您能具体说明推荐依据吗？",
            "Dr. Zhang Wei (张维)",
            "谢谢您的回答。您能具体说明推荐依据吗？",
        ),
        (
            "Dr. Zhang Wei: Could you clarify the evidence?",
            "Dr. Zhang Wei (张维)",
            "Could you clarify the evidence?",
        ),
        (
            "Could you clarify the evidence?",
            "Dr. Zhang Wei (张维)",
            "Could you clarify the evidence?",
        ),
    ],
)
def test_strip_speaker_prefix(text: str, speaker_name: str, expected: str):
    assert _strip_speaker_prefix(text, speaker_name) == expected


async def _seed_conference_fixture(
    session, *, mode="conference", audience_count=3, roles=None
) -> dict:
    """Create User, HcpProfiles, Scenario, and ConferenceAudienceHcp records."""
    user = User(
        username="conf-svc-user",
        email="confsvc@test.com",
        hashed_password=get_password_hash("pass"),
        full_name="Conference Tester",
        role="user",
    )
    session.add(user)
    await session.flush()

    hcps = []
    for i in range(audience_count):
        hcp = HcpProfile(
            name=f"Dr. HCP-{i}",
            specialty="Oncology",
            personality_type="analytical",
            voice_name=f"zh-CN-TestVoice{i}Neural",
            created_by=user.id,
        )
        session.add(hcp)
        hcps.append(hcp)
    await session.flush()

    scenario = Scenario(
        name="Conference Test Scenario",
        mode=mode,
        hcp_profile_id=hcps[0].id,
        created_by=user.id,
        key_messages=json.dumps(["Safety profile", "Efficacy data"]),
        skill_id="test-skill-id",
        description="Cancer treatment data presentation",
        rubric_id="test-rubric-id",
    )
    session.add(scenario)
    await session.flush()

    audience_hcps = []
    for i, hcp in enumerate(hcps):
        role = roles[i] if roles and i < len(roles) else "audience"
        ah = ConferenceAudienceHcp(
            scenario_id=scenario.id,
            hcp_profile_id=hcp.id,
            role_in_conference=role,
            voice_id=f"voice-{i}",
            sort_order=i,
        )
        session.add(ah)
        audience_hcps.append(ah)
    await session.flush()

    return {
        "user": user,
        "hcps": hcps,
        "scenario": scenario,
        "audience_hcps": audience_hcps,
    }


class TestCreateConferenceSession:
    """Tests for create_conference_session service function."""

    async def test_success(self):
        """Creates session with conference fields populated."""
        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db)
            session = await create_conference_session(db, data["scenario"].id, data["user"].id)
            assert session.session_type == "conference"
            assert session.sub_state == "presenting"
            assert session.status == "created"
            # audience_config should be populated JSON
            config = json.loads(session.audience_config)
            assert len(config) == 3
            assert config[0]["name"] == "Dr. HCP-0"
            assert config[0]["voice_name"] == "zh-CN-TestVoice0Neural"
            assert config[0]["speaker_priority"] == "primary"
            assert config[0]["voice_live_enabled"] is True
            assert config[0]["avatar_enabled"] is True
            assert config[0]["avatar_character"]
            assert config[0]["avatar_style"]
            assert config[1]["speaker_priority"] == "secondary"
            assert "conference_prompt_config" in config[0]

    async def test_audience_config_prefers_voice_live_instance_voice(self):
        """Snapshots Voice Live instance voice before deprecated inline profile voice."""
        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db)
            voice_instance = VoiceLiveInstance(
                name="中文男声",
                voice_name="zh-CN-YunjianNeural",
                avatar_character="jeff",
                avatar_style="formal",
                created_by=data["user"].id,
            )
            db.add(voice_instance)
            await db.flush()

            data["hcps"][0].voice_name = "zh-CN-XiaoxiaoNeural"
            data["hcps"][0].voice_live_instance_id = voice_instance.id
            await db.flush()

            session = await create_conference_session(db, data["scenario"].id, data["user"].id)
            config = json.loads(session.audience_config)

            assert config[0]["voice_live_instance_id"] == voice_instance.id
            assert config[0]["voice_name"] == "zh-CN-YunjianNeural"
            assert config[0]["avatar_character"] == "jeff"
            assert config[0]["avatar_style"] == "formal"

    async def test_custom_conference_prompt_config_is_snapshotted(self):
        """Creates session with scenario-level conference prompt config."""
        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db, roles=["moderator", "audience", "audience"])
            custom_config = {
                "speaker_order_policy": "Dr. HCP-1 asks first as primary; others are secondary.",
                "moderator_remarks": {"invite": {"zh": "自定义开场", "en": "Custom invite"}},
                "audience_prompt_template": "{hcp_name}|{speaker_priority}|{speaker_order_policy}",
            }
            data["scenario"].conference_prompt_config = json.dumps(custom_config)
            await db.flush()

            session = await create_conference_session(db, data["scenario"].id, data["user"].id)
            config = json.loads(session.audience_config)

            invite_remark = config[0]["conference_prompt_config"]["moderator_remarks"]["invite"][
                "zh"
            ]
            assert invite_remark == "自定义开场"
            assert config[1]["speaker_order_policy"] == custom_config["speaker_order_policy"]

    async def test_non_conference_scenario_raises_409(self):
        """Scenario with mode='f2f' raises 409."""
        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db, mode="f2f")
            with pytest.raises(AppException) as exc:
                await create_conference_session(db, data["scenario"].id, data["user"].id)
            assert exc.value.status_code == 409
            assert exc.value.code == "NOT_CONFERENCE_SCENARIO"

    async def test_insufficient_audience_raises_409(self):
        """Scenario with fewer than 2 audience HCPs raises 409."""
        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db, audience_count=1)
            with pytest.raises(AppException) as exc:
                await create_conference_session(db, data["scenario"].id, data["user"].id)
            assert exc.value.status_code == 409
            assert exc.value.code == "INSUFFICIENT_AUDIENCE"

    async def test_missing_scenario_raises_404(self):
        """Non-existent scenario raises NotFoundException."""
        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db)
            with pytest.raises(NotFoundException):
                await create_conference_session(db, "non-existent-id", data["user"].id)


class TestTransitionSubState:
    """Tests for transition_sub_state service function."""

    async def test_transition_to_qa(self):
        """Sub-state transitions from 'presenting' to 'qa'."""
        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db)
            session = await create_conference_session(db, data["scenario"].id, data["user"].id)
            assert session.sub_state == "presenting"

            await transition_sub_state(db, session.id, "qa")
            await db.refresh(session)
            assert session.sub_state == "qa"

    async def test_missing_session_raises_404(self):
        """Non-existent session raises NotFoundException."""
        async with TestSessionLocal() as db:
            await _seed_conference_fixture(db)
            with pytest.raises(NotFoundException):
                await transition_sub_state(db, "no-session", "qa")


class TestEndConferenceSession:
    """Tests for end_conference_session service function."""

    @patch("app.services.conference_service.turn_manager")
    async def test_end_sets_completed(self, mock_tm):
        """Ending session sets status='completed' and cleans up turn_manager."""
        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db)
            session = await create_conference_session(db, data["scenario"].id, data["user"].id)
            # Set started_at so duration can be calculated
            session.started_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
            session.status = "in_progress"
            await db.flush()

            with patch(
                "app.services.scoring_service.score_session", new_callable=AsyncMock
            ) as score:
                result = await end_conference_session(db, session.id, data["user"].id)
            assert result.status == "completed"
            assert result.completed_at is not None
            mock_tm.cleanup_session.assert_called_once_with(session.id)
            score.assert_not_awaited()

    async def test_end_wrong_user_raises_403(self):
        """Ending session with wrong user raises 403."""
        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db)
            session = await create_conference_session(db, data["scenario"].id, data["user"].id)
            with pytest.raises(AppException) as exc:
                await end_conference_session(db, session.id, "wrong-user-id")
            assert exc.value.status_code == 403

    async def test_end_already_completed_raises_409(self):
        """Ending an already-completed session raises 409."""
        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db)
            session = await create_conference_session(db, data["scenario"].id, data["user"].id)
            session.status = "completed"
            await db.flush()

            with pytest.raises(AppException) as exc:
                await end_conference_session(db, session.id, data["user"].id)
            assert exc.value.status_code == 409

    async def test_end_nonexistent_session_raises_404(self):
        """Ending non-existent session raises NotFoundException."""
        async with TestSessionLocal() as db:
            await _seed_conference_fixture(db)
            with pytest.raises(NotFoundException):
                await end_conference_session(db, "no-id", "user-id")


class TestGenerateHcpQuestions:
    """Tests for generate_hcp_questions with mocked LLM adapter."""

    async def test_generates_questions_from_llm(self):
        """Mock LLM generates questions that are added to turn_manager."""
        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db)
            session = await create_conference_session(db, data["scenario"].id, data["user"].id)

            # Create mock adapter that returns question text
            mock_adapter = MagicMock()

            async def mock_execute(request):
                yield CoachEvent(
                    type=CoachEventType.TEXT,
                    content="What about side effects?",
                )
                yield CoachEvent(type=CoachEventType.DONE, content="")

            mock_adapter.execute = mock_execute

            # Patch both the registry and turn_manager
            fresh_tm = TurnManager()
            with (
                patch("app.services.conference_service.registry") as mock_registry,
                patch(
                    "app.services.conference_service.turn_manager",
                    fresh_tm,
                ),
            ):
                mock_registry.get.return_value = mock_adapter
                questions = await generate_hcp_questions(
                    db, session, "Our drug shows great efficacy"
                )

            assert len(questions) == 3  # one per HCP
            for q in questions:
                assert q.question == "What about side effects?"
                assert q.status == "waiting"

    async def test_empty_audience_returns_empty(self):
        """Session with empty audience_config returns no questions."""
        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db)
            session = await create_conference_session(db, data["scenario"].id, data["user"].id)
            session.audience_config = "[]"
            await db.flush()

            questions = await generate_hcp_questions(db, session, "Some text")
            assert questions == []

    async def test_skips_empty_questions(self):
        """Questions that are empty or 'no question' are skipped."""
        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db)
            session = await create_conference_session(db, data["scenario"].id, data["user"].id)

            mock_adapter = MagicMock()

            async def mock_execute(request):
                yield CoachEvent(type=CoachEventType.TEXT, content="no question")
                yield CoachEvent(type=CoachEventType.DONE, content="")

            mock_adapter.execute = mock_execute

            fresh_tm = TurnManager()
            with (
                patch("app.services.conference_service.registry") as mock_registry,
                patch(
                    "app.services.conference_service.turn_manager",
                    fresh_tm,
                ),
            ):
                mock_registry.get.return_value = mock_adapter
                questions = await generate_hcp_questions(db, session, "Our drug data")

            assert len(questions) == 0

    async def test_skips_quote_only_questions(self):
        """Quote-only model outputs are treated as empty questions."""
        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db)
            session = await create_conference_session(db, data["scenario"].id, data["user"].id)

            mock_adapter = MagicMock()

            async def mock_execute(request):
                yield CoachEvent(type=CoachEventType.TEXT, content='"')
                yield CoachEvent(type=CoachEventType.DONE, content="")

            mock_adapter.execute = mock_execute

            fresh_tm = TurnManager()
            with (
                patch("app.services.conference_service.registry") as mock_registry,
                patch("app.services.conference_service.turn_manager", fresh_tm),
            ):
                mock_registry.get.return_value = mock_adapter
                questions = await generate_hcp_questions(db, session, "Our drug data")

            assert questions == []


class TestRunPresentationRound:
    """Tests for run_presentation_round sequential speaker orchestration."""

    @staticmethod
    def _mock_adapter(content: str = "What about efficacy?") -> MagicMock:
        adapter = MagicMock()

        async def mock_execute(request):
            yield CoachEvent(type=CoachEventType.TEXT, content=content)
            yield CoachEvent(type=CoachEventType.DONE, content="")

        adapter.execute = mock_execute
        return adapter

    async def _run(self, db, session, mr_text: str) -> list[dict]:
        from app.services.conference_service import run_presentation_round

        fresh_tm = TurnManager()
        events: list[dict] = []
        with (
            patch("app.services.conference_service.registry") as mock_registry,
            patch("app.services.conference_service.turn_manager", fresh_tm),
        ):
            mock_registry.get.return_value = self._mock_adapter()
            async for ev in run_presentation_round(db, session, mr_text):
                events.append(ev)
        return events

    async def test_start_conference_invites_presentation(self, monkeypatch):
        """Start phase emits only a moderator invitation before the MR presents."""
        monkeypatch.setattr("app.services.conference_service.SPEAKER_PACING_SECONDS", 0)
        from app.services.conference_service import start_conference_round

        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db, roles=["moderator", "audience", "audience"])
            session = await create_conference_session(db, data["scenario"].id, data["user"].id)

            events = []
            async for event in start_conference_round(db, session):
                events.append(event)

            speaker_events = [json.loads(e["data"]) for e in events if e["event"] == "speaker_text"]
            assert len(speaker_events) == 1
            assert speaker_events[0]["speaker_name"] == "Dr. HCP-0"
            assert "请先进行你的主题演讲" in speaker_events[0]["content"]
            assert not any(e["event"] == "queue_update" for e in events)

    async def test_start_conference_uses_custom_moderator_invite(self, monkeypatch):
        """Start phase uses configured moderator remarks from the session snapshot."""
        monkeypatch.setattr("app.services.conference_service.SPEAKER_PACING_SECONDS", 0)
        from app.services.conference_service import start_conference_round

        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db, roles=["moderator", "audience", "audience"])
            data["scenario"].conference_prompt_config = json.dumps(
                {"moderator_remarks": {"invite": {"zh": "请主讲人先发言", "en": "Please present"}}}
            )
            await db.flush()
            session = await create_conference_session(db, data["scenario"].id, data["user"].id)

            events = []
            async for event in start_conference_round(db, session):
                events.append(event)

            speaker_events = [json.loads(e["data"]) for e in events if e["event"] == "speaker_text"]
            assert speaker_events[0]["content"] == "请主讲人先发言"

    async def test_present_opens_and_releases_only_first_hcp(self, monkeypatch):
        """Present phase emits moderator opening and the first HCP question only."""
        monkeypatch.setattr("app.services.conference_service.SPEAKER_PACING_SECONDS", 0)
        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db, roles=["moderator", "audience", "audience"])
            session = await create_conference_session(db, data["scenario"].id, data["user"].id)

            events = await self._run(db, session, "我们的药物数据展示")

            speaker_events = [json.loads(e["data"]) for e in events if e["event"] == "speaker_text"]
            # Moderator opening + first audience question only.
            assert len(speaker_events) == 2
            assert speaker_events[0]["speaker_name"] == "Dr. HCP-0"
            assert "问答环节" in speaker_events[0]["content"]
            assert speaker_events[1]["speaker_name"] == "Dr. HCP-1"

    async def test_moderator_opening_does_not_skip_first_hcp(self, monkeypatch):
        """Moderator messages do not count as released audience HCP questions."""
        monkeypatch.setattr("app.services.conference_service.SPEAKER_PACING_SECONDS", 0)
        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db, roles=["moderator", "audience", "audience"])
            session = await create_conference_session(db, data["scenario"].id, data["user"].id)

            events = await self._run(db, session, "我们的药物数据展示")

            queue_updates = [e for e in events if e["event"] == "queue_update"]
            queue = json.loads(queue_updates[0]["data"])
            assert queue[0]["hcp_name"] == "Dr. HCP-1"
            assert queue[0]["status"] == "active"

    async def test_empty_model_output_falls_back_to_hcp_question(self, monkeypatch):
        """The presentation round does not close immediately when the LLM returns empty text."""
        monkeypatch.setattr("app.services.conference_service.SPEAKER_PACING_SECONDS", 0)

        mock_adapter = MagicMock()

        async def mock_execute(request):
            yield CoachEvent(type=CoachEventType.TEXT, content="no question")
            yield CoachEvent(type=CoachEventType.DONE, content="")

        mock_adapter.execute = mock_execute

        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db, roles=["moderator", "audience", "audience"])
            session = await create_conference_session(db, data["scenario"].id, data["user"].id)

            fresh_tm = TurnManager()
            events = []
            with (
                patch("app.services.conference_service.registry") as mock_registry,
                patch("app.services.conference_service.turn_manager", fresh_tm),
            ):
                mock_registry.get.return_value = mock_adapter
                from app.services.conference_service import run_presentation_round

                async for event in run_presentation_round(db, session, "我想聊聊泽布替尼"):
                    events.append(event)

            speaker_events = [json.loads(e["data"]) for e in events if e["event"] == "speaker_text"]
            assert len(speaker_events) == 2
            assert speaker_events[1]["speaker_name"] == "Dr. HCP-1"
            assert "临床价值" in speaker_events[1]["content"]
            assert not any("到此结束" in e["content"] for e in speaker_events)

    async def test_no_moderator_skips_remarks(self, monkeypatch):
        """Without a moderator, only the first audience HCP is released on present."""
        monkeypatch.setattr("app.services.conference_service.SPEAKER_PACING_SECONDS", 0)
        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db)  # all audience
            session = await create_conference_session(db, data["scenario"].id, data["user"].id)

            events = await self._run(db, session, "Our drug efficacy data")

            speaker_events = [json.loads(e["data"]) for e in events if e["event"] == "speaker_text"]
            assert len(speaker_events) == 1
            assert speaker_events[0]["speaker_name"] == "Dr. HCP-0"

    async def test_emits_queue_update_after_speakers(self, monkeypatch):
        """Queue exposes only the active HCP after their question is emitted."""
        monkeypatch.setattr("app.services.conference_service.SPEAKER_PACING_SECONDS", 0)
        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db, roles=["moderator", "audience", "audience"])
            session = await create_conference_session(db, data["scenario"].id, data["user"].id)

            events = await self._run(db, session, "我们的数据")

            queue_updates = [e for e in events if e["event"] == "queue_update"]
            assert len(queue_updates) == 1
            queue = json.loads(queue_updates[0]["data"])
            assert len(queue) == 1
            assert queue[0]["hcp_name"] == "Dr. HCP-1"
            assert queue[0]["status"] == "active"

    async def test_generate_questions_skips_moderator(self, monkeypatch):
        """generate_hcp_questions excludes moderator-role HCPs."""
        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db, roles=["moderator", "audience", "audience"])
            session = await create_conference_session(db, data["scenario"].id, data["user"].id)

            fresh_tm = TurnManager()
            with (
                patch("app.services.conference_service.registry") as mock_registry,
                patch("app.services.conference_service.turn_manager", fresh_tm),
            ):
                mock_registry.get.return_value = self._mock_adapter()
                questions = await generate_hcp_questions(db, session, "Our drug data")

            assert len(questions) == 2
            assert all(q.hcp_name != "Dr. HCP-0" for q in questions)

    async def test_respond_keeps_current_hcp_until_followup_is_answered(self, monkeypatch):
        """Answering an initial HCP question emits only that HCP follow-up."""
        monkeypatch.setattr("app.services.conference_service.SPEAKER_PACING_SECONDS", 0)
        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db, roles=["moderator", "audience", "audience"])
            session = await create_conference_session(db, data["scenario"].id, data["user"].id)

            from app.services.conference_service import handle_respond, run_presentation_round

            fresh_tm = TurnManager()
            with (
                patch("app.services.conference_service.registry") as mock_registry,
                patch("app.services.conference_service.turn_manager", fresh_tm),
            ):
                mock_registry.get.return_value = self._mock_adapter("Question from HCP")
                async for _ in run_presentation_round(db, session, "我们的药物数据展示"):
                    pass

                first_hcp = data["hcps"][1].id
                events_first: list[dict] = []
                async for event in handle_respond(db, session, first_hcp, "我的回答 1"):
                    events_first.append(event)

                first_speakers = [
                    json.loads(e["data"]) for e in events_first if e["event"] == "speaker_text"
                ]
                assert any(s["speaker_name"] == "Dr. HCP-1" for s in first_speakers)
                assert not any(s["speaker_name"] == "Dr. HCP-2" for s in first_speakers)
                assert all("结束" not in s["content"] for s in first_speakers)

    async def test_active_hcp_continues_following_up_before_next_hcp(self, monkeypatch):
        """The current HCP follows up for multiple turns before another HCP speaks."""
        monkeypatch.setattr("app.services.conference_service.SPEAKER_PACING_SECONDS", 0)
        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db, roles=["moderator", "audience", "audience"])
            session = await create_conference_session(db, data["scenario"].id, data["user"].id)

            from app.services.conference_service import handle_respond, run_presentation_round

            fresh_tm = TurnManager()
            with (
                patch("app.services.conference_service.registry") as mock_registry,
                patch("app.services.conference_service.turn_manager", fresh_tm),
            ):
                mock_registry.get.return_value = self._mock_adapter("Question from HCP")
                async for _ in run_presentation_round(db, session, "我们的药物数据展示"):
                    pass

                first_hcp = data["hcps"][1].id
                async for _ in handle_respond(db, session, first_hcp, "我的回答 1"):
                    pass

                events_next: list[dict] = []
                async for event in handle_respond(db, session, first_hcp, "我的回答 2"):
                    events_next.append(event)

                next_speakers = [
                    json.loads(e["data"]) for e in events_next if e["event"] == "speaker_text"
                ]
                assert any(s["speaker_name"] == "Dr. HCP-1" for s in next_speakers)
                assert not any(s["speaker_name"] == "Dr. HCP-2" for s in next_speakers)

    async def test_active_hcp_moves_next_after_mr_answers_final_followup(self, monkeypatch):
        """After the follow-up limit, the next HCP waits until the MR replies."""
        monkeypatch.setattr("app.services.conference_service.SPEAKER_PACING_SECONDS", 0)
        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db, roles=["moderator", "audience", "audience"])
            session = await create_conference_session(db, data["scenario"].id, data["user"].id)

            from app.services.conference_service import handle_respond, run_presentation_round

            fresh_tm = TurnManager()
            with (
                patch("app.services.conference_service.registry") as mock_registry,
                patch("app.services.conference_service.turn_manager", fresh_tm),
            ):
                mock_registry.get.return_value = self._mock_adapter("Question from HCP")
                async for _ in run_presentation_round(db, session, "我们的药物数据展示"):
                    pass

                first_hcp = data["hcps"][1].id
                for response in ("我的回答 1", "我的回答 2"):
                    async for _ in handle_respond(db, session, first_hcp, response):
                        pass

                events_final_followup: list[dict] = []
                async for event in handle_respond(db, session, first_hcp, "我的回答 3"):
                    events_final_followup.append(event)

                final_followup_speakers = [
                    json.loads(e["data"])
                    for e in events_final_followup
                    if e["event"] == "speaker_text"
                ]
                assert any(s["speaker_name"] == "Dr. HCP-1" for s in final_followup_speakers)
                assert not any(s["speaker_name"] == "Dr. HCP-2" for s in final_followup_speakers)

                events_next: list[dict] = []
                async for event in handle_respond(db, session, first_hcp, "我的最后回答"):
                    events_next.append(event)

                next_speakers = [
                    json.loads(e["data"]) for e in events_next if e["event"] == "speaker_text"
                ]
                assert [s["speaker_name"] for s in next_speakers] == ["Dr. HCP-0", "Dr. HCP-2"]
                assert "下一位专家" in next_speakers[0]["content"]

                second_hcp = data["hcps"][2].id
                events_second: list[dict] = []
                for response in ("第二位回答 1", "第二位回答 2", "第二位回答 3"):
                    async for _ in handle_respond(db, session, second_hcp, response):
                        pass
                async for event in handle_respond(db, session, second_hcp, "第二位最后回答"):
                    events_second.append(event)

                second_speakers = [
                    json.loads(e["data"]) for e in events_second if e["event"] == "speaker_text"
                ]
                assert any("结束" in s["content"] for s in second_speakers)
                queue_updates = [e for e in events_second if e["event"] == "queue_update"]
                assert queue_updates
                assert json.loads(queue_updates[-1]["data"]) == []

    async def test_active_hcp_moves_next_when_mr_requests_next(self, monkeypatch):
        """MR can explicitly move the floor to the next HCP."""
        monkeypatch.setattr("app.services.conference_service.SPEAKER_PACING_SECONDS", 0)
        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db, roles=["moderator", "audience", "audience"])
            session = await create_conference_session(db, data["scenario"].id, data["user"].id)

            from app.services.conference_service import handle_respond, run_presentation_round

            fresh_tm = TurnManager()
            with (
                patch("app.services.conference_service.registry") as mock_registry,
                patch("app.services.conference_service.turn_manager", fresh_tm),
            ):
                mock_registry.get.return_value = self._mock_adapter("Question from HCP")
                async for _ in run_presentation_round(db, session, "我们的药物数据展示"):
                    pass

                first_hcp = data["hcps"][1].id
                events_next: list[dict] = []
                async for event in handle_respond(db, session, first_hcp, "下一位"):
                    events_next.append(event)

                speakers = [
                    json.loads(e["data"]) for e in events_next if e["event"] == "speaker_text"
                ]
                assert [s["speaker_name"] for s in speakers] == ["Dr. HCP-0", "Dr. HCP-2"]
                assert "下一位专家" in speakers[0]["content"]

    """Tests for handle_respond with mocked LLM adapter."""

    async def test_handle_respond_no_waiting_question(self):
        """Respond to an HCP with no waiting question yields error event."""
        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db)
            session = await create_conference_session(db, data["scenario"].id, data["user"].id)

            from app.services.conference_service import handle_respond

            events = []
            fresh_tm = TurnManager()
            with patch(
                "app.services.conference_service.turn_manager",
                fresh_tm,
            ):
                async for event in handle_respond(db, session, "hcp-nonexistent", "My response"):
                    events.append(event)

            assert len(events) == 1
            assert events[0]["event"] == "error"

    async def test_handle_respond_with_question(self):
        """Respond to HCP with a waiting question streams HCP follow-up."""
        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db)
            session = await create_conference_session(db, data["scenario"].id, data["user"].id)

            hcp_id = data["hcps"][0].id

            # Set up turn_manager with a queued question
            fresh_tm = TurnManager()
            q = QueuedQuestion(
                hcp_profile_id=hcp_id,
                hcp_name=data["hcps"][0].name,
                question="What about side effects?",
                relevance_score=0.8,
                queued_at=datetime.now(UTC),
            )
            fresh_tm.add_question(session.id, q)

            # Mock LLM adapter for follow-up
            mock_adapter = MagicMock()

            async def mock_execute(request):
                yield CoachEvent(
                    type=CoachEventType.TEXT,
                    content="Follow-up response text",
                )
                yield CoachEvent(type=CoachEventType.DONE, content="")

            mock_adapter.execute = mock_execute

            from app.services.conference_service import _save_conference_message, handle_respond

            await _save_conference_message(
                db,
                session.id,
                "assistant",
                q.question,
                speaker_id=hcp_id,
                speaker_name=q.hcp_name,
            )

            events = []
            with (
                patch(
                    "app.services.conference_service.turn_manager",
                    fresh_tm,
                ),
                patch("app.services.conference_service.registry") as mock_registry,
            ):
                mock_registry.get.return_value = mock_adapter
                async for event in handle_respond(db, session, hcp_id, "Here is my response"):
                    events.append(event)

            # Should have: turn_change, speaker_text, turn_change, queue_update
            event_types = [e["event"] for e in events]
            assert "turn_change" in event_types
            assert "speaker_text" in event_types
            assert "queue_update" in event_types

    async def test_handle_respond_aggregates_stream_chunks_into_one_speaker_text(self):
        """Chunked adapter output is emitted as one HCP message bubble."""
        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db)
            session = await create_conference_session(db, data["scenario"].id, data["user"].id)

            hcp_id = data["hcps"][0].id
            fresh_tm = TurnManager()
            q = QueuedQuestion(
                hcp_profile_id=hcp_id,
                hcp_name=data["hcps"][0].name,
                question="What about side effects?",
                relevance_score=0.8,
                queued_at=datetime.now(UTC),
            )
            fresh_tm.add_question(session.id, q)

            mock_adapter = MagicMock()

            async def mock_execute(request):
                yield CoachEvent(type=CoachEventType.TEXT, content="Follow ")
                yield CoachEvent(type=CoachEventType.TEXT, content="up ")
                yield CoachEvent(type=CoachEventType.TEXT, content="response")
                yield CoachEvent(type=CoachEventType.DONE, content="")

            mock_adapter.execute = mock_execute

            from app.services.conference_service import _save_conference_message, handle_respond

            await _save_conference_message(
                db,
                session.id,
                "assistant",
                q.question,
                speaker_id=hcp_id,
                speaker_name=q.hcp_name,
            )

            events = []
            with (
                patch("app.services.conference_service.turn_manager", fresh_tm),
                patch("app.services.conference_service.registry") as mock_registry,
            ):
                mock_registry.get.return_value = mock_adapter
                async for event in handle_respond(db, session, hcp_id, "Here is my response"):
                    events.append(event)

            speaker_events = [e for e in events if e["event"] == "speaker_text"]
            assert len(speaker_events) == 1
            assert json.loads(speaker_events[0]["data"])["content"] == "Follow up response"

    async def test_handle_respond_no_adapter_releases_next_hcp(self):
        """Respond with no LLM adapter releases the next HCP instead of getting stuck."""
        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db)
            session = await create_conference_session(db, data["scenario"].id, data["user"].id)

            hcp_id = data["hcps"][0].id
            fresh_tm = TurnManager()
            q = QueuedQuestion(
                hcp_profile_id=hcp_id,
                hcp_name="Dr. Test",
                question="Question?",
                relevance_score=0.8,
                queued_at=datetime.now(UTC),
            )
            fresh_tm.add_question(session.id, q)

            from app.services.conference_service import _save_conference_message, handle_respond

            await _save_conference_message(
                db,
                session.id,
                "assistant",
                q.question,
                speaker_id=hcp_id,
                speaker_name=q.hcp_name,
            )

            events = []
            with (
                patch(
                    "app.services.conference_service.turn_manager",
                    fresh_tm,
                ),
                patch("app.services.conference_service.registry") as mock_registry,
            ):
                mock_registry.get.return_value = None
                async for event in handle_respond(db, session, hcp_id, "Response"):
                    events.append(event)

            assert not any(e["event"] == "error" for e in events)
            speaker_events = [e for e in events if e["event"] == "speaker_text"]
            assert speaker_events
            assert json.loads(speaker_events[-1]["data"])["speaker_name"] == data["hcps"][1].name

            msg_result = await db.execute(
                select(SessionMessage).where(
                    SessionMessage.session_id == session.id,
                    SessionMessage.role == "assistant",
                    SessionMessage.speaker_id == hcp_id,
                )
            )
            assert all(msg.content for msg in msg_result.scalars().all())

    def test_fallback_questions_vary_across_hcps(self):
        """Fallback questions cover different topics instead of repeating one template."""
        from app.services.conference_service import _fallback_hcp_question

        hcp = {"specialty": "肿瘤内科"}
        first = _fallback_hcp_question(hcp, "请介绍这个产品", prior_question_count=0)
        second = _fallback_hcp_question(hcp, "请介绍这个产品", prior_question_count=1)
        third = _fallback_hcp_question(hcp, "请介绍这个产品", prior_question_count=2)

        assert len({first, second, third}) == 3
        assert "患者人群" in first
        assert "临床证据" in second
        assert "安全性" in third

    async def test_handle_respond_llm_error_does_not_save_empty_message(self):
        """Adapter errors during follow-up do not create blank HCP messages."""
        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db)
            session = await create_conference_session(db, data["scenario"].id, data["user"].id)

            hcp_id = data["hcps"][0].id
            fresh_tm = TurnManager()
            q = QueuedQuestion(
                hcp_profile_id=hcp_id,
                hcp_name=data["hcps"][0].name,
                question="Question?",
                relevance_score=0.8,
                queued_at=datetime.now(UTC),
            )
            fresh_tm.add_question(session.id, q)

            mock_adapter = MagicMock()

            async def mock_execute(request):
                yield CoachEvent(type=CoachEventType.ERROR, content="LLM unavailable")
                yield CoachEvent(type=CoachEventType.DONE, content="")

            mock_adapter.execute = mock_execute

            from app.services.conference_service import _save_conference_message, handle_respond

            await _save_conference_message(
                db,
                session.id,
                "assistant",
                q.question,
                speaker_id=hcp_id,
                speaker_name=q.hcp_name,
            )

            events = []
            with (
                patch("app.services.conference_service.turn_manager", fresh_tm),
                patch("app.services.conference_service.registry") as mock_registry,
            ):
                mock_registry.get.return_value = mock_adapter
                async for event in handle_respond(db, session, hcp_id, "Response"):
                    events.append(event)

            assert not any(e["event"] == "error" for e in events)
            assert fresh_tm.get_active_speaker(session.id) is not None
            assert fresh_tm.get_active_speaker(session.id).hcp_profile_id == data["hcps"][1].id

            msg_result = await db.execute(
                select(SessionMessage).where(
                    SessionMessage.session_id == session.id,
                    SessionMessage.role == "assistant",
                    SessionMessage.speaker_id == hcp_id,
                )
            )
            assert all(msg.content for msg in msg_result.scalars().all())

    async def test_handle_respond_empty_llm_output_does_not_save_empty_message(self):
        """Empty DONE-only follow-up output releases the next HCP without blank text."""
        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db)
            session = await create_conference_session(db, data["scenario"].id, data["user"].id)

            hcp_id = data["hcps"][0].id
            fresh_tm = TurnManager()
            q = QueuedQuestion(
                hcp_profile_id=hcp_id,
                hcp_name=data["hcps"][0].name,
                question="Question?",
                relevance_score=0.8,
                queued_at=datetime.now(UTC),
            )
            fresh_tm.add_question(session.id, q)

            mock_adapter = MagicMock()

            async def mock_execute(request):
                yield CoachEvent(type=CoachEventType.DONE, content="")

            mock_adapter.execute = mock_execute

            from app.services.conference_service import _save_conference_message, handle_respond

            await _save_conference_message(
                db,
                session.id,
                "assistant",
                q.question,
                speaker_id=hcp_id,
                speaker_name=q.hcp_name,
            )

            events = []
            with (
                patch("app.services.conference_service.turn_manager", fresh_tm),
                patch("app.services.conference_service.registry") as mock_registry,
            ):
                mock_registry.get.return_value = mock_adapter
                async for event in handle_respond(db, session, hcp_id, "Response"):
                    events.append(event)

            assert not any(e["event"] == "error" for e in events)
            speaker_events = [e for e in events if e["event"] == "speaker_text"]
            assert speaker_events
            assert json.loads(speaker_events[-1]["data"])["speaker_name"] == data["hcps"][1].name

            msg_result = await db.execute(
                select(SessionMessage).where(
                    SessionMessage.session_id == session.id,
                    SessionMessage.role == "assistant",
                    SessionMessage.speaker_id == hcp_id,
                )
            )
            assert all(msg.content for msg in msg_result.scalars().all())


class TestEndConferenceEdgeCases:
    """Edge case tests for end_conference_session."""

    @patch("app.services.conference_service.turn_manager")
    async def test_end_with_naive_started_at(self, mock_tm):
        """Naive datetime started_at gets UTC tzinfo before duration calc."""
        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db)
            session = await create_conference_session(db, data["scenario"].id, data["user"].id)
            # Set a naive datetime (no tzinfo) for started_at
            session.started_at = datetime(2026, 1, 1, 12, 0, 0)
            session.status = "in_progress"
            await db.flush()

            result = await end_conference_session(db, session.id, data["user"].id)
            assert result.status == "completed"
            assert result.duration_seconds is not None
            assert result.duration_seconds > 0

    @patch("app.services.conference_service.turn_manager")
    async def test_end_does_not_run_scoring_inline(self, mock_tm):
        """Ending a session returns after completion without awaiting scoring."""
        async with TestSessionLocal() as db:
            data = await _seed_conference_fixture(db)
            session = await create_conference_session(db, data["scenario"].id, data["user"].id)
            session.status = "in_progress"
            await db.flush()

            with patch(
                "app.services.scoring_service.score_session", new_callable=AsyncMock
            ) as score:
                result = await end_conference_session(db, session.id, data["user"].id)

            assert result.status == "completed"
            score.assert_not_awaited()

    async def test_background_scoring_commits_success(self):
        """Background scoring uses its own session and commits on success."""
        db = AsyncMock()
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=db)
        context.__aexit__ = AsyncMock(return_value=None)
        session_factory = MagicMock(return_value=context)

        with (
            patch("app.services.conference_service.AsyncSessionLocal", session_factory),
            patch("app.services.scoring_service.score_session", new_callable=AsyncMock) as score,
        ):
            await score_conference_session_background("session-1")

        score.assert_awaited_once_with(db, "session-1")
        db.commit.assert_awaited_once()
        db.rollback.assert_not_awaited()

    async def test_background_scoring_rolls_back_unexpected_exception(self):
        """Background scoring rolls back and swallows unexpected scoring errors."""
        db = AsyncMock()
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=db)
        context.__aexit__ = AsyncMock(return_value=None)
        session_factory = MagicMock(return_value=context)

        with (
            patch("app.services.conference_service.AsyncSessionLocal", session_factory),
            patch(
                "app.services.scoring_service.score_session",
                new_callable=AsyncMock,
                side_effect=RuntimeError("scoring backend unavailable"),
            ) as score,
        ):
            await score_conference_session_background("session-1")

        score.assert_awaited_once_with(db, "session-1")
        db.rollback.assert_awaited_once()
        db.commit.assert_not_awaited()


class TestComputeRelevanceScore:
    """Tests for the _compute_relevance_score helper."""

    def test_full_overlap(self):
        """Identical words give score close to 1.0."""
        score = _compute_relevance_score("hello world", "hello world")
        assert score >= 0.9

    def test_no_overlap(self):
        """No word overlap gives base score 0.3."""
        score = _compute_relevance_score("alpha beta", "gamma delta")
        assert score == 0.3

    def test_partial_overlap(self):
        """Partial overlap gives score between 0.3 and 1.0."""
        score = _compute_relevance_score("hello world test", "hello foo bar")
        assert 0.3 < score < 1.0

    def test_empty_strings(self):
        """Empty inputs return default 0.5."""
        assert _compute_relevance_score("", "") == 0.5
        assert _compute_relevance_score("", "hello") == 0.5

    def test_single_word_overlap(self):
        """Single word in both gives intermediate score."""
        score = _compute_relevance_score("hello", "hello")
        assert score == 1.0


class TestSerializeQueue:
    """Tests for the _serialize_queue helper."""

    def test_serializes_questions(self):
        """Queue items are serialized with expected keys."""
        queue = [
            QueuedQuestion(
                hcp_profile_id="hcp-1",
                hcp_name="Dr. A",
                question="Question?",
                relevance_score=0.8,
                queued_at=datetime.now(UTC),
            )
        ]
        result = _serialize_queue(queue)
        assert len(result) == 1
        assert result[0]["hcp_profile_id"] == "hcp-1"
        assert result[0]["hcp_name"] == "Dr. A"
        assert result[0]["question"] == "Question?"
        assert result[0]["relevance_score"] == 0.8
        assert result[0]["status"] == "waiting"

    def test_empty_queue(self):
        """Empty queue returns empty list."""
        assert _serialize_queue([]) == []
