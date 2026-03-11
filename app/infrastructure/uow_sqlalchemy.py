from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.repositories import (
    SQLAlchemyBusinessRuleRepository,
    SQLAlchemyKnowledgeDocumentRepository,
    SQLAlchemyProjectRepository,
)


class SQLAlchemyUnitOfWork:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory
        self._projects: SQLAlchemyProjectRepository | None = None
        self._rules: SQLAlchemyBusinessRuleRepository | None = None
        self._knowledge_documents: SQLAlchemyKnowledgeDocumentRepository | None = None

    @property
    def projects(self) -> SQLAlchemyProjectRepository:
        if self._projects is None:
            raise RuntimeError("UnitOfWork transaction is not active")
        return self._projects

    @property
    def rules(self) -> SQLAlchemyBusinessRuleRepository:
        if self._rules is None:
            raise RuntimeError("UnitOfWork transaction is not active")
        return self._rules

    @property
    def knowledge_documents(self) -> SQLAlchemyKnowledgeDocumentRepository:
        if self._knowledge_documents is None:
            raise RuntimeError("UnitOfWork transaction is not active")
        return self._knowledge_documents

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SQLAlchemyUnitOfWork]:
        async with self._session_factory() as session:
            self._bind_repositories(session)
            try:
                async with session.begin():
                    yield self
            finally:
                self._unbind_repositories()

    def _bind_repositories(self, session: AsyncSession) -> None:
        self._projects = SQLAlchemyProjectRepository(session)
        self._rules = SQLAlchemyBusinessRuleRepository(session)
        self._knowledge_documents = SQLAlchemyKnowledgeDocumentRepository(session)

    def _unbind_repositories(self) -> None:
        self._projects = None
        self._rules = None
        self._knowledge_documents = None
