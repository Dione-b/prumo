from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    question: str = Field(..., min_length=1, max_length=4000)
    session_id: str = Field(..., min_length=1, max_length=255)
    history: list[ChatMessage] = Field(default_factory=list)


class SourceReference(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    source_url: str


class ChatResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    answer: str
    sources: list[SourceReference]
    session_id: str
