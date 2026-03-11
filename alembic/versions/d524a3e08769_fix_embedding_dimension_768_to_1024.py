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


"""fix_embedding_dimension_768_to_1024

Revision ID: d524a3e08769
Revises: 28082673658e
Create Date: 2026-02-26 10:12:54.254313

"""

from collections.abc import Sequence

# IMPORTANT: import pgvector type so autogenerate recognizes it in the future
from pgvector.sqlalchemy import VECTOR  # noqa: F401

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d524a3e08769"
down_revision: str | Sequence[str] | None = "28082673658e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Widen the embedding column from Vector(768) to Vector(1024).

    Qwen3-embedding:0.6b outputs 1024-dimensional vectors.
    The old 768 dimension was incorrect and would cause runtime errors.

    Existing embeddings (if any) are cleared because they were either:
      - Never stored (dimension mismatch would have errored), or
      - Stored with wrong dimensions and must be re-embedded.
    """
    # 1. Drop the HNSW index (cannot ALTER a vector column with an index).
    op.execute("DROP INDEX IF EXISTS ix_graph_nodes_embedding_hnsw")

    # 2. Clean stale embeddings that don't match new dimension.
    #    (This handles any existing 768d records safely).
    op.execute(
        """
        DELETE FROM graph_nodes
        WHERE embedding IS NOT NULL AND array_length(embedding, 1) != 1024
        """
    )

    # 3. Alter column type from Vector(768) to Vector(1024).
    op.execute("ALTER TABLE graph_nodes ALTER COLUMN embedding TYPE vector(1024)")

    # 4. Recreate the HNSW index with optimal params (m=16, ef_construction=64).
    op.execute(
        """
        CREATE INDEX ix_graph_nodes_embedding_hnsw
        ON graph_nodes USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )


def downgrade() -> None:
    """Revert embedding column back to Vector(768)."""
    # 1. Drop the HNSW index
    op.execute("DROP INDEX IF EXISTS ix_graph_nodes_embedding_hnsw")

    # 2. Delete embeddings with 1024d (since they won't fit in 768d column)
    op.execute(
        """
        DELETE FROM graph_nodes
        WHERE embedding IS NOT NULL AND array_length(embedding, 1) = 1024
        """
    )

    # 3. Revert column type to vector(768)
    op.execute("ALTER TABLE graph_nodes ALTER COLUMN embedding TYPE vector(768)")

    # 4. Recreate old index (with default parameters)
    op.execute(
        """
        CREATE INDEX ix_graph_nodes_embedding_hnsw
        ON graph_nodes USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )
