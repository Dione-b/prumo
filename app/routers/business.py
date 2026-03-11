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
