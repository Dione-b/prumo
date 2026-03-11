from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from app.application.use_cases import (
    BusinessRuleNotFoundError,
    DeleteBusinessRuleUseCase,
)
from app.composition import provide_delete_business_rule_use_case

router = APIRouter(prefix="/business", tags=["Business Rules"])


@router.delete("/rules/{rule_id}")
async def delete_business_rule(
    rule_id: UUID,
    use_case: DeleteBusinessRuleUseCase = Depends(
        provide_delete_business_rule_use_case
    ),
) -> Any:
    """Delete a specific business rule by ID."""
    try:
        await use_case.execute(rule_id=rule_id)
    except BusinessRuleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "Business rule deleted successfully"},
    )
