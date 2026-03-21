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


from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.config import settings

from . import Base

EMBEDDING_DIMENSIONS = settings.gemini_embedding_dim


class KnowledgeDocument(Base):
    """Documento de conhecimento com embedding vetorial para RAG."""

    __tablename__ = "knowledge_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

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

    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'READY', 'ERROR')",
            name="ck_knowledge_status_valid",
        ),
    )
