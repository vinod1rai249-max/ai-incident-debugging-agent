from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="development")
    log_level: str = Field(default="INFO")
    log_prompts: bool = Field(default=False)

    anthropic_api_key: str = Field(default="")
    openai_api_key: str = Field(default="")

    # Default model used across the app — override via MODEL_NAME env var
    model_name: str = Field(default="claude-sonnet-4-6")

    chroma_host: str = Field(default="localhost")
    chroma_port: int = Field(default=8001)

    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    api_rate_limit: int = Field(default=100)

    # Incident Debugger
    incident_max_cost_usd: float = Field(default=0.10)
    incident_timeout_s: int = Field(default=60)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


settings = Settings()
