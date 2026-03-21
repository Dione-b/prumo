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


from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy models."""


# Re-export all models so Alembic autogenerate detects them.
# These imports MUST come after `Base` is defined to avoid circular imports.
from .cookbook import CookbookRecipe as CookbookRecipe  # noqa: E402
from .knowledge import KnowledgeDocument as KnowledgeDocument  # noqa: E402
from .project import Project as Project  # noqa: E402
from .prompt import GeneratedPromptModel as GeneratedPromptModel  # noqa: E402

__all__ = [
    "Base",
    "Project",
    "CookbookRecipe",
    "KnowledgeDocument",
    "GeneratedPromptModel",
]
