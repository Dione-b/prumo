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
