"""Document processing pipeline with Graph-RAG integration.

Three-branch architecture:
  Branch A: File API upload + Context Caching (Phase 2 — existing)
  Branch B: Entity extraction via Flash + graph upsert (text-only)
  Branch C: Node embedding + community detection fire-and-forget

If Branch A succeeds but B/C fail, status is set to READY_PARTIAL
instead of ERROR — the document is usable for cache-based queries
even without a complete knowledge graph.

Binary files (PDF/DOCX) follow a streaming-only path:
  - raw_content is NULL in the database
  - temp_file_path in metadata points to the streamed file on disk
  - Branch B is skipped (Gemini extracts from the file via File API)
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from google import genai
from pypdf import PdfReader
from sqlalchemy import select, update

from app.config import settings
from app.database import async_session_maker
from app.models.knowledge import KnowledgeDocument
from app.schemas.knowledge import KnowledgeAnswer
from app.services.community_detector import fire_community_detection

logger = structlog.get_logger()
client = genai.Client(api_key=settings.gemini_api_key.get_secret_value())

MAX_POLL_SECONDS = 300
POLL_INTERVAL = 2


def _upload_and_wait_for_active(
    tmp_path: str,
    display_name: str,
    mime_type: str,
    max_wait: int = MAX_POLL_SECONDS,
) -> Any:
    """Upload a file and poll until it becomes ACTIVE.

    This function is synchronous by design and intended to run in a thread.
    """
    uploaded_file = client.files.upload(
        file=tmp_path,
        config=genai.types.UploadFileConfig(
            mime_type=mime_type,
            display_name=display_name,
        ),
    )
    elapsed = 0

    while (
        getattr(uploaded_file.state, "name", str(uploaded_file.state)) == "PROCESSING"
    ):
        if elapsed >= max_wait:
            msg = f"File {uploaded_file.name} stuck in PROCESSING after {max_wait}s."
            raise TimeoutError(msg)
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        uploaded_file = client.files.get(name=str(uploaded_file.name))

    if getattr(uploaded_file.state, "name", str(uploaded_file.state)) != "ACTIVE":
        msg = f"File upload failed. Final state: {uploaded_file.state}"
        raise ValueError(msg)

    return uploaded_file


async def process_document_task(document_id: UUID) -> None:
    """Process a knowledge document through File API, caching, and graph extraction.

    Architecture:
      Branch A: File API + Cache (C_03 — own session)
      Branch B: Entity extraction + graph upsert (text-only; skipped for binaries)
      Branch C: Embedding + community detection (savepoint + fire-and-forget)

    Binary documents (is_binary_upload=True):
      - File is read from temp_file_path on disk (streamed, no RAM spike)
      - raw_content is NULL — never materialized as string
      - Branch B is skipped (entities extracted by Gemini via File API)

    If A succeeds but B/C fail, status is READY_PARTIAL — the document is
    usable for cache queries but the knowledge graph is incomplete.
    """
    tmp_path_owned: str | None = None
    tmp_path_from_router: str | None = None

    try:
        # ── Phase 1: Fetch document data ──
        async with async_session_maker() as db:
            async with db.begin():
                result = await db.execute(
                    select(KnowledgeDocument).where(KnowledgeDocument.id == document_id)
                )
                doc = result.scalar_one_or_none()

        if doc is None:
            return

        raw_content = doc.raw_content
        title = doc.title
        project_id = doc.project_id
        metadata = doc.metadata_json or {}

        is_binary_upload = bool(metadata.get("is_binary_upload"))
        content_type = str(metadata.get("content_type") or "text/plain")
        tmp_path_from_router = metadata.get("temp_file_path")

        # ── Branch A: File API + Context Caching ──
        if is_binary_upload:
            # Binary: file already on disk (streamed by the router).
            if tmp_path_from_router and Path(tmp_path_from_router).exists():
                upload_path = tmp_path_from_router
            else:
                logger.error(
                    "binary_temp_file_missing",
                    document_id=str(document_id),
                    expected_path=tmp_path_from_router,
                )
                raise FileNotFoundError(
                    f"Temp file not found for binary document: {tmp_path_from_router}"
                )
            upload_mime = content_type

            # If it's a PDF and there's no raw_content yet,
            # extract the text so GraphExtractor can use it
            if upload_mime == "application/pdf" and not raw_content:

                def _extract_pdf(path: str) -> str:
                    try:
                        reader = PdfReader(path)
                        pages = (p.extract_text() for p in reader.pages)
                        return "\n\n".join(t for t in pages if t)
                    except Exception as e:
                        logger.error(
                            "pdf_extraction_failed",
                            error=str(e),
                            document_id=str(document_id),
                        )
                        return ""

                extracted_text = await asyncio.to_thread(_extract_pdf, upload_path)
                if extracted_text.strip():
                    raw_content = extracted_text
                    logger.info(
                        "pdf_text_extracted",
                        document_id=str(document_id),
                        length=len(raw_content),
                    )

        else:
            # Text: materialize content into a temp file for the File API.
            if raw_content is None:
                logger.warning(
                    "text_document_no_content",
                    document_id=str(document_id),
                )
                return

            fd, tmp_path_owned = tempfile.mkstemp(suffix=".txt", text=True)
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                file.write(raw_content)
            upload_path = tmp_path_owned
            upload_mime = "text/plain"

        file_info = await asyncio.to_thread(
            _upload_and_wait_for_active,
            upload_path,
            title,
            upload_mime,
        )

        from app.services.knowledge_orchestrator import KnowledgeOrchestrator

        orchestrator = KnowledgeOrchestrator()
        try:
            update_values = await orchestrator.process_document_caching(
                doc=doc,
                file_info=file_info,
            )
        except Exception as exc:
            logger.error("orchestrator_caching_failed", error=str(exc))
            update_values = {
                "gemini_file_uri": (
                    getattr(file_info, "uri", getattr(file_info, "name", None))
                    if file_info
                    else None
                ),
                "status": "READY_PARTIAL",
            }

        # Persist Branch A results.
        if raw_content and is_binary_upload:
            update_values["raw_content"] = raw_content

        async with async_session_maker() as db:
            async with db.begin():
                await db.execute(
                    update(KnowledgeDocument)
                    .where(KnowledgeDocument.id == document_id)
                    .values(**update_values),
                )

        logger.info(
            "branch_a_complete",
            document_id=str(document_id),
            status=update_values.get("status", "READY"),
        )

        # ── Branch B: Entity Extraction + Graph Upsert (Atomic Swap) ──
        from app.services.graph_extractor import (
            extract_graph_data,
            remove_document_graph_data,
            upsert_graph_data,
        )

        # Gating: force entity extraction if we have raw_content (even for PDFs).
        extraction_is_binary = is_binary_upload if not raw_content else False

        graph_success = False
        reprocess_failed = False
        reprocess_error_msg = ""

        # 1. Extração Isolada e Validação Prévia Pydantic
        try:
            extraction, embeddings, skip_reason = await extract_graph_data(
                raw_content=raw_content, is_binary=extraction_is_binary
            )

            if skip_reason:
                logger.info(
                    "branch_b_skipped",
                    document_id=str(document_id),
                    reason=skip_reason,
                )
                graph_success = True
            elif extraction:
                # 3. Transação de Troca (Swap)
                async with async_session_maker() as extraction_db:
                    async with extraction_db.begin():
                        # Deletar dados antigos do document_id
                        await remove_document_graph_data(extraction_db, document_id)
                        # Inserir novos dados validados
                        await upsert_graph_data(
                            extraction_db,
                            project_id,
                            document_id,
                            extraction,
                            embeddings,
                        )

                graph_success = True
                logger.info(
                    "branch_b_complete",
                    document_id=str(document_id),
                    entities=len(extraction.entities),
                    relations=len(extraction.relations),
                )
        except Exception as exc:  # noqa: BLE001
            # 2. Validação falhou -> Dispara log e dados antigos ficam INTACTOS.
            logger.error(
                "branch_b_extraction_failed",
                document_id=str(document_id),
                error=str(exc),
            )
            reprocess_failed = True
            reprocess_error_msg = (
                f"Falha no Reprocessamento: Verifique os Logs ({str(exc)[:50]})"
            )

        # ── Branch C: Community Detection ──
        community_detection_success = False
        try:
            if graph_success:
                # Fire community detection as an independent background task.
                # It owns its own session via fire_community_detection().
                asyncio.create_task(fire_community_detection(project_id))
                community_detection_success = True

                logger.info(
                    "branch_c_complete",
                    document_id=str(document_id),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "branch_c_failed",
                document_id=str(document_id),
                error=str(exc),
            )

        # ── Final status update ──
        if not graph_success or not community_detection_success:
            async with async_session_maker() as db:
                async with db.begin():
                    # Handle atomic reprocess fallback:
                    # Se falhou na validação de uma re-extração, os dados antigos
                    # não foram apagados graças ao Swap Atômico. Mantemos o READY
                    # e só reportamos o erro no metadata. Se for primeira vez, READY_PARTIAL.
                    final_status = "READY" if reprocess_failed else "READY_PARTIAL"

                    # Merge metadata
                    doc_result = await db.execute(
                        select(KnowledgeDocument).where(
                            KnowledgeDocument.id == document_id
                        )
                    )
                    doc_current = doc_result.scalar_one()
                    meta = doc_current.metadata_json or {}

                    if reprocess_failed:
                        meta["reprocess_error"] = reprocess_error_msg
                    else:
                        meta.pop("reprocess_error", None)

                    await db.execute(
                        update(KnowledgeDocument)
                        .where(KnowledgeDocument.id == document_id)
                        .values(status=final_status, metadata_json=meta)
                    )

            logger.info(
                "document_ready_partial_or_reprocess",
                document_id=str(document_id),
                graph_success=graph_success,
                community_detection_success=community_detection_success,
                reprocess_failed=reprocess_failed,
            )
        else:
            logger.info(
                "document_fully_processed",
                document_id=str(document_id),
            )

    except Exception as exc:  # noqa: BLE001
        async with async_session_maker() as db:
            async with db.begin():
                await db.execute(
                    update(KnowledgeDocument)
                    .where(KnowledgeDocument.id == document_id)
                    .values(
                        status="ERROR",
                        metadata_json={"error": str(exc)},
                    ),
                )

        logger.error(
            "document_processing_failed",
            document_id=str(document_id),
            error=str(exc),
        )
    finally:
        # Clean up temp files — both the one created here and from the router.
        if tmp_path_owned and os.path.exists(tmp_path_owned):
            os.unlink(tmp_path_owned)
        if tmp_path_from_router and os.path.exists(tmp_path_from_router):
            os.unlink(tmp_path_from_router)


async def answer_question_with_cache(
    question: str,
    ready_docs: list[KnowledgeDocument],
) -> KnowledgeAnswer:
    """Answer a question using hybrid cache routing (ADR-003).

    If a single cached document is available, use from_cached_content.
    Otherwise, inline the raw content of all ready documents in the prompt.
    Binary documents without raw_content are accessed via gemini_file_uri.
    """
    system_instruction = (
        "You are an expert Context Orchestrator for an Agentic IDE. "
        "Answer the user's question based strictly on the provided documents. "
        "You MUST provide citations (snippets from the text). "
        "If the answer cannot be found in the text, you MUST state 'I don't know'."
    )

    if len(ready_docs) == 1 and ready_docs[0].gemini_cache_name is not None:
        from app.services.gemini_client import GeminiClient

        gemini_client = GeminiClient()
        logger.info(
            "qa_routing",
            strategy="cached_content",
            document_id=str(ready_docs[0].id),
        )
        return await gemini_client.generate_with_cache(
            cache_name=ready_docs[0].gemini_cache_name,
            prompt=question,
            schema=KnowledgeAnswer,
            model=settings.gemini_synthesis_model,
        )

    # Inline fallback
    context_blocks = [
        f"--- DOCUMENT: {doc.title} ---\n{doc.raw_content}\n"
        for doc in ready_docs
        if doc.raw_content
    ]
    combined_context = "\n".join(context_blocks)
    prompt = f"CONTEXT:\n{combined_context}\n\nQUESTION:\n{question}"
    logger.info(
        "qa_routing",
        strategy="inline_context",
        documents=len(ready_docs),
        text_docs=len(context_blocks),
    )

    def sync_generate() -> KnowledgeAnswer:
        response = client.models.generate_content(
            model=settings.gemini_synthesis_model,
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=KnowledgeAnswer,
                temperature=0.0,
                system_instruction=system_instruction,
            ),
        )
        # Ensure we pass str to model_validate_json
        return KnowledgeAnswer.model_validate_json(str(response.text))

    answer = await asyncio.to_thread(sync_generate)

    # C_01: Enforce confidence downgrades if cache-routing fails
    if answer.confidence_level == "HIGH":
        object.__setattr__(answer, "confidence_level", "MEDIUM")

    return answer
