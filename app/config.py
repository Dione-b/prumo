from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    database_url: SecretStr
    api_key: SecretStr

    # Cloud Synthesis
    gemini_api_key: SecretStr
    gemini_synthesis_model: str = "gemini-2.5-pro"
    gemini_temperature: float = 0.2

    # Local Ingestion (Ollama)
    ollama_base_url: str = "http://localhost:11434"
    ollama_business_model: str = "llama3.2:3b"
    ollama_embedding_model: str = "qwen3-embedding:0.6b"
    ollama_embedding_dim: int = 1024  # Standard for Qwen3-0.6b
    ollama_max_concurrent: int = 1

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()  # type: ignore[call-arg]
