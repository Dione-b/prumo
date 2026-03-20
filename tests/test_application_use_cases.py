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


import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

from app.application.use_cases import (
    IngestBusinessUseCase,
    IngestKnowledgeDocumentUseCase,
    ProjectNotFoundError,
)
from app.domain.entities import (
    BusinessRuleDraft,
    BusinessRuleExtraction,
    BusinessRuleRecord,
    KnowledgeDocumentDraft,
    KnowledgeDocumentRecord,
    ProjectRecord,
)


class FakeProjectRepository:
    def __init__(self, project: ProjectRecord | None) -> None:
        self._project = project

    async def add(self, draft):  # pragma: no cover
        raise NotImplementedError

    async def get_by_id(self, project_id: uuid.UUID) -> ProjectRecord | None:
        if self._project and self._project.id == project_id:
            return self._project
        return None


class FakeBusinessRuleRepository:
    def __init__(self) -> None:
        self.saved_rules: list[BusinessRuleDraft] = []

    async def add(self, rule: BusinessRuleDraft) -> BusinessRuleRecord:
        self.saved_rules.append(rule)
        return BusinessRuleRecord(
            id=uuid.uuid4(),
            project_id=rule.project_id,
            raw_text=rule.raw_text,
            client_name=rule.extraction.client_name,
            core_objective=rule.extraction.core_objective,
            technical_constraints=rule.extraction.technical_constraints,
            acceptance_criteria=rule.extraction.acceptance_criteria,
            additional_notes=rule.extraction.additional_notes,
            confidence_level=rule.extraction.confidence_level,
            source=rule.source,
        )

    async def delete_by_id(self, rule_id: uuid.UUID) -> bool:  # pragma: no cover
        return False


class FakeKnowledgeDocumentRepository:
    def __init__(self) -> None:
        self.saved_documents: list[KnowledgeDocumentDraft] = []

    async def add(self, draft: KnowledgeDocumentDraft) -> KnowledgeDocumentRecord:
        self.saved_documents.append(draft)
        return KnowledgeDocumentRecord(
            id=uuid.uuid4(),
            project_id=draft.project_id,
            title=draft.title,
            source_type=draft.source_type,
            status=draft.status,
            content=draft.content,
        )

    async def get_by_id(self, document_id: uuid.UUID):  # pragma: no cover
        return None

    async def get_by_identity(
        self,
        project_id: uuid.UUID,
        title: str,
        source_type: str,
    ) -> KnowledgeDocumentRecord | None:
        return None

    async def list_ready_by_project(
        self, project_id: uuid.UUID
    ):  # pragma: no cover
        return []

    async def delete_by_id(
        self, document_id: uuid.UUID
    ) -> bool:  # pragma: no cover
        return False

    async def purge_project(
        self, project_id: uuid.UUID
    ) -> None:  # pragma: no cover
        return None


class FakeUnitOfWork:
    def __init__(self, project: ProjectRecord | None) -> None:
        self.projects = FakeProjectRepository(project)
        self.rules = FakeBusinessRuleRepository()
        self.knowledge_documents = FakeKnowledgeDocumentRepository()
        self.transaction_calls = 0

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["FakeUnitOfWork"]:
        self.transaction_calls += 1
        yield self


class FakeLLMEngine:
    async def extract_business_rules(self, text: str) -> BusinessRuleExtraction:
        return BusinessRuleExtraction(
            client_name="Acme",
            core_objective="Automate onboarding",
            technical_constraints=("Postgres", "FastAPI"),
            acceptance_criteria=("Users can sign in",),
            additional_notes="Use SSO",
            confidence_level="HIGH",
            warnings=("review manually",),
        )


class FakeScheduler:
    def __init__(self) -> None:
        self.scheduled_ids: list[uuid.UUID] = []

    def schedule_document_processing(self, document_id: uuid.UUID) -> None:
        self.scheduled_ids.append(document_id)


@pytest.mark.asyncio
async def test_ingest_business_use_case_uses_ports_only() -> None:
    # Arrange
    project = ProjectRecord(
        id=uuid.uuid4(),
        name="Prumo",
        description=None,
    )
    uow = FakeUnitOfWork(project)
    use_case = IngestBusinessUseCase(uow, FakeLLMEngine())

    # Act
    result = await use_case.execute(
        project_id=project.id,
        raw_text="Need onboarding flow with FastAPI and Postgres",
        source="meeting.txt",
    )

    # Assert
    assert result.extraction.client_name == "Acme"
    assert len(uow.rules.saved_rules) == 1
    assert uow.rules.saved_rules[0].source == "meeting.txt"
    assert uow.transaction_calls == 2


@pytest.mark.asyncio
async def test_ingest_business_use_case_fails_fast_without_project() -> None:
    # Arrange
    uow = FakeUnitOfWork(project=None)
    use_case = IngestBusinessUseCase(uow, FakeLLMEngine())

    # Act / Assert
    with pytest.raises(ProjectNotFoundError):
        await use_case.execute(
            project_id=uuid.uuid4(),
            raw_text="Need onboarding flow with FastAPI and Postgres",
            source=None,
        )

    assert uow.transaction_calls == 1
    assert uow.rules.saved_rules == []


@pytest.mark.asyncio
async def test_ingest_knowledge_document_schedules_processing() -> None:
    # Arrange
    project = ProjectRecord(
        id=uuid.uuid4(),
        name="Prumo",
        description=None,
    )
    uow = FakeUnitOfWork(project)
    scheduler = FakeScheduler()
    use_case = IngestKnowledgeDocumentUseCase(uow, scheduler)

    # Act
    result = await use_case.execute(
        project_id=project.id,
        title="ADR-001",
        content="Hexagonal architecture notes",
        source_type="text/markdown",
    )

    # Assert
    assert result.is_existing is False
    assert len(uow.knowledge_documents.saved_documents) == 1
    assert scheduler.scheduled_ids == [result.document.id]
