from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.domain.entities import (
    BusinessRuleDraft,
    BusinessRuleExtraction,
    BusinessRuleRecord,
    KnowledgeDocumentDraft,
    KnowledgeDocumentRecord,
    ProjectDraft,
    ProjectRecord,
    QueryMode,
)
from app.domain.ports import (
    DocumentProcessingSchedulerPort,
    KnowledgeQueryPort,
    LLMEnginePort,
    UnitOfWork,
)
from app.schemas.knowledge import CacheRefreshingResponse

_REUSABLE_DOCUMENT_STATUSES = {"PROCESSING", "READY", "READY_PARTIAL"}


class ProjectNotFoundError(LookupError):
    """Raised when a referenced project does not exist."""


class BusinessRuleNotFoundError(LookupError):
    """Raised when a business rule cannot be found."""


class KnowledgeDocumentNotFoundError(LookupError):
    """Raised when a knowledge document cannot be found."""


@dataclass(frozen=True, slots=True)
class IngestBusinessResult:
    record: BusinessRuleRecord
    extraction: BusinessRuleExtraction


@dataclass(frozen=True, slots=True)
class IngestKnowledgeDocumentResult:
    document: KnowledgeDocumentRecord
    is_existing: bool


class CreateProjectUseCase:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def execute(
        self,
        *,
        name: str,
        stack: str,
        description: str | None,
    ) -> ProjectRecord:
        async with self._uow.transaction():
            return await self._uow.projects.add(
                ProjectDraft(name=name, stack=stack, description=description)
            )


class IngestBusinessUseCase:
    def __init__(self, uow: UnitOfWork, llm_engine: LLMEnginePort) -> None:
        self._uow = uow
        self._llm_engine = llm_engine

    async def execute(
        self,
        *,
        project_id: UUID,
        raw_text: str,
        source: str | None,
    ) -> IngestBusinessResult:
        async with self._uow.transaction():
            project = await self._uow.projects.get_by_id(project_id)

        if project is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")

        extraction = await self._llm_engine.extract_business_rules(raw_text)

        async with self._uow.transaction():
            record = await self._uow.rules.add(
                BusinessRuleDraft(
                    project_id=project_id,
                    raw_text=raw_text,
                    extraction=extraction,
                    source=source,
                )
            )

        return IngestBusinessResult(record=record, extraction=extraction)


class DeleteBusinessRuleUseCase:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def execute(self, *, rule_id: UUID) -> None:
        async with self._uow.transaction():
            deleted = await self._uow.rules.delete_by_id(rule_id)

        if not deleted:
            raise BusinessRuleNotFoundError(f"Business rule {rule_id} not found")


class IngestKnowledgeDocumentUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        scheduler: DocumentProcessingSchedulerPort,
    ) -> None:
        self._uow = uow
        self._scheduler = scheduler

    async def execute(
        self,
        *,
        project_id: UUID,
        title: str,
        content: str | None,
        source_type: str,
        metadata: dict[str, object] | None,
    ) -> IngestKnowledgeDocumentResult:
        async with self._uow.transaction():
            existing = await self._uow.knowledge_documents.get_by_identity(
                project_id=project_id,
                title=title,
                source_type=source_type,
            )

        if existing and existing.status in _REUSABLE_DOCUMENT_STATUSES:
            return IngestKnowledgeDocumentResult(document=existing, is_existing=True)

        async with self._uow.transaction():
            document = await self._uow.knowledge_documents.add(
                KnowledgeDocumentDraft(
                    project_id=project_id,
                    title=title,
                    source_type=source_type,
                    content=content,
                    metadata=metadata,
                    status="PROCESSING",
                )
            )

        self._scheduler.schedule_document_processing(document.id)
        return IngestKnowledgeDocumentResult(document=document, is_existing=False)


class GetKnowledgeDocumentStatusUseCase:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def execute(self, *, document_id: UUID) -> KnowledgeDocumentRecord:
        async with self._uow.transaction():
            document = await self._uow.knowledge_documents.get_by_id(document_id)

        if document is None:
            raise KnowledgeDocumentNotFoundError("Document not found")

        return document


class QueryKnowledgeUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        scheduler: DocumentProcessingSchedulerPort,
        query_port: KnowledgeQueryPort,
    ) -> None:
        self._uow = uow
        self._scheduler = scheduler
        self._query_port = query_port

    async def execute(
        self,
        *,
        project_id: UUID,
        question: str,
        mode: QueryMode,
    ) -> object | None:
        async with self._uow.transaction():
            documents = await self._uow.knowledge_documents.list_queryable_by_project(
                project_id
            )

        if not documents:
            return None

        stale_document_ids = self._collect_stale_document_ids(documents)
        if stale_document_ids:
            async with self._uow.transaction():
                await self._uow.knowledge_documents.mark_processing(stale_document_ids)

            for document_id in stale_document_ids:
                self._scheduler.schedule_document_processing(document_id)

            return CacheRefreshingResponse(
                status="CACHE_REFRESHING",
                stale_document_ids=[str(document_id) for document_id in stale_document_ids],
                retry_after_seconds=30,
            )

        ready_documents = [
            document
            for document in documents
            if document.status in ("READY", "READY_PARTIAL")
            and (document.gemini_cache_name or document.raw_content)
        ]
        if not ready_documents:
            return CacheRefreshingResponse(
                status="PROCESSING_WAIT",
                stale_document_ids=[],
                retry_after_seconds=5,
            )

        if mode in ("local", "global"):
            try:
                return await self._query_port.query_graph(mode, project_id, question)
            except Exception:  # noqa: BLE001
                return await self._query_port.answer_with_cache(
                    question,
                    ready_documents,
                )

        try:
            answer = await self._query_port.hybrid_query(project_id, question)
            if answer.confidence_level != "LOW" or answer.citations:
                return answer
        except Exception:  # noqa: BLE001
            pass

        return await self._query_port.answer_with_cache(question, ready_documents)

    def _collect_stale_document_ids(
        self,
        documents: list[KnowledgeDocumentRecord],
    ) -> list[UUID]:
        now = datetime.now(UTC)
        return [
            document.id
            for document in documents
            if document.cache_expires_at
            and document.cache_expires_at < now
            and document.status != "PROCESSING"
        ]


class DeleteKnowledgeDocumentUseCase:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def execute(self, *, document_id: UUID) -> None:
        async with self._uow.transaction():
            deleted = await self._uow.knowledge_documents.delete_by_id(document_id)

        if not deleted:
            raise KnowledgeDocumentNotFoundError("Document not found")


class PurgeProjectKnowledgeUseCase:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def execute(self, *, project_id: UUID, keep_documents: bool) -> None:
        async with self._uow.transaction():
            await self._uow.knowledge_documents.purge_project(
                project_id,
                keep_documents=keep_documents,
            )
