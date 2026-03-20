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


"""Pipeline de processamento de documentos e RAG simples.

Fluxo de ingestão:
  1. Extrai texto de PDF se necessário (via pypdf)
  2. Gera embedding via Ollama/Qwen3
  3. Salva embedding e marca como READY

Fluxo de query:
  1. Gera embedding da pergunta
  2. Busca top-K docs por cosine similarity (via query_rag)
  3. Sintetiza resposta via Gemini (inline context)
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import structlog
from google import genai
from pypdf import PdfReader
from sqlalchemy import select, update

from app.config import settings
from app.database import async_session_maker
from app.models.knowledge import KnowledgeDocument
from app.schemas.knowledge import KnowledgeAnswer
from app.services.embedding_service import EmbeddingService

logger = structlog.get_logger()
gemini_client = genai.Client(api_key=settings.gemini_api_key.get_secret_value())


def _extract_pdf_text(path: str) -> str:
    """Extrai texto de um PDF — síncrono, executar via to_thread."""
    try:
        reader = PdfReader(path)
        pages = (p.extract_text() for p in reader.pages)
        return "\n\n".join(t for t in pages if t)
    except Exception as e:
        logger.error("pdf_extraction_failed", error=str(e), path=path)
        return ""


async def process_document_task(document_id: UUID) -> None:
    """Processa documento: extrai texto, gera embedding, marca READY.

    C_03: Usa sessão própria — nunca compartilha transação.
    """
    try:
        # 1. Buscar documento
        async with async_session_maker() as db:
            async with db.begin():
                result = await db.execute(
                    select(KnowledgeDocument).where(
                        KnowledgeDocument.id == document_id
                    )
                )
                doc = result.scalar_one_or_none()

        if doc is None:
            return

        content = doc.content
        title = doc.title

        # 2. Extrair texto de PDF se necessário
        if doc.source_type == "application/pdf" and not content:
            # Verificar se há path temporário — fallback para content vazio
            logger.info("pdf_extraction_start", document_id=str(document_id))
            # Para PDFs, o content já deveria estar preenchido pelo router
            # Se não estiver, marcar como ERROR
            if not content:
                async with async_session_maker() as db:
                    async with db.begin():
                        await db.execute(
                            update(KnowledgeDocument)
                            .where(KnowledgeDocument.id == document_id)
                            .values(
                                status="ERROR",
                                error_message="PDF sem conteúdo textual extraído",
                            ),
                        )
                return

        if not content or not content.strip():
            async with async_session_maker() as db:
                async with db.begin():
                    await db.execute(
                        update(KnowledgeDocument)
                        .where(KnowledgeDocument.id == document_id)
                        .values(
                            status="ERROR",
                            error_message="Documento sem conteúdo textual",
                        ),
                    )
            return

        # 3. Gerar embedding via Qwen3
        embedding_service = EmbeddingService()
        embeddings = await embedding_service.embed_batch([content])

        if not embeddings:
            async with async_session_maker() as db:
                async with db.begin():
                    await db.execute(
                        update(KnowledgeDocument)
                        .where(KnowledgeDocument.id == document_id)
                        .values(
                            status="ERROR",
                            error_message="Falha ao gerar embedding",
                        ),
                    )
            return

        # 4. Persistir embedding e marcar READY
        async with async_session_maker() as db:
            async with db.begin():
                await db.execute(
                    update(KnowledgeDocument)
                    .where(KnowledgeDocument.id == document_id)
                    .values(
                        embedding=embeddings[0],
                        status="READY",
                    ),
                )

        logger.info(
            "document_processed",
            document_id=str(document_id),
            title=title,
        )

    except Exception as exc:  # noqa: BLE001
        async with async_session_maker() as db:
            async with db.begin():
                await db.execute(
                    update(KnowledgeDocument)
                    .where(KnowledgeDocument.id == document_id)
                    .values(
                        status="ERROR",
                        error_message=str(exc)[:500],
                    ),
                )

        logger.error(
            "document_processing_failed",
            document_id=str(document_id),
            error=str(exc),
        )


async def answer_question(
    question: str,
    context_docs: list[tuple[str, str]],
) -> KnowledgeAnswer:
    """Sintetiza resposta usando Gemini com contexto inline.

    Args:
        question: Pergunta do usuário.
        context_docs: Lista de (title, content) dos docs relevantes.

    Returns:
        KnowledgeAnswer com resposta estruturada.
    """
    system_instruction = (
        "You are an expert Context Orchestrator. "
        "Answer the user's question based strictly on the provided documents. "
        "You MUST provide citations (snippets from the text). "
        "If the answer cannot be found in the text, you MUST state 'I don't know'."
    )

    context_blocks = [
        f"--- DOCUMENT: {title} ---\n{content}\n"
        for title, content in context_docs
        if content
    ]
    combined_context = "\n".join(context_blocks)
    prompt = f"CONTEXT:\n{combined_context}\n\nQUESTION:\n{question}"

    logger.info(
        "qa_routing",
        strategy="inline_context",
        documents=len(context_docs),
    )

    def sync_generate() -> KnowledgeAnswer:
        response = gemini_client.models.generate_content(
            model=settings.gemini_synthesis_model,
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=KnowledgeAnswer,
                temperature=0.0,
                system_instruction=system_instruction,
            ),
        )
        return KnowledgeAnswer.model_validate_json(str(response.text))

    return await asyncio.to_thread(sync_generate)
