from app.api.admin_users import router as admin_users_router
from app.api.analytics import router as analytics_router
from app.api.auth import router as auth_router
from app.api.azure_config import router as azure_config_router
from app.api.conference import router as conference_router
from app.api.config import router as config_router
from app.api.dry_runs import router as dry_runs_router
from app.api.hcp_profiles import router as hcp_profiles_router
from app.api.knowledge_base import router as knowledge_base_router
from app.api.materials import router as materials_router
from app.api.meta_skills import router as meta_skills_router
from app.api.rubrics import router as rubrics_router
from app.api.scenario_groups import router as scenario_groups_router
from app.api.scenarios import router as scenarios_router
from app.api.scoring import router as scoring_router
from app.api.sessions import router as sessions_router
from app.api.skills import router as skills_router
from app.api.speech import router as speech_router
from app.api.system_enums import router as system_enums_router
from app.api.voice_live import router as voice_live_router

__all__ = [
    "admin_users_router",
    "analytics_router",
    "auth_router",
    "azure_config_router",
    "conference_router",
    "config_router",
    "dry_runs_router",
    "hcp_profiles_router",
    "knowledge_base_router",
    "materials_router",
    "meta_skills_router",
    "rubrics_router",
    "scenarios_router",
    "scenario_groups_router",
    "scoring_router",
    "sessions_router",
    "skills_router",
    "speech_router",
    "system_enums_router",
    "voice_live_router",
]
