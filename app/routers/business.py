from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.business_rule import BusinessRule

router = APIRouter(prefix="/business", tags=["Business Rules"])


@router.delete("/rules/{rule_id}")
async def delete_business_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Delete a specific business rule by ID."""
    async with db.begin():
        stmt = delete(BusinessRule).where(BusinessRule.id == rule_id)
        result = await db.execute(stmt)
        if result.rowcount == 0:  # type: ignore[attr-defined]
            raise HTTPException(
                status_code=404, detail=f"Business rule {rule_id} not found"
            )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "Business rule deleted successfully"},
    )
