"""Graph query engines: Local, Global, and Hybrid.

Implements the three LightRAG query modes:
- LOCAL: pgvector cosine similarity on nodes → CTE edge traversal → synthesis
- GLOBAL: community summaries → synthesis
- HYBRID: Local first → if confidence < threshold, Global → merge synthesis

All query methods use session for reads only. Synthesis calls go through
asyncio.to_thread() to avoid blocking the event loop (Gemini SDK is sync).
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import structlog
from google import genai
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.graph import EMBEDDING_DIMENSIONS, GraphNode
from app.schemas.graph import CommunityInfo, EdgeContext, NodeContext
from app.schemas.knowledge import AnswerCitation, KnowledgeAnswer

logger = structlog.get_logger()

client = genai.Client(api_key=settings.gemini_api_key.get_secret_value())

_EMBEDDING_MODEL = "models/text-embedding-004"
_TASK_TYPE_QUERY = "RETRIEVAL_QUERY"

# Number of top-k similar nodes for local queries.
_LOCAL_TOP_K = 10

# CTE traversal depth for edge expansion.
_CTE_MAX_DEPTH = 2

# Confidence threshold below which hybrid escalates to global.
_HYBRID_CONFIDENCE_THRESHOLD = "MEDIUM"

_SYNTHESIS_SYSTEM_INSTRUCTION = (
    "You are an expert Context Orchestrator for an Agentic IDE. "
    "Answer the user's question based strictly on the provided graph context. "
    "You MUST provide citations (entity names or snippets). "
    "If the answer cannot be found in the context, you MUST state 'I don't know'. "
    "Output ONLY valid JSON matching the provided schema."
)


def _embed_query_sync(query: str) -> list[float]:
    """Embed a query string synchronously — runs in thread."""
    result = client.models.embed_content(
        model=_EMBEDDING_MODEL,
        contents=query,
        config=genai.types.EmbedContentConfig(
            task_type=_TASK_TYPE_QUERY,
            output_dimensionality=EMBEDDING_DIMENSIONS,
        ),
    )
    embeddings = getattr(result, "embeddings", None)
    if not embeddings or not embeddings[0].values:
        return []
    return [float(v) for v in embeddings[0].values]


def _synthesize_sync(context: str, question: str) -> KnowledgeAnswer:
    """Run synthesis via Gemini Pro synchronously — runs in thread."""
    prompt = f"GRAPH CONTEXT:\n{context}\n\nQUESTION:\n{question}"

    response = client.models.generate_content(
        model=settings.gemini_synthesis_model,
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=KnowledgeAnswer,
            temperature=0.0,
            system_instruction=_SYNTHESIS_SYSTEM_INSTRUCTION,
        ),
    )
    return KnowledgeAnswer.model_validate_json(str(response.text))


async def _get_query_embedding(question: str) -> list[float]:
    """Get embedding for the query string."""
    return await asyncio.to_thread(_embed_query_sync, question)


async def _find_similar_nodes(
    session: AsyncSession,
    project_id: UUID,
    query_embedding: list[float],
    top_k: int = _LOCAL_TOP_K,
) -> list[NodeContext]:
    """Find top-k similar nodes via pgvector cosine distance."""
    # pgvector cosine distance: 1 - cosine_similarity. Lower = more similar.
    stmt = text("""
        SELECT
            name,
            entity_type,
            description,
            1 - (embedding <=> :query_embedding::vector) AS score,
            community_id
        FROM graph_nodes
        WHERE project_id = :project_id
            AND embedding IS NOT NULL
        ORDER BY embedding <=> :query_embedding::vector
        LIMIT :top_k
    """)

    result = await session.execute(
        stmt,
        {
            "project_id": str(project_id),
            "query_embedding": str(query_embedding),
            "top_k": top_k,
        },
    )

    return [
        NodeContext(
            name=row[0],
            entity_type=row[1],
            description=row[2],
            score=max(0.0, min(1.0, float(row[3]))),
            community_id=row[4],
        )
        for row in result.all()
    ]


async def _expand_edges(
    session: AsyncSession,
    project_id: UUID,
    node_names: list[str],
    max_depth: int = _CTE_MAX_DEPTH,
) -> list[EdgeContext]:
    """Expand edges from seed nodes using a recursive CTE.

    Uses CAST(:param AS text[]) for asyncpg compatibility with array params.
    """
    if not node_names:
        return []

    cte_query = text("""
        WITH RECURSIVE expanded AS (
            -- Base case: edges connected to seed nodes.
            SELECT
                e.source_node_id,
                e.target_node_id,
                e.relation_type,
                e.description,
                e.weight,
                e.confidence,
                sn.name AS source_name,
                tn.name AS target_name,
                1 AS depth
            FROM graph_edges e
            JOIN graph_nodes sn ON e.source_node_id = sn.id
            JOIN graph_nodes tn ON e.target_node_id = tn.id
            WHERE e.project_id = :project_id
                AND (sn.name = ANY(:seed_names) OR tn.name = ANY(:seed_names))

            UNION

            -- Recursive step: follow edges up to max_depth.
            SELECT
                e2.source_node_id,
                e2.target_node_id,
                e2.relation_type,
                e2.description,
                e2.weight,
                e2.confidence,
                sn2.name AS source_name,
                tn2.name AS target_name,
                ex.depth + 1
            FROM graph_edges e2
            JOIN graph_nodes sn2 ON e2.source_node_id = sn2.id
            JOIN graph_nodes tn2 ON e2.target_node_id = tn2.id
            JOIN expanded ex ON (
                e2.source_node_id = ex.target_node_id
                OR e2.target_node_id = ex.source_node_id
            )
            WHERE ex.depth < :max_depth
                AND e2.project_id = :project_id
        )
        SELECT DISTINCT ON (source_name, target_name, relation_type)
            source_name, target_name, relation_type,
            description, weight, confidence
        FROM expanded
        ORDER BY source_name, target_name, relation_type, depth
    """)

    result = await session.execute(
        cte_query,
        {
            "project_id": str(project_id),
            "seed_names": node_names,
            "max_depth": max_depth,
        },
    )

    return [
        EdgeContext(
            source_name=row[0],
            target_name=row[1],
            relation_type=row[2],
            description=row[3],
            weight=float(row[4]),
            confidence=row[5],
        )
        for row in result.all()
    ]


def _build_local_context(
    nodes: list[NodeContext],
    edges: list[EdgeContext],
) -> str:
    """Format nodes and edges into a text block for synthesis."""
    lines: list[str] = ["=== ENTITIES ==="]

    for node in nodes:
        lines.append(
            f"- {node.name} [{node.entity_type}] (relevance: {node.score:.2f}): "
            f"{node.description}"
        )

    if edges:
        lines.append("\n=== RELATIONS ===")
        for edge in edges:
            lines.append(
                f"- {edge.source_name} --[{edge.relation_type}]--> "
                f"{edge.target_name}: {edge.description} "
                f"(confidence: {edge.confidence})"
            )

    return "\n".join(lines)


async def local_query(
    session: AsyncSession,
    project_id: UUID,
    question: str,
) -> KnowledgeAnswer:
    """LOCAL query: embed → pgvector → CTE expand → synthesis."""
    query_embedding = await _get_query_embedding(question)

    similar_nodes = await _find_similar_nodes(session, project_id, query_embedding)

    if not similar_nodes:
        return KnowledgeAnswer(
            answer="No relevant entities found in the knowledge graph.",
            confidence_level="LOW",
            citations=[],
        )

    node_names = [n.name for n in similar_nodes]
    edges = await _expand_edges(session, project_id, node_names)

    context = _build_local_context(similar_nodes, edges)

    logger.info(
        "local_query_executing",
        project_id=str(project_id),
        nodes_found=len(similar_nodes),
        edges_expanded=len(edges),
    )

    return await asyncio.to_thread(_synthesize_sync, context, question)


async def global_query(
    session: AsyncSession,
    project_id: UUID,
    question: str,
) -> KnowledgeAnswer:
    """Execute a GLOBAL query: community summaries → synthesis."""
    # Fetch community summaries by aggregating node data per community.
    stmt = (
        select(
            GraphNode.community_id,
            func.count(GraphNode.id).label("member_count"),
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

    if not rows:
        return KnowledgeAnswer(
            answer="No community structure found in the knowledge graph.",
            confidence_level="LOW",
            citations=[],
        )

    communities: list[CommunityInfo] = []
    context_lines = ["=== COMMUNITY SUMMARIES ==="]

    for community_id, member_count, names, descriptions in rows:
        summary_parts = [f"{name}: {desc}" for name, desc in zip(names, descriptions)]
        summary = f"Community {community_id} ({member_count} members): " + "; ".join(
            summary_parts
        )
        context_lines.append(f"- {summary}")
        communities.append(
            CommunityInfo(
                community_id=int(community_id),
                summary=summary,
                member_count=int(member_count),
            )
        )

    context = "\n".join(context_lines)

    logger.info(
        "global_query_executing",
        project_id=str(project_id),
        communities_found=len(communities),
    )

    answer = await asyncio.to_thread(_synthesize_sync, context, question)

    # Enrich citations with community source info.
    if answer.citations:
        enriched = [
            AnswerCitation(
                document_id=c.document_id,
                snippet=c.snippet,
                source=c.source or "graph_community",
            )
            for c in answer.citations
        ]
        object.__setattr__(answer, "citations", enriched)

    return answer


async def hybrid_query(
    session: AsyncSession,
    project_id: UUID,
    question: str,
) -> KnowledgeAnswer:
    """Execute a HYBRID query: Local → check confidence → Global if needed → merge.

    This is the default query mode. Falls back gracefully to local-only
    if community structure is not yet available.
    """
    local_answer = await local_query(session, project_id, question)

    # If local confidence is sufficient, return immediately.
    if local_answer.confidence_level == "HIGH":
        logger.info(
            "hybrid_query_local_sufficient",
            project_id=str(project_id),
            confidence=local_answer.confidence_level,
        )
        return local_answer

    # Escalate to global query.
    try:
        global_answer = await global_query(session, project_id, question)
    except Exception:  # noqa: BLE001
        logger.warning(
            "hybrid_query_global_fallback_failed",
            project_id=str(project_id),
        )
        return local_answer

    # If global didn't improve confidence, prefer local.
    if global_answer.confidence_level == "LOW":
        return local_answer

    # Merge: prefer the answer with higher confidence.
    confidence_rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
    local_rank = confidence_rank.get(local_answer.confidence_level, 0)
    global_rank = confidence_rank.get(global_answer.confidence_level, 0)

    if global_rank > local_rank:
        # Merge local citations into global answer.
        merged_citations = list(global_answer.citations) + [
            c for c in local_answer.citations if c not in global_answer.citations
        ]
        object.__setattr__(global_answer, "citations", merged_citations)
        logger.info(
            "hybrid_query_global_preferred",
            project_id=str(project_id),
            local_confidence=local_answer.confidence_level,
            global_confidence=global_answer.confidence_level,
        )
        return global_answer

    logger.info(
        "hybrid_query_local_preferred",
        project_id=str(project_id),
        local_confidence=local_answer.confidence_level,
        global_confidence=global_answer.confidence_level,
    )
    return local_answer
