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


from typing import Any, Protocol
from uuid import UUID


class IOutputStorage(Protocol):
    """
    Abstração para persistência de prompts e artefatos,
    removendo acoplamento direto com sistema de arquivos.
    """

    async def save(
        self,
        project_id: UUID,
        content: str,
        metadata: dict[str, Any],
        ttl: int | None = None,
    ) -> str:
        """
        Persiste o conteúdo e retorna um identificador opaco (ex: UUID).

        Args:
            project_id: ID do projeto vinculado.
            content: O conteúdo gerado do prompt (YAML etc).
            metadata: Metadados associados ao conteúdo gerado.
            ttl: Tempo de vida em segundos (opcional).
            O storage deve garantir a expiração.
        Returns:
            Identificador opaco (ID do banco ou UUID local).
        """

    async def get_content(self, project_id: UUID, file_id: str) -> str | None:
        """
        Recupera o conteúdo persistido se ainda for válido.

        Args:
            project_id: ID do projeto vinculado.
            file_id: Identificador opaco retornado por save().

        Returns:
            O conteúdo original ou None se não encontrado/expirado.
        """
        ...
