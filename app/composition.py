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

from app.application.use_cases import (
    CreateProjectUseCase,
    DeleteBusinessRuleUseCase,
    DeleteKnowledgeDocumentUseCase,
    IngestBusinessUseCase,
    IngestKnowledgeDocumentUseCase,
    PurgeProjectKnowledgeUseCase,
    QueryKnowledgeUseCase,
)
from app.database import async_session_factory
from app.infrastructure.knowledge_workflows import (
    BackgroundTaskDocumentScheduler,
    SimpleRAGQueryAdapter,
)
from app.infrastructure.llm_external import ExternalAIEngineAdapter
from app.infrastructure.uow_sqlalchemy import SQLAlchemyUnitOfWork


def _build_uow() -> SQLAlchemyUnitOfWork:
    return SQLAlchemyUnitOfWork(async_session_factory)


def provide_create_project_use_case() -> CreateProjectUseCase:
    return CreateProjectUseCase(_build_uow())


def provide_ingest_business_use_case() -> IngestBusinessUseCase:
    return IngestBusinessUseCase(_build_uow(), ExternalAIEngineAdapter())


def provide_delete_business_rule_use_case() -> DeleteBusinessRuleUseCase:
    return DeleteBusinessRuleUseCase(_build_uow())


def provide_ingest_knowledge_document_use_case(
    background_tasks: BackgroundTasks,
) -> IngestKnowledgeDocumentUseCase:
    scheduler = BackgroundTaskDocumentScheduler(background_tasks)
    return IngestKnowledgeDocumentUseCase(_build_uow(), scheduler)


def provide_query_knowledge_use_case() -> QueryKnowledgeUseCase:
    return QueryKnowledgeUseCase(
        _build_uow(),
        SimpleRAGQueryAdapter(),
    )


def provide_delete_knowledge_document_use_case() -> DeleteKnowledgeDocumentUseCase:
    return DeleteKnowledgeDocumentUseCase(_build_uow())


def provide_purge_project_knowledge_use_case() -> PurgeProjectKnowledgeUseCase:
    return PurgeProjectKnowledgeUseCase(_build_uow())
