from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]
from sqlalchemy import DateTime as SADateTime
from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from . import Base

EMBEDDING_DIMENSIONS = 768


class GraphNode(Base):
    """Entity node in the knowledge graph.

    Each node represents a named entity extracted from ingested documents.
    Embeddings are generated asynchronously via text-embedding-004 and stored
    as pgvector Vector(768) for HNSW cosine-similarity search.
    """

    __tablename__ = "graph_nodes"

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
    name: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # pgvector Vector(768) — type: ignore because pgvector stubs are untyped.
    embedding: Mapped[list[float] | None] = mapped_column(  # type: ignore[assignment]
        Vector(EMBEDDING_DIMENSIONS),
        nullable=True,
    )

    source_document_ids: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="'[]'::jsonb",
    )
    community_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        SADateTime(timezone=True),
        default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        SADateTime(timezone=True),
        nullable=True,
        onupdate=func.now(),
    )

    __table_args__ = (
        # Unique entity name per project.
        {"info": {"uq_project_name": True}},
    )


class GraphEdge(Base):
    """Directed relation between two graph nodes.

    Edges carry a relation_type, description, weight and confidence level
    extracted by the LLM. source_document_ids tracks provenance.
    """

    __tablename__ = "graph_edges"

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
    source_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("graph_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("graph_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    relation_type: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    confidence: Mapped[str] = mapped_column(
        String(10), nullable=False, default="MEDIUM"
    )

    source_document_ids: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="'[]'::jsonb",
    )

    created_at: Mapped[datetime] = mapped_column(
        SADateTime(timezone=True),
        default=func.now(),
    )
