from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import ValidationError

from app.application.use_cases import IngestBusinessUseCase, ProjectNotFoundError
from app.composition import provide_ingest_business_use_case
from app.config import settings
from app.logger import get_logger
from app.schemas.business_rule import (
    BusinessRuleSchema,
    IngestBusinessRequest,
    IngestBusinessResponse,
)

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
    use_case: IngestBusinessUseCase = Depends(provide_ingest_business_use_case),
    _: str = Depends(_verify_api_key),
) -> IngestBusinessResponse:
    """Ingest raw meeting notes, extract structured data via Gemini, and persist."""
    try:
        result = await use_case.execute(
            project_id=payload.project_id,
            raw_text=payload.raw_text,
            source=payload.source,
        )
        extracted = BusinessRuleSchema(
            client_name=result.extraction.client_name,
            core_objective=result.extraction.core_objective,
            technical_constraints=list(result.extraction.technical_constraints),
            acceptance_criteria=list(result.extraction.acceptance_criteria),
            additional_notes=result.extraction.additional_notes,
            confidence_level=result.extraction.confidence_level,
        )
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
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

    log.info(
        "business_rule_ingested",
        record_id=str(result.record.id),
        project_id=str(payload.project_id),
        confidence=extracted.confidence_level,
    )

    return IngestBusinessResponse(
        record_id=str(result.record.id),
        data=extracted,
        warnings=extracted.warnings,
        saved_in_db=True,
    )
