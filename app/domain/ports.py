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

from typing import AsyncContextManager, Protocol
from uuid import UUID

from app.domain.entities import (
    ConversationRecord,
    KnowledgeAnswerResult,
    BusinessRuleDraft,
    BusinessRuleExtraction,
    BusinessRuleRecord,
    KnowledgeDocumentDraft,
    KnowledgeDocumentRecord,
    KnowledgeEntityExtraction,
    MessageDraft,
    MessageRecord,
    ProjectDraft,
    ProjectRecord,
    QueryMode,
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

    async def list_queryable_by_project(
        self,
        project_id: UUID,
    ) -> list[KnowledgeDocumentRecord]: ...

    async def mark_processing(self, document_ids: list[UUID]) -> None: ...

    async def delete_by_id(self, document_id: UUID) -> bool: ...

    async def purge_project(self, project_id: UUID, keep_documents: bool) -> None: ...


class ConversationRepository(Protocol):
    async def create(
        self, project_id: UUID, title: str,
    ) -> ConversationRecord: ...

    async def add_message(
        self, conversation_id: UUID, message: MessageDraft,
    ) -> MessageRecord: ...

    async def get_history(
        self, conversation_id: UUID, limit: int = 20,
    ) -> list[MessageRecord]: ...

    async def list_by_project(
        self, project_id: UUID,
    ) -> list[ConversationRecord]: ...

    async def delete(self, conversation_id: UUID) -> bool: ...


class UnitOfWork(Protocol):
    @property
    def projects(self) -> ProjectRepository: ...

    @property
    def rules(self) -> BusinessRuleRepository: ...

    @property
    def knowledge_documents(self) -> KnowledgeDocumentRepository: ...

    @property
    def conversations(self) -> ConversationRepository: ...

    def transaction(self) -> AsyncContextManager["UnitOfWork"]: ...


class LLMEnginePort(Protocol):
    async def extract_business_rules(self, text: str) -> BusinessRuleExtraction: ...

    async def extract_entities(
        self,
        text: str,
        system_prompt: str | None = None,
    ) -> KnowledgeEntityExtraction: ...


class EmbeddingPort(Protocol):
    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class DocumentProcessingSchedulerPort(Protocol):
    def schedule_document_processing(self, document_id: UUID) -> None: ...


class KnowledgeQueryPort(Protocol):
    async def query_graph(
        self,
        mode: QueryMode,
        project_id: UUID,
        question: str,
    ) -> KnowledgeAnswerResult: ...

    async def hybrid_query(
        self,
        project_id: UUID,
        question: str,
    ) -> KnowledgeAnswerResult: ...

    async def answer_with_cache(
        self,
        question: str,
        ready_documents: list[KnowledgeDocumentRecord],
    ) -> KnowledgeAnswerResult: ...
