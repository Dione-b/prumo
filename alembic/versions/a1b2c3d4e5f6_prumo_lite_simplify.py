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


"""prumo_lite_simplify

Remove graph tables, simplify projects and knowledge_documents.

Revision ID: a1b2c3d4e5f6
Revises: 28082673658e
Create Date: 2026-03-20 17:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "28082673658e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Simplify schema for Prumo Lite."""
    # 1. Drop graph tables (se existirem — podem já ter sido removidas)
    op.execute("DROP TABLE IF EXISTS graph_edges CASCADE")
    op.execute("DROP TABLE IF EXISTS graph_nodes CASCADE")

    # 2. Drop table plans (não usada no Lite)
    op.execute("DROP TABLE IF EXISTS plans CASCADE")

    # 3. Simplificar projects — remover colunas não usadas
    op.drop_column("projects", "llm_model")
    op.drop_column("projects", "namespace")
    op.drop_column("projects", "config_json")

    # 4. Simplificar knowledge_documents
    # Remover colunas de cache Gemini
    op.drop_column("knowledge_documents", "gemini_file_uri")
    op.drop_column("knowledge_documents", "gemini_cache_name")
    op.drop_column("knowledge_documents", "cache_expires_at")
    op.drop_column("knowledge_documents", "metadata_json")

    # Renomear raw_content → content
    op.alter_column(
        "knowledge_documents",
        "raw_content",
        new_column_name="content",
    )

    # Adicionar coluna embedding (Vector 768)
    op.add_column(
        "knowledge_documents",
        sa.Column("embedding", Vector(768), nullable=True),
    )

    # Adicionar coluna error_message
    op.add_column(
        "knowledge_documents",
        sa.Column("error_message", sa.Text(), nullable=True),
    )

    # Adicionar coluna updated_at
    op.add_column(
        "knowledge_documents",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Revert Prumo Lite simplification."""
    # knowledge_documents — reverter
    op.drop_column("knowledge_documents", "updated_at")
    op.drop_column("knowledge_documents", "error_message")
    op.drop_column("knowledge_documents", "embedding")

    op.alter_column(
        "knowledge_documents",
        "content",
        new_column_name="raw_content",
    )

    op.add_column(
        "knowledge_documents",
        sa.Column(
            "metadata_json",
            sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column(
            "cache_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("gemini_cache_name", sa.Text(), nullable=True),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("gemini_file_uri", sa.Text(), nullable=True),
    )

    # projects — reverter
    op.add_column(
        "projects",
        sa.Column(
            "config_json",
            sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "projects",
        sa.Column(
            "namespace",
            sa.String(length=50),
            nullable=False,
            server_default="default",
        ),
    )
    op.add_column(
        "projects",
        sa.Column(
            "llm_model",
            sa.String(length=100),
            nullable=False,
            server_default="gemini-1.5-pro",
        ),
    )
