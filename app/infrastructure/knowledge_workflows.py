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

from fastapi import BackgroundTasks

from app.adapters.remote_graph_adapter import RemoteGraphAdapter
from app.database import async_session_factory
from app.domain.entities import (
    AnswerCitation,
    KnowledgeAnswerResult,
    KnowledgeDocumentRecord,
    QueryMode,
)
from app.schemas.knowledge import KnowledgeAnswer
from app.services.graph_query_service import GraphQueryService
from app.services.knowledge_gemini import answer_question_with_cache, process_document_task


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

    def schedule_document_processing(self, document_id) -> None:
        self._background_tasks.add_task(process_document_task, document_id)


class LegacyKnowledgeQueryAdapter:
    def __init__(self) -> None:
        self._graph_query_service = GraphQueryService(RemoteGraphAdapter())

    async def query_graph(
        self,
        mode: QueryMode,
        project_id,
        question: str,
    ) -> KnowledgeAnswerResult:
        async with async_session_factory() as db:
            if mode == "local":
                return _map_answer(
                    await self._graph_query_service.local_query(db, project_id, question)
                )
            return _map_answer(
                await self._graph_query_service.global_query(db, project_id, question)
            )

    async def hybrid_query(self, project_id, question: str) -> KnowledgeAnswerResult:
        async with async_session_factory() as db:
            return _map_answer(
                await self._graph_query_service.hybrid_query(db, project_id, question)
            )

    async def answer_with_cache(
        self,
        question: str,
        ready_documents: list[KnowledgeDocumentRecord],
    ) -> KnowledgeAnswerResult:
        return _map_answer(await answer_question_with_cache(question, ready_documents))
