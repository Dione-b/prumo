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

from dataclasses import dataclass
from uuid import UUID

from app.domain.entities import (
    BusinessRuleDraft,
    BusinessRuleExtraction,
    BusinessRuleRecord,
    KnowledgeAnswerResult,
    KnowledgeDocumentDraft,
    KnowledgeDocumentRecord,
    ProjectDraft,
    ProjectRecord,
)
from app.domain.ports import (
    DocumentProcessingSchedulerPort,
    KnowledgeQueryPort,
    LLMEnginePort,
    UnitOfWork,
)

_REUSABLE_DOCUMENT_STATUSES = {"PROCESSING", "READY"}


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
        description: str | None,
    ) -> ProjectRecord:
        async with self._uow.transaction():
            return await self._uow.projects.add(
                ProjectDraft(name=name, description=description)
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
                    status="PROCESSING",
                )
            )

        self._scheduler.schedule_document_processing(document.id)
        return IngestKnowledgeDocumentResult(document=document, is_existing=False)


class QueryKnowledgeUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        query_port: KnowledgeQueryPort,
    ) -> None:
        self._uow = uow
        self._query_port = query_port

    async def execute(
        self,
        *,
        project_id: UUID,
        question: str,
    ) -> KnowledgeAnswerResult | None:
        async with self._uow.transaction():
            documents = await self._uow.knowledge_documents.list_ready_by_project(
                project_id
            )

        if not documents:
            return None

        return await self._query_port.answer_question(project_id, question)


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

    async def execute(self, *, project_id: UUID) -> None:
        async with self._uow.transaction():
            await self._uow.knowledge_documents.purge_project(project_id)
