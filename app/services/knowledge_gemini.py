"""Document processing pipeline with Graph-RAG integration.

Three-branch architecture:
  Branch A: File API upload + Context Caching (Phase 2 — existing)
  Branch B: Entity extraction via Flash + graph upsert
  Branch C: Node embedding + community detection fire-and-forget

If Branch A succeeds but B/C fail, status is set to READY_PARTIAL
instead of ERROR — the document is usable for cache-based queries
even without a complete knowledge graph.
"""

import asyncio
import os
import tempfile
import time
from datetime import timedelta
from typing import Any
from uuid import UUID

import google.generativeai as genai  # type: ignore[import-untyped]
import structlog
from google.api_core.exceptions import InvalidArgument
from sqlalchemy import select, update

from app.config import settings
from app.database import async_session_maker
from app.models.knowledge import KnowledgeDocument
from app.schemas.knowledge import KnowledgeAnswer
from app.services.community_detector import fire_community_detection
from app.services.embedding_service import embed_new_nodes
from app.services.graph_extractor import extract_entities_from_chunks, upsert_graph_data

logger = structlog.get_logger()
genai.configure(api_key=settings.gemini_api_key.get_secret_value())  # type: ignore[attr-defined]

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
    uploaded_file: Any = genai.upload_file(  # type: ignore[attr-defined]
        tmp_path,
        mime_type=mime_type,
        display_name=display_name,
    )
    elapsed = 0

    while uploaded_file.state.name == "PROCESSING":
        if elapsed >= max_wait:
            msg = f"File {uploaded_file.name} stuck in PROCESSING after {max_wait}s."
            raise TimeoutError(msg)
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        uploaded_file = genai.get_file(uploaded_file.name)  # type: ignore[attr-defined]

    if uploaded_file.state.name != "ACTIVE":
        msg = f"File upload failed. Final state: {uploaded_file.state.name}"
        raise ValueError(msg)

    return uploaded_file


def _create_cache_sync(file_info: Any) -> Any:
    """Create a Gemini cache for the uploaded file.

    This function is synchronous by design and intended to run in a thread.
    """
    return genai.caching.CachedContent.create(
        model="models/gemini-1.5-pro-002",
        system_instruction=(
            "You are a strict technical context orchestrator. "
            "Answer questions based strictly on the provided document. "
            "If the answer is not in the document, you must say 'I don't know'."
        ),
        contents=[file_info],
        ttl=timedelta(minutes=60),
    )


async def process_document_task(document_id: UUID) -> None:
    """Process a knowledge document through File API, caching, and graph extraction.

    Architecture:
      Branch A: File API + Cache (C_03 — own session)
      Branch B: Entity extraction + graph upsert (savepoint)
      Branch C: Embedding + community detection (savepoint + fire-and-forget)

    If A succeeds but B/C fail, status is READY_PARTIAL — the document is
    usable for cache queries but the knowledge graph is incomplete.
    """
    tmp_path: str | None = None
    try:
        # ── Phase 1: Fetch document data ──
        async with async_session_maker() as db:
            async with db.begin():
                result = await db.execute(
                    select(
                        KnowledgeDocument.raw_content,
                        KnowledgeDocument.title,
                        KnowledgeDocument.project_id,
                        KnowledgeDocument.metadata_json,
                    ).where(KnowledgeDocument.id == document_id)
                )
                row = result.first()

        if row is None:
            return

        raw_content = row[0]
        title = row[1]
        project_id = row[2]
        metadata: dict[str, Any] = row[3] or {}

        if raw_content is None:
            return

        is_binary_upload = bool(metadata.get("is_binary_upload"))
        encoding = str(metadata.get("encoding") or "utf-8")
        content_type = str(metadata.get("content_type") or "text/plain")
        file_suffix = str(metadata.get("file_suffix") or ".txt")

        # ── Branch A: File API + Context Caching ──
        if is_binary_upload:
            raw_bytes = raw_content.encode(encoding)
            fd, tmp_path = tempfile.mkstemp(suffix=file_suffix, text=False)
            with os.fdopen(fd, "wb") as file:
                file.write(raw_bytes)
            upload_mime = content_type
        else:
            fd, tmp_path = tempfile.mkstemp(suffix=".txt", text=True)
            with os.fdopen(fd, "w") as file:
                file.write(raw_content)
            upload_mime = "text/plain"

        file_info = await asyncio.to_thread(
            _upload_and_wait_for_active,
            tmp_path,
            title,
            upload_mime,
        )

        try:
            cache = await asyncio.to_thread(_create_cache_sync, file_info)
            update_values: dict[str, Any] = {
                "gemini_file_uri": getattr(file_info, "uri", None),
                "gemini_cache_name": getattr(cache, "name", None),
                "cache_expires_at": getattr(cache, "expire_time", None),
                "status": "READY",
            }
        except InvalidArgument as exc:
            message = str(exc).lower()
            if "minimum" in message or "32768" in message:
                update_values = {
                    "gemini_file_uri": getattr(file_info, "uri", None),
                    "gemini_cache_name": None,
                    "status": "READY",
                }
                logger.info(
                    "document_ready_uncached",
                    document_id=str(document_id),
                    reason="below_token_limit_or_cache_constraints",
                )
            else:
                raise

        # Persist Branch A results.
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

        # ── Branch B: Entity Extraction + Graph Upsert ──
        graph_success = False
        try:
            extraction = await extract_entities_from_chunks(raw_content)

            if extraction.entities:
                async with async_session_maker() as db:
                    async with db.begin():
                        # Savepoint for atomicity — if this fails, Branch A
                        # result is already committed.
                        async with db.begin_nested():
                            await upsert_graph_data(
                                db, project_id, document_id, extraction
                            )
                        graph_success = True

                logger.info(
                    "branch_b_complete",
                    document_id=str(document_id),
                    entities=len(extraction.entities),
                    relations=len(extraction.relations),
                )
            else:
                logger.info(
                    "branch_b_no_entities",
                    document_id=str(document_id),
                )
                graph_success = True  # No entities is not a failure.

        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "branch_b_failed",
                document_id=str(document_id),
                error=str(exc),
            )

        # ── Branch C: Embedding + Community Detection ──
        embedding_success = False
        try:
            if graph_success:
                async with async_session_maker() as db:
                    async with db.begin():
                        async with db.begin_nested():
                            await embed_new_nodes(db, project_id)
                        embedding_success = True

                # Fire community detection as an independent background task.
                # It owns its own session via fire_community_detection().
                asyncio.create_task(
                    fire_community_detection(project_id)
                )

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
        if not graph_success or not embedding_success:
            async with async_session_maker() as db:
                async with db.begin():
                    await db.execute(
                        update(KnowledgeDocument)
                        .where(KnowledgeDocument.id == document_id)
                        .values(status="READY_PARTIAL"),
                    )
            logger.info(
                "document_ready_partial",
                document_id=str(document_id),
                graph_success=graph_success,
                embedding_success=embedding_success,
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
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


async def answer_question_with_cache(
    question: str,
    ready_docs: list[KnowledgeDocument],
) -> KnowledgeAnswer:
    """Answer a question using hybrid cache routing (ADR-003).

    If a single cached document is available, use from_cached_content.
    Otherwise, inline the raw content of all ready documents in the prompt.
    """
    system_instruction = (
        "You are an expert Context Orchestrator for an Agentic IDE. "
        "Answer the user's question based strictly on the provided documents. "
        "You MUST provide citations (snippets from the text). "
        "If the answer cannot be found in the text, you MUST state 'I don't know'."
    )

    # Hybrid routing logic
    if (
        len(ready_docs) == 1
        and ready_docs[0].gemini_cache_name is not None
    ):
        model = genai.GenerativeModel.from_cached_content(  # type: ignore[attr-defined]
            cached_content=ready_docs[0].gemini_cache_name,
        )
        prompt = question
        logger.info(
            "qa_routing",
            strategy="cached_content",
            document_id=str(ready_docs[0].id),
        )
    else:
        model = genai.GenerativeModel(  # type: ignore[attr-defined]
            model_name="gemini-1.5-pro-002",
            system_instruction=system_instruction,
        )
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
        )

    response = await asyncio.to_thread(
        model.generate_content,
        prompt,
        generation_config=genai.GenerationConfig(  # type: ignore[attr-defined]
            response_mime_type="application/json",
            response_schema=KnowledgeAnswer,
            temperature=0.0,
        ),
    )

    return KnowledgeAnswer.model_validate_json(response.text)
