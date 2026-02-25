from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.knowledge import KnowledgeDocument
from app.schemas.knowledge import (
    CacheRefreshingResponse,
    DocumentIngestRequest,
    KnowledgeAnswer,
    QueryMode,
)
from app.services.knowledge_orchestrator import (
    orchestrate_ingestion,
    orchestrate_query,
)

router = APIRouter(prefix="/knowledge", tags=["Knowledge Base"])


@router.post("/documents", status_code=status.HTTP_202_ACCEPTED)
async def ingest_document(
    request: DocumentIngestRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Ingest a knowledge document and trigger asynchronous cache processing."""
    doc, is_existing = await orchestrate_ingestion(request, background_tasks, db)
    if is_existing:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "document_id": str(doc.id),
                "status": doc.status,
                "message": "Document already exists",
            },
        )
    return {"document_id": str(doc.id), "status": "PROCESSING"}


@router.get("/documents/{document_id}/status")
async def get_document_status(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Return the current processing status for a knowledge document."""
    stmt = select(KnowledgeDocument).where(KnowledgeDocument.id == document_id)
    result = await db.execute(stmt)
    doc: KnowledgeDocument | None = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "document_id": str(doc.id),
        "status": doc.status,
        "metadata": doc.metadata_json,
    }


@router.post(
    "/query",
    responses={
        200: {"model": KnowledgeAnswer},
        202: {"model": CacheRefreshingResponse},
    },
)
async def query_knowledge(
    project_id: UUID,
    question: str,
    background_tasks: BackgroundTasks,
    mode: QueryMode = "hybrid",
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Query the knowledge base for a project using cached document context.

    Supports three query modes:
    - 'local':  Entity-level via pgvector + CTE traversal.
    - 'global': Community summaries.
    - 'hybrid': Local → Global with confidence gating (default).
    """
    result = await orchestrate_query(
        project_id, question, background_tasks, db, mode=mode
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="No active documents found for this project.",
        )

    if isinstance(result, CacheRefreshingResponse):
        if result.status == "PROCESSING_WAIT":
            raise HTTPException(
                status_code=503,
                detail="Documents are still processing.",
            )
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=result.model_dump(),
        )

    return result

