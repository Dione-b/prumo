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


"""Knowledge orchestrator — RAG simples via pgvector.

Fluxo de query:
  1. Gerar embedding da pergunta via Qwen3
  2. Buscar top-K documentos por cosine similarity (pgvector)
  3. Passar contexto ao Gemini para síntese
"""

from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.knowledge import KnowledgeAnswer
from app.services.embedding_service import EmbeddingService
from app.services.knowledge_gemini import answer_question

logger = structlog.get_logger()

TOP_K_DOCUMENTS = 5


async def query_rag(
    db: AsyncSession,
    project_id: UUID,
    question: str,
) -> KnowledgeAnswer | None:
    """Executa RAG simples: embedding da pergunta → busca vetorial → síntese Gemini.

    Returns:
        KnowledgeAnswer com resposta, ou None se não há documentos.
    """
    # 1. Gerar embedding da pergunta
    embedding_service = EmbeddingService()
    question_embeddings = await embedding_service.embed_batch([question])

    if not question_embeddings:
        logger.warning("query_embedding_failed", project_id=str(project_id))
        return None

    question_embedding = question_embeddings[0]

    # 2. Buscar top-K documentos por cosine similarity
    embedding_str = "[" + ",".join(str(v) for v in question_embedding) + "]"

    stmt = text(
        """
        SELECT id, title, content,
               1 - (embedding <=> :query_embedding::vector) AS similarity
        FROM knowledge_documents
        WHERE project_id = :project_id
          AND status = 'READY'
          AND embedding IS NOT NULL
        ORDER BY embedding <=> :query_embedding::vector
        LIMIT :top_k
        """
    )

    result = await db.execute(
        stmt,
        {
            "query_embedding": embedding_str,
            "project_id": str(project_id),
            "top_k": TOP_K_DOCUMENTS,
        },
    )
    rows = result.fetchall()

    if not rows:
        return None

    # 3. Montar contexto e sintetizar via Gemini
    context_docs: list[tuple[str, str]] = [
        (row.title, row.content) for row in rows if row.content
    ]

    logger.info(
        "rag_query",
        project_id=str(project_id),
        documents_found=len(context_docs),
        top_similarity=float(rows[0].similarity) if rows else 0,
    )

    return await answer_question(question, context_docs)
