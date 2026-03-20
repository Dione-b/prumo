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


"""Router para geração de prompts YAML."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.infrastructure.storage.database import DatabaseStorage
from app.infrastructure.storage.local import LocalStorage
from app.interfaces.storage import IOutputStorage
from app.schemas.prompt_generator import GeneratedPrompt, PromptStrategyConfig
from app.services.prompt_generator import PromptGeneratorService

logger = structlog.get_logger()

router = APIRouter(prefix="/prompts", tags=["Prompts"])


# ── Storage Adapter ──────────────────────────────────────────────────────────


class BothStorage(IOutputStorage):
    def __init__(self, db_storage: DatabaseStorage, local_storage: LocalStorage):
        self._db = db_storage
        self._local = local_storage

    async def save(
        self,
        project_id: UUID,
        content: str,
        metadata: dict[str, Any],
        ttl: int | None = None,
    ) -> str:
        await self._local.save(project_id, content, metadata, ttl)
        return await self._db.save(project_id, content, metadata, ttl)

    async def get_content(self, project_id: UUID, file_id: str) -> str | None:
        res = await self._db.get_content(project_id, file_id)
        if res is not None:
            return res
        return await self._local.get_content(project_id, file_id)


def get_prompt_storage(session: AsyncSession = Depends(get_db)) -> IOutputStorage:
    backend = settings.prompt_storage_backend.lower()
    if backend == "both":
        return BothStorage(DatabaseStorage(session), LocalStorage())
    elif backend == "local":
        logger.warning(
            "Using 'local' storage single backend in "
            "potentially containerized environment."
        )
        return LocalStorage()
    else:
        return DatabaseStorage(session)


# ── Request / Response Schemas ──────────────────────────────────────────────


class GeneratePromptRequest(BaseModel):
    """Payload para geração de prompt YAML."""

    project_id: UUID
    intent: str = Field(..., min_length=3, max_length=2000)
    target_files: list[str] = Field(default_factory=list)
    extra_prohibited: list[str] = Field(default_factory=list)
    extra_required: list[str] = Field(default_factory=list)


class GeneratePromptResponse(BaseModel):
    """Response com metadata do prompt gerado."""

    prompt_id: str
    confidence: str
    strategies_applied: list[str]
    warnings: list[str]
    yaml_prompt: str


# ── Dependencies ────────────────────────────────────────────────────────────


def get_prompt_service(
    storage: IOutputStorage = Depends(get_prompt_storage),
) -> PromptGeneratorService:
    return PromptGeneratorService(storage)


# ── Endpoint ────────────────────────────────────────────────────────────────


@router.post(
    "/generate-cursor-yaml",
    response_model=GeneratePromptResponse,
    summary="Gera um prompt YAML estruturado para o Cursor IDE",
)
async def generate_cursor_yaml(
    request: GeneratePromptRequest,
    session: AsyncSession = Depends(get_db),
    service: PromptGeneratorService = Depends(get_prompt_service),
) -> GeneratePromptResponse:
    """Gera prompt YAML e persiste no storage ativo.

    C_03: NUNCA chama session.commit() dentro do service.
    """
    strategy = PromptStrategyConfig(
        extra_prohibited=request.extra_prohibited,
        extra_required=request.extra_required,
    )

    result: GeneratedPrompt = await service.generate_prompt(
        session=session,
        project_id=request.project_id,
        task_intent=request.intent,
        target_files=request.target_files,
        strategy_overrides=strategy,
    )

    if result.confidence == "LOW" and not result.yaml_prompt:
        raise HTTPException(
            status_code=500,
            detail="Prompt generation failed with insufficient context.",
        )

    await session.commit()

    return GeneratePromptResponse(
        prompt_id=result.prompt_id,
        confidence=result.confidence,
        strategies_applied=result.strategies_applied,
        warnings=result.warnings,
        yaml_prompt=result.yaml_prompt,
    )


@router.get(
    "/{prompt_id}",
    response_class=PlainTextResponse,
    summary="Baixa o prompt YAML pelo ID",
)
async def download_prompt(
    prompt_id: str,
    project_id: UUID = Query(...),
    storage: IOutputStorage = Depends(get_prompt_storage),
) -> str:
    """Recupera o YAML pelo ID do storage configurado."""
    content = await storage.get_content(project_id, prompt_id)
    if not content:
        raise HTTPException(
            status_code=404,
            detail="Prompt YAML file not found or expired for this project.",
        )
    return content
