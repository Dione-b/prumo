from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, PrivateAttr, model_validator


class DocumentIngestRequest(BaseModel):
    project_id: UUID
    title: str = Field(..., max_length=255)
    content: str | None = None
    source_type: str
    metadata: dict[str, Any] | None = None


class AnswerCitation(BaseModel):
    document_id: UUID | None = None
    snippet: str


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


class CacheRefreshingResponse(BaseModel):
    status: str
    stale_document_ids: list[str]
    retry_after_seconds: int


