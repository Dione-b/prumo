"""Knowledge query and ingestion orchestrator.

Handles document ingestion scheduling and query routing between cache-based
(Phase 2) and graph-based (Phase 3) query modes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import structlog
from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeDocument
from app.schemas.knowledge import (
    CacheRefreshingResponse,
    DocumentIngestRequest,
    KnowledgeAnswer,
    QueryMode,
)
from app.services.graph_query_service import global_query, hybrid_query, local_query
from app.services.knowledge_gemini import (
    answer_question_with_cache,
    process_document_task,
)

logger = structlog.get_logger()

# Statuses considered "usable" for queries (Phase 2 + Phase 3 compatible).
_QUERYABLE_STATUSES = ("READY", "READY_PARTIAL", "PROCESSING")


async def orchestrate_ingestion(
    request: DocumentIngestRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession,
) -> tuple[KnowledgeDocument, bool]:
    """Create or reuse a knowledge document and schedule background processing.

    Returns a tuple (document, is_existing).
    """
    stmt = select(KnowledgeDocument).where(
        KnowledgeDocument.project_id == request.project_id,
        KnowledgeDocument.title == request.title,
        KnowledgeDocument.source_type == request.source_type,
    )
    result = await db.execute(stmt)
    existing_doc: KnowledgeDocument | None = result.scalar_one_or_none()

    if existing_doc and existing_doc.status in ("PROCESSING", "READY", "READY_PARTIAL"):
        return existing_doc, True

    new_doc = KnowledgeDocument(
        project_id=request.project_id,
        title=request.title,
        source_type=request.source_type,
        raw_content=request.content,
        metadata_json=request.metadata,
        status="PROCESSING",
    )
    db.add(new_doc)
    await db.commit()
    await db.refresh(new_doc)

    background_tasks.add_task(process_document_task, new_doc.id)
    return new_doc, False


async def orchestrate_batch_ingestion(
    requests: list[DocumentIngestRequest],
    background_tasks: BackgroundTasks,
    db: AsyncSession,
) -> list[KnowledgeDocument]:
    """Create or reuse multiple knowledge documents and schedule background processing.

    Returns the list of documents created or reused.
    """
    if not requests:
        return []

    project_id = requests[0].project_id
    titles = [req.title for req in requests]
    source_types = list({req.source_type for req in requests})

    # Fetch existing documents in one query
    stmt = select(KnowledgeDocument).where(
        KnowledgeDocument.project_id == project_id,
        KnowledgeDocument.title.in_(titles),
        KnowledgeDocument.source_type.in_(source_types),
    )
    result = await db.execute(stmt)
    existing_docs = {
        (doc.title, doc.source_type): doc
        for doc in result.scalars().all()
        if doc.status in ("PROCESSING", "READY", "READY_PARTIAL")
    }

    final_docs: list[KnowledgeDocument] = []
    new_docs: list[KnowledgeDocument] = []

    for req in requests:
        existing = existing_docs.get((req.title, req.source_type))
        if existing:
            final_docs.append(existing)
            continue

        new_doc = KnowledgeDocument(
            project_id=req.project_id,
            title=req.title,
            source_type=req.source_type,
            raw_content=req.content,
            metadata_json=req.metadata,
            status="PROCESSING",
        )
        db.add(new_doc)
        new_docs.append(new_doc)
        final_docs.append(new_doc)

    if new_docs:
        await db.commit()
        for doc in new_docs:
            await db.refresh(doc)
            background_tasks.add_task(process_document_task, doc.id)

    return final_docs


async def orchestrate_query(
    project_id: UUID,
    question: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession,
    mode: QueryMode = "hybrid",
) -> KnowledgeAnswer | CacheRefreshingResponse | None:
    """Perform a knowledge query with mode-based routing.

    Modes:
      - 'local':  Graph-only query via pgvector + CTE traversal.
      - 'global': Graph-only query via community summaries.
      - 'hybrid': Graph query first, falls back to cache if graph is empty.

    Returns:
    - KnowledgeAnswer when a query can be executed.
    - CacheRefreshingResponse when caches are stale or still processing.
    - None when no documents exist for the project.
    """
    stmt = select(KnowledgeDocument).where(
        KnowledgeDocument.project_id == project_id,
        KnowledgeDocument.status.in_(list(_QUERYABLE_STATUSES)),
    )
    result = await db.execute(stmt)
    documents = list(result.scalars().all())

    if not documents:
        return None

    # ── Handle stale caches ──
    stale_docs: list[KnowledgeDocument] = []
    now = datetime.now(UTC)

    for doc in documents:
        if doc.cache_expires_at and doc.cache_expires_at < now:
            if doc.status != "PROCESSING":
                stale_docs.append(doc)

    if stale_docs:
        for doc in stale_docs:
            doc.status = "PROCESSING"
            background_tasks.add_task(process_document_task, doc.id)
        await db.commit()

        return CacheRefreshingResponse(
            status="CACHE_REFRESHING",
            stale_document_ids=[str(d.id) for d in stale_docs],
            retry_after_seconds=30,
        )

    # ── Route based on mode ──
    ready_docs = [
        doc
        for doc in documents
        if doc.status in ("READY", "READY_PARTIAL")
        and (doc.gemini_cache_name or doc.raw_content)
    ]

    if not ready_docs:
        return CacheRefreshingResponse(
            status="PROCESSING_WAIT",
            stale_document_ids=[],
            retry_after_seconds=5,
        )

    # Try graph-based query for explicit graph modes.
    if mode in ("local", "global"):
        try:
            if mode == "local":
                return await local_query(db, project_id, question)
            return await global_query(db, project_id, question)
        except Exception:  # noqa: BLE001
            logger.warning(
                "graph_query_failed_fallback_cache",
                project_id=str(project_id),
                mode=mode,
            )
            # Fall back to cache-based query.
            return await answer_question_with_cache(question, ready_docs)

    # Hybrid mode: try graph first, fall back to cache.
    try:
        answer = await hybrid_query(db, project_id, question)

        # If the graph returned a meaningful answer, use it.
        if answer.confidence_level != "LOW" or answer.citations:
            return answer

    except Exception:  # noqa: BLE001
        logger.info(
            "hybrid_graph_empty_fallback_cache",
            project_id=str(project_id),
        )

    # Fallback: cache-based query (Phase 2 behavior).
    return await answer_question_with_cache(question, ready_docs)
