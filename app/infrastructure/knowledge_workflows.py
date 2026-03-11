from __future__ import annotations

from fastapi import BackgroundTasks

from app.database import async_session_factory
from app.domain.entities import AnswerCitation, KnowledgeAnswerResult, KnowledgeDocumentRecord, QueryMode
from app.schemas.knowledge import KnowledgeAnswer
from app.services.graph_query_service import global_query, hybrid_query, local_query
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
    async def query_graph(
        self,
        mode: QueryMode,
        project_id,
        question: str,
    ) -> KnowledgeAnswerResult:
        async with async_session_factory() as db:
            if mode == "local":
                return _map_answer(await local_query(db, project_id, question))
            return _map_answer(await global_query(db, project_id, question))

    async def hybrid_query(self, project_id, question: str) -> KnowledgeAnswerResult:
        async with async_session_factory() as db:
            return _map_answer(await hybrid_query(db, project_id, question))

    async def answer_with_cache(
        self,
        question: str,
        ready_documents: list[KnowledgeDocumentRecord],
    ) -> KnowledgeAnswerResult:
        return _map_answer(await answer_question_with_cache(question, ready_documents))
