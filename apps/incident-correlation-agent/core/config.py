from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ServiceNow
    servicenow_url: str = "https://dev-instance.service-now.com"
    servicenow_user: str = "admin"
    servicenow_password: str = "password"
    servicenow_incident_limit: int = 50

    # Dynatrace
    dynatrace_url: str = "https://tenant.live.dynatrace.com"
    dynatrace_api_token: str = "dt0c01.token"
    dynatrace_problems_timeframe: str = "now-24h"

    # OpenAI / OpenRouter
    openai_api_key: str = ""
    openai_base_url: str = "https://openrouter.ai/api/v1"
    openai_model: str = "openai/gpt-4o-mini"

    # App
    app_name: str = "incident-correlation-agent"
    debug: bool = False
    correlation_time_window_minutes: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
