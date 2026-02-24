import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project


async def create_project(
    db: AsyncSession, name: str, description: str | None = None
) -> Project:
    """Create and persist a new Project record."""
    record = Project(name=name, description=description)
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def get_project(db: AsyncSession, project_id: uuid.UUID) -> Project | None:
    """Retrieve a Project record by its UUID."""
    return await db.get(Project, project_id)
