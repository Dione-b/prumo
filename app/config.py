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


from pydantic import SecretStr
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

    # Model Choices
    gemini_extraction_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "text-embedding-004"
    gemini_embedding_dim: int = 768

    # Cookbook Settings
    cookbook_auto_generation: bool = True

    # Paths
    output_dir: str = "outputs"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()  # type: ignore[call-arg]
