from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.logger import get_logger
from app.schemas.business_rule import (
    BusinessRuleSchema,
    IngestBusinessRequest,
    IngestBusinessResponse,
)
from app.services.business_rule import create_business_rule
from app.services.llm_gateway import LLMGateway
from app.services.project import get_project

log = get_logger(__name__)

router = APIRouter(prefix="/ingest", tags=["Ingestion"])

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def _verify_api_key(
    api_key: str | None = Security(_api_key_header),
) -> str:
    """Validate the static API key from the X-API-Key header."""
    if not api_key or api_key != settings.api_key.get_secret_value():
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
        )
    return api_key


@router.post("/business", response_model=IngestBusinessResponse)
async def ingest_business(
    payload: IngestBusinessRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(_verify_api_key),
) -> IngestBusinessResponse:
    """Ingest raw meeting notes, extract structured data via Gemini, and persist."""
    # 1. Verify project exists
    project = await get_project(db, payload.project_id)
    if not project:
        raise HTTPException(
            status_code=404,
            detail=f"Project {payload.project_id} not found",
        )

    # 2. Extract structured data via Ollama Native Async (C_02)
    try:
        gateway = LLMGateway()
        result = await gateway.extract_business_rules(
            payload.raw_text, BusinessRuleSchema
        )
    except ValidationError:
        raise HTTPException(
            status_code=422,
            detail=(
                "The model failed to extract the required data from the text. "
                "Try enriching the meeting note."
            ),
        )
    except Exception:
        log.exception("gemini_extraction_failed")
        raise HTTPException(
            status_code=500,
            detail="Erro interno ao processar a requisição LLM. Tente novamente.",
        )

    # 3. Persist
    record = await create_business_rule(
        db=db,
        project_id=payload.project_id,
        raw_text=payload.raw_text,
        extracted_data=result,
        source=payload.source,
    )

    log.info(
        "business_rule_ingested",
        record_id=str(record.id),
        project_id=str(payload.project_id),
        confidence=result.confidence_level,
    )

    return IngestBusinessResponse(
        record_id=str(record.id),
        data=result,
        warnings=result.warnings,
        saved_in_db=True,
    )
