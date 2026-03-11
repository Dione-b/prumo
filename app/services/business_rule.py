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


import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business_rule import BusinessRule
from app.schemas.business_rule import BusinessRuleSchema


async def create_business_rule(
    db: AsyncSession,
    project_id: uuid.UUID,
    raw_text: str,
    extracted_data: BusinessRuleSchema,
    source: str | None = None,
) -> BusinessRule:
    """Create and persist a new BusinessRule record after extraction."""
    record = BusinessRule(
        project_id=project_id,
        raw_text=raw_text,
        client_name=extracted_data.client_name,
        core_objective=extracted_data.core_objective,
        technical_constraints=extracted_data.technical_constraints,
        acceptance_criteria=extracted_data.acceptance_criteria,
        additional_notes=extracted_data.additional_notes,
        confidence_level=extracted_data.confidence_level,
        content_type="structured",
        namespace="business",
        source=source,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record
