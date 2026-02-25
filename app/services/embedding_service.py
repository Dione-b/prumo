"""Embedding service for graph nodes using text-embedding-004.

Fetches nodes with missing embeddings from the database, generates
embeddings in batches of 20 via genai.embed_content(), and writes them
back. This service NEVER calls session.commit() — the transaction
boundary belongs to the task owner (C_03).
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import google.generativeai as genai  # type: ignore[import-untyped]
import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.graph import EMBEDDING_DIMENSIONS, GraphNode

logger = structlog.get_logger()

genai.configure(api_key=settings.gemini_api_key.get_secret_value())  # type: ignore[attr-defined]

_EMBEDDING_MODEL = "models/text-embedding-004"
_BATCH_SIZE = 20  # text-embedding-004 limit per request.
_TASK_TYPE = "RETRIEVAL_DOCUMENT"


def _embed_batch_sync(texts: list[str]) -> list[list[float]]:
    """Synchronous call to genai.embed_content — runs in thread.

    Returns a list of embedding vectors (768d each).
    """
    result = genai.embed_content(  # type: ignore[attr-defined]
        model=_EMBEDDING_MODEL,
        content=texts,
        task_type=_TASK_TYPE,
        output_dimensionality=EMBEDDING_DIMENSIONS,
    )
    return result["embedding"]  # type: ignore[no-any-return]


async def embed_new_nodes(
    session: AsyncSession,
    project_id: UUID,
) -> int:
    """Generate embeddings for all graph nodes that don't have one yet.

    Processes in batches of 20. Does NOT call session.commit() — the
    transaction boundary belongs to the task owner (C_03).

    Returns the number of newly embedded nodes.
    """
    stmt = select(GraphNode.id, GraphNode.name, GraphNode.description).where(
        GraphNode.project_id == project_id,
        GraphNode.embedding.is_(None),  # type: ignore[union-attr]
    )
    result = await session.execute(stmt)
    rows = result.all()

    if not rows:
        return 0

    total_embedded = 0

    for batch_start in range(0, len(rows), _BATCH_SIZE):
        batch = rows[batch_start : batch_start + _BATCH_SIZE]

        # Build text representations: "name: description"
        texts = [f"{row[1]}: {row[2]}" for row in batch]
        node_ids = [row[0] for row in batch]

        embeddings = await asyncio.to_thread(_embed_batch_sync, texts)

        for node_id, embedding in zip(node_ids, embeddings):
            await session.execute(
                update(GraphNode)
                .where(GraphNode.id == node_id)
                .values(embedding=embedding)
            )

        total_embedded += len(batch)

    await session.flush()

    logger.info(
        "nodes_embedded",
        project_id=str(project_id),
        total_embedded=total_embedded,
    )

    return total_embedded
