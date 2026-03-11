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

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import (
    BusinessRuleDraft,
    BusinessRuleRecord,
    KnowledgeDocumentDraft,
    KnowledgeDocumentRecord,
    ProjectDraft,
    ProjectRecord,
)
from app.models.business_rule import BusinessRule
from app.models.knowledge import KnowledgeDocument
from app.models.project import Project
from app.services.graph_services import delete_knowledge_document, purge_project_knowledge

_QUERYABLE_STATUSES = ("READY", "READY_PARTIAL", "PROCESSING")


def _map_project(record: Project) -> ProjectRecord:
    return ProjectRecord(
        id=record.id,
        name=record.name,
        description=record.description,
        llm_model=record.llm_model,
        namespace=record.namespace,
    )


def _map_business_rule(record: BusinessRule) -> BusinessRuleRecord:
    return BusinessRuleRecord(
        id=record.id,
        project_id=record.project_id,
        raw_text=record.raw_text,
        client_name=record.client_name,
        core_objective=record.core_objective,
        technical_constraints=tuple(record.technical_constraints),
        acceptance_criteria=tuple(record.acceptance_criteria),
        additional_notes=record.additional_notes,
        confidence_level=record.confidence_level,
        source=record.source,
    )


def _map_knowledge_document(record: KnowledgeDocument) -> KnowledgeDocumentRecord:
    return KnowledgeDocumentRecord(
        id=record.id,
        project_id=record.project_id,
        title=record.title,
        source_type=record.source_type,
        status=record.status,
        gemini_file_uri=record.gemini_file_uri,
        gemini_cache_name=record.gemini_cache_name,
        cache_expires_at=record.cache_expires_at,
        raw_content=record.raw_content,
        metadata_json=dict(record.metadata_json) if record.metadata_json else None,
    )


class SQLAlchemyProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, draft: ProjectDraft) -> ProjectRecord:
        record = Project(
            name=draft.name,
            description=draft.description,
            config_json={"stack": draft.stack},
        )
        self._session.add(record)
        await self._session.flush()
        await self._session.refresh(record)
        return _map_project(record)

    async def get_by_id(self, project_id: UUID) -> ProjectRecord | None:
        record = await self._session.get(Project, project_id)
        if record is None:
            return None
        return _map_project(record)


class SQLAlchemyBusinessRuleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, rule: BusinessRuleDraft) -> BusinessRuleRecord:
        extraction = rule.extraction
        record = BusinessRule(
            project_id=rule.project_id,
            raw_text=rule.raw_text,
            client_name=extraction.client_name,
            core_objective=extraction.core_objective,
            technical_constraints=list(extraction.technical_constraints),
            acceptance_criteria=list(extraction.acceptance_criteria),
            additional_notes=extraction.additional_notes,
            confidence_level=extraction.confidence_level,
            content_type="structured",
            namespace="business",
            source=rule.source,
        )
        self._session.add(record)
        await self._session.flush()
        await self._session.refresh(record)
        return _map_business_rule(record)

    async def delete_by_id(self, rule_id: UUID) -> bool:
        result = await self._session.execute(
            delete(BusinessRule).where(BusinessRule.id == rule_id)
        )
        return bool(result.rowcount)  # type: ignore[attr-defined]


class SQLAlchemyKnowledgeDocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, draft: KnowledgeDocumentDraft) -> KnowledgeDocumentRecord:
        record = KnowledgeDocument(
            project_id=draft.project_id,
            title=draft.title,
            source_type=draft.source_type,
            raw_content=draft.content,
            metadata_json=draft.metadata,
            status=draft.status,
        )
        self._session.add(record)
        await self._session.flush()
        await self._session.refresh(record)
        return _map_knowledge_document(record)

    async def get_by_id(self, document_id: UUID) -> KnowledgeDocumentRecord | None:
        record = await self._session.get(KnowledgeDocument, document_id)
        if record is None:
            return None
        return _map_knowledge_document(record)

    async def get_by_identity(
        self,
        project_id: UUID,
        title: str,
        source_type: str,
    ) -> KnowledgeDocumentRecord | None:
        stmt = select(KnowledgeDocument).where(
            KnowledgeDocument.project_id == project_id,
            KnowledgeDocument.title == title,
            KnowledgeDocument.source_type == source_type,
        )
        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()
        if record is None:
            return None
        return _map_knowledge_document(record)

    async def list_queryable_by_project(
        self,
        project_id: UUID,
    ) -> list[KnowledgeDocumentRecord]:
        stmt = select(KnowledgeDocument).where(
            KnowledgeDocument.project_id == project_id,
            KnowledgeDocument.status.in_(list(_QUERYABLE_STATUSES)),
        )
        result = await self._session.execute(stmt)
        return [_map_knowledge_document(record) for record in result.scalars().all()]

    async def mark_processing(self, document_ids: list[UUID]) -> None:
        if not document_ids:
            return
        await self._session.execute(
            update(KnowledgeDocument)
            .where(KnowledgeDocument.id.in_(document_ids))
            .values(status="PROCESSING")
        )

    async def delete_by_id(self, document_id: UUID) -> bool:
        return await delete_knowledge_document(self._session, document_id)

    async def purge_project(self, project_id: UUID, keep_documents: bool) -> None:
        await purge_project_knowledge(
            self._session,
            project_id,
            keep_documents=keep_documents,
        )
