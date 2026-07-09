"""Idempotent seed-all logic for app lifespan startup.

Seeds users, default rubric, HCP profiles, scenarios, and training materials.
Skips any records that already exist. Safe to run on every startup.
"""

import json
import logging
import sys
from inspect import isawaitable
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Ensure scripts/ is importable for seed data constants
_scripts_dir = str(Path(__file__).resolve().parent.parent / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

logger = logging.getLogger(__name__)


async def seed_all(session: AsyncSession) -> None:
    """Run all seed operations in a single session."""
    from app.models.user import User
    from app.services.auth import get_password_hash

    # --- 1. Users ---
    seed_users = [
        {
            "username": "admin",
            "email": "admin@aicoach.com",
            "password": "admin123",
            "role": "admin",
            "full_name": "System Admin",
            "preferred_language": "zh-CN",
            "business_unit": "",
        },
        {
            "username": "user1",
            "email": "user1@aicoach.com",
            "password": "user123",
            "role": "user",
            "full_name": "Zhang Wei",
            "preferred_language": "zh-CN",
            "business_unit": "Oncology BU (肿瘤事业部)",
        },
        {
            "username": "user2",
            "email": "user2@aicoach.com",
            "password": "user123",
            "role": "user",
            "full_name": "Li Ming",
            "preferred_language": "zh-CN",
            "business_unit": "Hematology BU (血液事业部)",
        },
        {
            "username": "user3",
            "email": "user3@aicoach.com",
            "password": "user123",
            "role": "user",
            "full_name": "Wang Fang",
            "preferred_language": "en-US",
            "business_unit": "Solid Tumor BU (实体瘤事业部)",
        },
    ]
    for ud in seed_users:
        result = await session.execute(select(User).where(User.username == ud["username"]))
        if result.scalar_one_or_none() is None:
            session.add(
                User(
                    username=ud["username"],
                    email=ud["email"],
                    hashed_password=get_password_hash(ud["password"]),
                    full_name=ud["full_name"],
                    role=ud["role"],
                    preferred_language=ud["preferred_language"],
                    business_unit=ud.get("business_unit", ""),
                )
            )
    await session.commit()

    # Get admin user for created_by fields
    admin_result = await session.execute(select(User).where(User.role == "admin").limit(1))
    admin_user = admin_result.scalars().first()
    if admin_user is None:
        return
    admin_id = admin_user.id

    from app.models.scoring_rubric import ScoringRubric

    # --- 2. Default scoring rubric ---
    from app.services.default_rubrics import ensure_default_f2f_rubric

    if await ensure_default_f2f_rubric(session, admin_id) is not None:
        await session.commit()

    # --- 2b. Deduplicate defaults (fix for h21a migration creating duplicate) ---
    from sqlalchemy import func, update

    for stype in ("f2f", "conference"):
        count_result = await session.execute(
            select(func.count())
            .select_from(ScoringRubric)
            .where(
                ScoringRubric.scenario_type == stype,
                ScoringRubric.is_default == True,  # noqa: E712
            )
        )
        default_count = count_result.scalar() or 0
        if default_count > 1:
            # Keep only the most recently updated default, unset the rest
            latest_result = await session.execute(
                select(ScoringRubric.id)
                .where(
                    ScoringRubric.scenario_type == stype,
                    ScoringRubric.is_default == True,  # noqa: E712
                )
                .order_by(ScoringRubric.updated_at.desc())
                .limit(1)
            )
            keep_id = latest_result.scalar()
            if keep_id:
                await session.execute(
                    update(ScoringRubric)
                    .where(
                        ScoringRubric.scenario_type == stype,
                        ScoringRubric.is_default == True,  # noqa: E712
                        ScoringRubric.id != keep_id,
                    )
                    .values(is_default=False)
                )
                await session.commit()

    # --- 3. HCP profiles ---
    from app.models.hcp_profile import HcpProfile

    existing_hcp = await session.execute(select(HcpProfile).limit(1))
    if existing_hcp.scalar_one_or_none() is None:
        from seed_phase2 import SEED_HCP_PROFILES  # type: ignore[import-not-found]

        for profile_data in SEED_HCP_PROFILES:
            profile = HcpProfile(**profile_data, created_by=admin_id)
            session.add(profile)
        await session.flush()
        await session.commit()

    # --- 4. Scenarios ---
    from seed_phase2 import SEED_SCENARIOS  # type: ignore[import-not-found]

    from app.models.scenario import Scenario
    from app.models.skill import Skill, SkillVersion
    from app.services.conference_prompt_config import default_conference_prompt_config

    # Restore the original two demo scenarios even if other scenarios already exist.
    default_seed_scenarios = SEED_SCENARIOS[:2]

    # Resolve default rubric for rubric_id assignment
    default_rubric_result = await session.execute(
        select(ScoringRubric)
        .where(
            ScoringRubric.is_default == True,  # noqa: E712
            ScoringRubric.scenario_type == "f2f",
        )
        .limit(1)
    )
    default_rubric = default_rubric_result.scalars().first()
    default_rubric_id = default_rubric.id if default_rubric else None

    default_skill_result = await session.execute(
        select(Skill).where(Skill.status == "published").limit(1)
    )
    default_skill = default_skill_result.scalar_one_or_none()
    if default_skill is None:
        logger.info("Scenario seed skipped: no published skill exists")
        await session.commit()
    else:
        default_version_result = await session.execute(
            select(SkillVersion)
            .where(
                SkillVersion.skill_id == default_skill.id,
                SkillVersion.is_published == True,  # noqa: E712
            )
            .order_by(SkillVersion.version_number.desc())
            .limit(1)
        )
        default_version = default_version_result.scalar_one_or_none()

        # Build HCP name -> ID map
        hcp_result = await session.execute(select(HcpProfile))
        hcp_map = {p.name: p.id for p in hcp_result.scalars().all()}

        for scenario_data in default_seed_scenarios:
            existing_result = await session.execute(
                select(Scenario).where(Scenario.name == scenario_data["name"])
            )
            if existing_result.scalar_one_or_none() is not None:
                continue

            data = dict(scenario_data)  # copy to avoid mutating the constant
            hcp_name = data.pop("hcp_name", None)
            product = data.pop("product", "")
            therapeutic_area = data.pop("therapeutic_area", "")
            if "tags" not in data and (product or therapeutic_area):
                tags = []
                if product:
                    tags.append(f"product:{product}")
                if therapeutic_area:
                    tags.append(f"area:{therapeutic_area}")
                data["tags"] = json.dumps(tags)

            hcp_id = hcp_map.get(hcp_name) if hcp_name else None
            if hcp_id is None:
                logger.warning("Scenario seed skipped: HCP profile not found for %s", hcp_name)
                continue
            if default_rubric_id is None:
                logger.warning("Scenario seed skipped: no default rubric exists")
                continue
            data.setdefault("rubric_id", default_rubric_id)
            data.setdefault(
                "conference_prompt_config", json.dumps(default_conference_prompt_config())
            )
            scenario = Scenario(
                **data,
                hcp_profile_id=hcp_id,
                skill_id=default_skill.id,
                skill_version_id=default_version.id if default_version else None,
                created_by=admin_id,
            )
            session.add(scenario)
        await session.commit()

    # --- 5. Training materials ---
    from app.models.material import TrainingMaterial

    existing_mat = await session.execute(select(TrainingMaterial).limit(1))
    if existing_mat.scalar_one_or_none() is None:
        try:
            from seed_materials import seed_materials  # type: ignore[import-not-found]

            material_seed_result = seed_materials(session)
            if isawaitable(material_seed_result):
                await material_seed_result
        except Exception:
            logger.exception("Training material seed failed; continuing startup seed")

    # --- 6. Azure AI Foundry config from env vars ---
    try:
        from app.config import get_settings
        from app.models.service_config import ServiceConfig
        from app.services.config_service import ensure_voice_live_config
        from app.services.secret_store import get_secret_store

        foundry_settings = get_settings()
        secret_store = get_secret_store()
        existing_master = await session.execute(
            select(ServiceConfig).where(ServiceConfig.is_master == True)  # noqa: E712
        )
        existing_master_row = existing_master.scalar_one_or_none()
        if existing_master_row is None and foundry_settings.azure_foundry_endpoint:
            master = ServiceConfig(
                service_name="ai_foundry",
                display_name="Azure AI Foundry",
                endpoint=foundry_settings.azure_foundry_endpoint,
                api_key_encrypted=(
                    await secret_store.set_secret(
                        "ai_foundry",
                        foundry_settings.azure_foundry_api_key,
                    )
                    if foundry_settings.azure_foundry_api_key
                    else ""
                ),
                model_or_deployment=(
                    foundry_settings.azure_openai_deployment
                    or foundry_settings.voice_live_default_model
                ),
                default_project=foundry_settings.azure_foundry_default_project,
                region="swedencentral",
                is_master=True,
                is_active=True,
                updated_by="seed",
            )
            session.add(master)
            await session.flush()

            # Voice Live service row in agent mode
            if foundry_settings.azure_foundry_default_project:
                await ensure_voice_live_config(session, master, "seed")
            await session.commit()
        else:
            if existing_master_row is not None:
                await ensure_voice_live_config(session, existing_master_row, "seed")
                await session.commit()
    except Exception:
        import logging as _logging

        _logging.getLogger(__name__).warning(
            "AI Foundry config seed failed (table may not exist yet)", exc_info=True
        )

    # --- 7. Prompt registry ---
    try:
        from app.services.prompt_registry import seed_prompt_registry

        await seed_prompt_registry(session)
    except Exception:
        import logging as _logging

        _logging.getLogger(__name__).warning(
            "Prompt registry seed failed (table may not exist yet)", exc_info=True
        )
