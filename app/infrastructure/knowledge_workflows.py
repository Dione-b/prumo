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


from __future__ import annotations

from uuid import UUID

from fastapi import BackgroundTasks

from app.database import async_session_factory
from app.domain.entities import (
    AnswerCitation,
    KnowledgeAnswerResult,
)
from app.schemas.knowledge import KnowledgeAnswer
from app.services.knowledge_gemini import process_document_task
from app.services.knowledge_orchestrator import query_rag


def _map_answer(answer: KnowledgeAnswer) -> KnowledgeAnswerResult:
    return KnowledgeAnswerResult(
        answer=answer.answer,
        confidence_level=answer.confidence_level,
        citations=tuple(
            AnswerCitation(
                document_id=citation.document_id,
                snippet=citation.snippet,
                source=citation.source,
            )
            for citation in answer.citations
        ),
        warnings=tuple(answer.warnings),
    )


class BackgroundTaskDocumentScheduler:
    def __init__(self, background_tasks: BackgroundTasks) -> None:
        self._background_tasks = background_tasks

    def schedule_document_processing(self, document_id: UUID) -> None:
        self._background_tasks.add_task(process_document_task, document_id)


class SimpleRAGQueryAdapter:
    """Adapter simples para RAG via pgvector."""

    async def answer_question(
        self,
        project_id: UUID,
        question: str,
    ) -> KnowledgeAnswerResult:
        async with async_session_factory() as db:
            answer = await query_rag(db, project_id, question)

        if answer is None:
            return KnowledgeAnswerResult(
                answer="Nenhum documento encontrado para este projeto.",
                confidence_level="LOW",
            )

        return _map_answer(answer)
