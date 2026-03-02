"""Router for YAML prompt generation (Phase 3b).

C_03: File I/O is a router-level side effect — the service returns a pure DTO.
"""

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
from app.schemas.prompt_generator import (
    GeneratedPrompt,
    PromptStrategyConfig,
    PromptTier,
)
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
        # Save to both, return DB ID as requested by ADR
        await self._local.save(project_id, content, metadata, ttl)
        return await self._db.save(project_id, content, metadata, ttl)

    async def get_content(self, project_id: UUID, file_id: str) -> str | None:
        # Prioritize Database
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
    """Payload for YAML prompt generation."""

    project_id: UUID
    intent: str = Field(..., min_length=3, max_length=2000)
    target_files: list[str] = Field(default_factory=list)
    force_tier: PromptTier | None = None
    include_few_shot: bool = True
    include_skeletons: bool = True
    extra_prohibited: list[str] = Field(default_factory=list)
    extra_required: list[str] = Field(default_factory=list)


class GeneratePromptResponse(BaseModel):
    """Response with the generated prompt metadata and optional file path."""

    prompt_id: str
    tier: str
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
    summary="Generate a structured YAML prompt for the Cursor IDE",
)
async def generate_cursor_yaml(
    request: GeneratePromptRequest,
    session: AsyncSession = Depends(get_db),
    service: PromptGeneratorService = Depends(get_prompt_service),
) -> GeneratePromptResponse:
    """Generate a YAML prompt and persist it to the active storage.

    1. Delegates entirely to PromptGeneratorService (pure DTO, C_03).
    2. Writes the YAML file as a router-level side effect passing storage.
    3. Returns metadata + prompt_id.
    """
    strategy = PromptStrategyConfig(
        force_tier=request.force_tier,
        extra_prohibited=request.extra_prohibited,
        extra_required=request.extra_required,
        include_few_shot=request.include_few_shot,
        include_skeletons=request.include_skeletons,
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

    # Note: caller is responsible for the commit boundary in C_03
    await session.commit()

    return GeneratePromptResponse(
        prompt_id=result.prompt_id,
        tier=result.tier,
        confidence=result.confidence,
        strategies_applied=result.strategies_applied,
        warnings=result.warnings,
        yaml_prompt=result.yaml_prompt,
    )


@router.get(
    "/{prompt_id}",
    response_class=PlainTextResponse,
    summary="Download the YAML prompt file by ID",
)
async def download_prompt(
    prompt_id: str,
    project_id: UUID = Query(...),
    storage: IOutputStorage = Depends(get_prompt_storage),
) -> str:
    """Retrieves the YAML content by ID from the configured storage engine."""
    content = await storage.get_content(project_id, prompt_id)
    if not content:
        raise HTTPException(
            status_code=404,
            detail="Prompt YAML file not found or expired for this project.",
        )
    return content
