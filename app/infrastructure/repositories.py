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

from sqlalchemy import delete, select
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

_QUERYABLE_STATUSES = ("READY",)


def _map_project(record: Project) -> ProjectRecord:
    return ProjectRecord(
        id=record.id,
        name=record.name,
        description=record.description,
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
        content=record.content,
    )


class SQLAlchemyProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, draft: ProjectDraft) -> ProjectRecord:
        record = Project(
            name=draft.name,
            description=draft.description,
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
            content=draft.content,
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

    async def list_ready_by_project(
        self,
        project_id: UUID,
    ) -> list[KnowledgeDocumentRecord]:
        stmt = select(KnowledgeDocument).where(
            KnowledgeDocument.project_id == project_id,
            KnowledgeDocument.status.in_(list(_QUERYABLE_STATUSES)),
        )
        result = await self._session.execute(stmt)
        return [_map_knowledge_document(record) for record in result.scalars().all()]

    async def delete_by_id(self, document_id: UUID) -> bool:
        result = await self._session.execute(
            delete(KnowledgeDocument).where(KnowledgeDocument.id == document_id)
        )
        return bool(result.rowcount)  # type: ignore[attr-defined]

    async def purge_project(self, project_id: UUID) -> None:
        await self._session.execute(
            delete(KnowledgeDocument).where(
                KnowledgeDocument.project_id == project_id
            )
        )
