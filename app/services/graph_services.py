from uuid import UUID

from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.graph import GraphEdge, GraphNode
from app.models.knowledge import KnowledgeDocument


async def delete_knowledge_document(db: AsyncSession, document_id: UUID) -> bool:
    """Hard delete a document and clean up its orphaned knowledge graph elements.

    Any graph node that relies *only* on this document is deleted, cascading its edges
    and vector data (pgvector embeddings are inside graph_nodes).
    """
    # Find all nodes referencing this document.
    # source_document_ids is a JSONB array of UUID strings.
    stmt = text(
        """
        SELECT id, source_document_ids
        FROM graph_nodes
        WHERE source_document_ids @> :doc_id_json
        """
    )
    result = await db.execute(stmt, {"doc_id_json": f'["{document_id}"]'})
    nodes = result.fetchall()

    nodes_to_delete = []
    nodes_to_update = []

    for node_id, source_ids in nodes:
        if isinstance(source_ids, list):
            doc_uuid_str = str(document_id)
            if doc_uuid_str in source_ids:
                source_ids.remove(doc_uuid_str)

            if not source_ids:
                nodes_to_delete.append(node_id)
            else:
                nodes_to_update.append(
                    {"id": node_id, "source_document_ids": source_ids}
                )

    # Delete nodes that have no other source documents
    if nodes_to_delete:
        await db.execute(delete(GraphNode).where(GraphNode.id.in_(nodes_to_delete)))
    # GraphEdge has ON DELETE CASCADE to GraphNode.id.

    # Update nodes that still have other sources
    for node_data in nodes_to_update:
        await db.execute(
            text(
                "UPDATE graph_nodes SET source_document_ids = :source_ids "
                "WHERE id = :node_id"
            ),
            {
                "source_ids": str(node_data["source_document_ids"]).replace("'", '"'),
                "node_id": node_data["id"],
            },
        )

    # Finally, delete the document itself
    doc_delete_stmt = delete(KnowledgeDocument).where(
        KnowledgeDocument.id == document_id
    )
    doc_result = await db.execute(doc_delete_stmt)

    return bool(doc_result.rowcount > 0)  # type: ignore[attr-defined,no-any-return]


async def purge_project_knowledge(
    db: AsyncSession, project_id: UUID, keep_documents: bool = False
) -> None:
    """Nuke the graph nodes, edges, and optionally all documents in a project."""

    # 1. Edges are removed by DB cascade, but let's be thorough if we want to nuke all
    # edges first. Actually, ON DELETE CASCADE works on target/source node.
    await db.execute(delete(GraphEdge).where(GraphEdge.project_id == project_id))

    # 2. Delete nodes (this cleans up pgvector)
    await db.execute(delete(GraphNode).where(GraphNode.project_id == project_id))

    # 3. If requested, drop all documents
    if not keep_documents:
        await db.execute(
            delete(KnowledgeDocument).where(KnowledgeDocument.project_id == project_id)
        )
