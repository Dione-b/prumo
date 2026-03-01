import asyncio
import hashlib
import json
import logging
import uuid
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from app.config import settings
from app.interfaces.storage import IOutputStorage

logger = logging.getLogger(__name__)


def _write_files_sync(
    output_dir: Path, file_id: str, content: str, metadata: dict[str, Any]
) -> None:
    """I/O síncrono para escrita dos arquivos de output via thread."""
    output_dir.mkdir(parents=True, exist_ok=True)

    yaml_path = output_dir / f"{file_id}.yaml"
    sha256_path = output_dir / f"{file_id}.sha256"
    meta_path = output_dir / f"{file_id}.meta.json"

    yaml_path.write_text(content, encoding="utf-8")

    checksum = hashlib.sha256(content.encode()).hexdigest()
    sha256_path.write_text(checksum, encoding="utf-8")

    # Também vamos salvar os metadados localmente por completude
    meta_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _delete_files_sync(output_dir: Path, file_id: str) -> None:
    """Remove os arquivos de output (TTL expirou)."""
    paths = [
        output_dir / f"{file_id}.yaml",
        output_dir / f"{file_id}.sha256",
        output_dir / f"{file_id}.meta.json",
    ]
    for p in paths:
        try:
            if p.exists():
                p.unlink()
        except OSError as e:
            logger.warning("Falha ao remover arquivo de cache em %s: %s", p, e)


class LocalStorage(IOutputStorage):
    """
    Armazenamento de arquivos no sistema local. Utiliza `asyncio.to_thread`
    para respeitar a invariante C_02, removendo bloqueios de event loop.
    Efetua a limpeza de arquivos baseada em TTL temporal em background.
    """

    def __init__(self, base_dir: Path = Path(settings.output_dir)) -> None:
        self._base_dir = base_dir

    async def save(
        self,
        project_id: UUID,
        content: str,
        metadata: dict[str, Any],
        ttl: Optional[int] = None,
    ) -> str:
        """
        Salva o prompt numa pasta isolada pelo project_id usando um nome UUID
        (gerando um identificador opaco para segurança).
        Gera um arquivo sidecar com .sha256.
        """
        # Identificador opaco de arquivo
        file_id = str(uuid.uuid4())
        project_dir = self._base_dir / str(project_id)

        # Envia a escrita síncrona para thread C_02
        await asyncio.to_thread(
            _write_files_sync, project_dir, file_id, content, metadata
        )

        # Se houver ttl, agenda a deleção
        if ttl is not None and ttl > 0:
            asyncio.create_task(self._schedule_deletion(project_dir, file_id, ttl))

        return file_id

    async def _schedule_deletion(
        self, project_dir: Path, file_id: str, ttl: int
    ) -> None:
        """Task de background que espera ttl e limpa o dataset gerado."""
        try:
            await asyncio.sleep(ttl)
            await asyncio.to_thread(_delete_files_sync, project_dir, file_id)
            logger.info("Deleção por TTL executada para %s", file_id)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Erro interno ao efetuar TTL de %s: %s", file_id, e)

    async def get_content(self, project_id: UUID, file_id: str) -> Optional[str]:
        """Recupera conteúdo YAML lendo via thread, útil pra rota GET."""
        yaml_path = self._base_dir / str(project_id) / f"{file_id}.yaml"

        def _read_sync() -> Optional[str]:
            if not yaml_path.exists() or not yaml_path.is_file():
                return None
            return yaml_path.read_text(encoding="utf-8")

        return await asyncio.to_thread(_read_sync)
