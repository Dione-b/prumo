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
