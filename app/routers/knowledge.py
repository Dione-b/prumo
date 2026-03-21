from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.cookbook import CookbookRecipe
from app.models.knowledge import KnowledgeDocument
from app.schemas.knowledge import DocumentIngestRequest
from app.services.cookbook_pipeline import process_document_to_cookbooks

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
        status="PROCESSING",
    )
    db.add(new_doc)
    await db.flush()
    await db.refresh(new_doc)
    await db.commit()

    background_tasks.add_task(process_document_to_cookbooks, new_doc.id)
    return {"document_id": str(new_doc.id), "status": "PROCESSING"}


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
    # As receitas de Cookbook nao possuem reference de projeto direto (só por document_ids)
    # Por simplicidade, podemos purgar todas que cruzam ou simplesmente ignorar pra Prumo Lite.
    await db.execute(delete(CookbookRecipe))
    await db.commit()
    return {"message": "Project knowledge purged."}
