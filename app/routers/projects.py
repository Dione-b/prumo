import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.project import create_project as create_project_svc

router = APIRouter(prefix="/projects", tags=["Projects"])


class ProjectCreateRequest(BaseModel):
    """Request schema for creating a new project."""

    name: str = Field(..., max_length=255, description="Project name")
    description: str | None = Field(None, description="Project description")


class ProjectResponse(BaseModel):
    """Response schema for project creation."""

    id: uuid.UUID
    name: str
    description: str | None
    llm_model: str
    namespace: str

    model_config = ConfigDict(from_attributes=True)


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(
    payload: ProjectCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """Create a new project for context ingestion."""
    record = await create_project_svc(
        db=db,
        name=payload.name,
        description=payload.description,
    )

    return ProjectResponse.model_validate(record)
