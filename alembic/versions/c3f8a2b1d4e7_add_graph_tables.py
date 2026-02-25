"""add_graph_tables

Revision ID: c3f8a2b1d4e7
Revises: 08a93ce9d65b
Create Date: 2026-02-25 02:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3f8a2b1d4e7"
down_revision: str | Sequence[str] | None = "08a93ce9d65b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create graph_nodes and graph_edges tables with HNSW index."""
    # Ensure pgvector extension exists (idempotent).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # --- graph_nodes ---
    op.create_table(
        "graph_nodes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "embedding",
            postgresql.ARRAY(sa.Float(), dimensions=1),
            nullable=True,
            comment="pgvector Vector(768) — see raw SQL index below",
        ),
        sa.Column(
            "source_document_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("community_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            onupdate=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name", name="uq_graph_nodes_project_name"),
    )

    # Replace the ARRAY column with a real pgvector column via raw DDL,
    # because SQLAlchemy's Column() doesn't natively support Vector(768).
    op.execute(
        "ALTER TABLE graph_nodes "
        "ALTER COLUMN embedding TYPE vector(768) "
        "USING embedding::vector(768)"
    )

    # HNSW index for cosine similarity search.
    op.execute(
        "CREATE INDEX ix_graph_nodes_embedding_hnsw "
        "ON graph_nodes USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )

    # B-tree indexes for common lookups.
    op.create_index(
        "ix_graph_nodes_project_id", "graph_nodes", ["project_id"]
    )
    op.create_index(
        "ix_graph_nodes_community_id", "graph_nodes", ["community_id"]
    )

    # --- graph_edges ---
    op.create_table(
        "graph_edges",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("source_node_id", sa.UUID(), nullable=False),
        sa.Column("target_node_id", sa.UUID(), nullable=False),
        sa.Column("relation_type", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "weight", sa.Float(), nullable=False, server_default=sa.text("1.0")
        ),
        sa.Column(
            "confidence",
            sa.String(length=10),
            nullable=False,
            server_default=sa.text("'MEDIUM'"),
        ),
        sa.Column(
            "source_document_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(
            ["source_node_id"],
            ["graph_nodes.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_node_id"],
            ["graph_nodes.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_graph_edges_project_id", "graph_edges", ["project_id"]
    )
    op.create_index(
        "ix_graph_edges_source_node_id", "graph_edges", ["source_node_id"]
    )
    op.create_index(
        "ix_graph_edges_target_node_id", "graph_edges", ["target_node_id"]
    )

    # --- Update KnowledgeDocument status constraint ---
    # Drop old constraint, re-create with READY_PARTIAL included.
    op.drop_constraint(
        "ck_knowledge_status_valid", "knowledge_documents", type_="check"
    )
    op.create_check_constraint(
        "ck_knowledge_status_valid",
        "knowledge_documents",
        "status IN ('PENDING', 'PROCESSING', 'READY', 'READY_PARTIAL', 'ERROR')",
    )

    # Add updated_at column to knowledge_documents for cache invalidation.
    op.add_column(
        "knowledge_documents",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Drop graph tables and revert status constraint."""
    op.drop_column("knowledge_documents", "updated_at")

    op.drop_constraint(
        "ck_knowledge_status_valid", "knowledge_documents", type_="check"
    )
    op.create_check_constraint(
        "ck_knowledge_status_valid",
        "knowledge_documents",
        "status IN ('PENDING', 'PROCESSING', 'READY', 'ERROR')",
    )

    op.drop_table("graph_edges")

    op.execute("DROP INDEX IF EXISTS ix_graph_nodes_embedding_hnsw")
    op.drop_table("graph_nodes")
