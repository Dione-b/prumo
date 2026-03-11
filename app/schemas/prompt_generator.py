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


"""Pydantic schemas for the PromptGeneratorService.

Defines the tier classification, strategy config, and the generated prompt
output with automatic confidence downgrade enforcement.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.knowledge import AnswerCitation

# Warning sentinel values that trigger confidence downgrade.
_GRAPH_BLOCKING_WARNINGS = frozenset(
    {
        "graph_local_unavailable",
        "graph_global_unavailable",
        "graph_empty",
    }
)


class PromptTier(StrEnum):
    """Complexity tier for generated prompts."""

    SIMPLE = "SIMPLE"
    COMPLEX = "COMPLEX"


class PromptStrategyConfig(BaseModel):
    """Caller-provided overrides for prompt generation behavior."""

    model_config = ConfigDict(frozen=True)

    force_tier: PromptTier | None = None
    extra_prohibited: list[str] = Field(default_factory=list)
    extra_required: list[str] = Field(default_factory=list)
    k_seeds: int = Field(default=10, ge=1, le=50)
    include_few_shot: bool = True
    include_skeletons: bool = True


class GeneratedPrompt(BaseModel):
    """Output of the prompt generation pipeline.

    The model_validator (C_01) enforces confidence downgrade when
    graph-related warnings are present, using object.__setattr__
    to mutate the frozen model during validation.
    """

    model_config = ConfigDict(frozen=True)

    yaml_prompt: str
    prompt_id: str = ""
    tier: PromptTier
    strategies_applied: list[str]
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    graph_citations: list[AnswerCitation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def enforce_confidence_downgrade(self) -> GeneratedPrompt:
        """C_01: Downgrade confidence when graph context is degraded.

        - 1 blocking warning + HIGH → MEDIUM
        - 2+ blocking warnings → LOW
        """
        blocking = _GRAPH_BLOCKING_WARNINGS.intersection(self.warnings)

        if not blocking:
            return self

        if len(blocking) >= 2:
            if self.confidence != "LOW":
                object.__setattr__(self, "confidence", "LOW")
        elif self.confidence == "HIGH":
            object.__setattr__(self, "confidence", "MEDIUM")

        return self
