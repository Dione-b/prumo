# Copyright (C) 2026 Dione Bastos
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]
from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.config import settings

from . import Base

EMBEDDING_DIMENSIONS = settings.gemini_embedding_dim


class CookbookRecipe(Base):
    """Armazena uma receita extraída com embeddings vetoriais para busca estruturada."""

    __tablename__ = "cookbook_recipes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(String(50), nullable=False)
    prerequisites: Mapped[str | None] = mapped_column(Text, nullable=True)
    steps: Mapped[str] = mapped_column(Text, nullable=False)

    # Store dynamic schema structs directly
    code_snippets: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB, nullable=True
    )
    references: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    source_document_ids: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="published")

    embedding: Mapped[list[float] | None] = mapped_column(  # type: ignore[assignment]
        Vector(EMBEDDING_DIMENSIONS),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=func.now(),
    )
