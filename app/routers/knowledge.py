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

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from app.application.use_cases import (
    DeleteKnowledgeDocumentUseCase,
    IngestKnowledgeDocumentUseCase,
    KnowledgeDocumentNotFoundError,
    PurgeProjectKnowledgeUseCase,
    QueryKnowledgeUseCase,
)
from app.composition import (
    provide_delete_knowledge_document_use_case,
    provide_ingest_knowledge_document_use_case,
    provide_purge_project_knowledge_use_case,
    provide_query_knowledge_use_case,
)
from app.domain.entities import KnowledgeAnswerResult
from app.schemas.knowledge import (
    AnswerCitation,
    DocumentIngestRequest,
    KnowledgeAnswer,
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
    """Ingere um documento de conhecimento e agenda processamento em background."""
    result = await use_case.execute(
        project_id=request.project_id,
        title=request.title,
        content=request.content,
        source_type=request.source_type,
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


@router.post("/query", response_model=KnowledgeAnswer)
async def query_knowledge(
    project_id: UUID,
    question: str,
    use_case: QueryKnowledgeUseCase = Depends(provide_query_knowledge_use_case),
) -> Any:
    """Consulta a base de conhecimento via RAG (busca vetorial + síntese Gemini)."""
    result = await use_case.execute(
        project_id=project_id,
        question=question,
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="No active documents found for this project.",
        )

    return _to_knowledge_answer(result)


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: UUID,
    use_case: DeleteKnowledgeDocumentUseCase = Depends(
        provide_delete_knowledge_document_use_case
    ),
) -> Any:
    """Remove um documento e seus dados associados."""
    try:
        await use_case.execute(document_id=document_id)
    except KnowledgeDocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "Document deleted."},
    )


@router.delete("/purge-all")
async def purge_project_data(
    project_id: UUID,
    use_case: PurgeProjectKnowledgeUseCase = Depends(
        provide_purge_project_knowledge_use_case
    ),
) -> Any:
    """Remove todos os documentos e dados de conhecimento do projeto."""
    await use_case.execute(project_id=project_id)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "Project knowledge purged."},
    )
