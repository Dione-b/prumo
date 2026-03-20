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

    # Cloud Synthesis (Gemini)
    gemini_api_key: SecretStr
    gemini_synthesis_model: str = "gemini-2.5-pro"
    gemini_temperature: float = 0.2

    # Storage
    prompt_storage_backend: str = "database"  # "local", "database", "both"

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

    # Paths
    output_dir: str = "outputs"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()  # type: ignore[call-arg]
