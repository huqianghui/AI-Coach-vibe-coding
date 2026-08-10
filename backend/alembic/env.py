"""Alembic environment configuration for async SQLAlchemy."""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.config import get_settings
from app.models import (  # noqa: F401
    Base,
    CoachingSession,
    ConferenceAudienceHcp,
    HcpProfile,
    MaterialVersion,
    MetaSkill,
    PromptOptimizationRun,
    PromptTemplate,
    PromptVersion,
    Scenario,
    ScenarioGroup,
    ScenarioGroupItem,
    ScenarioGroupRun,
    ScenarioGroupRunItem,
    ScoreDetail,
    ScoringRubric,
    ServiceConfig,
    SessionMessage,
    SessionScore,
    SessionTurn,
    SessionTurnAttempt,
    SessionTurnAttemptEvent,
    SessionTurnContextAudit,
    Skill,
    SkillResource,
    SkillSourceMaterial,
    SkillVersion,
    TrainingMaterial,
    User,
    VoiceLiveInstance,
    VoiceScore,
    VoiceScoreDetail,
)

settings = get_settings()
config = context.config

# Override sqlalchemy.url from settings
if settings.database_auth_mode.lower() == "azure_ad":
    from app.database import database_url

    config.set_main_option("sqlalchemy.url", str(database_url))
else:
    config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # SQLite compatibility (Gotcha #1)
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    """Run migrations with the given connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,  # SQLite compatibility (Gotcha #1)
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    if settings.database_auth_mode.lower() == "azure_ad":
        from app.database import engine

        connectable = engine
        dispose_engine = True
    else:
        connectable = async_engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
        dispose_engine = True
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    if dispose_engine:
        await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
