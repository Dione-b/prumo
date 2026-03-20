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

from app.models.project import Project


async def create_project(
    db: AsyncSession, name: str, description: str | None = None
) -> Project:
    """Cria e persiste um novo Project."""
    record = Project(
        name=name,
        description=description,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def get_project(db: AsyncSession, project_id: uuid.UUID) -> Project | None:
    """Busca um Project pelo UUID."""
    return await db.get(Project, project_id)
