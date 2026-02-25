import asyncio
import os
import tempfile
import time
from datetime import timedelta
from typing import Any
from uuid import UUID

import google.generativeai as genai
import structlog
from google.api_core.exceptions import InvalidArgument
from sqlalchemy import select, update

from app.config import settings
from app.database import async_session_maker
from app.models.knowledge import KnowledgeDocument
from app.schemas.knowledge import KnowledgeAnswer

logger = structlog.get_logger()
genai.configure(api_key=settings.gemini_api_key.get_secret_value())  # type: ignore[attr-defined]

MAX_POLL_SECONDS = 300
POLL_INTERVAL = 2


def _upload_and_wait_for_active(
    tmp_path: str,
    display_name: str,
    max_wait: int = MAX_POLL_SECONDS,
) -> Any:
    """Upload a file and poll until it becomes ACTIVE.

    This function is synchronous by design and intended to run in a thread.
    """
    uploaded_file: Any = genai.upload_file(  # type: ignore[attr-defined]
        tmp_path,
        mime_type="text/plain",
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
    """Process a knowledge document through Gemini File API and Context Caching.

    Three phases:
    1) Read raw content from the database.
    2) Perform blocking File API + cache creation in a worker thread.
    3) Persist the resulting URIs / cache metadata in a fresh transaction.
    """
    tmp_path: str | None = None
    try:
        # Phase 1: fetch scalars only, then close the session.
        async with async_session_maker() as db:
            async with db.begin():
                result = await db.execute(
                    select(
                        KnowledgeDocument.raw_content,
                        KnowledgeDocument.title,
                    ).where(KnowledgeDocument.id == document_id)
                )
                row = result.first()

        if row is None:
            return

        raw_content = row[0]
        title = row[1]

        if raw_content is None:
            return

        # Phase 2: blocking I/O and SDK calls, no DB session open.
        fd, tmp_path = tempfile.mkstemp(suffix=".txt", text=True)
        with os.fdopen(fd, "w") as file:
            file.write(raw_content)

        file_info = await asyncio.to_thread(
            _upload_and_wait_for_active,
            tmp_path,
            title,
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
            # Handle cases where the document is below the minimum cache size
            # or violates token limits. In that scenario we still keep the file
            # reference but skip cache usage.
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

        # Phase 3: write result in a new transaction with explicit UPDATE.
        async with async_session_maker() as db:
            async with db.begin():
                await db.execute(
                    update(KnowledgeDocument)
                    .where(KnowledgeDocument.id == document_id)
                    .values(**update_values),
                )

        logger.info(
            "document_processed",
            document_id=str(document_id),
            status=update_values.get("status", "READY"),
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
        # Option 1: Single cached document via Context Caching API.
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
        # Option 2: Multi-document or uncached, inline context.
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

    # Execute LLM call with structured outputs enforced via response_schema.
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

