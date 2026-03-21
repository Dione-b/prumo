from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectResponse

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    request: ProjectCreate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Cria um novo projeto."""
    new_project = Project(
        name=request.name,
        description=request.description,
    )
    db.add(new_project)
    await db.flush()
    await db.refresh(new_project)
    await db.commit()

    return ProjectResponse(
        id=new_project.id,
        name=new_project.name,
        description=new_project.description,
        created_at=new_project.created_at,
    )


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Lista todos os projetos."""
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    projects = result.scalars().all()

    return [
        ProjectResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            created_at=p.created_at,
        )
        for p in projects
    ]


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna detalhes de um projeto."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        created_at=project.created_at,
    )
