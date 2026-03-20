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

from contextlib import AbstractAsyncContextManager
from typing import Protocol
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


class ProjectRepository(Protocol):
    async def add(self, draft: ProjectDraft) -> ProjectRecord: ...

    async def get_by_id(self, project_id: UUID) -> ProjectRecord | None: ...


class BusinessRuleRepository(Protocol):
    async def add(self, rule: BusinessRuleDraft) -> BusinessRuleRecord: ...

    async def delete_by_id(self, rule_id: UUID) -> bool: ...


class KnowledgeDocumentRepository(Protocol):
    async def add(self, draft: KnowledgeDocumentDraft) -> KnowledgeDocumentRecord: ...

    async def get_by_id(self, document_id: UUID) -> KnowledgeDocumentRecord | None: ...

    async def get_by_identity(
        self,
        project_id: UUID,
        title: str,
        source_type: str,
    ) -> KnowledgeDocumentRecord | None: ...

    async def list_ready_by_project(
        self,
        project_id: UUID,
    ) -> list[KnowledgeDocumentRecord]: ...

    async def delete_by_id(self, document_id: UUID) -> bool: ...

    async def purge_project(self, project_id: UUID) -> None: ...


class UnitOfWork(Protocol):
    @property
    def projects(self) -> ProjectRepository: ...

    @property
    def rules(self) -> BusinessRuleRepository: ...

    @property
    def knowledge_documents(self) -> KnowledgeDocumentRepository: ...

    def transaction(self) -> AbstractAsyncContextManager[UnitOfWork]: ...


class LLMEnginePort(Protocol):
    async def extract_business_rules(self, text: str) -> BusinessRuleExtraction: ...


class DocumentProcessingSchedulerPort(Protocol):
    def schedule_document_processing(self, document_id: UUID) -> None: ...


class KnowledgeQueryPort(Protocol):
    async def answer_question(
        self,
        project_id: UUID,
        question: str,
    ) -> KnowledgeAnswerResult: ...
