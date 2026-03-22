from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.cookbook import CookbookRecipe
from app.models.knowledge import KnowledgeDocument
from app.schemas.knowledge import (
    DocumentIngestRequest,
    KnowledgeAnswer,
    KnowledgeProjectSummary,
    KnowledgeQueryRequest,
)
from app.services.cookbook_pipeline import process_document_to_cookbooks
from app.services.knowledge_query_service import KnowledgeQueryService

router = APIRouter(prefix="/knowledge", tags=["Knowledge Base"])


@router.post("/documents", status_code=status.HTTP_202_ACCEPTED)
async def ingest_document(
    request: DocumentIngestRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Ingere um documento de conhecimento e agenda processamento em background."""
    new_doc = KnowledgeDocument(
        project_id=request.project_id,
        title=request.title,
        content=request.content,
        source_type=request.source_type,
        source_url=request.source_url,
        status="PROCESSING",
    )
    db.add(new_doc)
    await db.flush()
    await db.refresh(new_doc)
    await db.commit()

    background_tasks.add_task(process_document_to_cookbooks, new_doc.id)
    return {"document_id": str(new_doc.id), "status": "PROCESSING"}


@router.post("/query", response_model=KnowledgeAnswer)
async def query_knowledge(
    request: KnowledgeQueryRequest,
    db: AsyncSession = Depends(get_db),
) -> KnowledgeAnswer:
    """Consulta a base vetorial do projeto e sintetiza uma resposta com Gemini."""
    service = KnowledgeQueryService(db)
    return await service.answer_question(
        project_id=request.project_id,
        query=request.query,
        limit=request.limit,
    )


@router.get(
    "/projects/{project_id}/summary",
    response_model=KnowledgeProjectSummary,
)
async def knowledge_project_summary(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> KnowledgeProjectSummary:
    """
    Mostra quantos documentos existem por status e quantos ja podem ser usados no RAG.
    """
    status_rows = await db.execute(
        select(KnowledgeDocument.status, func.count())
        .where(KnowledgeDocument.project_id == project_id)
        .group_by(KnowledgeDocument.status)
    )
    by_status = {row[0]: int(row[1]) for row in status_rows.all()}
    total_documents = sum(by_status.values())

    ready_res = await db.execute(
        select(func.count())
        .select_from(KnowledgeDocument)
        .where(KnowledgeDocument.project_id == project_id)
        .where(KnowledgeDocument.status == "READY")
        .where(KnowledgeDocument.embedding.is_not(None))
    )
    ready_with_embedding = int(ready_res.scalar_one())

    return KnowledgeProjectSummary(
        project_id=project_id,
        total_documents=total_documents,
        by_status=by_status,
        ready_with_embedding=ready_with_embedding,
    )


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Remove um documento e seus dados associados."""
    doc = await db.get(KnowledgeDocument, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    await db.delete(doc)
    await db.commit()
    return {"message": "Document deleted."}


@router.delete("/purge-all")
async def purge_project_data(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Remove todos os documentos e dados de conhecimento do projeto."""
    await db.execute(
        delete(KnowledgeDocument).where(KnowledgeDocument.project_id == project_id)
    )
    # As receitas de Cookbook nao possuem reference de projeto direto.
    # Por simplicidade, esta versao ainda remove todas as receitas.
    await db.execute(delete(CookbookRecipe))
    await db.commit()
    return {"message": "Project knowledge purged."}
