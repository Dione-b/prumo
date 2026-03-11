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


import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.interfaces.storage import IOutputStorage
from app.models.prompt import GeneratedPromptModel


class DatabaseStorage(IOutputStorage):
    """
    Armazenamento de arquivos diretamente no banco de dados.
    Esta classe depende de uma transação aberta do SQLAlchemy.
    O método save fará um flush (mas não commit), pois a rota
    é dona da demarcação de transação.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(
        self,
        project_id: UUID,
        content: str,
        metadata: dict[str, Any],
        ttl: int | None = None,
    ) -> str:
        """
        Salva o prompt numa tabela de histórico do banco de dados,
        permitindo ttl de segurança (expires_at). Retorna o proprio Id local.
        """
        checksum = hashlib.sha256(content.encode()).hexdigest()

        expires_at: datetime | None = None
        if ttl is not None and ttl > 0:
            expires_at = datetime.now(UTC) + timedelta(seconds=ttl)

        prompt_record = GeneratedPromptModel(
            project_id=project_id,
            content_hash=checksum,
            content=content,
            metadata_info=metadata,
            expires_at=expires_at,
        )

        self._session.add(prompt_record)
        # Flush no commit para pegar o ID e respeitar C_03
        await self._session.flush()

        return str(prompt_record.id)

    async def get_content(self, project_id: UUID, file_id: str) -> str | None:
        """
        Recupera conteúdo se ainda for válido e bater com o projeto.
        """
        try:
            target_id = UUID(file_id)
        except ValueError:
            return None

        stmt = select(GeneratedPromptModel).where(
            GeneratedPromptModel.id == target_id,
            GeneratedPromptModel.project_id == project_id,
        )
        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()

        if not record:
            return None

        # Se já expirou via lógica, embora possa estar no banco por não ter
        # varredura ainda.
        if record.expires_at is not None and record.expires_at < datetime.now(UTC):
            return None

        return record.content
