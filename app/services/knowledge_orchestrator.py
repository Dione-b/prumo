from datetime import UTC, datetime
from uuid import UUID

from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeDocument
from app.schemas.knowledge import (
    CacheRefreshingResponse,
    DocumentIngestRequest,
    KnowledgeAnswer,
)
from app.services.knowledge_gemini import (
    answer_question_with_cache,
    process_document_task,
)


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

    if existing_doc and existing_doc.status in ("PROCESSING", "READY"):
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


async def orchestrate_query(
    project_id: UUID,
    question: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession,
) -> KnowledgeAnswer | CacheRefreshingResponse | None:
    """Perform a knowledge query with cache refresh and processing state handling.

    Returns:
    - KnowledgeAnswer when a query can be executed.
    - CacheRefreshingResponse when caches are stale or still processing.
    - None when no documents exist for the project.
    """
    stmt = select(KnowledgeDocument).where(
        KnowledgeDocument.project_id == project_id,
        KnowledgeDocument.status.in_(["READY", "PROCESSING"]),
    )
    result = await db.execute(stmt)
    documents = list(result.scalars().all())

    if not documents:
        return None

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

    ready_and_active_docs = [
        doc
        for doc in documents
        if doc not in stale_docs
        and doc.status == "READY"
        and (doc.gemini_cache_name or doc.raw_content)
    ]

    if not ready_and_active_docs:
        # Indicates documents exist but are all currently processing.
        return CacheRefreshingResponse(
            status="PROCESSING_WAIT",
            stale_document_ids=[],
            retry_after_seconds=5,
        )

    return await answer_question_with_cache(question, ready_and_active_docs)

