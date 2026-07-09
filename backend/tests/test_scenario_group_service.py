"""Tests for weighted scenario group orchestration."""

import json

import pytest
from pydantic import ValidationError

from app.models.hcp_profile import HcpProfile
from app.models.scenario import Scenario
from app.models.score import SessionScore
from app.models.scoring_rubric import ScoringRubric
from app.models.session import CoachingSession
from app.models.skill import Skill, SkillVersion
from app.models.user import User
from app.schemas.scenario_group import (
    ScenarioGroupCreate,
    ScenarioGroupItemCreate,
    ScenarioGroupUpdate,
)
from app.services.auth import get_password_hash
from app.services.scenario_group_service import (
    create_child_session,
    create_group,
    create_run,
    refresh_run_score,
    update_group,
)
from tests.conftest import TestSessionLocal


async def _seed_group_fixture(db):
    user = User(
        username="group-user",
        email="group@test.com",
        hashed_password=get_password_hash("pass"),
        full_name="Group User",
        role="user",
    )
    admin = User(
        username="group-admin",
        email="group-admin@test.com",
        hashed_password=get_password_hash("pass"),
        full_name="Group Admin",
        role="admin",
    )
    db.add_all([user, admin])
    await db.flush()

    hcp = HcpProfile(
        name="Dr. Group",
        specialty="Oncology",
        personality_type="analytical",
        created_by=admin.id,
    )
    db.add(hcp)

    rubric = ScoringRubric(
        name="Group Rubric",
        scenario_type="f2f",
        dimensions=json.dumps(
            [{"name": "Knowledge", "weight": 100, "criteria": "", "max_score": 100}]
        ),
        is_default=False,
        created_by=admin.id,
    )
    skill = Skill(
        name="Group Skill",
        description="Skill",
        status="published",
        created_by=admin.id,
    )
    db.add_all([rubric, skill])
    await db.flush()

    skill_version = SkillVersion(
        skill_id=skill.id,
        version_number=1,
        content="skill content",
        is_published=True,
        created_by=admin.id,
    )
    db.add(skill_version)
    await db.flush()

    scenarios = []
    for index in range(2):
        scenario = Scenario(
            name=f"Scenario {index + 1}",
            description="",
            tags="[]",
            mode="f2f",
            difficulty="medium",
            status="active",
            hcp_profile_id=hcp.id,
            key_messages=json.dumps(["message"]),
            skill_id=skill.id,
            skill_version_id=skill_version.id,
            rubric_id=rubric.id,
            pass_threshold=70,
            created_by=admin.id,
        )
        db.add(scenario)
        scenarios.append(scenario)
    await db.flush()
    return {"user": user, "admin": admin, "scenarios": scenarios}


class TestScenarioGroupService:
    async def test_create_group_requires_weights_sum_to_100(self):
        async with TestSessionLocal() as db:
            data = await _seed_group_fixture(db)

            with pytest.raises(ValidationError, match="weights must sum to 100"):
                ScenarioGroupCreate(
                    name="组合训练",
                    items=[
                        ScenarioGroupItemCreate(
                            scenario_id=data["scenarios"][0].id,
                            weight=40,
                        ),
                        ScenarioGroupItemCreate(
                            scenario_id=data["scenarios"][1].id,
                            weight=40,
                        ),
                    ],
                )

    async def test_create_group_and_run_child_session(self):
        async with TestSessionLocal() as db:
            data = await _seed_group_fixture(db)
            group = await create_group(
                db,
                ScenarioGroupCreate(
                    name="组合训练",
                    items=[
                        ScenarioGroupItemCreate(
                            scenario_id=data["scenarios"][0].id,
                            weight=40,
                            sort_order=0,
                        ),
                        ScenarioGroupItemCreate(
                            scenario_id=data["scenarios"][1].id,
                            weight=60,
                            sort_order=1,
                        ),
                    ],
                ),
                data["admin"].id,
            )
            assert len(group.items) == 2
            group.status = "active"
            await db.flush()

            run = await create_run(db, group.id, data["user"].id)
            assert run.status == "in_progress"
            assert len(run.items) == 2

            run, session = await create_child_session(
                db,
                run.id,
                run.items[0].id,
                data["user"].id,
                "text",
            )
            assert session.scenario_id == data["scenarios"][0].id
            assert run.items[0].session_id == session.id
            assert run.items[0].status == "in_progress"

    async def test_update_active_group_can_save_items_and_threshold(self):
        async with TestSessionLocal() as db:
            data = await _seed_group_fixture(db)
            group = await create_group(
                db,
                ScenarioGroupCreate(
                    name="组合训练",
                    pass_threshold=70,
                    items=[
                        ScenarioGroupItemCreate(scenario_id=data["scenarios"][0].id, weight=50),
                        ScenarioGroupItemCreate(scenario_id=data["scenarios"][1].id, weight=50),
                    ],
                ),
                data["admin"].id,
            )
            group.status = "active"
            await db.flush()

            updated = await update_group(
                db,
                group.id,
                ScenarioGroupUpdate(
                    name="组合训练更新",
                    pass_threshold=85,
                    items=[
                        ScenarioGroupItemCreate(scenario_id=data["scenarios"][0].id, weight=60),
                        ScenarioGroupItemCreate(scenario_id=data["scenarios"][1].id, weight=40),
                    ],
                ),
            )

            assert updated.status == "active"
            assert updated.name == "组合训练更新"
            assert updated.pass_threshold == 85
            assert [item.weight for item in updated.items] == [60, 40]

    async def test_refresh_run_score_aggregates_weighted_children(self):
        async with TestSessionLocal() as db:
            data = await _seed_group_fixture(db)
            group = await create_group(
                db,
                ScenarioGroupCreate(
                    name="组合训练",
                    pass_threshold=80,
                    items=[
                        ScenarioGroupItemCreate(scenario_id=data["scenarios"][0].id, weight=25),
                        ScenarioGroupItemCreate(scenario_id=data["scenarios"][1].id, weight=75),
                    ],
                ),
                data["admin"].id,
            )
            group.status = "active"
            await db.flush()
            run = await create_run(db, group.id, data["user"].id)

            for index, item in enumerate(run.items):
                session = CoachingSession(
                    user_id=data["user"].id,
                    scenario_id=item.scenario_id,
                    status="scored",
                    key_messages_status="[]",
                    overall_score=60 if index == 0 else 100,
                    passed=index == 1,
                )
                db.add(session)
                await db.flush()
                item.session_id = session.id
                db.add(
                    SessionScore(
                        session_id=session.id,
                        overall_score=session.overall_score,
                        passed=bool(session.passed),
                        feedback_summary="",
                    )
                )
            await db.flush()

            refreshed = await refresh_run_score(db, run.id, data["user"].id)

            assert refreshed.status == "scored"
            assert refreshed.overall_score == 90.0
            assert refreshed.passed is True
            assert [item.status for item in refreshed.items] == ["scored", "scored"]
            assert [item.score for item in refreshed.items] == [60.0, 100.0]

    async def test_refresh_run_score_links_best_scored_session_when_item_has_no_session(self):
        async with TestSessionLocal() as db:
            data = await _seed_group_fixture(db)
            group = await create_group(
                db,
                ScenarioGroupCreate(
                    name="组合训练",
                    pass_threshold=70,
                    items=[
                        ScenarioGroupItemCreate(scenario_id=data["scenarios"][0].id, weight=40),
                        ScenarioGroupItemCreate(scenario_id=data["scenarios"][1].id, weight=60),
                    ],
                ),
                data["admin"].id,
            )
            group.status = "active"
            await db.flush()
            run = await create_run(db, group.id, data["user"].id)

            lower_session = CoachingSession(
                user_id=data["user"].id,
                scenario_id=data["scenarios"][0].id,
                status="scored",
                key_messages_status="[]",
                overall_score=88,
                passed=True,
            )
            higher_session = CoachingSession(
                user_id=data["user"].id,
                scenario_id=data["scenarios"][0].id,
                status="scored",
                key_messages_status="[]",
                overall_score=95,
                passed=True,
            )
            db.add_all([lower_session, higher_session])
            await db.flush()
            db.add_all(
                [
                    SessionScore(
                        session_id=lower_session.id,
                        overall_score=88,
                        passed=True,
                        feedback_summary="",
                    ),
                    SessionScore(
                        session_id=higher_session.id,
                        overall_score=95,
                        passed=True,
                        feedback_summary="",
                    ),
                ]
            )
            latest_lower_session = CoachingSession(
                user_id=data["user"].id,
                scenario_id=data["scenarios"][0].id,
                status="scored",
                key_messages_status="[]",
                overall_score=70,
                passed=True,
            )
            db.add(latest_lower_session)
            await db.flush()
            db.add(
                SessionScore(
                    session_id=latest_lower_session.id,
                    overall_score=70,
                    passed=True,
                    feedback_summary="",
                )
            )
            await db.flush()
            run.items[0].session_id = latest_lower_session.id
            run.items[0].status = "scored"
            run.items[0].score = latest_lower_session.overall_score
            await db.flush()

            refreshed = await refresh_run_score(db, run.id, data["user"].id)

            first_item = refreshed.items[0]
            assert first_item.session_id == higher_session.id
            assert first_item.status == "scored"
            assert first_item.score == 95.0
            assert refreshed.status == "in_progress"
            assert refreshed.overall_score is None

    async def test_retrain_child_session_reopens_scored_run_item(self):
        async with TestSessionLocal() as db:
            data = await _seed_group_fixture(db)
            group = await create_group(
                db,
                ScenarioGroupCreate(
                    name="组合训练",
                    items=[
                        ScenarioGroupItemCreate(scenario_id=data["scenarios"][0].id, weight=50),
                        ScenarioGroupItemCreate(scenario_id=data["scenarios"][1].id, weight=50),
                    ],
                ),
                data["admin"].id,
            )
            group.status = "active"
            await db.flush()
            run = await create_run(db, group.id, data["user"].id)
            item = run.items[0]
            old_session = CoachingSession(
                user_id=data["user"].id,
                scenario_id=item.scenario_id,
                status="scored",
                key_messages_status="[]",
                overall_score=88,
                passed=True,
            )
            db.add(old_session)
            await db.flush()
            item.session_id = old_session.id
            item.status = "scored"
            item.score = 88
            item.passed = True
            await db.flush()

            updated_run, new_session = await create_child_session(
                db,
                run.id,
                item.id,
                data["user"].id,
                "text",
                retrain=True,
            )

            reopened_item = next(
                run_item for run_item in updated_run.items if run_item.id == item.id
            )
            assert new_session.id != old_session.id
            assert reopened_item.session_id == new_session.id
            assert reopened_item.status == "in_progress"
            assert reopened_item.score is None
            assert updated_run.status == "in_progress"
