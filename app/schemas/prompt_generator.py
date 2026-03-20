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


"""Pydantic schemas para o PromptGeneratorService."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PromptStrategyConfig(BaseModel):
    """Overrides do caller para geração de prompts."""

    model_config = ConfigDict(frozen=True)

    extra_prohibited: list[str] = Field(default_factory=list)
    extra_required: list[str] = Field(default_factory=list)


class GeneratedPrompt(BaseModel):
    """Output do pipeline de geração de prompt."""

    model_config = ConfigDict(frozen=True)

    yaml_prompt: str
    prompt_id: str = ""
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    strategies_applied: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
