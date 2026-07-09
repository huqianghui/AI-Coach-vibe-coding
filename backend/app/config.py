from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    app_name: str = "AI Coach Platform"
    debug: bool = False
    api_prefix: str = "/api/v1"

    # Database
    database_url: str = "sqlite+aiosqlite:///./ai_coach.db"
    database_auth_mode: str = "password"  # password | azure_ad
    database_host: str = ""
    database_port: int = 5432
    database_name: str = "ai_coach"
    database_user: str = ""
    database_ssl: str = "require"
    database_pool_recycle_seconds: int = 1800
    database_auto_create_tables: bool = True

    # JWT
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    # CORS
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # AI Services
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # Voice / ASR
    azure_speech_key: str = ""
    azure_speech_region: str = ""

    # Feature Toggles (ARCH-02)
    feature_avatar_enabled: bool = False
    feature_voice_enabled: bool = False
    feature_realtime_voice_enabled: bool = False
    feature_conference_enabled: bool = False
    feature_voice_live_enabled: bool = True

    # Voice Mode (PLAT-05): "text_only" | "stt_tts" | "realtime" | "voice_live"
    default_voice_mode: str = "text_only"

    # Region (PLAT-04): "global" | "china" | "eu"
    region: str = "global"

    # Azure AI Foundry (master config for agent sync)
    azure_foundry_endpoint: str = ""
    azure_foundry_api_key: str = ""
    azure_foundry_default_project: str = ""

    # Azure Avatar (optional premium) (ARCH-05)
    azure_avatar_endpoint: str = ""
    azure_avatar_key: str = ""

    # Azure Tenant (for portal URL generation)
    azure_tenant_id: str = ""
    azure_client_id: str = ""

    # Azure Content Understanding (ARCH-05)
    azure_content_endpoint: str = ""
    azure_content_key: str = ""
    content_understanding_api_version: str = "2025-11-01"
    voice_scoring_transcode_enabled: bool = False
    voice_scoring_transcode_timeout_seconds: int = 120

    # Training Material Management
    storage_backend: str = "local"
    material_storage_path: str = "./storage/materials"
    material_max_size_mb: int = 50
    material_retention_days: int = 365
    azure_storage_connection_string: str = ""
    azure_storage_account_url: str = ""
    azure_storage_container_name: str = "materials"
    azure_storage_blob_prefix: str = ""

    # Encryption (for API key storage)
    encryption_key: str = ""  # Set via ENCRYPTION_KEY env var; generated at runtime if empty
    secret_store: str = "database"  # database | keyvault
    azure_key_vault_url: str = ""

    # Seed data control: set SEED_DATA_IGNORE=true to skip seed on startup
    seed_data_ignore: bool = False

    # Default Voice Live model (when creating new instances/profiles; override via .env)
    voice_live_default_model: str = "gpt-4o"

    # Default chat completion model for skill conversion/evaluation (override via .env)
    default_chat_model: str = "gpt-4o"
    # AI parameters for skill conversion/evaluation
    skill_ai_temperature: float = 0.3
    skill_ai_max_tokens: int = 4096
    skill_ai_api_version: str = "2024-06-01"
    # Language for AI-generated SOP content: "en" (English) or "zh" (Chinese)
    skill_sop_language: str = "en"

    # Voice Live Agent Mode (RD-1: SDK >=1.2.0b5 supports API-key agent mode)
    voice_live_agent_mode_enabled: bool = True

    # Hosted Agent override: when set, ALL Voice Live agent-mode connections
    # use this hosted agent instead of per-HCP classic agents (asst_* IDs).
    voice_live_hosted_agent_name: str = ""
    voice_live_hosted_agent_project: str = ""
    voice_live_hosted_agent_endpoint: str = ""

    # Logging
    log_level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR

    # Default AI provider per category
    default_llm_provider: str = "mock"
    default_stt_provider: str = "mock"
    default_tts_provider: str = "mock"
    default_avatar_provider: str = "mock"

    # Prompt Optimizer sidecar (PROMPT-01): MCP Streamable-HTTP endpoint
    prompt_optimizer_mcp_url: str = "http://prompt-optimizer:80/mcp"
    prompt_optimizer_timeout_seconds: float = 60.0

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
