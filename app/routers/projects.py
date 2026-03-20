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

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases import CreateProjectUseCase
from app.composition import provide_create_project_use_case
from app.database import get_db
from app.models.project import Project

router = APIRouter(prefix="/projects", tags=["Projects"])


class ProjectCreateRequest(BaseModel):
    """Request schema para criação de projeto."""

    name: str = Field(..., max_length=255, description="Project name")
    description: str | None = Field(None, description="Project description")


class ProjectResponse(BaseModel):
    """Response schema para projeto."""

    id: uuid.UUID
    name: str
    description: str | None

    model_config = ConfigDict(from_attributes=True)


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(
    request: Request,
    response: Response,
    payload: ProjectCreateRequest,
    use_case: CreateProjectUseCase = Depends(provide_create_project_use_case),
) -> ProjectResponse:
    """Cria um novo projeto para ingestão de contexto."""
    record = await use_case.execute(
        name=payload.name,
        description=payload.description,
    )

    if "hx-request" in request.headers:
        response.headers["HX-Redirect"] = "/ui"

    return ProjectResponse.model_validate(record)


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    db: AsyncSession = Depends(get_db),
) -> list[ProjectResponse]:
    """Lista todos os projetos."""
    result = await db.execute(
        select(Project).order_by(Project.created_at.desc())
    )
    projects = result.scalars().all()
    return [ProjectResponse.model_validate(p) for p in projects]
