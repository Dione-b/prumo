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

from collections.abc import AsyncIterator
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
