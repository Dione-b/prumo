"""Community detection via Leiden algorithm + summary generation.

Loads the graph from the database, builds an igraph graph, runs
Leiden community detection via asyncio.to_thread(), assigns community
IDs back to nodes, and generates summaries per community via Flash.

This service NEVER calls session.commit() directly — except when fired
as an independent background task via _fire_community_detection().
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import google.generativeai as genai  # type: ignore[import-untyped]
import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_maker
from app.models.graph import GraphEdge, GraphNode

logger = structlog.get_logger()

genai.configure(api_key=settings.gemini_api_key.get_secret_value())  # type: ignore[attr-defined]

# Minimum number of nodes required before community detection is useful.
_MIN_NODES_FOR_COMMUNITY = 5

_COMMUNITY_SUMMARY_INSTRUCTION = (
    "You are a knowledge-graph analyst. Given a list of entities and their "
    "relations within a community cluster, produce a concise summary (2-4 "
    "sentences) that captures the core theme and key relationships of this "
    "community. Output ONLY the summary text, no JSON wrapping."
)


def _run_leiden_sync(
    node_ids: list[str],
    edges: list[tuple[str, str, float]],
) -> dict[str, int]:
    """Run Leiden community detection synchronously — intended for asyncio.to_thread.

    Returns a mapping of node_id_str → community_id.
    """
    import igraph as ig  # type: ignore[import-untyped]
    import leidenalg  # type: ignore[import-untyped]

    # Build igraph graph from node/edge data.
    id_to_idx = {nid: idx for idx, nid in enumerate(node_ids)}
    graph = ig.Graph(directed=False)
    graph.add_vertices(len(node_ids))

    edge_list: list[tuple[int, int]] = []
    weights: list[float] = []

    for src, tgt, weight in edges:
        src_idx = id_to_idx.get(src)
        tgt_idx = id_to_idx.get(tgt)
        if src_idx is not None and tgt_idx is not None:
            edge_list.append((src_idx, tgt_idx))
            weights.append(weight)

    graph.add_edges(edge_list)
    graph.es["weight"] = weights  # type: ignore[index]

    partition = leidenalg.find_partition(
        graph,
        leidenalg.ModularityVertexPartition,
        weights=weights if weights else None,
    )

    return {
        node_ids[idx]: community_id
        for community_id, members in enumerate(partition)
        for idx in members
    }


async def check_community_readiness(
    session: AsyncSession,
    project_id: UUID,
) -> tuple[int, int]:
    """Check node and edge counts for a project in a single query.

    Returns (node_count, edge_count). Uses COUNT FILTER to
    Returns (node_count, edge_count). Uses subqueries in one statement
    to avoid 2 separate SELECTs (performance constraint).
    """
    node_count_q = (
        select(func.count()).where(GraphNode.project_id == project_id).scalar_subquery()
    )
    edge_count_q = (
        select(func.count()).where(GraphEdge.project_id == project_id).scalar_subquery()
    )

    result = await session.execute(
        select(node_count_q.label("nodes"), edge_count_q.label("edges"))
    )
    row = result.one()
    return int(row[0]), int(row[1])


async def run_community_detection(
    session: AsyncSession,
    project_id: UUID,
) -> int:
    """Detect communities in the project's knowledge graph.

    Loads all nodes and edges, runs Leiden, updates community_id on nodes.
    Does NOT call session.commit() — caller is responsible (C_03).

    Returns the number of communities detected.
    """
    node_count, edge_count = await check_community_readiness(session, project_id)

    if node_count < _MIN_NODES_FOR_COMMUNITY or edge_count == 0:
        logger.info(
            "community_detection_skipped",
            project_id=str(project_id),
            reason="insufficient_nodes_or_edges",
            node_count=node_count,
            edge_count=edge_count,
        )
        return 0

    # Load all node IDs.
    node_result = await session.execute(
        select(GraphNode.id).where(GraphNode.project_id == project_id)
    )
    node_ids = [str(row[0]) for row in node_result.all()]

    # Load all edges with weights.
    edge_result = await session.execute(
        select(
            GraphEdge.source_node_id,
            GraphEdge.target_node_id,
            GraphEdge.weight,
        ).where(GraphEdge.project_id == project_id)
    )
    edges = [(str(r[0]), str(r[1]), float(r[2])) for r in edge_result.all()]

    # Run Leiden in a thread (CPU-bound).
    node_communities = await asyncio.to_thread(_run_leiden_sync, node_ids, edges)

    # Write community assignments back.
    for node_id_str, community_id in node_communities.items():
        await session.execute(
            update(GraphNode)
            .where(GraphNode.id == node_id_str)  # type: ignore[arg-type]
            .values(community_id=community_id)
        )

    await session.flush()

    num_communities = len(set(node_communities.values()))
    logger.info(
        "community_detection_complete",
        project_id=str(project_id),
        num_communities=num_communities,
        total_nodes=len(node_ids),
    )

    return num_communities


def _generate_summary_sync(entities_text: str) -> str:
    """Generate a community summary via Flash — runs in thread."""
    model = genai.GenerativeModel(  # type: ignore[attr-defined]
        model_name="gemini-1.5-flash-002",
        system_instruction=_COMMUNITY_SUMMARY_INSTRUCTION,
    )
    response = model.generate_content(entities_text)
    return str(response.text).strip()


async def generate_community_summaries(
    session: AsyncSession,
    project_id: UUID,
) -> dict[int, str]:
    """Generate text summaries for each detected community.

    Returns a dict of community_id → summary string.
    Does NOT call session.commit() (C_03).
    """
    stmt = (
        select(
            GraphNode.community_id,
            func.array_agg(GraphNode.name),
            func.array_agg(GraphNode.description),
        )
        .where(
            GraphNode.project_id == project_id,
            GraphNode.community_id.is_not(None),
        )
        .group_by(GraphNode.community_id)
    )

    result = await session.execute(stmt)
    rows = result.all()

    summaries: dict[int, str] = {}

    for community_id, names, descriptions in rows:
        if community_id is None:
            continue

        entities_text = "\n".join(
            f"- {name}: {desc}" for name, desc in zip(names, descriptions)
        )

        try:
            summary = await asyncio.to_thread(_generate_summary_sync, entities_text)
            summaries[int(community_id)] = summary
        except Exception:  # noqa: BLE001
            logger.warning(
                "community_summary_failed",
                community_id=community_id,
                project_id=str(project_id),
            )

    return summaries


async def fire_community_detection(project_id: UUID) -> None:
    """Fire-and-forget wrapper for community detection with exception handling.

    Intended to be used with asyncio.create_task(). Owns its own session
    and transaction (C_03 — background tasks create their own sessions).
    """
    try:
        async with async_session_maker() as session:
            async with session.begin():
                num = await run_community_detection(session, project_id)
                if num > 0:
                    await generate_community_summaries(session, project_id)

        logger.info(
            "fire_community_detection_complete",
            project_id=str(project_id),
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "fire_community_detection_failed",
            project_id=str(project_id),
        )
