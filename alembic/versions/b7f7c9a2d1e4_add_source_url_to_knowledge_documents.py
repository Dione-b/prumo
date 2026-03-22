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

"""add_source_url_to_knowledge_documents

Revision ID: b7f7c9a2d1e4
Revises: 756b12e9d829
Create Date: 2026-03-21 11:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7f7c9a2d1e4"
down_revision: str | Sequence[str] | None = "756b12e9d829"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add source URL metadata to knowledge documents."""
    op.add_column(
        "knowledge_documents",
        sa.Column("source_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Remove source URL metadata from knowledge documents."""
    op.drop_column("knowledge_documents", "source_url")
