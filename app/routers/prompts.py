"""Router for YAML prompt generation (Phase 3b).

C_03: File I/O is a router-level side effect — the service returns a pure DTO.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.schemas.prompt_generator import (
    GeneratedPrompt,
    PromptStrategyConfig,
    PromptTier,
)
from app.services.prompt_generator import PromptGeneratorService

logger = structlog.get_logger()

router = APIRouter(prefix="/prompts", tags=["Prompts"])

_OUTPUT_DIR = Path(settings.output_dir)


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

    file_path: str | None = None
    tier: str
    confidence: str
    strategies_applied: list[str]
    warnings: list[str]
    yaml_prompt: str


# ── Dependencies ────────────────────────────────────────────────────────────


def _get_prompt_service() -> PromptGeneratorService:
    return PromptGeneratorService()


# ── Endpoint ────────────────────────────────────────────────────────────────


@router.post(
    "/generate-cursor-yaml",
    response_model=GeneratePromptResponse,
    summary="Generate a structured YAML prompt for the Cursor IDE",
)
async def generate_cursor_yaml(
    request: GeneratePromptRequest,
    session: AsyncSession = Depends(get_db),
    service: PromptGeneratorService = Depends(_get_prompt_service),
) -> GeneratePromptResponse:
    """Generate a YAML prompt and persist it to disk.

    1. Delegates entirely to PromptGeneratorService (pure DTO, C_03).
    2. Writes the YAML file as a router-level side effect.
    3. Returns metadata + file path.
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

    # ── C_03: File I/O side effect belongs to the router ──
    file_path: str | None = None
    try:
        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        safe_intent = (
            request.intent[:30]
            .replace(" ", "_")
            .replace("/", "_")
            .replace("\\", "_")
            .lower()
        )
        file_name = f"prompt_{request.project_id}_{safe_intent}.yaml"
        full_path = _OUTPUT_DIR / file_name
        full_path.write_text(result.yaml_prompt, encoding="utf-8")
        file_path = str(full_path)

        logger.info(
            "prompt_yaml_saved",
            file_path=file_path,
            tier=result.tier,
            confidence=result.confidence,
        )
    except OSError as exc:
        logger.warning("prompt_yaml_save_failed", error=str(exc))

    return GeneratePromptResponse(
        file_path=file_path,
        tier=result.tier,
        confidence=result.confidence,
        strategies_applied=result.strategies_applied,
        warnings=result.warnings,
        yaml_prompt=result.yaml_prompt,
    )
