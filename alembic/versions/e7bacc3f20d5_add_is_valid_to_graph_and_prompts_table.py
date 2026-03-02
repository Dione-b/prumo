"""add_is_valid_to_graph_and_prompts_table

Revision ID: e7bacc3f20d5
Revises: d524a3e08769
Create Date: 2026-03-01 15:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7bacc3f20d5"
down_revision: str | None = "d524a3e08769"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add is_valid to graph_nodes
    op.add_column(
        "graph_nodes",
        sa.Column("is_valid", sa.Boolean(), server_default="true", nullable=False),
    )

    # Add is_valid to graph_edges
    op.add_column(
        "graph_edges",
        sa.Column("is_valid", sa.Boolean(), server_default="true", nullable=False),
    )

    # Create generated_prompts table
    op.create_table(
        "generated_prompts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "metadata_info",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("generated_prompts")
    op.drop_column("graph_edges", "is_valid")
    op.drop_column("graph_nodes", "is_valid")
