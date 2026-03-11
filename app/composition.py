from __future__ import annotations

from fastapi import BackgroundTasks

from app.application.use_cases import (
    CreateProjectUseCase,
    DeleteBusinessRuleUseCase,
    DeleteKnowledgeDocumentUseCase,
    GetKnowledgeDocumentStatusUseCase,
    IngestBusinessUseCase,
    IngestKnowledgeDocumentUseCase,
    PurgeProjectKnowledgeUseCase,
    QueryKnowledgeUseCase,
)
from app.database import async_session_factory
from app.infrastructure.knowledge_workflows import (
    BackgroundTaskDocumentScheduler,
    LegacyKnowledgeQueryAdapter,
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


def provide_get_knowledge_document_status_use_case() -> GetKnowledgeDocumentStatusUseCase:
    return GetKnowledgeDocumentStatusUseCase(_build_uow())


def provide_query_knowledge_use_case(
    background_tasks: BackgroundTasks,
) -> QueryKnowledgeUseCase:
    scheduler = BackgroundTaskDocumentScheduler(background_tasks)
    return QueryKnowledgeUseCase(
        _build_uow(),
        scheduler,
        LegacyKnowledgeQueryAdapter(),
    )


def provide_delete_knowledge_document_use_case() -> DeleteKnowledgeDocumentUseCase:
    return DeleteKnowledgeDocumentUseCase(_build_uow())


def provide_purge_project_knowledge_use_case() -> PurgeProjectKnowledgeUseCase:
    return PurgeProjectKnowledgeUseCase(_build_uow())
