import uuid

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.domain.strategies.factory import VALID_STACKS
from app.services.project import create_project as create_project_svc

router = APIRouter(prefix="/projects", tags=["Projects"])


class ProjectCreateRequest(BaseModel):
    """Request schema for creating a new project."""

    name: str = Field(..., max_length=255, description="Project name")
    description: str | None = Field(None, description="Project description")
    stack: str = Field(..., description="Project stack target")

    @field_validator("stack")
    @classmethod
    def validate_stack(cls, v: str) -> str:
        """Ensure the chosen stack is valid."""
        if v.lower() not in VALID_STACKS:
            raise ValueError(f"Stack {v} is not valid. Choose from {VALID_STACKS}")
        return v.lower()


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
    request: Request,
    response: Response,
    payload: ProjectCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """Create a new project for context ingestion."""
    record = await create_project_svc(
        db=db,
        name=payload.name,
        stack=payload.stack,
        description=payload.description,
    )

    if "hx-request" in request.headers:
        response.headers["HX-Redirect"] = "/ui"

    return ProjectResponse.model_validate(record)
