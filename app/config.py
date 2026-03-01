from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    database_url: SecretStr
    api_key: SecretStr

    # Cloud Synthesis
    gemini_api_key: SecretStr
    gemini_synthesis_model: str = "gemini-2.5-pro"
    gemini_flash_model: str = "gemini-2.5-flash"
    gemini_temperature: float = 0.2

    # Caching
    gemini_cache_ttl: int = Field(
        3600, ge=60, description="TTL in seconds for explicit Gemini caches"
    )
    gemini_explicit_cache_min_tokens: int = Field(
        4096,
        ge=1,
        description="Minimum token count to attempt explicit caching",
    )

    # Rate limiting for Gemini Flash (to avoid throttling)
    gemini_flash_delay_ms: int = Field(
        60, ge=0, description="Minimum delay between Flash API calls in ms"
    )

    # Local Ingestion (Ollama)
    ollama_base_url: str = "http://localhost:11434"
    ollama_business_model: str = "llama3.2:3b"
    ollama_embedding_model: str = "qwen3-embedding:0.6b"
    ollama_embedding_dim: int = 1024  # Standard for Qwen3-0.6b
    ollama_max_concurrent: int = 1
    ollama_keep_alive: int = Field(
        0,
        ge=0,
        description="Seconds to keep model in VRAM after request (0 = offload)",
    )
    ollama_request_timeout: int = Field(
        120, ge=10, description="Timeout in seconds for Ollama semaphore acquisition"
    )

    # Paths
    output_dir: str = "outputs"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()  # type: ignore[call-arg]
