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


from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, PrivateAttr, model_validator


class DocumentIngestRequest(BaseModel):
    project_id: UUID
    title: str = Field(..., max_length=255)
    content: str | None = None
    source_type: str


class AnswerCitation(BaseModel):
    document_id: UUID | None = None
    snippet: str
    source: str | None = Field(
        default=None,
        description="Human-readable source label (doc title or relevance).",
    )

    @model_validator(mode="after")
    def coerce_source_from_document(self) -> "AnswerCitation":
        """Garante source sempre preenchido quando há document_id."""
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

    @property
    def warnings(self) -> list[str]:
        return self._warnings
