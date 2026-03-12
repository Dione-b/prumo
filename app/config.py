# Copyright (C) 2026 Dione Bastos
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.


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

    # Embedding
    gemini_embedding_model: str = "text-embedding-004"
    gemini_embedding_dim: int = 768

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

    # Storage and Config
    prompt_storage_backend: str = "database"  # "local", "database", "both"
    graph_invalid_threshold: float = Field(
        0.3,
        ge=0.0,
        le=1.0,
        description="Percentual de limites para invalidar circuit breaker no graphql.",
    )
    graph_worker_url: str = "http://localhost:8090"
    graph_worker_timeout_seconds: float = Field(
        10.0,
        gt=0.0,
        description="Timeout em segundos para chamadas ao graph worker remoto.",
    )
    graph_worker_max_retries: int = Field(
        3,
        ge=0,
        description="Numero maximo de retries do adapter remoto de graph worker.",
    )

    # Paths
    output_dir: str = "outputs"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()  # type: ignore[call-arg]

