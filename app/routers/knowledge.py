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


from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from app.application.use_cases import (
    DeleteKnowledgeDocumentUseCase,
    GetKnowledgeDocumentStatusUseCase,
    IngestKnowledgeDocumentUseCase,
    KnowledgeDocumentNotFoundError,
    PurgeProjectKnowledgeUseCase,
    QueryKnowledgeUseCase,
)
from app.composition import (
    provide_delete_knowledge_document_use_case,
    provide_get_knowledge_document_status_use_case,
    provide_ingest_knowledge_document_use_case,
    provide_purge_project_knowledge_use_case,
    provide_query_knowledge_use_case,
)
from app.domain.entities import KnowledgeAnswerResult
from app.schemas.knowledge import (
    AnswerCitation,
    CacheRefreshingResponse,
    DocumentIngestRequest,
    KnowledgeAnswer,
    QueryMode,
)

router = APIRouter(prefix="/knowledge", tags=["Knowledge Base"])


def _to_knowledge_answer(answer: KnowledgeAnswerResult) -> KnowledgeAnswer:
    return KnowledgeAnswer(
        answer=answer.answer,
        confidence_level=answer.confidence_level,
        citations=[
            AnswerCitation(
                document_id=citation.document_id,
                snippet=citation.snippet,
                source=citation.source,
            )
            for citation in answer.citations
        ],
    )


@router.post("/documents", status_code=status.HTTP_202_ACCEPTED)
async def ingest_document(
    request: DocumentIngestRequest,
    use_case: IngestKnowledgeDocumentUseCase = Depends(
        provide_ingest_knowledge_document_use_case
    ),
) -> Any:
    """Ingest a knowledge document and trigger asynchronous cache processing."""
    result = await use_case.execute(
        project_id=request.project_id,
        title=request.title,
        content=request.content,
        source_type=request.source_type,
        metadata=request.metadata,
    )
    if result.is_existing:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "document_id": str(result.document.id),
                "status": result.document.status,
                "message": "Document already exists",
            },
        )
    return {"document_id": str(result.document.id), "status": "PROCESSING"}


@router.get("/documents/{document_id}/status")
async def get_document_status(
    document_id: UUID,
    use_case: GetKnowledgeDocumentStatusUseCase = Depends(
        provide_get_knowledge_document_status_use_case
    ),
) -> Any:
    """Return the current processing status for a knowledge document."""
    try:
        doc = await use_case.execute(document_id=document_id)
    except KnowledgeDocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

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
    use_case: QueryKnowledgeUseCase = Depends(provide_query_knowledge_use_case),
) -> Any:
    """Query the knowledge base for a project using cached document context.

    Supports three query modes:
    - 'local':  Entity-level via pgvector + CTE traversal.
    - 'global': Community summaries.
    - 'hybrid': Local → Global with confidence gating (default).
    """
    del background_tasks
    result = await use_case.execute(
        project_id=project_id,
        question=question,
        mode=mode,
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

    return _to_knowledge_answer(result)


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: UUID,
    use_case: DeleteKnowledgeDocumentUseCase = Depends(
        provide_delete_knowledge_document_use_case
    ),
) -> Any:
    """Delete a document and related graph nodes."""
    try:
        await use_case.execute(document_id=document_id)
    except KnowledgeDocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "Document and associated entities deleted."},
    )


@router.delete("/purge-all")
async def purge_project_data(
    project_id: UUID,
    keep_documents: bool = False,
    use_case: PurgeProjectKnowledgeUseCase = Depends(
        provide_purge_project_knowledge_use_case
    ),
) -> Any:
    """Purge project graph, optionally purging documents as well."""
    await use_case.execute(project_id=project_id, keep_documents=keep_documents)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "Project knowledge purged."},
    )
