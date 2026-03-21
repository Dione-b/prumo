from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class CodeSnippetSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    language: str
    code: str
    description: str | None = None


class CookbookRecipeSchema(BaseModel):
    title: str
    description: str
    domain: str
    prerequisites: str | None = None
    steps: str
    code_snippets: list[CodeSnippetSchema] | None = None
    references: list[str] | None = None


class RecipeExtractionResponse(BaseModel):
    """Schema principal esperado no retorno de JSON da Gemini."""

    recipes: list[CookbookRecipeSchema]


class CookbookRecipeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str
    domain: str
    prerequisites: str | None
    steps: str
    code_snippets: list[dict[str, Any]] | None
    references: list[str] | None
    source_document_ids: list[str] | None
    status: str
    created_at: datetime
    updated_at: datetime | None
