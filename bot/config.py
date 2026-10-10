from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str = ""
    api_base_url: str = "http://localhost:8000"
    # Empty: in-memory FSM (tests, local runs). docker-compose sets redis://redis:6379/0.
    redis_url: str = ""
    # Same value as the API's INTERNAL_API_KEY; empty = API accepts X-User-Id without it.
    internal_api_key: str | None = None


settings = BotSettings()
