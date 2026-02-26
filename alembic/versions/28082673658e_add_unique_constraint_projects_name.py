"""add_unique_constraint_projects_name

Revision ID: 28082673658e
Revises: c3f8a2b1d4e7
Create Date: 2026-02-25 12:38:45.286097

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '28082673658e'
down_revision: str | Sequence[str] | None = 'c3f8a2b1d4e7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add UNIQUE constraint on projects.name for bootstrap idempotency."""
    op.create_unique_constraint('uq_projects_name', 'projects', ['name'])


def downgrade() -> None:
    """Remove UNIQUE constraint on projects.name."""
    op.drop_constraint('uq_projects_name', 'projects', type_='unique')
