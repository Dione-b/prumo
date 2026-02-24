from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    database_url: SecretStr
    gemini_api_key: SecretStr
    gemini_model: str = "gemini-1.5-pro"
    gemini_temperature: float = 0.2
    api_key: SecretStr

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()  # type: ignore[call-arg]
