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


"""add_unique_constraint_projects_name

Revision ID: 28082673658e
Revises: c3f8a2b1d4e7
Create Date: 2026-02-25 12:38:45.286097

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "28082673658e"
down_revision: str | Sequence[str] | None = "c3f8a2b1d4e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add UNIQUE constraint on projects.name for bootstrap idempotency."""
    op.create_unique_constraint("uq_projects_name", "projects", ["name"])


def downgrade() -> None:
    """Remove UNIQUE constraint on projects.name."""
    op.drop_constraint("uq_projects_name", "projects", type_="unique")
