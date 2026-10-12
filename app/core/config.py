from pydantic_settings import BaseSettings, SettingsConfigDict
from uuid import UUID


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://crm:crm@localhost:5432/crm"
    test_database_url: str = "postgresql+asyncpg://crm:crm@localhost:5432/crm_test"
    sql_echo: bool = False
    consent_token_ttl_minutes: int = 15
    search_fuzzy_threshold: float = 0.5
    catalog_fuzzy_threshold: float = 0.3
    recent_views_limit: int = 10
    file_storage_root: str = "./storage"
    default_branch_id: UUID = UUID("00000000-0000-0000-0000-000000000001")
    telegram_bot_token: str | None = None

    # Web / Mini App auth
    session_secret: str | None = None
    session_ttl_hours: int = 12
    telegram_init_data_max_age_s: int = 86400
    dev_login: bool = False
    # Bot's service key: with it set, X-User-Id is honoured only with a matching X-Service-Key.
    internal_api_key: str | None = None


settings = Settings()
