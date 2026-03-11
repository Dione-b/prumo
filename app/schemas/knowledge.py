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


from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, PrivateAttr, model_validator

# Query mode for the /knowledge/query endpoint.
QueryMode = Literal["local", "global", "hybrid"]


class DocumentIngestRequest(BaseModel):
    project_id: UUID
    title: str = Field(..., max_length=255)
    content: str | None = None
    source_type: str
    metadata: dict[str, Any] | None = None


class AnswerCitation(BaseModel):
    document_id: UUID | None = None
    snippet: str
    source: str | None = Field(
        default=None,
        description="Human-readable source label (entity name or doc title).",
    )

    @model_validator(mode="after")
    def coerce_source_from_entity(self) -> "AnswerCitation":
        """Ensure source is always populated for Phase 2 compatibility."""
        if self.source is None and self.document_id is not None:
            object.__setattr__(self, "source", f"doc:{self.document_id}")
        return self


class KnowledgeAnswer(BaseModel):
    answer: str
    confidence_level: Literal["HIGH", "MEDIUM", "LOW"]
    citations: list[AnswerCitation] = Field(default_factory=list)

    _warnings: list[str] = PrivateAttr(default_factory=list)

    @model_validator(mode="after")
    def apply_quality_penalties(self) -> "KnowledgeAnswer":
        if self.citations:
            return self

        warnings: list[str] = []

        if self.confidence_level in ("HIGH", "MEDIUM"):
            object.__setattr__(self, "confidence_level", "LOW")
            warnings.append(
                "Confidence downgraded to LOW: answer provided without document "
                "citations."
            )

        abstention_tokens = [
            "don't know",
            "não sei",
            "desconheço",
            "sem informação",
            "no sé",
        ]
        is_abstaining = any(token in self.answer.lower() for token in abstention_tokens)

        if not is_abstaining:
            warnings.append(
                "Answer provided without direct document citations. "
                "High risk of hallucination."
            )

        if warnings:
            object.__setattr__(self, "_warnings", warnings)

        return self

    @model_validator(mode="after")
    def apply_c_01_downgrades(self) -> "KnowledgeAnswer":
        """Downgrade to MEDIUM if explicit cache was unavailable."""
        if any("explicit_cache_unavailable" in w for w in self._warnings):
            if self.confidence_level == "HIGH":
                object.__setattr__(self, "confidence_level", "MEDIUM")
        return self

    @property
    def warnings(self) -> list[str]:
        return self._warnings


class CacheRefreshingResponse(BaseModel):
    status: str
    stale_document_ids: list[str]
    retry_after_seconds: int
